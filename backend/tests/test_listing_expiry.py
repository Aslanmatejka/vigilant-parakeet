"""Tests for listing expiry normalization and AI post guards."""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from backend.tools import (
    _create_food_listing,
    _normalize_claim_quantity,
    _normalize_expiry_date,
)


class TestNormalizeExpiryDate:
    def test_iso_date_only(self):
        assert _normalize_expiry_date("2026-06-10") == "2026-06-10"

    def test_expiration_date_alias(self):
        assert _normalize_expiry_date(None, "2026-06-11") == "2026-06-11"

    def test_empty_returns_none(self):
        assert _normalize_expiry_date(None, "", "  ") is None


class TestCreateFoodListingExpiry:
    @pytest.mark.asyncio
    async def test_rejects_missing_expiry(self):
        with patch("backend.ai_engine.fetch_donor_listing_defaults", new=AsyncMock(return_value={})), \
             patch("backend.tools._resolve_community", new=AsyncMock(return_value=("c1", "Test Community"))):
            result = await _create_food_listing(
                user_id="user-1",
                title="Bread",
                quantity=2,
                unit="loaves",
                category="bakery",
                community_name="Test Community",
                community_confirmed=True,
                location="123 Main St",
            )
        assert result["success"] is False
        assert result["error"] == "expiry_date_required"

    @pytest.mark.asyncio
    async def test_accepts_expiration_date_alias(self):
        with patch("backend.ai_engine.fetch_donor_listing_defaults", new=AsyncMock(return_value={})), \
             patch("backend.tools._resolve_community", new=AsyncMock(return_value=("c1", "Test Community"))), \
             patch("backend.tools._forward_geocode", new=AsyncMock(return_value=(37.8, -122.2))), \
             patch("backend.ai_engine.supabase_post", new=AsyncMock(return_value=[{"id": "listing-1"}])):
            result = await _create_food_listing(
                user_id="user-1",
                title="Bread",
                quantity=2,
                unit="loaves",
                category="bakery",
                expiration_date="2026-06-12",
                community_name="Test Community",
                community_confirmed=True,
                location="123 Main St",
            )
        assert result["success"] is True
        assert result["expiry_date"] == "2026-06-12"


class TestNormalizeClaimQuantity:
    """Regression tests for `_normalize_claim_quantity`. The original inline
    `int(quantity) if quantity is not None else 1` swallowed every non-numeric
    string (including "all" / "everything") as 1, so users asking to claim
    every available loaf silently got a single-loaf claim."""

    def test_none_defaults_to_full_quantity(self):
        # Mutual-aid default: when the AI omits quantity (e.g. user said
        # "yes please" without a number), claim the whole listing instead
        # of silently grabbing 1 unit out of N.
        assert _normalize_claim_quantity(None, 10) == (10, False)

    def test_native_int_within_range(self):
        assert _normalize_claim_quantity(3, 10) == (3, False)

    def test_native_int_clamped_returns_flag(self):
        assert _normalize_claim_quantity(99, 5) == (5, True)

    def test_negative_int_becomes_one(self):
        assert _normalize_claim_quantity(-2, 10) == (1, False)

    def test_zero_becomes_one(self):
        assert _normalize_claim_quantity(0, 10) == (1, False)

    def test_float_truncates_to_int(self):
        assert _normalize_claim_quantity(2.7, 10) == (2, False)

    def test_string_integer(self):
        assert _normalize_claim_quantity("5", 10) == (5, False)

    def test_string_with_unit_extracts_leading_int(self):
        assert _normalize_claim_quantity("5 loaves", 10) == (5, False)

    def test_string_with_unit_clamped(self):
        assert _normalize_claim_quantity("99 loaves", 5) == (5, True)

    def test_all_keyword_takes_available(self):
        assert _normalize_claim_quantity("all", 7) == (7, False)

    def test_everything_keyword_takes_available(self):
        assert _normalize_claim_quantity("everything", 4) == (4, False)

    def test_spanish_all_keyword_takes_available(self):
        assert _normalize_claim_quantity("todo", 6) == (6, False)
        assert _normalize_claim_quantity("todas", 3) == (3, False)

    def test_empty_string_defaults_to_one(self):
        assert _normalize_claim_quantity("", 10) == (1, False)
        assert _normalize_claim_quantity("   ", 10) == (1, False)

    def test_garbage_string_defaults_to_one(self):
        assert _normalize_claim_quantity("xyz", 10) == (1, False)

    def test_bool_rejected_not_treated_as_int(self):
        # bool is a subclass of int in Python — explicitly reject so
        # `quantity=True` doesn't become 1 via the int path silently.
        assert _normalize_claim_quantity(True, 10) == (1, False)

    def test_available_zero_returns_one(self):
        # Defensive: caller already short-circuits when available <= 0,
        # but the helper must not return 0 either way.
        assert _normalize_claim_quantity(5, 0) == (1, False)
