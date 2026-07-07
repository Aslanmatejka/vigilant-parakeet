"""Regression tests for planner ↔ handler tool name alignment."""

import pytest
from unittest.mock import AsyncMock, patch

from backend.agent.planner import _plan_navigate, execute_plan_step
from backend.agent.state import PlanStep


class TestNavigatePlan:
    def test_plan_navigate_uses_valid_ui_action(self):
        plan = _plan_navigate({"page": "dashboard"})
        assert len(plan) == 1
        assert plan[0]["tool_name"] == "navigate_ui"
        assert plan[0]["tool_args"]["action"] == "navigate"
        assert plan[0]["tool_args"]["path"] == "/dashboard"

    def test_plan_navigate_open_map(self):
        plan = _plan_navigate({}, "Open the map")
        assert plan[0]["tool_args"]["action"] == "open_map"
        assert "path" not in plan[0]["tool_args"]


class TestToolAliases:
    @pytest.mark.asyncio
    async def test_get_my_listings_alias_resolves(self):
        mock_list = AsyncMock(return_value={"success": True, "listings": []})
        with patch.dict("backend.tools._HANDLERS", {"get_user_listings": mock_list}, clear=False):
            from backend.tools import execute_tool
            result = await execute_tool("get_my_listings", {"user_id": "u-1"})
        assert result["success"] is True
        mock_list.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_my_impact_summary_registered(self):
        mock_impact = AsyncMock(return_value={"success": True, "summary": "ok"})
        with patch.dict("backend.tools._HANDLERS", {"get_my_impact_summary": mock_impact}, clear=False):
            from backend.tools import execute_tool
            result = await execute_tool("get_my_impact_summary", {"user_id": "u-1"})
        assert result["success"] is True
        mock_impact.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_navigate_open_page_dashboard_path(self):
        from backend.tools import _navigate_ui
        result = await _navigate_ui(action="open_page", path="dashboard")
        assert result.get("ok") is True
        assert result.get("action") == "navigate"
        assert result.get("path") == "/dashboard"


class TestExecutePlanStepAliases:
    @pytest.mark.asyncio
    async def test_planner_get_user_listings_dispatches(self):
        step: PlanStep = {
            "step_number": 1,
            "action": "Listings",
            "tool_name": "get_user_listings",
            "tool_args": {"user_id": "u-1"},
            "status": "pending",
            "result": None,
        }
        with patch(
            "backend.tools.execute_tool",
            new=AsyncMock(return_value={"success": True, "listings": []}),
        ) as mock_exec:
            result = await execute_plan_step(step, user_id="u-1", user_context={})
        assert result["success"] is True
        mock_exec.assert_awaited_once_with("get_user_listings", {"user_id": "u-1"})
