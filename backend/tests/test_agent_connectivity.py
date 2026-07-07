"""Smoke tests that agent subsystems are wired together."""

from backend.agent.actions import tools_requiring_confirmation
from backend.agent.planner import _tools_requiring_confirmation, _build_intercept_summary
from backend.agent.tool_actions import register_all
from backend.agent.tools import TOOL_DISPATCH
from backend.agent.context_block import format_reasoning_block
from backend.agent.reasoning import Thought
from backend.agent.goals import Goal


def test_write_tools_require_confirmation_in_planner():
    planner_tools = _tools_requiring_confirmation()
    registry_tools = tools_requiring_confirmation()
    assert "claim_listing" in planner_tools
    assert "post_food_listing" in planner_tools
    assert "claim_listing" in registry_tools
    assert "post_food_listing" in registry_tools
    summary = _build_intercept_summary(
        "claim_listing", {"listing_id": "9", "title": "Bread"}, language="en",
    )
    assert "Bread" in summary


def test_tool_dispatch_covers_core_agent_tools():
    assert "claim_listing" in TOOL_DISPATCH
    assert "post_food_listing" in TOOL_DISPATCH
    assert "navigate_ui" in TOOL_DISPATCH
    assert "search_food_near_user" in TOOL_DISPATCH


def test_all_write_actions_registered():
    names = set(register_all())
    for required in (
        "claim_listing",
        "post_food_listing",
        "join_community",
        "leave_community",
        "message_donor",
        "schedule_pickup",
    ):
        assert required in names


def test_reasoning_block_reaches_response_prompt_shape():
    block = format_reasoning_block(
        thought=Thought(thought="User wants food nearby.", intent="search", confidence=0.9),
        goals=[Goal(id="g1", user_id="u1", description="Find dinner", intent="search")],
        affect_dominant="neutral",
    )
    assert "<consciousness>" in block
    assert "Find dinner" in block
