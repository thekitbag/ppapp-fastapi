"""Tests for the RecommendationEngine strategy abstraction (SUGGEST-003 / SUGGEST-004)."""
import logging
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.models import Goal, GoalStatusEnum, Task, TaskGoal, User, ProviderEnum
from app.services.llm_recommendation_provider import LLMProviderError
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


def _make_task(size=None, status="backlog", energy=None, user_id="engine-user-1"):
    return Task(
        id=f"task_{_uid()}",
        title="Test Task",
        user_id=user_id,
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


class _StubProvider:
    """Injectable stub for LLMRecommendationEngine tests."""

    def __init__(self, response=None, raises=None):
        self.response = response
        self.raises = raises

    def call(self, context):
        if self.raises:
            raise self.raises
        return self.response


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
        """With no provider (no API key), engine falls back to algorithmic."""
        tasks = [_make_task(), _make_task()]
        engine = LLMRecommendationEngine(_provider=None)
        result = engine.recommend(_ctx(tasks))
        assert len(result) > 0
        for r in result:
            assert hasattr(r, "task")
            assert hasattr(r, "score")
            assert hasattr(r, "factors")
            assert hasattr(r, "why")

    def test_respects_limit(self):
        """Fallback path respects limit."""
        tasks = [_make_task() for _ in range(8)]
        engine = LLMRecommendationEngine(_provider=None)
        result = engine.recommend(_ctx(tasks, limit=4))
        assert len(result) == 4

    def test_factors_unchanged_from_algorithmic(self):
        """LLM engine preserves algorithmic factors on the LLM-selected item."""
        today_task = _make_task(size=3, status="today")
        stub = _StubProvider(response={
            "task_id": today_task.id,
            "score": 85,
            "why": "This task is ready and aligned with your goals.",
        })
        engine = LLMRecommendationEngine(_provider=stub)
        ctx = _ctx([today_task], limit=1)

        llm_result = engine.recommend(ctx)
        algo_result = AlgorithmicRecommendationEngine().recommend(ctx)

        assert llm_result[0].factors == algo_result[0].factors


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
        assert engine.NAME == "llm"

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


# ---------------------------------------------------------------------------
# Real LLM engine tests (SUGGEST-004)
# ---------------------------------------------------------------------------

class TestLLMEngineReal:
    """
    Tests for the real LLMRecommendationEngine behaviour.

    Tests 1 uses the test_db fixture. Tests 2–8 use in-memory Task objects and
    _StubProvider to avoid any network calls.
    """

    # ------------------------------------------------------------------
    # Test 1: tenant isolation via context assembler
    # ------------------------------------------------------------------

    def test_tenant_isolation(self, test_db):
        """
        Context assembler must only include user_a's goals — never user_b's.
        """
        from app.services.recommendation_context_assembler import (
            RecommendationContextAssembler,
        )

        # Create users
        user_a = User(
            id="iso-user-a",
            provider=ProviderEnum.google,
            provider_sub="iso-sub-a",
            email="iso-a@example.com",
            name="User A",
        )
        user_b = User(
            id="iso-user-b",
            provider=ProviderEnum.google,
            provider_sub="iso-sub-b",
            email="iso-b@example.com",
            name="User B",
        )
        test_db.add_all([user_a, user_b])
        test_db.commit()

        # Create goals
        goal_a = Goal(
            id="goal-a-1",
            title="User A Goal",
            user_id="iso-user-a",
        )
        goal_b = Goal(
            id="goal-b-1",
            title="User B Goal",
            user_id="iso-user-b",
        )
        test_db.add_all([goal_a, goal_b])
        test_db.commit()

        # Create task for user_a linked to goal_a
        task_a = Task(
            id="task-a-1",
            title="User A Task",
            user_id="iso-user-a",
            status="today",
            sort_order=0.0,
            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
        test_db.add(task_a)
        test_db.commit()

        tg = TaskGoal(
            id=f"tg-{_uid()}",
            task_id="task-a-1",
            goal_id="goal-a-1",
            user_id="iso-user-a",
        )
        test_db.add(tg)
        test_db.commit()

        # Assemble context for user_a
        assembler = RecommendationContextAssembler(test_db, "iso-user-a")
        context = assembler.assemble([task_a], energy=None, time_window=None)

        # Extract all goal IDs that appear in context
        goal_ids_in_context = {g["id"] for g in context["goals"]}
        for task_summary in context["tasks"]:
            for lg in task_summary["linked_goals"]:
                goal_ids_in_context.add(lg["id"])

        assert "goal-a-1" in goal_ids_in_context
        assert "goal-b-1" not in goal_ids_in_context

    # ------------------------------------------------------------------
    # Test 2: successful LLM path
    # ------------------------------------------------------------------

    def test_llm_success_path(self):
        today_task = _make_task(status="today")
        backlog_task = _make_task(status="backlog")

        stub = _StubProvider(response={
            "task_id": today_task.id,
            "score": 91,
            "why": "This task is urgent and aligns with your current goal.",
        })
        engine = LLMRecommendationEngine(_provider=stub)
        result = engine.recommend(_ctx([today_task, backlog_task], limit=5))

        assert result[0].task.id == today_task.id
        assert result[0].score == 91

    # ------------------------------------------------------------------
    # Test 3: missing API key → fallback
    # ------------------------------------------------------------------

    def test_missing_api_key_fallback(self, caplog):
        """Engine with no injected provider and no API key in settings falls back."""
        tasks = [_make_task(status="today")]
        # Pass _provider=None explicitly; settings.llm_api_key is None in test env
        engine = LLMRecommendationEngine(_provider=None)

        with caplog.at_level(logging.INFO, logger="app.services.recommendation_engine"):
            result = engine.recommend(_ctx(tasks))

        assert len(result) > 0
        assert "missing_api_key" in caplog.text

    # ------------------------------------------------------------------
    # Test 4: transport error → fallback
    # ------------------------------------------------------------------

    def test_transport_error_fallback(self, caplog):
        stub = _StubProvider(raises=LLMProviderError("timeout"))
        today_task = _make_task(status="today")
        engine = LLMRecommendationEngine(_provider=stub)

        with caplog.at_level(logging.INFO, logger="app.services.recommendation_engine"):
            result = engine.recommend(_ctx([today_task]))

        assert len(result) > 0
        assert "llm_request_failed" in caplog.text

    # ------------------------------------------------------------------
    # Test 4b: unexpected exception from provider → fallback (not 500)
    # ------------------------------------------------------------------

    def test_unexpected_provider_exception_fallback(self, caplog):
        stub = _StubProvider(raises=RuntimeError("provider bug"))
        today_task = _make_task(status="today")
        engine = LLMRecommendationEngine(_provider=stub)

        with caplog.at_level(logging.INFO, logger="app.services.recommendation_engine"):
            result = engine.recommend(_ctx([today_task]))

        assert len(result) > 0
        assert "unexpected error" in caplog.text
        assert "llm_request_failed" in caplog.text

    # ------------------------------------------------------------------
    # Test 5: invalid response (missing fields) → fallback
    # ------------------------------------------------------------------

    def test_invalid_response_fallback(self, caplog):
        stub = _StubProvider(response={})  # no task_id, score, why
        today_task = _make_task(status="today")
        engine = LLMRecommendationEngine(_provider=stub)

        with caplog.at_level(logging.INFO, logger="app.services.recommendation_engine"):
            result = engine.recommend(_ctx([today_task]))

        assert len(result) > 0
        assert "invalid_response" in caplog.text

    # ------------------------------------------------------------------
    # Test 6: unknown task_id in response → fallback
    # ------------------------------------------------------------------

    def test_unknown_task_id_fallback(self, caplog):
        stub = _StubProvider(response={
            "task_id": "nonexistent-id-xyz",
            "score": 80,
            "why": "Great task.",
        })
        today_task = _make_task(status="today")
        engine = LLMRecommendationEngine(_provider=stub)

        with caplog.at_level(logging.INFO, logger="app.services.recommendation_engine"):
            result = engine.recommend(_ctx([today_task]))

        assert len(result) > 0
        assert "unknown_task_id" in caplog.text

    # ------------------------------------------------------------------
    # Test 7: no today/week candidates → fallback
    # ------------------------------------------------------------------

    def test_empty_today_week_fallback(self, caplog):
        stub = _StubProvider(response={"task_id": "x", "score": 90, "why": "Fine."})
        backlog_task = _make_task(status="backlog")
        engine = LLMRecommendationEngine(_provider=stub)

        with caplog.at_level(logging.INFO, logger="app.services.recommendation_engine"):
            result = engine.recommend(_ctx([backlog_task]))

        assert len(result) > 0
        assert result[0].task.id == backlog_task.id
        assert "empty_candidate_set" in caplog.text

    # ------------------------------------------------------------------
    # Test 8: limit behaviour
    # ------------------------------------------------------------------

    def test_limit_behavior(self):
        today_task_1 = _make_task(status="today")
        today_task_2 = _make_task(status="today")
        backlog_1 = _make_task(status="backlog")
        backlog_2 = _make_task(status="backlog")
        backlog_3 = _make_task(status="backlog")

        stub = _StubProvider(response={
            "task_id": today_task_1.id,
            "score": 95,
            "why": "Top priority task.",
        })
        engine = LLMRecommendationEngine(_provider=stub)
        all_tasks = [today_task_1, today_task_2, backlog_1, backlog_2, backlog_3]
        result = engine.recommend(_ctx(all_tasks, limit=3))

        assert len(result) == 3
        assert result[0].task.id == today_task_1.id
        # No duplicate IDs
        result_ids = [r.task.id for r in result]
        assert len(result_ids) == len(set(result_ids))
