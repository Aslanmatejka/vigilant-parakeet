"""
AGENT_V2 — Procedural rule persistence tests
=============================================

Verifies `procedural_store.upsert_*` shapes the correct Supabase payload
and `fetch_*` decodes RPC/REST rows back into the pure dataclasses. All
Supabase interactions are stubbed.

Run:
    python -m pytest backend/tests/test_agent_v2_procedural_store.py -v
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from backend.agent import procedural_store as store
from backend.agent.procedural import AntiPatternRule, ProceduralRule


USER = "aaaaaaaa-0000-0000-0000-000000000001"


def _rule(intent="find_food", action="search_food_near_user"):
    return ProceduralRule(
        intent=intent, action=action, support_count=6,
        mean_reward=0.7, mean_confidence=0.85, success_rate=0.9,
        confidence=0.75, sample_summaries=["s1", "s2"],
    )


def _anti(intent="claim_food", action="claim_expired"):
    return AntiPatternRule(
        intent=intent, action=action, support_count=4,
        mean_reward=-0.4, mean_confidence=0.6,
        failure_rate=0.8, success_rate=0.2, severity=0.65,
        sample_summaries=["bad-1"],
    )


# ============================================================================
# _rule_row / _anti_row pure builders
# ============================================================================

class TestRowBuilders:
    def test_rule_row_shape(self):
        row = store._rule_row(USER, _rule(), "run-1")
        assert row["user_id"] == USER
        assert row["intent"] == "find_food"
        assert row["action"] == "search_food_near_user"
        assert row["support_count"] == 6
        assert row["confidence"] == pytest.approx(0.75)
        assert row["run_id"] == "run-1"

    def test_rule_row_omits_run_id_when_missing(self):
        row = store._rule_row(USER, _rule(), None)
        assert "run_id" not in row

    def test_rule_row_supports_global(self):
        row = store._rule_row(None, _rule(), None)
        assert row["user_id"] is None

    def test_anti_row_shape(self):
        row = store._anti_row(USER, _anti(), None)
        assert row["intent"] == "claim_food"
        assert row["failure_rate"] == pytest.approx(0.8)
        assert row["severity"] == pytest.approx(0.65)

    def test_string_fields_capped(self):
        long_intent = "x" * 500
        long_action = "y" * 500
        r = ProceduralRule(
            intent=long_intent, action=long_action, support_count=1,
            mean_reward=0.1, mean_confidence=0.1, success_rate=0.5,
            confidence=0.1,
        )
        row = store._rule_row(USER, r, None)
        assert len(row["intent"]) <= 120
        assert len(row["action"]) <= 140


# ============================================================================
# fetch_procedural_rules — decodes rows into dataclasses
# ============================================================================

class TestFetch:
    def test_fetch_procedural_decodes_rows(self, monkeypatch):
        async def _fake_get(table, params):
            assert table == "agent_procedural_rules"
            # Ensure "or" clause covers user + NULL when user_id set.
            assert "or" in params
            return [
                {
                    "id": "r-1", "user_id": USER,
                    "intent": "find_food", "action": "search_food_near_user",
                    "support_count": 3, "mean_reward": 0.5,
                    "mean_confidence": 0.6, "success_rate": 0.75,
                    "confidence": 0.7, "sample_summaries": ["hit"],
                },
            ]
        import backend.ai_engine as ai_engine
        monkeypatch.setattr(ai_engine, "supabase_get", _fake_get, raising=False)

        rows = asyncio.run(store.fetch_procedural_rules(USER, intent="find_food"))
        assert len(rows) == 1
        assert isinstance(rows[0], ProceduralRule)
        assert rows[0].confidence == pytest.approx(0.7)

    def test_fetch_procedural_returns_empty_on_error(self, monkeypatch):
        async def _boom(table, params): raise RuntimeError("db down")
        import backend.ai_engine as ai_engine
        monkeypatch.setattr(ai_engine, "supabase_get", _boom, raising=False)

        rows = asyncio.run(store.fetch_procedural_rules(USER))
        assert rows == []

    def test_fetch_antipattern_decodes_rows(self, monkeypatch):
        async def _fake_get(table, params):
            assert table == "agent_procedural_antipatterns"
            return [
                {
                    "id": "a-1", "user_id": USER,
                    "intent": "claim_food", "action": "claim_expired",
                    "support_count": 2, "mean_reward": -0.5,
                    "mean_confidence": 0.5, "failure_rate": 0.9,
                    "success_rate": 0.1, "severity": 0.72,
                    "sample_summaries": [],
                },
            ]
        import backend.ai_engine as ai_engine
        monkeypatch.setattr(ai_engine, "supabase_get", _fake_get, raising=False)

        rows = asyncio.run(store.fetch_antipattern_rules(USER, intent="claim_food"))
        assert len(rows) == 1
        assert isinstance(rows[0], AntiPatternRule)
        assert rows[0].severity == pytest.approx(0.72)

    def test_fetch_global_only_when_user_id_none(self, monkeypatch):
        captured: dict[str, Any] = {}
        async def _fake_get(table, params):
            captured["params"] = dict(params)
            return []
        import backend.ai_engine as ai_engine
        monkeypatch.setattr(ai_engine, "supabase_get", _fake_get, raising=False)

        asyncio.run(store.fetch_procedural_rules(None))
        # Global query must use `user_id=is.null`, not an OR.
        assert captured["params"].get("user_id") == "is.null"
        assert "or" not in captured["params"]


# ============================================================================
# upsert helpers — split per-user vs global, both use httpx POST
# ============================================================================

class TestUpsert:
    def test_upsert_procedural_splits_scopes(self, monkeypatch):
        calls: list[tuple[str, str, list]] = []

        class _Resp:
            status_code = 201
            def raise_for_status(self): return None
            def json(self): return [{"id": "x"}]

        class _Client:
            def __init__(self, *a, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return None
            async def post(self, url, params=None, json=None, headers=None):
                calls.append((url, params.get("on_conflict"), list(json)))
                return _Resp()

        import httpx
        monkeypatch.setattr(httpx, "AsyncClient", _Client)
        import backend.ai_engine as ai_engine
        monkeypatch.setattr(ai_engine, "SUPABASE_URL", "http://fake.supabase", raising=False)
        monkeypatch.setattr(ai_engine, "SUPABASE_SERVICE_KEY", "key", raising=False)
        monkeypatch.setattr(ai_engine, "SUPABASE_TIMEOUT", 5, raising=False)

        # One per-user + one global.
        rules = [_rule()]
        written = asyncio.run(store.upsert_procedural_rules(USER, rules))
        assert written == 1
        assert len(calls) == 1
        assert calls[0][1] == "user_id,intent,action"

        calls.clear()
        written = asyncio.run(store.upsert_procedural_rules(None, rules))
        assert written == 1
        assert calls[0][1] == "intent,action"

    def test_upsert_returns_zero_on_error(self, monkeypatch):
        class _Client:
            def __init__(self, *a, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return None
            async def post(self, *a, **kw):
                raise RuntimeError("db unreachable")

        import httpx
        monkeypatch.setattr(httpx, "AsyncClient", _Client)
        import backend.ai_engine as ai_engine
        monkeypatch.setattr(ai_engine, "SUPABASE_URL", "http://fake", raising=False)
        monkeypatch.setattr(ai_engine, "SUPABASE_SERVICE_KEY", "key", raising=False)
        monkeypatch.setattr(ai_engine, "SUPABASE_TIMEOUT", 5, raising=False)

        written = asyncio.run(store.upsert_procedural_rules(USER, [_rule()]))
        assert written == 0

    def test_upsert_empty_list_is_noop(self):
        written = asyncio.run(store.upsert_procedural_rules(USER, []))
        assert written == 0
