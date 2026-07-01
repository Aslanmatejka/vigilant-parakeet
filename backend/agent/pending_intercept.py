"""
Destructive-Intent Interception (AGENT_V2 — Phase 4 full)
==========================================================

Turns a "delete this / cancel my claim / leave my community / forget me"
style turn into a `pending_action` envelope INSTEAD of running the v1
graph and firing the destructive write immediately.

The frontend renders a Confirm/Cancel card from the `pending_action`
payload and later resolves it via `POST /api/ai/confirm`, which calls
`commit_pending_action` (or `cancel_pending_action`) on the action
framework.

Pure logic module — no OpenAI, no Supabase. All Supabase writes go
through `backend.agent.actions.plan_action()`.

Scope for this pass:

- Zero-arg destructive intents: `leave_community`, `forget_about_me`.
  Always intercept when confidence >= floor.

- One-arg destructive intents where the target is unambiguous from the
  world snapshot: `cancel_claim` (exactly one open claim),
  `delete_listing` (exactly one open listing).

- Everything else falls through to v1 and is handled by the post-hoc
  audit + `confirmation_recommended` banner path already in place.

The bar for interception is intentionally high: we only queue a pending
action when we can produce a truthful, specific summary the user can
confirm without additional questions. Anything ambiguous stays on v1,
where the (existing) confirmation policy still surfaces an undo banner.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


#: Minimum confidence required to queue a pending action. Below this we
#: still short-circuit to a *clarifying question* (via the existing
#: reasoning path) rather than committing a pending row the user might
#: not recognize.
_MIN_INTERCEPT_CONFIDENCE: float = 0.55


@dataclass
class InterceptedAction:
    tool: str
    args: dict[str, Any]
    summary_en: str
    summary_es: str


def _first(items: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    return items[0] if items else None


def build_intercepted_action(
    *,
    intent: str,
    confidence: float,
    world_snapshot: Any,          # WorldSnapshot | None (duck-typed)
    language: str = "en",
) -> Optional[InterceptedAction]:
    """Return an InterceptedAction iff the intent is a destructive one we can
    queue with a truthful, specific summary. Otherwise None."""
    if not intent:
        return None
    if confidence is not None and confidence < _MIN_INTERCEPT_CONFIDENCE:
        return None

    intent_n = intent.strip().lower()

    if intent_n == "leave_community":
        # Zero-arg. The action handler looks up the current community.
        community_name = _current_community_name(world_snapshot)
        return InterceptedAction(
            tool="leave_community",
            args={},
            summary_en=(
                f"Leave community: {community_name}." if community_name
                else "Leave your current community."
            ),
            summary_es=(
                f"Dejar la comunidad: {community_name}." if community_name
                else "Dejar tu comunidad actual."
            ),
        )

    if intent_n == "forget_about_me":
        # Zero-arg destructive delete on agent_user_facts.
        return InterceptedAction(
            tool="forget_about_me",
            args={},
            summary_en="Delete everything the assistant has learned about you.",
            summary_es="Borrar todo lo que el asistente ha aprendido sobre ti.",
        )

    if intent_n == "cancel_claim":
        claim = _sole_open_claim(world_snapshot)
        if not claim:
            return None
        cid = str(claim.get("id") or "")
        if not cid:
            return None
        title = _listing_title_for_claim(claim)
        return InterceptedAction(
            tool="cancel_claim",
            args={"claim_id": cid},
            summary_en=(
                f"Release your claim on '{title}'." if title
                else "Release your active claim."
            ),
            summary_es=(
                f"Liberar tu reserva de '{title}'." if title
                else "Liberar tu reserva activa."
            ),
        )

    if intent_n == "delete_listing":
        listing = _sole_open_listing(world_snapshot)
        if not listing:
            return None
        lid = str(listing.get("id") or "")
        if not lid:
            return None
        title = str(listing.get("title") or "").strip()
        return InterceptedAction(
            tool="delete_listing",
            args={"listing_id": lid, "confirmed": True},
            summary_en=(
                f"Permanently delete your listing '{title}'." if title
                else "Permanently delete your listing."
            ),
            summary_es=(
                f"Borrar permanentemente tu publicación '{title}'." if title
                else "Borrar permanentemente tu publicación."
            ),
        )

    return None


# ============================================================================
# WorldSnapshot accessors — duck-typed so tests can pass simple dicts.
# ============================================================================

def _get_attr(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _current_community_name(world_snapshot: Any) -> Optional[str]:
    communities = _get_attr(world_snapshot, "communities") or []
    if not communities:
        return None
    first = communities[0]
    if isinstance(first, str):
        return first.strip() or None
    if isinstance(first, dict):
        return (first.get("name") or first.get("community_name") or "").strip() or None
    return None


def _sole_open_claim(world_snapshot: Any) -> Optional[dict[str, Any]]:
    claims = _get_attr(world_snapshot, "open_claims") or []
    count = _get_attr(world_snapshot, "open_claims_count", len(claims)) or 0
    if len(claims) != 1 or int(count) != 1:
        return None
    claim = _first(claims)
    if not isinstance(claim, dict):
        return None
    return claim


def _sole_open_listing(world_snapshot: Any) -> Optional[dict[str, Any]]:
    listings = _get_attr(world_snapshot, "open_listings") or []
    count = _get_attr(world_snapshot, "open_listings_count", len(listings)) or 0
    if len(listings) != 1 or int(count) != 1:
        return None
    listing = _first(listings)
    if not isinstance(listing, dict):
        return None
    return listing


def _listing_title_for_claim(claim: dict[str, Any]) -> str:
    # Claims sometimes carry a joined listing dict.
    listing = claim.get("food_listings") or claim.get("listing") or {}
    if isinstance(listing, dict):
        title = str(listing.get("title") or "").strip()
        if title:
            return title
    return str(claim.get("title") or "").strip()


# ============================================================================
# Response-shaping helper
# ============================================================================

def build_pending_action_envelope(
    *,
    pending_id: str,
    tool: str,
    args: dict[str, Any],
    summary: str,
    expires_at: Optional[str] = None,
) -> dict[str, Any]:
    """Shape a `pending_action` object the frontend already renders.

    Matches the shape the AIChatPanel `PendingActionCard` reads (see
    utils/services/aiChatService.js — `data.pending_action`).
    """
    return {
        "pending_id": pending_id,
        "tool": tool,
        "summary": summary,
        "args": dict(args or {}),
        "requires_confirmation": True,
        "expires_at": expires_at,
    }


def format_intercept_text(
    intercept: InterceptedAction, *, language: str = "en",
) -> str:
    """User-facing confirmation prose. Kept short + specific."""
    if language.startswith("es"):
        return (
            f"{intercept.summary_es}\n\nConfirma o cancela abajo para continuar."
        )
    return (
        f"{intercept.summary_en}\n\nConfirm or cancel below to proceed."
    )


__all__ = [
    "InterceptedAction",
    "build_intercepted_action",
    "build_pending_action_envelope",
    "format_intercept_text",
]
