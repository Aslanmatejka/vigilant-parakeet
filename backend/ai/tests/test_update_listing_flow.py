"""Update listing: resolve indices and fix title_lookup vs new title."""
from __future__ import annotations

from backend.ai.conversation_flow import (
    _normalize_update_food_listing_args,
    _unwrap_listing_metadata_from_args,
    enrich_donor_listing_tool_args,
    set_last_donor_listings,
)


def _eggs_listing():
    return {
        "id": "07def34e-74a7-4e38-8a66-c8625ac504a1",
        "title": "Eggs",
        "quantity": 6,
    }


def test_title_lookup_becomes_new_title_when_listing_id_set():
    listings = [_eggs_listing(), {"id": "aaaa-bbbb", "title": "Milk"}]
    set_last_donor_listings("u1", listings)
    args = enrich_donor_listing_tool_args(
        "update_food_listing",
        {
            "listing_id": "07def34e-74a7-4e38-8a66-c8625ac504a1",
            "title_lookup": "apples",
            "title": "Eggs",
            "description": "Updated",
        },
        "rename eggs to apples",
        [],
        "u1",
    )
    assert args.get("title_lookup") is None
    assert args["title"] == "apples"
    assert "Eggs" != args["title"]


def test_stale_title_removed_when_same_as_current():
    listings = [_eggs_listing()]
    set_last_donor_listings("u1", listings)
    out = _normalize_update_food_listing_args(
        {
            "listing_id": "07def34e-74a7-4e38-8a66-c8625ac504a1",
            "title": "Eggs",
            "expiry_date": "2026-07-08",
        },
        "change expiry on eggs",
        "u1",
    )
    assert "title" not in out
    assert out["expiry_date"] == "2026-07-08"


def test_resolve_listing_by_display_index():
    listings = [
        {"id": "1111-2222-3333-4444-555555555555", "title": "Bread"},
        _eggs_listing(),
    ]
    set_last_donor_listings("u1", listings)
    args = enrich_donor_listing_tool_args(
        "update_food_listing",
        {"quantity": 10},
        "edit listing #2 quantity to 10",
        [],
        "u1",
    )
    assert args["listing_id"] == "07def34e-74a7-4e38-8a66-c8625ac504a1"
    assert args.get("quantity") == 10.0


def test_auto_resolve_does_not_set_title_for_update():
    listings = [_eggs_listing()]
    set_last_donor_listings("u1", listings)
    args = enrich_donor_listing_tool_args(
        "update_food_listing",
        {"expiry_date": "2026-07-10"},
        "update the eggs listing expiry",
        [],
        "u1",
    )
    assert args["listing_id"] == "07def34e-74a7-4e38-8a66-c8625ac504a1"
    assert "title" not in args


def test_unwrap_community_and_expiry_from_description():
    out = _unwrap_listing_metadata_from_args({
        "description": "Community: Alameda Neighborhood. Expiry: 2026-07-08.",
    })
    assert out.get("community_name") == "Alameda Neighborhood"
    assert out.get("expiry_date") == "2026-07-08"
    assert "description" not in out


def test_unwrap_metadata_from_message_enrichment():
    listings = [_eggs_listing()]
    set_last_donor_listings("u1", listings)
    args = enrich_donor_listing_tool_args(
        "update_food_listing",
        {
            "listing_id": "07def34e-74a7-4e38-8a66-c8625ac504a1",
            "description": "Community: Alameda. Expiry: 2026-07-10.",
        },
        "set community to Alameda and expiry 2026-07-10",
        [],
        "u1",
    )
    assert args.get("community_name") == "Alameda"
    assert args.get("expiry_date") == "2026-07-10"
    assert "description" not in args
