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
        # Far-past calendar day (not off-by-one) must still be rejected.
        past = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
        r = await execute_tool("post_food_listing", {
            "user_id": "1",
            "title": "Old milk",
            "category": "packaged",
            "qty": 1,
            "expiration_date": past,
            "images": ["https://example.com/milk.jpg"],
            "community_confirmed": True,
            "community_name": "Test Community",
        })
        assert isinstance(r, dict) and "error" in r
        assert "past" in r["error"].lower()

    async def test_date_only_today_is_coerced_not_rejected(self):
        """Made-today style expiry=today must not bounce as 'already past'."""
        from backend.ai.conversation_flow import normalize_expiration_date_for_post
        from datetime import date, timedelta

        today = date.today().isoformat()
        coerced = normalize_expiration_date_for_post(today)
        assert coerced == (date.today() + timedelta(days=1)).isoformat()
        r = await execute_tool("post_food_listing", {
            "user_id": "1",
            "title": "Fresh pizza",
            "category": "prepared",
            "qty": 10,
            "expiration_date": today,
            "images": ["https://example.com/pizza.jpg"],
        })
        # Should get past the timestamp gate (photo/community may still block).
        assert isinstance(r, dict)
        err = str(r.get("error") or r.get("message") or "").lower()
        assert "past" not in err or "expiration" not in err
        assert "expiration_date is in the past" not in str(r.get("error") or "")

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
