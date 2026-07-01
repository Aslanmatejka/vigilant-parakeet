"""
AGENT_V2 Telemetry (Phase 8)
============================

Best-effort per-turn writer for the `agent_v2_telemetry` table. Never
raises — a telemetry failure MUST NOT break a user-facing chat turn. The
schema lives in `supabase/migrations/20260701000001_agent_v2_telemetry.sql`.

Design:
- One row per successful `invoke_agent_v2` call, fired-and-forgotten via
  `asyncio.create_task` from the caller. We accept a tolerant snapshot
  dict rather than forcing the caller to build every field.
- Anonymous (nil-UUID) turns are skipped: RLS on the table requires a
  real actor and the analytics we care about are per authenticated user
  anyway.
- Rollout context is stamped so every row records what percentage /
  bucket routing was in effect. Makes it trivial to correlate a bump
  from 25% to 100% with a change in reward / retry rate.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


_NIL_UUID_PREFIX = "00000000"


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _safe_float(v: Any) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _safe_bool(v: Any, default: bool = False) -> bool:
    if v is None:
        return default
    return bool(v)


def _cap_str(v: Any, n: int) -> Optional[str]:
    if v is None:
        return None
    s = str(v)
    return s[:n] if len(s) > n else s


def build_v2_telemetry_row(response: dict[str, Any]) -> dict[str, Any]:
    """Distill the fat v2 response dict into a lean telemetry row. Pure
    function so tests can assert the exact shape without a Supabase mock."""
    from backend.agent.rollout import bucket_for_user, rollout_percentage

    user_id = response.get("user_id")

    affect = response.get("affect") or {}
    register = response.get("register") or {}
    reflection = response.get("reflection") or {}
    self_eval = response.get("self_eval") or {}
    persona = response.get("persona_check") or {}
    world = response.get("world_model") or {}
    goals = response.get("goals") or []

    tool_results = response.get("tool_results") or []
    tool_success = 0
    tool_failure = 0
    for tr in tool_results:
        if not isinstance(tr, dict):
            continue
        res = tr.get("result") if isinstance(tr.get("result"), dict) else None
        ok = bool(res and not res.get("error") and res.get("success") is not False)
        if ok:
            tool_success += 1
        else:
            tool_failure += 1

    row = {
        "user_id": user_id,
        "conversation_id": response.get("conversation_id"),
        "turn_id": response.get("turn_id"),

        "rollout_pct": rollout_percentage(),
        "rollout_bucket": bucket_for_user(user_id) if user_id else None,

        "detected_intent": _cap_str(
            (response.get("reasoning_trace") or [{}])[0].get("intent")
            if response.get("reasoning_trace") else None,
            60,
        ),
        "confidence": _safe_float(response.get("confidence")),
        "affect_dominant": _cap_str(affect.get("dominant"), 30),
        "register_tone": _cap_str(register.get("tone"), 30),

        "response_length": len(response.get("text") or ""),
        "reflection_outcome": _cap_str(reflection.get("outcome"), 30),
        "self_eval_overall": _safe_float(self_eval.get("overall")),
        "reward": _safe_float(response.get("reward")),

        "retried": _safe_bool(response.get("retried")),
        "pushback_detected": _safe_bool(response.get("pushback_detected")),
        "persona_ok": _safe_bool(persona.get("ok", True), default=True),
        "safe_text_changed": False,  # set by caller if it wants precision
        "brainstorm_used": _safe_bool(response.get("brainstorm_used")),
        "curiosity_followup": bool(response.get("curiosity_followup")),
        "confirmation_recommended": _safe_bool(
            response.get("confirmation_recommended")
        ),

        "listings_blocked": len(response.get("blocked_listings") or []),
        "tool_success_count": tool_success,
        "tool_failure_count": tool_failure,

        "memories_retrieved": len(response.get("memories") or []),
        "memories_written": len(response.get("new_memories") or []),
        "open_goals": sum(
            1 for g in goals
            if isinstance(g, dict) and g.get("status") in ("open", "in_progress")
        ),
        "few_shot_examples": len(response.get("few_shot_examples") or []),

        "elapsed_ms": _safe_int(response.get("_elapsed_ms")),
        "tokens_input": _safe_int(response.get("_tokens_input")),
        "tokens_output": _safe_int(response.get("_tokens_output")),
    }
    return row


async def log_v2_turn(response: dict[str, Any]) -> None:
    """Fire-and-forget writer. Safe to `asyncio.create_task(log_v2_turn(...))`.

    Skips anonymous turns and swallows any error — telemetry failures must
    NEVER surface to the user.
    """
    try:
        user_id = response.get("user_id")
        if not user_id or str(user_id).startswith(_NIL_UUID_PREFIX):
            return

        row = build_v2_telemetry_row(response)

        try:
            from backend.ai_engine import supabase_post
        except Exception as exc:  # noqa: BLE001
            logger.debug("agent_v2 telemetry skipped (no supabase_post): %s", exc)
            return

        await supabase_post("agent_v2_telemetry", row)
    except Exception as exc:  # noqa: BLE001 — telemetry must never raise
        logger.warning("agent_v2 telemetry insert failed (non-fatal): %s", exc)


__all__ = [
    "build_v2_telemetry_row",
    "log_v2_turn",
]
