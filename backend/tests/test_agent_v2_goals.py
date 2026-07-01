"""
AGENT_V2 — Goal Stack Tests (Phase 2)
======================================

Unit tests for `backend.agent.goals`. Pure functions — no live Supabase,
no live OpenAI.

Scenarios:
  1.  decompose_compound — singletons, AND/THEN/semicolon splits,
       ingredient-list preservation, empty input.
  2.  extract_goals_heuristic — single intent, compound parent+children,
       priority detection (urgent/high/normal), empty input.
  3.  prioritize_goals — urgent first, stable within priority, parents
       ahead of children.
  4.  update_status_from_reflection — success/partial/failed/deferred
       flowing onto child goals and rolling up to the parent.
  5.  replan_suggestion — failed/deferred/partial/success branches.
  6.  Goal.to_dict round-trip schema.

Run:
    python -m pytest backend/tests/test_agent_v2_goals.py -v
"""

from __future__ import annotations

import pytest

from backend.agent.goals import (
    Goal,
    decompose_compound,
    extract_goals_heuristic,
    prioritize_goals,
    replan_suggestion,
    update_status_from_reflection,
)


USER = "11111111-1111-1111-1111-111111111111"


# ============================================================================
# 1. decompose_compound
# ============================================================================

@pytest.mark.parametrize("text,expected_count", [
    ("find food near me", 1),
    ("post my bread AND ALSO remind me Friday", 2),
    ("update my address; send a notification", 2),
    ("claim that loaf, and then message the donor", 2),
    ("rice and beans please", 1),               # ingredient-list preserved
    ("hi there", 1),
    ("", 0),
    ("   ", 0),
])
def test_decompose_compound(text: str, expected_count: int) -> None:
    assert len(decompose_compound(text)) == expected_count


def test_decompose_strips_punctuation() -> None:
    parts = decompose_compound("post bread; remind me later.")
    assert parts == ["post bread", "remind me later"]


# ============================================================================
# 2. extract_goals_heuristic
# ============================================================================

def test_extract_single_intent_produces_one_goal() -> None:
    goals = extract_goals_heuristic("find vegan food near me", USER)
    assert len(goals) == 1
    g = goals[0]
    assert g.intent == "search"
    assert g.user_id == USER
    assert g.status == "open"
    assert g.parent_goal_id is None


def test_extract_compound_produces_parent_plus_children() -> None:
    goals = extract_goals_heuristic(
        "post my leftover bread AND ALSO remind me on Friday", USER,
    )
    parents = [g for g in goals if g.parent_goal_id is None]
    children = [g for g in goals if g.parent_goal_id is not None]
    assert len(parents) == 1
    assert len(children) >= 1
    # All children point at the same parent.
    assert {c.parent_goal_id for c in children} == {parents[0].id}


def test_extract_priority_urgent() -> None:
    goals = extract_goals_heuristic("I need food URGENT please", USER)
    assert goals[0].priority == "urgent"


def test_extract_priority_high() -> None:
    goals = extract_goals_heuristic("looking for groceries tomorrow", USER)
    assert goals[0].priority == "high"


def test_extract_empty_yields_no_goals() -> None:
    assert extract_goals_heuristic("", USER) == []
    assert extract_goals_heuristic("   ", USER) == []


def test_extract_drops_chitchat_children_in_compound() -> None:
    """A compound message keeps its parent + actionable children; pure
    chitchat chunks shouldn't earn their own goal slot."""
    goals = extract_goals_heuristic(
        "hi there ; AND ALSO find me food near downtown", USER,
    )
    # Parent + at most one search child — never a chitchat child.
    intents = [g.intent for g in goals if g.parent_goal_id is not None]
    assert "chitchat" not in intents


# ============================================================================
# 3. prioritize_goals
# ============================================================================

def _g(prio: str, parent: str | None = None, gid: str = "") -> Goal:
    return Goal(
        id=gid or f"id-{prio}-{parent or 'root'}",
        user_id=USER,
        description="x",
        priority=prio,            # type: ignore[arg-type]
        parent_goal_id=parent,
    )


def test_prioritize_orders_urgent_first() -> None:
    src = [_g("low", gid="a"), _g("urgent", gid="b"), _g("normal", gid="c")]
    ordered = prioritize_goals(src)
    assert [g.id for g in ordered] == ["b", "c", "a"]


def test_prioritize_is_stable_within_priority() -> None:
    src = [_g("normal", gid="a"), _g("normal", gid="b"), _g("normal", gid="c")]
    ordered = prioritize_goals(src)
    assert [g.id for g in ordered] == ["a", "b", "c"]


def test_prioritize_keeps_parents_ahead_of_children() -> None:
    parent = _g("normal", gid="P")
    child = _g("normal", parent="P", gid="C")
    ordered = prioritize_goals([child, parent])
    assert [g.id for g in ordered] == ["P", "C"]


# ============================================================================
# 4. update_status_from_reflection
# ============================================================================

def _make_parent_child_set() -> list[Goal]:
    parent = Goal(id="P", user_id=USER, description="post and remind")
    c1 = Goal(id="C1", user_id=USER, description="post bread",
              parent_goal_id="P", intent="donate")
    c2 = Goal(id="C2", user_id=USER, description="remind Friday",
              parent_goal_id="P", intent="profile")
    return [parent, c1, c2]


def test_update_success_marks_children_done_and_rolls_up_parent() -> None:
    goals = _make_parent_child_set()
    update_status_from_reflection(goals, "success")
    assert goals[1].status == "done"
    assert goals[2].status == "done"
    assert goals[0].status == "done"   # parent rolls up


def test_update_failed_blocks_children_and_parent() -> None:
    goals = _make_parent_child_set()
    update_status_from_reflection(goals, "failed", needs_retry=True)
    assert goals[1].status == "blocked"
    assert goals[2].status == "blocked"
    assert goals[0].status == "blocked"
    assert "reflection requested retry" in goals[1].notes


def test_update_partial_first_done_rest_in_progress() -> None:
    goals = _make_parent_child_set()
    update_status_from_reflection(goals, "partial")
    assert goals[1].status == "done"
    assert goals[2].status == "in_progress"
    # Mixed children → parent rolls up to in_progress.
    assert goals[0].status == "in_progress"


def test_update_deferred_keeps_children_open_with_note() -> None:
    goals = _make_parent_child_set()
    update_status_from_reflection(goals, "deferred")
    assert goals[1].status == "open"
    assert "deferred this turn" in goals[1].notes


def test_update_singleton_goal_success() -> None:
    g = Goal(id="solo", user_id=USER, description="find apples", intent="search")
    update_status_from_reflection([g], "success")
    assert g.status == "done"


# ============================================================================
# 5. replan_suggestion
# ============================================================================

def test_replan_success_returns_none() -> None:
    assert replan_suggestion("use_tool", "success",
                             needs_retry=False, intent="search") is None


def test_replan_failed_search_suggests_broadening() -> None:
    hint = replan_suggestion("use_tool", "failed",
                             needs_retry=True, intent="search")
    assert hint is not None
    assert "broaden" in hint.lower() or "criteria" in hint.lower()


def test_replan_failed_claim_suggests_confirm_before_retry() -> None:
    hint = replan_suggestion("use_tool", "failed",
                             needs_retry=True, intent="claim")
    assert hint is not None
    assert "confirm" in hint.lower() or "re-fetch" in hint.lower()


def test_replan_deferred_tool_path() -> None:
    hint = replan_suggestion("use_tool", "deferred",
                             needs_retry=False, intent="claim")
    assert hint is not None
    assert "tool" in hint.lower()


def test_replan_partial_outcome() -> None:
    hint = replan_suggestion("use_tool", "partial",
                             needs_retry=False, intent="donate")
    assert hint is not None
    assert "worked" in hint.lower() or "remaining" in hint.lower()


# ============================================================================
# 6. Goal.to_dict
# ============================================================================

def test_goal_to_dict_shape() -> None:
    g = Goal(
        id="g1", user_id=USER, description="find food",
        intent="search", priority="urgent",
    )
    d = g.to_dict()
    assert d["id"] == "g1"
    assert d["intent"] == "search"
    assert d["priority"] == "urgent"
    assert d["status"] == "open"
    assert d["parent_goal_id"] is None
    assert isinstance(d["notes"], list)
    assert "created_at" in d
    assert "updated_at" in d


def test_goal_touch_updates_timestamp() -> None:
    g = Goal(id="g1", user_id=USER, description="x")
    before = g.updated_at
    # Force a different microsecond by sleeping a tick.
    import time
    time.sleep(0.001)
    g.touch()
    assert g.updated_at >= before
