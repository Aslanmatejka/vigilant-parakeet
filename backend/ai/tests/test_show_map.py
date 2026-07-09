"""Tests for the show_map UI-control tool."""
from __future__ import annotations

import pytest

from backend.ai.tools import TOOL_DEFINITIONS, execute_tool


def test_show_map_tool_is_registered():
    names = {t["function"]["name"] for t in TOOL_DEFINITIONS}
    assert "show_map" in names


def test_show_map_schema_requires_user_id_and_allows_focus():
    fn = next(
        t["function"]
        for t in TOOL_DEFINITIONS
        if t["function"]["name"] == "show_map"
    )
    params = fn["parameters"]
    assert "user_id" in params["properties"]
    assert "focus" in params["properties"]
    assert params["required"] == ["user_id"]


@pytest.mark.asyncio
class TestShowMapHandler:
    async def test_default_focus_returns_success(self):
        r = await execute_tool("show_map", {"user_id": "1"})
        assert r.get("success") is True
        assert r.get("view") == "map"
        assert r.get("focus") is None
        assert "error" not in r
        assert "map" in (r.get("summary") or "").lower()

    async def test_focus_me(self):
        r = await execute_tool("show_map", {"user_id": "1", "focus": "me"})
        assert r["focus"] == "me"
        assert "you" in r["summary"].lower()

    async def test_focus_all(self):
        r = await execute_tool("show_map", {"user_id": "1", "focus": "all"})
        assert r["focus"] == "all"
        assert "all" in r["summary"].lower()

    async def test_focus_freeform(self):
        r = await execute_tool(
            "show_map", {"user_id": "1", "focus": "downtown bakeries"}
        )
        assert r["focus"] == "downtown bakeries"
        assert "downtown bakeries" in r["summary"]

    async def test_blank_focus_treated_as_none(self):
        r = await execute_tool("show_map", {"user_id": "1", "focus": "   "})
        assert r["focus"] is None
