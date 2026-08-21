"""Fulfilling a community food request locks donation community."""
from __future__ import annotations

import pytest

from backend.tools import _create_food_listing


@pytest.mark.asyncio
async def test_fulfilling_request_id_skips_community_confirm(monkeypatch):
    async def fake_from_request(rid):
        assert rid == "req-42"
        return ("comm-uuid", "Alameda Unified", "Bread")

    async def fake_resolve(name, cid):
        return cid or "comm-uuid", name or "Alameda Unified"

    posted = {}

    async def fake_post(table, row):
        posted["table"] = table
        posted["row"] = row
        return [{"id": "listing-1", **row}]

    async def fake_donor_defaults(_uid):
        return {"community_id": "other-comm", "full_address": "1 Main St"}

    def fake_apply_defaults(row, _donor):
        return row

    monkeypatch.setattr(
        "backend.tools._community_from_food_request", fake_from_request
    )
    monkeypatch.setattr("backend.tools._resolve_community", fake_resolve)
    monkeypatch.setattr(
        "backend.ai_engine.fetch_donor_listing_defaults", fake_donor_defaults
    )
    monkeypatch.setattr(
        "backend.ai_engine.apply_donor_defaults_to_listing", fake_apply_defaults
    )
    monkeypatch.setattr("backend.ai_engine.supabase_post", fake_post)
    monkeypatch.setattr(
        "backend.ai_engine._is_placeholder_address", lambda _a: False
    )

    # Avoid approval/status helpers depending on live settings.
    async def fake_status(_listing_type="donation"):
        return "approved"

    monkeypatch.setattr(
        "backend.tools._resolve_create_listing_status", fake_status
    )

    # Skip near-dup / geocode side paths if called.
    async def fake_find_dup(*_a, **_k):
        return None

    monkeypatch.setattr("backend.tools._find_recent_duplicate_listing", fake_find_dup)

    result = await _create_food_listing(
        user_id="user-1",
        title="Sourdough",
        quantity=2,
        unit="loaves",
        category="bakery",
        expiry_date="2099-12-31",
        community_confirmed=False,  # normally blocks — should be overridden
        fulfilling_request_id="req-42",
        image_url="https://example.com/sourdough.jpg",
    )

    assert result.get("success") is True
    assert posted["row"]["community_id"] == "comm-uuid"
    assert posted["row"]["listing_type"] == "donation"
