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
            ("just 1", "3 of them"),
            ("All of them", "Still sealed"),
            "bread",
        ),
        (
            "List under Do Good Warehouse?",
            ("warehouse", "different school"),
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
            ("allergen", "gluten", "dairy"),
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
