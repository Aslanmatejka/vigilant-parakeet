"""Validation tests for post_food_listing.

These exercise the parts that reject BEFORE touching the database (timestamp
sanity checks). The `_sync()` location-required path needs a real DB so it is
covered separately by the integration suite.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from backend.ai.tools import execute_tool


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


@pytest.mark.asyncio
class TestPostListingTimestampValidation:
    async def test_past_pickup_window_end_rejected(self):
        past = datetime.utcnow() - timedelta(days=1)
        r = await execute_tool("post_food_listing", {
            "user_id": "1",
            "title": "Test bread",
            "category": "bakery",
            "qty": 5,
            "pickup_window_end": _iso(past),
        })
        assert isinstance(r, dict) and "error" in r
        assert "past" in r["error"].lower()

    async def test_past_expiration_date_rejected(self):
        past = datetime.utcnow() - timedelta(hours=2)
        r = await execute_tool("post_food_listing", {
            "user_id": "1",
            "title": "Old milk",
            "category": "packaged",
            "qty": 1,
            "expiration_date": _iso(past),
        })
        assert isinstance(r, dict) and "error" in r
        assert "past" in r["error"].lower()

    async def test_window_start_after_end_rejected(self):
        now = datetime.utcnow()
        r = await execute_tool("post_food_listing", {
            "user_id": "1",
            "title": "Reverse window",
            "category": "produce",
            "qty": 2,
            "pickup_window_start": _iso(now + timedelta(hours=10)),
            "pickup_window_end": _iso(now + timedelta(hours=2)),
        })
        assert isinstance(r, dict) and "error" in r
        assert "before" in r["error"].lower()

    async def test_invalid_iso_rejected(self):
        r = await execute_tool("post_food_listing", {
            "user_id": "1",
            "title": "Bad date",
            "category": "produce",
            "qty": 2,
            "pickup_window_end": "not-a-date",
        })
        assert isinstance(r, dict) and "error" in r
