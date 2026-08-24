"""Regression: tomatoes/carrots share transcript bugs.

1. Spoken dates ("24th july", "july 24th this year") → next/current year ISO,
   never invent a past year like 2024.
2. After "Shall I post? / yes", post immediately — don't re-ask photos.
3. Success copy ("All set! … are shared?") must not show Yes/post/Cancel chips.
"""
from __future__ import annotations

from datetime import date, timedelta

from backend.ai.ai_engine import generate_quick_replies
from backend.ai.conversation_flow import (
    _extract_expiry_from_text,
    build_posting_step_reminder,
    enrich_post_food_listing_args,
    posting_flow_state,
    posting_tool_block_reason,
)


class TestSpokenExpiryParsing:
    def test_day_month_without_year_picks_upcoming(self):
        today = date.today()
        result = _extract_expiry_from_text("24th july")
        assert result is not None
        y, m, d = map(int, result.split("-"))
        assert (m, d) == (7, 24)
        assert date(y, m, d) >= today
        assert not result.startswith("2024-")

    def test_july_24th_this_year(self):
        today = date.today()
        result = _extract_expiry_from_text("july 24th this year")
        assert result == f"{today.year}-07-24"

    def test_month_first_with_explicit_year(self):
        assert _extract_expiry_from_text("July 24, 2026") == "2026-07-24"

    def test_never_returns_invented_past_iso_from_user_phrase(self):
        result = _extract_expiry_from_text("24th july")
        assert result is not None
        assert not result.startswith("2024-")
        assert date.fromisoformat(result) >= date.today()

    def test_in_three_days(self):
        from datetime import timedelta
        result = _extract_expiry_from_text("good for in 3 days")
        assert result == (date.today() + timedelta(days=3)).isoformat()

    def test_next_friday(self):
        result = _extract_expiry_from_text("best by next friday")
        assert result is not None
        assert date.fromisoformat(result).weekday() == 4


class TestSpokenExpiryShelfLife:
    def test_made_today_maps_to_tomorrow(self):
        from datetime import timedelta
        assert _extract_expiry_from_text("Made today") == (
            date.today() + timedelta(days=1)
        ).isoformat()

    def test_made_yesterday_maps_to_today(self):
        assert _extract_expiry_from_text("Made yesterday") == date.today().isoformat()

    def test_good_for_24_hours(self):
        from datetime import timedelta
        assert _extract_expiry_from_text("Good for 24 hours") == (
            date.today() + timedelta(days=1)
        ).isoformat()

    def test_in_2_days(self):
        from datetime import timedelta
        assert _extract_expiry_from_text("In 2 days") == (
            date.today() + timedelta(days=2)
        ).isoformat()

    def test_in_2_months(self):
        from backend.ai.conversation_flow import _add_calendar_months
        assert _extract_expiry_from_text("2 months from now") == (
            _add_calendar_months(date.today(), 2).isoformat()
        )

    def test_in_two_months_phrase(self):
        from backend.ai.conversation_flow import _add_calendar_months
        assert _extract_expiry_from_text("expires in 2 months") == (
            _add_calendar_months(date.today(), 2).isoformat()
        )

    def test_in_a_month_and_weeks(self):
        from datetime import timedelta
        from backend.ai.conversation_flow import _add_calendar_months

        assert _extract_expiry_from_text("in a month") == (
            _add_calendar_months(date.today(), 1).isoformat()
        )
        assert _extract_expiry_from_text("next month") == (
            _add_calendar_months(date.today(), 1).isoformat()
        )
        assert _extract_expiry_from_text("in 6 weeks") == (
            (date.today() + timedelta(weeks=6)).isoformat()
        )

    def test_normalize_bumps_date_only_today_to_tomorrow(self):
        from datetime import timedelta
        from backend.ai.conversation_flow import normalize_expiration_date_for_post

        today = date.today().isoformat()
        assert normalize_expiration_date_for_post(today) == (
            date.today() + timedelta(days=1)
        ).isoformat()

    def test_enrich_made_today_overrides_model_today(self):
        from datetime import timedelta
        history = [
            {"role": "user", "message": "I want to share pizza"},
            {"role": "assistant", "message": "When is it best by?"},
            {"role": "user", "message": "Made today"},
            {"role": "assistant", "message": "Ready to post?"},
        ]
        out = enrich_post_food_listing_args(
            {
                "title": "pizza",
                "qty": 10,
                "expiration_date": date.today().isoformat(),
                "community_confirmed": True,
            },
            "Yes, post it",
            history,
        )
        assert out["expiration_date"] == (
            date.today() + timedelta(days=1)
        ).isoformat()

    def test_upsert_applies_expiry_from_prior_user_message(self):
        from backend.ai.conversation_flow import upsert_share_drafts_from_message

        history = [
            {"role": "user", "message": "I want to share 2 loaves of bread"},
            {"role": "assistant", "message": "When does it expire?"},
            {"role": "user", "message": "tomorrow"},
        ]
        drafts = upsert_share_drafts_from_message(
            "u-exp",
            "yes Do Good Warehouse",
            history,
        )
        assert drafts
        from datetime import timedelta
        assert drafts[0]["expiry"] == (date.today() + timedelta(days=1)).isoformat()


class TestExpiryAskedButAlreadyProvided:
    def test_reminder_tells_model_not_to_reask(self):
        history = [
            {"role": "user", "message": "share bread under Do Good Warehouse"},
            {"role": "assistant", "message": "Should this go under Do Good Warehouse?"},
            {"role": "user", "message": "yes"},
            {"role": "assistant", "message": "What's the best by date?"},
            {"role": "user", "message": "tomorrow"},
        ]
        reminder = build_posting_step_reminder("tomorrow works", history, lang="en")
        assert reminder is not None
        assert "Do NOT ask again" in reminder or "already gave" in reminder.lower()


class TestEnrichPrefersUserExpiryOverModelPastYear:
    def test_overrides_model_past_year(self):
        history = [
            {"role": "user", "message": "i want to share tomatoes and carrots"},
            {"role": "assistant", "message": "When do they expire?"},
            {"role": "user", "message": "24th july"},
            {
                "role": "assistant",
                "message": "Looks like July 24th, 2024 is in the past",
            },
            {"role": "user", "message": "july 24th next year"},
        ]
        out = enrich_post_food_listing_args(
            {
                "title": "tomatoes",
                "qty": 1,
                "expiration_date": "2024-07-24",
            },
            "yes",
            history,
        )
        today = date.today()
        assert out["expiration_date"] == f"{today.year + 1}-07-24"
        assert out["expiry_date"] == f"{today.year + 1}-07-24"


class TestPostConfirmDoesNotReaskPhotos:
    def _history_ready(self):
        return [
            {"role": "user", "message": "i want to share tomatoes and carrots"},
            {
                "role": "assistant",
                "message": "Should these go under Alameda Unified, or Do Good Warehouse?",
            },
            {"role": "user", "message": "Do Good Warehouse"},
            {
                "role": "assistant",
                "message": "When do the tomatoes and carrots expire?",
            },
            {"role": "user", "message": "in 3 days"},
            {
                "role": "assistant",
                "message": "Please add a short description for recipients.",
            },
            {"role": "user", "message": "Fresh garden mix, still cool."},
            {
                "role": "assistant",
                "message": "Want to snap a quick photo of the tomatoes or carrots?",
            },
            {"role": "user", "message": "image: https://cdn.example.com/veggies.jpg"},
            {
                "role": "assistant",
                "message": "Perfect, photos received! How many of each?",
            },
            {"role": "user", "message": "1 basket of tomatoes and 1 basket of carrots"},
            {
                "role": "assistant",
                "message": (
                    "Ready to post: 1 basket of tomatoes and 1 basket of carrots, "
                    "no allergens, pickup at 1423 Park St, under Do Good Warehouse, "
                    "with your photos. Shall I post these now?"
                ),
            },
        ]

    def test_yes_unblocks_post_tool(self):
        history = self._history_ready()
        reason = posting_tool_block_reason(
            "yes",
            history,
            {
                "title": "tomatoes",
                "qty": 1,
                "community_name": "Do Good Warehouse",
                "community_confirmed": True,
                "expiration_date": f"{date.today().year + 1}-07-24",
            },
        )
        assert reason is None

    def test_reminder_says_post_now_not_photo(self):
        history = self._history_ready()
        reminder = build_posting_step_reminder("yes", history, lang="en")
        assert reminder is not None
        low = reminder.lower()
        assert "call post_food_listing" in low or "post_food_listings" in low
        assert "waiting on either a photo" not in low

    def test_verbal_already_shared_without_url_is_not_enough(self):
        history = self._history_ready() + [
            {
                "role": "assistant",
                "message": "Want to snap a quick photo?",
            },
        ]
        # Strip photo URLs from earlier turns by starting a new share-like
        # history that asks for a photo without an upload.
        history = [
            {"role": "user", "message": "i want to share bread"},
            {
                "role": "assistant",
                "message": "Should this go under Do Good Warehouse?",
            },
            {"role": "user", "message": "yes"},
            {
                "role": "assistant",
                "message": "When does it expire?",
            },
            {"role": "user", "message": "tomorrow"},
            {
                "role": "assistant",
                "message": "Please upload a photo of the bread.",
            },
        ]
        state = posting_flow_state("i already shared the photos with you", history)
        assert state["has_photo"] is False
        assert state["awaiting_photo"] is True

    def test_skip_photo_still_blocks_post(self):
        history = [
            {"role": "user", "message": "share 5 apples"},
            {
                "role": "assistant",
                "message": "Should this go under Do Good Warehouse?",
            },
            {"role": "user", "message": "yes"},
            {
                "role": "assistant",
                "message": "When does it expire?",
            },
            {"role": "user", "message": "tomorrow"},
            {
                "role": "assistant",
                "message": "Please upload a photo.",
            },
            {"role": "user", "message": "skip photo"},
        ]
        reason = posting_tool_block_reason(
            "yes, post it",
            history,
            {
                "title": "apples",
                "qty": 5,
                "community_name": "Do Good Warehouse",
                "community_confirmed": True,
                "expiration_date": (date.today() + timedelta(days=3)).isoformat(),
            },
        )
        assert reason is not None
        assert "photo" in reason.lower()
        assert "skip" in reason.lower() or "required" in reason.lower()


class TestNoPostChipsAfterShareSuccess:
    def test_all_set_shared_gets_next_step_chips(self):
        text = (
            "All set! Your tomatoes and carrots baskets are shared and ready "
            "for pickup at 1423 Park St, expiring July 24. Anything else you "
            "want to share today?"
        )
        out = generate_quick_replies(text)
        assert "Yes, post it" not in out
        assert "Skip photo" not in out
        joined = " ".join(out).lower()
        assert "share" in joined or "find" in joined or "all" in joined

    def test_listed_under_success_no_community_chips(self):
        text = (
            "Done! Your 100 boxes of vegetables are listed under "
            "Alameda Unified School District and awaiting admin approval."
        )
        out = generate_quick_replies(text)
        assert "Different one" not in out
        assert "Alameda Unified" not in out
        assert "Yes, post it" not in out
        joined = " ".join(out).lower()
        assert "share" in joined or "find" in joined or "all" in joined

    def test_shall_i_post_still_gets_confirm_chips(self):
        text = (
            "Ready to post: 1 basket of tomatoes and 1 basket of carrots, "
            "with your photos. Shall I post these now?"
        )
        out = generate_quick_replies(text)
        assert "Yes, post it" in out

    def test_ready_to_post_without_photo_asks_for_photo(self):
        text = (
            "Ready to post: 100 boxes of vegetables under Alameda Unified. "
            "Shall I post these now?"
        )
        out = generate_quick_replies(text)
        assert "Attach a photo" in out
        assert "Yes, post it" not in out


class TestCustomExpiryHandsOnPath:
    def _history(self, extra=None):
        history = [
            {"role": "user", "message": "Do it for me"},
            {"role": "assistant", "message": "What food do you want to share, and how much?"},
            {"role": "user", "message": "100 boxes of vegetables"},
            {"role": "assistant", "message": "Should this go under Alameda Unified?"},
            {"role": "user", "message": "Alameda County"},
            {"role": "assistant", "message": "When does it expire?"},
            {"role": "user", "message": "2 months from now"},
        ]
        return history + (extra or [])

    def test_two_months_is_parsed_and_stateful(self):
        from backend.ai.conversation_flow import _add_calendar_months

        history = self._history()
        state = posting_flow_state("2 months from now", history[:-1])
        assert state["expiry_provided"] is True
        assert _extract_expiry_from_text("2 months from now") == (
            _add_calendar_months(date.today(), 2).isoformat()
        )

    def test_cannot_post_without_photo_url(self):
        history = self._history([
            {
                "role": "assistant",
                "message": "Please add a short description for recipients.",
            },
            {"role": "user", "message": "Assorted leftover vegetables, boxed."},
            {"role": "assistant", "message": "Please attach a photo — required before I can post."},
            {"role": "user", "message": "I already uploaded it"},
            {
                "role": "assistant",
                "message": "Ready to post 100 boxes of vegetables under Alameda Unified?",
            },
        ])
        reason = posting_tool_block_reason(
            "yes, post it",
            history,
            {
                "title": "vegetables",
                "qty": 100,
                "community_name": "Alameda Unified",
                "community_confirmed": True,
                "expiration_date": _extract_expiry_from_text("2 months from now"),
            },
        )
        assert reason is not None
        assert "photo" in reason.lower()

    def test_photo_ask_chip_is_attach_only(self):
        out = generate_quick_replies(
            "Please attach a photo of the vegetables — required before I can post."
        )
        assert "Attach a photo" in out
        assert "I already uploaded it" not in out
        assert "Skip photo" not in out
