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
    assert "GUIDED" in rem
    assert "REQUEST" in rem or "request" in rem.lower()
    assert "baby" in rem.lower() or "Open Request" in rem or "Abrir Solicitar" in rem
    assert "Do NOT call navigate_ui" in rem or "NO llames navigate_ui" in rem
    assert "STEP 1" in rem or "PASO 1" in rem


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


def test_hands_on_share_enters_posting_flow():
    """Do it for me after a share ask must stay in the chat posting pipeline."""
    from backend.ai.conversation_flow import (
        is_finding_flow,
        is_posting_flow,
        is_request_flow,
        build_posting_step_reminder,
        clear_assistance_session,
    )

    clear_assistance_session("test-hands-on")
    history = [
        {"role": "user", "message": "I want to share food"},
        {
            "role": "assistant",
            "message": (
                "Want me to open the form, do it for me, or guide me "
                "step by step?"
            ),
        },
    ]
    assert is_posting_flow("Do it for me", history) is True
    assert is_finding_flow("Do it for me", history) is False
    assert is_request_flow("Do it for me", history) is False
    rem = build_assistance_mode_reminder(
        "Do it for me", history, user_id="test-hands-on",
    )
    assert rem and rem.startswith("HANDS-ON")
    posting = build_posting_step_reminder("Do it for me", history)
    assert posting is not None
    assert "community" in posting.lower() or "school" in posting.lower()


def test_hands_on_find_enters_finding_flow():
    from backend.ai.conversation_flow import is_finding_flow, is_posting_flow

    history = [
        {"role": "user", "message": "I want to find food"},
        {
            "role": "assistant",
            "message": "Want me to handle everything, or guide me step by step?",
        },
    ]
    assert is_finding_flow("Do it for me", history) is True
    assert is_posting_flow("Do it for me", history) is False


def test_quick_replies_hands_on_ack_not_fork():
    """Hands-on acknowledgments must not re-show Open / Do it / Guide chips."""
    from backend.agent.suggestion_chips import share_assistance_fork_chips, build_turn_suggestions

    reminder = (
        "HANDS-ON MODE — SHARE FOOD:\nUser wants you to handle it in chat."
    )
    assert share_assistance_fork_chips(
        "Got it — I'll handle everything for you in chat. "
        "What food are you sharing and how much?",
        user_message="Do it for me",
        assistance_reminder=reminder,
    ) == []

    leak = "How would you like to proceed — handle everything here in chat or guide me?"
    chips = build_turn_suggestions(
        leak,
        "en",
        tool_results=[],
        last_user_message="100 boxes of vegetables",
        assistance_reminder=reminder,
        min_chips=0,
    )
    labels = [c if isinstance(c, str) else c.get("label") for c in chips]
    assert "Do it for me" not in labels
    assert "Guide me step by step" not in labels
    assert "Open the form" not in labels


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
    assert "GUIDED" in rem
    assert "SHARE" in rem or "share" in rem.lower()
    assert "Do NOT call navigate_ui" in rem
    assert "Open Share Food" in rem or "baby" in rem.lower() or "IDIOT" in rem
    assert "STEP 1" in rem
    assert "Look at the top" in rem or "top menu" in rem or "Share Food" in rem


def test_open_page_share_navigates_only():
    history = [
        {"role": "user", "message": "I want to share food"},
        {
            "role": "assistant",
            "message": "Want me to handle everything, or guide you step by step?",
        },
    ]
    rem = build_assistance_mode_reminder("Open the form", history)
    assert rem is not None
    assert "OPEN PAGE ONLY" in rem
    assert "navigate_ui" in rem
    assert "target=create" in rem
    assert "Do NOT ask what they want to share" in rem
    assert "GUIDED" not in rem or "Do NOT start GUIDED" in rem
    assert detect_assistance_mode("Open the form") == "open_page"


def test_open_page_find_navigates_only():
    history = [
        {"role": "user", "message": "I want to find food"},
        {
            "role": "assistant",
            "message": "Want me to handle everything, or guide you step by step?",
        },
    ]
    rem = build_assistance_mode_reminder("Open Find Food", history)
    assert rem is not None
    assert "OPEN PAGE ONLY" in rem
    assert "target=list" in rem
    assert "Do NOT ask what they want to share / find / request" in rem
    assert detect_assistance_mode("Open Find Food") == "open_page"


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
    # Ambiguous fork (no find/share cue) defaults to Share → Open the form.
    out = generate_quick_replies(
        "Want me to handle everything for you in chat, or walk you through "
        "doing it yourself step by step on the pages?",
    )
    assert out == [
        "Open the form",
        "Do it for me",
        "Guide me step by step",
    ]


def test_quick_replies_share_fork_mentions_share_in_reply():
    out = generate_quick_replies(
        "I can help you share food — want me to handle everything for you "
        "in chat, or walk you through it step by step on the pages?"
    )
    assert out == [
        "Open the form",
        "Do it for me",
        "Guide me step by step",
    ]


def test_quick_replies_find_fork_uses_open_find_food():
    out = generate_quick_replies(
        "I can search nearby. Want me to handle the search for you, "
        "or guide you on Find Food step by step?",
        user_message="I want to find food",
    )
    assert out == [
        "Open Find Food",
        "Do it for me",
        "Guide me step by step",
    ]
    assert "Open the form" not in out


def test_quick_replies_find_fork_omits_open_on_find_page():
    out = generate_quick_replies(
        "Want me to handle the search for you, or guide you step by step?",
        user_message="find food near me",
        guide_state={"pageKey": "find", "path": "/find"},
    )
    assert out == [
        "Open Find Food",
        "Do it for me",
        "Guide me step by step",
    ]
    assert "Open the form" not in out


def test_quick_replies_headerless_guided_not_fork():
    out = generate_quick_replies(
        "You got it! First, please open the Share Food page by tapping "
        "Share Food on the main menu. Let me know when you see the form "
        "and we'll go to the next step together.",
        user_message="Guide me step by step",
    )
    assert "Open the form" not in out
    assert "Do it for me" not in out
    assert "Guide me step by step" not in out
    assert "Done" in out


def test_guided_share_advances_on_done():
    history = [
        {"role": "user", "message": "I want to share food"},
        {
            "role": "assistant",
            "message": "Want me to handle everything for you in chat, or guide me step by step?",
        },
        {"role": "user", "message": "Guide me step by step"},
        {
            "role": "assistant",
            "message": "GUIDED — STEP 1 of 16 (SHARE FOOD — Open Share Food): ...",
        },
    ]
    rem = build_assistance_mode_reminder("done", history)
    assert rem is not None
    assert "STEP 2" in rem
    assert "Your name" in rem or "Name" in rem or "donor" in rem.lower()

    # Donor already named food + qty — go straight into posting.
    assert needs_assistance_mode_choice("I want to share 5 apples") is False
    # Still a share trigger without qty should ask.
    assert needs_assistance_mode_choice("Share food") is True


def test_live_guide_state_skips_reopen():
    from backend.ai.conversation_flow import build_live_guide_prompt

    history = [
        {"role": "user", "message": "I want to share food"},
        {
            "role": "assistant",
            "message": "Want me to handle everything, or walk you through it?",
        },
        {"role": "user", "message": "Guide me step by step"},
        {
            "role": "assistant",
            "message": "GUIDED — STEP 1 of 16 (SHARE FOOD) — Open Share Food:\nOpen the page.",
        },
    ]
    guide_state = {
        "formId": "share-food",
        "fieldName": "donor_name",
        "stepIndex": 1,
        "stepTotal": 16,
        "path": "/share",
        "label": "Name / Organization",
        "source": "form",
    }
    rem = build_assistance_mode_reminder("what goes here?", history, guide_state=guide_state)
    assert rem is not None
    assert "Do NOT call navigate_ui" in rem
    assert "baby" in rem.lower() or "IDIOT" in rem or "Name" in rem
    live = build_live_guide_prompt(guide_state)
    assert live is not None
    assert "share-food" in live or "/share" in live
    assert "donor_name" in live


def test_live_guide_state_advances_from_form_field():
    history = [
        {"role": "user", "message": "Guide me step by step"},
        {
            "role": "assistant",
            "message": "GUIDED — STEP 1 of 16 (SHARE FOOD) — Open Share Food:\nOpen.",
        },
    ]
    rem = build_assistance_mode_reminder(
        "done",
        history,
        guide_state={
            "formId": "share-food",
            "fieldName": "donor_name",
            "stepIndex": 1,
            "path": "/share",
        },
    )
    # Focused on name → advance goes to donor type (STEP 3).
    assert "STEP 3" in rem
    assert "Donor type" in rem or "donor_type" in rem.lower() or "Tipo" in rem


def test_durable_assistance_session_survives_without_history_mode():
    from backend.ai.conversation_flow import (
        clear_assistance_session,
        set_assistance_session,
        resolve_assistance_mode,
    )

    uid = "durable-assist-test-user"
    clear_assistance_session(uid)
    set_assistance_session(uid, mode="guided", goal="find")
    assert resolve_assistance_mode("ok next", [], user_id=uid) == "guided"
    clear_assistance_session(uid)
    assert resolve_assistance_mode("ok next", [], user_id=uid) is None


def test_live_form_does_not_force_guided_mode():
    # FormVoiceGuide focus must not flip assistance mode to guided.
    assert resolve_assistance_mode(
        "what goes here?",
        [],
        guide_state={"formId": "share-food", "fieldName": "donor_name"},
    ) is None


def test_guided_blocks_navigate_ui():
    history = [
        {"role": "user", "message": "I want to share food"},
        {
            "role": "assistant",
            "message": "Want me to handle everything, or guide you step by step?",
        },
    ]
    reason = assistance_mode_tool_block_reason(
        "navigate_ui", "Guide me step by step", history,
    )
    assert reason is not None
    assert "do not open" in reason.lower() or "TELL" in reason or "tutorial" in reason.lower()


def test_guided_find_does_not_force_search_tool():
    history = [
        {"role": "user", "message": "I want to find food"},
        {
            "role": "assistant",
            "message": "Want me to handle everything, or walk you through it?",
        },
    ]
    rem = build_assistance_mode_reminder("Guide me step by step", history)
    assert rem is not None
    assert "GUIDED" in rem
    # Step 1 tells them to open Find Food — must not demand search yet.
    assert "search_food_near_user THIS turn" not in rem
    assert "Open Find Food" in rem or "Find Food" in rem


def test_checklist_defers_when_guided():
    from backend.ai.conversation_flow import _finding_checklist, _defer_to_guided_block

    history = [
        {"role": "user", "message": "Guide me step by step"},
        {"role": "assistant", "message": "GUIDED — STEP 1 of 3 (FIND FOOD): open."},
    ]
    out = _finding_checklist("done", history, "en")
    assert out == _defer_to_guided_block("en")
    assert "search_food_near_user THIS turn" not in out
