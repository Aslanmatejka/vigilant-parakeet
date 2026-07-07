"""Conversation context helpers shared by the agent.

Listing reference resolution, memory snapshots, and sticky language
detection originally lived inside ``ConversationEngine.chat()``; they
are extracted here so the LangGraph agent gets the same multi-turn
behaviour without a second orchestrator.
"""

from __future__ import annotations

from typing import Any, Optional

from backend.ai_engine import (
    _build_memory_snapshot,
    _resolve_listing_reference,
    _role_behavior_prompt,
    conversation_engine,
    detect_english,
    detect_spanish,
)


def detect_language_sticky(
    message: str,
    history: Optional[list[dict[str, Any]]] = None,
    profile: Optional[dict[str, Any]] = None,
) -> str:
    """Sticky en/es detection — short replies inherit conversation language."""
    return conversation_engine._detect_lang_sticky(message, history=history, profile=profile)


def resolve_listing_reference(
    message: str,
    history: list[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    """Map '#3' / 'the bread' to a listing from the latest search."""
    return _resolve_listing_reference(message, history)


def build_memory_snapshot(history: list[dict[str, Any]]) -> Optional[str]:
    """Compact summary of recent listings/claims/posts for prompt context."""
    return _build_memory_snapshot(history)


def filter_history_for_context(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop silent / internal rows before injecting history into the agent."""
    filtered: list[dict[str, Any]] = []
    for row in history or []:
        if not isinstance(row, dict):
            continue
        meta = row.get("metadata") or {}
        if meta.get("silent_trigger") or meta.get("silent"):
            continue
        if row.get("role") == "user":
            text = str(row.get("message") or "").lstrip()
            if text.startswith(("[Action completed]", "[Acción completada]", "[Accion completada]")):
                continue
        filtered.append(row)
    return filtered


    return filtered


def format_language_lock(language: str) -> str:
    """Strong per-turn language instruction (matches legacy chat engine)."""
    if language == "es":
        return (
            "The user is communicating in Spanish. You MUST respond ENTIRELY in "
            "Spanish for this turn and every following turn unless the user "
            "explicitly switches language. This includes reply text, tool-result "
            "summaries, confirmation prompts, and follow-up questions."
        )
    return (
        "The user is communicating in English. You MUST respond ENTIRELY in "
        "English for this turn, even if earlier turns were in Spanish. Match "
        "the user's current language for all reply text, summaries, and prompts."
    )


def format_rich_user_context(
    user_context: dict[str, Any],
    user_id: str,
    *,
    language: str = "en",
) -> str:
    """Per-turn profile facts block so the model does not re-ask known fields."""
    lines = [
        "## KNOWN USER FACTS (DO NOT RE-ASK)",
        "These fields are already on file. Use them as defaults for tool calls. "
        "Only ask when a value is missing or the user asks to use something different.",
        f"Current user: {user_context.get('name') or 'Community Member'} (ID: {user_id})",
    ]
    role = user_context.get("role") or user_context.get("community_role") or "member"
    lines.append(f"role: {role}")
    community_role = user_context.get("community_role")
    if community_role:
        lines.append(f"community role: {community_role}")

    if user_context.get("address"):
        lines.append(f"profile address on file: {user_context['address']}")
    else:
        lines.append("NO profile address on file (needed to post listings)")

    try:
        raw_lat = user_context.get("lat") or user_context.get("latitude")
        raw_lng = user_context.get("lng") or user_context.get("longitude")
        p_lat = float(raw_lat) if raw_lat is not None else None
        p_lng = float(raw_lng) if raw_lng is not None else None
    except (TypeError, ValueError):
        p_lat, p_lng = None, None
    if p_lat is not None and p_lng is not None:
        lines.append(
            f"profile coordinates: lat={p_lat:.6f}, lng={p_lng:.6f} — use as origin "
            "for search_food_near_user and distance tools; do NOT ask where they are."
        )

    if user_context.get("phone"):
        lines.append(f"phone on file: {user_context['phone']}")
    dietary = user_context.get("dietary_restrictions")
    if dietary:
        lines.append(f"dietary restrictions: {dietary}")
    allergens = user_context.get("allergies") or user_context.get("allergens")
    if allergens:
        lines.append(f"allergens: {allergens} — never suggest matching food")

    role_hint = _role_behavior_prompt(str(role), lang=language)
    if role_hint:
        lines.append(role_hint)

    lines.append(format_language_lock(language))
    return "\n".join(lines)


__all__ = [
    "build_memory_snapshot",
    "detect_language_sticky",
    "detect_english",
    "detect_spanish",
    "filter_history_for_context",
    "format_language_lock",
    "format_rich_user_context",
    "resolve_listing_reference",
]
