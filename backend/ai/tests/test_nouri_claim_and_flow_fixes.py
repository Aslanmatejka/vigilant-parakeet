"""Regression tests for Nouri claim qty restore and conversation phrasing."""
from __future__ import annotations

from backend.ai.conversation_flow import (
    _community_was_confirmed,
    _is_affirmative_post_confirm,
    _user_declined_photo,
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

    def test_skip_photo_still_declines(self):
        history = [
            {"role": "assistant", "message": "Want to add a photo?"},
            {"role": "user", "message": "skip photo"},
        ]
        assert _user_declined_photo(history, "skip photo")


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
