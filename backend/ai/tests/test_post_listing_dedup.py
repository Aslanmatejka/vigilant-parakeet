"""Duplicate-post guard for Supabase create_food_listing."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.tools import _create_food_listing


@pytest.mark.asyncio
async def test_duplicate_post_returns_existing_without_second_insert():
    existing = {
        "id": "abc-123",
        "title": "Rice",
        "quantity": 10,
        "unit": "lbs",
        "image_url": "https://example.com/old.jpg",
        "full_address": "1423 Park St",
        "latitude": 1.0,
        "longitude": 2.0,
        "community_id": "8",
        "expiry_date": "2026-07-08",
    }
    with patch(
        "backend.tools._find_recent_duplicate_listing",
        new_callable=AsyncMock,
        return_value=existing,
    ), patch(
        "backend.tools._resolve_community",
        new_callable=AsyncMock,
        return_value=("8", "Alameda Unified"),
    ), patch(
        "backend.ai_engine.fetch_donor_listing_defaults",
        new_callable=AsyncMock,
        return_value={"community_id": "8", "address": "1423 Park St"},
    ), patch("backend.ai_engine.supabase_post", new_callable=AsyncMock) as mock_post:
        result = await _create_food_listing(
            user_id="user-uuid",
            title="Rice",
            quantity=10,
            unit="lbs",
            category="other",
            location="1423 Park St",
            community_id="8",
            community_confirmed=True,
            image_url="https://example.com/old.jpg",
            expiry_date="2026-07-08",
        )
    assert result["success"] is True
    assert result["duplicate_of_recent"] is True
    assert result["listing_id"] == "abc-123"
    mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_duplicate_post_merges_photo_instead_of_new_listing():
    existing = {
        "id": "abc-123",
        "title": "Rice",
        "quantity": 10,
        "unit": "lbs",
        "image_url": None,
        "full_address": "1423 Park St",
        "latitude": 1.0,
        "longitude": 2.0,
        "community_id": "8",
        "expiry_date": "2026-07-08",
    }
    with patch(
        "backend.tools._find_recent_duplicate_listing",
        new_callable=AsyncMock,
        return_value=existing,
    ), patch(
        "backend.tools._resolve_community",
        new_callable=AsyncMock,
        return_value=("8", "Alameda Unified"),
    ), patch(
        "backend.ai_engine.fetch_donor_listing_defaults",
        new_callable=AsyncMock,
        return_value={"community_id": "8", "address": "1423 Park St"},
    ), patch(
        "backend.ai_engine.supabase_patch",
        new_callable=AsyncMock,
    ) as mock_patch, patch("backend.ai_engine.supabase_post", new_callable=AsyncMock) as mock_post:
        result = await _create_food_listing(
            user_id="user-uuid",
            title="Rice",
            quantity=10,
            unit="lbs",
            category="other",
            location="1423 Park St",
            community_id="8",
            community_confirmed=True,
            image_url="https://example.com/new.jpg",
            expiry_date="2026-07-08",
        )
    assert result["success"] is True
    assert result.get("photo_merged") is True
    mock_patch.assert_awaited_once()
    mock_post.assert_not_called()
