"""
Action Registrations (AGENT_V2)
================================

Bridges the legacy `backend.tools._<handler>` functions into the typed
action framework defined in `backend.agent.actions`.

For each WRITE the legacy agent can perform we register:

- `handler`         — wrapper that runs the underlying tool and unpacks
                      its return dict into the
                      `(after_state, target_table, target_id)` tuple the
                      action framework expects.
- `fetch_before`    — optional SELECT that captures the row(s) about to be
                      mutated so the audit log records a meaningful diff.
- `rollback`        — compensating action that reverses the write using
                      the snapshot stored on the audit row. Returns
                      `True` only when the rollback is observably complete.
- `requires_confirmation` — `True` for destructive or hard-to-reverse
                      writes; `False` for low-risk writes (notifications,
                      reminders, "read" flags) that should commit
                      immediately.
- `summary_template` — human-readable string rendered into the pending
                      confirmation card.

This module is imported (lazily, via try/except) from `backend.agent.__init__`
so the side-effectful `register_action(...)` calls fire on first import.

All Supabase access is funneled through the existing `backend.ai_engine`
REST helpers — never the supabase-py client — to stay consistent with the
rest of the agent.
"""

from __future__ import annotations

import logging
from typing import Any

from backend.agent.actions import register_action

logger = logging.getLogger(__name__)


# ============================================================================
# Internal helpers
# ============================================================================

def _ok(result: Any) -> bool:
    """Treat dict-shaped tool results as successful only when explicitly OK."""
    if not isinstance(result, dict):
        return False
    if result.get("error"):
        return False
    return bool(result.get("success") or result.get("ok"))


def _coerce_id(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


# ============================================================================
# claim_listing
# ============================================================================

async def _fetch_before_claim(args: dict[str, Any], user_id: str) -> dict[str, Any] | None:
    """Snapshot the listing row before we claim against it."""
    from backend.ai_engine import supabase_get

    listing_id = args.get("listing_id") or args.get("food_id")
    if not listing_id:
        return None
    try:
        rows = await supabase_get("food_listings", {
            "id": f"eq.{listing_id}",
            "select": "id,title,quantity,status",
            "limit": "1",
        })
        return rows[0] if rows else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("fetch_before claim_listing failed: %s", exc)
        return None


async def _handle_claim(args: dict[str, Any], user_id: str):
    from backend.tools import _claim_food_listing

    result = await _claim_food_listing(user_id=user_id, **args)
    if not _ok(result):
        raise RuntimeError(result.get("error") or "claim_listing failed")
    after = {
        "claim_id": _coerce_id(result.get("claim_id")),
        "listing_id": _coerce_id(result.get("listing_id") or args.get("listing_id")),
        "quantity": result.get("quantity"),
        "status": result.get("status") or "approved",
    }
    return after, "food_claims", _coerce_id(result.get("claim_id"))


async def _rollback_claim(audit_row: dict[str, Any]) -> bool:
    """Cancel the created claim by id."""
    from backend.tools import _cancel_claim

    after = audit_row.get("after_state") or {}
    claim_id = after.get("claim_id")
    user_id = audit_row.get("actor_user_id")
    if not claim_id or not user_id:
        return False
    result = await _cancel_claim(user_id=user_id, claim_id=claim_id)
    return _ok(result)


# ============================================================================
# cancel_claim
# ============================================================================

async def _fetch_before_cancel_claim(args: dict[str, Any], user_id: str) -> dict[str, Any] | None:
    from backend.ai_engine import supabase_get

    claim_id = args.get("claim_id")
    listing_id = args.get("listing_id")
    filters: dict[str, str] = {"claimer_id": f"eq.{user_id}"}
    if claim_id:
        filters["id"] = f"eq.{claim_id}"
    elif listing_id:
        filters["food_id"] = f"eq.{listing_id}"
    else:
        return None
    filters["select"] = "id,food_id,quantity,status"
    filters["limit"] = "1"
    try:
        rows = await supabase_get("food_claims", filters)
        return rows[0] if rows else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("fetch_before cancel_claim failed: %s", exc)
        return None


async def _handle_cancel_claim(args: dict[str, Any], user_id: str):
    from backend.tools import _cancel_claim

    result = await _cancel_claim(user_id=user_id, **args)
    if not _ok(result):
        raise RuntimeError(result.get("error") or "cancel_claim failed")
    after = {
        "claim_id": _coerce_id(result.get("claim_id")),
        "listing_id": _coerce_id(result.get("listing_id")),
        "status": "cancelled",
    }
    return after, "food_claims", _coerce_id(result.get("claim_id"))


# Rollback for cancel_claim is intentionally NOT registered: re-creating a
# claim against a listing that may have been re-claimed by someone else is
# non-deterministic. Admins must manually re-issue if needed.


# ============================================================================
# post_food_listing
# ============================================================================

async def _handle_post_food_listing(args: dict[str, Any], user_id: str):
    from backend.tools import _create_food_listing

    result = await _create_food_listing(user_id=user_id, **args)
    if not _ok(result):
        raise RuntimeError(result.get("error") or "post_food_listing failed")
    listing_id = _coerce_id(result.get("listing_id") or result.get("id"))
    after = {
        "listing_id": listing_id,
        "title": result.get("title") or args.get("title"),
        "status": result.get("status") or "approved",
    }
    return after, "food_listings", listing_id


async def _rollback_post_food_listing(audit_row: dict[str, Any]) -> bool:
    """Soft-delete the listing we just created."""
    from backend.tools import _delete_listing

    user_id = audit_row.get("actor_user_id")
    listing_id = (audit_row.get("after_state") or {}).get("listing_id")
    if not user_id or not listing_id:
        return False
    result = await _delete_listing(
        user_id=user_id, listing_id=listing_id, confirmed=True
    )
    return _ok(result)


# ============================================================================
# update_food_listing / edit_listing
# ============================================================================

async def _fetch_before_update_listing(args: dict[str, Any], user_id: str) -> dict[str, Any] | None:
    from backend.ai_engine import supabase_get

    listing_id = args.get("listing_id") or args.get("id")
    if not listing_id:
        return None
    try:
        rows = await supabase_get("food_listings", {
            "id": f"eq.{listing_id}",
            "user_id": f"eq.{user_id}",
            "select": (
                "id,title,description,quantity,unit,category,status,"
                "expiry_date,location"
            ),
            "limit": "1",
        })
        return rows[0] if rows else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("fetch_before update_listing failed: %s", exc)
        return None


async def _handle_update_listing(args: dict[str, Any], user_id: str):
    from backend.tools import _update_food_listing

    result = await _update_food_listing(user_id=user_id, **args)
    if not _ok(result):
        raise RuntimeError(result.get("error") or "update_listing failed")
    listing_id = _coerce_id(result.get("listing_id") or args.get("listing_id"))
    after = {
        "listing_id": listing_id,
        "updated_fields": result.get("updated_fields"),
    }
    return after, "food_listings", listing_id


async def _rollback_update_listing(audit_row: dict[str, Any]) -> bool:
    """Replay the captured before_state via supabase PATCH."""
    from backend.ai_engine import supabase_patch

    user_id = audit_row.get("actor_user_id")
    before = audit_row.get("before_state") or {}
    listing_id = before.get("id") or (audit_row.get("after_state") or {}).get("listing_id")
    if not user_id or not listing_id:
        return False

    # Only restore the columns we snapshotted in fetch_before; never write back
    # the id itself.
    payload = {
        k: before.get(k)
        for k in (
            "title", "description", "quantity", "unit", "category",
            "status", "expiry_date", "location",
        )
        if k in before
    }
    if not payload:
        return False
    try:
        await supabase_patch(
            "food_listings",
            {"id": f"eq.{listing_id}", "user_id": f"eq.{user_id}"},
            payload,
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("rollback update_listing failed: %s", exc)
        return False


# ============================================================================
# delete_listing  (hard delete — no rollback, but audit is critical)
# ============================================================================

async def _fetch_before_delete_listing(args: dict[str, Any], user_id: str) -> dict[str, Any] | None:
    from backend.ai_engine import supabase_get

    listing_id = args.get("listing_id")
    title = args.get("title")
    filters: dict[str, str] = {"user_id": f"eq.{user_id}", "limit": "1"}
    if listing_id:
        filters["id"] = f"eq.{listing_id}"
    elif title:
        filters["title"] = f"ilike.%{title}%"
    else:
        return None
    filters["select"] = (
        "id,title,description,quantity,unit,category,status,"
        "expiry_date,location,created_at"
    )
    try:
        rows = await supabase_get("food_listings", filters)
        return rows[0] if rows else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("fetch_before delete_listing failed: %s", exc)
        return None


async def _handle_delete_listing(args: dict[str, Any], user_id: str):
    from backend.tools import _delete_listing

    # The legacy handler insists on a `confirmed=True` flag; we provide it
    # because the action framework's own confirmation step already happened.
    payload = {**args}
    payload.setdefault("confirmed", True)
    result = await _delete_listing(user_id=user_id, **payload)
    if not _ok(result):
        raise RuntimeError(result.get("error") or "delete_listing failed")
    return (
        {"listing_id": _coerce_id(result.get("listing_id")), "title": result.get("title")},
        "food_listings",
        _coerce_id(result.get("listing_id")),
    )


# ============================================================================
# deactivate_listing  (soft remove; reversible)
# ============================================================================

async def _handle_deactivate_listing(args: dict[str, Any], user_id: str):
    from backend.tools import _deactivate_listing

    result = await _deactivate_listing(user_id=user_id, **args)
    if not _ok(result):
        raise RuntimeError(result.get("error") or "deactivate_listing failed")
    listing_id = _coerce_id(result.get("listing_id"))
    return {"listing_id": listing_id, "status": "removed"}, "food_listings", listing_id


async def _rollback_deactivate_listing(audit_row: dict[str, Any]) -> bool:
    """Flip status back to active using the captured before_state status."""
    from backend.ai_engine import supabase_patch

    user_id = audit_row.get("actor_user_id")
    before = audit_row.get("before_state") or {}
    listing_id = before.get("id") or (audit_row.get("after_state") or {}).get("listing_id")
    if not user_id or not listing_id:
        return False
    restore_status = before.get("status") or "active"
    try:
        await supabase_patch(
            "food_listings",
            {"id": f"eq.{listing_id}", "user_id": f"eq.{user_id}"},
            {"status": restore_status},
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("rollback deactivate_listing failed: %s", exc)
        return False


# ============================================================================
# update_user_profile
# ============================================================================

async def _fetch_before_update_profile(args: dict[str, Any], user_id: str) -> dict[str, Any] | None:
    from backend.ai_engine import supabase_get

    cols = sorted(set(args.keys()) | {
        "name", "address", "phone", "dietary_restrictions",
        "allergies", "dietary_preferences",
    })
    select_cols = ",".join(["id"] + [c for c in cols if c != "user_id"])
    try:
        rows = await supabase_get("users", {
            "id": f"eq.{user_id}",
            "select": select_cols,
            "limit": "1",
        })
        return rows[0] if rows else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("fetch_before update_user_profile failed: %s", exc)
        return None


async def _handle_update_user_profile(args: dict[str, Any], user_id: str):
    from backend.tools import _update_user_profile

    result = await _update_user_profile(user_id=user_id, **args)
    if not _ok(result):
        raise RuntimeError(result.get("error") or "update_user_profile failed")
    after = {
        "updated_fields": result.get("updated_fields"),
        "rejected_fields": result.get("rejected_fields"),
    }
    return after, "users", _coerce_id(user_id)


async def _rollback_update_user_profile(audit_row: dict[str, Any]) -> bool:
    """Restore each updated column from before_state."""
    from backend.ai_engine import supabase_patch

    user_id = audit_row.get("actor_user_id")
    before = audit_row.get("before_state") or {}
    after = audit_row.get("after_state") or {}
    if not user_id or not before:
        return False
    updated_fields = after.get("updated_fields") or []
    payload = {k: before.get(k) for k in updated_fields if k in before}
    if not payload:
        return False
    try:
        await supabase_patch("users", {"id": f"eq.{user_id}"}, payload)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("rollback update_user_profile failed: %s", exc)
        return False


# ============================================================================
# send_notification  (low risk, no confirmation needed)
# ============================================================================

async def _handle_send_notification(args: dict[str, Any], user_id: str):
    from backend.tools import _send_notification

    # send_notification targets a recipient via its own user_id arg; if missing
    # we default the recipient to the actor (the agent notifying the user).
    payload = {**args}
    payload.setdefault("user_id", user_id)
    result = await _send_notification(**payload)
    if not _ok(result):
        raise RuntimeError(result.get("error") or "send_notification failed")
    nid = _coerce_id(result.get("notification_id"))
    return {"notification_id": nid, "title": args.get("title")}, "notifications", nid


async def _rollback_send_notification(audit_row: dict[str, Any]) -> bool:
    from backend.ai_engine import supabase_delete

    nid = (audit_row.get("after_state") or {}).get("notification_id")
    if not nid:
        return False
    try:
        await supabase_delete("notifications", {"id": f"eq.{nid}"})
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("rollback send_notification failed: %s", exc)
        return False


# ============================================================================
# mark_notifications_read  (low risk; bulk reversible)
# ============================================================================

async def _fetch_before_mark_read(args: dict[str, Any], user_id: str) -> dict[str, Any] | None:
    from backend.ai_engine import supabase_get

    notification_id = args.get("notification_id")
    filters: dict[str, str] = {"user_id": f"eq.{user_id}", "read": "eq.false"}
    if notification_id:
        filters["id"] = f"eq.{notification_id}"
    filters["select"] = "id"
    filters["limit"] = "100"
    try:
        rows = await supabase_get("notifications", filters)
        return {"unread_ids": [r.get("id") for r in rows or []]}
    except Exception as exc:  # noqa: BLE001
        logger.warning("fetch_before mark_notifications_read failed: %s", exc)
        return None


async def _handle_mark_read(args: dict[str, Any], user_id: str):
    from backend.tools import _mark_notifications_read

    result = await _mark_notifications_read(user_id=user_id, **args)
    if not _ok(result):
        raise RuntimeError(result.get("error") or "mark_notifications_read failed")
    return (
        {"updated_count": result.get("updated_count", 0)},
        "notifications",
        _coerce_id(args.get("notification_id")),
    )


async def _rollback_mark_read(audit_row: dict[str, Any]) -> bool:
    from backend.ai_engine import supabase_patch

    user_id = audit_row.get("actor_user_id")
    before = audit_row.get("before_state") or {}
    ids = before.get("unread_ids") or []
    if not user_id or not ids:
        return False
    try:
        # Re-mark the rows we flipped as unread. PostgREST `in.(...)` syntax.
        in_clause = "(" + ",".join(str(i) for i in ids) + ")"
        await supabase_patch(
            "notifications",
            {"user_id": f"eq.{user_id}", "id": f"in.{in_clause}"},
            {"read": False},
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("rollback mark_notifications_read failed: %s", exc)
        return False


# ============================================================================
# create_reminder  (low risk; reversible by delete)
# ============================================================================

async def _handle_create_reminder(args: dict[str, Any], user_id: str):
    from backend.tools import _create_reminder

    result = await _create_reminder(user_id=user_id, **args)
    if not _ok(result):
        raise RuntimeError(result.get("error") or "create_reminder failed")
    rid = _coerce_id(result.get("reminder_id") or result.get("id"))
    return {"reminder_id": rid, "claim_id": result.get("claim_id")}, "reminders", rid


async def _rollback_create_reminder(audit_row: dict[str, Any]) -> bool:
    from backend.ai_engine import supabase_delete

    rid = (audit_row.get("after_state") or {}).get("reminder_id")
    if not rid:
        return False
    try:
        await supabase_delete("reminders", {"id": f"eq.{rid}"})
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("rollback create_reminder failed: %s", exc)
        return False


# ============================================================================
# forget_about_me  (DELETE on agent_user_facts; rollback re-inserts snapshot)
# ============================================================================

async def _fetch_before_forget(args: dict[str, Any], user_id: str) -> dict[str, Any] | None:
    from backend.ai_engine import supabase_get

    filters: dict[str, str] = {"user_id": f"eq.{user_id}"}
    if args.get("kind"):
        filters["kind"] = f"eq.{args['kind']}"
    filters["select"] = "id,kind,content,importance,confirmed_by_user,source_turn_id,created_at"
    filters["limit"] = "500"
    try:
        rows = await supabase_get("agent_user_facts", filters)
        return {"facts": rows or []}
    except Exception as exc:  # noqa: BLE001
        logger.warning("fetch_before forget_about_me failed: %s", exc)
        return None


async def _handle_forget(args: dict[str, Any], user_id: str):
    from backend.tools import _forget_about_me

    result = await _forget_about_me(user_id=user_id, **args)
    if not _ok(result):
        raise RuntimeError(result.get("error") or "forget_about_me failed")
    after = {
        "deleted_count": result.get("deleted_count", 0),
        "kind": result.get("kind"),
    }
    return after, "agent_user_facts", None


async def _rollback_forget(audit_row: dict[str, Any]) -> bool:
    """Re-insert the deleted facts. Stable because each fact carries a UUID."""
    from backend.ai_engine import supabase_post

    user_id = audit_row.get("actor_user_id")
    before = audit_row.get("before_state") or {}
    facts = before.get("facts") or []
    if not user_id or not facts:
        return False
    try:
        # Re-insert each row with its original id so downstream foreign keys
        # (if any) still resolve. supabase_post accepts a single dict; loop.
        for fact in facts:
            if not isinstance(fact, dict):
                continue
            row = {k: v for k, v in fact.items() if v is not None}
            row.setdefault("user_id", user_id)
            await supabase_post("agent_user_facts", row)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("rollback forget_about_me failed: %s", exc)
        return False


# ============================================================================
# Registry initialization
# ============================================================================

# ---------------------------------------------------------------------------
# AGENT_V2 (Phase 4) — message_donor / schedule_pickup / join_community /
# leave_community. Each mirrors the existing pattern: optional fetch_before,
# handler that runs the underlying tool, and (where meaningful) a rollback.
# ---------------------------------------------------------------------------

async def _handle_message_donor(args: dict[str, Any], user_id: str):
    from backend.tools import _message_donor

    result = await _message_donor(user_id=user_id, **args)
    if not _ok(result):
        raise RuntimeError(result.get("error") or "message_donor failed")
    nid = _coerce_id(result.get("notification_id"))
    after = {
        "notification_id": nid,
        "listing_id": _coerce_id(args.get("listing_id")),
    }
    return after, "notifications", nid


async def _rollback_message_donor(audit_row: dict[str, Any]) -> bool:
    """Delete the delivered notification."""
    from backend.ai_engine import supabase_delete

    nid = (audit_row.get("after_state") or {}).get("notification_id")
    if not nid:
        return False
    try:
        await supabase_delete("notifications", {"id": f"eq.{nid}"})
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("rollback message_donor failed: %s", exc)
        return False


async def _handle_schedule_pickup(args: dict[str, Any], user_id: str):
    from backend.tools import _schedule_pickup

    result = await _schedule_pickup(user_id=user_id, **args)
    if not _ok(result):
        raise RuntimeError(result.get("error") or "schedule_pickup failed")
    rid = _coerce_id(result.get("reminder_id"))
    after = {
        "reminder_id": rid,
        "claim_id": _coerce_id(result.get("claim_id")),
        "pickup_datetime": result.get("pickup_datetime"),
    }
    return after, "reminders", rid


async def _rollback_schedule_pickup(audit_row: dict[str, Any]) -> bool:
    """Delete the reminder we created."""
    from backend.ai_engine import supabase_delete

    rid = (audit_row.get("after_state") or {}).get("reminder_id")
    if not rid:
        return False
    try:
        await supabase_delete("reminders", {"id": f"eq.{rid}"})
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("rollback schedule_pickup failed: %s", exc)
        return False


async def _fetch_before_community_change(args: dict[str, Any], user_id: str) -> dict[str, Any] | None:
    """Snapshot the user's current community so we can restore it."""
    from backend.ai_engine import supabase_get

    try:
        rows = await supabase_get("users", {
            "id": f"eq.{user_id}",
            "select": "id,community_id",
            "limit": "1",
        })
        return rows[0] if rows else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("fetch_before community_change failed: %s", exc)
        return None


async def _handle_join_community(args: dict[str, Any], user_id: str):
    from backend.tools import _join_community

    result = await _join_community(user_id=user_id, **args)
    if not _ok(result):
        raise RuntimeError(result.get("error") or "join_community failed")
    after = {
        "community_id": _coerce_id(result.get("community_id")),
        "community_name": result.get("community_name"),
    }
    return after, "users", _coerce_id(user_id)


async def _rollback_join_community(audit_row: dict[str, Any]) -> bool:
    """Restore the prior community_id from before_state."""
    from backend.ai_engine import supabase_patch

    user_id = audit_row.get("actor_user_id")
    prior = (audit_row.get("before_state") or {}).get("community_id")
    if not user_id:
        return False
    try:
        await supabase_patch(
            "users", {"id": f"eq.{user_id}"},
            {"community_id": prior},
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("rollback join_community failed: %s", exc)
        return False


async def _handle_leave_community(args: dict[str, Any], user_id: str):
    from backend.tools import _leave_community

    result = await _leave_community(user_id=user_id, **args)
    if not _ok(result):
        raise RuntimeError(result.get("error") or "leave_community failed")
    after = {
        "community_id": None,
        "prior_community_name": result.get("prior_community_name"),
    }
    return after, "users", _coerce_id(user_id)


async def _rollback_leave_community(audit_row: dict[str, Any]) -> bool:
    """Rejoin the community by patching users.community_id back."""
    from backend.ai_engine import supabase_patch

    user_id = audit_row.get("actor_user_id")
    prior = (audit_row.get("before_state") or {}).get("community_id")
    if not user_id or not prior:
        return False
    try:
        await supabase_patch(
            "users", {"id": f"eq.{user_id}"},
            {"community_id": prior},
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("rollback leave_community failed: %s", exc)
        return False


def register_all() -> list[str]:
    """Register every WRITE the legacy agent can perform.

    Returns the list of registered action names (handy in tests and at
    startup logging).
    """
    register_action(
        "claim_listing",
        _handle_claim,
        rollback=_rollback_claim,
        fetch_before=_fetch_before_claim,
        requires_confirmation=True,
        summary_template="Claim listing {listing_id}",
    )
    register_action(
        "cancel_claim",
        _handle_cancel_claim,
        fetch_before=_fetch_before_cancel_claim,
        requires_confirmation=True,
        summary_template="Release your claim",
    )
    register_action(
        "post_food_listing",
        _handle_post_food_listing,
        rollback=_rollback_post_food_listing,
        requires_confirmation=True,
        summary_template="Post '{title}' to the community",
    )
    register_action(
        "create_food_listing",
        _handle_post_food_listing,
        rollback=_rollback_post_food_listing,
        requires_confirmation=True,
        summary_template="Post '{title}' to the community",
    )
    register_action(
        "update_food_listing",
        _handle_update_listing,
        rollback=_rollback_update_listing,
        fetch_before=_fetch_before_update_listing,
        requires_confirmation=True,
        summary_template="Update your listing",
    )
    register_action(
        "edit_listing",
        _handle_update_listing,
        rollback=_rollback_update_listing,
        fetch_before=_fetch_before_update_listing,
        requires_confirmation=True,
        summary_template="Edit your listing",
    )
    register_action(
        "delete_listing",
        _handle_delete_listing,
        fetch_before=_fetch_before_delete_listing,
        requires_confirmation=True,
        summary_template="Permanently delete your listing",
    )
    register_action(
        "deactivate_listing",
        _handle_deactivate_listing,
        rollback=_rollback_deactivate_listing,
        fetch_before=_fetch_before_update_listing,
        requires_confirmation=True,
        summary_template="Take your listing down",
    )
    register_action(
        "update_user_profile",
        _handle_update_user_profile,
        rollback=_rollback_update_user_profile,
        fetch_before=_fetch_before_update_profile,
        requires_confirmation=True,
        summary_template="Update your profile",
    )
    register_action(
        "set_dietary_preferences",
        _handle_update_user_profile,
        rollback=_rollback_update_user_profile,
        fetch_before=_fetch_before_update_profile,
        requires_confirmation=True,
        summary_template="Save your dietary preferences",
    )
    register_action(
        "send_notification",
        _handle_send_notification,
        rollback=_rollback_send_notification,
        requires_confirmation=False,
        summary_template="Send notification: {title}",
    )
    register_action(
        "mark_notifications_read",
        _handle_mark_read,
        rollback=_rollback_mark_read,
        fetch_before=_fetch_before_mark_read,
        requires_confirmation=False,
        summary_template="Mark notifications as read",
    )
    register_action(
        "dismiss_notification",
        _handle_mark_read,
        rollback=_rollback_mark_read,
        fetch_before=_fetch_before_mark_read,
        requires_confirmation=False,
        summary_template="Dismiss notification",
    )
    register_action(
        "dismiss_all_notifications",
        _handle_mark_read,
        rollback=_rollback_mark_read,
        fetch_before=_fetch_before_mark_read,
        requires_confirmation=False,
        summary_template="Dismiss all notifications",
    )
    register_action(
        "create_reminder",
        _handle_create_reminder,
        rollback=_rollback_create_reminder,
        requires_confirmation=False,
        summary_template="Create a pickup reminder",
    )
    register_action(
        "forget_about_me",
        _handle_forget,
        rollback=_rollback_forget,
        fetch_before=_fetch_before_forget,
        requires_confirmation=True,
        summary_template="Forget what I've learned about you",
    )
    # AGENT_V2 Phase 4 — 4 new WRITE tools
    register_action(
        "message_donor",
        _handle_message_donor,
        rollback=_rollback_message_donor,
        requires_confirmation=True,
        summary_template="Send a message to the donor of listing {listing_id}",
    )
    register_action(
        "schedule_pickup",
        _handle_schedule_pickup,
        rollback=_rollback_schedule_pickup,
        requires_confirmation=True,
        summary_template="Schedule pickup for {pickup_datetime}",
    )
    register_action(
        "join_community",
        _handle_join_community,
        rollback=_rollback_join_community,
        fetch_before=_fetch_before_community_change,
        requires_confirmation=True,
        summary_template="Join community {community_name}",
    )
    register_action(
        "leave_community",
        _handle_leave_community,
        rollback=_rollback_leave_community,
        fetch_before=_fetch_before_community_change,
        requires_confirmation=True,
        summary_template="Leave your current community",
    )

    from backend.agent.actions import list_actions
    names = list_actions()
    logger.info("agent_v2 registered %d actions: %s", len(names), names)
    return names


__all__ = ["register_all"]
