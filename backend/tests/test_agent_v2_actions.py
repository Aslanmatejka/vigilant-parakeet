"""
AGENT_V2 — Action Framework Tests
==================================

Unit-level tests for `backend.agent.actions` + the per-tool registrations in
`backend.agent.tool_actions`. No live Supabase, no live OpenAI.

We monkeypatch the four supabase REST helpers
(`supabase_get / supabase_post / supabase_patch / supabase_delete`) on
`backend.ai_engine` to simulate the database.

Scenarios covered:
  1. `forget_about_me` handler deletes facts + returns count.
  2. Action framework registers every expected WRITE.
  3. Idempotency key is deterministic and identical for repeated requests.
  4. `plan_action` queues a pending row when `requires_confirmation=True`.
  5. `commit_pending_action` runs the handler + writes audit + resolves pending.
  6. `cancel_pending_action` flips the pending row to cancelled.
  7. Pending action expiry is enforced by `commit_pending_action`.
  8. `rollback_action` invokes the registered rollback handler.

Run:
    python -m pytest backend/tests/test_agent_v2_actions.py -v
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from backend.agent import actions as actions_mod
from backend.agent.actions import (
    ActionRequest,
    cancel_pending_action,
    commit_pending_action,
    get_action,
    list_actions,
    plan_action,
    register_action,
    rollback_action,
)

# Loading the package triggers `tool_actions.register_all()` via __init__.py.
import backend.agent  # noqa: F401


# ============================================================================
# Helpers — fake supabase REST surface
# ============================================================================

class FakeSupabase:
    """In-memory stand-in for the four REST helpers we use.

    Each `state` table is a list of dicts; insert assigns a uuid id if absent.
    Filter parsing is intentionally minimal — we only need equality predicates
    and the `in.(...)` shorthand used by the rollback paths.
    """

    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {}

    # ---- filter utility ----
    @staticmethod
    def _matches(row: dict[str, Any], filters: dict[str, Any]) -> bool:
        for k, v in filters.items():
            if k in ("select", "limit", "order"):
                continue
            if not isinstance(v, str):
                continue
            if v.startswith("eq."):
                if str(row.get(k)) != v[3:]:
                    return False
            elif v.startswith("ilike."):
                pat = v[6:].replace("%", "").lower()
                if pat not in str(row.get(k, "")).lower():
                    return False
            elif v.startswith("in."):
                inner = v[3:].strip("()")
                vals = {p.strip() for p in inner.split(",") if p.strip()}
                if str(row.get(k)) not in vals:
                    return False
        return True

    # ---- REST helpers ----
    async def supabase_get(self, table: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        rows = list(self.tables.get(table, []))
        out = [r for r in rows if self._matches(r, params)]
        limit = params.get("limit")
        if limit:
            try:
                out = out[: int(limit)]
            except Exception:
                pass
        return out

    async def supabase_post(self, table: str, body: dict[str, Any]) -> list[dict[str, Any]]:
        rows = self.tables.setdefault(table, [])
        body = dict(body)
        body.setdefault("id", str(uuid.uuid4()))
        if table == "agent_pending_actions":
            body.setdefault(
                "expires_at",
                (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
            )
            body.setdefault("status", "pending")
        rows.append(body)
        return [body]

    async def supabase_patch(self, table: str, filters: dict[str, Any], body: dict[str, Any]) -> list[dict[str, Any]]:
        rows = self.tables.get(table, [])
        updated: list[dict[str, Any]] = []
        for r in rows:
            if self._matches(r, filters):
                r.update(body)
                updated.append(r)
        return updated

    async def supabase_delete(self, table: str, filters: dict[str, Any]) -> int:
        rows = self.tables.get(table, [])
        keep = [r for r in rows if not self._matches(r, filters)]
        removed = len(rows) - len(keep)
        self.tables[table] = keep
        return removed


@pytest.fixture
def fake_supabase(monkeypatch: pytest.MonkeyPatch) -> FakeSupabase:
    """Patch every supabase REST helper the action framework uses."""
    fake = FakeSupabase()
    import backend.ai_engine as ai_engine

    monkeypatch.setattr(ai_engine, "supabase_get", fake.supabase_get, raising=False)
    monkeypatch.setattr(ai_engine, "supabase_post", fake.supabase_post, raising=False)
    monkeypatch.setattr(ai_engine, "supabase_patch", fake.supabase_patch, raising=False)
    monkeypatch.setattr(ai_engine, "supabase_delete", fake.supabase_delete, raising=False)
    return fake


# ============================================================================
# Scenario 1 — _forget_about_me deletes facts and reports a count
# ============================================================================

class TestForgetAboutMe:
    """The new memory-wipe handler must delete the user's facts and return
    a `success=True` envelope with the deleted snapshot."""

    @pytest.mark.asyncio
    async def test_deletes_all_facts(self, fake_supabase: FakeSupabase) -> None:
        from backend.tools import _forget_about_me

        user_id = str(uuid.uuid4())
        fake_supabase.tables["agent_user_facts"] = [
            {"id": str(uuid.uuid4()), "user_id": user_id, "kind": "preference", "content": "vegan"},
            {"id": str(uuid.uuid4()), "user_id": user_id, "kind": "style", "content": "brief replies"},
            {"id": str(uuid.uuid4()), "user_id": "other", "kind": "preference", "content": "kept"},
        ]

        result = await _forget_about_me(user_id=user_id)

        assert result["success"] is True
        assert result["deleted_count"] == 2
        assert len(fake_supabase.tables["agent_user_facts"]) == 1
        # The other user's fact survived.
        assert fake_supabase.tables["agent_user_facts"][0]["user_id"] == "other"

    @pytest.mark.asyncio
    async def test_kind_filter_narrows_purge(self, fake_supabase: FakeSupabase) -> None:
        from backend.tools import _forget_about_me

        user_id = str(uuid.uuid4())
        fake_supabase.tables["agent_user_facts"] = [
            {"id": "a", "user_id": user_id, "kind": "preference", "content": "vegan"},
            {"id": "b", "user_id": user_id, "kind": "style", "content": "brief"},
        ]
        result = await _forget_about_me(user_id=user_id, kind="preference")
        assert result["success"] is True
        assert result["deleted_count"] == 1
        remaining_kinds = [r["kind"] for r in fake_supabase.tables["agent_user_facts"]]
        assert remaining_kinds == ["style"]

    @pytest.mark.asyncio
    async def test_rejects_invalid_kind(self, fake_supabase: FakeSupabase) -> None:
        from backend.tools import _forget_about_me
        result = await _forget_about_me(user_id=str(uuid.uuid4()), kind="banana")
        assert result["success"] is False
        assert "invalid" in result.get("error", "").lower()


# ============================================================================
# Scenario 2 — registry has every expected WRITE
# ============================================================================

class TestActionRegistry:
    """`tool_actions.register_all()` must register every write tool we
    promised the safety layer + frontend would be wired up."""

    EXPECTED = {
        "claim_listing",
        "cancel_claim",
        "post_food_listing",
        "create_food_listing",
        "update_food_listing",
        "edit_listing",
        "delete_listing",
        "deactivate_listing",
        "update_user_profile",
        "set_dietary_preferences",
        "send_notification",
        "mark_notifications_read",
        "dismiss_notification",
        "dismiss_all_notifications",
        "create_reminder",
        "forget_about_me",
    }

    def test_all_expected_actions_registered(self) -> None:
        registered = set(list_actions())
        missing = self.EXPECTED - registered
        assert not missing, f"missing actions: {sorted(missing)}"

    def test_destructive_actions_require_confirmation(self) -> None:
        for name in ("claim_listing", "delete_listing", "forget_about_me", "update_user_profile"):
            spec = get_action(name)
            assert spec is not None, f"{name} not registered"
            assert spec.requires_confirmation is True, f"{name} should require confirmation"

    def test_low_risk_actions_skip_confirmation(self) -> None:
        for name in ("mark_notifications_read", "create_reminder", "send_notification"):
            spec = get_action(name)
            assert spec is not None
            assert spec.requires_confirmation is False, f"{name} should commit immediately"


# ============================================================================
# Scenario 3 — idempotency keys are deterministic
# ============================================================================

class TestIdempotencyKey:
    """Two ActionRequests with the same (tool, args, user_id, turn_id) MUST
    produce the same idempotency_key so retries can't double-write."""

    def test_same_inputs_same_key(self) -> None:
        a = ActionRequest(
            tool="claim_listing",
            args={"listing_id": "abc", "quantity": 2},
            user_id="u1",
            turn_id="t1",
        )
        b = ActionRequest(
            tool="claim_listing",
            args={"quantity": 2, "listing_id": "abc"},  # key order shuffled
            user_id="u1",
            turn_id="t1",
        )
        assert a.compute_idempotency_key() == b.compute_idempotency_key()

    def test_different_turn_different_key(self) -> None:
        a = ActionRequest(tool="x", args={}, user_id="u1", turn_id="t1")
        b = ActionRequest(tool="x", args={}, user_id="u1", turn_id="t2")
        assert a.compute_idempotency_key() != b.compute_idempotency_key()


# ============================================================================
# Scenario 4 — plan_action queues a pending row for confirm-required tools
# ============================================================================

class TestPlanAction:
    """When `requires_confirmation=True`, `plan_action` must NOT execute the
    handler — it inserts an `agent_pending_actions` row and returns a
    `pending` ActionResult."""

    @pytest.mark.asyncio
    async def test_pending_row_inserted(self, fake_supabase: FakeSupabase) -> None:
        # Register a one-off action so we don't depend on the live tool.
        called = {"n": 0}

        async def handler(args: dict[str, Any], user_id: str):
            called["n"] += 1
            return {"ok": True}, "test_table", "tid"

        register_action(
            "test_pending_tool",
            handler,
            requires_confirmation=True,
            summary_template="test op",
        )

        req = ActionRequest(
            tool="test_pending_tool",
            args={"x": 1},
            user_id="u1",
            turn_id="t1",
        )
        result = await plan_action(req)
        assert result.status == "pending"
        assert result.pending_id is not None
        assert called["n"] == 0  # handler not yet executed
        pending = fake_supabase.tables.get("agent_pending_actions", [])
        assert len(pending) == 1
        assert pending[0]["tool_name"] == "test_pending_tool"
        assert pending[0]["status"] == "pending"


# ============================================================================
# Scenario 5 — commit_pending_action runs the handler + audits
# ============================================================================

class TestCommitPending:
    @pytest.mark.asyncio
    async def test_commit_runs_handler_and_audits(self, fake_supabase: FakeSupabase) -> None:
        async def handler(args: dict[str, Any], user_id: str):
            return {"ok": True, "args": args}, "widgets", "w-1"

        register_action(
            "test_commit_tool",
            handler,
            requires_confirmation=True,
            summary_template="commit op",
        )

        # Queue first.
        plan_result = await plan_action(ActionRequest(
            tool="test_commit_tool",
            args={"k": "v"},
            user_id="u1",
            turn_id="t1",
        ))
        assert plan_result.status == "pending"
        pid = plan_result.pending_id

        # Confirm.
        commit_result = await commit_pending_action(pid, "u1")
        assert commit_result.status == "committed"
        assert commit_result.audit_id is not None
        assert commit_result.target_table == "widgets"

        # Pending row resolved.
        pending_row = fake_supabase.tables["agent_pending_actions"][0]
        assert pending_row["status"] == "confirmed"

        # Audit row written.
        audit_rows = fake_supabase.tables.get("agent_audit_log", [])
        assert len(audit_rows) == 1
        assert audit_rows[0]["tool_name"] == "test_commit_tool"
        assert audit_rows[0]["status"] == "committed"


# ============================================================================
# Scenario 6 — cancel_pending_action flips the row to cancelled
# ============================================================================

class TestCancelPending:
    @pytest.mark.asyncio
    async def test_cancel_marks_row_cancelled(self, fake_supabase: FakeSupabase) -> None:
        async def handler(args, user_id):
            return {"ok": True}, "t", "x"

        register_action("test_cancel_tool", handler, requires_confirmation=True)

        plan_result = await plan_action(ActionRequest(
            tool="test_cancel_tool",
            args={},
            user_id="u1",
            turn_id="t1",
        ))
        pid = plan_result.pending_id

        ok = await cancel_pending_action(pid, "u1")
        assert ok is True
        row = fake_supabase.tables["agent_pending_actions"][0]
        assert row["status"] == "cancelled"


# ============================================================================
# Scenario 7 — expired pending rows refuse to commit
# ============================================================================

class TestPendingExpiry:
    @pytest.mark.asyncio
    async def test_expired_row_refused(self, fake_supabase: FakeSupabase) -> None:
        async def handler(args, user_id):
            return {"ok": True}, "t", "x"

        register_action("test_expiry_tool", handler, requires_confirmation=True)
        plan_result = await plan_action(ActionRequest(
            tool="test_expiry_tool",
            args={},
            user_id="u1",
            turn_id="t1",
        ))
        pid = plan_result.pending_id

        # Backdate the expiry.
        row = fake_supabase.tables["agent_pending_actions"][0]
        row["expires_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()

        commit_result = await commit_pending_action(pid, "u1")
        assert commit_result.status == "failed"
        assert "expired" in (commit_result.error or "").lower()
        assert row["status"] == "expired"


# ============================================================================
# Scenario 8 — rollback_action fires the registered compensating handler
# ============================================================================

class TestRollback:
    @pytest.mark.asyncio
    async def test_rollback_calls_handler_and_flips_audit(self, fake_supabase: FakeSupabase) -> None:
        rolled_back = {"n": 0}

        async def handler(args, user_id):
            return {"created": "yes"}, "t", "x"

        async def rollback(audit_row):
            rolled_back["n"] += 1
            return True

        register_action(
            "test_rollback_tool",
            handler,
            rollback=rollback,
            requires_confirmation=False,
        )

        # Commit immediately (no confirmation).
        plan_result = await plan_action(ActionRequest(
            tool="test_rollback_tool",
            args={"k": "v"},
            user_id="u1",
            turn_id="t1",
        ))
        assert plan_result.status == "committed"
        audit_id = plan_result.audit_id
        assert audit_id is not None

        ok = await rollback_action(audit_id, "u1")
        assert ok is True
        assert rolled_back["n"] == 1
        audit_row = fake_supabase.tables["agent_audit_log"][0]
        assert audit_row["status"] == "rolled_back"


# ============================================================================
# Scenario 9 — adapter handler unpacks legacy tool dict for the registry
# ============================================================================

class TestLegacyAdapter:
    """The handler registered for `forget_about_me` must call into the
    legacy `_forget_about_me`, succeed end-to-end, and produce an audit row
    pointing at `agent_user_facts`."""

    @pytest.mark.asyncio
    async def test_forget_action_commits(self, fake_supabase: FakeSupabase) -> None:
        user_id = str(uuid.uuid4())
        fake_supabase.tables["agent_user_facts"] = [
            {"id": str(uuid.uuid4()), "user_id": user_id, "kind": "preference", "content": "v"},
        ]

        # forget_about_me is configured `requires_confirmation=True`; commit
        # directly via plan→pending→commit to exercise the full loop.
        plan_result = await plan_action(ActionRequest(
            tool="forget_about_me",
            args={},
            user_id=user_id,
            turn_id=str(uuid.uuid4()),
        ))
        assert plan_result.status == "pending"

        commit_result = await commit_pending_action(plan_result.pending_id, user_id)
        assert commit_result.status == "committed"
        assert commit_result.target_table == "agent_user_facts"
        assert fake_supabase.tables["agent_user_facts"] == []

        audit = fake_supabase.tables["agent_audit_log"][0]
        assert audit["tool_name"] == "forget_about_me"
        assert audit["status"] == "committed"


# ============================================================================
# Scenario 10 — end-to-end intercept ➜ /api/ai/confirm round trip
# ============================================================================

class TestLegacyInterceptToConfirmE2E:
    """Full round trip: legacy tool loop intercepts a destructive write,
    the frontend renders the pending card, the user taps Yes, we hit
    /api/ai/confirm → commit_pending_action → the write finally fires and
    an audit row is written. This locks the contract between
    `_maybe_intercept_legacy_tool_call` (ai_engine.py) and
    `commit_pending_action` (agent/actions.py) so a shape change in either
    breaks this test loudly.
    """

    @pytest.mark.asyncio
    async def test_forget_about_me_full_round_trip(
        self, fake_supabase: FakeSupabase
    ) -> None:
        """Chosen because `forget_about_me` is (a) in the intercept set,
        (b) already registered in `tool_actions.register_all()`, and (c)
        its underlying handler only touches `agent_user_facts` which the
        fake supabase can service without extra plumbing."""
        from backend.ai_engine import _maybe_intercept_legacy_tool_call

        user_id = str(uuid.uuid4())
        fake_supabase.tables["agent_user_facts"] = [
            {"id": str(uuid.uuid4()), "user_id": user_id,
             "kind": "preference", "content": "vegan"},
            {"id": str(uuid.uuid4()), "user_id": user_id,
             "kind": "style", "content": "brief replies"},
        ]

        # Step 1: legacy tool loop intercepts the write.
        intercept = await _maybe_intercept_legacy_tool_call(
            fn_name="forget_about_me",
            fn_args={},
            auth_user_id=user_id,
            language="en",
        )
        assert intercept is not None
        assert intercept["error"] == "awaiting_user_confirmation"
        env = intercept["pending_action"]
        pending_id = env["pending_id"]
        assert pending_id
        # The frontend receives this envelope and renders a Confirm card.
        assert env["tool"] == "forget_about_me"
        assert env["summary"]

        # A pending row exists but the write hasn't fired.
        pending_rows = fake_supabase.tables["agent_pending_actions"]
        assert len(pending_rows) == 1
        assert pending_rows[0]["status"] == "pending"
        assert len(fake_supabase.tables["agent_user_facts"]) == 2  # unchanged

        # Step 2: user taps Yes ➜ /api/ai/confirm ➜ commit_pending_action.
        commit_result = await commit_pending_action(pending_id, user_id)

        # Step 3: verify the write actually happened and the trail is
        # complete.
        assert commit_result.status == "committed"
        assert commit_result.tool == "forget_about_me"
        assert commit_result.audit_id is not None
        # Pending row transitioned.
        assert pending_rows[0]["status"] == "confirmed"
        # The user's facts are gone.
        assert fake_supabase.tables["agent_user_facts"] == []
        # Audit trail written.
        audit_rows = fake_supabase.tables.get("agent_audit_log", [])
        assert len(audit_rows) == 1
        assert audit_rows[0]["tool_name"] == "forget_about_me"
        assert audit_rows[0]["status"] == "committed"
        assert audit_rows[0]["actor_user_id"] == user_id

    @pytest.mark.asyncio
    async def test_cancel_flow_leaves_data_intact(
        self, fake_supabase: FakeSupabase
    ) -> None:
        """The cancel path (user taps No) must NOT execute the write and
        must flip the pending row to `cancelled`."""
        from backend.ai_engine import _maybe_intercept_legacy_tool_call

        user_id = str(uuid.uuid4())
        fake_supabase.tables["agent_user_facts"] = [
            {"id": str(uuid.uuid4()), "user_id": user_id,
             "kind": "preference", "content": "keep me"},
        ]

        intercept = await _maybe_intercept_legacy_tool_call(
            fn_name="forget_about_me",
            fn_args={},
            auth_user_id=user_id,
            language="es",
        )
        assert intercept is not None
        pending_id = intercept["pending_action"]["pending_id"]

        # Spanish envelope carries the Spanish summary end-to-end.
        assert "olvidar" in intercept["pending_action"]["summary"].lower()

        ok = await cancel_pending_action(pending_id, user_id)
        assert ok is True
        # Data preserved.
        assert len(fake_supabase.tables["agent_user_facts"]) == 1
        assert fake_supabase.tables["agent_pending_actions"][0]["status"] == "cancelled"
        # No audit row (nothing was committed).
        assert not fake_supabase.tables.get("agent_audit_log")

    @pytest.mark.asyncio
    async def test_wrong_user_cannot_confirm_others_pending(
        self, fake_supabase: FakeSupabase
    ) -> None:
        """Security: /api/ai/confirm scopes the lookup by user_id. A
        different signed-in user submitting someone else's pending_id
        must get a failed result, not execute the write."""
        from backend.ai_engine import _maybe_intercept_legacy_tool_call

        owner = str(uuid.uuid4())
        attacker = str(uuid.uuid4())
        fake_supabase.tables["agent_user_facts"] = [
            {"id": str(uuid.uuid4()), "user_id": owner,
             "kind": "preference", "content": "private"},
        ]

        intercept = await _maybe_intercept_legacy_tool_call(
            fn_name="forget_about_me",
            fn_args={},
            auth_user_id=owner,
            language="en",
        )
        pending_id = intercept["pending_action"]["pending_id"]

        # Attacker tries to commit owner's pending row.
        result = await commit_pending_action(pending_id, attacker)
        assert result.status == "failed"
        assert result.error and "not found" in result.error.lower()
        # Owner's data is still there.
        assert len(fake_supabase.tables["agent_user_facts"]) == 1
        # Pending row untouched.
        assert fake_supabase.tables["agent_pending_actions"][0]["status"] == "pending"
