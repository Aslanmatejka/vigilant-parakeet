"""Regression tests for planner ↔ handler tool name alignment.

These exercise the retired planner + `backend.tools.execute_tool` dispatcher
so that if we ever re-enable the LangGraph planner path (behind
`AGENT_V2` / `ENABLE_AGENTIC_MODE`), legacy tool-name aliases keep working
and the `navigate_ui` plan step produces args the handler actually accepts.
"""

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
        """Legacy `get_my_listings` name must route to `get_user_listings`."""
        mock_list = AsyncMock(return_value={"success": True, "listings": []})
        with patch.dict(
            "backend.tools._HANDLERS",
            {"get_user_listings": mock_list},
            clear=False,
        ):
            from backend.tools import execute_tool
            result = await execute_tool("get_my_listings", {"user_id": "u-1"})
        assert result["success"] is True
        mock_list.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_share_food_alias_resolves_to_post_food_listing(self):
        """Fuzzy legacy names for the donor share flow must not 404."""
        mock_post = AsyncMock(return_value={"success": True, "listing_id": "abc"})
        with patch.dict(
            "backend.tools._HANDLERS",
            {"post_food_listing": mock_post},
            clear=False,
        ):
            from backend.tools import execute_tool
            result = await execute_tool(
                "share_food",
                {"user_id": "u-1", "title": "Bread", "quantity": 2},
            )
        assert result["success"] is True
        mock_post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_navigate_open_page_dashboard_path(self):
        """`action=open_page, path=dashboard` (legacy) must normalise to
        `action=navigate, path=/dashboard` before hitting `_ui_action`."""
        from backend.tools import _navigate_ui
        result = await _navigate_ui(action="open_page", path="dashboard")
        assert result.get("ok") is True
        assert result.get("action") == "navigate"
        assert result.get("path") == "/dashboard"


class TestExecutePlanStepAliases:
    @pytest.mark.asyncio
    async def test_planner_falls_back_to_flat_dispatcher(self):
        """Planner should reach `backend.tools.execute_tool` for handlers
        that aren't wrapped in the LangChain `TOOL_DISPATCH` map."""
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
