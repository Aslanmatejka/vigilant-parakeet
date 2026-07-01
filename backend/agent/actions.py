"""
Agent Action Framework (AGENT_V2)
==================================

Provides a typed wrapper for every WRITE action the agent can take. The
purpose is threefold:

1. **Confirmation envelope** — actions tagged `requires_confirmation=True`
   are not executed directly; instead they're persisted into
   `agent_pending_actions` and returned to the UI for the user to confirm.
   The user's "yes" / "no" resolves via POST /api/ai/confirm.

2. **Audit log + rollback** — every committed action writes a row into
   `agent_audit_log` containing the before-state, after-state, target table
   and id, and a rollback handler name. If a downstream step in a multi-step
   plan fails, the orchestrator can call `rollback(audit_id)` to fire the
   registered compensating action (e.g. cancel a claim if the post-claim
   PATCH on the listing failed).

3. **Idempotency** — every action is given a deterministic idempotency key
   `hash(user_id, tool_name, args, turn_id)`. A retry never produces a second
   write. The DB enforces this through a partial unique index on
   `agent_pending_actions(user_id, idempotency_key)`.

This module is pure plumbing — it does NOT know about specific tools. Tools
register themselves by calling `register_action(tool_name, ...)` at module
import time (see backend/tools.py).

Slice A scope:
- Confirmation envelope: fully implemented.
- Audit log: fully implemented.
- Rollback: registry + fire mechanism implemented; per-tool compensating
  actions are wired in tools.py.
- Idempotency: hash-based, DB-enforced.

Out of scope here:
- Multi-step transaction logs (Slice B).
- Cross-user/admin batched actions (Slice C).
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# Typed action objects
# ============================================================================

# A handler signature: receives the validated args + the actor user_id and
# returns a tuple (after_state, target_table, target_id). The caller is
# responsible for capturing the before_state BEFORE invoking the handler so
# the audit log row is complete.
ActionHandler = Callable[[dict[str, Any], str], Awaitable[tuple[dict[str, Any] | None, str | None, str | None]]]

# A rollback handler receives the committed audit row and undoes its effect.
# Returns True if rollback succeeded, False otherwise.
RollbackHandler = Callable[[dict[str, Any]], Awaitable[bool]]

# A before-state fetcher: receives the args + user_id, returns a serializable
# snapshot of the targeted row(s) so the audit log can record what changed.
BeforeStateFetcher = Callable[[dict[str, Any], str], Awaitable[dict[str, Any] | None]]


@dataclass(frozen=True)
class ActionSpec:
    """Static metadata for a registered action."""
    name: str
    handler: ActionHandler
    rollback: Optional[RollbackHandler] = None
    fetch_before: Optional[BeforeStateFetcher] = None
    requires_confirmation: bool = True
    summary_template: str = "{name}"  # rendered into agent_pending_actions.summary

    def render_summary(self, args: dict[str, Any]) -> str:
        try:
            return self.summary_template.format(name=self.name, **(args or {}))
        except Exception:
            return self.name


@dataclass
class ActionRequest:
    """A planned WRITE the agent wants to perform."""
    tool: str
    args: dict[str, Any]
    user_id: str
    turn_id: str
    conversation_id: Optional[str] = None
    requires_confirmation: Optional[bool] = None  # None → use spec default
    summary: Optional[str] = None
    idempotency_key: Optional[str] = None

    def compute_idempotency_key(self) -> str:
        if self.idempotency_key:
            return self.idempotency_key
        canonical = json.dumps(
            {"tool": self.tool, "args": self.args or {}, "user_id": self.user_id, "turn_id": self.turn_id},
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


@dataclass
class ActionResult:
    """Outcome of executing an action."""
    status: str                            # committed | pending | cancelled | failed
    tool: str
    args: dict[str, Any]
    pending_id: Optional[str] = None       # set when status == pending
    audit_id: Optional[str] = None         # set when status == committed
    rollback_token: Optional[str] = None
    before_state: Optional[dict[str, Any]] = None
    after_state: Optional[dict[str, Any]] = None
    target_table: Optional[str] = None
    target_id: Optional[str] = None
    error: Optional[str] = None
    summary: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "tool": self.tool,
            "args": self.args,
            "pending_id": self.pending_id,
            "audit_id": self.audit_id,
            "summary": self.summary,
            "error": self.error,
            # Don't expose internal before/after to the frontend — those are
            # only for rollback / admin audit.
        }


# ============================================================================
# Registry
# ============================================================================

_REGISTRY: dict[str, ActionSpec] = {}


def register_action(
    name: str,
    handler: ActionHandler,
    *,
    rollback: RollbackHandler | None = None,
    fetch_before: BeforeStateFetcher | None = None,
    requires_confirmation: bool = True,
    summary_template: str = "{name}",
) -> ActionSpec:
    """Register an action. Tools call this at module load time."""
    if not name:
        raise ValueError("action name required")
    spec = ActionSpec(
        name=name,
        handler=handler,
        rollback=rollback,
        fetch_before=fetch_before,
        requires_confirmation=requires_confirmation,
        summary_template=summary_template,
    )
    if name in _REGISTRY:
        logger.warning("re-registering action %s (overwriting previous)", name)
    _REGISTRY[name] = spec
    return spec


def get_action(name: str) -> ActionSpec | None:
    return _REGISTRY.get(name)


def list_actions() -> list[str]:
    return sorted(_REGISTRY.keys())


# ============================================================================
# Decorator sugar — @action / @rollback_for / @fetch_before_for
# ============================================================================
# Ergonomic alternative to the explicit `register_action(name, handler, ...)`
# calls in `tool_actions.py`. The decorators register the callable at import
# time and return it unchanged, so decorated handlers remain directly
# callable in tests. Rollback / fetch-before wiring can attach either
# eagerly (via `@action(..., rollback=fn)`) or lazily by name (via
# `@rollback_for("claim_listing")`).
#
# Example:
#
#     @action("claim_listing",
#             requires_confirmation=True,
#             summary_template="Claim listing {listing_id}")
#     async def _handle_claim(args, user_id):
#         ...
#
#     @rollback_for("claim_listing")
#     async def _rollback_claim(audit_row):
#         ...

def action(
    name: str,
    *,
    rollback: RollbackHandler | None = None,
    fetch_before: BeforeStateFetcher | None = None,
    requires_confirmation: bool = True,
    summary_template: str = "{name}",
):
    """Decorator form of `register_action`. Returns the wrapped handler
    unchanged so callers can still invoke it directly (e.g. in tests)."""
    def _decorator(handler: ActionHandler) -> ActionHandler:
        register_action(
            name,
            handler,
            rollback=rollback,
            fetch_before=fetch_before,
            requires_confirmation=requires_confirmation,
            summary_template=summary_template,
        )
        return handler
    return _decorator


def rollback_for(name: str):
    """Attach a rollback handler to an action registered elsewhere.

    Fails loudly if the action isn't registered yet — decorator order in
    `tool_actions.py` should always put `@action` before `@rollback_for`.
    """
    def _decorator(fn: RollbackHandler) -> RollbackHandler:
        spec = _REGISTRY.get(name)
        if spec is None:
            raise ValueError(
                f"rollback_for('{name}'): action not registered — "
                "declare @action first"
            )
        # ActionSpec is frozen; replace with an updated copy.
        _REGISTRY[name] = ActionSpec(
            name=spec.name,
            handler=spec.handler,
            rollback=fn,
            fetch_before=spec.fetch_before,
            requires_confirmation=spec.requires_confirmation,
            summary_template=spec.summary_template,
        )
        return fn
    return _decorator


def fetch_before_for(name: str):
    """Attach a before-state fetcher to an already-registered action."""
    def _decorator(fn: BeforeStateFetcher) -> BeforeStateFetcher:
        spec = _REGISTRY.get(name)
        if spec is None:
            raise ValueError(
                f"fetch_before_for('{name}'): action not registered — "
                "declare @action first"
            )
        _REGISTRY[name] = ActionSpec(
            name=spec.name,
            handler=spec.handler,
            rollback=spec.rollback,
            fetch_before=fn,
            requires_confirmation=spec.requires_confirmation,
            summary_template=spec.summary_template,
        )
        return fn
    return _decorator


# ============================================================================
# Args redaction (audit log should never store secrets)
# ============================================================================

# Keys whose values should be replaced with a placeholder in the audit log.
_REDACT_KEYS: frozenset[str] = frozenset({
    "password", "token", "access_token", "refresh_token", "api_key",
    "secret", "authorization",
})


def redact_args(args: dict[str, Any] | None) -> dict[str, Any]:
    if not args:
        return {}
    out: dict[str, Any] = {}
    for k, v in args.items():
        if k.lower() in _REDACT_KEYS:
            out[k] = "[redacted]"
        elif isinstance(v, dict):
            out[k] = redact_args(v)
        elif isinstance(v, str) and len(v) > 1000:
            out[k] = v[:200] + "...[truncated]"
        else:
            out[k] = v
    return out


# ============================================================================
# Execution: confirm-or-commit + audit + rollback
# ============================================================================

async def plan_action(req: ActionRequest) -> ActionResult:
    """Decide whether to commit immediately or queue for confirmation.

    If the action requires confirmation (per spec or per-request override),
    a row is inserted into `agent_pending_actions` and a `pending` ActionResult
    is returned. The frontend renders a confirmation card; on user yes,
    POST /api/ai/confirm calls `commit_pending_action(pending_id)`.

    If confirmation is NOT required, this calls `commit_action()` immediately.
    """
    spec = get_action(req.tool)
    if not spec:
        return ActionResult(status="failed", tool=req.tool, args=req.args,
                            error=f"unknown action: {req.tool}")

    requires = req.requires_confirmation if req.requires_confirmation is not None else spec.requires_confirmation

    if not requires:
        return await commit_action(req)

    # Queue for user confirmation.
    from backend.ai_engine import supabase_post  # local import — avoids cycle at module load

    idem = req.compute_idempotency_key()
    summary = req.summary or spec.render_summary(req.args)
    try:
        rows = await supabase_post("agent_pending_actions", {
            "user_id": req.user_id,
            "conversation_id": req.conversation_id,
            "turn_id": req.turn_id,
            "tool_name": req.tool,
            "args": req.args or {},
            "summary": summary,
            "idempotency_key": idem,
            "status": "pending",
        })
        if isinstance(rows, list) and rows:
            pending_id = rows[0].get("id")
        else:
            pending_id = None
    except Exception as exc:  # noqa: BLE001
        # If the unique-idempotency index trips we treat the existing pending
        # row as the authoritative one. Look it up.
        logger.info("plan_action insert hit existing pending row: %s", exc)
        pending_id = None
        try:
            from backend.ai_engine import supabase_get
            existing = await supabase_get("agent_pending_actions", {
                "user_id": f"eq.{req.user_id}",
                "idempotency_key": f"eq.{idem}",
                "status": "eq.pending",
                "select": "id,summary",
                "limit": "1",
            })
            if existing:
                pending_id = existing[0].get("id")
                summary = existing[0].get("summary") or summary
        except Exception:  # noqa: BLE001
            pass

    if not pending_id:
        return ActionResult(status="failed", tool=req.tool, args=req.args,
                            error="failed to queue confirmation")

    return ActionResult(
        status="pending",
        tool=req.tool,
        args=req.args,
        pending_id=pending_id,
        summary=summary,
    )


async def commit_action(req: ActionRequest, *, pending_id: str | None = None) -> ActionResult:
    """Run the action handler, write the audit log row, return result.

    `pending_id` is set when this commit was triggered by /api/ai/confirm; the
    pending row gets marked `confirmed` and linked to the audit row.
    """
    from backend.ai_engine import supabase_post, supabase_patch  # local — avoid cycle

    spec = get_action(req.tool)
    if not spec:
        return ActionResult(status="failed", tool=req.tool, args=req.args,
                            error=f"unknown action: {req.tool}")

    # 1. Capture before-state (best-effort).
    before_state: dict[str, Any] | None = None
    if spec.fetch_before:
        try:
            before_state = await spec.fetch_before(req.args, req.user_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("fetch_before for %s failed: %s", req.tool, exc)
            before_state = None

    # 2. Run the handler.
    rollback_token = uuid.uuid4().hex
    try:
        after_state, target_table, target_id = await spec.handler(req.args, req.user_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("action %s handler failed: %s", req.tool, exc, exc_info=True)
        # Best-effort failure audit row so admins can see attempted writes.
        try:
            await supabase_post("agent_audit_log", {
                "actor_user_id": req.user_id,
                "turn_id": req.turn_id,
                "conversation_id": req.conversation_id,
                "tool_name": req.tool,
                "args_redacted": redact_args(req.args),
                "before_state": before_state,
                "after_state": None,
                "target_table": None,
                "target_id": None,
                "status": "failed",
                "rollback_token": None,
                "error_message": str(exc)[:1000],
            })
        except Exception:  # noqa: BLE001
            pass

        if pending_id:
            try:
                await supabase_patch(
                    "agent_pending_actions",
                    {"id": f"eq.{pending_id}"},
                    {"status": "failed", "resolved_at": datetime.now(timezone.utc).isoformat()},
                )
            except Exception:  # noqa: BLE001
                pass

        return ActionResult(status="failed", tool=req.tool, args=req.args, error=str(exc))

    # 3. Audit log.
    audit_id: str | None = None
    try:
        audit_rows = await supabase_post("agent_audit_log", {
            "actor_user_id": req.user_id,
            "turn_id": req.turn_id,
            "conversation_id": req.conversation_id,
            "tool_name": req.tool,
            "args_redacted": redact_args(req.args),
            "before_state": before_state,
            "after_state": after_state,
            "target_table": target_table,
            "target_id": str(target_id) if target_id is not None else None,
            "status": "committed",
            "rollback_token": rollback_token,
        })
        if isinstance(audit_rows, list) and audit_rows:
            audit_id = audit_rows[0].get("id")
    except Exception as exc:  # noqa: BLE001
        logger.warning("audit_log insert failed for %s (non-fatal): %s", req.tool, exc)

    # 4. Resolve the pending row, if any.
    if pending_id:
        try:
            await supabase_patch(
                "agent_pending_actions",
                {"id": f"eq.{pending_id}"},
                {
                    "status": "confirmed",
                    "result": {"audit_id": audit_id, "target_id": target_id, "target_table": target_table},
                    "audit_id": audit_id,
                    "resolved_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception:  # noqa: BLE001
            pass

    return ActionResult(
        status="committed",
        tool=req.tool,
        args=req.args,
        pending_id=pending_id,
        audit_id=audit_id,
        rollback_token=rollback_token,
        before_state=before_state,
        after_state=after_state,
        target_table=target_table,
        target_id=str(target_id) if target_id is not None else None,
        summary=spec.render_summary(req.args),
    )


async def cancel_pending_action(pending_id: str, user_id: str) -> bool:
    """Resolve a pending action with status=cancelled. Idempotent."""
    from backend.ai_engine import supabase_patch
    try:
        rows = await supabase_patch(
            "agent_pending_actions",
            {"id": f"eq.{pending_id}", "user_id": f"eq.{user_id}", "status": "eq.pending"},
            {"status": "cancelled", "resolved_at": datetime.now(timezone.utc).isoformat()},
        )
        return bool(rows)
    except Exception as exc:  # noqa: BLE001
        logger.warning("cancel_pending_action failed for %s: %s", pending_id, exc)
        return False


async def commit_pending_action(pending_id: str, user_id: str) -> ActionResult:
    """Look up the pending action and execute it. Used by /api/ai/confirm."""
    from backend.ai_engine import supabase_get

    rows = await supabase_get("agent_pending_actions", {
        "id": f"eq.{pending_id}",
        "user_id": f"eq.{user_id}",
        "status": "eq.pending",
        "select": "id,user_id,conversation_id,turn_id,tool_name,args,summary,expires_at",
        "limit": "1",
    })
    if not rows:
        return ActionResult(status="failed", tool="(unknown)", args={},
                            error="pending action not found or already resolved")
    row = rows[0]

    expires_at = row.get("expires_at")
    if expires_at:
        try:
            exp = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
            if exp < datetime.now(timezone.utc):
                # Mark expired and refuse to commit.
                from backend.ai_engine import supabase_patch
                try:
                    await supabase_patch(
                        "agent_pending_actions",
                        {"id": f"eq.{pending_id}"},
                        {"status": "expired", "resolved_at": datetime.now(timezone.utc).isoformat()},
                    )
                except Exception:  # noqa: BLE001
                    pass
                return ActionResult(status="failed", tool=row.get("tool_name") or "(unknown)",
                                    args=row.get("args") or {},
                                    error="pending action expired")
        except Exception:  # noqa: BLE001
            pass

    req = ActionRequest(
        tool=row.get("tool_name") or "",
        args=row.get("args") or {},
        user_id=row.get("user_id") or user_id,
        turn_id=row.get("turn_id") or "",
        conversation_id=row.get("conversation_id"),
        requires_confirmation=False,  # already confirmed by user
        summary=row.get("summary"),
    )
    return await commit_action(req, pending_id=pending_id)


async def rollback_action(audit_id: str, user_id: str) -> bool:
    """Fire the compensating action registered for a given audit row."""
    from backend.ai_engine import supabase_get, supabase_patch

    rows = await supabase_get("agent_audit_log", {
        "id": f"eq.{audit_id}",
        "actor_user_id": f"eq.{user_id}",
        "status": "eq.committed",
        "select": "id,tool_name,args_redacted,before_state,after_state,target_table,target_id,rollback_token",
        "limit": "1",
    })
    if not rows:
        return False
    row = rows[0]

    spec = get_action(row.get("tool_name") or "")
    if not spec or not spec.rollback:
        logger.info("no rollback registered for %s — skipping", row.get("tool_name"))
        return False

    try:
        ok = await spec.rollback(row)
    except Exception as exc:  # noqa: BLE001
        logger.error("rollback handler for %s failed: %s", row.get("tool_name"), exc, exc_info=True)
        return False

    if ok:
        try:
            await supabase_patch(
                "agent_audit_log",
                {"id": f"eq.{audit_id}"},
                {
                    "status": "rolled_back",
                    "rollback_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception:  # noqa: BLE001
            pass
    return ok


__all__ = [
    "ActionSpec",
    "ActionRequest",
    "ActionResult",
    "ActionHandler",
    "RollbackHandler",
    "BeforeStateFetcher",
    "register_action",
    "action",
    "rollback_for",
    "fetch_before_for",
    "get_action",
    "list_actions",
    "plan_action",
    "commit_action",
    "commit_pending_action",
    "cancel_pending_action",
    "rollback_action",
    "redact_args",
]
