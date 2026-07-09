"""Tests for the navigate_ui UI-control tool."""
from __future__ import annotations

import pytest

from backend.ai.tools import TOOL_DEFINITIONS, execute_tool


def test_navigate_ui_tool_is_registered():
    names = {t["function"]["name"] for t in TOOL_DEFINITIONS}
    assert "navigate_ui" in names


def test_navigate_ui_schema_has_action_enum_and_required_fields():
    fn = next(
        t["function"] for t in TOOL_DEFINITIONS
        if t["function"]["name"] == "navigate_ui"
    )
    params = fn["parameters"]
    assert "user_id" in params["properties"]
    assert "action" in params["properties"]
    assert "target" in params["properties"]
    actions = params["properties"]["action"].get("enum") or []
    assert set(actions) == {"open", "close", "toggle"}
    targets = params["properties"]["target"].get("enum") or []
    for t in ("map", "list", "dashboard", "admin", "favorites", "chat", "voice"):
        assert t in targets, f"missing target {t}"
    assert params["required"] == ["user_id", "action"]


@pytest.mark.asyncio
class TestNavigateUiHandler:
    async def test_open_dashboard(self):
        r = await execute_tool(
            "navigate_ui", {"user_id": "1", "action": "open", "target": "dashboard"}
        )
        assert r.get("success") is True
        assert r.get("ok") is True
        assert r["action"] == "navigate"
        assert r["path"] == "/dashboard"
        assert r["target"] == "dashboard"
        assert "dashboard" in r["summary"].lower()

    async def test_open_map(self):
        r = await execute_tool(
            "navigate_ui", {"user_id": "1", "action": "open", "target": "map"}
        )
        assert r["action"] == "open_map"
        assert r.get("ok") is True

    async def test_close_without_target_returns_to_map(self):
        r = await execute_tool(
            "navigate_ui", {"user_id": "1", "action": "close"}
        )
        assert r["success"] is True
        assert r["action"] == "navigate"
        assert r["path"] == "/find"

    async def test_toggle_favorites(self):
        r = await execute_tool(
            "navigate_ui",
            {"user_id": "1", "action": "toggle", "target": "favorites"},
        )
        assert r["action"] == "navigate"
        assert r["path"] == "/find"
        assert r["target"] == "favorites"

    async def test_invalid_action_rejected(self):
        r = await execute_tool(
            "navigate_ui", {"user_id": "1", "action": "delete", "target": "map"}
        )
        assert "error" in r

    async def test_unknown_target_rejected(self):
        r = await execute_tool(
            "navigate_ui",
            {"user_id": "1", "action": "open", "target": "secret_panel"},
        )
        assert "error" in r

    async def test_open_without_target_rejected(self):
        r = await execute_tool(
            "navigate_ui", {"user_id": "1", "action": "open"}
        )
        assert "error" in r
