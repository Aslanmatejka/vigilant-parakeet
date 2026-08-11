"""
Multi-Step Planner
===================

Generates and executes multi-step plans for complex user requests.

Example: "Help me donate 5 items"
Plan:
1. Ask for first item details
2. Ask for photo (optional)
3. Post listing
4. Repeat for remaining items
5. Confirm all posted
"""

import logging
from typing import Dict, Any, List, Optional
import json

from backend.agent.state import PlanStep

logger = logging.getLogger(__name__)


async def create_plan(
    intent: str,
    message: str,
    entities: Dict[str, Any],
    user_context: Dict[str, Any],
) -> List[PlanStep]:
    """
    Generate a multi-step execution plan based on intent.
    
    Args:
        intent: Classified intent (search, claim, donate, etc.)
        message: Original user message
        entities: Extracted entities (food_type, location, etc.)
        user_context: User profile and preferences
    
    Returns:
        List of PlanStep objects
    """
    logger.info(f"Creating plan for intent: {intent}")
    
    if intent == "search":
        return _plan_search(entities, user_context)
    elif intent == "claim":
        return _plan_claim(entities, user_context)
    elif intent == "donate":
        return _plan_donate(entities, user_context, message)
    elif intent == "navigate":
        return _plan_navigate(entities, message)
    else:
        # Simple intents don't need planning
        return []


def _plan_search(entities: Dict[str, Any], user_context: Dict[str, Any]) -> List[PlanStep]:
    """Plan for food search."""
    steps = []
    
    # Step 1: Search for food
    search_args = {
        "user_id": user_context.get("user_id"),
        "food_type": entities.get("food_type"),
        "dietary_tags": user_context.get("dietary_restrictions", []),
        "exclude_allergens": user_context.get("allergies", []),
    }
    
    steps.append(PlanStep(
        step_number=1,
        action="Search for available food",
        tool_name="search_food_near_user",
        tool_args=search_args,
        status="pending",
        result=None,
    ))
    
    return steps


def _plan_claim(entities: Dict[str, Any], user_context: Dict[str, Any]) -> List[PlanStep]:
    """Plan for claiming food."""
    steps = []
    
    food_id = entities.get("food_id")
    if not food_id:
        # Need to search first to get food_id
        steps.append(PlanStep(
            step_number=1,
            action="Search for food to claim",
            tool_name="search_food_near_user",
            tool_args={"user_id": user_context.get("user_id")},
            status="pending",
            result=None,
        ))
    
    # Step: Claim the food
    steps.append(PlanStep(
        step_number=len(steps) + 1,
        action="Claim the food listing",
        tool_name="claim_listing",
        tool_args={
            "user_id": user_context.get("user_id"),
            "food_id": food_id or "{from_search_result}",
            "quantity_requested": entities.get("quantity", 1),
        },
        status="pending",
        result=None,
    ))
    
    return steps


def _plan_donate(entities: Dict[str, Any], user_context: Dict[str, Any], message: str) -> List[PlanStep]:
    """Plan for donating food."""
    steps = []
    
    # Check if user already provided all details
    has_title = "title" in entities or any(word in message.lower() for word in ["have", "sharing", "donating"])
    has_quantity = "quantity" in entities
    has_location = user_context.get("address") is not None
    
    # Step 1: Gather listing details (if not provided)
    if not has_title or not has_quantity:
        steps.append(PlanStep(
            step_number=1,
            action="Ask for food details (title, quantity, expiry)",
            tool_name="ask_user",
            tool_args={"question": "What food are you sharing and how much?"},
            status="pending",
            result=None,
        ))
    
    # Step 2: Get location (if not set)
    if not has_location:
        steps.append(PlanStep(
            step_number=len(steps) + 1,
            action="Ask for pickup location",
            tool_name="ask_user",
            tool_args={"question": "Where can people pick this up?"},
            status="pending",
            result=None,
        ))
    
    # Step 3: Post the listing
    steps.append(PlanStep(
        step_number=len(steps) + 1,
        action="Post food listing",
        tool_name="post_food_listing",
        tool_args={
            "user_id": user_context.get("user_id"),
            "title": entities.get("title", "{from_user_response}"),
            "quantity": entities.get("quantity", "{from_user_response}"),
            "category": entities.get("food_type", "other"),
            "address": user_context.get("address", "{from_user_response}"),
        },
        status="pending",
        result=None,
    ))
    
    return steps


def _plan_navigate(entities: Dict[str, Any], message: str = "") -> List[PlanStep]:
    """Plan for navigation.

    Produces a `navigate_ui` step with args the handler will actually
    accept: `action=navigate` and a leading-slash `path`. If the message
    clearly asks to open the map, we emit `action=open_map` instead
    (which is also in the `_UI_ALLOWED_ACTIONS` set).
    """
    steps: List[PlanStep] = []

    lowered = (message or "").lower()
    if "map" in lowered and ("open" in lowered or "show" in lowered):
        steps.append(PlanStep(
            step_number=1,
            action="Open the map",
            tool_name="navigate_ui",
            tool_args={"action": "open_map"},
            status="pending",
            result=None,
        ))
        return steps

    target_page = str(entities.get("page") or "dashboard").strip()
    # Accept both bare page names ("dashboard") and leading-slash paths
    # ("/dashboard"). `_navigate_ui` also normalises this defensively,
    # but keeping the planner output canonical avoids one round-trip.
    if not target_page.startswith("/"):
        target_page = f"/{target_page.lstrip('/')}"

    steps.append(PlanStep(
        step_number=1,
        action=f"Navigate to {target_page} page",
        tool_name="navigate_ui",
        tool_args={"action": "navigate", "path": target_page},
        status="pending",
        result=None,
    ))

    return steps


async def execute_plan_step(
    step: PlanStep,
    user_id: str,
    user_context: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Execute a single step from the plan.
    
    Args:
        step: PlanStep to execute
        user_id: User's UUID
        user_context: User profile and context
    
    Returns:
        Tool execution result
    """
    tool_name = step.get("tool_name")
    tool_args = step.get("tool_args", {})
    
    logger.info(f"Executing step {step.get('step_number')}: {tool_name}")
    
    try:
        # Prefer the LangChain wrapper when one is registered (adds tool
        # schema validation for structured calls). Fall back to the flat
        # `backend.tools.execute_tool` dispatcher — which honours the full
        # handler map + alias table — so any tool NOT wrapped for LangChain
        # still runs cleanly from the planner path.
        from backend.agent.tools import TOOL_DISPATCH

        tool_fn = TOOL_DISPATCH.get(tool_name)
        if tool_fn is not None:
            if hasattr(tool_fn, "ainvoke"):
                result = await tool_fn.ainvoke(tool_args)
            else:
                result = await tool_fn(**tool_args)
        else:
            from backend.tools import execute_tool as _dispatch
            result = await _dispatch(tool_name, tool_args)

        logger.info(f"Step {step.get('step_number')} completed successfully")
        return result

    except Exception as e:
        logger.error(f"Step {step.get('step_number')} failed: {e}")
        return {
            "error": str(e),
            "step": step.get("step_number"),
            "tool": tool_name,
        }


def plan_to_text(plan: List[PlanStep], language: str = "en") -> str:
    """
    Convert plan to human-readable text.
    
    Used to show user the plan before execution.
    """
    if not plan:
        return ""
    
    if language == "es":
        intro = "Aquí está mi plan:\n"
        steps_text = "\n".join([
            f"{i}. {step.get('action', 'Unknown action')}"
            for i, step in enumerate(plan, 1)
        ])
        return intro + steps_text
    else:
        intro = "Here's my plan:\n"
        steps_text = "\n".join([
            f"{i}. {step.get('action', 'Unknown action')}"
            for i, step in enumerate(plan, 1)
        ])
        return intro + steps_text
