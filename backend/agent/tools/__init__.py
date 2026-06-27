"""
LangChain Tool Wrappers
========================

Wraps backend.tools.py functions as LangChain tools for the agent graph.
"""

from backend.agent.tools.food_tools import (
    search_food_near_user,
    claim_listing,
    post_food_listing,
)

from backend.agent.tools.user_tools import (
    get_user_profile,
    update_user_profile,
)

from backend.agent.tools.navigation_tools import (
    navigate_ui,
)

__all__ = [
    "search_food_near_user",
    "claim_listing",
    "post_food_listing",
    "get_user_profile",
    "update_user_profile",
    "navigate_ui",
]

# Tool dispatch dictionary for planner.py
TOOL_DISPATCH = {
    "search_food_near_user": search_food_near_user,
    "claim_listing": claim_listing,
    "post_food_listing": post_food_listing,
    "get_user_profile": get_user_profile,
    "update_user_profile": update_user_profile,
    "navigate_ui": navigate_ui,
}
