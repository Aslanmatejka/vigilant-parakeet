"""Multi-food search: pawpaw AND carrots must OR-match, not drop one."""
from __future__ import annotations

from backend.ai.conversation_flow import (
    _mentioned_foods_from_message,
    build_last_search_snapshot_reminder,
    enrich_search_food_args,
    set_last_search_listings,
    clear_last_search_listings,
)
from backend.tools import (
    _apply_title_query_filter,
    _listing_matches_title_hint,
    split_title_query_hints,
)


class TestSplitTitleHints:
    def test_and_comma(self):
        assert split_title_query_hints("pawpaw and carrots") == ["pawpaw", "carrots"]
        assert split_title_query_hints("pawpaw, carrots") == ["pawpaw", "carrots"]

    def test_single(self):
        assert split_title_query_hints("carrots") == ["carrots"]


class TestTitleOrMatch:
    def test_basket_of_carrots_matches_carrot(self):
        row = {"title": "Basket of Carrots", "id": "1"}
        assert _listing_matches_title_hint(row, "carrots")
        assert _listing_matches_title_hint(row, "carrot")

    def test_or_keeps_both_foods(self):
        rows = [
            {"id": "p", "title": "Pawpaw", "distance_km": 0.1},
            {"id": "c", "title": "Basket of Carrots", "distance_km": 0.2},
            {"id": "b", "title": "Bread", "distance_km": 0.3},
        ]
        kept, matched, missing = _apply_title_query_filter(
            rows, "pawpaw, carrots",
        )
        lids = {r["id"] for r in kept}
        assert lids == {"p", "c"}
        assert "pawpaw" in matched
        assert "carrots" in matched
        assert missing == []

    def test_single_pawpaw_no_longer_required_to_drop_carrots_when_or(self):
        rows = [
            {"id": "p", "title": "Pawpaw"},
            {"id": "c", "title": "Basket of Carrots"},
        ]
        # Old bug path used title_query="pawpaw" alone — still filters to pawpaw.
        kept, matched, missing = _apply_title_query_filter(rows, "pawpaw")
        assert [r["id"] for r in kept] == ["p"]
        assert matched == ["pawpaw"]


class TestEnrichMultiFood:
    def test_pawpaw_and_carrots_sets_or_query(self):
        out = enrich_search_food_args(
            {"title_query": "pawpaw"},
            "i want pawpaw and carrots",
        )
        tq = out.get("title_query") or ""
        assert "pawpaw" in tq
        assert "carrot" in tq  # carrot or carrots
        assert out.get("_multi_food_search") is True

    def test_extract_foods(self):
        foods = _mentioned_foods_from_message("looking for pawpaw and carrots near me")
        assert "pawpaw" in foods
        assert "carrots" in foods or "carrot" in foods


class TestSearchSnapshotHasAddress:
    def test_includes_address_and_qty(self):
        clear_last_search_listings("u-snap")
        set_last_search_listings("u-snap", [
            {
                "id": "lid-c",
                "display_index": 1,
                "title": "Basket of Carrots",
                "quantity": 1,
                "unit": "basket",
                "address": "1423 Park St, Alameda, CA",
                "community_name": "Do Good Warehouse",
            },
        ])
        rem = build_last_search_snapshot_reminder("u-snap")
        assert rem is not None
        assert "Basket of Carrots" in rem
        assert "1423 Park" in rem
        assert "1 basket" in rem
        clear_last_search_listings("u-snap")
