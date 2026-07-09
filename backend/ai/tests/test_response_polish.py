"""Tests for assistant response polish layer."""
from backend.ai.response_polish import (
    enrich_tool_action,
    polish_assistant_response,
    tool_result_ok,
)


def test_tool_result_ok_prefers_success_flag():
    assert tool_result_ok({"success": True, "error": "ignored"}) is True
    assert tool_result_ok({"error": "nope"}) is False
    assert tool_result_ok({"summary": "ok"}) is True


def test_polish_strips_uuids():
    text = "Claim id d7cf24db-166e-4f6c-8cd5-076d7135784d done"
    out = polish_assistant_response(text, [], lang="en")
    assert "d7cf24db" not in out
    assert "done" in out.lower()


def test_polish_dedupes_search_list_when_cards_present():
    text = (
        "Here's what's nearby:\n"
        "1. Tomatoes — 0.5 mi\n"
        "2. Bread — 1.2 mi\n"
        "3. Kale — 2 mi\n"
        "Which number works for you?"
    )
    actions = [{
        "tool": "search_food_near_user",
        "ok": True,
        "listings": [{"id": "a", "title": "Tomatoes", "display_index": 1}],
    }]
    out = polish_assistant_response(text, actions, lang="en")
    assert "1. Tomatoes" not in out
    assert "Which number" in out


def test_polish_does_not_inject_claim_boilerplate():
    actions = [{
        "tool": "claim_listing",
        "ok": True,
        "title": "Tomatoes",
        "quantity": 2,
        "pickup_location": "1423 Park St",
    }]
    out = polish_assistant_response("Great!", actions, lang="en")
    assert out == "Great!"


def test_enrich_search_action_forwards_listings():
    result = {
        "listings": [
            {"id": "x", "title": "Bread", "quantity": 3, "display_index": 1, "secret": "nope"},
        ],
        "total": 1,
    }
    entry = enrich_tool_action("search_food_near_user", result, {"tool": "search_food_near_user", "ok": True})
    assert len(entry["listings"]) == 1
    assert entry["listings"][0]["title"] == "Bread"
    assert "secret" not in entry["listings"][0]
