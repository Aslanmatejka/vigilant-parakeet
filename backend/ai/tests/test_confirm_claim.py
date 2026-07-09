"""Tests for the confirm_claim AI tool."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from backend.ai.tools import execute_tool


@pytest.mark.asyncio
class TestConfirmClaimValidation:
    async def test_invalid_user_id_rejected(self):
        r = await execute_tool("confirm_claim", {"user_id": "abc", "listing_id": 1, "code": "1234"})
        assert "error" in r

    async def test_missing_code_rejected(self):
        r = await execute_tool("confirm_claim", {"user_id": "1", "listing_id": 1, "code": ""})
        assert "error" in r and "code" in r["error"].lower()

    async def test_no_pending_confirmation_rejected(self):
        # Use a listing id that almost certainly has no pending confirmation.
        from backend.app import pending_confirmations
        pending_confirmations.pop(99999, None)
        r = await execute_tool("confirm_claim", {"user_id": "1", "listing_id": 99999, "code": "1234"})
        assert "error" in r

    async def test_wrong_code_rejected(self):
        from backend.app import pending_confirmations
        pending_confirmations[99998] = {
            "code": "9999",
            "recipient_id": 1,
            "expires_at": datetime.utcnow() + timedelta(minutes=5),
        }
        try:
            r = await execute_tool("confirm_claim", {"user_id": "1", "listing_id": 99998, "code": "0000"})
            assert "error" in r and "invalid" in r["error"].lower()
        finally:
            pending_confirmations.pop(99998, None)

    async def test_wrong_recipient_rejected(self):
        from backend.app import pending_confirmations
        pending_confirmations[99997] = {
            "code": "1234",
            "recipient_id": 1,
            "expires_at": datetime.utcnow() + timedelta(minutes=5),
        }
        try:
            r = await execute_tool("confirm_claim", {"user_id": "2", "listing_id": 99997, "code": "1234"})
            assert "error" in r
        finally:
            pending_confirmations.pop(99997, None)

    async def test_expired_code_rejected(self):
        from backend.app import pending_confirmations
        pending_confirmations[99996] = {
            "code": "1234",
            "recipient_id": 1,
            "expires_at": datetime.utcnow() - timedelta(seconds=1),
        }
        try:
            r = await execute_tool("confirm_claim", {"user_id": "1", "listing_id": 99996, "code": "1234"})
            assert "error" in r and "expired" in r["error"].lower()
            assert 99996 not in pending_confirmations
        finally:
            pending_confirmations.pop(99996, None)
