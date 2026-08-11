"""Listing approval gate: pending create + Nouri summary copy."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.tools import (
    _create_food_listing,
    _get_user_listings,
    _require_listing_approval,
    _resolve_create_listing_status,
)


class TestRequireListingApproval:
    @pytest.mark.asyncio
    async def test_true_when_setting_true(self):
        with patch(
            "backend.ai_engine.supabase_get",
            new=AsyncMock(return_value=[{"value": True}]),
        ):
            assert await _require_listing_approval() is True

    @pytest.mark.asyncio
    async def test_false_when_setting_false(self):
        with patch(
            "backend.ai_engine.supabase_get",
            new=AsyncMock(return_value=[{"value": False}]),
        ):
            assert await _require_listing_approval() is False

    @pytest.mark.asyncio
    async def test_defaults_true_when_missing(self):
        with patch(
            "backend.ai_engine.supabase_get",
            new=AsyncMock(return_value=[]),
        ):
            assert await _require_listing_approval() is True


class TestCreateFoodListingApproval:
    @pytest.mark.asyncio
    async def test_creates_pending_when_approval_required(self):
        posted = {}

        async def _capture_post(table, row):
            posted["row"] = row
            return [{"id": "listing-pending-1"}]

        with patch("backend.ai_engine.fetch_donor_listing_defaults", new=AsyncMock(return_value={})), \
             patch("backend.tools._resolve_community", new=AsyncMock(return_value=("c1", "Test Community"))), \
             patch("backend.tools._resolve_create_listing_status", new=AsyncMock(return_value="pending")), \
             patch("backend.tools._find_recent_duplicate_listing", new=AsyncMock(return_value=None)), \
             patch("backend.tools._forward_geocode", new=AsyncMock(return_value=(37.8, -122.2))), \
             patch("backend.ai_engine.supabase_post", new=AsyncMock(side_effect=_capture_post)):
            result = await _create_food_listing(
                user_id="user-1",
                title="Sourdough",
                quantity=2,
                unit="loaves",
                category="bakery",
                expiry_date="2099-06-12",
                community_name="Test Community",
                community_confirmed=True,
                location="123 Main St, Alameda, CA",
            )

        assert result["success"] is True
        assert result["status"] == "pending"
        assert result["awaiting_approval"] is True
        assert "awaiting admin approval" in result["summary"].lower()
        assert "wait for admin approval" in result["summary"].lower()
        assert "live on the map" not in result["summary"].lower()
        assert posted["row"]["status"] == "pending"

    @pytest.mark.asyncio
    async def test_creates_approved_when_approval_off(self):
        posted = {}

        async def _capture_post(table, row):
            posted["row"] = row
            return [{"id": "listing-live-1"}]

        with patch("backend.ai_engine.fetch_donor_listing_defaults", new=AsyncMock(return_value={})), \
             patch("backend.tools._resolve_community", new=AsyncMock(return_value=("c1", "Test Community"))), \
             patch("backend.tools._resolve_create_listing_status", new=AsyncMock(return_value="approved")), \
             patch("backend.tools._find_recent_duplicate_listing", new=AsyncMock(return_value=None)), \
             patch("backend.tools._forward_geocode", new=AsyncMock(return_value=(37.8, -122.2))), \
             patch("backend.ai_engine.supabase_post", new=AsyncMock(side_effect=_capture_post)):
            result = await _create_food_listing(
                user_id="user-1",
                title="Apples",
                quantity=5,
                unit="lbs",
                category="produce",
                expiry_date="2099-06-12",
                community_name="Test Community",
                community_confirmed=True,
                location="123 Main St, Alameda, CA",
            )

        assert result["success"] is True
        assert result["status"] == "approved"
        assert result["awaiting_approval"] is False
        assert "live on the map" in result["summary"].lower()
        assert posted["row"]["status"] == "approved"


class TestGetUserListingsIncludesPending:
    @pytest.mark.asyncio
    async def test_default_filter_includes_pending(self):
        captured = {}

        async def _fake_get(table, params):
            if table == "food_listings":
                captured["params"] = params
                return [
                    {
                        "id": "a",
                        "title": "Bread",
                        "quantity": 1,
                        "unit": "loaf",
                        "category": "bakery",
                        "status": "pending",
                        "expiry_date": "2099-01-01",
                    }
                ]
            return []

        with patch("backend.ai_engine.supabase_get", new=AsyncMock(side_effect=_fake_get)):
            result = await _get_user_listings(user_id="user-1")

        assert result["success"] is True
        assert "pending" in captured["params"]["status"]
        assert "awaiting approval" in result["summary"].lower()


class TestResolveCreateStatus:
    @pytest.mark.asyncio
    async def test_maps_require_flag(self):
        with patch("backend.tools._require_listing_approval", new=AsyncMock(return_value=True)):
            assert await _resolve_create_listing_status() == "pending"
        with patch("backend.tools._require_listing_approval", new=AsyncMock(return_value=False)):
            assert await _resolve_create_listing_status() == "approved"
