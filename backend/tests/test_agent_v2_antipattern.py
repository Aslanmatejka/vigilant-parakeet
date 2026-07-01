"""Tests for backend.agent.procedural anti-pattern miner (Phase 6 ext)."""
from __future__ import annotations

import pytest

from backend.agent.adaptation import TrajectoryRecord
from backend.agent.procedural import (
    ANTIPATTERN_MAX_REWARD,
    ANTIPATTERN_MAX_RULES,
    ANTIPATTERN_MIN_FAILURE_RATE,
    ANTIPATTERN_MIN_SUPPORT,
    AntiPatternRule,
    format_antipattern_hint,
    mine_antipatterns,
    select_antipattern_for_intent,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _traj(
    *,
    intent: str = "search_food",
    action: str = "search_food_listings",
    reward: float = 0.0,
    outcome: str = "failed",
    confidence: float = 0.3,
    summary: str = "couldn't find anything",
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
# mine_antipatterns — edge cases
# ---------------------------------------------------------------------------

def test_mine_antipatterns_empty_inputs() -> None:
    assert mine_antipatterns(None) == []
    assert mine_antipatterns([]) == []


def test_mine_antipatterns_filters_missing_fields() -> None:
    items = [
        _traj(intent="", action="search_food_listings"),
        _traj(intent="search_food", action=""),
        _traj(intent="   ", action="search_food_listings"),
    ]
    assert mine_antipatterns(items) == []


def test_mine_antipatterns_filters_non_records() -> None:
    items = ["nope", 42, {"intent": "x"}, _traj(), _traj()]
    rules = mine_antipatterns(items)
    # Real records produce a single (search_food, search_food_listings)
    assert len(rules) == 1


def test_mine_antipatterns_support_floor() -> None:
    items = [_traj(intent="search_food", action="search_food_listings")]
    # support = 1 < ANTIPATTERN_MIN_SUPPORT (=2)
    assert mine_antipatterns(items) == []


def test_mine_antipatterns_reward_ceiling_blocks_emission() -> None:
    # High mean reward → not an anti-pattern, even with failures
    items = [
        _traj(reward=0.9, outcome="failed"),
        _traj(reward=0.9, outcome="failed"),
    ]
    assert mine_antipatterns(items) == []


def test_mine_antipatterns_failure_rate_floor() -> None:
    # All success → failure_rate=0 < min_failure_rate
    items = [
        _traj(reward=0.0, outcome="success"),
        _traj(reward=0.0, outcome="success"),
    ]
    assert mine_antipatterns(items) == []


def test_mine_antipatterns_happy_path_emits_rule() -> None:
    items = [
        _traj(reward=0.0, outcome="failed", summary="first failure"),
        _traj(reward=0.1, outcome="failed", summary="second failure"),
    ]
    rules = mine_antipatterns(items)
    assert len(rules) == 1
    r = rules[0]
    assert isinstance(r, AntiPatternRule)
    assert r.intent == "search_food"
    assert r.action == "search_food_listings"
    assert r.support_count == 2
    assert r.failure_rate == pytest.approx(1.0)
    assert r.success_rate == pytest.approx(0.0)
    assert 0.0 < r.severity <= 1.0


def test_mine_antipatterns_severity_descending() -> None:
    # Pair A: 2 failures, reward 0 → moderate severity
    # Pair B: 5 failures, reward 0 → full support_weight, max severity
    items = [
        _traj(intent="i_a", action="a", reward=0.0, outcome="failed"),
        _traj(intent="i_a", action="a", reward=0.0, outcome="failed"),
        *[
            _traj(intent="i_b", action="b", reward=0.0, outcome="failed")
            for _ in range(5)
        ],
    ]
    rules = mine_antipatterns(items)
    assert len(rules) == 2
    assert rules[0].action == "b"
    assert rules[1].action == "a"
    assert rules[0].severity > rules[1].severity


def test_mine_antipatterns_groups_by_intent_action_pair() -> None:
    items = [
        _traj(intent="i_a", action="a", outcome="failed"),
        _traj(intent="i_a", action="a", outcome="failed"),
        _traj(intent="i_b", action="a", outcome="failed"),
        _traj(intent="i_b", action="a", outcome="failed"),
        _traj(intent="i_a", action="b", outcome="failed"),
        _traj(intent="i_a", action="b", outcome="failed"),
    ]
    rules = mine_antipatterns(items)
    pairs = {(r.intent, r.action) for r in rules}
    assert pairs == {("i_a", "a"), ("i_b", "a"), ("i_a", "b")}


def test_mine_antipatterns_sample_summaries_lowest_reward_first() -> None:
    items = [
        _traj(reward=0.3, outcome="failed", summary="meh"),
        _traj(reward=0.0, outcome="failed", summary="worst"),
        _traj(reward=0.1, outcome="failed", summary="bad"),
    ]
    rules = mine_antipatterns(items)
    assert rules[0].sample_summaries[0] == "worst"
    assert rules[0].sample_summaries[1] == "bad"


def test_mine_antipatterns_sample_summaries_deduped_and_capped() -> None:
    items = [
        _traj(reward=0.0, outcome="failed", summary="same"),
        _traj(reward=0.05, outcome="failed", summary="same"),
        _traj(reward=0.1, outcome="failed", summary="different"),
        _traj(reward=0.15, outcome="failed", summary="other"),
    ]
    rules = mine_antipatterns(items)
    samples = rules[0].sample_summaries
    assert len(samples) <= 2
    assert samples[0] == "same"
    assert "same" not in samples[1:]


def test_mine_antipatterns_support_weight_saturates_at_five() -> None:
    big = [
        _traj(reward=0.0, outcome="failed") for _ in range(10)
    ]
    small = [
        _traj(intent="other", action="other_act", reward=0.0, outcome="failed")
        for _ in range(5)
    ]
    rules_big = mine_antipatterns(big)
    rules_small = mine_antipatterns(small)
    # 10 vs 5 trajectories — severity should be identical (both saturate)
    assert rules_big[0].severity == pytest.approx(rules_small[0].severity)


def test_mine_antipatterns_max_rules_cap() -> None:
    items: list[TrajectoryRecord] = []
    for i in range(ANTIPATTERN_MAX_RULES + 5):
        items.append(_traj(intent=f"intent_{i}", action="act", outcome="failed"))
        items.append(_traj(intent=f"intent_{i}", action="act", outcome="failed"))
    rules = mine_antipatterns(items)
    assert len(rules) <= ANTIPATTERN_MAX_RULES


def test_mine_antipatterns_threshold_overrides() -> None:
    items = [_traj(reward=0.0, outcome="failed")]
    # Default min_support=2 → empty; override to 1 → emits
    assert mine_antipatterns(items) == []
    rules = mine_antipatterns(items, min_support=1)
    assert len(rules) == 1


def test_mine_antipatterns_partial_failure_with_low_reward() -> None:
    # Mostly failures with low reward — should still emit
    items = [
        _traj(reward=0.1, outcome="failed"),
        _traj(reward=0.1, outcome="failed"),
        _traj(reward=0.2, outcome="success"),
    ]
    rules = mine_antipatterns(items)
    assert len(rules) == 1
    assert rules[0].success_rate == pytest.approx(1 / 3)
    assert rules[0].failure_rate == pytest.approx(2 / 3)


def test_mine_antipatterns_to_dict_rounds_floats() -> None:
    items = [
        _traj(reward=0.123456, outcome="failed"),
        _traj(reward=0.123456, outcome="failed"),
    ]
    rules = mine_antipatterns(items)
    d = rules[0].to_dict()
    assert d["support_count"] == 2
    assert d["mean_reward"] == round(0.123456, 3)
    assert isinstance(d["sample_summaries"], list)
    assert "severity" in d
    assert "failure_rate" in d


# ---------------------------------------------------------------------------
# select_antipattern_for_intent
# ---------------------------------------------------------------------------

def test_select_antipattern_empty_or_none() -> None:
    assert select_antipattern_for_intent(None, "x") is None
    assert select_antipattern_for_intent([], "x") is None
    assert select_antipattern_for_intent([AntiPatternRule(
        intent="x", action="y", support_count=2, mean_reward=0.0,
        mean_confidence=0.0, failure_rate=1.0, success_rate=0.0,
        severity=0.4,
    )], "") is None


def test_select_antipattern_picks_matching_intent() -> None:
    rules = [
        AntiPatternRule(intent="a", action="x", support_count=2, mean_reward=0.0,
                        mean_confidence=0.0, failure_rate=1.0, success_rate=0.0,
                        severity=0.4),
        AntiPatternRule(intent="b", action="y", support_count=2, mean_reward=0.0,
                        mean_confidence=0.0, failure_rate=1.0, success_rate=0.0,
                        severity=0.6),
    ]
    out = select_antipattern_for_intent(rules, "b")
    assert out is not None and out.action == "y"


def test_select_antipattern_returns_none_on_miss() -> None:
    rules = [
        AntiPatternRule(intent="a", action="x", support_count=2, mean_reward=0.0,
                        mean_confidence=0.0, failure_rate=1.0, success_rate=0.0,
                        severity=0.4),
    ]
    assert select_antipattern_for_intent(rules, "nope") is None


def test_select_antipattern_highest_severity_wins() -> None:
    rules = [
        AntiPatternRule(intent="i", action="x", support_count=2, mean_reward=0.0,
                        mean_confidence=0.0, failure_rate=1.0, success_rate=0.0,
                        severity=0.3),
        AntiPatternRule(intent="i", action="y", support_count=2, mean_reward=0.0,
                        mean_confidence=0.0, failure_rate=1.0, success_rate=0.0,
                        severity=0.7),
        AntiPatternRule(intent="i", action="z", support_count=2, mean_reward=0.0,
                        mean_confidence=0.0, failure_rate=1.0, success_rate=0.0,
                        severity=0.5),
    ]
    out = select_antipattern_for_intent(rules, "i")
    assert out is not None and out.action == "y"


def test_select_antipattern_ignores_non_rules() -> None:
    rules = ["bad", 42, AntiPatternRule(
        intent="i", action="x", support_count=2, mean_reward=0.0,
        mean_confidence=0.0, failure_rate=1.0, success_rate=0.0, severity=0.4,
    )]
    out = select_antipattern_for_intent(rules, "i")
    assert out is not None and out.action == "x"


# ---------------------------------------------------------------------------
# format_antipattern_hint
# ---------------------------------------------------------------------------

def test_format_antipattern_hint_none_or_non_rule() -> None:
    assert format_antipattern_hint(None) == ""
    assert format_antipattern_hint("not a rule") == ""  # type: ignore[arg-type]


def test_format_antipattern_hint_english() -> None:
    rule = AntiPatternRule(
        intent="search_food", action="search_food_listings",
        support_count=3, mean_reward=0.1, mean_confidence=0.4,
        failure_rate=0.75, success_rate=0.25, severity=0.5,
    )
    out = format_antipattern_hint(rule, language="en")
    assert "Avoid" in out
    assert "search_food" in out
    assert "search_food_listings" in out
    assert "3" in out
    assert "75%" in out


def test_format_antipattern_hint_spanish() -> None:
    rule = AntiPatternRule(
        intent="search_food", action="search_food_listings",
        support_count=2, mean_reward=0.05, mean_confidence=0.3,
        failure_rate=1.0, success_rate=0.0, severity=0.9,
    )
    out = format_antipattern_hint(rule, language="es")
    assert "Evita" in out
    assert "search_food" in out
    assert "100%" in out


def test_format_antipattern_hint_unknown_language_falls_back_to_english() -> None:
    rule = AntiPatternRule(
        intent="i", action="a", support_count=2, mean_reward=0.0,
        mean_confidence=0.0, failure_rate=1.0, success_rate=0.0, severity=0.4,
    )
    out = format_antipattern_hint(rule, language="zz")
    assert "Avoid" in out


# ---------------------------------------------------------------------------
# End-to-end
# ---------------------------------------------------------------------------

def test_mine_select_format_end_to_end() -> None:
    items = [
        _traj(intent="claim_food", action="claim_food_listing",
              reward=0.0, outcome="failed", summary="rejected by donor"),
        _traj(intent="claim_food", action="claim_food_listing",
              reward=0.05, outcome="failed", summary="already claimed"),
        # Distractor that should NOT match the intent
        _traj(intent="other", action="search_food_listings",
              reward=0.0, outcome="failed", summary="x"),
        _traj(intent="other", action="search_food_listings",
              reward=0.0, outcome="failed", summary="y"),
    ]
    rules = mine_antipatterns(items)
    selected = select_antipattern_for_intent(rules, "claim_food")
    assert selected is not None
    hint = format_antipattern_hint(selected, language="en")
    assert "claim_food" in hint
    assert "claim_food_listing" in hint


def test_constants_within_expected_bounds() -> None:
    assert ANTIPATTERN_MIN_SUPPORT >= 1
    assert 0.0 <= ANTIPATTERN_MAX_REWARD <= 1.0
    assert 0.0 <= ANTIPATTERN_MIN_FAILURE_RATE <= 1.0
    assert ANTIPATTERN_MAX_RULES >= 1
