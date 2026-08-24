"""Tests for unified natural conversation flow detection."""
from __future__ import annotations

from backend.ai.conversation_flow import (
    assess_input_clarity,
    build_turn_reminder,
    build_typo_confirm_reminder,
    build_ambiguous_pick_reminder,
    build_claim_quantity_reminder,
    build_claim_execute_reminder,
    build_food_order_spec_reminder,
    build_availability_answer_reminder,
    build_last_search_snapshot_reminder,
    claiming_tool_block_reason,
    detect_conversation_flow,
    enrich_claim_listing_args,
    resolve_listing_id_from_search,
    set_last_search_listings,
    _looks_like_multi_option_pick,
    enrich_post_food_listing_args,
    is_claiming_flow,
    is_finding_flow,
    is_request_flow,
    posting_tool_block_reason,
    update_new_share_block_reason,
)


class TestUpdateNewShareGuard:
    """A fresh share of a new food must not overwrite an existing listing."""

    def test_blocks_update_on_fresh_share(self):
        history = [
            {"role": "user", "message": "I want to share 5 apples"},
            {"role": "assistant", "message": "Posted! Apples are up."},
        ]
        reason = update_new_share_block_reason(
            "update_food_listing",
            {"title": "Carrots", "quantity": 3},
            "I want to share 3 carrots",
            history,
            "u-1",
        )
        assert reason is not None
        assert "post_food_listing" in reason

    def test_allows_explicit_edit_verb(self):
        reason = update_new_share_block_reason(
            "update_food_listing",
            {"title": "Apples", "quantity": 10},
            "update the apples to 10",
            [],
            "u-1",
        )
        assert reason is None

    def test_allows_index_reference(self):
        reason = update_new_share_block_reason(
            "update_food_listing",
            {"quantity": 10},
            "share #2 change qty to 10",
            [],
            "u-1",
        )
        assert reason is None

    def test_ignores_non_update_tools(self):
        assert update_new_share_block_reason(
            "post_food_listing", {}, "I want to share bread", [], "u-1",
        ) is None


class TestFlowDetection:
    def test_finding_on_distress(self):
        assert detect_conversation_flow("I'm starving, need food") == "finding"

    def test_posting_beats_finding_when_sharing(self):
        assert detect_conversation_flow("I want to share extra bread") == "posting"

    def test_claiming_from_pick_phrase(self):
        history = [
            {"role": "assistant", "message": "Here are 3 options near you..."},
        ]
        assert detect_conversation_flow("I'll take #2", history) == "claiming"

    def test_request_flow(self):
        assert detect_conversation_flow("I need to request food for my family") == "requesting"

    def test_idle_on_greeting(self):
        assert detect_conversation_flow("hello", []) == "idle"

    def test_hi_not_finding_with_stale_history(self):
        history = [
            {"role": "assistant", "message": "Which one sounds good? 1. Rice 2. Tomatoes"},
        ]
        assert detect_conversation_flow("hi", history) == "idle"

    def test_listing_number_after_search_is_claiming(self):
        history = [
            {"role": "assistant", "message": "Here's what's close: 1. Tomatoes 2. Eggs"},
        ]
        assert detect_conversation_flow("1", history) == "claiming"

    def test_family_food_need_is_finding_not_claiming(self):
        history = [
            {"role": "assistant", "message": "Nice choice — how many loaves?"},
        ]
        msg = "i have a large family of 10 people, i need some food"
        assert detect_conversation_flow(msg, history) == "finding"

    def test_want_some_food_is_finding(self):
        assert detect_conversation_flow("i want some food") == "finding"
        assert is_finding_flow("Something easy to prepare")

    def test_phantom_claim_qty_loop_breaks_on_denial(self):
        """Help menu → mistaken qty ask must not trap the user in claiming."""
        history = [
            {
                "role": "assistant",
                "message": (
                    "You can find free food near you, check pickups, or see events. "
                    "Which one would you like to try first?"
                ),
            },
            {"role": "user", "message": "Something easy to prepare"},
            {
                "role": "assistant",
                "message": (
                    "Looks like you're already in the middle of claiming some food. "
                    "How many would you like from that option?"
                ),
            },
        ]
        assert detect_conversation_flow("i want some food", history) == "finding"
        assert detect_conversation_flow("i dont have any", history) == "finding"
        assert detect_conversation_flow("we havent talked about anything", history) == "finding"
        assert detect_conversation_flow("which claim is it?", history) == "finding"

    def test_multi_pick_not_posting(self):
        history = [
            {"role": "assistant", "message": "Here's what's close: 1. Rice 2. Tomatoes 3. Eggs"},
        ]
        assert detect_conversation_flow("1, 2 and 3", history) == "claiming"


class TestAmbiguousPick:
    def test_one_and_two_after_search(self):
        history = [
            {"role": "assistant", "message": "Which one sounds good? 1. Rice 2. Tomatoes"},
        ]
        reminder = build_ambiguous_pick_reminder("1 and 2", history, lang="en")
        assert reminder is not None
        assert "confirm" in reminder.lower()

    def test_comma_separated_multi_pick(self):
        history = [
            {"role": "assistant", "message": "Here's what's close: 1. Rice 2. Tomatoes 3. Eggs"},
        ]
        reminder = build_ambiguous_pick_reminder("1, 2 and 3", history, lang="en")
        assert reminder is not None


class TestClaimQuantity:
    def test_quantity_reminder_after_listing_pick(self):
        history = [
            {"role": "assistant", "message": "Here's what's close: 1. Tomatoes — 10 items 2. Eggs — 5"},
        ]
        reminder = build_claim_quantity_reminder("1", history, lang="en")
        assert reminder is not None
        assert "how many" in reminder.lower()
        assert "claim_listing" in reminder.lower()

    def test_no_quantity_reminder_during_qty_answer(self):
        history = [
            {"role": "assistant", "message": "Nice choice — how many do you want? They have 10."},
        ]
        reminder = build_claim_quantity_reminder("2", history, lang="en")
        assert reminder is None

    def test_no_quantity_reminder_for_multi_pick(self):
        history = [
            {"role": "assistant", "message": "Which one? 1. Tomatoes 2. Eggs"},
        ]
        assert build_claim_quantity_reminder("1 and 2", history) is None

    def test_food_quantity_spec_not_multi_pick(self):
        assert not _looks_like_multi_option_pick("10 potatoes, 3tomatoes, and rice")

    def test_food_order_reminder(self):
        history = [
            {"role": "assistant", "message": "Here's what's close: 1. Potatoes 2. Tomatoes"},
        ]
        r = build_food_order_spec_reminder(
            "10 potatoes, 3 tomatoes", history, lang="en",
        )
        assert r is not None
        assert "listing" in r.lower()

    def test_active_claim_on_vague_qty_answer(self):
        # Qty wait only sticks when search/listing context exists (avoids
        # phantom claim loops after help-menu mistakes).
        history = [
            {
                "role": "assistant",
                "message": "Here's what's close near you: 1. Bread — 6 loaves",
            },
            {"role": "user", "message": "1"},
            {"role": "assistant", "message": "Nice choice — how many do you want?"},
        ]
        assert detect_conversation_flow("certain amount of them", history) == "claiming"

    def test_qty_ask_without_search_is_not_claiming(self):
        history = [
            {"role": "assistant", "message": "Nice choice — how many do you want?"},
        ]
        assert detect_conversation_flow("certain amount of them", history) != "claiming"

    def test_resolve_listing_index_to_uuid(self):
        listings = [
            {"id": "aaaa-bbbb", "title": "Tomatoes"},
            {"id": "cccc-dddd", "title": "Eggs"},
        ]
        set_last_search_listings("user-1", listings)
        resolved, err = resolve_listing_id_from_search(2, "user-1")
        assert err is None
        assert resolved == "cccc-dddd"

    def test_enrich_claim_resolves_index(self):
        set_last_search_listings("u1", [{"id": "uuid-1", "title": "Rice"}])
        out = enrich_claim_listing_args(
            {"listing_id": 1, "user_id": "u1"},
            "1",
            [{"role": "assistant", "message": "Here's what's close: 1. Rice"}],
            "u1",
        )
        assert out["listing_id"] == "uuid-1"

    def test_enrich_claim_from_history_when_qty_only(self):
        listings = [
            {"id": "uuid-tom", "title": "Tomatoes"},
            {"id": "uuid-egg", "title": "Eggs"},
        ]
        set_last_search_listings("u2", listings)
        history = [
            {"role": "assistant", "message": "Here's what's close: 1. Tomatoes 2. Eggs"},
            {"role": "user", "message": "1"},
            {"role": "assistant", "message": "Nice choice — how many do you want?"},
        ]
        out = enrich_claim_listing_args(
            {"user_id": "u2"},
            "3",
            history,
            "u2",
        )
        assert out["listing_id"] == "uuid-tom"
        assert out["quantity"] == 3

    def test_claim_execute_reminder_after_quantity(self):
        history = [
            {"role": "assistant", "message": "Here's what's close: 1. Rice"},
            {"role": "user", "message": "1"},
            {"role": "assistant", "message": "How many do you want?"},
        ]
        r = build_claim_execute_reminder("2", history, lang="en")
        assert r is not None
        assert "claim_listing" in r.lower()


class TestClaimDistractorBlock:
    def test_blocks_search_after_listing_pick(self):
        from backend.ai.conversation_flow import claiming_distractor_tool_block_reason

        history = [
            {"role": "assistant", "message": "Here's what's close: 1. Tomatoes 2. Eggs"},
        ]
        reason = claiming_distractor_tool_block_reason(
            "search_food_near_user", "1", history,
        )
        assert reason is not None
        assert "claim_listing" not in reason.lower() or "how many" in reason.lower()

    def test_blocks_search_on_quantity_answer(self):
        from backend.ai.conversation_flow import claiming_distractor_tool_block_reason

        history = [
            {"role": "assistant", "message": "How many do you want?"},
        ]
        reason = claiming_distractor_tool_block_reason(
            "get_active_communities", "2", history,
        )
        assert reason is not None
        assert "claim_listing" in reason.lower()


class TestBuildTurnReminder:
    def test_finding_includes_search_guidance(self):
        prompt, flow = build_turn_reminder("find food near me", [], lang="en")
        assert flow == "finding"
        assert prompt is not None
        assert "search_food_near_user" in prompt

    def test_claiming_includes_claim_steps(self):
        history = [{"role": "assistant", "message": "Which one sounds good?"}]
        prompt, flow = build_turn_reminder("the bread one", history, lang="en")
        assert flow == "claiming"
        assert prompt is not None
        assert "claim_listing" in prompt

    def test_idle_returns_none(self):
        prompt, flow = build_turn_reminder("thanks!", [], lang="en")
        assert flow == "idle"
        assert prompt is None

    def test_multi_turn_idle_gets_rhythm_via_export(self):
        from backend.ai.conversation_flow import natural_rhythm_prompt

        rhythm = natural_rhythm_prompt("en")
        assert "ONE question" in rhythm


class TestFlowHelpers:
    def test_is_finding_not_posting(self):
        assert is_finding_flow("food near me", []) is True
        assert is_finding_flow("share food", []) is False

    def test_is_claiming_not_when_posting(self):
        assert is_claiming_flow("claim it", []) is True
        assert is_claiming_flow("post a listing", []) is False

    def test_is_request_not_when_posting(self):
        assert is_request_flow("post a request for food", []) is True
        assert is_request_flow("donate bread", []) is False

    def test_need_food_is_finding_not_request(self):
        assert is_finding_flow("need food for my kids", []) is True
        assert is_request_flow("need food for my kids", []) is False


class TestPostingEnrichment:
    def test_enrich_community_from_description(self):
        history = [
            {"role": "assistant", "message": "Which community should this go under?"},
            {"role": "user", "message": "Yes, use Do Good Warehouse"},
        ]
        args = enrich_post_food_listing_args(
            {
                "title": "Bananas",
                "description": "Community: Do Good Warehouse. Pickup only.",
            },
            "Yes, post it",
            history,
        )
        assert args["community_name"] == "Do Good Warehouse"
        assert args["community_confirmed"] is True

    def test_blocks_post_without_photo_step(self):
        history = [
            {"role": "user", "message": "I want to share 20 bananas"},
            {"role": "assistant", "message": "Which community?"},
            {"role": "user", "message": "Do Good Warehouse"},
            {"role": "assistant", "message": "When does it expire?"},
            {"role": "user", "message": "expiry 2030-01-01"},
            {
                "role": "assistant",
                "message": "Please add a short description for recipients.",
            },
            {"role": "user", "message": "Ripe, still in the bunch."},
        ]
        reason = posting_tool_block_reason("Yes, post it", history)
        assert reason is not None
        assert "photo" in reason.lower()


class TestTypoConfirm:
    def test_detects_known_typo(self):
        assessment = assess_input_clarity("I have 3 loav of bred to share")
        assert assessment["unclear"] is True
        assert any(h["guess"] == "bread" for h in assessment["typo_hits"])

    def test_skips_clear_yes(self):
        assert assess_input_clarity("yes").get("unclear") is False

    def test_builds_confirm_reminder(self):
        reminder = build_typo_confirm_reminder("I want to share appels", [], lang="en")
        assert reminder is not None
        assert "did you mean" in reminder.lower()

    def test_fuzzy_banana_typo(self):
        assessment = assess_input_clarity("share 5 banans")
        assert assessment["unclear"] is True

    def test_hungry_not_flagged(self):
        assessment = assess_input_clarity("I am hungry need food")
        assert not any(h["token"] == "hungry" for h in assessment["typo_hits"])

    def test_iam_typo_detected(self):
        assessment = assess_input_clarity("iam hungry, i need some food")
        assert assessment["unclear"] is True
        assert any(h.get("guess") == "I am" for h in assessment["typo_hits"])
        assert not any(h["token"] == "hungry" for h in assessment["typo_hits"])


class TestAvailabilityQuestions:
    def setup_method(self):
        set_last_search_listings("u-avail", [
            {"id": "uuid-milk", "title": "Fresh Milk", "quantity": 4, "unit": "gallons", "display_index": 1},
            {"id": "uuid-bread", "title": "Sourdough Bread", "quantity": 2, "unit": "loaves", "display_index": 2},
        ])

    def test_how_much_left_is_finding_not_claiming(self):
        history = [
            {"role": "assistant", "message": "Here's what's close: 1. Fresh Milk 2. Bread"},
            {"role": "user", "message": "I want milk"},
        ]
        assert detect_conversation_flow("how much milk is left?", history) == "finding"

    def test_availability_reminder_includes_quantity(self):
        history = [
            {"role": "assistant", "message": "Here's what's close: 1. Fresh Milk"},
        ]
        reminder = build_availability_answer_reminder(
            "how much milk is left?", history, user_id="u-avail",
        )
        assert reminder is not None
        assert "4" in reminder
        assert "claim_listing" in reminder.lower()

    def test_claim_blocked_on_availability_question(self):
        reason = claiming_tool_block_reason(
            "how many gallons of milk are left?", [], {}, "u-avail",
        )
        assert reason is not None
        assert "claim_listing" in reason.lower()

    def test_search_snapshot_shows_listings(self):
        snap = build_last_search_snapshot_reminder("u-avail")
        assert snap is not None
        assert "Fresh Milk" in snap
        assert "4" in snap


class TestWrongListingFallback:
    def test_no_history_fallback_when_food_not_in_search(self):
        set_last_search_listings("u-wrong", [
            {"id": "uuid-bread", "title": "Sourdough Bread"},
        ])
        history = [
            {"role": "assistant", "message": "Here's what's close: 1. Sourdough Bread"},
            {"role": "user", "message": "1"},
        ]
        out = enrich_claim_listing_args(
            {"user_id": "u-wrong"},
            "claim milk",
            history,
            "u-wrong",
        )
        assert out.get("_no_matching_listing_food") == "milk"
        assert out.get("listing_id") is None


class TestStaleClaimIntake:
    def test_find_food_after_claim_success_is_finding(self):
        history = [
            {"role": "assistant", "message": "Here's what's close: 1. Milk 2. Bread"},
            {"role": "user", "message": "1"},
            {"role": "assistant", "message": "How many do you want?"},
            {"role": "user", "message": "2"},
            {"role": "assistant", "message": "Claimed 2 gallons of Milk! Pickup at 123 Main."},
        ]
        assert detect_conversation_flow("find available food near me", history) == "finding"

    def test_claim_intake_closed_after_success(self):
        history = [
            {"role": "assistant", "message": "Claimed 2 loaves! Pickup at Oak St."},
        ]
        from backend.ai.conversation_flow import _claim_intake_open
        assert not _claim_intake_open("find food", history)

    def test_search_not_blocked_after_claim(self):
        from backend.ai.conversation_flow import claiming_distractor_tool_block_reason

        history = [
            {"role": "assistant", "message": "Claimed 2 loaves! Pickup at Oak St."},
        ]
        reason = claiming_distractor_tool_block_reason(
            "search_food_near_user", "what food is available?", history,
        )
        assert reason is None

    def test_fresh_search_reminder_after_claim(self):
        from backend.ai.conversation_flow import build_fresh_search_after_claim_reminder

        history = [
            {"role": "assistant", "message": "Claimed 2 loaves! Pickup at Oak St."},
        ]
        reminder = build_fresh_search_after_claim_reminder(
            "show me available food", history,
        )
        assert reminder is not None
        assert "search_food_near_user" in reminder

    def test_cache_updates_after_claim(self):
        from backend.ai.conversation_flow import (
            get_last_search_listings,
            update_last_search_listing_after_claim,
        )
        set_last_search_listings("u-cache", [
            {"id": "lid-1", "title": "Milk", "quantity": 10, "display_index": 1},
            {"id": "lid-2", "title": "Bread", "quantity": 5, "display_index": 2},
        ])
        update_last_search_listing_after_claim("u-cache", "lid-1", remaining=7)
        rows = get_last_search_listings("u-cache")
        milk = next(r for r in rows if r["id"] == "lid-1")
        assert milk["quantity"] == 7

    def test_cache_removes_fully_claimed_listing(self):
        from backend.ai.conversation_flow import (
            get_last_search_listings,
            update_last_search_listing_after_claim,
        )
        set_last_search_listings("u-full", [
            {"id": "lid-1", "title": "Milk", "quantity": 2, "display_index": 1},
        ])
        update_last_search_listing_after_claim(
            "u-full", "lid-1", remaining=0, fully_claimed=True,
        )
        assert get_last_search_listings("u-full") == []
