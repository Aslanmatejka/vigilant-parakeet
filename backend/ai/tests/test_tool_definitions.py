"""Schema sanity tests for the OpenAI function-calling tool definitions."""
from __future__ import annotations

from backend.ai.tools import TOOL_DEFINITIONS


class TestToolDefinitionsShape:
    def test_non_empty(self):
        assert isinstance(TOOL_DEFINITIONS, list)
        assert len(TOOL_DEFINITIONS) >= 10

    def test_every_entry_is_function_type(self):
        for t in TOOL_DEFINITIONS:
            assert isinstance(t, dict)
            assert t.get("type") == "function"
            assert "function" in t

    def test_every_function_has_required_fields(self):
        for t in TOOL_DEFINITIONS:
            fn = t["function"]
            assert isinstance(fn.get("name"), str) and fn["name"], t
            assert isinstance(fn.get("description"), str) and fn["description"], fn["name"]
            params = fn.get("parameters")
            assert isinstance(params, dict), fn["name"]
            assert params.get("type") == "object", fn["name"]
            assert isinstance(params.get("properties"), dict), fn["name"]

    def test_tool_names_are_unique(self):
        names = [t["function"]["name"] for t in TOOL_DEFINITIONS]
        assert len(names) == len(set(names)), f"duplicate tool names: {names}"

    def test_required_fields_are_declared_in_properties(self):
        for t in TOOL_DEFINITIONS:
            fn = t["function"]
            params = fn["parameters"]
            props = params.get("properties", {})
            for req in params.get("required", []) or []:
                assert req in props, f"{fn['name']}: required field '{req}' not in properties"


# Tools that MUST be exposed to GPT for the product features to work.
REQUIRED_TOOLS = {
    "search_food_near_user",
    "get_user_dashboard",
    "get_user_profile",
    "get_recipes",
    "get_storage_tips",
    "get_pickup_schedule",
    "get_mapbox_route",
    "optimize_pickup_route",
    "get_donor_expiring_listings",
    "get_driver_route_plan",
    "get_dispatch_queue",
    "get_platform_stats",
    "get_profile_gaps",
    "run_safe_query",
    "claim_listing",
    "claim_listings",
    "cancel_claim",
    "confirm_claim",
    "update_user_profile",
    "post_food_request",
    "post_food_listing",
    "post_food_listings",
    "get_user_listings",
    "update_food_listing",
    "deactivate_listing",
    "delete_listing",
    "send_user_message",
    "show_map",
    "navigate_ui",
}


def test_all_required_tools_registered():
    names = {t["function"]["name"] for t in TOOL_DEFINITIONS}
    missing = REQUIRED_TOOLS - names
    assert not missing, f"missing tool definitions: {sorted(missing)}"
