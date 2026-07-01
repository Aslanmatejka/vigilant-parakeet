"""
AGENT_V2 Gradual Rollout (Phase 8)
==================================

Percentage-based routing between the v1 graph and the v2 wrapper so we can
promote v2 traffic incrementally (5% -> 25% -> 100%) without a redeploy.

Two knobs (both read from env each call so ops can flip them live):

    AGENT_V2                – master enable switch (bool).
                              When "false" nothing else in this module has
                              any effect and every user stays on v1.
    AGENT_V2_ROLLOUT_PCT    – integer 0-100. Fraction of authenticated
                              users routed to v2. Defaults to 100 so
                              existing "AGENT_V2=true" deployments keep
                              their current behavior (v2 for everyone).

Routing rule for authenticated users:
    bucket = int(md5(user_id).hexdigest()[:8], 16) % 100
    v2 = bucket < clamp(AGENT_V2_ROLLOUT_PCT, 0, 100)

Two guardrails:
- Anonymous (nil-UUID) turns always stay on v1. v2's memory + trajectory
  writes require a real user_id and RLS would reject the insert anyway.
- The bucket is derived from a *stable* hash of the user_id, so a given
  user consistently lands on v1 or v2 across turns. That keeps the
  conversation coherent (they won't see the tone/reasoning suddenly
  change mid-session) and makes A/B analysis clean.

Pure-Python module: no Supabase, no LangGraph, no LLM. Safe to import in
any environment.
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


_NIL_UUID_PREFIX = "00000000"


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("true", "1", "yes", "on")


def _pct_env(name: str, default: int = 100) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(0, min(100, int(str(raw).strip())))
    except (TypeError, ValueError):
        logger.warning("invalid %s=%r; falling back to %d", name, raw, default)
        return default


def is_agent_v2_globally_enabled() -> bool:
    """Master switch. Independent of any user."""
    return _bool_env("AGENT_V2", False)


def rollout_percentage() -> int:
    """Currently configured percentage (0-100)."""
    return _pct_env("AGENT_V2_ROLLOUT_PCT", 100)


def bucket_for_user(user_id: Optional[str]) -> int:
    """Stable 0-99 bucket for a user_id. Missing / empty ids get bucket 100
    which is outside the valid range so they never match any percentage."""
    if not user_id:
        return 100
    digest = hashlib.md5(user_id.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


def is_agent_v2_enabled_for_user(user_id: Optional[str]) -> bool:
    """The routing decision the chat handler should ask for every turn.

    Returns True iff:
      1. AGENT_V2 env is on.
      2. user_id is present and not the anonymous nil-UUID.
      3. The user's stable bucket falls under AGENT_V2_ROLLOUT_PCT.
    """
    if not is_agent_v2_globally_enabled():
        return False
    if not user_id or user_id.startswith(_NIL_UUID_PREFIX):
        return False
    pct = rollout_percentage()
    if pct <= 0:
        return False
    if pct >= 100:
        return True
    return bucket_for_user(user_id) < pct


def rollout_snapshot() -> dict[str, object]:
    """Snapshot of the current knobs. Used by /api/ai/health-style endpoints
    and telemetry rows so ops can see what routing was in effect at time t."""
    return {
        "enabled": is_agent_v2_globally_enabled(),
        "rollout_pct": rollout_percentage(),
    }


__all__ = [
    "bucket_for_user",
    "is_agent_v2_enabled_for_user",
    "is_agent_v2_globally_enabled",
    "rollout_percentage",
    "rollout_snapshot",
]
