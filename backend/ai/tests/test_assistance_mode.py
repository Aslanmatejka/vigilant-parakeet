"""Assistance mode fork: do-it-for-me vs guide-me on find/share."""
from backend.ai.conversation_flow import (
    assistance_mode_tool_block_reason,
    build_assistance_mode_reminder,
    detect_assistance_goal,
    detect_assistance_mode,
    needs_assistance_mode_choice,
    resolve_assistance_mode,
)
from backend.ai.ai_engine import generate_quick_replies


def test_detect_hands_on_and_guided_phrases():
    assert detect_assistance_mode("Do it for me") == "hands_on"
    assert detect_assistance_mode("Handle everything") == "hands_on"
    assert detect_assistance_mode("Guide me step by step") == "guided"
    assert detect_assistance_mode("Walk me through it") == "guided"
    assert detect_assistance_mode("Find food near me") is None


def test_fresh_find_and_share_need_mode_choice():
    assert needs_assistance_mode_choice("I want to find food") is True
    assert needs_assistance_mode_choice("Find free food near me") is True
    assert needs_assistance_mode_choice("I want to share food") is True
    assert needs_assistance_mode_choice("I want to request food") is True
    assert detect_assistance_goal("I want to find food") == "find"
    assert detect_assistance_goal("I want to share food") == "share"
    assert detect_assistance_goal("I want to request food") == "request"


def test_reminder_guided_request():
    history = [
        {"role": "user", "message": "I want to request food"},
        {
            "role": "assistant",
            "message": (
                "Want me to handle everything for you in chat, or walk you "
                "through doing it yourself step by step on the pages?"
            ),
        },
    ]
    rem = build_assistance_mode_reminder("Guide me step by step", history)
    assert rem is not None
    # Step-tracker returns the exact next step, starting with "GUIDED —"
    assert "GUIDED" in rem
    assert "REQUEST" in rem or "request" in rem.lower()
    # Guided mode walks through fields in chat — no page navigation until user asks
    assert "Do NOT" in rem or "do NOT" in rem or "ONE question" in rem


def test_reminder_hands_on_request():
    history = [
        {"role": "user", "message": "Request food"},
        {
            "role": "assistant",
            "message": (
                "Want me to handle everything for you in chat, or guide me "
                "step by step on the pages?"
            ),
        },
    ]
    rem = build_assistance_mode_reminder("Do it for me", history)
    assert rem is not None
    assert "HANDS-ON MODE — REQUEST FOOD" in rem
    assert "post_food_request" in rem


def test_distress_skips_mode_choice():
    assert needs_assistance_mode_choice("I'm hungry and have nothing to eat") is False
    assert build_assistance_mode_reminder("I'm starving") is None


def test_explicit_mode_skips_ask():
    assert needs_assistance_mode_choice("Do it for me — find food") is False
    assert resolve_assistance_mode("Guide me step by step") == "guided"


def test_reminder_asks_before_tools():
    rem = build_assistance_mode_reminder("I want to find food")
    assert rem is not None
    assert "ASSISTANCE MODE" in rem
    assert "Do NOT call search_food_near_user" in rem


def test_reminder_hands_on_find():
    history = [
        {"role": "user", "message": "I want to find food"},
        {
            "role": "assistant",
            "message": (
                "Want me to handle everything for you in chat, or walk you "
                "through doing it yourself step by step on the pages?"
            ),
        },
    ]
    rem = build_assistance_mode_reminder("Do it for me", history)
    assert rem is not None
    assert "HANDS-ON MODE" in rem
    assert "search_food_near_user" in rem


def test_reminder_guided_share():
    history = [
        {"role": "user", "message": "I want to share food"},
        {
            "role": "assistant",
            "message": (
                "Want me to handle everything for you in chat, or guide me "
                "step by step — walk you through the pages yourself?"
            ),
        },
    ]
    rem = build_assistance_mode_reminder("Guide me step by step", history)
    assert rem is not None
    # Step-tracker returns the exact next step, starting with "GUIDED —"
    assert "GUIDED" in rem
    # Must be a single-step instruction, not a full script
    assert "ONE question" in rem or "Step" in rem or "SUMMARY" in rem


def test_tool_block_while_waiting_for_choice():
    reason = assistance_mode_tool_block_reason(
        "search_food_near_user", "I want to find food", None,
    )
    assert reason is not None
    assert "Ask the user first" in reason

    assert assistance_mode_tool_block_reason(
        "navigate_ui", "I want to find food", None,
    ) is None


def test_no_tool_block_after_mode_chosen():
    history = [
        {"role": "user", "message": "Find food near me"},
        {
            "role": "assistant",
            "message": "Want me to do everything for you, or guide me step by step?",
        },
    ]
    assert assistance_mode_tool_block_reason(
        "search_food_near_user", "Do it for me", history,
    ) is None


def test_quick_replies_for_assistance_fork():
    out = generate_quick_replies(
        "Want me to handle everything for you in chat, or walk you through "
        "doing it yourself step by step on the pages?"
    )
    assert "Do it for me" in out
    assert "Guide me step by step" in out


def test_concrete_share_qty_skips_fork():
    # Donor already named food + qty — go straight into posting.
    assert needs_assistance_mode_choice("I want to share 5 apples") is False
    # Still a share trigger without qty should ask.
    assert needs_assistance_mode_choice("Share food") is True
