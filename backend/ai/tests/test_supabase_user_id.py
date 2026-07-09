"""Tools must accept Supabase UUID user ids (not only integer PKs)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.ai.tools import (
    _cancel_claim,
    _claim_listing,
    _confirm_claim,
    _get_user_memory,
    _is_supabase_user_id,
    _save_user_memory,
    _update_user_profile,
)

UUID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"


class TestIsSupabaseUserId:
    def test_uuid_is_supabase(self):
        assert _is_supabase_user_id(UUID) is True

    def test_int_string_is_legacy(self):
        assert _is_supabase_user_id("42") is False


class TestSupabaseToolDelegation:
    @pytest.mark.asyncio
    async def test_update_user_profile_delegates(self):
        with patch(
            "backend.tools._update_user_profile",
            new_callable=AsyncMock,
            return_value={"success": True, "updated_fields": ["phone"]},
        ) as mock_impl:
            out = await _update_user_profile(UUID, phone="555-0100")
        assert out["success"] is True
        mock_impl.assert_awaited_once()
        assert mock_impl.await_args.kwargs["user_id"] == UUID

    @pytest.mark.asyncio
    async def test_cancel_claim_delegates(self):
        with patch(
            "backend.tools._cancel_claim",
            new_callable=AsyncMock,
            return_value={"success": True, "summary": "Released."},
        ) as mock_impl:
            out = await _cancel_claim(UUID, listing_id="listing-uuid")
        assert out["success"] is True
        mock_impl.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_confirm_claim_delegates(self):
        with patch(
            "backend.tools._confirm_claim",
            new_callable=AsyncMock,
            return_value={"success": True, "summary": "Pickup confirmed."},
        ) as mock_impl:
            out = await _confirm_claim(UUID, listing_id="listing-uuid", code="1234")
        assert out["success"] is True
        mock_impl.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_claim_listing_delegates_with_uuid_listing_id(self):
        listing_uuid = "d7cf24db-166e-4f6c-8cd5-076d7135784d"
        with patch(
            "backend.tools._claim_food_listing",
            new_callable=AsyncMock,
            return_value={
                "success": True,
                "listing_id": listing_uuid,
                "claim_id": "claim-uuid",
                "quantity": 1,
                "summary": "Claimed.",
                "title": "Tomatoes",
            },
        ) as mock_impl:
            out = await _claim_listing(UUID, listing_id=listing_uuid, quantity=1)
        assert out["success"] is True
        mock_impl.assert_awaited_once()
        assert mock_impl.await_args.kwargs["listing_id"] == listing_uuid

    @pytest.mark.asyncio
    async def test_save_user_memory_accepts_uuid(self):
        with patch("backend.ai.tools.asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(
                return_value={"saved": True, "key": "diet", "value": "vegan"}
            )
            out = await _save_user_memory(UUID, "diet", "vegan")
        assert out.get("saved") is True

    @pytest.mark.asyncio
    async def test_get_user_memory_accepts_uuid(self):
        with patch("backend.ai.tools.asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(
                return_value={"memories": []}
            )
            out = await _get_user_memory(UUID)
        assert "error" not in out or out.get("memories") == []
