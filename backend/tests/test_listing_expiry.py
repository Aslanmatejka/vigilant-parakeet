"""Tests for listing expiry normalization and AI post guards."""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from backend.tools import _create_food_listing, _normalize_expiry_date


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
