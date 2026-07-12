"""Tests for multi-listing claim drafts + batch claim_listings."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.ai.conversation_flow import (
    claim_drafts_missing,
    claim_drafts_ready,
    claiming_batch_tool_block_reason,
    clear_claim_drafts,
    enrich_claim_listings_args,
    get_claim_drafts,
    set_claim_drafts,
    set_last_search_listings,
    sync_claim_drafts,
    upsert_claim_drafts_from_message,
)


@pytest.fixture(autouse=True)
def _clean_drafts():
    clear_claim_drafts("u-claim")
    set_last_search_listings("u-claim", [])
    yield
    clear_claim_drafts("u-claim")
    set_last_search_listings("u-claim", [])


def _seed_search():
    set_last_search_listings("u-claim", [
        {"id": "lid-orange", "title": "Oranges", "quantity": 10, "unit": "items",
         "display_index": 1},
        {"id": "lid-bread", "title": "Bread", "quantity": 8, "unit": "loaves",
         "display_index": 2},
        {"id": "lid-banana", "title": "Bananas", "quantity": 12, "unit": "items",
         "display_index": 3},
    ])


class TestParseClaimPicks:
    def test_hash_indices(self):
        _seed_search()
        drafts = upsert_claim_drafts_from_message("u-claim", "#1 and #3")
        assert len(drafts) == 2
        lids = {d["listing_id"] for d in drafts}
        assert lids == {"lid-orange", "lid-banana"}
        assert all(d.get("qty") is None for d in drafts)

    def test_both(self):
        _seed_search()
        drafts = upsert_claim_drafts_from_message("u-claim", "both")
        assert len(drafts) == 2
        assert drafts[0]["listing_id"] == "lid-orange"
        assert drafts[1]["listing_id"] == "lid-bread"

    def test_qty_and_foods(self):
        _seed_search()
        drafts = upsert_claim_drafts_from_message(
            "u-claim", "2 oranges and 3 bread",
        )
        assert len(drafts) >= 2
        by_title = {str(d.get("title") or "").lower(): d for d in drafts}
        orange = next(d for k, d in by_title.items() if "orange" in k)
        bread = next(d for k, d in by_title.items() if "bread" in k)
        assert orange["listing_id"] == "lid-orange"
        assert bread["listing_id"] == "lid-bread"
        assert float(orange["qty"]) == 2
        assert float(bread["qty"]) == 3

    def test_bare_dual_titles(self):
        _seed_search()
        drafts = upsert_claim_drafts_from_message(
            "u-claim", "the apples and the bananas",
        )
        # apples may not match; bananas should. Need two food words in FOOD set.
        # Use oranges + bananas which are both in search.
        clear_claim_drafts("u-claim")
        drafts = upsert_claim_drafts_from_message(
            "u-claim", "the oranges and the bananas",
        )
        assert len(drafts) >= 2
        assert all(d.get("qty") is None for d in drafts)


class TestClaimDraftQueue:
    def test_missing_qty_not_ready(self):
        drafts = [
            {"id": "c1", "listing_id": "a", "title": "Oranges", "qty": None},
            {"id": "c2", "listing_id": "b", "title": "Bread", "qty": 3},
        ]
        missing = claim_drafts_missing(drafts)
        assert any(m["title"] == "Oranges" for m in missing)
        assert claim_drafts_ready(drafts) is False

    def test_fill_qty_then_ready(self):
        _seed_search()
        sync_claim_drafts("u-claim", "#1 and #3", [])
        history = [
            {"role": "assistant", "message": "How many of the Oranges?"},
        ]
        drafts = sync_claim_drafts("u-claim", "2", history)
        orange = next(d for d in drafts if d["listing_id"] == "lid-orange")
        assert float(orange["qty"]) == 2
        drafts = sync_claim_drafts(
            "u-claim", "4",
            [{"role": "assistant", "message": "How many of the Bananas?"}],
        )
        assert claim_drafts_ready(drafts) is True


class TestBatchEnrichAndBlock:
    def test_enrich_builds_distinct_items(self):
        set_claim_drafts("u-claim", [
            {"id": "c1", "listing_id": "lid-orange", "title": "Oranges",
             "qty": 2, "unit": "items"},
            {"id": "c2", "listing_id": "lid-bread", "title": "Bread",
             "qty": 3, "unit": "loaves"},
        ])
        out = enrich_claim_listings_args(
            {}, "claim them", [], "u-claim",
        )
        items = out.get("items") or []
        assert len(items) == 2
        assert items[0]["listing_id"] == "lid-orange"
        assert items[0]["quantity"] == 2
        assert items[1]["listing_id"] == "lid-bread"
        assert items[1]["quantity"] == 3

    def test_block_when_incomplete(self):
        set_claim_drafts("u-claim", [
            {"id": "c1", "listing_id": "lid-orange", "title": "Oranges", "qty": None},
            {"id": "c2", "listing_id": "lid-bread", "title": "Bread", "qty": 3},
        ])
        reason = claiming_batch_tool_block_reason(
            "claim them",
            [],
            {"items": []},
            user_id="u-claim",
        )
        assert reason
        assert "incomplete" in reason.lower() or "need" in reason.lower()

    def test_block_single_item_batch(self):
        clear_claim_drafts("u-claim")
        reason = claiming_batch_tool_block_reason(
            "claim it",
            [],
            {"items": [{"listing_id": "x", "quantity": 1}]},
            user_id="u-claim",
        )
        assert reason
        assert "claim_listing" in reason


@pytest.mark.asyncio
async def test_claim_listings_loops_with_distinct_qty():
    from backend.ai.tools import _claim_listings

    calls = []

    async def fake_claim(**kwargs):
        calls.append(kwargs)
        return {
            "success": True,
            "listing_id": kwargs["listing_id"],
            "title": kwargs["listing_id"],
            "quantity": kwargs["quantity"],
            "claim_id": f"c-{len(calls)}",
        }

    with patch("backend.ai.tools._claim_listing", new=AsyncMock(side_effect=fake_claim)):
        result = await _claim_listings(
            user_id="u-claim",
            items=[
                {"listing_id": "lid-a", "quantity": 2, "title": "Oranges"},
                {"listing_id": "lid-b", "quantity": 5, "title": "Bread"},
            ],
        )

    assert result["success"] is True
    assert result["count_claimed"] == 2
    assert len(calls) == 2
    assert calls[0]["listing_id"] == "lid-a"
    assert calls[0]["quantity"] == 2
    assert calls[1]["listing_id"] == "lid-b"
    assert calls[1]["quantity"] == 5
