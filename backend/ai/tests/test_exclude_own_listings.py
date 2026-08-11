"""Own listings must never appear in Find Food / Nouri search results."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from backend.tools import _search_food_near_user


def test_search_excludes_callers_own_listings():
    me = "user-aaaa-bbbb-cccc-dddddddddddd"
    other = "user-zzzz-yyyy-xxxx-wwwwwwwwwwww"

    fake_user = [{
        "id": me,
        "latitude": 37.77,
        "longitude": -122.42,
        "address": "1 Market St, SF",
        "location": None,
        "community_id": 1,
        "is_admin": False,
    }]
    fake_listings = [
        {
            "id": "own-1",
            "title": "My Apples",
            "user_id": me,
            "community_id": 1,
            "status": "approved",
            "listing_type": "donation",
            "quantity": 5,
            "unit": "items",
            "latitude": 37.77,
            "longitude": -122.42,
            "expiry_date": None,
            "created_at": "2026-07-14T00:00:00+00:00",
        },
        {
            "id": "other-1",
            "title": "Neighbor Bread",
            "user_id": other,
            "community_id": 1,
            "status": "approved",
            "listing_type": "donation",
            "quantity": 2,
            "unit": "loaves",
            "latitude": 37.771,
            "longitude": -122.421,
            "expiry_date": None,
            "created_at": "2026-07-14T00:00:00+00:00",
        },
    ]

    captured = {}

    async def fake_get(table, params):
        if table == "users":
            return fake_user
        if table == "food_listings":
            captured["params"] = dict(params)
            # Simulate PostgREST neq by filtering client-side here when present.
            rows = list(fake_listings)
            neq = params.get("user_id") or ""
            if neq.startswith("neq."):
                exclude = neq[4:]
                rows = [r for r in rows if str(r.get("user_id")) != exclude]
            cid = params.get("community_id") or ""
            if cid.startswith("eq."):
                want = cid[3:]
                rows = [r for r in rows if str(r.get("community_id")) == want]
            elif cid.startswith("in.("):
                want = {x.strip() for x in cid[4:-1].split(",") if x.strip()}
                rows = [r for r in rows if str(r.get("community_id")) in want]
            return rows
        return []

    with patch("backend.ai_engine.supabase_get", new=AsyncMock(side_effect=fake_get)):
        with patch("backend.tools._listing_is_fresh_enough", return_value=True):
            out = asyncio.run(
                _search_food_near_user(user_id=me, max_results=20),
            )

    assert captured["params"].get("user_id") == f"neq.{me}"
    ids = [r["id"] for r in out.get("listings") or []]
    assert "own-1" not in ids
    assert "other-1" in ids
    assert all(not r.get("is_own_listing") for r in out["listings"])


def test_claim_rejects_own_listing():
    from backend.tools import _claim_food_listing

    me = "user-aaaa-bbbb-cccc-dddddddddddd"

    async def fake_get(table, params):
        if table == "food_listings":
            return [{
                "id": "own-1",
                "title": "My Apples",
                "user_id": me,
                "status": "approved",
                "listing_type": "donation",
                "quantity": 5,
            }]
        return []

    with patch("backend.ai_engine.supabase_get", new=AsyncMock(side_effect=fake_get)):
        out = asyncio.run(
            _claim_food_listing(user_id=me, listing_id="own-1", quantity=1),
        )

    assert out.get("success") is False
    assert out.get("error") == "own_listing"
