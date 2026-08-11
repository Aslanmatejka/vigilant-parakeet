"""Bulk / delete-all listing cleanup for donors (CSV imports)."""
from __future__ import annotations

from backend.ai.conversation_flow import (
    enrich_donor_listing_tool_args,
    resolve_donor_listing_id,
    set_last_bulk_posted_ids,
    set_last_donor_listings,
)
from backend.ai.ai_engine import _build_confirmation_summary


def _make_csv_batch():
    return [
        {"id": "aaaa1111-0000-0000-0000-000000000001", "title": "Fresh Apples", "status": "approved"},
        {"id": "bbbb2222-0000-0000-0000-000000000002", "title": "Whole Wheat Bread", "status": "approved"},
        {"id": "cccc3333-0000-0000-0000-000000000003", "title": "Canned Beans", "status": "approved"},
        {"id": "dddd4444-0000-0000-0000-000000000004", "title": "Fresh Apples", "status": "approved"},
    ]


def test_resolve_donor_listing_id_accepts_three_digit_index():
    rows = [
        {"id": f"{i:08d}-0000-0000-0000-000000000000", "title": f"Item {i}"}
        for i in range(1, 12)
    ]
    set_last_donor_listings("u-bulk", rows)
    resolved, err = resolve_donor_listing_id("11", "u-bulk")
    assert err is None
    assert resolved == "00000011-0000-0000-0000-000000000000"


def test_enrich_resolves_display_indices_in_listing_ids():
    rows = _make_csv_batch()
    set_last_donor_listings("u1", rows)
    args = enrich_donor_listing_tool_args(
        "delete_listing",
        {"user_id": "u1", "listing_ids": ["1", "2", "3"]},
        "delete these",
        [],
        "u1",
    )
    assert args["listing_ids"] == [
        rows[0]["id"], rows[1]["id"], rows[2]["id"],
    ]
    assert args.get("_bulk_delete_count") == 3


def test_enrich_rejects_hallucinated_numeric_ids():
    rows = _make_csv_batch()
    set_last_donor_listings("u1", rows)
    args = enrich_donor_listing_tool_args(
        "delete_listing",
        {"user_id": "u1", "listing_ids": ["146", "147", "148"]},
        "delete them",
        [],
        "u1",
    )
    assert args.get("_resolve_error")
    assert not args.get("listing_ids")


def test_enrich_delete_bulk_listings_uses_last_batch():
    ids = [r["id"] for r in _make_csv_batch()]
    set_last_bulk_posted_ids("u1", ids)
    set_last_donor_listings("u1", _make_csv_batch())
    args = enrich_donor_listing_tool_args(
        "delete_listing",
        {"user_id": "u1"},
        "delete the bulk listings",
        [
            {"role": "assistant", "message": "Created 4 listings from your CSV."},
        ],
        "u1",
    )
    assert args.get("delete_all") is True
    assert args.get("listing_ids") == ids
    assert args.get("_delete_scope") == "last_bulk"


def test_enrich_delete_them_all_is_delete_all_not_duplicates():
    rows = _make_csv_batch()
    set_last_donor_listings("u1", rows)
    set_last_bulk_posted_ids("u1", [])
    # Clear bulk cache explicitly
    from backend.ai.conversation_flow import clear_last_bulk_posted_ids
    clear_last_bulk_posted_ids("u1")
    args = enrich_donor_listing_tool_args(
        "delete_listing",
        {"user_id": "u1"},
        "delete them all",
        [
            {"role": "user", "message": "I uploaded a CSV of food"},
            {"role": "assistant", "message": "Posted 4 listings from your spreadsheet."},
        ],
        "u1",
    )
    assert args.get("delete_all") is True
    assert not args.get("delete_duplicates")
    assert len(args.get("listing_ids") or []) == 4


def test_build_confirmation_summary_delete_all():
    summary = _build_confirmation_summary("delete_listing", {
        "delete_all": True,
        "listing_ids": ["a", "b", "c"],
        "_bulk_delete_count": 3,
        "_delete_scope": "last_bulk",
    })
    assert "bulk" in summary.lower()
    assert "3" in summary
