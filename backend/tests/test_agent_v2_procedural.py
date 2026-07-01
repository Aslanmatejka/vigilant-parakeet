"""Tests for backend.agent.procedural — heuristic procedural memory miner."""
from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import patch

import pytest

from backend.agent.adaptation import TrajectoryRecord
from backend.agent.procedural import (
    MAX_RULES,
    MIN_REWARD,
    MIN_SUCCESS_RATE,
    MIN_SUPPORT,
    ProceduralRule,
    fetch_recent_trajectories,
    format_procedural_hint,
    mine_procedural_rules,
    select_rule_for_intent,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _traj(
    *,
    intent: str = "search_food",
    action: str = "search_food_listings",
    reward: float = 0.9,
    outcome: str = "success",
    confidence: float = 0.8,
    summary: str = "find bread near me",
) -> TrajectoryRecord:
    return TrajectoryRecord(
        user_id="u1",
        intent=intent,
        message_summary=summary,
        action=action,
        outcome=outcome,
        reward=reward,
        confidence=confidence,
        language="en",
    )


# ---------------------------------------------------------------------------
# mine_procedural_rules — empty/edge cases
# ---------------------------------------------------------------------------

def test_mine_empty_inputs() -> None:
    assert mine_procedural_rules(None) == []
    assert mine_procedural_rules([]) == []


def test_mine_filters_missing_intent_or_action() -> None:
    items = [
        _traj(intent="", action="search_food_listings"),
        _traj(intent="search_food", action=""),
        _traj(intent="   ", action="search_food_listings"),
    ]
    assert mine_procedural_rules(items) == []


def test_mine_filters_non_trajectory_records() -> None:
    items = ["not a record", 42, None, _traj()]
    # Only one TrajectoryRecord but support floor=2 so still empty.
    assert mine_procedural_rules(items) == []  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Threshold gates
# ---------------------------------------------------------------------------

def test_mine_support_floor() -> None:
    # Default MIN_SUPPORT=2; one trajectory should not emit a rule.
    rules = mine_procedural_rules([_traj()])
    assert rules == []


def test_mine_reward_floor() -> None:
    # All rewards below MIN_REWARD => no rule.
    rules = mine_procedural_rules([
        _traj(reward=0.1),
        _traj(reward=0.2),
        _traj(reward=0.3),
    ])
    assert rules == []


def test_mine_success_rate_floor() -> None:
    # Reward is high but most outcomes are failures.
    rules = mine_procedural_rules([
        _traj(reward=0.9, outcome="failed"),
        _traj(reward=0.9, outcome="failed"),
        _traj(reward=0.9, outcome="success"),
    ])
    # success_rate = 1/3 ≈ 0.33 < MIN_SUCCESS_RATE=0.6
    assert rules == []


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_mine_emits_qualifying_group() -> None:
    rules = mine_procedural_rules([_traj() for _ in range(3)])
    assert len(rules) == 1
    rule = rules[0]
    assert rule.intent == "search_food"
    assert rule.action == "search_food_listings"
    assert rule.support_count == 3
    assert rule.success_rate == 1.0
    assert rule.mean_reward == pytest.approx(0.9)
    assert rule.confidence > 0
    # sample summaries deduped, capped at 2
    assert len(rule.sample_summaries) <= 2


def test_mine_sample_summaries_deduped_and_capped() -> None:
    items = [
        _traj(summary="msg A"),
        _traj(summary="msg A"),  # dup
        _traj(summary="msg B"),
        _traj(summary="msg C"),  # would be 3rd unique
    ]
    rules = mine_procedural_rules(items)
    assert len(rules) == 1
    assert len(rules[0].sample_summaries) == 2  # capped


def test_mine_groups_by_intent_action_pair() -> None:
    items = [
        _traj(intent="search_food", action="search_food_listings"),
        _traj(intent="search_food", action="search_food_listings"),
        _traj(intent="search_food", action="search_food_listings"),
        _traj(intent="claim_food", action="create_food_claim"),
        _traj(intent="claim_food", action="create_food_claim"),
    ]
    rules = mine_procedural_rules(items)
    pairs = {(r.intent, r.action) for r in rules}
    assert ("search_food", "search_food_listings") in pairs
    assert ("claim_food", "create_food_claim") in pairs
    assert len(rules) == 2


def test_mine_sorted_by_confidence_desc() -> None:
    # Higher support → higher support_weight → higher composite confidence
    items = [
        # Group A: 5 items, perfect — composite ≈ 0.9 * 1.0 * 1.0 = 0.9
        *[_traj(intent="search_food", reward=0.9) for _ in range(5)],
        # Group B: 2 items, lower reward — composite ≈ 0.7 * 1.0 * 0.4 = 0.28
        *[_traj(intent="claim_food", action="create_food_claim", reward=0.7) for _ in range(2)],
    ]
    rules = mine_procedural_rules(items)
    assert len(rules) == 2
    assert rules[0].confidence > rules[1].confidence
    assert rules[0].intent == "search_food"


def test_mine_max_rules_cap() -> None:
    # Build many qualifying groups
    items = []
    for i in range(MAX_RULES + 5):
        for _ in range(2):
            items.append(_traj(intent=f"intent_{i}", action=f"action_{i}"))
    rules = mine_procedural_rules(items)
    assert len(rules) <= MAX_RULES


def test_mine_support_weight_caps_at_one() -> None:
    # 10 successful trajectories — composite shouldn't exceed mean_reward
    # because support_weight = min(10/5, 1.0) = 1.0
    items = [_traj(reward=0.8) for _ in range(10)]
    rules = mine_procedural_rules(items)
    assert len(rules) == 1
    assert rules[0].confidence == pytest.approx(0.8)


def test_mine_constants_are_sane() -> None:
    assert MIN_SUPPORT >= 1
    assert 0.0 < MIN_REWARD <= 1.0
    assert 0.0 < MIN_SUCCESS_RATE <= 1.0
    assert MAX_RULES > 0


def test_mine_threshold_overrides_work() -> None:
    # Default would reject — but with lowered thresholds it should pass.
    items = [_traj(reward=0.3, outcome="success") for _ in range(2)]
    assert mine_procedural_rules(items) == []
    rules = mine_procedural_rules(items, min_reward=0.2, min_success_rate=0.5)
    assert len(rules) == 1


# ---------------------------------------------------------------------------
# select_rule_for_intent
# ---------------------------------------------------------------------------

def test_select_rule_empty_or_missing() -> None:
    assert select_rule_for_intent(None, "search_food") is None
    assert select_rule_for_intent([], "search_food") is None
    assert select_rule_for_intent([_traj()], "") is None  # type: ignore[list-item]


def test_select_rule_picks_matching_intent() -> None:
    rules = mine_procedural_rules([
        *[_traj(intent="search_food") for _ in range(3)],
        *[_traj(intent="claim_food", action="create_food_claim") for _ in range(3)],
    ])
    chosen = select_rule_for_intent(rules, "claim_food")
    assert chosen is not None
    assert chosen.intent == "claim_food"


def test_select_rule_returns_none_when_no_match() -> None:
    rules = mine_procedural_rules([_traj() for _ in range(3)])
    assert select_rule_for_intent(rules, "unknown_intent") is None


def test_select_rule_picks_highest_confidence_when_multiple() -> None:
    # Construct two ProceduralRule objects with the same intent but
    # different confidence.
    low = ProceduralRule(
        intent="search_food", action="low_action",
        support_count=2, mean_reward=0.6, mean_confidence=0.5,
        success_rate=0.7, confidence=0.2,
    )
    high = ProceduralRule(
        intent="search_food", action="high_action",
        support_count=5, mean_reward=0.9, mean_confidence=0.8,
        success_rate=1.0, confidence=0.9,
    )
    chosen = select_rule_for_intent([low, high], "search_food")
    assert chosen is high


def test_select_rule_ignores_non_rule_entries() -> None:
    rule = ProceduralRule(
        intent="search_food", action="a", support_count=2,
        mean_reward=0.7, mean_confidence=0.6, success_rate=1.0,
        confidence=0.7,
    )
    chosen = select_rule_for_intent(["junk", 42, rule], "search_food")  # type: ignore[list-item]
    assert chosen is rule


# ---------------------------------------------------------------------------
# format_procedural_hint
# ---------------------------------------------------------------------------

def test_format_hint_none() -> None:
    assert format_procedural_hint(None) == ""


def test_format_hint_non_rule() -> None:
    assert format_procedural_hint("not a rule") == ""  # type: ignore[arg-type]


def test_format_hint_en() -> None:
    rule = ProceduralRule(
        intent="search_food", action="search_food_listings",
        support_count=4, mean_reward=0.85, mean_confidence=0.7,
        success_rate=1.0, confidence=0.68,
    )
    out = format_procedural_hint(rule, language="en")
    assert "Procedural hint" in out
    assert "search_food" in out
    assert "search_food_listings" in out
    assert "4" in out
    assert "100%" in out
    assert "0.85" in out


def test_format_hint_es() -> None:
    rule = ProceduralRule(
        intent="claim_food", action="create_food_claim",
        support_count=3, mean_reward=0.75, mean_confidence=0.6,
        success_rate=0.67, confidence=0.30,
    )
    out = format_procedural_hint(rule, language="es")
    assert "Pista procedimental" in out
    assert "claim_food" in out
    assert "create_food_claim" in out


# ---------------------------------------------------------------------------
# fetch_recent_trajectories — async Supabase wrapper
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_recent_nil_uuid_returns_empty() -> None:
    assert await fetch_recent_trajectories("") == []
    assert await fetch_recent_trajectories("00000000-0000-0000-0000-000000000000") == []


@pytest.mark.asyncio
async def test_fetch_recent_engine_unavailable() -> None:
    # Force the local import to fail by injecting a broken backend.ai_engine.
    fake = ModuleType("backend.ai_engine")
    # Don't define supabase_get → AttributeError on import-time access works
    # but the function only imports the name; we want the import itself OK
    # but the attribute missing. Simpler: set the attribute to raise.
    def _explode(*_a, **_k):  # noqa: ANN001
        raise RuntimeError("nope")
    fake.supabase_get = _explode  # type: ignore[attr-defined]
    with patch.dict(sys.modules, {"backend.ai_engine": fake}):
        out = await fetch_recent_trajectories("u1", limit=10)
        assert out == []


@pytest.mark.asyncio
async def test_fetch_recent_supabase_returns_rows() -> None:
    fake = ModuleType("backend.ai_engine")

    async def _fake_get(table, params):  # noqa: ANN001
        assert table == "agent_trajectories"
        return [
            {
                "id": "t1", "turn_id": "tn1", "intent": "search_food",
                "message_summary": "find bread", "action": "search_food_listings",
                "outcome": "success", "reward": 0.8, "confidence": 0.7,
                "language": "en", "retried": False, "pushback_detected": False,
                "created_at": "2026-06-28T00:00:00Z",
            },
            {
                "id": "t2", "turn_id": "tn2", "intent": "claim_food",
                "message_summary": "claim listing 5", "action": "create_food_claim",
                "outcome": "success", "reward": 0.9, "confidence": 0.8,
                "language": "en", "retried": False, "pushback_detected": False,
                "created_at": "2026-06-28T01:00:00Z",
            },
            "garbage row",  # tests the isinstance dict guard
        ]

    fake.supabase_get = _fake_get  # type: ignore[attr-defined]
    with patch.dict(sys.modules, {"backend.ai_engine": fake}):
        out = await fetch_recent_trajectories("u1", limit=10)
        assert len(out) == 2
        assert out[0].intent == "search_food"
        assert out[1].action == "create_food_claim"


@pytest.mark.asyncio
async def test_fetch_recent_supabase_get_raises() -> None:
    fake = ModuleType("backend.ai_engine")

    async def _broken_get(table, params):  # noqa: ANN001
        raise RuntimeError("supabase down")

    fake.supabase_get = _broken_get  # type: ignore[attr-defined]
    with patch.dict(sys.modules, {"backend.ai_engine": fake}):
        out = await fetch_recent_trajectories("u1", limit=10)
        assert out == []


@pytest.mark.asyncio
async def test_fetch_recent_clamps_limit() -> None:
    fake = ModuleType("backend.ai_engine")
    captured: dict = {}

    async def _fake_get(table, params):  # noqa: ANN001
        captured["params"] = params
        return []

    fake.supabase_get = _fake_get  # type: ignore[attr-defined]
    with patch.dict(sys.modules, {"backend.ai_engine": fake}):
        await fetch_recent_trajectories("u1", limit=99999)
        assert int(captured["params"]["limit"]) <= 200


# ---------------------------------------------------------------------------
# Composition: mining the output of fetch_recent_trajectories
# ---------------------------------------------------------------------------

def test_mine_and_select_end_to_end() -> None:
    items = [
        _traj(intent="search_food", action="search_food_listings", reward=0.9) for _ in range(4)
    ] + [
        _traj(intent="claim_food", action="create_food_claim", reward=0.85) for _ in range(2)
    ]
    rules = mine_procedural_rules(items)
    assert len(rules) == 2
    chosen = select_rule_for_intent(rules, "search_food")
    assert chosen is not None
    hint = format_procedural_hint(chosen, language="en")
    assert "search_food_listings" in hint
