"""Tests for multi-listing share drafts + per-item photo binding."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.ai.conversation_flow import (
    _parse_share_items_from_text,
    assign_photos_to_drafts,
    clear_share_drafts,
    enrich_post_food_listings_args,
    get_share_drafts,
    posting_batch_tool_block_reason,
    set_share_drafts,
    share_drafts_missing,
    share_drafts_ready,
    sync_share_drafts,
    upsert_share_drafts_from_message,
)


@pytest.fixture(autouse=True)
def _clean_drafts():
    clear_share_drafts("u-test")
    yield
    clear_share_drafts("u-test")


class TestParseShareItems:
    def test_two_qty_foods(self):
        items = _parse_share_items_from_text(
            "I want to share 3 loaves of bread and 5 apples"
        )
        titles = {i["title"].lower() for i in items}
        assert "bread" in titles
        assert "apples" in titles or "apple" in titles
        assert len(items) >= 2

    def test_bare_and_foods(self):
        items = _parse_share_items_from_text("share bread and apples")
        titles = {i["title"].lower() for i in items}
        assert "bread" in titles
        assert "apples" in titles or "apple" in titles

    def test_also_bag_of_oranges(self):
        items = _parse_share_items_from_text(
            "3 loaves of bread and a bag of oranges"
        )
        titles = {i["title"].lower() for i in items}
        assert "bread" in titles
        assert "oranges" in titles or "orange" in titles

    def test_ignores_photo_only(self):
        assert _parse_share_items_from_text("image: https://cdn.example.com/a.jpg") == []

    def test_carrot_and_tomatoes_both_parsed(self):
        items = _parse_share_items_from_text("i want to share carrot and tomatoes")
        titles = {i["title"].lower() for i in items}
        assert "carrot" in titles or "carrots" in titles
        assert "tomato" in titles or "tomatoes" in titles

    def test_basket_of_carrots(self):
        items = _parse_share_items_from_text(
            "1 basket of carrots and 1 basket of tomatoes"
        )
        titles = {i["title"].lower() for i in items}
        assert any("carrot" in t for t in titles)
        assert any("tomato" in t for t in titles)


class TestShareDraftDoesNotBleedPriorFood:
    def test_fresh_share_clears_stale_bananas(self):
        set_share_drafts("u-test", [
            {"id": "d1", "title": "bananas", "qty": 5, "unit": "items",
             "expiry": "2026-07-20", "photo_url": None, "photo_declined": False},
        ])
        drafts = sync_share_drafts(
            "u-test",
            "i want to share carrot and tomatoes",
            history=[
                {"role": "assistant", "message": "Posted! Your bananas are live."},
            ],
        )
        titles = {str(d.get("title") or "").lower() for d in drafts}
        assert "bananas" not in titles
        assert any("carrot" in t for t in titles)
        assert any("tomato" in t for t in titles)

    def test_user_restrict_keeps_only_named_foods(self):
        set_share_drafts("u-test", [
            {"id": "d1", "title": "bananas", "qty": 5, "unit": "items",
             "expiry": None, "photo_url": None, "photo_declined": False},
            {"id": "d2", "title": "carrots", "qty": 1, "unit": "basket",
             "expiry": "2026-07-25", "photo_url": None, "photo_declined": False},
            {"id": "d3", "title": "tomatoes", "qty": 1, "unit": "basket",
             "expiry": "2026-07-25", "photo_url": None, "photo_declined": False},
        ])
        drafts = sync_share_drafts(
            "u-test",
            "we are listing tomatoes and carrots please",
            history=[
                {"role": "user", "message": "i want to share carrot and tomatoes"},
                {"role": "assistant", "message": "How many bananas?"},
            ],
        )
        titles = {str(d.get("title") or "").lower() for d in drafts}
        assert "bananas" not in titles
        assert any("carrot" in t for t in titles)
        assert any("tomato" in t for t in titles)
    def test_upsert_creates_two_drafts(self):
        drafts = upsert_share_drafts_from_message(
            "u-test", "share 3 bread and 5 apples",
        )
        assert len(drafts) >= 2

    def test_ordered_photo_assignment(self):
        set_share_drafts("u-test", [
            {"id": "d1", "title": "bread", "qty": 3, "unit": "loaf",
             "expiry": None, "photo_url": None, "photo_declined": False},
            {"id": "d2", "title": "apples", "qty": 5, "unit": "items",
             "expiry": None, "photo_url": None, "photo_declined": False},
        ])
        history = [
            {"role": "user", "message": "image: https://cdn.example.com/bread.jpg"},
            {"role": "user", "message": "image: https://cdn.example.com/apples.jpg"},
        ]
        drafts = assign_photos_to_drafts("u-test", history, "")
        assert drafts[0]["photo_url"] == "https://cdn.example.com/bread.jpg"
        assert drafts[1]["photo_url"] == "https://cdn.example.com/apples.jpg"

    def test_titled_photo_binds_to_named_food(self):
        set_share_drafts("u-test", [
            {"id": "d1", "title": "bread", "qty": 3, "unit": "loaf",
             "expiry": "2026-07-20", "photo_url": None, "photo_declined": False},
            {"id": "d2", "title": "apples", "qty": 5, "unit": "items",
             "expiry": "2026-07-20", "photo_url": None, "photo_declined": False},
        ])
        history = [
            {"role": "assistant", "message": "Want a photo of the apples?"},
        ]
        drafts = assign_photos_to_drafts(
            "u-test",
            history,
            "photo for the apples image: https://cdn.example.com/apples.jpg",
        )
        apples = next(d for d in drafts if d["title"] == "apples")
        assert apples["photo_url"] == "https://cdn.example.com/apples.jpg"
        bread = next(d for d in drafts if d["title"] == "bread")
        assert bread.get("photo_url") in (None, "")

    def test_no_cross_draft_photo_reuse_after_clear(self):
        sync_share_drafts(
            "u-test",
            "3 bread and 5 apples",
            [{"role": "user", "message": "image: https://cdn.example.com/old.jpg"}],
        )
        clear_share_drafts("u-test")
        drafts = sync_share_drafts("u-test", "share oranges", [])
        assert all(not d.get("photo_url") for d in drafts)

    def test_missing_and_ready(self):
        drafts = [
            {"title": "bread", "qty": 3, "unit": "loaf", "expiry": "2026-07-20",
             "photo_url": "https://x/a.jpg", "photo_declined": False},
            {"title": "apples", "qty": 5, "unit": "items", "expiry": None,
             "photo_url": None, "photo_declined": False},
        ]
        missing = share_drafts_missing(drafts)
        assert any(m["title"] == "apples" for m in missing)
        assert share_drafts_ready(drafts, community_confirmed=True) is False
        drafts[1]["expiry"] = "2026-07-21"
        drafts[1]["photo_declined"] = True
        # Declining a photo no longer makes the draft ready.
        assert share_drafts_ready(drafts, community_confirmed=True) is False
        drafts[1]["photo_url"] = "https://x/b.jpg"
        drafts[1]["photo_declined"] = False
        assert share_drafts_ready(drafts, community_confirmed=True) is True


class TestBatchEnrichAndBlock:
    def test_enrich_builds_items_from_drafts(self):
        set_share_drafts("u-test", [
            {"id": "d1", "title": "bread", "qty": 3, "unit": "loaf",
             "expiry": "2026-07-20", "photo_url": "https://cdn.example.com/b.jpg",
             "photo_declined": False},
            {"id": "d2", "title": "apples", "qty": 5, "unit": "items",
             "expiry": "2026-07-21", "photo_url": "https://cdn.example.com/a.jpg",
             "photo_declined": False},
        ])
        history = [
            {"role": "assistant", "message": "List under Alameda Unified?"},
            {"role": "user", "message": "yes"},
        ]
        out = enrich_post_food_listings_args(
            {"community_name": "Alameda Unified", "community_confirmed": True},
            "post them",
            history,
            "u-test",
        )
        items = out.get("items") or []
        assert len(items) == 2
        assert items[0]["images"] == ["https://cdn.example.com/b.jpg"]
        assert items[1]["images"] == ["https://cdn.example.com/a.jpg"]

    def test_block_when_incomplete(self):
        set_share_drafts("u-test", [
            {"id": "d1", "title": "bread", "qty": 3, "unit": "loaf",
             "expiry": None, "photo_url": None, "photo_declined": False},
            {"id": "d2", "title": "apples", "qty": 5, "unit": "items",
             "expiry": None, "photo_url": None, "photo_declined": False},
        ])
        reason = posting_batch_tool_block_reason(
            "post them",
            [],
            {"community_confirmed": True, "items": []},
            user_id="u-test",
        )
        assert reason
        assert "incomplete" in reason.lower() or "need" in reason.lower()

    def test_block_single_item_batch(self):
        clear_share_drafts("u-test")
        reason = posting_batch_tool_block_reason(
            "post it",
            [],
            {"community_confirmed": True, "items": [{"title": "bread", "qty": 1}]},
            user_id="u-test",
        )
        assert reason
        assert "post_food_listing" in reason


@pytest.mark.asyncio
async def test_post_food_listings_passes_distinct_photos():
    from backend.ai.tools import _post_food_listings

    calls = []

    async def fake_post(**kwargs):
        calls.append(kwargs)
        return {
            "success": True,
            "listing_id": f"id-{len(calls)}",
            "image_url": (kwargs.get("images") or [None])[0],
            "has_photo": bool(kwargs.get("images")),
        }

    with patch("backend.ai.tools._post_food_listing", new=AsyncMock(side_effect=fake_post)):
        result = await _post_food_listings(
            user_id="u-test",
            community_name="Alameda Unified",
            community_confirmed=True,
            address="1 Main St",
            items=[
                {
                    "title": "bread",
                    "qty": 3,
                    "unit": "loaf",
                    "expiration_date": "2026-07-20",
                    "images": ["https://cdn.example.com/bread.jpg"],
                },
                {
                    "title": "apples",
                    "qty": 5,
                    "unit": "items",
                    "expiration_date": "2026-07-21",
                    "images": ["https://cdn.example.com/apples.jpg"],
                },
            ],
        )
    assert result["success"] is True
    assert result["count_posted"] == 2
    assert calls[0]["images"] == ["https://cdn.example.com/bread.jpg"]
    assert calls[1]["images"] == ["https://cdn.example.com/apples.jpg"]
    assert get_share_drafts  # keep import used
