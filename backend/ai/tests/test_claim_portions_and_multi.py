"""Regression: claim portions + multi-claim qty reflection."""
from __future__ import annotations

from backend.ai.conversation_flow import (
    clear_claim_drafts,
    enrich_claim_listing_args,
    enrich_claim_listings_args,
    get_claim_drafts,
    set_last_search_listings,
    sync_claim_drafts,
    upsert_claim_drafts_from_message,
)
from backend.tools import _normalize_claim_quantity


def _seed(uid: str = "u-portion"):
    clear_claim_drafts(uid)
    set_last_search_listings(uid, [
        {"id": "lid-t", "title": "Tomatoes", "quantity": 10, "unit": "items"},
        {"id": "lid-c", "title": "Carrots", "quantity": 8, "unit": "items"},
        {"id": "lid-b", "title": "Bread", "quantity": 6, "unit": "loaves"},
    ])


class TestPortionClaims:
    def test_normalize_allows_portion_above_two(self):
        assert _normalize_claim_quantity(5, 10) == (5, False)

    def test_normalize_all_takes_stock(self):
        assert _normalize_claim_quantity("all", 10) == (10, False)
        assert _normalize_claim_quantity("all of them", 7) == (7, False)

    def test_enrich_all_of_them_does_not_force_one(self):
        _seed()
        history = [
            {
                "role": "assistant",
                "message": "Here's what's near you:\n1. Tomatoes — 10 left\n2. Carrots",
            },
            {"role": "user", "message": "1"},
            {"role": "assistant", "message": "Nice choice — how many tomatoes do you want?"},
        ]
        out = enrich_claim_listing_args(
            {"listing_id": 1},
            "All of them",
            history,
            "u-portion",
        )
        assert out.get("quantity") in (10, "all")
        assert out.get("quantity") != 1

    def test_enrich_digit_qty_three(self):
        _seed()
        history = [
            {
                "role": "assistant",
                "message": "Here's what's near you:\n1. Tomatoes — 10 left",
            },
            {"role": "user", "message": "1"},
            {"role": "assistant", "message": "How many would you like?"},
        ]
        out = enrich_claim_listing_args(
            {"listing_id": 1},
            "3",
            history,
            "u-portion",
        )
        assert out.get("quantity") == 3


class TestMultiClaimQtyReflection:
    def test_two_listings_with_distinct_qty_ready(self):
        _seed()
        drafts = upsert_claim_drafts_from_message(
            "u-portion", "2 tomatoes and 3 bread",
        )
        assert len(drafts) >= 2
        by = {str(d.get("title") or "").lower(): d for d in drafts}
        assert float(by["tomatoes"]["qty"]) == 2
        assert float(by["bread"]["qty"]) == 3
        enriched = enrich_claim_listings_args({}, "yes", [], "u-portion")
        items = enriched.get("items") or []
        assert len(items) >= 2
        qty_by_lid = {i["listing_id"]: i["quantity"] for i in items}
        assert qty_by_lid["lid-t"] == 2
        assert qty_by_lid["lid-b"] == 3

    def test_each_fills_all_missing_qtys(self):
        _seed()
        upsert_claim_drafts_from_message("u-portion", "#1 and #2")
        drafts = sync_claim_drafts(
            "u-portion",
            "2 each",
            [{"role": "assistant", "message": "How many of each?"}],
        )
        assert all(float(d.get("qty") or 0) == 2 for d in drafts)

    def test_all_of_them_fills_from_search_cache(self):
        _seed()
        upsert_claim_drafts_from_message("u-portion", "#1 and #3")
        drafts = sync_claim_drafts(
            "u-portion",
            "all of them",
            [{"role": "assistant", "message": "How many do you want?"}],
        )
        by_lid = {d["listing_id"]: d for d in drafts}
        assert float(by_lid["lid-t"]["qty"]) == 10
        assert float(by_lid["lid-b"]["qty"]) == 6

    def test_fresh_search_clears_stale_drafts(self):
        _seed()
        upsert_claim_drafts_from_message("u-portion", "#1 and #2")
        assert len(get_claim_drafts("u-portion")) == 2
        set_last_search_listings("u-portion", [
            {"id": "lid-new", "title": "Apples", "quantity": 4},
        ])
        assert get_claim_drafts("u-portion") == []
