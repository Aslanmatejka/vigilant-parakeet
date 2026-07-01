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

import asyncio
import logging
import os
from typing import Dict, Any, List, Optional, Tuple
import json

from backend.agent.state import PlanStep

logger = logging.getLogger(__name__)


# Destructive / hard-to-reverse tools that must go through the audited
# `tool_actions.py` path (pending_action + confirmation card + rollback),
# NOT the free-form LLM planner. If the LLM planner could emit these, a
# single hallucinated tool call would delete a listing or wipe a profile
# without the user confirming.
_LLM_PLANNER_TOOL_DENYLIST: frozenset[str] = frozenset({
    "delete_listing",
    "deactivate_listing",
    "forget_about_me",
    "leave_community",
    "cancel_claim",
    "update_food_listing",
    "edit_listing",
    "update_listing",
})


# Tools whose execution in the v1 agent path (ENABLE_AGENTIC_MODE=true,
# AGENT_V2=false) MUST be intercepted with a pending_action envelope. The
# v2 graph already does this at a higher layer via
# `backend.agent.pending_intercept.build_intercepted_action`; the v1 graph
# has no equivalent, so we hook `execute_plan_step` right before dispatch.
#
# The intercept is bypassed when `tool_args["confirmed"] is True` — that
# flag is set by /api/ai/confirm after the user taps "Yes" on the card.
_DESTRUCTIVE_TOOLS_INTERCEPT: frozenset[str] = frozenset({
    "delete_listing",
    "cancel_claim",
    "leave_community",
    "forget_about_me",
})

# How long we're willing to wait for `plan_action` to insert the pending
# row before falling open. Matches the v2 graph's 4s budget so behaviour
# is consistent across paths.
_INTERCEPT_TIMEOUT_SEC: float = 4.0


def _build_intercept_summary(
    tool_name: str,
    tool_args: Dict[str, Any],
    language: str = "en",
) -> str:
    """Render a human-readable summary for the confirmation card.

    The frontend shows this line verbatim as "Are you sure you want to
    {summary}?" so keep it action-oriented and free of markup.
    """
    is_es = language == "es"
    if tool_name == "delete_listing":
        title = (tool_args or {}).get("title") or (tool_args or {}).get("listing_title")
        if title:
            return (
                f"eliminar permanentemente tu publicación '{title}'"
                if is_es else
                f"permanently delete your listing '{title}'"
            )
        return (
            "eliminar permanentemente tu publicación"
            if is_es else
            "permanently delete your listing"
        )
    if tool_name == "cancel_claim":
        return (
            "cancelar tu reserva"
            if is_es else
            "release your claim"
        )
    if tool_name == "leave_community":
        return (
            "salir de la comunidad"
            if is_es else
            "leave the community"
        )
    if tool_name == "forget_about_me":
        return (
            "olvidar lo que he aprendido sobre ti"
            if is_es else
            "forget what I've learned about you"
        )
    return tool_name


async def _maybe_intercept_destructive(
    tool_name: str,
    tool_args: Dict[str, Any],
    user_id: Optional[str],
    user_context: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Queue a pending_action envelope for destructive writes.

    Returns a dict shaped for `execute_plan_step` (containing
    `pending_action` + `requires_confirmation`) when the write was queued,
    or ``None`` when the call should proceed normally (not destructive,
    already confirmed, no user_id, plan_action errored, etc.). Failing
    open matches the v2 graph — a Supabase outage must not block writes,
    the post-hoc audit still runs.
    """
    if tool_name not in _DESTRUCTIVE_TOOLS_INTERCEPT:
        return None
    if not isinstance(tool_args, dict):
        return None
    if tool_args.get("confirmed") is True:
        return None
    if not user_id:
        return None

    try:
        from backend.agent.actions import ActionRequest, plan_action
        from backend.agent.pending_intercept import build_pending_action_envelope
    except Exception as exc:  # noqa: BLE001
        logger.warning("intercept imports failed for %s (%s), falling through", tool_name, exc)
        return None

    language = "en"
    if isinstance(user_context, dict):
        lang = user_context.get("language") or user_context.get("detected_language")
        if isinstance(lang, str) and lang:
            language = lang
    summary = _build_intercept_summary(tool_name, tool_args, language=language)

    # Strip planner-internal flags from the args we persist so the
    # commit-time handler doesn't see stray keys.
    persisted_args = {k: v for k, v in tool_args.items() if k not in ("confirmed",)}

    try:
        req = ActionRequest(
            tool=tool_name,
            args=persisted_args,
            user_id=str(user_id),
            turn_id=(user_context.get("turn_id") if isinstance(user_context, dict) else None) or "",
            conversation_id=(user_context.get("conversation_id") if isinstance(user_context, dict) else None),
            requires_confirmation=True,
            summary=summary,
        )
        plan_result = await asyncio.wait_for(plan_action(req), timeout=_INTERCEPT_TIMEOUT_SEC)
    except asyncio.TimeoutError:
        logger.warning("v1 intercept for %s timed out after %.1fs, falling through", tool_name, _INTERCEPT_TIMEOUT_SEC)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("v1 intercept plan_action for %s raised %s, falling through", tool_name, exc)
        return None

    if not plan_result or getattr(plan_result, "status", None) != "pending":
        return None
    pending_id = getattr(plan_result, "pending_id", None)
    if not pending_id:
        return None

    envelope = build_pending_action_envelope(
        pending_id=str(pending_id),
        tool=tool_name,
        args=persisted_args,
        summary=summary,
        expires_at=None,
    )
    logger.info("v1 intercept queued %s as pending_id=%s", tool_name, pending_id)
    return {
        "success": True,
        "pending_action": envelope,
        "requires_confirmation": True,
        "summary": summary,
    }


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
        return _plan_navigate(entities)
    else:
        # No rule-based branch matched (help / general / unknown). Ask the
        # LLM to pick zero or more tools from the full non-destructive
        # registry so ~30 read-only tools (get_recipes, get_user_dashboard,
        # get_active_communities, meal_suggestions, …) become reachable.
        # Returns [] when the model decides no tool call is needed, in
        # which case the responder handles it as pure conversation.
        try:
            return await create_plan_llm(message, entities, user_context)
        except Exception as exc:
            logger.warning("create_plan_llm failed (%s) — falling back to no-op plan", exc)
            return []


def _plan_search(entities: Dict[str, Any], user_context: Dict[str, Any]) -> List[PlanStep]:
    """Plan for food search."""
    steps = []
    
    # Step 1: Search for food
    search_args = {
        "user_id": user_context.get("user_id"),
        "food_type": entities.get("food_type"),
        "radius_km": entities.get("radius", 10),
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


def _plan_navigate(entities: Dict[str, Any]) -> List[PlanStep]:
    """Plan for navigation."""
    steps = []
    
    target_page = entities.get("page", "dashboard")
    
    steps.append(PlanStep(
        step_number=1,
        action=f"Navigate to {target_page} page",
        tool_name="navigate_ui",
        tool_args={"action": "open_page", "path": target_page},
        status="pending",
        result=None,
    ))
    
    return steps


def _planner_safe_tool_definitions() -> List[Dict[str, Any]]:
    """Return the TOOL_DEFINITIONS subset the LLM planner is allowed to pick.

    Excludes destructive / hard-to-reverse tools that must flow through the
    audited pending-action pipeline in ``backend/agent/tool_actions.py``.
    """
    from backend.tools import TOOL_DEFINITIONS

    safe: list[dict[str, Any]] = []
    for spec in TOOL_DEFINITIONS:
        fn = spec.get("function") if isinstance(spec, dict) else None
        if not isinstance(fn, dict):
            continue
        name = fn.get("name")
        if not name or name in _LLM_PLANNER_TOOL_DENYLIST:
            continue
        safe.append(spec)
    return safe


async def create_plan_llm(
    message: str,
    entities: Dict[str, Any],
    user_context: Dict[str, Any],
) -> List[PlanStep]:
    """Ask GPT to pick zero or more tools from the non-destructive registry.

    Returns a ``PlanStep`` per ``tool_call`` the model emits, or ``[]`` when
    the model decides no tool is needed (pure conversational turn).
    """
    from backend.ai_engine import (
        OPENAI_API_KEY,
        OPENAI_BASE_URL,
        FOLLOWUP_MODEL,
        _get_http_client,
    )

    if not OPENAI_API_KEY:
        logger.info("create_plan_llm: no OPENAI_API_KEY, returning empty plan")
        return []

    tools = _planner_safe_tool_definitions()
    if not tools:
        return []

    user_id = user_context.get("user_id") or user_context.get("id") or ""
    profile_bits: list[str] = []
    if user_context.get("address"):
        profile_bits.append(f"address: {user_context['address']}")
    if user_context.get("dietary_restrictions"):
        profile_bits.append(f"dietary_restrictions: {user_context['dietary_restrictions']}")
    if user_context.get("allergies"):
        profile_bits.append(f"allergies: {user_context['allergies']}")
    profile_line = "; ".join(profile_bits) if profile_bits else "(no profile fields set)"

    system_prompt = (
        "You are the tool-selection planner for DoGoods, a mutual-aid food "
        "sharing platform. Given the user's message, decide whether any of "
        "the available tools would help fulfil the request. Only pick a "
        "tool when the user is clearly asking for something a tool can "
        "deliver (recipes, dashboards, community info, notifications, "
        "storage tips, etc.). If the message is casual conversation or a "
        "clarification, return no tool calls. When you do call a tool, "
        "pass `user_id` verbatim from the context; never invent one. "
        "Prefer read tools over writes. Do not respond with prose — only "
        "tool calls or nothing."
    )
    user_prompt = (
        f"user_id: {user_id}\n"
        f"profile: {profile_line}\n"
        f"extracted_entities: {json.dumps(entities or {}, default=str)}\n"
        f"user_message: {message}"
    )

    payload = {
        "model": FOLLOWUP_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "tools": tools,
        "tool_choice": "auto",
        "temperature": 0.2,
        "max_tokens": 400,
    }
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    client = _get_http_client(30)
    try:
        resp = await client.post(
            f"{OPENAI_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("create_plan_llm HTTP call failed: %s", exc)
        return []

    try:
        choice = resp.json()["choices"][0]
    except (KeyError, IndexError, ValueError) as exc:
        logger.warning("create_plan_llm bad response shape: %s", exc)
        return []

    tool_calls = (choice.get("message") or {}).get("tool_calls") or []
    plan: List[PlanStep] = []
    for i, call in enumerate(tool_calls, start=1):
        fn = call.get("function") or {}
        name = fn.get("name")
        if not name or name in _LLM_PLANNER_TOOL_DENYLIST:
            # Belt-and-suspenders: the deny filter is already applied to
            # the tool schema we send, but re-check output in case the
            # model tries a name it wasn't offered.
            continue
        raw_args = fn.get("arguments") or "{}"
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
        except json.JSONDecodeError:
            logger.warning("create_plan_llm: bad JSON args for %s: %r", name, raw_args)
            continue
        if user_id and "user_id" not in args:
            # Force-inject user_id so user-scoped handlers can't be tricked
            # into acting on someone else's data.
            args["user_id"] = user_id
        plan.append(PlanStep(
            step_number=i,
            action=f"Call {name}",
            tool_name=name,
            tool_args=args,
            status="pending",
            result=None,
        ))

    logger.info("create_plan_llm: emitted %d step(s)", len(plan))
    return plan


async def execute_plan_step(
    step: PlanStep,
    user_id: str,
    user_context: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Execute a single step from the plan.

    Dispatch order:
    1. ``ask_user`` short-circuits — it's a planner sentinel, not a real
       tool. Returns a ``{"question": ...}`` envelope the responder renders.
    2. ``TOOL_DISPATCH`` fast-path — the 6 LangChain-wrapped agent tools.
    3. ``backend.tools.execute_tool`` fallback — the shared dispatcher that
       reaches all ~41 handlers (get_recipes, get_user_dashboard,
       message_donor, etc.) via a single registry.
    """
    tool_name = step.get("tool_name")
    tool_args = step.get("tool_args", {}) or {}

    logger.info(f"Executing step {step.get('step_number')}: {tool_name}")

    if tool_name == "ask_user":
        return {
            "question": tool_args.get("question", ""),
            "requires_user_input": True,
        }

    # v1 destructive-write guard. Must run BEFORE dispatch so the write
    # never fires until the user confirms. Fails open on error/timeout so
    # a Supabase outage can't wedge the whole planner — the post-hoc
    # audit log still captures every committed write.
    intercept = await _maybe_intercept_destructive(
        tool_name=tool_name,
        tool_args=tool_args,
        user_id=user_id,
        user_context=user_context,
    )
    if intercept is not None:
        return intercept

    try:
        from backend.agent.tools import TOOL_DISPATCH

        tool_fn = TOOL_DISPATCH.get(tool_name)
        if tool_fn is not None:
            if hasattr(tool_fn, "ainvoke"):
                result = await tool_fn.ainvoke(tool_args)
            else:
                result = await tool_fn(**tool_args)
            logger.info(f"Step {step.get('step_number')} completed via TOOL_DISPATCH")
            return result

        from backend.tools import execute_tool

        result = await execute_tool(tool_name, tool_args)
        logger.info(f"Step {step.get('step_number')} completed via execute_tool")
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
