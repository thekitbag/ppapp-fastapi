"""
Recommendation engine abstraction (SUGGEST-003 / SUGGEST-004).

Provides a stable strategy interface so ranking logic can be swapped between
algorithmic scoring and LLM-based prioritization without changing the API
contract or controller code.

Engines:
  AlgorithmicRecommendationEngine  — deterministic weighted-factor scorer (default)
  LLMRecommendationEngine          — calls an OpenAI-compatible API for the top
                                     pick; falls back to algorithmic on any failure.

Usage:
  engine = get_recommendation_engine(settings.use_llm_prioritization)
  ranked = engine.recommend(ctx)
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy.orm import Session

from app import models
from app.services.recommendations import Ranked, prioritize_tasks

logger = logging.getLogger(__name__)


@dataclass
class RecommendationContext:
    """
    Canonical request context passed to any recommendation engine.

    Centralising inputs here means both engines receive identical data and
    future engines can be added without touching the controller layer.
    """
    tasks: List[models.Task]
    db: Session
    energy: Optional[str]
    time_window: Optional[int]
    limit: int


class RecommendationEngine(ABC):
    """Abstract base for recommendation strategies."""

    NAME: str = "base"

    @abstractmethod
    def recommend(self, ctx: RecommendationContext) -> List[Ranked]:
        """
        Rank candidate tasks and return up to ctx.limit results.

        Guarantees:
        - Returns at least 1 item if ctx.tasks is non-empty.
        - Each Ranked item contains: task, score, factors, why.
        - Items are sorted descending by score.
        """
        ...


class AlgorithmicRecommendationEngine(RecommendationEngine):
    """
    Deterministic scorer using weighted factor model.
    Wraps prioritize_tasks() — all SUGGEST-002 weights and factors apply.
    """

    NAME = "algorithmic"

    def recommend(self, ctx: RecommendationContext) -> List[Ranked]:
        ranked = prioritize_tasks(
            ctx.tasks,
            db=ctx.db,
            energy=ctx.energy,
            time_window=ctx.time_window,
        )
        result = ranked[: max(1, ctx.limit)]

        logger.info(
            "engine=%s candidates=%d returned=%d energy=%s time_window=%s",
            self.NAME, len(ctx.tasks), len(result), ctx.energy, ctx.time_window,
        )
        for r in result:
            logger.debug("task_id=%s score=%.2f why=%r", r.task.id, r.score, r.why)

        return result


# Status values that are eligible for LLM candidate selection
_LLM_CANDIDATE_STATUSES = {"today", "week"}


class LLMRecommendationEngine(RecommendationEngine):
    """
    LLM-powered engine (SUGGEST-004).

    Selects the top task via an OpenAI-compatible API call; fills remaining
    slots from the algorithmic ranking of the full candidate pool.

    Fallback: any failure (missing key, empty candidates, transport error,
    invalid response) falls back to the full algorithmic ranking, logging the
    reason at INFO level.

    The LLM provider is injectable via __init__ for testing.
    """

    NAME = "llm"

    def __init__(self, _provider=None) -> None:
        # Allow test injection; production builds the provider lazily in recommend()
        self._injected_provider = _provider

    def _build_provider(self):
        """
        Return the provider to use for this request.

        Priority order:
        1. Injected provider (tests / explicit override)
        2. Provider built from settings if LLM_API_KEY is configured
        3. None → caller must fall back to algorithmic
        """
        if self._injected_provider is not None:
            return self._injected_provider

        from app.core.config import settings
        from app.services.llm_recommendation_provider import LLMRecommendationProvider

        if not settings.llm_api_key:
            return None

        return LLMRecommendationProvider(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout_seconds,
        )

    def _fallback(
        self,
        ctx: RecommendationContext,
        reason: str,
    ) -> List[Ranked]:
        """Run algorithmic ranking and log why LLM was not used."""
        ranked = prioritize_tasks(
            ctx.tasks,
            db=ctx.db,
            energy=ctx.energy,
            time_window=ctx.time_window,
        )
        result = ranked[: max(1, ctx.limit)]

        logger.info(
            "engine=%s candidates=%d returned=%d energy=%s time_window=%s "
            "llm_attempted=False llm_success=False fallback_reason=%s",
            self.NAME, len(ctx.tasks), len(result),
            ctx.energy, ctx.time_window, reason,
        )
        for r in result:
            logger.debug("task_id=%s score=%.2f why=%r", r.task.id, r.score, r.why)

        return result

    def recommend(self, ctx: RecommendationContext) -> List[Ranked]:  # noqa: C901
        from app.services.llm_recommendation_provider import LLMProviderError
        from app.services.recommendation_context_assembler import (
            RecommendationContextAssembler,
        )

        # Step 1: resolve provider
        provider = self._build_provider()
        if provider is None:
            return self._fallback(ctx, "missing_api_key")

        # Step 2: narrow candidates to today/week statuses
        llm_candidates = [
            t for t in ctx.tasks
            if _status_str(t.status) in _LLM_CANDIDATE_STATUSES
        ]
        if not llm_candidates:
            return self._fallback(ctx, "empty_candidate_set")

        # Step 3: algorithmic ranking of the full pool (used for remainder slots)
        algo_ranked = prioritize_tasks(
            ctx.tasks,
            db=ctx.db,
            energy=ctx.energy,
            time_window=ctx.time_window,
        )
        algo_by_id = {r.task.id: r for r in algo_ranked}

        # Step 4: resolve user_id
        user_id = llm_candidates[0].user_id

        # Step 5: assemble context and call LLM
        context_dict = RecommendationContextAssembler(ctx.db, user_id).assemble(
            llm_candidates, ctx.energy, ctx.time_window
        )

        try:
            raw = provider.call(context_dict)
        except LLMProviderError:
            return self._fallback(ctx, "llm_request_failed")
        except Exception:
            logger.warning(
                "engine=%s unexpected error in provider.call; falling back",
                self.NAME, exc_info=True,
            )
            return self._fallback(ctx, "llm_request_failed")

        # Step 6 & 7: validate response
        llm_candidate_ids = {t.id for t in llm_candidates}

        try:
            task_id = raw["task_id"]
        except (KeyError, TypeError):
            return self._fallback(ctx, "invalid_response")

        if task_id not in llm_candidate_ids:
            return self._fallback(ctx, "unknown_task_id")

        try:
            llm_score = float(raw["score"])
            llm_score = max(0.0, min(100.0, llm_score))
        except (KeyError, TypeError, ValueError):
            return self._fallback(ctx, "invalid_response")

        try:
            llm_why = str(raw["why"]).strip()
        except (KeyError, TypeError):
            return self._fallback(ctx, "invalid_response")

        if not llm_why:
            return self._fallback(ctx, "invalid_response")

        # Step 8: build the LLM-selected Ranked item (keep algo factors)
        algo_item = algo_by_id.get(task_id)
        if algo_item is None:
            # task_id was in candidates but didn't survive algo ranking (shouldn't happen)
            return self._fallback(ctx, "invalid_response")

        selected_task = algo_item.task
        llm_item = Ranked(
            task=selected_task,
            raw=algo_item.raw,
            score=llm_score,
            factors=algo_item.factors,
            why=llm_why,
        )

        # Step 9: remainder = algo ranking excluding the LLM-selected task
        remainder = [r for r in algo_ranked if r.task.id != task_id]

        # Step 10: combine
        result = [llm_item] + remainder[: max(0, ctx.limit - 1)]

        # Step 11: structured log
        logger.info(
            "engine=%s candidates=%d returned=%d energy=%s time_window=%s "
            "llm_attempted=True llm_success=True fallback_reason=None",
            self.NAME, len(ctx.tasks), len(result), ctx.energy, ctx.time_window,
        )
        for r in result:
            logger.debug("task_id=%s score=%.2f why=%r", r.task.id, r.score, r.why)

        return result


def _status_str(status) -> str:
    """Return the string value of a status enum or string."""
    return status.value if hasattr(status, "value") else str(status)


def _to_narrative(why: str) -> str:
    """
    Convert terse factor-based why text into a more conversational sentence.

    Input:  "Due soon and linked goal is off target"
    Output: "Recommended because due soon and linked goal is off target."
    """
    if not why or why.lower().startswith("no strong signals"):
        return "This task has been waiting — it might be a good time to make progress on it."
    # Lower-case first char so it reads naturally mid-sentence
    return f"Recommended because {why[0].lower()}{why[1:]}."


def get_recommendation_engine(use_llm: bool = False) -> RecommendationEngine:
    """
    Factory: return the engine configured by the USE_LLM_PRIORITIZATION flag.

    Called once per request in the controller; strategy selection is centralised
    here so no branching leaks into endpoint or schema code.
    """
    if use_llm:
        return LLMRecommendationEngine()
    return AlgorithmicRecommendationEngine()
