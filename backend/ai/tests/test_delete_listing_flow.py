"""Delete listing: resolve truncated UUIDs and donor listing indices."""
from __future__ import annotations

from backend.ai.conversation_flow import (
    enrich_donor_listing_tool_args,
    resolve_donor_listing_id,
    set_last_donor_listings,
)


def test_resolve_donor_listing_id_by_index():
    listings = [
        {"id": "aaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "title": "Rice"},
        {"id": "1111-2222-3333-4444-555555555555", "title": "Bread"},
    ]
    set_last_donor_listings("u1", listings)
    resolved, err = resolve_donor_listing_id("2", "u1")
    assert err is None
    assert resolved == "1111-2222-3333-4444-555555555555"
    resolved, err = resolve_donor_listing_id("#1", "u1")
    assert err is None
    assert resolved == "aaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def test_resolve_donor_listing_id_truncated_uuid():
    full = "c0e1e5f1-c60b-4669-8c06-610a9e0966ab"
    listings = [{"id": full, "title": "Duplicate rice"}]
    set_last_donor_listings("u1", listings)
    truncated = "c0e1e5f1-c60b-4669-8c06-610a9e0966"
    resolved, err = resolve_donor_listing_id(truncated, "u1")
    assert err is None
    assert resolved == full


def test_enrich_donor_listing_tool_args():
    listings = [{"id": "aaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "title": "Rice"}]
    set_last_donor_listings("u1", listings)
    args = enrich_donor_listing_tool_args(
        "delete_listing",
        {"listing_id": "1"},
        "yes delete it",
        [],
        "u1",
    )
    assert args["listing_id"] == "aaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert args.get("confirmed") is True
