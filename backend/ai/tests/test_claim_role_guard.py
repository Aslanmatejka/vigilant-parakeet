"""Tests for the donor-role guard on claim_listing.

Uses lightweight mocks so we don't need a populated database — we just
need to verify the role check fires before any claim transition runs.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.ai.tools import execute_tool


class _FakeRole:
    def __init__(self, value: str):
        self.value = value


def _fake_session_with_role(role_value: str) -> MagicMock:
    """Return a SessionLocal() stand-in whose User query yields a user
    with the given role. update() returns 0 so that if the guard ever
    failed the call would still error out cleanly."""
    user = MagicMock()
    user.role = _FakeRole(role_value)
    user.id = 1
    user.phone = "+15550000000"

    db = MagicMock()
    user_query = MagicMock()
    user_query.filter.return_value.first.return_value = user
    listing_query = MagicMock()
    listing_query.filter.return_value.update.return_value = 0
    listing_query.filter.return_value.first.return_value = None

    def _query(model):
        from backend.models import FoodResource, User
        if model is User:
            return user_query
        if model is FoodResource:
            return listing_query
        return MagicMock()

    db.query.side_effect = _query
    return db


@pytest.mark.asyncio
async def test_donor_account_cannot_claim():
    fake_db = _fake_session_with_role("donor")
    with patch("backend.app.SessionLocal", return_value=fake_db):
        r = await execute_tool(
            "claim_listing",
            {"user_id": "1", "listing_id": 42},
        )

    assert isinstance(r, dict)
    assert "error" in r
    msg = r["error"].lower()
    assert "donor" in msg
    assert "recipient" in msg
    assert r.get("reason") == "wrong_role"
    assert r.get("required_role") == "recipient"
    # Guard must short-circuit BEFORE attempting the claim transition.
    assert not fake_db.commit.called


@pytest.mark.asyncio
async def test_recipient_account_passes_role_check():
    """Recipient role must NOT be blocked by the role guard.
    The call will fail later (no real listing in mock db), but the
    failure reason must not be 'wrong_role'."""
    fake_db = _fake_session_with_role("recipient")
    with patch("backend.app.SessionLocal", return_value=fake_db):
        r = await execute_tool(
            "claim_listing",
            {"user_id": "1", "listing_id": 42},
        )

    assert isinstance(r, dict)
    assert r.get("reason") != "wrong_role"
