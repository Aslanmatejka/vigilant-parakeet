"""Regression tests for Nouri claim qty restore and conversation phrasing."""
from __future__ import annotations

from backend.ai.conversation_flow import (
    _community_was_confirmed,
    _is_affirmative_post_confirm,
    _user_declined_photo,
    _user_trying_to_skip_photo,
    build_posting_step_reminder,
    posting_tool_block_reason,
)
from backend.tools import _normalize_claim_quantity


class TestPostNowIsConfirmNotDecline:
    def test_post_now_is_affirmative(self):
        assert _is_affirmative_post_confirm("post now")
        assert _is_affirmative_post_confirm("yes, post it")

    def test_post_now_alone_is_not_photo_decline(self):
        history = [
            {"role": "assistant", "message": "Shall I post this listing?"},
            {"role": "user", "message": "post now"},
        ]
        assert not _user_declined_photo(history, "post now")

    def test_skip_photo_no_longer_declines(self):
        history = [
            {"role": "assistant", "message": "Please attach a photo — required."},
            {"role": "user", "message": "skip photo"},
        ]
        assert not _user_declined_photo(history, "skip photo")
        assert not _user_declined_photo(history, "no photo")


class TestPhotoAlwaysRequired:
    def _share_history(self):
        return [
            {"role": "user", "message": "I want to share bread"},
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
                "message": "Please attach a photo of the food — required before I can post.",
            },
        ]

    def test_skip_photo_is_detected(self):
        assert _user_trying_to_skip_photo("skip photo", self._share_history())
        assert _user_trying_to_skip_photo(
            "can I post without a photo?", self._share_history(),
        )
        assert _user_trying_to_skip_photo("no photo", self._share_history())
        assert _user_trying_to_skip_photo(
            "I already uploaded it", self._share_history(),
        )

    def test_ready_to_post_requires_photo_url(self):
        from backend.ai.conversation_flow import _posting_ready_to_execute

        history = self._share_history() + [
            {
                "role": "assistant",
                "message": "Ready to post: 2 loaves under Do Good Warehouse. Shall I post?",
            },
        ]
        assert _posting_ready_to_execute("yes, post it", history) is False

    def test_skip_photo_reminder_refuses(self):
        rem = build_posting_step_reminder(
            "skip photo", self._share_history(), lang="en",
        )
        assert rem is not None
        assert "REQUIRED" in rem or "required" in rem.lower()
        assert "skip" in rem.lower() or "without" in rem.lower()
        assert "NEVER" in rem or "Do NOT" in rem

    def test_post_tool_blocked_without_photo_on_skip(self):
        reason = posting_tool_block_reason(
            "post without a photo",
            self._share_history(),
            fn_args={"community_confirmed": True, "expiration_date": "2099-01-01"},
        )
        assert reason is not None
        assert "photo" in reason.lower()
        assert "REQUIRED" in reason or "required" in reason.lower()


class TestCommunityConfirmNotLoose:
    def test_qty_after_community_ask_is_not_confirm(self):
        history = [
            {"role": "assistant", "message": "Which community should this go under?"},
            {"role": "user", "message": "5 loaves"},
        ]
        assert not _community_was_confirmed(history)

    def test_school_name_confirms(self):
        history = [
            {"role": "assistant", "message": "Which school/community?"},
            {"role": "user", "message": "Ruby Bridges"},
        ]
        assert _community_was_confirmed(history)

    def test_yes_confirms(self):
        history = [
            {"role": "assistant", "message": "List under Alameda High?"},
            {"role": "user", "message": "yes"},
        ]
        assert _community_was_confirmed(history)

    def test_different_one_is_not_confirm(self):
        history = [
            {
                "role": "assistant",
                "message": "Should this go under Alameda Unified School District?",
            },
            {"role": "user", "message": "Different one"},
        ]
        assert not _community_was_confirmed(history)

    def test_named_community_after_wrong_food_reask_still_confirms(self):
        history = [
            {
                "role": "assistant",
                "message": "Should this go under Alameda Unified School District?",
            },
            {"role": "user", "message": "Different one"},
            {
                "role": "assistant",
                "message": "Got it, let's switch! What food would you like to share instead?",
            },
            {"role": "user", "message": "NEA/ACLC CC"},
        ]
        assert _community_was_confirmed(history)

    def test_different_one_nudge_keeps_food(self):
        from backend.ai.conversation_flow import build_posting_step_reminder

        history = [
            {"role": "user", "message": "I want to share food"},
            {"role": "user", "message": "10 loaves of bread"},
            {"role": "user", "message": "Made today"},
            {
                "role": "assistant",
                "message": "Should this go under Alameda Unified School District for your community?",
            },
        ]
        rem = build_posting_step_reminder("Different one", history)
        assert rem is not None
        assert "DIFFERENT COMMUNITY" in rem
        assert "Do NOT change" in rem or "food" in rem.lower()
        assert "community" in rem.lower() or "school" in rem.lower()


class TestTitleFilterEmptyMatch:
    def test_no_match_returns_empty_not_unfiltered(self):
        from backend.tools import _apply_title_query_filter

        rows = [
            {"id": "b", "title": "Bread"},
            {"id": "m", "title": "Milk"},
        ]
        kept, matched, missing = _apply_title_query_filter(rows, "pawpaw, carrots")
        assert kept == []
        assert matched == []
        assert missing == ["pawpaw", "carrots"]


class TestClaimQtyNormalizeStillAllOnNone:
    def test_none_still_means_all_available(self):
        assert _normalize_claim_quantity(None, 10) == (10, False)
