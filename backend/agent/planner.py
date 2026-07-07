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
import re
from typing import Dict, Any, List, Optional, Tuple
import json

from backend.agent.state import PlanStep
from backend.debug_log import agent_debug_log

logger = logging.getLogger(__name__)


def _resolve_user_id(
    user_context: Dict[str, Any],
    fallback: Optional[str] = None,
) -> Optional[str]:
    """Return the canonical user id from profile context.

    Supabase `users` rows expose `id`; some call sites pass `user_id`.
    Rule-based planners and tool dispatch must accept either key.
    """
    if not isinstance(user_context, dict):
        return fallback
    return user_context.get("user_id") or user_context.get("id") or fallback


def _parse_quantity(raw: Any) -> Optional[int]:
    """Extract a whole-number quantity from planner entities or user text."""
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return max(1, int(raw))
    match = re.search(r"(\d+)", str(raw))
    return max(1, int(match.group(1))) if match else None


def _parse_expiry_from_text(text: str) -> Optional[str]:
    """Map natural-language dates to YYYY-MM-DD for post_food_listing."""
    from datetime import datetime, timedelta, timezone

    if not text or not str(text).strip():
        return None
    lo = str(text).lower()
    today = datetime.now(timezone.utc).date()

    iso = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if iso:
        return iso.group(1)

    if any(p in lo for p in (
        "until tomorrow", "till tomorrow", "good till tomorrow",
        "good until tomorrow", "fresh until tomorrow", "fresh till tomorrow",
        "expires tomorrow", "good for tomorrow",
    )):
        return (today + timedelta(days=1)).isoformat()
    if re.search(r"\btomorrow\b", lo):
        return (today + timedelta(days=1)).isoformat()
    if any(p in lo for p in ("made today", "fresh today", "expires today", "good today")):
        return today.isoformat()
    if "24 hour" in lo or "24h" in lo:
        return (today + timedelta(days=1)).isoformat()
    if "2 days" in lo or "two days" in lo:
        return (today + timedelta(days=2)).isoformat()
    return None


def _donate_flow_messages(messages: Optional[List[Any]]) -> List[Any]:
    """Only consider messages since the latest 'I want to share' turn."""
    if not messages:
        return []
    start = 0
    for i, msg in enumerate(messages):
        if isinstance(msg, dict):
            role = msg.get("role")
            content = str(msg.get("content") or "")
        else:
            role = getattr(msg, "role", None)
            content = str(getattr(msg, "content", "") or "")
        if role == "user" and re.search(
            r"\b(want to share|share (some )?food|i('d| would) like to (share|donate)|"
            r"donate food|post a listing|publicar)\b",
            content,
            re.I,
        ):
            start = i
    return list(messages)[start:]


def enrich_entities_from_conversation(
    intent: Optional[str],
    entities: Dict[str, Any],
    message: str,
    messages: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """Fill donate-plan gaps from prior turns stored in message history."""
    if intent != "donate":
        return dict(entities or {})

    enriched = dict(entities or {})
    flow_messages = _donate_flow_messages(messages)
    parts = [message or ""]
    user_parts: list[str] = []
    last_assistant = ""
    for msg in (flow_messages or [])[-12:]:
        if isinstance(msg, dict):
            role = msg.get("role")
            content = str(msg.get("content") or "")
        else:
            role = getattr(msg, "role", None)
            content = str(getattr(msg, "content", "") or "")
        parts.append(content)
        if role == "user":
            user_parts.append(content)
        elif role == "assistant":
            last_assistant = content

    blob = " ".join(parts).lower()

    # Inline photo upload from chat UI
    img_match = re.search(r"image:\s*(https?://\S+)", message or "", re.I)
    if img_match:
        enriched["image_url"] = img_match.group(1).strip()

    cur_msg = (message or "").strip().lower()
    is_fresh_share = bool(re.search(
        r"\b(want to share|share (some )?food|i('d| would) like to (share|donate)|"
        r"donate food|post a listing|publicar)\b",
        cur_msg,
        re.I,
    ))

    # Fresh donate intent — drop stale intake from prior listings / sessions.
    if is_fresh_share:
        for stale_key in (
            "title", "food_type", "quantity", "unit",
            "community_confirmed", "post_confirmed", "photo_prompted",
            "skip_photo", "awaiting_photo_upload", "awaiting_post_confirm",
            "quantity_stated", "expiry_date", "image_url", "location",
        ):
            enriched.pop(stale_key, None)

    title_source = cur_msg if is_fresh_share else blob

    # Common food phrases not covered by single-word tokens
    if not enriched.get("title") and not enriched.get("food_type"):
        for phrase, label in (
            ("prepared meal", "Prepared meal"),
            ("prepared food", "Prepared food"),
            ("leftovers", "Leftovers"),
            ("home cooked", "Home cooked meal"),
        ):
            if phrase in title_source:
                enriched["food_type"] = phrase
                enriched.setdefault("title", label)
                break

    if not enriched.get("title") and not enriched.get("food_type"):
        for token in (
            "rice", "bread", "soup", "fruit", "vegetables", "meat",
            "milk", "eggs", "pasta", "beans", "chicken", "fish",
        ):
            if token in title_source:
                enriched["food_type"] = token
                enriched.setdefault("title", token.capitalize())
                break

    if enriched.get("quantity") is None or is_fresh_share:
        qty_chunks = [message or ""] if is_fresh_share else reversed([message or ""] + user_parts)
        for chunk in (qty_chunks if is_fresh_share else list(qty_chunks)):
            qty = _parse_quantity(chunk)
            if qty is not None:
                enriched["quantity"] = qty
                enriched["quantity_stated"] = True
                break
        if is_fresh_share and enriched.get("quantity") is None:
            enriched.pop("quantity_stated", None)

    elif enriched.get("quantity") is not None and not enriched.get("quantity_stated"):
        # Drop classifier-default qty unless the user actually said a number.
        user_stated = _parse_quantity(message or "")
        if user_stated is None:
            for chunk in reversed(user_parts):
                user_stated = _parse_quantity(chunk)
                if user_stated is not None:
                    break
        if user_stated is None:
            enriched.pop("quantity", None)
        else:
            enriched["quantity"] = user_stated
            enriched["quantity_stated"] = True

    from backend.agent.suggestion_chips import (
        _looks_like_community_name,
        _sanitize_community_name,
    )

    user_blob = " ".join(user_parts + [message or ""]).lower()

    # Community names: only trust the current user message, not old turns.
    if "alameda unified" in cur_msg:
        enriched.setdefault("community_name", "Alameda Unified")

    list_under = re.search(
        r"(?:list under|post under|publicar en|listar en)\s+(.+?)(?:\?|$|\.)",
        message or "",
        re.I,
    )
    if list_under:
        name = _sanitize_community_name(list_under.group(1).strip().strip('"\''))
        if name and _looks_like_community_name(name):
            enriched["community_name"] = name
            enriched["community_confirmed"] = True
            enriched.pop("awaiting_photo_upload", None)
            if not enriched.get("image_url"):
                enriched.pop("photo_prompted", None)

    def _assistant_asks_community(text: str) -> bool:
        la = (text or "").lower()
        if any(k in la for k in (
            "address", "pickup spot", "pick up from", "profile address",
            "pickup from you", "drop off", "deliver", "dirección", "recoger",
            "use your profile address", "different address",
        )):
            return False
        return any(k in la for k in (
            "which community", "what community", "list under", "list this under",
            "school should", "community should", "publicar en", "qué comunidad",
            "list this rice under", "should i list", "list this under",
        ))

    _AFFIRMATIVE = re.compile(
        r"^(?:yes|yeah|yep|sure|ok(?:ay)?|confirm|post(?:\s+it)?|go ahead|"
        r"sí|si|claro|vale)(?:\s|,|$)",
        re.I,
    )
    if _AFFIRMATIVE.match((message or "").strip()):
        if _assistant_asks_community(last_assistant):
            enriched["community_confirmed"] = True
        elif (
            enriched.get("community_name")
            and _looks_like_community_name(str(enriched["community_name"]))
            and any(k in last_assistant.lower() for k in ("post", "confirm", "unified", "publicar"))
        ):
            enriched["community_confirmed"] = True

    def _assistant_asked_photo(text: str) -> bool:
        la = (text or "").lower()
        return "photo" in la and any(
            k in la for k in ("add", "upload", "picture", "snap", "foto", "camera")
        )

    def _assistant_asked_post_confirm(text: str) -> bool:
        la = (text or "").lower()
        return (
            "quick check" in la
            or "post it?" in la
            or "post this?" in la
            or "shall i post" in la
            or "publish it" in la
        )

    if _assistant_asked_photo(last_assistant) and enriched.get("quantity_stated"):
        enriched["photo_prompted"] = True

    if re.search(r"\b(no photo|skip photo|without photo|no picture|sin foto)\b", cur_msg, re.I):
        enriched["skip_photo"] = True
        enriched.pop("awaiting_photo_upload", None)

    if re.search(r"\b(just post|skip the rest|post it now)\b", cur_msg, re.I):
        enriched["skip_photo"] = True
        enriched["post_confirmed"] = True

    if _assistant_asked_photo(last_assistant) and _AFFIRMATIVE.match((message or "").strip()):
        enriched["awaiting_photo_upload"] = True

    if _assistant_asked_post_confirm(last_assistant) and _AFFIRMATIVE.match((message or "").strip()):
        enriched["post_confirmed"] = True

    if enriched.get("post_confirmed"):
        enriched["quantity_stated"] = True

    if enriched.get("awaiting_post_confirm") and _AFFIRMATIVE.match((message or "").strip()):
        enriched["post_confirmed"] = True

    if re.search(
        r"\b(?:yes.*(?:unified|post|community)|post it|yes, post|alameda unified)\b",
        cur_msg,
        re.I,
    ):
        cn = enriched.get("community_name")
        if (cn and _looks_like_community_name(str(cn))) or "unified" in cur_msg:
            enriched["community_confirmed"] = True

    # Drop garbage community names scraped from assistant questions.
    cn_raw = enriched.get("community_name")
    if cn_raw and not _looks_like_community_name(str(cn_raw)):
        enriched.pop("community_name", None)
        if not list_under:
            enriched.pop("community_confirmed", None)

    # Preserve community confirmation once set this flow (classifier must not reset).
    if entities.get("community_confirmed") and not list_under and not is_fresh_share:
        enriched["community_confirmed"] = True

    if not enriched.get("expiry_date"):
        for chunk in reversed([message or ""] + user_parts):
            exp = _parse_expiry_from_text(chunk)
            if exp:
                enriched["expiry_date"] = exp
                break
        if not enriched.get("expiry_date") and "made today" in blob:
            if "tomorrow" in blob:
                enriched["expiry_date"] = _parse_expiry_from_text("tomorrow")
            else:
                from datetime import datetime, timedelta, timezone
                enriched["expiry_date"] = (
                    datetime.now(timezone.utc).date() + timedelta(days=2)
                ).isoformat()

    return enriched


def _args_have_placeholders(args: Dict[str, Any]) -> bool:
    """True when any arg is an unfilled planner template like `{from_user_response}`."""
    for value in args.values():
        if isinstance(value, str) and value.startswith("{from_"):
            return True
    return False


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
# Fallback when the action registry is unavailable (e.g. early import / tests).
_DESTRUCTIVE_TOOLS_INTERCEPT_FALLBACK: frozenset[str] = frozenset({
    "delete_listing",
    "cancel_claim",
    "leave_community",
    "forget_about_me",
    "claim_listing",
    "post_food_listing",
    "create_food_listing",
})


def _tools_requiring_confirmation() -> frozenset[str]:
    try:
        from backend.agent.actions import tools_requiring_confirmation
        registered = tools_requiring_confirmation()
        if registered:
            return registered
    except Exception:
        pass
    return _DESTRUCTIVE_TOOLS_INTERCEPT_FALLBACK

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
    if tool_name == "claim_listing":
        title = (tool_args or {}).get("title") or (tool_args or {}).get("listing_title")
        listing_id = (tool_args or {}).get("listing_id") or (tool_args or {}).get("food_id")
        if title:
            return (
                f"reclamar '{title}'"
                if is_es else
                f"claim '{title}'"
            )
        if listing_id:
            return (
                f"reclamar la publicación #{listing_id}"
                if is_es else
                f"claim listing #{listing_id}"
            )
        return "reclamar esta comida" if is_es else "claim this food listing"
    if tool_name in ("post_food_listing", "create_food_listing"):
        title = (tool_args or {}).get("title") or ("tu comida" if is_es else "your food")
        return (
            f"publicar '{title}' en la comunidad"
            if is_es else
            f"post '{title}' to the community"
        )
    try:
        from backend.agent.actions import get_action
        spec = get_action(tool_name)
        if spec:
            return spec.render_summary(tool_args or {})
    except Exception:
        pass
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
    if tool_name not in _tools_requiring_confirmation():
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
        if tool_name in ("post_food_listing", "create_food_listing"):
            err = getattr(plan_result, "error", None) if plan_result else "intercept unavailable"
            entities = (user_context or {}).get("last_intent_entities") or {}
            chat_confirmed = bool(
                tool_args.get("post_confirmed")
                or entities.get("post_confirmed")
            )
            if chat_confirmed and tool_args.get("community_confirmed"):
                agent_debug_log(
                    "planner.py:intercept",
                    "pending table unavailable — proceeding after chat confirm",
                    {"tool": tool_name, "error": str(err)},
                    hypothesis_id="H5",
                )
                return None
            agent_debug_log(
                "planner.py:intercept",
                "post intercept failed — blocking direct write",
                {"tool": tool_name, "error": str(err), "chat_confirmed": chat_confirmed},
                hypothesis_id="H5",
            )
            return {
                "success": False,
                "error": "confirmation_required",
                "message": (
                    "I need you to confirm before posting. "
                    "Please try again — a confirm button should appear."
                ),
                "requires_confirmation": True,
            }
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
    agent_debug_log(
        "planner.py:intercept",
        "destructive write intercepted — not yet posted",
        {
            "tool": tool_name,
            "has_pending_action": True,
            "community_confirmed": tool_args.get("community_confirmed"),
            "title": tool_args.get("title"),
            "returns_success_true": True,
        },
        hypothesis_id="H1",
    )
    return {
        "success": False,
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
        return _plan_navigate(entities, message)
    elif intent == "help":
        rule_plan = _plan_help(message, entities, user_context)
        if rule_plan:
            return rule_plan
        try:
            return await create_plan_llm(message, entities, user_context)
        except Exception as exc:
            logger.warning("create_plan_llm failed (%s) — falling back to no-op plan", exc)
            return []

    try:
        return await create_plan_llm(message, entities, user_context)
    except Exception as exc:
        logger.warning("create_plan_llm failed (%s) — falling back to no-op plan", exc)
        return []


def _plan_search(entities: Dict[str, Any], user_context: Dict[str, Any]) -> List[PlanStep]:
    """Plan for food search."""
    steps = []

    # Only filter by dietary/allergens when the user asked in THIS message
    # (extracted into entities). Do NOT silently apply profile restrictions —
    # that over-filters and makes the agent say "nothing matches halal" when
    # the user just asked for bread.
    dietary_tags = entities.get("dietary_tags") or []
    if isinstance(dietary_tags, str):
        dietary_tags = [dietary_tags]
    exclude_allergens = entities.get("exclude_allergens") or entities.get("allergens") or []
    if isinstance(exclude_allergens, str):
        exclude_allergens = [exclude_allergens]

    pref = user_context.get("preferred_search_params") or {}
    radius = entities.get("radius") or entities.get("radius_km") or pref.get("radius_km") or 10
    food_type = entities.get("food_type") or pref.get("food_type")
    if not dietary_tags and pref.get("dietary_tags"):
        dietary_tags = list(pref.get("dietary_tags") or [])

    search_args = {
        "user_id": _resolve_user_id(user_context),
        "food_type": food_type,
        "radius_km": radius,
        "dietary_tags": dietary_tags,
        "exclude_allergens": exclude_allergens,
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

    listing_id = entities.get("food_id") or entities.get("listing_id")
    if not listing_id:
        steps.append(PlanStep(
            step_number=1,
            action="Search for food to claim",
            tool_name="search_food_near_user",
            tool_args={"user_id": _resolve_user_id(user_context)},
            status="pending",
            result=None,
        ))
        return steps

    steps.append(PlanStep(
        step_number=1,
        action="Claim the food listing",
        tool_name="claim_listing",
        tool_args={
            "user_id": _resolve_user_id(user_context),
            "listing_id": listing_id,
            "quantity": entities.get("quantity", 1),
        },
        status="pending",
        result=None,
    ))

    return steps


def _plan_donate(entities: Dict[str, Any], user_context: Dict[str, Any], message: str) -> List[PlanStep]:
    """Plan for donating food."""
    lang = "es" if str(user_context.get("language") or "").startswith("es") else "en"
    raw_title = entities.get("title") or entities.get("food_type")
    _GENERIC = frozenset({"food", "item", "items", "donation", "share", "sharing"})
    title = None if str(raw_title or "").strip().lower() in _GENERIC else raw_title
    quantity = _parse_quantity(entities.get("quantity")) if entities.get("quantity_stated") else None
    has_location = bool(user_context.get("address") or entities.get("location"))
    food_hint = title or raw_title or "food"

    if not title or quantity is None:
        q = (
            f"What food are you sharing, and about how much?"
            if not title else
            f"About how much {food_hint} are you sharing?"
        )
        if lang == "es":
            q = (
                "¿Qué comida compartes y más o menos cuánto?"
                if not title else
                f"¿Más o menos cuánto {food_hint} compartes?"
            )
        return [PlanStep(
            step_number=1,
            action="Ask for food details (title, quantity, expiry)",
            tool_name="ask_user",
            tool_args={"question": q},
            status="pending",
            result=None,
        )]

    if not has_location:
        q = "Where can people pick this up?" if lang != "es" else "¿Dónde pueden recogerlo?"
        return [PlanStep(
            step_number=1,
            action="Ask for pickup location",
            tool_name="ask_user",
            tool_args={"question": q},
            status="pending",
            result=None,
        )]

    if not entities.get("community_confirmed"):
        from backend.agent.suggestion_chips import _looks_like_community_name

        comm = entities.get("community_name") or user_context.get("community_name")
        if comm and not _looks_like_community_name(str(comm)):
            comm = (
                user_context.get("community_name")
                or user_context.get("organization")
                or user_context.get("default_community_name")
            )
        if comm and not _looks_like_community_name(str(comm)):
            comm = None
        if comm:
            q = (
                f"Should I list this under {comm}?"
                if lang != "es" else
                f"¿Lo publico bajo {comm}?"
            )
        else:
            q = (
                "Which community or school should this donation go under?"
                if lang != "es" else
                "¿En qué comunidad o escuela va esta donación?"
            )
        agent_debug_log(
            "planner.py:_plan_donate",
            "donate plan step chosen",
            {"step": "ask_community", "community_name": comm, "title": title},
            hypothesis_id="H2",
        )
        return [PlanStep(
            step_number=1,
            action="Confirm community before posting",
            tool_name="ask_user",
            tool_args={"question": q},
            status="pending",
            result=None,
        )]

    pickup_addr = user_context.get("address") or entities.get("location") or ""
    comm_label = (
        entities.get("community_name")
        or user_context.get("community_name")
        or ("your community" if lang != "es" else "tu comunidad")
    )

    # Photo — must be its own turn per share-flow rules.
    if not entities.get("image_url") and not entities.get("skip_photo"):
        if not entities.get("photo_prompted"):
            q = (
                "Would you like to add a photo? Listings with photos get claimed much faster."
                if lang != "es" else
                "¿Quieres agregar una foto? Las publicaciones con foto se reclaman mucho más rápido."
            )
            agent_debug_log(
                "planner.py:_plan_donate",
                "donate plan step chosen",
                {"step": "ask_photo", "title": title},
                hypothesis_id="H2",
            )
            return [PlanStep(
                step_number=1,
                action="Ask for optional photo",
                tool_name="ask_user",
                tool_args={"question": q},
                status="pending",
                result=None,
            )]
        if entities.get("awaiting_photo_upload") and not entities.get("image_url"):
            q = (
                "Ready when you are — tap the camera to add a photo, or say 'no photo' to skip."
                if lang != "es" else
                "Cuando quieras — usa la cámara para agregar una foto, o di 'sin foto' para omitir."
            )
            agent_debug_log(
                "planner.py:_plan_donate",
                "donate plan step chosen",
                {"step": "await_photo_upload", "title": title},
                hypothesis_id="H2",
            )
            return [PlanStep(
                step_number=1,
                action="Wait for photo upload",
                tool_name="ask_user",
                tool_args={"question": q},
                status="pending",
                result=None,
            )]

    # Final confirmation before the write.
    if not entities.get("post_confirmed"):
        q = (
            f"Quick check — {title}, {quantity} {entities.get('unit', 'servings')}, "
            f"pickup at {pickup_addr}, under {comm_label}. Post it?"
            if lang != "es" else
            f"Resumen — {title}, {quantity} {entities.get('unit', 'porciones')}, "
            f"recogida en {pickup_addr}, en {comm_label}. ¿Publico?"
        )
        agent_debug_log(
            "planner.py:_plan_donate",
            "donate plan step chosen",
            {"step": "ask_post_confirm", "title": title, "quantity": quantity},
            hypothesis_id="H2",
        )
        return [PlanStep(
            step_number=1,
            action="Confirm before posting",
            tool_name="ask_user",
            tool_args={"question": q},
            status="pending",
            result=None,
        )]

    category = entities.get("food_type") or entities.get("category") or "other"
    if "prepared" in str(category).lower():
        category = "prepared_meals"
    post_args: Dict[str, Any] = {
        "user_id": _resolve_user_id(user_context),
        "title": title,
        "quantity": quantity,
        "unit": entities.get("unit", "servings"),
        "category": category,
        "address": user_context.get("address") or entities.get("location"),
    }
    if entities.get("community_name"):
        from backend.agent.suggestion_chips import _looks_like_community_name
        if _looks_like_community_name(str(entities["community_name"])):
            post_args["community_name"] = entities["community_name"]
        elif user_context.get("community_name") and _looks_like_community_name(
            str(user_context["community_name"])
        ):
            post_args["community_name"] = user_context["community_name"]
    if entities.get("community_id"):
        post_args["community_id"] = entities["community_id"]
    if entities.get("community_confirmed"):
        post_args["community_confirmed"] = True
    if entities.get("image_url"):
        post_args["image_url"] = entities["image_url"]
    if entities.get("expiry_date") or entities.get("prepared_date"):
        post_args["expiry_date"] = entities.get("expiry_date") or entities.get("prepared_date")
    elif entities.get("pickup_time"):
        post_args["expiry_date"] = entities.get("pickup_time")
    else:
        from backend.tools import _suggested_expiry_for_category
        post_args["expiry_date"] = _suggested_expiry_for_category(category)
    if entities.get("post_confirmed"):
        post_args["post_confirmed"] = True
    if user_context.get("address"):
        post_args["location"] = user_context.get("address")

    agent_debug_log(
        "planner.py:_plan_donate",
        "donate plan step chosen",
        {
            "step": "post_food_listing",
            "has_image_url": bool(entities.get("image_url")),
            "photo_prompted": bool(entities.get("photo_prompted")),
            "skip_photo": bool(entities.get("skip_photo")),
            "post_confirmed": bool(entities.get("post_confirmed")),
            "community_confirmed": bool(entities.get("community_confirmed")),
            "community_name": entities.get("community_name"),
            "title": title,
            "quantity": quantity,
        },
        hypothesis_id="H2,H3",
    )

    return [PlanStep(
        step_number=1,
        action="Post food listing",
        tool_name="post_food_listing",
        tool_args=post_args,
        status="pending",
        result=None,
    )]


def _plan_help(
    message: str,
    entities: Dict[str, Any],
    user_context: Dict[str, Any],
) -> List[PlanStep]:
    """Rule-based tool picks for common platform-help questions."""
    lo = message.lower()
    uid = _resolve_user_id(user_context)

    def _step(tool_name: str, tool_args: Dict[str, Any], action: str) -> PlanStep:
        return PlanStep(
            step_number=1,
            action=action,
            tool_name=tool_name,
            tool_args=tool_args,
            status="pending",
            result=None,
        )

    if any(kw in lo for kw in ("cancel", "release", "withdraw")) and "claim" in lo:
        return [_step("get_my_claims", {"user_id": uid}, "Fetch user's active claims")]

    if any(kw in lo for kw in ("my claims", "claims do i have", "did my claim", "claim status", "claim go through")):
        return [_step("get_my_claims", {"user_id": uid}, "Fetch user's claims")]

    if any(kw in lo for kw in (
        "my pickup", "my pickups", "pickups", "pick up", "pickup",
        "recogida", "recogidas", "mis reserv", "mis reclam",
    )):
        return [_step("get_my_claims", {"user_id": uid}, "Fetch user's pickups")]

    if any(kw in lo for kw in (
        "i'm hungry", "im hungry", "tengo hambre", "need food", "want food",
        "something to eat", "find food", "buscar comida", "comida cerca",
    )):
        return _plan_search(entities, user_context)

    if any(kw in lo for kw in ("what should i claim", "what can i claim", "what to claim", "recommend")):
        return _plan_search(entities, user_context)

    if any(kw in lo for kw in ("my listings", "who claimed", "any claims", "views does my listing")):
        return [_step("get_user_listings", {"user_id": uid}, "Fetch user's listings")]

    if any(kw in lo for kw in ("my impact", "how much have i", "stats")):
        return [_step("get_my_impact_summary", {"user_id": uid}, "Fetch impact summary")]

    return []


def _resolve_nav_tool_args(message: str, entities: Dict[str, Any]) -> Dict[str, Any]:
    """Map natural-language navigation requests to ui_action payloads."""
    lo = (message or "").lower()
    page = str(entities.get("page") or "").lower().strip().lstrip("/")

    if any(k in lo for k in (" map", "map ", "near me", "nearby", "near-me", "the map", "open map")) or lo.strip() in ("map",):
        return {"action": "open_map"}
    if any(k in lo for k in ("find food", "browse food", "search food", "buscar comida")) or page in ("find", "find-food"):
        return {"action": "navigate", "path": "/find"}
    if any(k in lo for k in ("share food", "donate", "post food", "compartir", "donar")) or page in ("share", "donate", "share-food"):
        return {"action": "navigate", "path": "/share"}
    if "recipe" in lo or "receta" in lo or page == "recipes":
        return {"action": "navigate", "path": "/recipes"}
    if "setting" in lo:
        return {"action": "navigate", "path": "/settings"}
    if "profile" in lo or "account" in lo or page == "profile":
        return {"action": "navigate", "path": "/profile"}
    if any(k in lo for k in ("notification", "notificacion")) or page == "notifications":
        return {"action": "navigate", "path": "/notifications"}
    if any(k in lo for k in ("dashboard", "home", "inicio")) or page == "dashboard":
        return {"action": "navigate", "path": "/dashboard"}

    target_page = entities.get("page") or "dashboard"
    path = target_page if str(target_page).startswith("/") else f"/{target_page}"
    return {"action": "navigate", "path": path}


def _plan_navigate(entities: Dict[str, Any], message: str = "") -> List[PlanStep]:
    """Plan for navigation."""
    nav_args = _resolve_nav_tool_args(message, entities)
    label = nav_args.get("path") or nav_args.get("action", "page")

    return [PlanStep(
        step_number=1,
        action=f"Navigate to {label}",
        tool_name="navigate_ui",
        tool_args=nav_args,
        status="pending",
        result=None,
    )]


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

    user_id = _resolve_user_id(user_context) or ""
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
        "storage tips, the user's claims/listings, etc.). Platform how-to "
        "questions ('how do I cancel my claim?', 'did my claim go through?') "
        "SHOULD call get_my_claims or another read tool — do not answer "
        "from memory alone. If the message is casual conversation or a "
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
    tool_args = dict(step.get("tool_args", {}) or {})
    effective_user_id = user_id or _resolve_user_id(user_context)
    # Rule-based planners embed user_id=None when profile rows only have `id`.
    # Only backfill when the key is present but falsy — do not inject into
    # tools that never asked for user_id (e.g. get_recipes).
    if effective_user_id and "user_id" in tool_args and not tool_args.get("user_id"):
        tool_args["user_id"] = effective_user_id

    # Normalize claim args: registry uses listing_id; older planner paths used food_id.
    if tool_name == "claim_listing":
        if not tool_args.get("listing_id"):
            tool_args["listing_id"] = tool_args.pop("food_id", None)
        if "quantity_requested" in tool_args and "quantity" not in tool_args:
            tool_args["quantity"] = tool_args.pop("quantity_requested")

    if tool_name == "post_food_listing" and tool_args.get("quantity") is not None:
        parsed_qty = _parse_quantity(tool_args.get("quantity"))
        if parsed_qty is not None:
            tool_args["quantity"] = parsed_qty

    if tool_name == "post_food_listing":
        last_entities = (user_context or {}).get("last_intent_entities") or {}
        if not tool_args.get("community_confirmed") and last_entities.get("community_confirmed"):
            tool_args["community_confirmed"] = True
        if not tool_args.get("community_name") and last_entities.get("community_name"):
            tool_args["community_name"] = last_entities["community_name"]
        if not tool_args.get("community_id") and last_entities.get("community_id"):
            tool_args["community_id"] = last_entities["community_id"]
        if not tool_args.get("expiry_date"):
            from backend.tools import _suggested_expiry_for_category
            tool_args["expiry_date"] = _suggested_expiry_for_category(
                tool_args.get("category") or "other",
            )

    if tool_name != "ask_user" and _args_have_placeholders(tool_args):
        logger.info("Skipping %s — plan still has unfilled placeholders", tool_name)
        return {
            "skipped": True,
            "requires_user_input": True,
            "reason": "awaiting_user_input",
            "tool": tool_name,
        }

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
        agent_debug_log(
            "planner.py:execute_plan_step",
            "post intercept returned to graph",
            {
                "intercepted": True,
                "success_flag": intercept.get("success"),
                "listing_id": intercept.get("listing_id"),
                "requires_confirmation": intercept.get("requires_confirmation"),
            },
            hypothesis_id="H1,H5",
        )
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
        if tool_name == "post_food_listing":
            agent_debug_log(
                "planner.py:execute_plan_step",
                "post_food_listing dispatch result",
                {
                    "success": result.get("success") if isinstance(result, dict) else None,
                    "error": result.get("error") if isinstance(result, dict) else None,
                    "listing_id": result.get("listing_id") if isinstance(result, dict) else None,
                    "intercepted": False,
                },
                hypothesis_id="H4,H5",
            )
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
