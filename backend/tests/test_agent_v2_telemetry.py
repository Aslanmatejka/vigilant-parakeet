"""
AGENT_V2 — Telemetry row-builder tests
======================================

Verify `build_v2_telemetry_row` distills the v2 response payload into the
exact shape the migration expects, and that `log_v2_turn` is safe to call
on anonymous / broken responses.

Run:
    python -m pytest backend/tests/test_agent_v2_telemetry.py -v
"""

from __future__ import annotations

import asyncio

import pytest

from backend.agent.telemetry import build_v2_telemetry_row, log_v2_turn


USER = "11111111-2222-3333-4444-555555555555"
NIL = "00000000-0000-0000-0000-000000000000"


def _fat_response(**overrides):
    """Approximate the shape of `invoke_agent_v2`'s return dict."""
    base = {
        "text": "Here's what I found.",
        "user_id": USER,
        "conversation_id": "conv-1",
        "turn_id": "turn-1",
        "affect": {"dominant": "frustrated"},
        "register": {"tone": "deescalating"},
        "reflection": {"outcome": "success"},
        "self_eval": {"overall": 0.82},
        "persona_check": {"ok": True, "issues": []},
        "reasoning_trace": [{"intent": "find_food", "confidence": 0.9}],
        "confidence": 0.9,
        "reward": 0.7,
        "retried": False,
        "pushback_detected": False,
        "brainstorm_used": False,
        "curiosity_followup": None,
        "confirmation_recommended": False,
        "blocked_listings": [],
        "tool_results": [
            {"tool": "search_food", "result": {"success": True}},
            {"tool": "flaky", "result": {"error": "boom"}},
        ],
        "memories": [{"content": "vegan"}],
        "new_memories": [],
        "goals": [
            {"status": "open"},
            {"status": "done"},
            {"status": "in_progress"},
        ],
        "few_shot_examples": [{"turn_id": "x"}],
        "_elapsed_ms": 1234,
    }
    base.update(overrides)
    return base


class TestBuildRow:
    def test_shape_all_present(self, monkeypatch):
        monkeypatch.setenv("AGENT_V2", "true")
        monkeypatch.setenv("AGENT_V2_ROLLOUT_PCT", "100")
        row = build_v2_telemetry_row(_fat_response())
        assert row["user_id"] == USER
        assert row["conversation_id"] == "conv-1"
        assert row["turn_id"] == "turn-1"
        assert row["detected_intent"] == "find_food"
        assert row["confidence"] == pytest.approx(0.9)
        assert row["affect_dominant"] == "frustrated"
        assert row["register_tone"] == "deescalating"
        assert row["reflection_outcome"] == "success"
        assert row["self_eval_overall"] == pytest.approx(0.82)
        assert row["reward"] == pytest.approx(0.7)
        assert row["tool_success_count"] == 1
        assert row["tool_failure_count"] == 1
        assert row["memories_retrieved"] == 1
        assert row["memories_written"] == 0
        assert row["open_goals"] == 2  # open + in_progress
        assert row["few_shot_examples"] == 1
        assert row["elapsed_ms"] == 1234
        # Rollout snapshot embedded.
        assert row["rollout_pct"] == 100
        assert 0 <= row["rollout_bucket"] < 100

    def test_missing_fields_default(self):
        row = build_v2_telemetry_row({"user_id": USER, "text": ""})
        assert row["response_length"] == 0
        assert row["tool_success_count"] == 0
        assert row["tool_failure_count"] == 0
        assert row["retried"] is False
        assert row["persona_ok"] is True
        assert row["elapsed_ms"] == 0

    def test_string_capping(self):
        long_intent = "x" * 500
        resp = _fat_response(
            reasoning_trace=[{"intent": long_intent, "confidence": 0.5}]
        )
        row = build_v2_telemetry_row(resp)
        assert row["detected_intent"] is not None
        assert len(row["detected_intent"]) <= 60


class TestLogV2Turn:
    def test_skips_anonymous(self):
        # Should not raise, and (because we don't mock supabase_post) it
        # simply returns after the anonymous check.
        asyncio.run(log_v2_turn({"user_id": NIL}))
        asyncio.run(log_v2_turn({"user_id": None}))
        asyncio.run(log_v2_turn({}))

    def test_swallows_supabase_errors(self, monkeypatch):
        """If supabase_post blows up, log_v2_turn must not propagate."""
        async def _bad_post(*_a, **_kw):
            raise RuntimeError("db down")

        import backend.ai_engine as ai_engine
        monkeypatch.setattr(ai_engine, "supabase_post", _bad_post, raising=False)
        # Must not raise.
        asyncio.run(log_v2_turn(_fat_response()))
