"""Tests for the 'update <listing> add a photo' → attach_photos_to_listing route.

The user reported that saying 'update oranges add a photo' or 'add new photo'
was confusing Nouri. The fix is a two-tier guard:
  * A detector (`donor_photo_add_intent`) that recognizes photo-add intent
    in a donor context and resolves the target listing.
  * A block-reason (`update_photo_intent_block_reason`) that reroutes
    misdirected `update_food_listing` calls to `attach_photos_to_listing`.
"""
from __future__ import annotations

from backend.ai.conversation_flow import (
    donor_photo_add_intent,
    set_last_donor_listings,
    update_photo_intent_block_reason,
)


class TestPhotoAddDetection:
    def test_add_a_photo_is_intent(self):
        set_last_donor_listings("u-donor", [{"id": "L-1", "title": "Fresh Oranges"}])
        out = donor_photo_add_intent(
            "update oranges add a photo",
            [],
            "u-donor",
        )
        assert out is not None
        assert out.get("listing_id") == "L-1"
        assert out.get("has_photo_url") is False

    def test_add_new_photo_variant(self):
        set_last_donor_listings("u-donor2", [{"id": "L-9", "title": "Sourdough Bread"}])
        out = donor_photo_add_intent(
            "please add new photo to my bread listing",
            [],
            "u-donor2",
        )
        assert out is not None
        assert out.get("listing_id") == "L-9"

    def test_upload_a_picture_variant(self):
        set_last_donor_listings("u-donor3", [{"id": "L-3", "title": "Fresh Apples"}])
        out = donor_photo_add_intent(
            "upload a picture for my apples",
            [],
            "u-donor3",
        )
        assert out is not None
        assert out.get("listing_id") == "L-3"

    def test_photo_url_from_history_is_detected(self):
        set_last_donor_listings("u-donor4", [{"id": "L-4", "title": "Fresh Kale"}])
        history = [
            {"role": "user", "message": "image: /uploads/ai/abc.jpg"},
        ]
        out = donor_photo_add_intent(
            "add a photo to my kale listing",
            history,
            "u-donor4",
        )
        assert out is not None
        assert out.get("has_photo_url") is True
        assert out.get("photo_url", "").endswith("abc.jpg")

    def test_spanish_variant(self):
        set_last_donor_listings("u-esp", [{"id": "L-5", "title": "Manzanas"}])
        out = donor_photo_add_intent(
            "agregar una foto a mis manzanas",
            [],
            "u-esp",
        )
        assert out is not None
        assert out.get("listing_id") == "L-5"

    def test_no_intent_when_no_photo_verb(self):
        set_last_donor_listings("u-none", [{"id": "L-6", "title": "Rice"}])
        out = donor_photo_add_intent(
            "change the price on my rice",
            [],
            "u-none",
        )
        assert out is None


class TestUpdatePhotoIntentBlock:
    def test_route_to_attach_when_url_missing(self):
        set_last_donor_listings("u-blk", [{"id": "L-1", "title": "Fresh Oranges"}])
        reason = update_photo_intent_block_reason(
            "update_food_listing",
            {"user_id": "u-blk", "listing_id": "L-1"},
            "update oranges add a photo",
            [],
            "u-blk",
        )
        assert reason is not None
        assert "attach_photos_to_listing" in reason
        # Asking donor to upload the photo first.
        assert "upload" in reason.lower() or "image" in reason.lower()

    def test_route_to_attach_when_url_present(self):
        set_last_donor_listings("u-blk2", [{"id": "L-2", "title": "Bread"}])
        history = [
            {"role": "user", "message": "image: /uploads/ai/x.jpg"},
        ]
        reason = update_photo_intent_block_reason(
            "update_food_listing",
            {"user_id": "u-blk2", "listing_id": "L-2"},
            "please add a new photo to my bread",
            history,
            "u-blk2",
        )
        assert reason is not None
        assert "attach_photos_to_listing" in reason
        assert "L-2" in reason

    def test_no_block_on_price_update(self):
        set_last_donor_listings("u-nb", [{"id": "L-1", "title": "Rice"}])
        reason = update_photo_intent_block_reason(
            "update_food_listing",
            {"user_id": "u-nb", "listing_id": "L-1", "quantity": 5},
            "change quantity on my rice to 5",
            [],
            "u-nb",
        )
        assert reason is None

    def test_no_block_for_non_update_tool(self):
        set_last_donor_listings("u-nb2", [{"id": "L-1", "title": "Rice"}])
        reason = update_photo_intent_block_reason(
            "delete_listing",
            {"user_id": "u-nb2", "listing_id": "L-1"},
            "delete my rice and add a photo",
            [],
            "u-nb2",
        )
        assert reason is None
