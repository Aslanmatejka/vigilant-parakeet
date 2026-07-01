"""
AGENT_V2 — Learning & Adaptation Tests (Phase 6 lite)
======================================================

Unit tests for `backend.agent.adaptation`.

Scenarios:
  Pure helpers:
   1.  compute_reward — outcome map, self-eval scaling, tool signals,
        pushback/retried/persona/safety penalties, clamp at [-1, 1].
   2.  score_trajectory_similarity — empty / intent-match boost /
        token overlap / off-intent.
   3.  format_few_shot_examples — empty / limit honoured / block shape.

  Supabase-backed:
   4.  retrieve_similar_trajectories — nil-UUID short-circuit, empty
        table, min_reward filter, ranking by similarity * reward,
        intent boost in practice.
   5.  record_trajectory — happy path, nil-UUID skip, message
        summarisation, clamping fields.
   6.  summarise_user_style — empty / single-row / multi-row aggregate
        with EN/ES language preference + emoji + formality.

Run:
    python -m pytest backend/tests/test_agent_v2_learning.py -v
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest

from backend.agent.adaptation import (
    FEW_SHOT_MIN_REWARD,
    HIGH_REWARD_THRESHOLD,
    TrajectoryRecord,
    UserStyle,
    compute_reward,
    format_few_shot_examples,
    record_trajectory,
    retrieve_similar_trajectories,
    score_trajectory_similarity,
    summarise_user_style,
)


USER = "44444444-4444-4444-4444-444444444444"
NIL = "00000000-0000-0000-0000-000000000000"


# ============================================================================
# FakeSupabase — shared shape with the memory test suite.
# ============================================================================

class FakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {}

    @staticmethod
    def _matches(row: dict[str, Any], filters: dict[str, Any]) -> bool:
        for k, v in filters.items():
            if k in ("select", "limit", "order"):
                continue
            if not isinstance(v, str):
                continue
            if v.startswith("eq."):
                if str(row.get(k)) != v[3:]:
                    return False
        return True

    async def supabase_get(self, table: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        rows = list(self.tables.get(table, []))
        out = [r for r in rows if self._matches(r, params)]
        # Respect order=created_at.desc.
        order = params.get("order") or ""
        if "created_at" in order and ".desc" in order:
            out.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
        limit = params.get("limit")
        if limit:
            try:
                out = out[: int(limit)]
            except Exception:
                pass
        return out

    async def supabase_post(self, table: str, body: dict[str, Any]) -> list[dict[str, Any]]:
        rows = self.tables.setdefault(table, [])
        body = dict(body)
        body.setdefault("id", str(uuid.uuid4()))
        rows.append(body)
        return [body]


@pytest.fixture
def fake_supabase(monkeypatch: pytest.MonkeyPatch) -> FakeSupabase:
    fake = FakeSupabase()
    import backend.ai_engine as ai_engine

    monkeypatch.setattr(ai_engine, "supabase_get", fake.supabase_get, raising=False)
    monkeypatch.setattr(ai_engine, "supabase_post", fake.supabase_post, raising=False)
    return fake


# ============================================================================
# 1. compute_reward
# ============================================================================

def test_reward_success_clean_tool_high_eval_is_positive():
    r = compute_reward(
        reflection_outcome="success",
        self_eval_overall=0.90,
        pushback_detected=False,
        retried=False,
        succeeded_tools=1,
        failed_tools=0,
    )
    # outcome (+0.50) + eval (0.90*0.50 - 0.20 = +0.25) + clean tool (+0.10)
    assert r == pytest.approx(0.85, abs=0.02)
    assert r >= HIGH_REWARD_THRESHOLD


def test_reward_failed_all_tools_drops_below_zero():
    r = compute_reward(
        reflection_outcome="failed",
        self_eval_overall=0.30,
        pushback_detected=False,
        retried=False,
        succeeded_tools=0,
        failed_tools=2,
    )
    # outcome (-0.40) + eval (0.30*0.50 - 0.20 = -0.05) + all fail (-0.15)
    assert r == pytest.approx(-0.60, abs=0.02)
    assert r < 0.0


def test_reward_pushback_and_retried_penalties_apply():
    r_clean = compute_reward(
        reflection_outcome="success", self_eval_overall=0.80,
        pushback_detected=False, retried=False,
        succeeded_tools=1, failed_tools=0,
    )
    r_messy = compute_reward(
        reflection_outcome="success", self_eval_overall=0.80,
        pushback_detected=True, retried=True,
        succeeded_tools=1, failed_tools=0,
    )
    # pushback (-0.20) + retried (-0.10) = -0.30 difference
    assert r_clean - r_messy == pytest.approx(0.30, abs=0.001)


def test_reward_persona_and_safety_penalties_apply():
    r_clean = compute_reward(
        reflection_outcome="success", self_eval_overall=0.80,
        pushback_detected=False, retried=False,
        succeeded_tools=1, failed_tools=0,
        persona_ok=True, safe_text_changed=False,
    )
    r_messy = compute_reward(
        reflection_outcome="success", self_eval_overall=0.80,
        pushback_detected=False, retried=False,
        succeeded_tools=1, failed_tools=0,
        persona_ok=False, safe_text_changed=True,
    )
    assert r_clean - r_messy == pytest.approx(0.20, abs=0.001)


def test_reward_clamps_to_minus_one():
    # Drive every penalty.
    r = compute_reward(
        reflection_outcome="failed",
        self_eval_overall=0.0,
        pushback_detected=True,
        retried=True,
        succeeded_tools=0,
        failed_tools=3,
        persona_ok=False,
        safe_text_changed=True,
    )
    assert r >= -1.0
    assert r <= 0.0


def test_reward_clamps_to_plus_one():
    # Stack the positive signals; outcome=success already gives +0.50,
    # eval=1.0 gives +0.30, tool clean +0.10 → 0.90 max in current schema.
    r = compute_reward(
        reflection_outcome="success",
        self_eval_overall=1.0,
        pushback_detected=False,
        retried=False,
        succeeded_tools=2,
        failed_tools=0,
    )
    assert r <= 1.0
    assert r >= 0.85


def test_reward_unknown_outcome_is_zero_baseline():
    r = compute_reward(
        reflection_outcome="unknown",
        self_eval_overall=0.40,  # eval contribution = 0.0
        pushback_detected=False,
        retried=False,
        succeeded_tools=0,
        failed_tools=0,
    )
    assert r == pytest.approx(0.0, abs=0.01)


# ============================================================================
# 2. score_trajectory_similarity
# ============================================================================

def test_similarity_empty_query_falls_back_to_intent_match():
    s_match = score_trajectory_similarity("anything", "search_food", "", "search_food")
    s_miss = score_trajectory_similarity("anything", "search_food", "", "claim_food")
    assert s_match > 0.0
    assert s_miss == 0.0


def test_similarity_token_overlap_basic():
    s = score_trajectory_similarity(
        "I want to find rice tonight",
        "search_food",
        "find some rice please",
        "search_food",
    )
    # Has token overlap (find, rice) AND intent match — should be > 0.2
    assert s > 0.20


def test_similarity_intent_match_boosts_score():
    s_with_intent = score_trajectory_similarity(
        "find rice", "search_food", "find rice", "search_food",
    )
    s_without_intent = score_trajectory_similarity(
        "find rice", "search_food", "find rice", "claim_food",
    )
    assert s_with_intent > s_without_intent
    # Boost is +0.20
    assert s_with_intent - s_without_intent == pytest.approx(0.20, abs=0.01)


def test_similarity_no_overlap_no_intent_match_is_zero():
    s = score_trajectory_similarity(
        "completely different content",
        "intent_a",
        "totally unrelated query",
        "intent_b",
    )
    assert s == 0.0


# ============================================================================
# 3. format_few_shot_examples
# ============================================================================

def test_format_few_shot_empty_returns_empty_string():
    assert format_few_shot_examples([]) == ""
    assert format_few_shot_examples(None) == ""  # type: ignore[arg-type]


def test_format_few_shot_zero_limit_returns_empty():
    rec = TrajectoryRecord(message_summary="hi", action="x", outcome="success", reward=0.9)
    assert format_few_shot_examples([rec], limit=0) == ""


def test_format_few_shot_block_shape_and_limit():
    recs = [
        TrajectoryRecord(message_summary=f"msg {i}", action=f"act {i}",
                         outcome="success", reward=0.85)
        for i in range(5)
    ]
    out = format_few_shot_examples(recs, limit=2)
    assert out.startswith("<few_shot_examples>")
    assert out.endswith("</few_shot_examples>")
    # 2 examples → 4 lines (header, 2 items, footer)
    assert len(out.splitlines()) == 4
    assert "msg 0" in out
    assert "msg 1" in out
    assert "msg 2" not in out


# ============================================================================
# 4. retrieve_similar_trajectories (supabase-backed)
# ============================================================================

def test_retrieve_nil_uuid_returns_empty(fake_supabase: FakeSupabase):
    out = asyncio.run(retrieve_similar_trajectories(NIL, "find rice"))
    assert out == []


def test_retrieve_empty_user_returns_empty(fake_supabase: FakeSupabase):
    out = asyncio.run(retrieve_similar_trajectories("", "find rice"))
    assert out == []


def test_retrieve_empty_table_returns_empty(fake_supabase: FakeSupabase):
    out = asyncio.run(retrieve_similar_trajectories(USER, "find rice"))
    assert out == []


def test_retrieve_filters_below_min_reward(fake_supabase: FakeSupabase):
    fake_supabase.tables["agent_trajectories"] = [
        {
            "user_id": USER, "id": "a",
            "intent": "search_food", "message_summary": "find rice please",
            "action": "search", "outcome": "success",
            "reward": 0.10,  # below default 0.40 floor
            "confidence": 0.8, "language": "en",
            "retried": False, "pushback_detected": False,
            "created_at": "2026-06-28T10:00:00Z",
        },
        {
            "user_id": USER, "id": "b",
            "intent": "search_food", "message_summary": "find rice tonight",
            "action": "search", "outcome": "success",
            "reward": 0.80,
            "confidence": 0.9, "language": "en",
            "retried": False, "pushback_detected": False,
            "created_at": "2026-06-28T10:01:00Z",
        },
    ]
    out = asyncio.run(retrieve_similar_trajectories(
        USER, "find rice", query_intent="search_food",
    ))
    assert len(out) == 1
    assert out[0].id == "b"
    assert out[0].reward >= FEW_SHOT_MIN_REWARD


def test_retrieve_ranks_by_similarity_and_reward(fake_supabase: FakeSupabase):
    fake_supabase.tables["agent_trajectories"] = [
        # High reward but off-topic
        {
            "user_id": USER, "id": "stale",
            "intent": "list_food", "message_summary": "post a listing about apples",
            "action": "list", "outcome": "success",
            "reward": 0.95,
            "confidence": 0.9, "language": "en",
            "retried": False, "pushback_detected": False,
            "created_at": "2026-06-28T09:00:00Z",
        },
        # Lower reward but on-topic
        {
            "user_id": USER, "id": "match",
            "intent": "search_food", "message_summary": "find rice for tonight",
            "action": "search", "outcome": "success",
            "reward": 0.60,
            "confidence": 0.9, "language": "en",
            "retried": False, "pushback_detected": False,
            "created_at": "2026-06-28T10:00:00Z",
        },
    ]
    out = asyncio.run(retrieve_similar_trajectories(
        USER, "find rice", query_intent="search_food",
    ))
    # The on-topic match should win because the stale one has zero similarity.
    assert len(out) == 1
    assert out[0].id == "match"


def test_retrieve_respects_limit(fake_supabase: FakeSupabase):
    fake_supabase.tables["agent_trajectories"] = [
        {
            "user_id": USER, "id": f"r{i}",
            "intent": "search_food", "message_summary": f"find rice {i}",
            "action": "search", "outcome": "success",
            "reward": 0.70,
            "confidence": 0.9, "language": "en",
            "retried": False, "pushback_detected": False,
            "created_at": f"2026-06-28T10:0{i}:00Z",
        }
        for i in range(5)
    ]
    out = asyncio.run(retrieve_similar_trajectories(
        USER, "find rice", query_intent="search_food", limit=2,
    ))
    assert len(out) == 2


# ============================================================================
# 5. record_trajectory
# ============================================================================

def test_record_trajectory_persists_row(fake_supabase: FakeSupabase):
    rec = asyncio.run(record_trajectory(
        USER,
        turn_id="t1",
        intent="search_food",
        message="please find me some rice for tonight",
        action="search",
        outcome="success",
        reward=0.85,
        confidence=0.9,
        language="en",
    ))
    assert rec is not None
    assert rec.id is not None
    rows = fake_supabase.tables["agent_trajectories"]
    assert len(rows) == 1
    assert rows[0]["user_id"] == USER
    assert rows[0]["intent"] == "search_food"
    assert rows[0]["outcome"] == "success"
    assert rows[0]["reward"] == 0.85


def test_record_trajectory_nil_uuid_skips(fake_supabase: FakeSupabase):
    rec = asyncio.run(record_trajectory(
        NIL,
        turn_id="t1", intent="search_food", message="rice",
        action="search", outcome="success",
        reward=0.9, confidence=0.9,
    ))
    assert rec is None
    assert "agent_trajectories" not in fake_supabase.tables


def test_record_trajectory_summarises_long_message(fake_supabase: FakeSupabase):
    long_msg = "find rice " * 50  # ~500 chars
    rec = asyncio.run(record_trajectory(
        USER,
        turn_id="t1", intent="search_food", message=long_msg,
        action="search", outcome="success",
        reward=0.9, confidence=0.9,
    ))
    assert rec is not None
    assert len(rec.message_summary) <= 140
    assert rec.message_summary.startswith("find rice")


def test_record_trajectory_clamps_reward(fake_supabase: FakeSupabase):
    rec = asyncio.run(record_trajectory(
        USER,
        turn_id="t1", intent="x", message="ok",
        action="x", outcome="success",
        reward=5.0, confidence=2.5,  # both out of range
    ))
    assert rec is not None
    assert rec.reward == 1.0
    assert rec.confidence == 1.0


# ============================================================================
# 6. summarise_user_style
# ============================================================================

def test_style_nil_uuid_returns_empty(fake_supabase: FakeSupabase):
    s = asyncio.run(summarise_user_style(NIL))
    assert isinstance(s, UserStyle)
    assert s.sample_size == 0


def test_style_empty_table_returns_empty(fake_supabase: FakeSupabase):
    s = asyncio.run(summarise_user_style(USER))
    assert s.sample_size == 0


def test_style_aggregates_recent_trajectories(fake_supabase: FakeSupabase):
    fake_supabase.tables["agent_trajectories"] = [
        {
            "user_id": USER, "message_summary": "please find rice",
            "language": "en", "outcome": "success", "reward": 0.80,
            "created_at": "2026-06-28T10:01:00Z",
        },
        {
            "user_id": USER, "message_summary": "thank you kindly",
            "language": "en", "outcome": "success", "reward": 0.70,
            "created_at": "2026-06-28T10:02:00Z",
        },
        {
            "user_id": USER, "message_summary": "hey, anything fun?",
            "language": "en", "outcome": "partial", "reward": 0.20,
            "created_at": "2026-06-28T10:03:00Z",
        },
    ]
    s = asyncio.run(summarise_user_style(USER))
    assert s.sample_size == 3
    assert s.primary_language == "en"
    assert s.success_rate == pytest.approx(2 / 3, abs=0.01)
    assert s.avg_reward == pytest.approx((0.80 + 0.70 + 0.20) / 3, abs=0.01)
    # At least one row has a formal marker ("please" / "thank you kindly")
    assert s.formality > 0.5


def test_style_picks_majority_language(fake_supabase: FakeSupabase):
    fake_supabase.tables["agent_trajectories"] = [
        {
            "user_id": USER, "message_summary": "hola encuentra arroz",
            "language": "es", "outcome": "success", "reward": 0.8,
            "created_at": "2026-06-28T10:01:00Z",
        },
        {
            "user_id": USER, "message_summary": "por favor busca arroz",
            "language": "es", "outcome": "success", "reward": 0.8,
            "created_at": "2026-06-28T10:02:00Z",
        },
        {
            "user_id": USER, "message_summary": "find rice",
            "language": "en", "outcome": "success", "reward": 0.8,
            "created_at": "2026-06-28T10:03:00Z",
        },
    ]
    s = asyncio.run(summarise_user_style(USER))
    assert s.primary_language == "es"


def test_style_counts_emojis(fake_supabase: FakeSupabase):
    fake_supabase.tables["agent_trajectories"] = [
        {
            "user_id": USER, "message_summary": "hello \U0001f600 \U0001f603",
            "language": "en", "outcome": "success", "reward": 0.8,
            "created_at": "2026-06-28T10:01:00Z",
        },
        {
            "user_id": USER, "message_summary": "no emojis here",
            "language": "en", "outcome": "success", "reward": 0.8,
            "created_at": "2026-06-28T10:02:00Z",
        },
    ]
    s = asyncio.run(summarise_user_style(USER))
    # 2 emojis across 2 messages = 1.0 avg
    assert s.emoji_rate == pytest.approx(1.0, abs=0.01)


# ============================================================================
# 7. TrajectoryRecord + UserStyle to_dict
# ============================================================================

def test_trajectory_to_dict_shape():
    rec = TrajectoryRecord(
        user_id=USER, turn_id="t1", intent="search_food",
        message_summary="find rice", action="search",
        outcome="success", reward=0.85, confidence=0.9,
        language="en", retried=False, pushback_detected=False,
    )
    d = rec.to_dict()
    for k in (
        "user_id", "turn_id", "intent", "message_summary", "action",
        "outcome", "reward", "confidence", "language", "retried",
        "pushback_detected", "created_at", "notes",
    ):
        assert k in d
    assert d["reward"] == 0.85
    assert isinstance(d["retried"], bool)
    assert isinstance(d["notes"], list)


def test_user_style_to_dict_shape():
    s = UserStyle(
        sample_size=5, avg_message_length=42.7, primary_language="en",
        formality=0.6, emoji_rate=0.4, avg_reward=0.7, success_rate=0.8,
    )
    d = s.to_dict()
    assert d["sample_size"] == 5
    assert d["avg_message_length"] == 42.7
    assert d["primary_language"] == "en"
    assert d["formality"] == 0.6
