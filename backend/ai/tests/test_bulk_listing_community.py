"""Photo/CSV bulk listings must persist the preview community picker."""
from __future__ import annotations

from backend.ai.routes import BulkListingItem, _normalize_listing_row


class TestBulkListingCommunityPersistence:
    def test_model_accepts_community_id(self):
        item = BulkListingItem(
            title="Mangoes",
            quantity=1,
            unit="basket",
            category="produce",
            community_id="8",
        )
        assert item.community_id == "8"

    def test_normalize_keeps_picker_community_over_donor_default(self):
        item = BulkListingItem(
            title="Mangoes",
            quantity=1,
            unit="basket",
            category="produce",
            community_id=8,
            expiry_date="2099-01-01",
        )
        donor = {"community_id": 1, "address": "1423 Park St, Alameda, CA"}
        row = _normalize_listing_row(item, "user-1", donor=donor)
        assert row.get("community_id") == 8

    def test_normalize_falls_back_to_donor_community_when_picker_empty(self):
        item = BulkListingItem(
            title="Mangoes",
            quantity=1,
            unit="basket",
            category="produce",
            expiry_date="2099-01-01",
        )
        donor = {"community_id": 1}
        row = _normalize_listing_row(item, "user-1", donor=donor)
        assert row.get("community_id") == 1

    def test_normalize_pending_name_does_not_inherit_donor_warehouse(self):
        item = BulkListingItem(
            title="Oranges",
            quantity=3,
            unit="bags",
            category="produce",
            community_name="Some School",
            expiry_date="2099-01-01",
        )
        donor = {"community_id": 1, "address": "1 Main St"}
        row = _normalize_listing_row(item, "user-1", donor=donor)
        assert row.get("community_id") is None
        assert row.get("_community_name_pending") == "Some School"

    def test_normalize_accepts_string_community_id(self):
        item = BulkListingItem(
            title="Carrots",
            quantity=1,
            unit="basket",
            category="produce",
            community_id="12",
            expiry_date="2099-01-01",
        )
        row = _normalize_listing_row(item, "user-1", donor={"community_id": 1})
        assert row.get("community_id") == 12

    def test_normalize_accepts_pending_status(self):
        item = BulkListingItem(
            title="Mangoes",
            quantity=1,
            unit="basket",
            category="produce",
            expiry_date="2099-01-01",
        )
        row = _normalize_listing_row(item, "user-1", donor={}, status="pending")
        assert row["status"] == "pending"
