"""Tests for backend.agent.confirmation_policy — pure per-turn confirmation
verdict module (Phase 4 mid)."""
from __future__ import annotations

import pytest

from backend.agent.confirmation_policy import (
    CONFIRM_CONFIDENCE_FLOOR,
    ConfirmationDecision,
    any_confirmation_required,
    decide_for_intent,
    decide_for_tool_call,
    evaluate_tool_results,
    format_decision_summary,
)


# ---------------------------------------------------------------------------
# decide_for_intent
# ---------------------------------------------------------------------------

def test_decide_for_intent_empty() -> None:
    d = decide_for_intent("", 0.9)
    assert d.required is False
    assert d.kind == "none"


def test_decide_for_intent_whitespace() -> None:
    d = decide_for_intent("   ", 0.9)
    assert d.required is False


def test_decide_for_intent_none_intent() -> None:
    d = decide_for_intent(None, 0.9)
    assert d.required is False
    assert d.kind == "none"


@pytest.mark.parametrize("intent", [
    "delete_listing", "cancel_claim", "leave_community", "forget_about_me",
])
def test_decide_for_intent_destructive_always_required(intent: str) -> None:
    # High confidence shouldn't matter — destructive is destructive.
    d = decide_for_intent(intent, 0.99)
    assert d.required is True
    assert d.kind == "destructive"
    assert intent in d.reason_en
    assert intent in d.reason_es


@pytest.mark.parametrize("intent", [
    "claim_food", "share_food", "donate", "donate_food",
    "schedule_pickup", "join_community", "update_profile",
    "set_dietary_preferences", "edit_listing",
])
def test_decide_for_intent_mutating_low_conf_required(intent: str) -> None:
    d = decide_for_intent(intent, CONFIRM_CONFIDENCE_FLOOR - 0.1)
    assert d.required is True
    assert d.kind == "low_confidence"


@pytest.mark.parametrize("intent", [
    "claim_food", "donate", "schedule_pickup", "join_community",
])
def test_decide_for_intent_mutating_high_conf_not_required(intent: str) -> None:
    d = decide_for_intent(intent, 0.95)
    assert d.required is False
    assert d.kind == "none"


def test_decide_for_intent_mutating_at_floor_not_required() -> None:
    # Exactly at the floor → confidence >= floor, so not required.
    d = decide_for_intent("claim_food", CONFIRM_CONFIDENCE_FLOOR)
    assert d.required is False


def test_decide_for_intent_mutating_none_confidence_required() -> None:
    # None confidence → treated as 0.0 → below floor → required.
    d = decide_for_intent("claim_food", None)
    assert d.required is True
    assert d.kind == "low_confidence"


def test_decide_for_intent_read_only_intent() -> None:
    d = decide_for_intent("search_food", 0.3)
    assert d.required is False
    assert d.kind == "none"
    assert "read-only" in d.reason_en


def test_decide_for_intent_to_dict_shape() -> None:
    d = decide_for_intent("delete_listing", 0.9)
    out = d.to_dict()
    assert set(out.keys()) >= {
        "required", "kind", "reason_en", "reason_es",
        "tool", "intent", "confidence", "args_snapshot",
    }
    assert out["required"] is True
    assert out["intent"] == "delete_listing"
    assert out["confidence"] == 0.9


def test_constants_sanity() -> None:
    assert 0.0 < CONFIRM_CONFIDENCE_FLOOR < 1.0


# ---------------------------------------------------------------------------
# decide_for_tool_call
# ---------------------------------------------------------------------------

def test_decide_tool_empty_tool() -> None:
    d = decide_for_tool_call(intent="claim_food", tool_name="", confidence=0.9)
    assert d.required is False
    assert d.kind == "none"


def test_decide_tool_none_tool() -> None:
    d = decide_for_tool_call(intent="claim_food", tool_name=None, confidence=0.9)
    assert d.required is False


@pytest.mark.parametrize("tool", [
    "delete_listing", "cancel_claim",
    "dismiss_all_notifications", "forget_about_me",
])
def test_decide_tool_destructive_always_required(tool: str) -> None:
    d = decide_for_tool_call(
        intent="search_food", tool_name=tool, confidence=0.99,
    )
    assert d.required is True
    assert d.kind == "destructive"
    assert d.tool == tool


def test_decide_tool_bulk_claim_high_impact() -> None:
    d = decide_for_tool_call(
        intent="claim_food",
        tool_name="claim_listing",
        confidence=0.95,
        args={"quantity": 10},
    )
    assert d.required is True
    assert d.kind == "high_impact"


def test_decide_tool_small_claim_at_high_conf_not_required() -> None:
    d = decide_for_tool_call(
        intent="claim_food",
        tool_name="claim_listing",
        confidence=0.95,
        args={"quantity": 2},
    )
    assert d.required is False


def test_decide_tool_bulk_threshold_boundary() -> None:
    # Exactly 5 should NOT trigger bulk (we use strict >).
    d = decide_for_tool_call(
        intent="claim_food",
        tool_name="claim_listing",
        confidence=0.95,
        args={"quantity": 5},
    )
    assert d.required is False
    # 6 does.
    d6 = decide_for_tool_call(
        intent="claim_food",
        tool_name="claim_listing",
        confidence=0.95,
        args={"quantity": 6},
    )
    assert d6.required is True
    assert d6.kind == "high_impact"


def test_decide_tool_bulk_with_qty_alias() -> None:
    d = decide_for_tool_call(
        intent="claim_food",
        tool_name="claim_listing",
        confidence=0.9,
        args={"qty": "8"},  # string + alias key
    )
    assert d.required is True
    assert d.kind == "high_impact"


def test_decide_tool_bulk_with_garbage_qty() -> None:
    d = decide_for_tool_call(
        intent="claim_food",
        tool_name="claim_listing",
        confidence=0.9,
        args={"quantity": "many"},
    )
    # Garbage quantity falls back to no high-impact flag — conf is high so
    # mutating-floor doesn't fire either.
    assert d.required is False


def test_decide_tool_address_change_high_impact() -> None:
    d = decide_for_tool_call(
        intent="update_profile",
        tool_name="update_user_profile",
        confidence=0.95,
        args={"address": "456 Elm"},
    )
    assert d.required is True
    assert d.kind == "high_impact"


def test_decide_tool_coordinate_change_high_impact() -> None:
    d = decide_for_tool_call(
        intent="update_profile",
        tool_name="update_user_profile",
        confidence=0.95,
        args={"lat": 40.0, "lng": -74.0},
    )
    assert d.required is True
    assert d.kind == "high_impact"


def test_decide_tool_address_irrelevant_args_pass() -> None:
    d = decide_for_tool_call(
        intent="update_profile",
        tool_name="update_user_profile",
        confidence=0.95,
        args={"name": "Sam"},
    )
    assert d.required is False


def test_decide_tool_mutating_low_conf_required() -> None:
    d = decide_for_tool_call(
        intent="share_food",
        tool_name="post_food_listing",
        confidence=CONFIRM_CONFIDENCE_FLOOR - 0.1,
        args={"title": "Bread"},
    )
    assert d.required is True
    assert d.kind == "low_confidence"


def test_decide_tool_mutating_high_conf_not_required() -> None:
    d = decide_for_tool_call(
        intent="share_food",
        tool_name="post_food_listing",
        confidence=0.95,
        args={"title": "Bread"},
    )
    assert d.required is False


def test_decide_tool_low_impact_never_flagged() -> None:
    for tool in (
        "send_notification", "mark_notifications_read",
        "dismiss_notification", "create_reminder",
    ):
        d = decide_for_tool_call(
            intent="schedule_pickup", tool_name=tool, confidence=0.1,
        )
        assert d.required is False, f"{tool} flagged unexpectedly"


def test_decide_tool_unknown_not_flagged() -> None:
    d = decide_for_tool_call(
        intent="claim_food", tool_name="lookup_something",
        confidence=0.1, args={"x": 1},
    )
    assert d.required is False
    assert d.kind == "none"


def test_decide_tool_args_snapshot_preserved_in_dict() -> None:
    d = decide_for_tool_call(
        intent="claim_food",
        tool_name="claim_listing",
        confidence=0.5,
        args={"quantity": 10, "listing_id": "abc"},
    )
    out = d.to_dict()
    assert out["args_snapshot"] == {"quantity": 10, "listing_id": "abc"}


def test_decide_tool_non_dict_args_normalized() -> None:
    d = decide_for_tool_call(
        intent="claim_food",
        tool_name="claim_listing",
        confidence=0.95,
        args="not-a-dict",  # type: ignore[arg-type]
    )
    assert d.required is False
    assert d.args_snapshot == {}


# ---------------------------------------------------------------------------
# evaluate_tool_results
# ---------------------------------------------------------------------------

def test_evaluate_tool_results_empty() -> None:
    assert evaluate_tool_results(intent="claim_food", confidence=0.9, tool_results=None) == []
    assert evaluate_tool_results(intent="claim_food", confidence=0.9, tool_results=[]) == []


def test_evaluate_tool_results_filters_non_dict() -> None:
    trs = ["junk", 42, None, {"tool": "delete_listing", "args": {"id": "x"}}]
    out = evaluate_tool_results(intent="claim_food", confidence=0.9, tool_results=trs)
    assert len(out) == 1
    assert out[0].required is True
    assert out[0].kind == "destructive"


def test_evaluate_tool_results_multiple_writes() -> None:
    trs = [
        {"tool": "search_food_listings", "args": {"q": "bread"}},   # not mutating
        {"tool": "claim_listing", "args": {"quantity": 8}},          # bulk → required
        {"tool": "delete_listing", "args": {"id": "abc"}},           # destructive → required
        {"tool": "send_notification", "args": {"title": "hi"}},      # low impact
    ]
    out = evaluate_tool_results(intent="claim_food", confidence=0.95, tool_results=trs)
    assert len(out) == 4
    required = [d for d in out if d.required]
    assert len(required) == 2
    kinds = {d.kind for d in required}
    assert kinds == {"high_impact", "destructive"}


def test_evaluate_tool_results_handles_name_alias() -> None:
    # Some tool results use "name" instead of "tool".
    trs = [{"name": "cancel_claim", "args": {"claim_id": "c1"}}]
    out = evaluate_tool_results(intent="cancel_claim", confidence=0.99, tool_results=trs)
    assert len(out) == 1
    assert out[0].required is True
    assert out[0].tool == "cancel_claim"


def test_evaluate_tool_results_missing_tool_name() -> None:
    trs = [{"args": {"x": 1}}]  # no tool key
    out = evaluate_tool_results(intent="claim_food", confidence=0.9, tool_results=trs)
    assert len(out) == 1
    assert out[0].required is False
    assert out[0].tool is None


# ---------------------------------------------------------------------------
# any_confirmation_required + format_decision_summary
# ---------------------------------------------------------------------------

def test_any_confirmation_required_empty_and_none() -> None:
    assert any_confirmation_required(None) is False
    assert any_confirmation_required([]) is False


def test_any_confirmation_required_mixed() -> None:
    rule_required = ConfirmationDecision(
        required=True, kind="destructive",
        reason_en="x", reason_es="y", tool="delete_listing",
    )
    rule_ok = ConfirmationDecision(
        required=False, kind="none",
        reason_en="x", reason_es="y", tool="search_food_listings",
    )
    assert any_confirmation_required([rule_ok]) is False
    assert any_confirmation_required([rule_ok, rule_required]) is True


def test_any_confirmation_required_ignores_non_decisions() -> None:
    assert any_confirmation_required(["junk", 42, None]) is False  # type: ignore[list-item]


def test_format_summary_empty() -> None:
    assert format_decision_summary([]) == ""
    assert format_decision_summary(None) == ""


def test_format_summary_only_non_required() -> None:
    d = ConfirmationDecision(
        required=False, kind="none",
        reason_en="x", reason_es="y", tool="search",
    )
    assert format_decision_summary([d]) == ""


def test_format_summary_en_with_tools() -> None:
    flagged = [
        ConfirmationDecision(required=True, kind="destructive",
                             reason_en="x", reason_es="y", tool="delete_listing"),
        ConfirmationDecision(required=True, kind="high_impact",
                             reason_en="x", reason_es="y", tool="claim_listing"),
    ]
    out = format_decision_summary(flagged, language="en")
    assert "Confirmation recommended" in out
    assert "`delete_listing`" in out
    assert "`claim_listing`" in out


def test_format_summary_es_with_tools() -> None:
    flagged = [
        ConfirmationDecision(required=True, kind="destructive",
                             reason_en="x", reason_es="y", tool="delete_listing"),
    ]
    out = format_decision_summary(flagged, language="es")
    assert "Confirmación recomendada" in out
    assert "`delete_listing`" in out


def test_format_summary_required_without_tool() -> None:
    # A required decision with no tool (e.g. intent-only) falls back to
    # a generic phrase.
    flagged = [
        ConfirmationDecision(required=True, kind="destructive",
                             reason_en="x", reason_es="y", tool=None),
    ]
    out_en = format_decision_summary(flagged, language="en")
    assert "Confirmation recommended" in out_en
    assert "high-impact" in out_en
    out_es = format_decision_summary(flagged, language="es")
    assert "Confirmación recomendada" in out_es
    assert "alto impacto" in out_es


# ---------------------------------------------------------------------------
# Integration: evaluate + summarize end-to-end
# ---------------------------------------------------------------------------

def test_end_to_end_destructive_write_surfaces() -> None:
    trs = [
        {"tool": "delete_listing", "args": {"listing_id": "abc"}},
    ]
    decisions = evaluate_tool_results(
        intent="delete_listing", confidence=0.95, tool_results=trs,
    )
    assert any_confirmation_required(decisions) is True
    summary = format_decision_summary(decisions, language="en")
    assert "Confirmation recommended" in summary
    assert "delete_listing" in summary
