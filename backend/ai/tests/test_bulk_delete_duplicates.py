"""Bulk duplicate delete for donor listings."""
from __future__ import annotations

from backend.ai.conversation_flow import (
    enrich_donor_listing_tool_args,
    set_last_donor_listings,
)
from backend.tools import duplicate_listing_ids_to_remove


def _make_vegetable_duplicates(n: int = 13):
    keep_id = "keep-0000-0000-0000-000000000001"
    rows = [{
        "id": keep_id,
        "title": "Fresh Vegetables",
        "has_photo": True,
        "image_url": "https://example.com/v.jpg",
    }]
    for i in range(2, n + 1):
        rows.append({
            "id": f"dup-{i:04d}-0000-0000-000000000000",
            "title": "Fresh Vegetables",
            "has_photo": False,
        })
    return rows


def test_duplicate_listing_ids_to_remove_keeps_one_with_photo():
    rows = _make_vegetable_duplicates(13)
    remove_ids, meta = duplicate_listing_ids_to_remove(rows)
    assert len(remove_ids) == 12
    assert meta["to_delete"] == 12
    assert "keep-0000" in meta["kept"][0]["id"]


def test_enrich_delete_all_duplicates_from_history():
    rows = _make_vegetable_duplicates(5)
    set_last_donor_listings("u1", rows)
    args = enrich_donor_listing_tool_args(
        "delete_listing",
        {"user_id": "u1"},
        "yes, confirm",
        [
            {"role": "user", "message": "delete all duplicates"},
            {"role": "assistant", "message": "You have 5 duplicate Fresh Vegetables listings."},
        ],
        "u1",
    )
    assert args.get("delete_duplicates") is True
    assert len(args.get("listing_ids") or []) == 4
    assert args.get("_bulk_delete_count") == 4


def test_build_confirmation_summary_bulk():
    from backend.ai.ai_engine import _build_confirmation_summary

    summary = _build_confirmation_summary("delete_listing", {
        "delete_duplicates": True,
        "listing_ids": ["a", "b", "c"],
        "_bulk_delete_count": 12,
    })
    assert "12 duplicate" in summary
