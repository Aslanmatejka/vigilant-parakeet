"""CSV parse must keep per-row community so imports do not leak across schools."""
from __future__ import annotations

from backend.ai.routes import BulkListingItem, _normalize_listing_row
from backend.tools import _normalize_bulk_row


class TestNormalizeBulkRowCommunity:
    def test_keeps_numeric_community_id(self):
        row = _normalize_bulk_row(
            {
                "title": "Apples",
                "quantity": 5,
                "unit": "lbs",
                "category": "produce",
                "community_id": "8",
            },
            "user-1",
        )
        assert row is not None
        assert row.get("community_id") == 8

    def test_keeps_community_name_for_later_resolve(self):
        row = _normalize_bulk_row(
            {
                "title": "Bread",
                "quantity": 2,
                "unit": "loaves",
                "category": "bakery",
                "community": "Alameda High",
            },
            "user-1",
        )
        assert row is not None
        assert row.get("_community_name") == "Alameda High"
        assert row.get("community_id") is None

    def test_school_alias_maps_to_community_name(self):
        row = _normalize_bulk_row(
            {
                "title": "Rice",
                "qty": 10,
                "unit": "bags",
                "category": "pantry",
                "school": "Ruby Bridges",
            },
            "user-1",
        )
        assert row is not None
        assert row.get("_community_name") == "Ruby Bridges"


class TestBulkListingNormalizePendingName:
    def test_pending_community_name_skips_donor_warehouse(self):
        item = BulkListingItem(
            title="Mangoes",
            quantity=1,
            unit="basket",
            category="produce",
            community_name="School B",
            expiry_date="2099-01-01",
        )
        donor = {"community_id": 1, "address": "1423 Park St, Alameda, CA"}
        row = _normalize_listing_row(item, "user-1", donor=donor)
        assert row.get("community_id") is None
        assert row.get("_community_name_pending") == "School B"

    def test_explicit_community_id_beats_donor(self):
        item = BulkListingItem(
            title="Mangoes",
            quantity=1,
            unit="basket",
            category="produce",
            community_id=12,
            expiry_date="2099-01-01",
        )
        donor = {"community_id": 1}
        row = _normalize_listing_row(item, "user-1", donor=donor)
        assert row.get("community_id") == 12
        assert "_community_name_pending" not in row
