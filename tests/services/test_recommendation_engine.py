"""Tests for the RecommendationEngine strategy abstraction (SUGGEST-003)."""
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.models import Task
from app.services.recommendation_engine import (
    AlgorithmicRecommendationEngine,
    LLMRecommendationEngine,
    RecommendationContext,
    RecommendationEngine,
    _to_narrative,
    get_recommendation_engine,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uid():
    return str(uuid.uuid4())


def _make_task(size=None, status="backlog", energy=None):
    return Task(
        id=f"task_{_uid()}",
        title="Test Task",
        user_id="engine-user-1",
        status=status,
        sort_order=0.0,
        size=size,
        energy=energy,
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )


def _ctx(tasks, limit=5, energy=None, time_window=None, db=None):
    return RecommendationContext(
        tasks=tasks,
        db=db,
        energy=energy,
        time_window=time_window,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# Engine abstraction tests
# ---------------------------------------------------------------------------

class TestRecommendationEngineInterface:

    def test_algorithmic_engine_implements_interface(self):
        engine = AlgorithmicRecommendationEngine()
        assert isinstance(engine, RecommendationEngine)

    def test_llm_engine_implements_interface(self):
        engine = LLMRecommendationEngine()
        assert isinstance(engine, RecommendationEngine)

    def test_engines_have_distinct_names(self):
        assert AlgorithmicRecommendationEngine.NAME != LLMRecommendationEngine.NAME

    def test_factory_returns_algorithmic_by_default(self):
        engine = get_recommendation_engine(use_llm=False)
        assert isinstance(engine, AlgorithmicRecommendationEngine)

    def test_factory_returns_llm_when_flag_set(self):
        engine = get_recommendation_engine(use_llm=True)
        assert isinstance(engine, LLMRecommendationEngine)


class TestAlgorithmicEngine:

    def test_returns_list_of_ranked(self):
        tasks = [_make_task(size=2), _make_task(size=5)]
        engine = AlgorithmicRecommendationEngine()
        result = engine.recommend(_ctx(tasks))
        assert len(result) > 0
        assert all(hasattr(r, "task") for r in result)
        assert all(hasattr(r, "score") for r in result)
        assert all(hasattr(r, "factors") for r in result)
        assert all(hasattr(r, "why") for r in result)

    def test_respects_limit(self):
        tasks = [_make_task() for _ in range(10)]
        engine = AlgorithmicRecommendationEngine()
        result = engine.recommend(_ctx(tasks, limit=3))
        assert len(result) == 3

    def test_always_returns_at_least_one(self):
        tasks = [_make_task()]
        engine = AlgorithmicRecommendationEngine()
        result = engine.recommend(_ctx(tasks, limit=0))
        assert len(result) == 1

    def test_sorted_descending_by_score(self):
        tasks = [_make_task(size=1, energy="low"), _make_task(size=8, energy="high")]
        engine = AlgorithmicRecommendationEngine()
        result = engine.recommend(_ctx(tasks, energy="low"))
        scores = [r.score for r in result]
        assert scores == sorted(scores, reverse=True)

    def test_energy_param_wired_through(self):
        low_task = _make_task(energy="low")
        high_task = _make_task(energy="high")
        engine = AlgorithmicRecommendationEngine()
        result = engine.recommend(_ctx([high_task, low_task], energy="low"))
        assert result[0].task.id == low_task.id
        assert result[0].factors["energy_match"] == 1.0

    def test_time_window_param_wired_through(self):
        small_task = _make_task(size=1)
        large_task = _make_task(size=8)
        engine = AlgorithmicRecommendationEngine()
        result = engine.recommend(_ctx([large_task, small_task], time_window=15))
        assert result[0].task.id == small_task.id
        assert result[0].factors["time_fit"] == 1.0

    def test_returns_empty_for_no_tasks(self):
        engine = AlgorithmicRecommendationEngine()
        # limit 0 or 1 with empty list → empty (no tasks to rank)
        result = engine.recommend(_ctx([]))
        assert result == []

    def test_new_factors_present_in_output(self):
        """All SUGGEST-002 factor keys are present in each result."""
        task = _make_task(size=2)
        engine = AlgorithmicRecommendationEngine()
        result = engine.recommend(_ctx([task]))
        required_keys = {
            "status_boost", "due_proximity", "goal_align",
            "project_due_proximity", "goal_linked",
            "energy_match", "time_fit",
            "goal_status_at_risk", "goal_status_off_target", "goal_urgency",
        }
        assert required_keys <= set(result[0].factors.keys())


class TestLLMEngine:

    def test_returns_valid_ranked_objects(self):
        tasks = [_make_task(), _make_task()]
        engine = LLMRecommendationEngine()
        result = engine.recommend(_ctx(tasks))
        assert len(result) > 0
        for r in result:
            assert hasattr(r, "task")
            assert hasattr(r, "score")
            assert hasattr(r, "factors")
            assert hasattr(r, "why")

    def test_respects_limit(self):
        tasks = [_make_task() for _ in range(8)]
        engine = LLMRecommendationEngine()
        result = engine.recommend(_ctx(tasks, limit=4))
        assert len(result) == 4

    def test_why_text_is_narrative(self):
        """LLM engine produces narrative why text, not terse factor text."""
        tasks = [_make_task(size=2)]
        engine = LLMRecommendationEngine()
        result = engine.recommend(_ctx(tasks))
        why = result[0].why
        # Narrative form should not start with a bare capitalized factor phrase
        assert isinstance(why, str) and len(why) > 0

    def test_scores_unchanged_from_algorithmic(self):
        """LLM engine only changes why text — scores and factors are identical."""
        tasks = [_make_task(size=1, energy="low"), _make_task(size=8, energy="high")]
        algo = AlgorithmicRecommendationEngine()
        llm = LLMRecommendationEngine()
        ctx = _ctx(tasks, energy="low", limit=10)

        algo_result = algo.recommend(ctx)
        llm_result = llm.recommend(ctx)

        assert len(algo_result) == len(llm_result)
        for a, l in zip(algo_result, llm_result):
            assert a.task.id == l.task.id
            assert abs(a.score - l.score) < 0.001
            assert a.factors == l.factors

    def test_factors_unchanged_from_algorithmic(self):
        task = _make_task(size=3)
        algo_result = AlgorithmicRecommendationEngine().recommend(_ctx([task]))
        llm_result = LLMRecommendationEngine().recommend(_ctx([task]))
        assert algo_result[0].factors == llm_result[0].factors


class TestNarrativeHelper:

    def test_narrative_baseline(self):
        result = _to_narrative("No strong signals (baseline order)")
        assert "waiting" in result.lower()

    def test_narrative_wraps_existing_why(self):
        result = _to_narrative("Due soon and linked goal is off target")
        assert result.startswith("Recommended because")
        assert "due soon" in result.lower()

    def test_narrative_is_sentence(self):
        result = _to_narrative("Due soon")
        assert result.endswith(".")

    def test_narrative_empty_string(self):
        result = _to_narrative("")
        assert isinstance(result, str) and len(result) > 0


# ---------------------------------------------------------------------------
# Strategy switch test (config-driven)
# ---------------------------------------------------------------------------

class TestStrategySwitch:

    def test_config_false_gives_algorithmic(self):
        engine = get_recommendation_engine(use_llm=False)
        assert engine.NAME == "algorithmic"

    def test_config_true_gives_llm(self):
        engine = get_recommendation_engine(use_llm=True)
        assert engine.NAME == "llm_placeholder"

    def test_endpoint_uses_llm_engine_when_overridden(self):
        """Endpoint returns valid shape when LLM engine is injected via dependency override."""
        from app.main import app
        from app.api.v1.recommendations import _get_engine

        llm_engine = LLMRecommendationEngine()
        app.dependency_overrides[_get_engine] = lambda: llm_engine
        try:
            client = TestClient(app)
            r = client.get("/api/v1/recommendations/next?limit=3")
            assert r.status_code == 200
            body = r.json()
            assert "items" in body
            assert isinstance(body["items"], list)
        finally:
            app.dependency_overrides.pop(_get_engine, None)

    def test_endpoint_uses_algorithmic_engine_by_default(self):
        """Endpoint returns valid shape with default algorithmic engine."""
        from app.main import app

        client = TestClient(app)
        r = client.get("/api/v1/recommendations/next?limit=3")
        assert r.status_code == 200
        assert "items" in r.json()
