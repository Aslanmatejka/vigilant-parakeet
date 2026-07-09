"""Robustness tests for the claiming flow.

Covers the confusion patterns the user reported:
  1. 'claim 2 oranges' → quantity + food parsed from a single message.
  2. Nouri asks 'how many X' for a listing that doesn't exist yet.
  3. 'claim in progress' persists when the user pivots to a new listing.
"""
from __future__ import annotations

from backend.ai.conversation_flow import (
    _extract_claim_intent,
    _user_pivoted_claim_target,
    _user_just_picked_listing,
    claiming_distractor_tool_block_reason,
    claiming_tool_block_reason,
    enrich_claim_listing_args,
    set_last_search_listings,
)


# ---------------------------------------------------------------------------
# Bug 1: 'claim 2 oranges' — parse quantity + food from one message
# ---------------------------------------------------------------------------


class TestClaimIntentParsing:
    def test_extract_quantity_and_food_from_claim(self):
        # The user's original failure mode: 'claim 2 oranges' →
        # Nouri asked 'how many 2 oranges?' because the quantity + food
        # weren't parsed from the same message.
        out = _extract_claim_intent("claim 2 oranges")
        assert out.get("quantity") == 2
        assert out.get("title_hint") == "oranges"
        # Also cover an in-vocabulary food to prove the primary branch.
        out2 = _extract_claim_intent("claim 2 apples")
        assert out2.get("quantity") == 2
        assert out2.get("title_hint") == "apples"

    def test_ill_take_with_loaves_of_bread(self):
        out = _extract_claim_intent("I'll take 3 loaves of bread")
        assert out.get("quantity") == 3
        assert out.get("title_hint") == "bread"

    def test_reserve_verb_alone_no_quantity(self):
        out = _extract_claim_intent("reserve the apples")
        assert out.get("quantity") is None
        assert out.get("title_hint") == "apples"

    def test_number_only_is_not_claim_intent(self):
        # A plain "2" reply after a how-many question is handled by the
        # quantity extractor, not the claim-intent parser.
        out = _extract_claim_intent("2")
        assert out == {}

    def test_multi_pick_not_treated_as_claim(self):
        out = _extract_claim_intent("1 and 2")
        assert out == {}


class TestClaimQuantityInFirstMessage:
    def setup_method(self):
        set_last_search_listings("u-qty", [
            {"id": "uuid-apples", "title": "Fresh Apples"},
            {"id": "uuid-bread", "title": "Sourdough Bread"},
        ])

    def test_enrich_extracts_qty_and_listing_up_front(self):
        history = [
            {"role": "assistant", "message": "Here's what's close: 1. Fresh Apples 2. Sourdough Bread"},
        ]
        out = enrich_claim_listing_args(
            {"user_id": "u-qty"},
            "claim 2 apples",
            history,
            "u-qty",
        )
        assert out.get("listing_id") == "uuid-apples"
        assert out.get("quantity") == 2

    def test_block_reason_skipped_when_qty_already_given(self):
        history = [
            {"role": "assistant", "message": "Here's what's close: 1. Fresh Apples 2. Sourdough Bread"},
        ]
        # Simulate what enrich would produce.
        args = {
            "user_id": "u-qty",
            "listing_id": "uuid-apples",
            "quantity": 2,
        }
        reason = claiming_tool_block_reason(
            "claim 2 apples", history, args, "u-qty",
        )
        assert reason is None


# ---------------------------------------------------------------------------
# Bug 2: Nouri asks 'how many X' for a listing that doesn't exist
# ---------------------------------------------------------------------------


class TestListingExistenceCheck:
    def setup_method(self):
        set_last_search_listings("u-nex", [
            {"id": "uuid-bread", "title": "Sourdough Bread"},
        ])

    def test_no_matching_food_sets_marker(self):
        history = [
            {"role": "assistant", "message": "Here's what's close: 1. Sourdough Bread"},
        ]
        out = enrich_claim_listing_args(
            {"user_id": "u-nex"},
            "claim 2 apples",
            history,
            "u-nex",
        )
        # Bread is in search cache; apples aren't. Marker must fire.
        assert out.get("_no_matching_listing_food") == "apples"

    def test_block_reason_tells_model_to_search(self):
        history = [
            {"role": "assistant", "message": "Here's what's close: 1. Sourdough Bread"},
        ]
        args = {
            "user_id": "u-nex",
            "_no_matching_listing_food": "apples",
        }
        reason = claiming_tool_block_reason(
            "claim 2 apples", history, args, "u-nex",
        )
        assert reason is not None
        assert "search_food_near_user" in reason
        assert "apples" in reason
        # Must not *instruct* the model to ask "how many"; must instruct search.
        assert "ask how many" not in reason.lower()


# ---------------------------------------------------------------------------
# Bug 3: Pivot to another listing — clear stale claim intent
# ---------------------------------------------------------------------------


class TestClaimPivot:
    def setup_method(self):
        set_last_search_listings("u-pivot", [
            {"id": "uuid-bread", "title": "Sourdough Bread"},
            {"id": "uuid-apples", "title": "Fresh Apples"},
        ])

    def test_actually_i_want_something_else_is_pivot(self):
        history = [
            {"role": "user", "message": "1"},
            {"role": "assistant", "message": "How many loaves?"},
        ]
        assert _user_pivoted_claim_target(
            "actually I want the apples instead", history, "u-pivot",
        )

    def test_different_number_after_first_pick_is_pivot(self):
        history = [
            {"role": "assistant", "message": "Here's what's close: 1. Bread 2. Apples"},
            {"role": "user", "message": "1"},
            {"role": "assistant", "message": "How many loaves?"},
        ]
        assert _user_pivoted_claim_target("actually 2", history, "u-pivot")

    def test_same_food_repeated_is_not_pivot(self):
        history = [
            {"role": "assistant", "message": "How many loaves of bread?"},
        ]
        # Reply to how-many with same food → not a pivot.
        assert not _user_pivoted_claim_target("2 bread", history, "u-pivot")

    def test_pivot_lets_search_through(self):
        history = [
            {"role": "assistant", "message": "Here's what's close: 1. Bread"},
            {"role": "user", "message": "1"},
            {"role": "assistant", "message": "How many?"},
        ]
        # When pivoting, search should NOT be blocked.
        reason = claiming_distractor_tool_block_reason(
            "search_food_near_user",
            "actually can you find me some apples instead",
            history,
            "u-pivot",
        )
        assert reason is None


# ---------------------------------------------------------------------------
# General: 'how many' block does NOT fire when quantity already in message
# ---------------------------------------------------------------------------


class TestPickListingHeuristic:
    def test_message_with_quantity_is_not_just_a_pick(self):
        history = [
            {"role": "assistant", "message": "Here's what's close: 1. Fresh Apples"},
        ]
        # Contains both intent + quantity — should not trigger the "how many" block.
        assert not _user_just_picked_listing("claim 2 apples", history)

    def test_bare_number_pick_still_triggers_how_many(self):
        history = [
            {"role": "assistant", "message": "Here's what's close: 1. Fresh Apples"},
        ]
        assert _user_just_picked_listing("1", history)


class TestMilkFoodIntent:
    def test_i_want_milk_is_finding(self):
        from backend.ai.conversation_flow import detect_conversation_flow
        assert detect_conversation_flow("I want milk", []) == "finding"
