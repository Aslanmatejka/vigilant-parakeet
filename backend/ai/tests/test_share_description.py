"""Do-it-for-me must ask for a donor-written description and save it."""
from __future__ import annotations

from backend.ai.ai_engine import generate_quick_replies
from backend.ai.conversation_flow import (
    _best_user_description_from_thread,
    _is_description_ask,
    build_posting_step_reminder,
    enrich_post_food_listing_args,
    posting_flow_state,
    posting_tool_block_reason,
)


def _share_through_expiry():
    return [
        {"role": "user", "message": "I want to share leftover lasagna"},
        {"role": "assistant", "message": "Should this go under Do Good Warehouse?"},
        {"role": "user", "message": "yes"},
        {"role": "assistant", "message": "When does it expire?"},
        {"role": "user", "message": "tomorrow"},
    ]


class TestDescriptionAskDetection:
    def test_short_description_prompt_is_an_ask(self):
        assert _is_description_ask(
            "Please add a short description for recipients."
        )
        assert _is_description_ask(
            "Got it. One sentence about the food — condition or packaging?"
        )
        assert _is_description_ask(
            "Tell me a bit about the food so people know what they're getting."
        )

    def test_mentioning_description_field_is_not_an_ask(self):
        assert not _is_description_ask(
            "I'll put pickup only in the description. Please attach a photo."
        )


class TestMustAskAfterExpiry:
    def test_leftover_share_is_not_already_a_description(self):
        history = _share_through_expiry()[:-1]
        state = posting_flow_state("tomorrow", history)
        assert state["expiry_provided"] is True
        assert state["description_provided"] is False
        assert state["description_asked"] is False

    def test_reminder_after_expiry_asks_for_description(self):
        history = _share_through_expiry()[:-1]
        reminder = build_posting_step_reminder("tomorrow", history, lang="en")
        assert reminder is not None
        low = reminder.lower()
        assert "description" in low
        assert "do not invent" in low or "their words" in low
        assert "do not ask again" in low or "already gave" in low

    def test_waiting_after_description_question(self):
        history = _share_through_expiry() + [
            {
                "role": "assistant",
                "message": "Please add a short description for recipients.",
            },
        ]
        reminder = build_posting_step_reminder("ok", history, lang="en")
        assert reminder is not None
        assert "description" in reminder.lower()
        assert "wait" in reminder.lower() or "do not invent" in reminder.lower()

    def test_post_blocked_until_donor_describes(self):
        history = _share_through_expiry()
        reason = posting_tool_block_reason(
            "yes post it",
            history,
            {
                "title": "lasagna",
                "qty": 1,
                "community_name": "Do Good Warehouse",
                "community_confirmed": True,
                "expiration_date": "2030-07-10",
                "images": ["https://cdn.example.com/lasagna.jpg"],
            },
        )
        assert reason is not None
        assert "description" in reason.lower()


class TestDescriptionSavedOnPost:
    def test_chip_answer_is_stored(self):
        history = _share_through_expiry() + [
            {
                "role": "assistant",
                "message": "Please add a short description for recipients.",
            },
        ]
        assert (
            _best_user_description_from_thread("Fresh today", history)
            == "Fresh today"
        )
        state = posting_flow_state("Fresh today", history)
        assert state["description_asked"] is True
        assert state["description_provided"] is True
        out = enrich_post_food_listing_args(
            {"title": "lasagna", "qty": 1},
            "Fresh today",
            history,
        )
        assert out.get("description") == "Fresh today"

    def test_typed_sentence_is_stored(self):
        history = _share_through_expiry() + [
            {
                "role": "assistant",
                "message": "Please add a short description for recipients.",
            },
            {
                "role": "user",
                "message": "Homemade, still in the pan, refrigerated.",
            },
        ]
        out = enrich_post_food_listing_args(
            {"title": "lasagna", "description": "Pickup only."},
            "yes post it",
            history,
        )
        assert "Homemade" in (out.get("description") or "")
        assert "Pickup only" not in (out.get("description") or "")

    def test_fresh_today_chip_does_not_overwrite_expiry(self):
        history = _share_through_expiry() + [
            {
                "role": "assistant",
                "message": "Please add a short description for recipients.",
            },
        ]
        out = enrich_post_food_listing_args(
            {"title": "lasagna"},
            "Fresh today",
            history,
        )
        assert out.get("description") == "Fresh today"
        exp = out.get("expiration_date") or out.get("expiry_date")
        assert exp
        # Expiry came from "tomorrow", not from the description chip.
        from datetime import date, timedelta
        assert exp == (date.today() + timedelta(days=1)).isoformat()


class TestDescriptionChips:
    def test_description_ask_gets_description_chips(self):
        out = generate_quick_replies(
            "Please add a short description for recipients.",
            user_message="share leftover lasagna",
        )
        joined = " ".join(out).lower()
        assert "fresh" in joined
        assert out[:3] != ["Yes", "No", "Later"]
        assert "Attach a photo" not in out
        assert "Tomorrow" not in out
