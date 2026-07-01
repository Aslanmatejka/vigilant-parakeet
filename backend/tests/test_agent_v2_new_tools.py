"""
AGENT_V2 (Phase 4) — new WRITE tools
=====================================

Tests the four tools added to close the plan's tool-expansion gap:
`message_donor`, `schedule_pickup`, `join_community`, `leave_community`.

These tests stub Supabase REST calls so they run offline. Each verifies
the tool's happy-path shape + the most important negative branches
(missing args, empty message, past pickup, self-message).

Run:
    python -m pytest backend/tests/test_agent_v2_new_tools.py -v
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from backend import tools as tools_mod
from backend.agent import tool_actions as tool_actions_mod


USER_A = "aaaaaaaa-0000-0000-0000-000000000001"
USER_B = "bbbbbbbb-0000-0000-0000-000000000002"
LISTING_ID = "cccccccc-0000-0000-0000-000000000003"
CLAIM_ID = "dddddddd-0000-0000-0000-000000000004"
COMMUNITY_ID = "eeeeeeee-0000-0000-0000-000000000005"


class _FakeSupabase:
    """Minimal stub for supabase_get / supabase_post / supabase_patch used
    by the tool implementations. Configure via `configure(routes=...)`."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any] | None, dict[str, Any] | None]] = []
        self.get_returns: dict[str, list[dict[str, Any]]] = {}
        self.post_returns: dict[str, list[dict[str, Any]]] = {}
        self.patch_returns: dict[str, list[dict[str, Any]]] = {}
        self.post_raises: dict[str, Exception] = {}

    async def supabase_get(self, table: str, params: dict) -> list[dict]:
        self.calls.append(("get", table, params, None))
        return self.get_returns.get(table, [])

    async def supabase_patch(self, table: str, filters: dict, payload: dict) -> list[dict]:
        self.calls.append(("patch", table, filters, payload))
        return self.patch_returns.get(table, [{"id": USER_A, **payload}])

    async def supabase_post(self, table: str, payload: dict) -> list[dict]:
        self.calls.append(("post", table, None, payload))
        if table in self.post_raises:
            raise self.post_raises[table]
        return self.post_returns.get(table, [{"id": "new-id-1", **payload}])


@pytest.fixture()
def fake_supabase(monkeypatch):
    fake = _FakeSupabase()
    import backend.ai_engine as ai_engine

    monkeypatch.setattr(ai_engine, "supabase_get", fake.supabase_get, raising=False)
    monkeypatch.setattr(ai_engine, "supabase_patch", fake.supabase_patch, raising=False)
    monkeypatch.setattr(ai_engine, "supabase_post", fake.supabase_post, raising=False)
    # Some tools reach for httpx directly (send_notification). Stub it too.
    monkeypatch.setattr(
        ai_engine, "SUPABASE_URL", "http://fake.supabase", raising=False,
    )
    monkeypatch.setattr(
        ai_engine, "SUPABASE_SERVICE_KEY", "fake-key", raising=False,
    )
    return fake


# ============================================================================
# message_donor
# ============================================================================

class TestMessageDonor:
    def test_rejects_empty_message(self, fake_supabase):
        result = asyncio.run(
            tools_mod._message_donor(user_id=USER_A, listing_id=LISTING_ID, message="   ")
        )
        assert result["success"] is False
        assert "empty" in result["error"].lower()

    def test_rejects_missing_listing(self, fake_supabase):
        # No fake row for food_listings → tool sees "not found"
        result = asyncio.run(
            tools_mod._message_donor(
                user_id=USER_A, listing_id=LISTING_ID, message="Hey!",
            )
        )
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_rejects_self_message(self, fake_supabase):
        fake_supabase.get_returns["food_listings"] = [
            {"id": LISTING_ID, "title": "Bread", "user_id": USER_A},
        ]
        result = asyncio.run(
            tools_mod._message_donor(
                user_id=USER_A, listing_id=LISTING_ID, message="Hey me!",
            )
        )
        assert result["success"] is False
        assert "yourself" in result["error"].lower()

    def test_happy_path(self, fake_supabase, monkeypatch):
        fake_supabase.get_returns["food_listings"] = [
            {"id": LISTING_ID, "title": "Fresh bread", "user_id": USER_B},
        ]
        fake_supabase.get_returns["users"] = [
            {"id": USER_A, "name": "Alice"},
        ]

        # Stub the httpx-based notification send.
        class _Resp:
            def __init__(self):
                self.status_code = 201
            def raise_for_status(self):
                return None
            def json(self):
                return [{"id": "notif-1"}]

        class _Client:
            def __init__(self, *a, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return None
            async def post(self, *a, **kw): return _Resp()

        import httpx
        monkeypatch.setattr(httpx, "AsyncClient", _Client)

        result = asyncio.run(
            tools_mod._message_donor(
                user_id=USER_A, listing_id=LISTING_ID, message="Can I pick up tonight?",
            )
        )
        assert result["success"] is True
        assert result["notification_id"] == "notif-1"


# ============================================================================
# schedule_pickup
# ============================================================================

class TestSchedulePickup:
    def _future(self, hours: int = 3) -> str:
        return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()

    def test_requires_claim_or_listing(self, fake_supabase):
        result = asyncio.run(
            tools_mod._schedule_pickup(
                user_id=USER_A, pickup_datetime=self._future(),
            )
        )
        assert result["success"] is False
        assert "claim_id" in result["error"] or "listing_id" in result["error"]

    def test_rejects_past_time(self, fake_supabase):
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        result = asyncio.run(
            tools_mod._schedule_pickup(
                user_id=USER_A, claim_id=CLAIM_ID, pickup_datetime=past,
            )
        )
        assert result["success"] is False
        assert "future" in result["error"].lower()

    def test_rejects_beyond_7_days(self, fake_supabase):
        far = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
        result = asyncio.run(
            tools_mod._schedule_pickup(
                user_id=USER_A, claim_id=CLAIM_ID, pickup_datetime=far,
            )
        )
        assert result["success"] is False
        assert "7 days" in result["error"] or "seven" in result["error"].lower()

    def test_no_active_claim(self, fake_supabase):
        # Claim lookup returns nothing.
        result = asyncio.run(
            tools_mod._schedule_pickup(
                user_id=USER_A, claim_id=CLAIM_ID, pickup_datetime=self._future(),
            )
        )
        assert result["success"] is False
        assert "active claim" in result["error"].lower()

    def test_happy_path(self, fake_supabase):
        fake_supabase.get_returns["food_claims"] = [
            {"id": CLAIM_ID, "food_id": LISTING_ID, "claimer_id": USER_A, "status": "approved"},
        ]
        fake_supabase.post_returns["ai_reminders"] = [
            {"id": "rem-1"},
        ]
        result = asyncio.run(
            tools_mod._schedule_pickup(
                user_id=USER_A, claim_id=CLAIM_ID, pickup_datetime=self._future(),
                note="After work",
            )
        )
        assert result["success"] is True
        assert result["claim_id"] == CLAIM_ID
        assert result["reminder_id"] == "rem-1"


# ============================================================================
# join_community / leave_community
# ============================================================================

class TestJoinCommunity:
    def test_requires_identifier(self, fake_supabase):
        result = asyncio.run(tools_mod._join_community(user_id=USER_A))
        assert result["success"] is False

    def test_community_not_found(self, fake_supabase):
        # _resolve_community returns (None, None) with no fake rows.
        result = asyncio.run(
            tools_mod._join_community(user_id=USER_A, community_name="Mystery")
        )
        assert result["success"] is False
        assert result["error"] == "community_not_found"

    def test_happy_path_by_id(self, fake_supabase):
        fake_supabase.get_returns["communities"] = [
            {"id": COMMUNITY_ID, "name": "Mission Food Hub"},
        ]
        result = asyncio.run(
            tools_mod._join_community(user_id=USER_A, community_id=COMMUNITY_ID)
        )
        assert result["success"] is True
        assert result["community_id"] == COMMUNITY_ID
        # A PATCH to `users` with community_id must have been issued.
        assert any(
            c[0] == "patch" and c[1] == "users" and c[3].get("community_id") == COMMUNITY_ID
            for c in fake_supabase.calls
        )


class TestLeaveCommunity:
    def test_not_in_community(self, fake_supabase):
        fake_supabase.get_returns["users"] = [
            {"id": USER_A, "community_id": None},
        ]
        result = asyncio.run(tools_mod._leave_community(user_id=USER_A))
        assert result["success"] is False
        assert result["error"] == "not_in_community"

    def test_happy_path(self, fake_supabase):
        fake_supabase.get_returns["users"] = [
            {
                "id": USER_A,
                "community_id": COMMUNITY_ID,
                "communities": {"id": COMMUNITY_ID, "name": "Old Hub"},
            },
        ]
        result = asyncio.run(tools_mod._leave_community(user_id=USER_A))
        assert result["success"] is True
        assert result["prior_community_name"] == "Old Hub"
        # community_id should have been set to NULL.
        assert any(
            c[0] == "patch" and c[1] == "users" and c[3].get("community_id") is None
            for c in fake_supabase.calls
        )


# ============================================================================
# Action registry — the 4 tools are registered and target correct tables.
# ============================================================================

class TestActionRegistration:
    def test_all_four_registered(self):
        # Import triggers register_all() via backend.agent.__init__.
        from backend.agent.actions import get_action

        for name in (
            "message_donor",
            "schedule_pickup",
            "join_community",
            "leave_community",
        ):
            spec = get_action(name)
            assert spec is not None, f"missing action registration: {name}"
            assert spec.requires_confirmation is True

    def test_target_tables_mapping(self):
        from backend.agent.v2_graph import _ACTION_TARGET_TABLES

        assert _ACTION_TARGET_TABLES["message_donor"] == "notifications"
        assert _ACTION_TARGET_TABLES["schedule_pickup"] == "reminders"
        assert _ACTION_TARGET_TABLES["join_community"] == "users"
        assert _ACTION_TARGET_TABLES["leave_community"] == "users"


# ============================================================================
# Dispatcher — execute_tool routes the new tools.
# ============================================================================

class TestDispatcher:
    def test_execute_tool_recognises_all_four(self, fake_supabase):
        # Missing args → tools return {"success": False, ...} but the
        # dispatcher must NOT return {"error": "Unknown tool ..."}.
        for name in (
            "message_donor",
            "schedule_pickup",
            "join_community",
            "leave_community",
        ):
            result = asyncio.run(tools_mod.execute_tool(name, {"user_id": USER_A}))
            assert isinstance(result, dict)
            assert "Unknown tool" not in str(result.get("error", ""))
