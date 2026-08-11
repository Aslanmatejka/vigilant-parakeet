"""Community-scoped Find Food / Nouri search."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from backend.tools import (
    _get_community_listings,
    _get_recent_listings,
    _search_food_near_user,
)


def _listing(lid, title, user_id, community_id, lat=37.77, lng=-122.42):
    return {
        "id": lid,
        "title": title,
        "user_id": user_id,
        "community_id": community_id,
        "status": "approved",
        "listing_type": "donation",
        "quantity": 5,
        "unit": "items",
        "latitude": lat,
        "longitude": lng,
        "expiry_date": None,
        "created_at": "2026-07-14T00:00:00+00:00",
        "full_address": "1 Market St",
        "category": "produce",
    }


async def _run_search(fake_get, user_id):
    with patch("backend.ai_engine.supabase_get", new=AsyncMock(side_effect=fake_get)), \
         patch("backend.tools._forward_geocode", new=AsyncMock(return_value=None)), \
         patch("backend.tools._listing_is_fresh_enough", return_value=True):
        return await _search_food_near_user(user_id=user_id, max_results=25)


def test_search_ignores_legacy_radius_km_arg():
    """Passing radius_km must not drop far same-community listings."""
    me = "user-school-a"
    other = "user-other"

    fake_user = [{
        "id": me,
        "latitude": 37.77,
        "longitude": -122.42,
        "address": "1 Market St, SF",
        "location": None,
        "community_id": 8,
        "is_admin": False,
    }]
    # ~80+ km from user coords
    far = _listing("very-far", "Far Apples", other, 8, lat=38.6, lng=-121.5)

    async def fake_get(table, params=None):
        if table == "users":
            return fake_user
        return [far]

    async def _run():
        with patch("backend.ai_engine.supabase_get", new=AsyncMock(side_effect=fake_get)), \
             patch("backend.tools._forward_geocode", new=AsyncMock(return_value=None)), \
             patch("backend.tools._listing_is_fresh_enough", return_value=True):
            # Tiny radius would have excluded this listing before; must still return.
            return await _search_food_near_user(
                user_id=me, max_results=25, radius_km=1,
            )

    result = asyncio.run(_run())
    ids = {row["id"] for row in result["listings"]}
    assert "very-far" in ids
    assert result.get("radius_km") is None


def test_search_includes_community_listings_without_coords():
    """Scoped users must see all community food even without lat/lng."""
    me = "user-school-a"
    other = "user-other"

    fake_user = [{
        "id": me,
        "latitude": 37.77,
        "longitude": -122.42,
        "address": "1 Market St, SF",
        "location": None,
        "community_id": 8,
        "is_admin": False,
    }]
    fake_listings = [
        _listing("with-coords", "Apples", other, 8, lat=37.77, lng=-122.42),
        {
            **_listing("no-coords", "Bread", other, 8),
            "latitude": None,
            "longitude": None,
        },
        _listing("far-same-school", "Rice", other, 8, lat=38.5, lng=-122.0),
    ]

    async def fake_get(table, params=None):
        if table == "users":
            return fake_user
        return fake_listings

    # Far listings in the same community must still appear (no radius cutoff).
    result = asyncio.run(_run_search(fake_get, me))
    ids = {row["id"] for row in result["listings"]}
    assert "with-coords" in ids
    assert "no-coords" in ids
    assert "far-same-school" in ids


def test_search_scopes_to_user_community_only():
    me = "user-school-a"
    other = "user-other"

    fake_user = [{
        "id": me,
        "latitude": 37.77,
        "longitude": -122.42,
        "address": "1 Market St, SF",
        "location": None,
        "community_id": 8,
        "is_admin": False,
    }]
    fake_listings = [
        _listing("own-school", "School A Apples", other, 8),
        _listing("other-school", "School B Bread", other, 12),
        _listing("warehouse", "Warehouse Rice", other, 1),
    ]

    async def fake_get(table, params=None):
        if table == "users":
            return fake_user
        assert "community_id" in (params or {})
        assert params["community_id"] == "eq.8"
        allowed = {"8"}
        return [r for r in fake_listings if str(r["community_id"]) in allowed]

    result = asyncio.run(_run_search(fake_get, me))
    ids = {row["id"] for row in result["listings"]}
    assert "own-school" in ids
    assert "warehouse" not in ids
    assert "other-school" not in ids


def test_search_post_fetch_drops_out_of_scope_rows():
    """Defense in depth: even if DB returns another school, drop it."""
    me = "user-school-a"
    other = "user-other"

    fake_user = [{
        "id": me,
        "latitude": 37.77,
        "longitude": -122.42,
        "address": "1 Market St, SF",
        "location": None,
        "community_id": 8,
        "is_admin": False,
    }]
    fake_listings = [
        _listing("own-school", "School A Apples", other, 8),
        _listing("other-school", "School B Bread", other, 12),
    ]

    async def fake_get(table, params=None):
        if table == "users":
            return fake_user
        # Pretend PostgREST ignored community_id — return everything.
        return fake_listings

    result = asyncio.run(_run_search(fake_get, me))
    ids = {row["id"] for row in result["listings"]}
    assert "own-school" in ids
    assert "other-school" not in ids
    assert all("community_id" in row for row in result["listings"])


def test_search_admin_sees_all_communities():
    me = "user-admin"
    other = "user-other"

    fake_user = [{
        "id": me,
        "latitude": 37.77,
        "longitude": -122.42,
        "address": "1 Market St, SF",
        "location": None,
        "community_id": 8,
        "is_admin": True,
    }]
    fake_listings = [
        _listing("a", "School A Apples", other, 8),
        _listing("b", "School B Bread", other, 12),
    ]

    async def fake_get(table, params=None):
        if table == "users":
            return fake_user
        assert "community_id" not in (params or {})
        return fake_listings

    result = asyncio.run(_run_search(fake_get, me))
    ids = {row["id"] for row in result["listings"]}
    assert ids == {"a", "b"}


def test_search_no_community_sees_nothing():
    me = "user-no-community"
    other = "user-other"

    fake_user = [{
        "id": me,
        "latitude": 37.77,
        "longitude": -122.42,
        "address": "1 Market St, SF",
        "location": None,
        "community_id": None,
        "is_admin": False,
    }]
    fake_listings = [
        _listing("school", "School Food", other, 8),
        _listing("warehouse", "Warehouse Food", other, 1),
    ]

    async def fake_get(table, params=None):
        if table == "users":
            return fake_user
        assert (params or {}).get("community_id") == "eq.-1"
        return []

    result = asyncio.run(_run_search(fake_get, me))
    assert result["listings"] == []


def test_search_warehouse_member_sees_warehouse_only():
    me = "user-warehouse"
    other = "user-other"

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
        _listing("school", "School Food", other, 8),
        _listing("warehouse", "Warehouse Food", other, 1),
    ]

    async def fake_get(table, params=None):
        if table == "users":
            return fake_user
        assert (params or {}).get("community_id") == "eq.1"
        return [r for r in fake_listings if r["community_id"] == 1]

    result = asyncio.run(_run_search(fake_get, me))
    ids = {row["id"] for row in result["listings"]}
    assert ids == {"warehouse"}


async def _run_recent(fake_get, user_id):
    with patch("backend.ai_engine.supabase_get", new=AsyncMock(side_effect=fake_get)), \
         patch("backend.tools._listing_is_fresh_enough", return_value=True):
        return await _get_recent_listings(user_id=user_id, hours=72, limit=10)


def test_recent_listings_scopes_to_user_community():
    me = "user-school-a"
    other = "user-other"

    fake_user = [{
        "id": me,
        "community_id": 8,
        "is_admin": False,
    }]
    fake_listings = [
        _listing("own-school", "School A Apples", other, 8),
        _listing("other-school", "School B Bread", other, 12),
    ]

    async def fake_get(table, params=None):
        if table == "users":
            return fake_user
        assert params["community_id"] == "eq.8"
        allowed = {"8"}
        return [r for r in fake_listings if str(r["community_id"]) in allowed]

    result = asyncio.run(_run_recent(fake_get, me))
    ids = {row["id"] for row in result["listings"]}
    assert "own-school" in ids
    assert "other-school" not in ids


async def _run_community_listings(fake_get, user_id, community_id):
    with patch("backend.ai_engine.supabase_get", new=AsyncMock(side_effect=fake_get)), \
         patch("backend.tools._listing_is_fresh_enough", return_value=True):
        return await _get_community_listings(
            community_id=community_id,
            user_id=user_id,
            limit=10,
        )


def test_community_listings_blocks_other_school():
    me = "user-school-a"

    fake_user = [{
        "id": me,
        "community_id": 8,
        "is_admin": False,
    }]

    async def fake_get(table, params=None):
        if table == "users":
            return fake_user
        raise AssertionError("should not fetch listings for out-of-scope community")

    result = asyncio.run(_run_community_listings(fake_get, me, "12"))
    assert result["listings"] == []
    assert result["total"] == 0


def test_community_listings_allows_own_school():
    me = "user-school-a"
    other = "user-other"

    fake_user = [{
        "id": me,
        "community_id": 8,
        "is_admin": False,
    }]
    fake_listings = [
        _listing("own-school", "School A Apples", other, 8),
    ]

    async def fake_get(table, params=None):
        if table == "users":
            return fake_user
        assert params["community_id"] == "eq.8"
        return fake_listings

    result = asyncio.run(_run_community_listings(fake_get, me, "8"))
    assert len(result["listings"]) == 1
    assert result["listings"][0]["id"] == "own-school"
