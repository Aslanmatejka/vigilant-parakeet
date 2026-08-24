"""Do-it-for-me suggestion chips — fixed per flow step, not reply heuristics."""

from __future__ import annotations

import pytest

from backend.agent.suggestion_chips import (
    build_labeled_hands_on_share_chips,
    build_turn_suggestions,
    resolve_hands_on_share_chip_step,
)


def _labels(chips) -> list[str]:
    return [c if isinstance(c, str) else (c.get("label") or "") for c in chips]


def _joined(chips) -> str:
    return " ".join(_labels(chips)).lower()


def _hands_on_history(*extra) -> list[dict]:
    base = [
        {"role": "user", "message": "I want to share food"},
        {"role": "assistant", "message": "How would you like to proceed with sharing?"},
        {"role": "user", "message": "Do it for me"},
    ]
    return base + list(extra)


def _chips_for_step(step: str, response_text: str, history: list, user_message: str = "Do it for me"):
    return build_turn_suggestions(
        response_text,
        "en",
        tool_results=[],
        min_chips=0,
        last_user_message=user_message,
        assistance_reminder="hands-on share posting",
        history=history,
        user_context={
            "suggested_community": "Ruby Bridges Elementary CC",
            "active_communities": [
                "Ruby Bridges Elementary CC",
                "Do Good Warehouse",
                "Alameda Unified",
            ],
        },
    )


@pytest.mark.parametrize(
    "step,response_text,history_extra,user_message,need,forbid",
    [
        (
            "food_qty",
            "What food do you want to share, and how much do you have?",
            [],
            "Do it for me",
            ("apple", "bread"),
            ("Tomorrow", "Still sealed", "Yes, post it"),
        ),
        (
            "qty",
            "How many loaves?",
            [
                {"role": "assistant", "message": "What food and how much?"},
                {"role": "user", "message": "bread"},
            ],
            "bread",
            ("1", "3", "5"),
            ("Still sealed", "All of them"),
        ),
        (
            "community",
            "Your profile is linked to Ruby Bridges Elementary CC. Use that one?",
            [
                {"role": "assistant", "message": "What food and how much?"},
                {"role": "user", "message": "3 loaves of bread"},
            ],
            "3 loaves of bread",
            ("Ruby", "Different community"),
            ("Yes, post it", "alameda"),
        ),
        (
            "expiry",
            "When does it expire?",
            [
                {"role": "assistant", "message": "What food and how much?"},
                {"role": "user", "message": "3 loaves of bread"},
                {"role": "assistant", "message": "List under Ruby Bridges?"},
                {"role": "user", "message": "Yes, list under Ruby Bridges Elementary CC"},
            ],
            "Yes, list under Ruby Bridges Elementary CC",
            ("Tomorrow",),
            ("Still sealed", "Yes, post it"),
        ),
        (
            "description",
            "Please add a short description for recipients.",
            [
                {"role": "assistant", "message": "What food and how much?"},
                {"role": "user", "message": "3 loaves of bread"},
                {"role": "assistant", "message": "List under Ruby Bridges?"},
                {"role": "user", "message": "Yes, list under Ruby Bridges Elementary CC"},
                {"role": "assistant", "message": "When does it expire?"},
                {"role": "user", "message": "Tomorrow"},
            ],
            "Tomorrow",
            ("sealed", "homemade", "leftover"),
            ("Tomorrow", "Attach a photo", "No allergens"),
        ),
        (
            "description",
            "Description?",
            [
                {"role": "assistant", "message": "What food and how much?"},
                {"role": "user", "message": "3 loaves of bread"},
                {"role": "assistant", "message": "List under Ruby Bridges?"},
                {"role": "user", "message": "Yes, list under Ruby Bridges Elementary CC"},
                {"role": "assistant", "message": "When does it expire?"},
                {"role": "user", "message": "Tomorrow"},
            ],
            "Tomorrow",
            ("sealed", "homemade"),
            ("Tomorrow", "Yes, post it"),
        ),
        (
            "photo",
            "Please attach a photo of the food — required before I can post.",
            [
                {"role": "assistant", "message": "What food and how much?"},
                {"role": "user", "message": "3 loaves of bread"},
                {"role": "assistant", "message": "List under Ruby Bridges?"},
                {"role": "user", "message": "Yes, list under Ruby Bridges Elementary CC"},
                {"role": "assistant", "message": "When does it expire?"},
                {"role": "user", "message": "Tomorrow"},
                {"role": "assistant", "message": "Please add a short description."},
                {"role": "user", "message": "Still sealed"},
            ],
            "Still sealed",
            ("Attach a photo",),
            ("Still sealed", "Yes, post it", "skip"),
        ),
        (
            "post_confirm",
            "Ready to post 3 loaves under Alameda Unified, with photo. Shall I post it?",
            [
                {"role": "assistant", "message": "What food and how much?"},
                {"role": "user", "message": "3 loaves of bread"},
                {"role": "assistant", "message": "List under Ruby Bridges?"},
                {"role": "user", "message": "Yes, list under Ruby Bridges Elementary CC"},
                {"role": "assistant", "message": "When does it expire?"},
                {"role": "user", "message": "Tomorrow"},
                {"role": "assistant", "message": "Please add a short description."},
                {"role": "user", "message": "Still sealed"},
                {"role": "user", "message": "image: https://example.com/food.jpg"},
            ],
            "image: https://example.com/food.jpg",
            ("Yes, post it",),
            ("Attach a photo", "No allergen"),
        ),
        (
            "post_confirm",
            "Ready to post — no allergens noted. Does this look right?",
            [
                {"role": "assistant", "message": "What food and how much?"},
                {"role": "user", "message": "3 loaves of bread"},
                {"role": "assistant", "message": "List under Ruby Bridges?"},
                {"role": "user", "message": "Yes, list under Ruby Bridges Elementary CC"},
                {"role": "assistant", "message": "When does it expire?"},
                {"role": "user", "message": "Tomorrow"},
                {"role": "assistant", "message": "Please add a short description."},
                {"role": "user", "message": "Still sealed"},
                {"role": "user", "message": "image: https://example.com/food.jpg"},
            ],
            "image: https://example.com/food.jpg",
            ("Yes, post it",),
            ("No allergen", "Still sealed", "Tomorrow"),
        ),
        (
            "photo",
            "Ready to post: 100 boxes under Alameda Unified. Shall I post these now?",
            [
                {"role": "assistant", "message": "What food and how much?"},
                {"role": "user", "message": "100 boxes"},
                {"role": "assistant", "message": "List under Alameda Unified?"},
                {"role": "user", "message": "Yes, list under Alameda Unified"},
                {"role": "assistant", "message": "When does it expire?"},
                {"role": "user", "message": "Tomorrow"},
                {"role": "assistant", "message": "Please add a short description."},
                {"role": "user", "message": "Still sealed"},
            ],
            "Still sealed",
            ("Attach a photo",),
            ("Yes, post it",),
        ),
        (
            "allergen",
            "Does this contain nuts, dairy, eggs, soy, or wheat?",
            [
                {"role": "assistant", "message": "What food and how much?"},
                {"role": "user", "message": "3 loaves of bread"},
                {"role": "assistant", "message": "List under Ruby Bridges?"},
                {"role": "user", "message": "Yes, list under Ruby Bridges Elementary CC"},
                {"role": "assistant", "message": "When does it expire?"},
                {"role": "user", "message": "Tomorrow"},
            ],
            "Tomorrow",
            ("No allergens", "gluten", "dairy"),
            ("Still sealed", "Yes, post it"),
        ),
        (
            "success",
            "Your listing is live! Anything else you want to share?",
            [],
            "Do it for me",
            ("Share something else", "Find food"),
            ("Yes, post it", "Still sealed"),
        ),
    ],
)
def test_labeled_hands_on_chips_match_step(
    step, response_text, history_extra, user_message, need, forbid,
):
    history = _hands_on_history(*history_extra)
    resolved = resolve_hands_on_share_chip_step(
        user_message,
        history,
        assistance_reminder="hands-on share posting",
        response_text=response_text,
    )
    assert resolved == step, f"expected step {step!r}, got {resolved!r}"

    chips = _chips_for_step(step, response_text, history, user_message)
    joined = _joined(chips)
    assert chips, f"empty chips for step {step!r}"
    assert all(
        isinstance(c, dict) and c.get("kind") == "hands_on_step" for c in chips
    ), f"chips must be hands_on_step labeled: {_labels(chips)}"
    assert any(n.lower() in joined for n in need), f"{step!r} -> {_labels(chips)}"
    for bad in forbid:
        assert bad.lower() not in joined, f"{step!r} got forbidden {bad!r} in {_labels(chips)}"


def test_labeled_chips_stable_across_rephrasing():
    """Step labels stay the same even when Nouri rephrases the question."""
    history = _hands_on_history(
        {"role": "assistant", "message": "What food and how much?"},
        {"role": "user", "message": "3 loaves of bread"},
        {"role": "assistant", "message": "List under Ruby Bridges?"},
        {"role": "user", "message": "Yes, list under Ruby Bridges Elementary CC"},
    )
    variants = [
        "When does it expire?",
        "How long will it stay good?",
        "What's the best-by date for these loaves?",
    ]
    for text in variants:
        step = resolve_hands_on_share_chip_step(
            "Yes, list under Ruby Bridges Elementary CC",
            history,
            assistance_reminder="hands-on share posting",
            response_text=text,
        )
        assert step == "expiry"
        chips = build_labeled_hands_on_share_chips(step, "en")
        assert "Tomorrow" in _labels(chips)


def test_expiry_ask_wins_when_community_not_yet_confirmed():
    """Nouri may acknowledge a school and ask expiry before the donor taps confirm."""
    history = _hands_on_history(
        {"role": "assistant", "message": "What food and how much?"},
        {"role": "user", "message": "bread"},
    )
    text = (
        "Perfect, I'll list your bread under Do Good Warehouse. "
        "When is the bread best by, or how long is it good for?"
    )
    step = resolve_hands_on_share_chip_step(
        "bread",
        history,
        assistance_reminder="hands-on share posting",
        response_text=text,
    )
    assert step == "expiry"
    chips = build_turn_suggestions(
        text,
        "en",
        tool_results=[],
        min_chips=0,
        last_user_message="bread",
        assistance_reminder="hands-on share posting",
        history=history,
        user_context={
            "suggested_community": "Alameda Unified School District",
            "active_communities": [
                "Alameda Unified School District",
                "Do Good Warehouse",
            ],
        },
    )
    joined = _joined(chips)
    assert "tomorrow" in joined
    assert "different community" not in joined
    assert "alameda" not in joined


def test_description_ask_wins_over_allergen_ack():
    """'Perfect, no allergens. Describe…?' must show description chips, not allergen."""
    history = _hands_on_history(
        {"role": "assistant", "message": "What food and how much?"},
        {"role": "user", "message": "5 apples"},
        {"role": "assistant", "message": "List under Do Good Warehouse?"},
        {"role": "user", "message": "Yes, list under Do Good Warehouse"},
        {"role": "assistant", "message": "When does it expire?"},
        {"role": "user", "message": "Tomorrow"},
        {"role": "assistant", "message": "Any allergens?"},
        {"role": "user", "message": "No allergens"},
    )
    text = (
        "Perfect, no allergens. Could you give me one short sentence to describe "
        "the apples? (For example: how fresh they are, if they're bagged or loose, "
        "anything special about them.)"
    )
    step = resolve_hands_on_share_chip_step(
        "No allergens",
        history,
        assistance_reminder="hands-on share posting",
        response_text=text,
    )
    assert step == "description"
    chips = build_turn_suggestions(
        text,
        "en",
        tool_results=[],
        min_chips=0,
        last_user_message="No allergens",
        assistance_reminder="hands-on share posting",
        history=history,
    )
    joined = _joined(chips)
    assert "sealed" in joined or "homemade" in joined
    assert "no allergens" not in joined
    assert "gluten" not in joined


def test_different_community_ask_shows_school_list_not_food():
    """After 'Different community', ask for school name → community chips, not food."""
    history = _hands_on_history(
        {"role": "assistant", "message": "What food and how much?"},
        {"role": "user", "message": "5 apples"},
        {"role": "assistant", "message": "List under Alameda Unified?"},
        {"role": "user", "message": "Different community"},
    )
    text = (
        "Got it, you want a different community. Could you please tell me the name "
        "of the school or community you want to share your food under?"
    )
    step = resolve_hands_on_share_chip_step(
        "Different community",
        history,
        assistance_reminder="hands-on share posting",
        response_text=text,
    )
    assert step == "community_pick"
    chips = build_turn_suggestions(
        text,
        "en",
        tool_results=[],
        min_chips=0,
        last_user_message="Different community",
        assistance_reminder="hands-on share posting",
        history=history,
        user_context={
            "suggested_community": "Alameda Unified School District",
            "active_communities": [
                "Do Good Warehouse",
                "Ruby Bridges Elementary CC",
                "Alameda Unified School District",
            ],
        },
    )
    joined = _joined(chips)
    assert "do good warehouse" in joined or "ruby bridges" in joined
    assert "5 apples" not in joined
    assert "loaves" not in joined


def test_description_ask_wins_over_expiry_ack():
    """'Got it, good for a month. Write one short sentence…?' → description chips."""
    history = _hands_on_history(
        {"role": "assistant", "message": "What food and how much?"},
        {"role": "user", "message": "1 dozen eggs"},
        {"role": "assistant", "message": "List under Do Good Warehouse?"},
        {"role": "user", "message": "Yes, list under Do Good Warehouse"},
        {"role": "assistant", "message": "When does it expire?"},
        {"role": "user", "message": "In a month"},
    )
    text = (
        "Got it, eggs are good for about a month. Could you write one short sentence "
        "about these eggs? For example, let me know if they're fresh, in a carton, "
        "or anything else you'd like to share."
    )
    step = resolve_hands_on_share_chip_step(
        "In a month",
        history,
        assistance_reminder="hands-on share posting",
        response_text=text,
    )
    assert step == "description"
    chips = build_turn_suggestions(
        text,
        "en",
        tool_results=[],
        min_chips=0,
        last_user_message="In a month",
        assistance_reminder="hands-on share posting",
        history=history,
    )
    joined = _joined(chips)
    assert "sealed" in joined or "homemade" in joined
    assert "tomorrow" not in joined
    assert "in a month" not in joined


def test_description_ask_wins_over_best_by_ack():
    """'Got it — best-by Aug 30. Tell me a little about…?' → description, not dates."""
    history = _hands_on_history(
        {"role": "assistant", "message": "What food and how much?"},
        {"role": "user", "message": "5 apples"},
        {"role": "assistant", "message": "List under Do Good Warehouse?"},
        {"role": "user", "message": "Yes, list under Do Good Warehouse"},
        {"role": "assistant", "message": "When does it expire?"},
        {"role": "user", "message": "August 30"},
    )
    text = (
        "Thanks! Got it — best-by August 30. Can you tell me a little about the apples? "
        "For example, their condition or if they're in a bag."
    )
    step = resolve_hands_on_share_chip_step(
        "August 30",
        history,
        assistance_reminder="hands-on share posting",
        response_text=text,
    )
    assert step == "description"
    chips = build_turn_suggestions(
        text,
        "en",
        tool_results=[],
        min_chips=0,
        last_user_message="August 30",
        assistance_reminder="hands-on share posting",
        history=history,
    )
    joined = _joined(chips)
    assert "sealed" in joined or "homemade" in joined
    assert "tomorrow" not in joined
