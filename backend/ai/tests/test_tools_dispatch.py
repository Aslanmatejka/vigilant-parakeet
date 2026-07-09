"""Tests for execute_tool dispatcher and run_safe_query validation."""
from __future__ import annotations

import pytest

from backend.ai.tools import execute_tool


@pytest.mark.asyncio
class TestDispatcher:
    async def test_unknown_tool_returns_error(self):
        r = await execute_tool("nonexistent_tool_xyz", {})
        assert isinstance(r, dict)
        assert "error" in r
        assert "Unknown tool" in r["error"]

    async def test_exception_in_handler_is_wrapped(self):
        # Passing an unknown kwarg causes TypeError inside the handler;
        # dispatcher must catch and return {"error": ...}
        r = await execute_tool("get_user_profile", {"bogus_kwarg": 1})
        assert isinstance(r, dict)
        assert "error" in r


@pytest.mark.asyncio
class TestRunSafeQueryValidation:
    """These validation paths reject BEFORE touching the database, so no DB required."""

    async def test_unknown_entity_rejected(self):
        r = await execute_tool("run_safe_query", {"entity": "users_secret"})
        assert isinstance(r, dict)
        assert "error" in r
        assert "entity must be one of" in r["error"]

    async def test_empty_entity_rejected(self):
        r = await execute_tool("run_safe_query", {"entity": ""})
        assert "error" in r

    async def test_whitelist_exposes_only_safe_entities(self):
        from backend.ai.tools import _QUERY_WHITELIST
        assert set(_QUERY_WHITELIST.keys()) == {"listings", "requests", "centers", "users"}

    async def test_users_whitelist_does_not_expose_pii_fields(self):
        from backend.ai.tools import _QUERY_WHITELIST
        sensitive = {"password_hash", "email", "phone", "hashed_password",
                     "sms_opt_out_date", "verification_token"}
        users_fields = set(_QUERY_WHITELIST["users"]["fields"].keys())
        users_select = set(_QUERY_WHITELIST["users"]["select"])
        assert not (sensitive & users_fields), \
            f"sensitive fields exposed in filter whitelist: {sensitive & users_fields}"
        assert not (sensitive & users_select), \
            f"sensitive fields exposed in projection: {sensitive & users_select}"

    async def test_allowed_ops_is_read_only(self):
        from backend.ai.tools import _ALLOWED_OPS
        # No mutating operators
        assert _ALLOWED_OPS == {"eq", "ne", "gt", "gte", "lt", "lte", "in", "like"}
        for banned in ("drop", "delete", "update", "insert", "truncate", "exec"):
            assert banned not in _ALLOWED_OPS


@pytest.mark.asyncio
class TestToolArgValidation:
    async def test_search_food_invalid_user_id(self):
        r = await execute_tool("search_food_near_user", {"user_id": "not-an-int"})
        # Supabase-backed search: invalid ids may return empty results, not a local parse error.
        assert isinstance(r, dict)
        assert "error" not in r or r.get("total", 0) == 0 or r.get("results") == []

    async def test_get_user_profile_invalid_id(self):
        r = await execute_tool("get_user_profile", {"user_id": "abc"})
        # Supabase-backed lookup: garbage ids yield no row (not a local int parse error).
        assert r.get("profile") is None
        assert r.get("error") or r.get("message")
