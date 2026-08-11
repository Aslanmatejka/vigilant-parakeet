"""Food request create status + claim rejection."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.tools import (
    _claim_food_listing,
    _create_food_request,
    _require_request_approval,
    _resolve_create_listing_status,
)


class TestRequireRequestApproval:
    @pytest.mark.asyncio
    async def test_true_when_setting_true(self):
        with patch(
            "backend.ai_engine.supabase_get",
            new=AsyncMock(return_value=[{"value": True}]),
        ):
            assert await _require_request_approval() is True

    @pytest.mark.asyncio
    async def test_false_when_setting_false(self):
        with patch(
            "backend.ai_engine.supabase_get",
            new=AsyncMock(return_value=[{"value": False}]),
        ):
            assert await _require_request_approval() is False

    @pytest.mark.asyncio
    async def test_defaults_true_when_missing(self):
        with patch(
            "backend.ai_engine.supabase_get",
            new=AsyncMock(return_value=[]),
        ):
            assert await _require_request_approval() is True


class TestResolveCreateStatusByType:
    @pytest.mark.asyncio
    async def test_request_uses_request_flag(self):
        with patch("backend.tools._require_request_approval", new=AsyncMock(return_value=True)), \
             patch("backend.tools._require_listing_approval", new=AsyncMock(return_value=False)):
            assert await _resolve_create_listing_status("request") == "pending"
        with patch("backend.tools._require_request_approval", new=AsyncMock(return_value=False)), \
             patch("backend.tools._require_listing_approval", new=AsyncMock(return_value=True)):
            assert await _resolve_create_listing_status("request") == "approved"

    @pytest.mark.asyncio
    async def test_donation_uses_listing_flag(self):
        with patch("backend.tools._require_listing_approval", new=AsyncMock(return_value=True)), \
             patch("backend.tools._require_request_approval", new=AsyncMock(return_value=False)):
            assert await _resolve_create_listing_status("donation") == "pending"
        with patch("backend.tools._require_listing_approval", new=AsyncMock(return_value=False)), \
             patch("backend.tools._require_request_approval", new=AsyncMock(return_value=True)):
            assert await _resolve_create_listing_status() == "approved"


class TestCreateFoodRequestApproval:
    @pytest.mark.asyncio
    async def test_creates_pending_when_request_approval_required(self):
        posted = {}

        async def _capture_post(table, row):
            posted["row"] = row
            return [{"id": "request-pending-1", **row}]

        with patch("backend.ai_engine.fetch_donor_listing_defaults", new=AsyncMock(return_value={})), \
             patch("backend.tools._resolve_community", new=AsyncMock(return_value=("c1", "Test Community"))), \
             patch("backend.tools._resolve_create_listing_status", new=AsyncMock(return_value="pending")) as resolve_mock, \
             patch("backend.tools._find_recent_duplicate_listing", new=AsyncMock(return_value=None)), \
             patch("backend.tools._forward_geocode", new=AsyncMock(return_value=None)), \
             patch("backend.ai_engine.apply_donor_defaults_to_listing", new=lambda row, *_a, **_k: row), \
             patch("backend.ai_engine.supabase_post", new=AsyncMock(side_effect=_capture_post)), \
             patch("backend.ai_engine.supabase_get", new=AsyncMock(return_value=[])):
            result = await _create_food_request(
                user_id="user-1",
                title="Looking for rice",
                category="pantry",
                quantity=2,
                unit="bags",
                community_name="Test Community",
            )

        resolve_mock.assert_awaited()
        assert resolve_mock.await_args.args[0] == "request"
        assert result["success"] is True
        assert result.get("awaiting_approval") is True
        assert posted["row"]["listing_type"] == "request"
        assert posted["row"]["status"] == "pending"

    @pytest.mark.asyncio
    async def test_creates_approved_when_request_approval_off(self):
        posted = {}

        async def _capture_post(table, row):
            posted["row"] = row
            return [{"id": "request-live-1", **row}]

        with patch("backend.ai_engine.fetch_donor_listing_defaults", new=AsyncMock(return_value={})), \
             patch("backend.tools._resolve_community", new=AsyncMock(return_value=("c1", "Test Community"))), \
             patch("backend.tools._resolve_create_listing_status", new=AsyncMock(return_value="approved")), \
             patch("backend.tools._find_recent_duplicate_listing", new=AsyncMock(return_value=None)), \
             patch("backend.tools._forward_geocode", new=AsyncMock(return_value=None)), \
             patch("backend.ai_engine.apply_donor_defaults_to_listing", new=lambda row, *_a, **_k: row), \
             patch("backend.ai_engine.supabase_post", new=AsyncMock(side_effect=_capture_post)), \
             patch("backend.ai_engine.supabase_get", new=AsyncMock(return_value=[])):
            result = await _create_food_request(
                user_id="user-1",
                title="Looking for milk",
                category="dairy",
                community_name="Test Community",
            )

        assert result["success"] is True
        assert result.get("awaiting_approval") is False
        assert posted["row"]["status"] == "approved"
        assert posted["row"]["listing_type"] == "request"


class TestClaimRejectsFoodRequest:
    @pytest.mark.asyncio
    async def test_claim_food_listing_rejects_request_type(self):
        async def _fake_get(table, params):
            if table == "food_listings":
                return [{
                    "id": "req-1",
                    "user_id": "donor-1",
                    "title": "Need bread",
                    "listing_type": "request",
                    "status": "approved",
                    "quantity": 1,
                    "unit": "loaf",
                }]
            return []

        with patch("backend.ai_engine.supabase_get", new=AsyncMock(side_effect=_fake_get)):
            result = await _claim_food_listing(
                user_id="claimer-1",
                listing_id="req-1",
            )

        assert result["success"] is False
        assert "request" in str(result.get("error") or "").lower()

    @pytest.mark.asyncio
    async def test_claim_rejects_malformed_listing_id(self):
        result = await _claim_food_listing(
            user_id="claimer-1",
            listing_id="bad,id",
        )
        assert result["success"] is False
        assert result.get("error") == "invalid listing_id"
