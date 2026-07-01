"""
Per-user World Model (AGENT_V2 — Phase 3 lite)
=================================================

A small, turn-scoped snapshot of the user's current state inside the
food-sharing system. Injected as a `<world>` block in the system prompt
so the LLM can ground answers like "I just claimed something — when do
I pick it up?" without re-querying tools.

This module is intentionally read-only and best-effort:

- Every Supabase query is wrapped — any failure returns the partial
  snapshot collected so far.
- All counts/lists are capped so the prompt never blows past its budget.
- The snapshot dataclass is lazily evaluable: an empty `WorldSnapshot`
  is a valid result and renders to an empty string.

Public API:

    WorldSnapshot                              # dataclass + to_dict + render_block()
    build_world_snapshot(user_id, *, is_admin=False)  # async, supabase-backed
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# Types
# ============================================================================

@dataclass
class WorldSnapshot:
    """Per-user current-state snapshot. All fields are best-effort.

    Empty snapshot (no Supabase / new user) → renders to "".
    """
    user_id: str
    user_name: Optional[str] = None
    dietary_restrictions: list[str] = field(default_factory=list)
    allergies: list[str] = field(default_factory=list)
    address: Optional[str] = None

    # Activity
    open_claims_count: int = 0
    open_claims: list[dict[str, Any]] = field(default_factory=list)
    open_listings_count: int = 0
    open_listings: list[dict[str, Any]] = field(default_factory=list)
    communities: list[str] = field(default_factory=list)

    # Metadata
    fetched_at: str = ""
    is_admin: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "user_name": self.user_name,
            "dietary_restrictions": list(self.dietary_restrictions),
            "allergies": list(self.allergies),
            "address": self.address,
            "open_claims_count": self.open_claims_count,
            "open_claims": list(self.open_claims),
            "open_listings_count": self.open_listings_count,
            "open_listings": list(self.open_listings),
            "communities": list(self.communities),
            "fetched_at": self.fetched_at,
            "is_admin": self.is_admin,
        }

    def is_empty(self) -> bool:
        return not (
            self.dietary_restrictions or self.allergies or self.address
            or self.open_claims_count or self.open_listings_count
            or self.communities
        )

    def render_block(self) -> str:
        """Render the snapshot as a `<world>` markdown block suitable for
        inclusion in the system prompt. Returns "" when empty."""
        if self.is_empty():
            return ""
        lines: list[str] = ["<world>"]
        if self.user_name:
            lines.append(f"name: {self.user_name}")
        if self.dietary_restrictions:
            lines.append("dietary: " + ", ".join(self.dietary_restrictions))
        if self.allergies:
            lines.append("allergies: " + ", ".join(self.allergies))
        if self.address:
            lines.append(f"address: {self.address}")
        if self.open_claims_count:
            lines.append(f"open_claims: {self.open_claims_count}")
        if self.open_listings_count:
            lines.append(f"open_listings: {self.open_listings_count}")
        if self.communities:
            lines.append("communities: " + ", ".join(self.communities[:5]))
        lines.append("</world>")
        return "\n".join(lines)


# ============================================================================
# Builder
# ============================================================================

#: Statuses we treat as "open / pending" on the claims side.
_OPEN_CLAIM_STATUSES = {"pending", "approved", "confirmed", "in_progress"}

#: Statuses we treat as "active" on the listings side.
_ACTIVE_LISTING_STATUSES = {"available", "active", "open"}


async def _safe_get(table: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    """Wrap supabase_get so any failure returns []."""
    try:
        from backend.ai_engine import supabase_get
        rows = await supabase_get(table, params)
        return rows or []
    except Exception as exc:  # noqa: BLE001
        logger.info("world_model._safe_get(%s) failed: %s", table, exc)
        return []


def _coerce_str_list(value: Any) -> list[str]:
    """Normalise the JSONB/array fields used for dietary/allergies/communities."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if v and str(v).strip()]
    if isinstance(value, str):
        # Comma- or pipe-separated string.
        return [
            p.strip() for p in value.replace("|", ",").split(",")
            if p.strip()
        ]
    return []


async def build_world_snapshot(
    user_id: str,
    *,
    is_admin: bool = False,
    claim_limit: int = 5,
    listing_limit: int = 5,
) -> WorldSnapshot:
    """Build the per-turn world snapshot for `user_id`.

    Runs the three sub-queries (profile / claims / listings) in parallel
    to keep the per-turn overhead under ~200ms in practice. Anonymous /
    nil-UUID callers short-circuit to an empty snapshot.
    """
    snap = WorldSnapshot(
        user_id=user_id,
        is_admin=is_admin,
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )
    if not user_id or user_id.startswith("00000000"):
        return snap

    profile_task = _safe_get("users", {
        "id": f"eq.{user_id}",
        "select": "id,full_name,address,dietary_restrictions,allergies,communities",
        "limit": "1",
    })
    claims_task = _safe_get("food_claims", {
        "claimer_id": f"eq.{user_id}",
        "select": "id,listing_id,status,created_at,pickup_at",
        "order": "created_at.desc",
        "limit": str(max(1, int(claim_limit)) * 3),
    })
    listings_task = _safe_get("food_listings", {
        "donor_id": f"eq.{user_id}",
        "select": "id,title,status,created_at,expires_at",
        "order": "created_at.desc",
        "limit": str(max(1, int(listing_limit)) * 3),
    })

    try:
        profile_rows, claim_rows, listing_rows = await asyncio.gather(
            profile_task, claims_task, listings_task,
            return_exceptions=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.info("build_world_snapshot: gather failed (%s)", exc)
        return snap

    # ---- profile ----
    if isinstance(profile_rows, list) and profile_rows:
        p = profile_rows[0]
        if isinstance(p, dict):
            snap.user_name = p.get("full_name")
            snap.address = p.get("address")
            snap.dietary_restrictions = _coerce_str_list(p.get("dietary_restrictions"))
            snap.allergies = _coerce_str_list(p.get("allergies"))
            snap.communities = _coerce_str_list(p.get("communities"))

    # ---- claims (filter to "open" + truncate) ----
    if isinstance(claim_rows, list):
        open_claims = [
            c for c in claim_rows
            if isinstance(c, dict)
            and str(c.get("status") or "").lower() in _OPEN_CLAIM_STATUSES
        ]
        snap.open_claims_count = len(open_claims)
        snap.open_claims = open_claims[: max(0, int(claim_limit))]

    # ---- listings (filter to "active" + truncate) ----
    if isinstance(listing_rows, list):
        active_listings = [
            l for l in listing_rows
            if isinstance(l, dict)
            and str(l.get("status") or "").lower() in _ACTIVE_LISTING_STATUSES
        ]
        snap.open_listings_count = len(active_listings)
        snap.open_listings = active_listings[: max(0, int(listing_limit))]

    return snap


__all__ = [
    "WorldSnapshot",
    "build_world_snapshot",
]
