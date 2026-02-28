"""
Recommendation engine abstraction (SUGGEST-003).

Provides a stable strategy interface so ranking logic can be swapped between
algorithmic scoring and future LLM-based prioritization without changing the
API contract or controller code.

Engines:
  AlgorithmicRecommendationEngine  — current deterministic scorer (default)
  LLMRecommendationEngine          — placeholder; post-processes algorithmic
                                     output with narrative why text. No external
                                     API is called in this implementation.

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


class LLMRecommendationEngine(RecommendationEngine):
    """
    Placeholder LLM engine (SUGGEST-003).

    Currently passes through algorithmic ranking and post-processes the `why`
    text into a more narrative, conversational style. No external LLM API is
    called in this implementation — integration is deferred to a future ticket.

    Output contract is identical to AlgorithmicRecommendationEngine:
    same Ranked dataclass, same response shape.
    """

    NAME = "llm_placeholder"

    def recommend(self, ctx: RecommendationContext) -> List[Ranked]:
        ranked = prioritize_tasks(
            ctx.tasks,
            db=ctx.db,
            energy=ctx.energy,
            time_window=ctx.time_window,
        )
        top = ranked[: max(1, ctx.limit)]

        result = [
            Ranked(
                task=r.task,
                raw=r.raw,
                score=r.score,
                factors=r.factors,
                why=_to_narrative(r.why),
            )
            for r in top
        ]

        logger.info(
            "engine=%s candidates=%d returned=%d energy=%s time_window=%s",
            self.NAME, len(ctx.tasks), len(result), ctx.energy, ctx.time_window,
        )
        for r in result:
            logger.debug("task_id=%s score=%.2f why=%r", r.task.id, r.score, r.why)

        return result


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
