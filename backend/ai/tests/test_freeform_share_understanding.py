"""Nouri must understand free-form food, dates, and catalog communities."""
from __future__ import annotations

from datetime import date, timedelta

from backend.ai.conversation_flow import (
    _calendar_date_is_past,
    _extract_expiry_from_text,
    _match_community_in_catalog,
    _parse_share_items_from_text,
    _share_title_qty_from_thread,
    build_posting_step_reminder,
    enrich_post_food_listing_args,
    posting_flow_state,
    posting_tool_block_reason,
)


class TestAnyFutureExpiry:
    def test_word_numbers(self):
        assert _extract_expiry_from_text("in two days") == (
            date.today() + timedelta(days=2)
        ).isoformat()
        assert _extract_expiry_from_text("in a few days") == (
            date.today() + timedelta(days=3)
        ).isoformat()
        from backend.ai.conversation_flow import _add_calendar_months
        assert _extract_expiry_from_text("in two months") == (
            _add_calendar_months(date.today(), 2).isoformat()
        )

    def test_next_week_and_weekend(self):
        nxt = _extract_expiry_from_text("next week")
        assert nxt == (date.today() + timedelta(weeks=1)).isoformat()
        weekend = _extract_expiry_from_text("this weekend")
        assert weekend is not None
        assert date.fromisoformat(weekend).weekday() == 5

    def test_end_of_named_month(self):
        result = _extract_expiry_from_text("end of December")
        assert result is not None
        y, m, d = map(int, result.split("-"))
        assert (m, d) == (12, 31)
        assert date(y, m, d) >= date.today()

    def test_slash_date_without_year_is_upcoming(self):
        result = _extract_expiry_from_text("8/30")
        assert result is not None
        y, m, d = map(int, result.split("-"))
        assert (m, d) == (8, 30)
        assert date(y, m, d) >= date.today()

    def test_past_iso_is_wrong_time(self):
        assert _calendar_date_is_past("2020-01-01") is True
        assert _calendar_date_is_past(date.today().isoformat()) is False
        assert _calendar_date_is_past(
            (date.today() + timedelta(days=3)).isoformat()
        ) is False

    def test_past_spoken_date_does_not_count_as_provided(self):
        history = [
            {"role": "user", "message": "share leftover lasagna"},
            {"role": "assistant", "message": "Should this go under Do Good Warehouse?"},
            {"role": "user", "message": "yes"},
            {"role": "assistant", "message": "When is it good until?"},
        ]
        state = posting_flow_state("January 1, 2020", history)
        assert state["expiry_provided"] is False
        assert state["expiry_is_past"] is True
        reminder = build_posting_step_reminder("January 1, 2020", history, lang="en")
        assert reminder is not None
        assert "past" in reminder.lower() or "wrong time" in reminder.lower()

    def test_past_expiry_blocks_post_tool(self):
        history = [
            {"role": "user", "message": "share bread"},
            {"role": "assistant", "message": "Should this go under Do Good Warehouse?"},
            {"role": "user", "message": "yes"},
            {"role": "assistant", "message": "When does it expire?"},
            {"role": "user", "message": "2020-01-01"},
            {
                "role": "assistant",
                "message": "Ready to post bread under Do Good Warehouse with your photos?",
            },
            {"role": "user", "message": "image: https://cdn.example.com/b.jpg"},
        ]
        reason = posting_tool_block_reason(
            "yes, post it",
            history,
            {
                "title": "bread",
                "qty": 1,
                "community_confirmed": True,
                "expiration_date": "2020-01-01",
                "images": ["https://cdn.example.com/b.jpg"],
            },
        )
        assert reason is not None
        assert "past" in reason.lower()

    def test_bare_duration_answer_is_saved(self):
        history = [
            {"role": "user", "message": "Do it for me"},
            {"role": "assistant", "message": "What food do you want to share, and how much?"},
            {"role": "user", "message": "100 boxes of vegetables"},
            {"role": "assistant", "message": "Should this go under Alameda Unified?"},
            {"role": "user", "message": "yes"},
            {"role": "assistant", "message": "When does it expire"},
        ]
        for answer in ("2 days", "2 months", "a week", "Tomorrow", "In 2 days"):
            state = posting_flow_state(answer, history)
            assert state["expiry_provided"] is True, answer
            assert state["expiry_is_past"] is False, answer
            reminder = build_posting_step_reminder(answer, history, lang="en")
            assert reminder is not None
            assert "do not ask again" in reminder.lower() or "already gave" in reminder.lower()

    def test_qty_range_is_not_an_expiry(self):
        history = [
            {"role": "user", "message": "share 5-10 boxes of vegetables"},
            {"role": "assistant", "message": "Should this go under Do Good Warehouse?"},
            {"role": "user", "message": "yes"},
        ]
        state = posting_flow_state("yes", history)
        assert state["expiry_provided"] is False
        assert _extract_expiry_from_text("5-10 boxes of vegetables") is None

    def test_later_real_date_overrides_nothing_from_food_turn(self):
        history = [
            {"role": "user", "message": "share 5-10 boxes of vegetables"},
            {"role": "assistant", "message": "When does it expire?"},
        ]
        state = posting_flow_state("tomorrow", history)
        assert state["expiry_provided"] is True
        assert _extract_expiry_from_text("tomorrow") == (
            date.today() + timedelta(days=1)
        ).isoformat()


class TestAnyFoodTitle:
    def test_unknown_dish_with_unit(self):
        items = _parse_share_items_from_text("20 servings of chicken tikka masala")
        assert items
        assert "tikka" in items[0]["title"]
        assert items[0]["qty"] == 20

    def test_leftover_lasagna_from_share_intent(self):
        items = _parse_share_items_from_text("I want to share leftover lasagna")
        assert items
        assert "lasagna" in items[0]["title"]

    def test_food_qty_answer_without_lexicon(self):
        history = [
            {"role": "assistant", "message": "What food do you want to share, and how much?"},
        ]
        title, qty, unit = _share_title_qty_from_thread(
            history, "homemade empanadas",
        )
        assert title and "empanada" in title
        assert qty == 1.0
        assert unit == "items"

    def test_does_not_treat_three_days_as_food(self):
        assert _parse_share_items_from_text("in 3 days") == []
        assert _parse_share_items_from_text("3 days from now") == []


class TestAnyCatalogCommunity:
    def test_unique_fuzzy_match(self):
        catalog = [
            {"id": "c1", "name": "Alameda Unified School District"},
            {"id": "c2", "name": "Ruby Bridges Elementary CC"},
            {"id": "c3", "name": "Do Good Warehouse"},
        ]
        hit = _match_community_in_catalog("ruby bridges", catalog)
        assert hit is not None
        assert hit["id"] == "c2"

    def test_ambiguous_unified_does_not_guess(self):
        catalog = [
            {"id": "c1", "name": "Alameda Unified School District"},
            {"id": "c2", "name": "Oakland Unified School District"},
        ]
        assert _match_community_in_catalog("Unified", catalog) is None

    def test_enrich_accepts_typed_hub_name(self):
        history = [
            {"role": "user", "message": "share leftover lasagna"},
            {"role": "assistant", "message": "Which community should this go under?"},
        ]
        out = enrich_post_food_listing_args(
            {},
            "NEA/ACLC CC",
            history,
        )
        assert out.get("community_confirmed") is True
        assert "nea" in (out.get("community_name") or "").lower()
        assert "lasagna" in (out.get("title") or "")
