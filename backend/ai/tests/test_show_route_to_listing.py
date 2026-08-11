"""Tests for the show_route_to_listing AI tool."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.ai.tools import TOOL_DEFINITIONS, execute_tool


def _fake_session(user=None, listing=None) -> MagicMock:
    """SessionLocal() stand-in that returns the given user and listing
    for the standard User/FoodResource queries used by the tool."""
    db = MagicMock()

    def _query(model):
        q = MagicMock()
        # Both queries use .filter(...).first(); decide which result to
        # return based on the model name.
        name = getattr(model, "__name__", "")
        if name == "User":
            q.filter.return_value.first.return_value = user
        elif name == "FoodResource":
            q.filter.return_value.first.return_value = listing
        else:
            q.filter.return_value.first.return_value = None
        return q

    db.query.side_effect = _query
    return db


def _make_user(**overrides) -> MagicMock:
    u = MagicMock()
    u.id = 1
    u.coords_lat = 37.7749
    u.coords_lng = -122.4194
    u.address = "1 Market St, San Francisco, CA"
    for k, v in overrides.items():
        setattr(u, k, v)
    return u


def _make_listing(**overrides) -> MagicMock:
    l = MagicMock()
    l.id = 42
    l.title = "Fresh bread"
    l.coords_lat = 37.7849
    l.coords_lng = -122.4094
    l.address = "200 Pine St, San Francisco, CA"
    for k, v in overrides.items():
        setattr(l, k, v)
    return l


def test_show_route_tool_is_registered():
    names = {t["function"]["name"] for t in TOOL_DEFINITIONS}
    assert "show_route_to_listing" in names


def test_show_route_schema_requires_user_id():
    fn = next(
        t["function"]
        for t in TOOL_DEFINITIONS
        if t["function"]["name"] == "show_route_to_listing"
    )
    params = fn["parameters"]
    assert "user_id" in params["properties"]
    assert "listing_id" in params["properties"]
    assert set(params["required"]) >= {"user_id"}
    # listing_id is a string so UUIDs and "#1" both work for Supabase users.
    assert params["properties"]["listing_id"]["type"] == "string"


@pytest.mark.asyncio
async def test_invalid_listing_id_returns_error():
    r = await execute_tool(
        "show_route_to_listing", {"user_id": "1", "listing_id": "not-an-int"}
    )
    assert isinstance(r, dict)
    assert "error" in r
    assert "listing_id" in r["error"].lower()


@pytest.mark.asyncio
async def test_supabase_user_routes_via_food_listings():
    """UUID auth users must not hit the legacy FoodResource int path."""
    uid = "56e3c110-8e22-4756-b98e-02d2d5c81a36"
    lid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    async def fake_get(table, params=None):
        if table == "users":
            return [{
                "id": uid,
                "address": "1 Market St, San Francisco, CA",
                "latitude": 37.7749,
                "longitude": -122.4194,
            }]
        if table == "food_listings":
            return [{
                "id": lid,
                "title": "Fresh bread",
                "full_address": "200 Pine St, San Francisco, CA",
                "latitude": 37.7849,
                "longitude": -122.4094,
            }]
        return []

    with patch("backend.ai_engine.supabase_get", side_effect=fake_get), \
         patch("backend.ai.tools.MAPBOX_TOKEN", ""):
        r = await execute_tool(
            "show_route_to_listing",
            {"user_id": uid, "listing_id": lid},
        )

    assert r.get("success") is True
    assert r.get("action") == "open_map"
    assert r["route"]["destination"]["listing_id"] == lid
    assert r["route"]["fallback"] is True


@pytest.mark.asyncio
async def test_missing_origin_when_user_has_no_address():
    user = _make_user(coords_lat=None, coords_lng=None, address=None)
    listing = _make_listing()
    fake_db = _fake_session(user=user, listing=listing)

    with patch("backend.app.SessionLocal", return_value=fake_db):
        r = await execute_tool(
            "show_route_to_listing", {"user_id": "1", "listing_id": 42}
        )

    assert "error" in r
    assert r.get("reason") == "missing_origin"


@pytest.mark.asyncio
async def test_missing_destination_when_listing_has_no_coords():
    user = _make_user()
    listing = _make_listing(coords_lat=None, coords_lng=None, address=None)
    fake_db = _fake_session(user=user, listing=listing)

    with patch("backend.app.SessionLocal", return_value=fake_db):
        r = await execute_tool(
            "show_route_to_listing", {"user_id": "1", "listing_id": 42}
        )

    assert "error" in r
    assert r.get("reason") == "missing_destination"


@pytest.mark.asyncio
async def test_listing_not_found_returns_error():
    user = _make_user()
    fake_db = _fake_session(user=user, listing=None)

    with patch("backend.app.SessionLocal", return_value=fake_db):
        r = await execute_tool(
            "show_route_to_listing", {"user_id": "1", "listing_id": 999}
        )

    assert "error" in r
    assert "999" in r["error"]


@pytest.mark.asyncio
async def test_success_with_mocked_mapbox_directions():
    user = _make_user()
    listing = _make_listing()
    fake_db = _fake_session(user=user, listing=listing)

    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json = MagicMock(return_value={
        "routes": [{
            "distance": 1609.344,  # exactly 1 mile
            "duration": 300.0,     # 5 minutes
            "geometry": {
                "type": "LineString",
                "coordinates": [
                    [-122.4194, 37.7749],
                    [-122.4140, 37.7800],
                    [-122.4094, 37.7849],
                ],
            },
        }]
    })

    client_ctx = MagicMock()
    client_ctx.__aenter__ = AsyncMock(return_value=MagicMock(
        get=AsyncMock(return_value=fake_resp)
    ))
    client_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch("backend.app.SessionLocal", return_value=fake_db), \
         patch("backend.ai.tools.MAPBOX_TOKEN", "test-token"), \
         patch("backend.ai.tools.httpx.AsyncClient", return_value=client_ctx):
        r = await execute_tool(
            "show_route_to_listing", {"user_id": "1", "listing_id": 42}
        )

    assert r.get("success") is True
    assert r.get("view") == "map"
    route = r["route"]
    assert route["fallback"] is False
    assert route["mode"] == "driving"
    assert route["distance_m"] == pytest.approx(1609.344)
    assert route["duration_s"] == pytest.approx(300.0)
    assert route["geometry"]["type"] == "LineString"
    assert len(route["geometry"]["coordinates"]) == 3
    assert route["origin"]["lat"] == pytest.approx(37.7749)
    assert route["destination"]["listing_id"] == 42
    assert "1.0 mi" in r["summary"]
    assert "5 min" in r["summary"]


@pytest.mark.asyncio
async def test_fallback_when_mapbox_token_missing():
    user = _make_user()
    listing = _make_listing()
    fake_db = _fake_session(user=user, listing=listing)

    with patch("backend.app.SessionLocal", return_value=fake_db), \
         patch("backend.ai.tools.MAPBOX_TOKEN", ""):
        r = await execute_tool(
            "show_route_to_listing", {"user_id": "1", "listing_id": 42}
        )

    assert r.get("success") is True
    route = r["route"]
    assert route["fallback"] is True
    # Straight-line fallback: just origin and destination.
    coords = route["geometry"]["coordinates"]
    assert len(coords) == 2
    assert coords[0] == [user.coords_lng, user.coords_lat]
    assert coords[1] == [listing.coords_lng, listing.coords_lat]


@pytest.mark.asyncio
async def test_mode_walking_is_honored():
    user = _make_user()
    listing = _make_listing()
    fake_db = _fake_session(user=user, listing=listing)

    with patch("backend.app.SessionLocal", return_value=fake_db), \
         patch("backend.ai.tools.MAPBOX_TOKEN", ""):
        r = await execute_tool(
            "show_route_to_listing",
            {"user_id": "1", "listing_id": 42, "mode": "walking"},
        )

    assert r["route"]["mode"] == "walking"


@pytest.mark.asyncio
async def test_invalid_mode_falls_back_to_driving():
    user = _make_user()
    listing = _make_listing()
    fake_db = _fake_session(user=user, listing=listing)

    with patch("backend.app.SessionLocal", return_value=fake_db), \
         patch("backend.ai.tools.MAPBOX_TOKEN", ""):
        r = await execute_tool(
            "show_route_to_listing",
            {"user_id": "1", "listing_id": 42, "mode": "teleport"},
        )

    assert r["route"]["mode"] == "driving"
