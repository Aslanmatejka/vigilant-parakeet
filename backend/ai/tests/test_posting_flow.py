"""Tests for donor posting-flow detection and checklist reminders."""
from __future__ import annotations

from backend.ai.conversation_flow import (
    build_posting_step_reminder,
    enrich_post_food_listing_args,
    is_posting_flow,
    posting_distractor_tool_block_reason,
    posting_flow_reminder,
    posting_tool_block_reason,
)


class TestEnrichPostListingArgs:
    def test_confirms_community_from_history_on_yes(self):
        history = [
            {"role": "user", "message": "I want to share 10 lbs of rice"},
            {"role": "assistant", "message": "Which community should this go under — Alameda Unified School District?"},
            {"role": "user", "message": "yes"},
            {"role": "assistant", "message": "Snap a quick photo?"},
            {"role": "user", "message": "image: https://example.com/rice.jpg"},
            {"role": "assistant", "message": "Ready to post 10 lbs of rice at your address?"},
        ]
        out = enrich_post_food_listing_args(
            {"title": "Rice", "qty": 10, "unit": "lbs"},
            "yes post it",
            history,
        )
        assert out.get("community_confirmed") is True
        assert "alameda" in (out.get("community_name") or "").lower()

    def test_injects_photo_from_history(self):
        history = [
            {"role": "user", "message": "image: https://example.com/rice.jpg"},
            {"role": "assistant", "message": "Ready to post 10 lbs of rice?"},
        ]
        out = enrich_post_food_listing_args(
            {"title": "Rice", "qty": 10},
            "yes post it",
            history,
        )
        assert out.get("images") == ["https://example.com/rice.jpg"]


class TestPostingDistractorBlock:
    def test_blocks_repeat_community_fetch(self):
        history = [
            {"role": "user", "message": "share rice"},
            {"role": "assistant", "message": "Which community — Alameda Unified?"},
        ]
        reason = posting_distractor_tool_block_reason(
            "get_active_communities",
            "yes",
            history,
        )
        assert reason is not None
        assert "post_food_listing" in reason

    def test_allows_different_community_request(self):
        history = [
            {"role": "assistant", "message": "List under Alameda Unified?"},
        ]
        assert posting_distractor_tool_block_reason(
            "get_active_communities",
            "different community please",
            history,
        ) is None


class TestIsPostingFlow:
    def test_share_food_triggers(self):
        assert is_posting_flow("I want to share some bread") is True

    def test_hunger_does_not_trigger(self):
        assert is_posting_flow("I'm hungry, need food near me") is False

    def test_ongoing_flow_from_history(self):
        history = [
            {"role": "user", "message": "I have extra apples"},
            {"role": "assistant", "message": "How many?"},
        ]
        assert is_posting_flow("5 bags", history) is True


class TestPostingFlowReminder:
    def test_asks_photo_when_missing(self):
        history = [
            {"role": "user", "message": "I want to share 3 loaves of bread"},
            {"role": "assistant", "message": "Which community should this go under?"},
            {"role": "user", "message": "Alameda High"},
            {"role": "assistant", "message": "When does it expire?"},
            {"role": "user", "message": "expiry 2030-01-01"},
        ]
        reminder = posting_flow_reminder("yes that one", history, lang="en")
        assert reminder is not None
        assert "photo" in reminder.lower()

    def test_blocks_post_when_yes_after_photo_ask_without_upload(self):
        history = [
            {"role": "user", "message": "I want to share 5 apples"},
            {"role": "assistant", "message": "List under Alameda Unified?"},
            {"role": "user", "message": "yes"},
            {"role": "assistant", "message": "When does it expire or what's the best-by?"},
            {"role": "user", "message": "2030-07-10"},
            {"role": "assistant", "message": "Want to snap a quick photo? It helps people choose."},
        ]
        reason = posting_tool_block_reason(
            "yes",
            history,
            {
                "title": "Apples",
                "qty": 5,
                "community_name": "Alameda Unified",
                "community_confirmed": True,
                "expiration_date": "2030-07-10",
            },
        )
        assert reason is not None
        assert "photo" in reason.lower()

    def test_photo_yes_reminder_clarifies_upload_needed(self):
        history = [
            {"role": "user", "message": "share 5 apples"},
            {"role": "assistant", "message": "List under Alameda Unified?"},
            {"role": "user", "message": "yes"},
            {"role": "assistant", "message": "Best by 2030-07-10?"},
            {"role": "user", "message": "yes"},
            {"role": "assistant", "message": "Want to snap a quick photo?"},
        ]
        reminder = build_posting_step_reminder("yes", history, lang="en")
        assert reminder is not None
        assert "upload" in reminder.lower() or "attach" in reminder.lower() or "photo" in reminder.lower()

    def test_blocks_post_without_community_confirm(self):
        history = [
            {"role": "user", "message": "I want to share 5 apples"},
            {"role": "assistant", "message": "Which community should this go under — Alameda Unified?"},
        ]
        reason = posting_tool_block_reason(
            "5 apples",
            history,
            {"title": "Apples", "qty": 5, "expiration_date": "2030-07-10"},
        )
        assert reason is not None
        assert "community" in reason.lower()

    def test_blocks_post_without_expiry(self):
        history = [
            {"role": "user", "message": "I want to share 5 apples"},
            {"role": "assistant", "message": "List under Alameda Unified?"},
            {"role": "user", "message": "yes"},
        ]
        reason = posting_tool_block_reason(
            "yes",
            history,
            {"title": "Apples", "qty": 5, "community_name": "Alameda Unified", "community_confirmed": True},
        )
        assert reason is not None
        assert "expir" in reason.lower()

    def test_expiry_reminder_when_not_asked(self):
        history = [
            {"role": "user", "message": "share 3 loaves"},
            {"role": "assistant", "message": "List under Alameda High?"},
            {"role": "user", "message": "yes"},
        ]
        from backend.ai.conversation_flow import build_posting_step_reminder
        reminder = build_posting_step_reminder("yes", history, lang="en")
        assert reminder is not None
        assert "expir" in reminder.lower()

    def test_skips_photo_ask_when_url_present(self):
        history = [
            {"role": "user", "message": "I want to share bread"},
            {"role": "assistant", "message": "List under Alameda High?"},
            {"role": "user", "message": "yes"},
            {"role": "assistant", "message": "Best by tomorrow?"},
            {"role": "user", "message": "tomorrow"},
            {"role": "user", "message": "image: /uploads/ai/abc.jpg"},
        ]
        reminder = posting_flow_reminder("yes post it", history, lang="en")
        assert reminder is not None
        assert "photo" in reminder.lower() or "summary" in reminder.lower() or "ready to post" in reminder.lower()

    def test_none_when_not_posting(self):
        assert posting_flow_reminder("find food near me", [], lang="en") is None


class TestSinglePostConfirm:
    def test_allows_post_after_one_ready_yes(self):
        history = [
            {"role": "user", "message": "share 3 bread and 5 apples"},
            {"role": "assistant", "message": "List under Alameda Unified?"},
            {"role": "user", "message": "yes"},
            {"role": "assistant", "message": "When do they expire?"},
            {"role": "user", "message": "2030-07-20"},
            {"role": "user", "message": "image: https://cdn.example.com/bread.jpg"},
            {"role": "user", "message": "image: https://cdn.example.com/apples.jpg"},
            {
                "role": "assistant",
                "message": (
                    "Got it — 3 bread + 5 apples under Alameda Unified, "
                    "expiring 2030-07-20, with photos. Ready to post these?"
                ),
            },
        ]
        reason = posting_tool_block_reason(
            "yes",
            history,
            {
                "title": "bread",
                "qty": 3,
                "community_name": "Alameda Unified",
                "community_confirmed": True,
                "expiration_date": "2030-07-20",
                "images": ["https://cdn.example.com/bread.jpg"],
            },
        )
        assert reason is None

    def test_looks_good_phrasing_counts_as_post_confirm(self):
        history = [
            {"role": "user", "message": "share oranges"},
            {"role": "assistant", "message": "List under Alameda Unified?"},
            {"role": "user", "message": "yes"},
            {"role": "assistant", "message": "Best by?"},
            {"role": "user", "message": "Friday"},
            {"role": "user", "message": "image: https://cdn.example.com/o.jpg"},
            {
                "role": "assistant",
                "message": "Does this look right — oranges under Alameda Unified with photo?",
            },
        ]
        reason = posting_tool_block_reason(
            "looks good",
            history,
            {
                "title": "oranges",
                "qty": 1,
                "community_name": "Alameda Unified",
                "community_confirmed": True,
                "expiration_date": "2030-07-18",
                "images": ["https://cdn.example.com/o.jpg"],
            },
        )
        assert reason is None

    def test_blocks_before_any_ready_ask(self):
        history = [
            {"role": "user", "message": "share bread image: https://cdn.example.com/b.jpg"},
            {"role": "assistant", "message": "List under Alameda Unified?"},
            {"role": "user", "message": "yes"},
            {"role": "assistant", "message": "Best by?"},
            {"role": "user", "message": "2030-07-20"},
        ]
        reason = posting_tool_block_reason(
            "2030-07-20",
            history,
            {
                "title": "bread",
                "qty": 1,
                "community_name": "Alameda Unified",
                "community_confirmed": True,
                "expiration_date": "2030-07-20",
                "images": ["https://cdn.example.com/b.jpg"],
            },
        )
        assert reason is not None
        assert "ready to post" in reason.lower() or "summary" in reason.lower()
