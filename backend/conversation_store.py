"""Conversation persistence — shared by the LangGraph agent and API routes.

History rows live in ``ai_conversations``. The agent is the sole chat
orchestrator; this module owns read/write access so nothing depends on
``ConversationEngine.chat()``.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from backend.ai_engine import supabase_get, supabase_post

logger = logging.getLogger(__name__)

_NIL_UUID = "00000000-0000-0000-0000-000000000000"


async def get_conversation_history(
    user_id: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return chronological chat rows (oldest → newest) for a user."""
    try:
        rows = await supabase_get("ai_conversations", {
            "user_id": f"eq.{user_id}",
            "select": "id,role,message,metadata,created_at",
            "order": "created_at.desc",
            "limit": str(limit),
        })
    except Exception as exc:  # noqa: BLE001
        logger.error("get_conversation_history failed for %s: %s", user_id, exc)
        return []
    rows.reverse()
    return [
        {
            "id": r.get("id"),
            "role": r.get("role", "user"),
            "message": r.get("message", ""),
            "metadata": r.get("metadata") or {},
            "created_at": r.get("created_at", ""),
        }
        for r in rows
    ]


async def store_message(
    user_id: str,
    role: str,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> Optional[str]:
    """Persist one chat row; returns the new row id when available."""
    if not user_id or user_id == _NIL_UUID or user_id.startswith("00000000"):
        return None
    try:
        result = await supabase_post("ai_conversations", {
            "user_id": user_id,
            "role": role,
            "message": message,
            "metadata": metadata or {},
        })
    except Exception as exc:  # noqa: BLE001
        logger.error("store_message failed for %s: %s", user_id, exc)
        return None
    if isinstance(result, list) and result:
        return result[0].get("id")
    if isinstance(result, dict):
        return result.get("id")
    return None


__all__ = ["get_conversation_history", "store_message"]
