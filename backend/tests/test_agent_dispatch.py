"""
Tests for the agent tool-dispatch layer
========================================
Covers:
- ``execute_plan_step`` fallback to ``backend.tools.execute_tool`` for tools
  outside the 6-entry ``TOOL_DISPATCH``.
- ``ask_user`` sentinel short-circuit (never dispatched).
- Unknown-tool safety envelope (must not raise).
- ``create_plan_llm`` destructive-tool filter (deny-list enforced on both
  the tool schema sent to the LLM and the tool calls returned by it).
- ``create_plan_llm`` mapping of OpenAI tool_calls → PlanStep list.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Env vars for module-level config reads inside backend.ai_engine
# ---------------------------------------------------------------------------
_ENV = {
    "OPENAI_API_KEY": "sk-test-key",
    "SUPABASE_URL": "https://test.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
    "MAPBOX_TOKEN": "pk.test-mapbox",
}
with patch.dict("os.environ", _ENV, clear=False):
    from backend.agent import planner
    from backend.agent.planner import (
        create_plan_llm,
        execute_plan_step,
        _LLM_PLANNER_TOOL_DENYLIST,
        _planner_safe_tool_definitions,
    )
    from backend.agent.state import PlanStep


# ===========================================================================
# execute_plan_step
# ===========================================================================

class TestExecutePlanStepDispatch:
    @pytest.mark.asyncio
    async def test_falls_back_to_execute_tool_for_unwrapped_tool(self):
        """A tool NOT in TOOL_DISPATCH must be dispatched via
        ``backend.tools.execute_tool`` so all 41 handlers are reachable."""
        step: PlanStep = {
            "step_number": 1,
            "action": "Get recipes",
            "tool_name": "get_recipes",
            "tool_args": {"ingredients": ["rice"]},
            "status": "pending",
            "result": None,
        }
        with patch("backend.tools.execute_tool", new=AsyncMock(return_value={
            "ok": True, "recipes": [{"title": "Rice bowl"}]
        })) as mock_exec:
            result = await execute_plan_step(step, user_id="u-1", user_context={})
        assert result == {"ok": True, "recipes": [{"title": "Rice bowl"}]}
        mock_exec.assert_awaited_once_with("get_recipes", {"ingredients": ["rice"]})

    @pytest.mark.asyncio
    async def test_ask_user_short_circuits_without_dispatch(self):
        """The ``ask_user`` sentinel is planner-internal, never dispatched.
        Regressions here would cause 'Unknown tool: ask_user' errors."""
        step: PlanStep = {
            "step_number": 1,
            "action": "Ask for details",
            "tool_name": "ask_user",
            "tool_args": {"question": "How many apples?"},
            "status": "pending",
            "result": None,
        }
        with patch("backend.tools.execute_tool", new=AsyncMock()) as mock_exec:
            result = await execute_plan_step(step, user_id="u-1", user_context={})
        assert result == {"question": "How many apples?", "requires_user_input": True}
        mock_exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error_envelope(self):
        """A tool name in neither TOOL_DISPATCH nor _HANDLERS must return
        a structured error envelope, never raise."""
        step: PlanStep = {
            "step_number": 1,
            "action": "Fake",
            "tool_name": "definitely_not_a_real_tool_12345",
            "tool_args": {"user_id": "u-1"},
            "status": "pending",
            "result": None,
        }
        result = await execute_plan_step(step, user_id="u-1", user_context={})
        assert isinstance(result, dict)
        assert "error" in result
        assert "definitely_not_a_real_tool_12345" in result["error"]


# ===========================================================================
# create_plan_llm — deny-list filter
# ===========================================================================

class TestCreatePlanLlmDenylist:
    def test_destructive_tools_excluded_from_planner_schema(self):
        """The tool schema list handed to the LLM planner must NOT include
        any destructive / audited-path tools. Those must only reach the
        runtime through ``backend/agent/tool_actions.py`` with a
        confirmation card and rollback support."""
        safe = _planner_safe_tool_definitions()
        exposed_names = {
            (spec.get("function") or {}).get("name")
            for spec in safe
            if isinstance(spec, dict)
        }
        for banned in _LLM_PLANNER_TOOL_DENYLIST:
            assert banned not in exposed_names, (
                f"Destructive tool '{banned}' was exposed to the LLM "
                "planner; it must go through the audited path instead."
            )

    def test_denylist_covers_expected_destructive_tools(self):
        """Documented invariant: these specific names must always be
        denylisted (regression guard against someone accidentally shrinking
        the deny-list)."""
        must_be_denied = {
            "delete_listing",
            "deactivate_listing",
            "forget_about_me",
            "leave_community",
            "cancel_claim",
            "update_food_listing",
            "edit_listing",
            "update_listing",
        }
        missing = must_be_denied - _LLM_PLANNER_TOOL_DENYLIST
        assert not missing, f"Deny-list is missing: {missing}"

    def test_safe_definitions_include_read_tools(self):
        """Sanity: the deny-list must not accidentally hide the read
        tools we're trying to expose to the LLM planner (this is the
        whole point of the 6→41 refactor)."""
        safe = _planner_safe_tool_definitions()
        exposed_names = {
            (spec.get("function") or {}).get("name")
            for spec in safe
            if isinstance(spec, dict)
        }
        for expected in ("get_recipes", "get_user_dashboard", "search_food_near_user"):
            assert expected in exposed_names, (
                f"Expected read tool '{expected}' missing from planner schema"
            )


# ===========================================================================
# create_plan_llm — OpenAI response → PlanStep mapping
# ===========================================================================

def _mock_openai_response(tool_calls: list[dict]) -> MagicMock:
    """Build a MagicMock resembling httpx.Response.json() for chat completions."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock(return_value=None)
    resp.json = MagicMock(return_value={
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": tool_calls,
                },
                "finish_reason": "tool_calls",
            }
        ]
    })
    return resp


class TestCreatePlanLlmMapping:
    @pytest.mark.asyncio
    async def test_tool_calls_map_to_plan_steps_in_order(self):
        """Each tool_call from the model becomes one PlanStep, preserving
        order and arguments."""
        openai_calls = [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "get_recipes",
                    "arguments": json.dumps({"ingredients": ["rice", "beans"]}),
                },
            },
            {
                "id": "call_2",
                "type": "function",
                "function": {
                    "name": "get_storage_tips",
                    "arguments": json.dumps({"food_item": "rice"}),
                },
            },
        ]
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=_mock_openai_response(openai_calls))
        with patch(
            "backend.ai_engine._get_http_client", return_value=mock_client
        ):
            plan = await create_plan_llm(
                message="what recipes can I make with rice and beans?",
                entities={},
                user_context={"user_id": "u-1"},
            )
        assert [s["tool_name"] for s in plan] == ["get_recipes", "get_storage_tips"]
        assert plan[0]["tool_args"] == {
            "ingredients": ["rice", "beans"],
            "user_id": "u-1",  # force-injected
        }
        assert plan[0]["step_number"] == 1
        assert plan[1]["step_number"] == 2
        assert plan[0]["status"] == "pending"

    @pytest.mark.asyncio
    async def test_no_tool_calls_returns_empty_plan(self):
        """When the model decides no tool is needed, planner returns []
        so the responder treats the turn as pure conversation."""
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=_mock_openai_response([]))
        with patch(
            "backend.ai_engine._get_http_client", return_value=mock_client
        ):
            plan = await create_plan_llm(
                message="hey how's it going",
                entities={},
                user_context={"user_id": "u-1"},
            )
        assert plan == []

    @pytest.mark.asyncio
    async def test_denylisted_tool_from_model_is_stripped(self):
        """Defense in depth: even if the model somehow returns a
        denylisted tool name, planner must drop it silently (not emit a
        PlanStep the executor would then run)."""
        openai_calls = [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "delete_listing",
                    "arguments": json.dumps({"listing_id": "42"}),
                },
            },
            {
                "id": "call_2",
                "type": "function",
                "function": {
                    "name": "get_recipes",
                    "arguments": json.dumps({"ingredients": ["rice"]}),
                },
            },
        ]
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=_mock_openai_response(openai_calls))
        with patch(
            "backend.ai_engine._get_http_client", return_value=mock_client
        ):
            plan = await create_plan_llm(
                message="please delete listing 42 then show recipes",
                entities={},
                user_context={"user_id": "u-1"},
            )
        assert [s["tool_name"] for s in plan] == ["get_recipes"]

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_api_key(self, monkeypatch):
        """Without OPENAI_API_KEY the planner must not attempt an HTTP
        call — it should return an empty plan so the responder handles
        the turn conversationally instead of erroring."""
        monkeypatch.setattr("backend.ai_engine.OPENAI_API_KEY", "")
        plan = await create_plan_llm(
            message="what recipes?",
            entities={},
            user_context={"user_id": "u-1"},
        )
        assert plan == []


# ===========================================================================
# execute_plan_step — v1 destructive-write intercept
# ===========================================================================

class TestExecutePlanStepDestructiveIntercept:
    """Guard rail: destructive writes must produce a pending_action
    envelope in the v1 agent path (ENABLE_AGENTIC_MODE=true,
    AGENT_V2=false) instead of firing directly. Mirrors the v2 graph's
    behaviour so switching feature flags never opens a hole.
    """

    @pytest.mark.asyncio
    async def test_intercepts_delete_listing(self):
        step: PlanStep = {
            "step_number": 1,
            "action": "Delete listing",
            "tool_name": "delete_listing",
            "tool_args": {"listing_id": "L-9", "title": "Tomatoes"},
            "status": "pending",
            "result": None,
        }
        fake_result = MagicMock()
        fake_result.status = "pending"
        fake_result.pending_id = "pend-abc"
        with patch(
            "backend.agent.actions.plan_action",
            new=AsyncMock(return_value=fake_result),
        ) as mock_plan, patch(
            "backend.tools.execute_tool", new=AsyncMock()
        ) as mock_exec:
            result = await execute_plan_step(step, user_id="u-1", user_context={})
        assert result.get("requires_confirmation") is True
        env = result.get("pending_action")
        assert isinstance(env, dict)
        assert env["pending_id"] == "pend-abc"
        assert env["tool"] == "delete_listing"
        assert "Tomatoes" in env["summary"]
        mock_plan.assert_awaited_once()
        # The write MUST NOT fire until the user confirms.
        mock_exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_intercepts_leave_community_zero_arg(self):
        step: PlanStep = {
            "step_number": 1,
            "action": "Leave community",
            "tool_name": "leave_community",
            "tool_args": {},
            "status": "pending",
            "result": None,
        }
        fake_result = MagicMock()
        fake_result.status = "pending"
        fake_result.pending_id = "pend-lc"
        with patch(
            "backend.agent.actions.plan_action",
            new=AsyncMock(return_value=fake_result),
        ), patch("backend.tools.execute_tool", new=AsyncMock()) as mock_exec:
            result = await execute_plan_step(step, user_id="u-2", user_context={})
        assert result["pending_action"]["tool"] == "leave_community"
        assert result["pending_action"]["pending_id"] == "pend-lc"
        mock_exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_confirmed_flag_bypasses_intercept(self):
        """Once the user taps Yes on the confirmation card, /api/ai/confirm
        re-issues the tool call with `confirmed=True`. That flag MUST
        bypass the intercept so the write actually fires this time."""
        step: PlanStep = {
            "step_number": 1,
            "action": "Delete listing (confirmed)",
            "tool_name": "delete_listing",
            "tool_args": {"listing_id": "L-9", "confirmed": True},
            "status": "pending",
            "result": None,
        }
        with patch(
            "backend.agent.actions.plan_action", new=AsyncMock()
        ) as mock_plan, patch(
            "backend.tools.execute_tool",
            new=AsyncMock(return_value={"success": True, "deleted": True}),
        ) as mock_exec:
            result = await execute_plan_step(step, user_id="u-1", user_context={})
        assert result == {"success": True, "deleted": True}
        # Intercept must NOT run when confirmed=True.
        mock_plan.assert_not_awaited()
        mock_exec.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_intercept_fails_open_on_timeout(self):
        """A Supabase outage that blocks `plan_action` must not wedge the
        planner. Fail open → normal dispatch runs and the post-hoc audit
        log still captures the write."""
        import asyncio as _asyncio

        step: PlanStep = {
            "step_number": 1,
            "action": "Cancel claim",
            "tool_name": "cancel_claim",
            "tool_args": {"claim_id": "C-3"},
            "status": "pending",
            "result": None,
        }

        async def _hang(*_a, **_kw):
            raise _asyncio.TimeoutError()

        with patch(
            "backend.agent.actions.plan_action", new=AsyncMock(side_effect=_hang)
        ), patch(
            "backend.tools.execute_tool",
            new=AsyncMock(return_value={"success": True, "cancelled": True}),
        ) as mock_exec:
            result = await execute_plan_step(step, user_id="u-1", user_context={})
        assert result == {"success": True, "cancelled": True}
        mock_exec.assert_awaited_once_with("cancel_claim", {"claim_id": "C-3"})

    @pytest.mark.asyncio
    async def test_no_user_id_skips_intercept(self):
        """Anonymous / missing user_id (nil-UUID landing-page chat) means
        we have no one to bill the pending row to. Skip the intercept
        rather than queuing an orphan row."""
        step: PlanStep = {
            "step_number": 1,
            "action": "Forget",
            "tool_name": "forget_about_me",
            "tool_args": {},
            "status": "pending",
            "result": None,
        }
        with patch(
            "backend.agent.actions.plan_action", new=AsyncMock()
        ) as mock_plan, patch(
            "backend.tools.execute_tool",
            new=AsyncMock(return_value={"success": True}),
        ) as mock_exec:
            result = await execute_plan_step(step, user_id="", user_context={})
        assert result == {"success": True}
        mock_plan.assert_not_awaited()
        mock_exec.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_non_destructive_tool_never_intercepted(self):
        """A read tool (get_recipes) must go straight to dispatch even
        with matching args shape — the intercept is scoped to the 4
        destructive tools only."""
        step: PlanStep = {
            "step_number": 1,
            "action": "Recipes",
            "tool_name": "get_recipes",
            "tool_args": {"ingredients": ["rice"]},
            "status": "pending",
            "result": None,
        }
        with patch(
            "backend.agent.actions.plan_action", new=AsyncMock()
        ) as mock_plan, patch(
            "backend.tools.execute_tool",
            new=AsyncMock(return_value={"ok": True, "recipes": []}),
        ) as mock_exec:
            result = await execute_plan_step(step, user_id="u-1", user_context={})
        assert result == {"ok": True, "recipes": []}
        mock_plan.assert_not_awaited()
        mock_exec.assert_awaited_once()
