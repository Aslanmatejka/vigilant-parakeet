"""Do-it-for-me suggestion chips must match each assistant question."""

from __future__ import annotations

import pytest

from backend.agent.suggestion_chips import build_turn_suggestions
from backend.ai.ai_engine import generate_quick_replies


def _labels(chips) -> list[str]:
    return [c if isinstance(c, str) else (c.get("label") or "") for c in chips]


def _joined(chips) -> str:
    return " ".join(_labels(chips)).lower()


@pytest.mark.parametrize(
    "text,need,forbid,user_message",
    [
        (
            "How would you like to proceed with sharing?",
            ("Do it for me", "Open the form", "Guide"),
            ("5 apples",),
            "I want to share food",
        ),
        (
            "What food do you want to share, and how much do you have?",
            ("apple", "bread"),
            ("Tomorrow", "Still sealed", "Yes, post it"),
            "Do it for me",
        ),
        (
            "How many loaves?",
            ("1", "3", "5"),
            ("All of them", "Still sealed"),
            "bread",
        ),
        (
            "List under Do Good Warehouse?",
            ("warehouse", "different community"),
            ("alameda", "Yes, post it"),
            "Do it for me",
        ),
        (
            "When does it expire?",
            ("Tomorrow",),
            ("Still sealed", "Yes, post it"),
            "Do it for me",
        ),
        (
            "Please add a short description for recipients.",
            ("sealed", "homemade", "leftover"),
            ("Tomorrow", "Attach a photo", "No allergens"),
            "Do it for me",
        ),
        (
            "Description?",
            ("sealed", "homemade"),
            ("Tomorrow", "Yes, post it"),
            "Do it for me",
        ),
        (
            "Got it — best by tomorrow. Please add a short description for recipients.",
            ("sealed", "homemade"),
            ("Tomorrow", "Attach a photo"),
            "Do it for me",
        ),
        (
            "Please attach a photo of the food — required before I can post.",
            ("Attach a photo",),
            ("Still sealed", "Yes, post it", "skip"),
            "Do it for me",
        ),
        (
            "Ready to post 3 loaves under Alameda Unified, with photo. Shall I post it?",
            ("Yes, post it",),
            ("Attach a photo", "Still sealed", "No allergen"),
            "Do it for me",
        ),
        (
            "Ready to post — no allergens noted. Does this look right?",
            ("Yes, post it",),
            ("No allergen", "Still sealed", "Tomorrow"),
            "Do it for me",
        ),
        (
            "Ready to post: 100 boxes under Alameda Unified. Shall I post these now?",
            ("Attach a photo",),
            ("Yes, post it",),
            "Do it for me",
        ),
        (
            "Does this contain nuts, dairy, eggs, soy, or wheat?",
            ("No allergens", "gluten", "dairy"),
            ("Still sealed", "Yes, post it"),
            "Do it for me",
        ),
        (
            "Your listing is live! Anything else you want to share?",
            ("Share something else", "Find food"),
            ("Yes, post it", "Still sealed"),
            "Do it for me",
        ),
    ],
)
def test_do_it_for_me_chips_match_question(text, need, forbid, user_message):
    for fn_name, chips in (
        ("quick", generate_quick_replies(text, user_message=user_message, suggested_community="Alameda Unified")),
        ("built", build_turn_suggestions(
            text, "en", tool_results=[], min_chips=0, last_user_message=user_message,
        )),
    ):
        joined = _joined(chips)
        assert chips, f"{fn_name}: empty for {text!r}"
        assert any(n.lower() in joined for n in need), f"{fn_name}: {text!r} -> {_labels(chips)}"
        for bad in forbid:
            assert bad.lower() not in joined, f"{fn_name}: {text!r} got forbidden {bad!r} in {_labels(chips)}"


class TestChipTurnRegression:
    """Highest-impact wrong-chip failures from the end-to-end plan."""

    def test_fork_does_not_steal_mid_flow_food_ask(self):
        text = (
            "Got it — I'll handle everything for you in chat. "
            "What food do you want to share, and how much?"
        )
        out = generate_quick_replies(
            text,
            user_message="bread",
            assistance_reminder="HANDS-ON MODE — SHARE FOOD",
        )
        joined = " ".join(out).lower()
        assert "apple" in joined or "bread" in joined or "vegetable" in joined
        assert "do it for me" not in joined
        assert "open the form" not in joined

    def test_fork_ack_without_guide_is_not_fork(self):
        from backend.ai.chip_turn import classify_share_chip_turn
        turn = classify_share_chip_turn(
            "Perfect — I'll handle everything for you in chat. What food are you sharing?",
            user_message="5 apples",
            assistance_reminder="HANDS-ON MODE — SHARE FOOD",
        )
        assert turn in ("food", "food_qty")

    def test_description_before_photo_narration(self):
        text = (
            "Please add a short description for recipients. "
            "After that I'll need a photo."
        )
        out = generate_quick_replies(text, user_message="Do it for me")
        assert "Still sealed" in out
        assert "Attach a photo" not in out

    def test_address_look_good_not_post_confirm(self):
        text = (
            "Should I use your profile address 1423 Park St for the pickup spot? "
            "Does that look good?"
        )
        out = generate_quick_replies(
            text,
            user_message="Do it for me",
            suggested_community="Alameda Unified",
        )
        joined = " ".join(out).lower()
        assert "yes, post it" not in joined
        assert "address" in joined or "use that" in joined or "saved" in joined

    def test_real_fork_still_works(self):
        out = generate_quick_replies(
            "Would you like me to handle everything here in chat, "
            "or guide you step by step on the Share Food page?",
            user_message="I want to share food",
        )
        joined = " ".join(out).lower()
        assert "do it for me" in joined
        assert "guide" in joined

    def test_classified_expiry_does_not_fall_through_to_help(self):
        text = (
            "When does it expire? I'm happy to guide you if you're lost."
        )
        out = generate_quick_replies(
            text,
            user_message="Do it for me",
            assistance_reminder="HANDS-ON MODE — SHARE FOOD",
        )
        joined = " ".join(out).lower()
        assert "tomorrow" in joined
        assert "how does this work" not in joined
        assert "find food near me" not in joined
        assert "do it for me" not in joined

    def test_hands_on_reminder_never_returns_fork_on_food_ask(self):
        out = generate_quick_replies(
            "What food are you sharing today?",
            user_message="Do it for me",
            assistance_reminder="HANDS-ON MODE — SHARE FOOD",
        )
        joined = " ".join(out).lower()
        assert "do it for me" not in joined
        assert "open the form" not in joined
        assert "guide me" not in joined

    def test_search_results_do_not_steal_expiry_ask(self):
        tool_results = [{
            "tool": "search_food_listings",
            "ok": True,
            "result": {
                "results": [
                    {"title": "Fresh Bread"},
                    {"title": "Vegetable Box"},
                ],
            },
        }]
        chips = build_turn_suggestions(
            "When does it expire?",
            "en",
            tool_results=tool_results,
            min_chips=0,
            last_user_message="Do it for me",
            assistance_reminder="HANDS-ON MODE — SHARE FOOD",
        )
        joined = _joined(chips)
        assert "tomorrow" in joined
        assert "claim" not in joined

    def test_search_results_do_not_steal_description_ask(self):
        tool_results = [{
            "tool": "search_food_listings",
            "ok": True,
            "result": {"results": [{"title": "Fresh Bread"}]},
        }]
        chips = build_turn_suggestions(
            "Please add a short description for recipients.",
            "en",
            tool_results=tool_results,
            min_chips=0,
            last_user_message="Do it for me",
        )
        joined = _joined(chips)
        assert "sealed" in joined
        assert "claim" not in joined

    def test_best_by_ack_then_description_ask_not_expiry_chips(self):
        text = (
            "Perfect, I'll set the best-by date as one month from now. "
            "Can you give me one short sentence describing the bread? "
            "For example, how fresh it is or how it's packed."
        )
        out = generate_quick_replies(
            text,
            user_message="In a month",
            assistance_reminder="HANDS-ON MODE — SHARE FOOD",
        )
        joined = " ".join(out).lower()
        assert "sealed" in joined or "homemade" in joined
        assert "tomorrow" not in joined
        assert "in 2 days" not in joined
        assert "in a month" not in joined

    def test_got_the_photo_ready_to_post_not_attach_chip(self):
        text = (
            "Got the photo, thanks! Here's what I have: 2 loaves of good bread "
            "from the bakery, best by September 25, pickup at your place under "
            "Do Good Warehouse. Ready to post this?"
        )
        out = generate_quick_replies(
            text,
            user_message="image: https://example.com/bread.jpg",
            assistance_reminder="HANDS-ON MODE — SHARE FOOD",
        )
        joined = " ".join(out).lower()
        assert "yes, post it" in joined
        assert "attach a photo" not in joined

    def test_short_description_of_eggs_in_carton_is_description_chips(self):
        text = (
            "Got it. Could you give me a short description of the eggs? "
            "For example, are they fresh, still in the carton, or "
            "anything else someone should know?"
        )
        out = generate_quick_replies(text, user_message="Do it for me")
        joined = " ".join(out).lower()
        assert "sealed" in joined or "homemade" in joined
        assert "tomorrow" not in joined
        assert "no allergens" not in joined

