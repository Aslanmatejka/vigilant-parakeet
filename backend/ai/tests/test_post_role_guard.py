"""Tests for the recipient-role guard on post_food_listing."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from backend.ai.tools import execute_tool


def _fake_session_with_role(role_enum) -> MagicMock:
    """SessionLocal() stand-in whose User query yields a user with the
    given UserRole enum. The listing path is never reached for blocked
    roles, but we still wire enough to fail loudly if the guard misses."""
    user = MagicMock()
    user.id = 1
    user.role = role_enum
    user.coords_lat = 37.0
    user.coords_lng = -122.0
    user.address = "1 Test St"
    user.phone = "+15550000000"

    db = MagicMock()
    user_query = MagicMock()
    user_query.filter.return_value.first.return_value = user
    db.query.return_value = user_query
    return db


@pytest.mark.asyncio
async def test_recipient_account_cannot_post_listing():
    from backend.models import UserRole

    fake_db = _fake_session_with_role(UserRole.RECIPIENT)
    future = (datetime.utcnow() + timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%S")

    with patch("backend.app.SessionLocal", return_value=fake_db):
        r = await execute_tool(
            "post_food_listing",
            {
                "user_id": "1",
                "title": "Sourdough bread",
                "category": "bakery",
                "qty": 3,
                "pickup_window_end": future,
            },
        )

    assert isinstance(r, dict)
    assert "error" in r
    msg = r["error"].lower()
    assert "recipient" in msg
    assert "donor" in msg
    assert r.get("reason") == "wrong_role"
    assert r.get("required_role") == "donor"


@pytest.mark.asyncio
async def test_donor_account_can_post_listing_role_check():
    """Donor role must NOT be blocked by the role guard. The call may
    fail on later validation (mocked DB), but the failure reason must
    not be 'wrong_role'."""
    from backend.models import UserRole

    fake_db = _fake_session_with_role(UserRole.DONOR)
    future = (datetime.utcnow() + timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%S")

    with patch("backend.app.SessionLocal", return_value=fake_db):
        r = await execute_tool(
            "post_food_listing",
            {
                "user_id": "1",
                "title": "Sourdough bread",
                "category": "bakery",
                "qty": 3,
                "pickup_window_end": future,
            },
        )

    assert isinstance(r, dict)
    assert r.get("reason") != "wrong_role"
