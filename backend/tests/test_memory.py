"""
Tests for backend AI long-term memory layer (ai_user_memory).
=============================================================

Covers:
  - _normalize_memory_key / _normalize_memory_value sanitization
  - format_memories_for_prompt rendering + confidence filter
  - upsert_user_memory, get_user_memories, delete_user_memory, clear_user_memories
  - extract_and_save_memories (background extractor) — happy path + bad json
  - Tool handlers: _remember_user_fact, _forget_user_fact, _list_user_facts
  - _message_donor: donor resolution + sender lookup
  - _extend_listing_deadline: ownership + deadline parsing

Run:
    python -m pytest backend/tests/test_memory.py -v
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

import pytest

# Ensure env vars are set so module-level config reads succeed.
_ENV = {
    "OPENAI_API_KEY": "sk-test-key",
    "SUPABASE_URL": "https://test.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
    "MAPBOX_TOKEN": "pk.test-mapbox",
}

with patch.dict("os.environ", _ENV, clear=False):
    from backend.ai_engine import (
        _normalize_memory_key,
        _normalize_memory_value,
        format_memories_for_prompt,
        upsert_user_memory,
        get_user_memories,
        delete_user_memory,
        clear_user_memories,
        extract_and_save_memories,
    )
    from backend.tools import (
        _remember_user_fact,
        _forget_user_fact,
        _list_user_facts,
        _message_donor,
        _extend_listing_deadline,
        _resolve_new_pickup_by,
    )


# ---------------------------------------------------------------------------
# Key / value normalization
# ---------------------------------------------------------------------------

class TestMemoryNormalization:
    def test_normalize_key_lowercases_and_snake_cases(self):
        assert _normalize_memory_key("Household Size") == "household_size"
        assert _normalize_memory_key("dietary-restriction") == "dietary_restriction"
        assert _normalize_memory_key("  HAS_CAR  ") == "has_car"

    def test_normalize_key_rejects_empty_or_too_long(self):
        assert _normalize_memory_key("") is None
        assert _normalize_memory_key("   ") is None
        assert _normalize_memory_key(None) is None
        assert _normalize_memory_key("x" * 200) is None

    def test_normalize_key_strips_special_chars(self):
        assert _normalize_memory_key("!@#$%") is None
        assert _normalize_memory_key("foo!bar") == "foo_bar"

    def test_normalize_value_trims_and_caps_length(self):
        assert _normalize_memory_value("  hello  ") == "hello"
        assert _normalize_memory_value("") is None
        assert _normalize_memory_value(None) is None
        long = "x" * 800
        normed = _normalize_memory_value(long)
        assert normed is not None
        assert len(normed) <= 500
        assert normed.endswith("...")


# ---------------------------------------------------------------------------
# Prompt rendering
# ---------------------------------------------------------------------------

class TestFormatMemoriesForPrompt:
    def test_empty_returns_empty_string(self):
        assert format_memories_for_prompt([]) == ""

    def test_renders_as_bulleted_list(self):
        out = format_memories_for_prompt([
            {"key": "household_size", "value": "4 people", "confidence": 0.9},
            {"key": "dietary_restriction", "value": "vegan", "confidence": 0.95},
        ])
        assert "## What I Remember About You" in out
        assert "- household size: 4 people" in out
        assert "- dietary restriction: vegan" in out

    def test_low_confidence_filtered_out(self):
        out = format_memories_for_prompt([
            {"key": "high_conf", "value": "real", "confidence": 0.8},
            {"key": "low_conf", "value": "noise", "confidence": 0.3},
        ], min_confidence=0.5)
        assert "high conf" in out
        assert "low conf" not in out
        assert "noise" not in out

    def test_caps_at_20_items(self):
        many = [
            {"key": f"k{i}", "value": f"v{i}", "confidence": 0.9}
            for i in range(50)
        ]
        out = format_memories_for_prompt(many)
        lines = [l for l in out.splitlines() if l.startswith("- ")]
        assert len(lines) == 20


# ---------------------------------------------------------------------------
# Storage CRUD (Supabase mocked)
# ---------------------------------------------------------------------------

class TestMemoryCrud:
    @pytest.mark.asyncio
    async def test_upsert_user_memory_normalizes_and_calls_supabase(self):
        fake_row = {"id": "x", "key": "household_size", "value": "4", "confidence": 1.0}
        with patch("backend.ai_engine._get_http_client") as get_client:
            fake_resp = AsyncMock()
            fake_resp.json = lambda: [fake_row]
            fake_resp.raise_for_status = lambda: None
            client = AsyncMock()
            client.post = AsyncMock(return_value=fake_resp)
            get_client.return_value = client

            result = await upsert_user_memory(
                "user-1", "Household Size", "4", confidence=1.0, source="explicit",
            )

            assert result == fake_row
            assert client.post.await_count == 1
            args, kwargs = client.post.call_args
            assert kwargs["json"]["key"] == "household_size"
            assert kwargs["json"]["source"] == "explicit"
            assert kwargs["params"] == {"on_conflict": "user_id,key"}

    @pytest.mark.asyncio
    async def test_upsert_rejects_bad_key(self):
        result = await upsert_user_memory("user-1", "", "value")
        assert result is None

    @pytest.mark.asyncio
    async def test_upsert_clamps_confidence(self):
        with patch("backend.ai_engine._get_http_client") as get_client:
            fake_resp = AsyncMock()
            fake_resp.json = lambda: [{"id": "x"}]
            fake_resp.raise_for_status = lambda: None
            client = AsyncMock()
            client.post = AsyncMock(return_value=fake_resp)
            get_client.return_value = client

            await upsert_user_memory("user-1", "key1", "val", confidence=5.0)

            body = client.post.call_args.kwargs["json"]
            assert body["confidence"] == 1.0

    @pytest.mark.asyncio
    async def test_get_user_memories_returns_rows(self):
        rows = [
            {"id": "1", "key": "a", "value": "x", "confidence": 0.9},
            {"id": "2", "key": "b", "value": "y", "confidence": 0.2},
        ]
        with patch("backend.ai_engine.supabase_get", new=AsyncMock(return_value=rows)):
            out = await get_user_memories("user-1", min_confidence=0.0)
            assert len(out) == 2
            out2 = await get_user_memories("user-1", min_confidence=0.5)
            assert len(out2) == 1
            assert out2[0]["key"] == "a"

    @pytest.mark.asyncio
    async def test_get_user_memories_gracefully_handles_missing_table(self):
        with patch("backend.ai_engine.supabase_get", new=AsyncMock(side_effect=Exception("relation does not exist"))):
            out = await get_user_memories("user-1")
            assert out == []

    @pytest.mark.asyncio
    async def test_delete_user_memory_calls_supabase(self):
        with patch("backend.ai_engine.supabase_delete", new=AsyncMock(return_value=1)) as mock_del:
            count = await delete_user_memory("user-1", "household_size")
            assert count == 1
            mock_del.assert_awaited_once_with("ai_user_memory", {
                "user_id": "eq.user-1",
                "key": "eq.household_size",
            })

    @pytest.mark.asyncio
    async def test_delete_rejects_invalid_key(self):
        with patch("backend.ai_engine.supabase_delete", new=AsyncMock(return_value=1)) as mock_del:
            assert await delete_user_memory("user-1", "") == 0
            mock_del.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_clear_user_memories_returns_count(self):
        with patch("backend.ai_engine.supabase_delete", new=AsyncMock(return_value=7)):
            count = await clear_user_memories("user-1")
            assert count == 7


# ---------------------------------------------------------------------------
# Background extractor
# ---------------------------------------------------------------------------

class TestExtractAndSaveMemories:
    @pytest.mark.asyncio
    async def test_skips_anonymous_users(self):
        out = await extract_and_save_memories(
            "00000000-0000-0000-0000-000000000000", "hi", "hello",
        )
        assert out == []

    @pytest.mark.asyncio
    async def test_extracts_and_persists(self):
        # Mock OpenAI's response with a JSON memories array
        openai_payload = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "memories": [
                            {"key": "Household Size", "value": "4 people", "confidence": 0.92},
                            {"key": "diet", "value": "vegan", "confidence": 0.85},
                            {"key": "low_conf", "value": "ignore me", "confidence": 0.2},
                        ],
                    }),
                },
            }],
        }
        fake_resp = AsyncMock()
        fake_resp.json = lambda: openai_payload
        fake_resp.raise_for_status = lambda: None
        client = AsyncMock()
        client.post = AsyncMock(return_value=fake_resp)

        with patch("backend.ai_engine._get_http_client", return_value=client), \
             patch("backend.ai_engine.upsert_user_memory", new=AsyncMock(side_effect=lambda *a, **k: {"key": a[1], "value": a[2]})):
            saved = await extract_and_save_memories(
                "user-1",
                "I have 4 people in my household and we're vegan",
                "Got it!",
            )

        # Low-confidence item filtered out, others saved
        assert len(saved) == 2
        keys = {s["key"] for s in saved}
        assert "household_size" in keys
        assert "diet" in keys

    @pytest.mark.asyncio
    async def test_handles_invalid_json_gracefully(self):
        bad_payload = {
            "choices": [{"message": {"content": "not json at all"}}],
        }
        fake_resp = AsyncMock()
        fake_resp.json = lambda: bad_payload
        fake_resp.raise_for_status = lambda: None
        client = AsyncMock()
        client.post = AsyncMock(return_value=fake_resp)

        with patch("backend.ai_engine._get_http_client", return_value=client):
            out = await extract_and_save_memories("user-1", "hi", "hello")
        assert out == []


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

class TestMemoryTools:
    @pytest.mark.asyncio
    async def test_remember_user_fact_saves(self):
        saved = {"key": "diet", "value": "vegan", "confidence": 1.0}
        with patch("backend.ai_engine.upsert_user_memory", new=AsyncMock(return_value=saved)):
            out = await _remember_user_fact("user-1", "diet", "vegan", confidence=1.0)
            assert out["success"] is True
            assert out["key"] == "diet"
            assert "vegan" in out["summary"]

    @pytest.mark.asyncio
    async def test_remember_user_fact_rejects_bad_key(self):
        out = await _remember_user_fact("user-1", "", "anything")
        assert out["success"] is False
        assert "key" in out["error"].lower()

    @pytest.mark.asyncio
    async def test_remember_user_fact_rejects_empty_value(self):
        out = await _remember_user_fact("user-1", "diet", "   ")
        assert out["success"] is False

    @pytest.mark.asyncio
    async def test_forget_user_fact_returns_zero_when_missing(self):
        with patch("backend.ai_engine.delete_user_memory", new=AsyncMock(return_value=0)):
            out = await _forget_user_fact("user-1", "diet")
            assert out["success"] is True
            assert out["removed"] == 0

    @pytest.mark.asyncio
    async def test_forget_user_fact_returns_count_when_removed(self):
        with patch("backend.ai_engine.delete_user_memory", new=AsyncMock(return_value=1)):
            out = await _forget_user_fact("user-1", "diet")
            assert out["success"] is True
            assert out["removed"] == 1

    @pytest.mark.asyncio
    async def test_list_user_facts_empty(self):
        with patch("backend.ai_engine.get_user_memories", new=AsyncMock(return_value=[])):
            out = await _list_user_facts("user-1")
            assert out["success"] is True
            assert out["facts"] == []
            assert "don't have" in out["summary"].lower()

    @pytest.mark.asyncio
    async def test_list_user_facts_renders_summary(self):
        rows = [
            {"key": "diet", "value": "vegan", "confidence": 1.0, "source": "explicit", "last_seen": "x"},
            {"key": "household_size", "value": "4", "confidence": 0.9, "source": "extracted", "last_seen": "x"},
        ]
        with patch("backend.ai_engine.get_user_memories", new=AsyncMock(return_value=rows)):
            out = await _list_user_facts("user-1")
            assert out["success"] is True
            assert len(out["facts"]) == 2
            assert "diet: vegan" in out["summary"]
            assert "household size: 4" in out["summary"]


# ---------------------------------------------------------------------------
# message_donor
# ---------------------------------------------------------------------------

class TestMessageDonor:
    @pytest.mark.asyncio
    async def test_resolves_listing_and_sends_notification(self):
        listing_rows = [{"id": "lst-1", "title": "Sourdough", "user_id": "donor-9"}]
        sender_rows = [{"name": "Sam", "full_name": None}]

        async def fake_get(table, params):
            if table == "food_listings":
                return listing_rows
            if table == "users":
                return sender_rows
            return []

        with patch("backend.ai_engine.supabase_get", new=AsyncMock(side_effect=fake_get)), \
             patch("backend.tools._send_notification", new=AsyncMock(return_value={"success": True, "notification_id": "notif-1"})) as send:
            out = await _message_donor("user-1", "lst-1", "Running 10 min late!", topic="Late")

        assert out["success"] is True
        assert out["donor_id"] == "donor-9"
        send.assert_awaited_once()
        kwargs = send.call_args.kwargs
        assert kwargs["user_id"] == "donor-9"
        assert "Sam" in kwargs["message"]
        assert "Sourdough" in kwargs["message"]

    @pytest.mark.asyncio
    async def test_rejects_self_message(self):
        listing_rows = [{"id": "lst-1", "title": "Sourdough", "user_id": "user-1"}]
        with patch("backend.ai_engine.supabase_get", new=AsyncMock(return_value=listing_rows)):
            out = await _message_donor("user-1", "lst-1", "hi me")
        assert out["success"] is False
        assert "yourself" in out["error"]

    @pytest.mark.asyncio
    async def test_returns_error_when_listing_missing(self):
        with patch("backend.ai_engine.supabase_get", new=AsyncMock(return_value=[])):
            out = await _message_donor("user-1", "lst-x", "hello")
        assert out["success"] is False
        assert "not found" in out["error"].lower()

    @pytest.mark.asyncio
    async def test_rejects_empty_message(self):
        out = await _message_donor("user-1", "lst-1", "   ")
        assert out["success"] is False


# ---------------------------------------------------------------------------
# extend_listing_deadline
# ---------------------------------------------------------------------------

class TestResolveNewPickupBy:
    def test_relative_hours(self):
        out = _resolve_new_pickup_by("+4h")
        assert out is not None
        delta = out - datetime.now(timezone.utc)
        assert timedelta(hours=3, minutes=55) < delta < timedelta(hours=4, minutes=5)

    def test_relative_days(self):
        out = _resolve_new_pickup_by("+1d")
        assert out is not None
        delta = out - datetime.now(timezone.utc)
        assert timedelta(hours=23) < delta < timedelta(hours=25)

    def test_iso_timestamp(self):
        fixed = "2099-12-31T23:59:00Z"
        out = _resolve_new_pickup_by(fixed)
        assert out is not None
        assert out.year == 2099 and out.month == 12 and out.day == 31

    def test_tomorrow_with_time(self):
        out = _resolve_new_pickup_by("tomorrow 09:30")
        assert out is not None
        tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).date()
        assert out.date() == tomorrow
        assert out.hour == 9 and out.minute == 30

    def test_invalid_returns_none(self):
        assert _resolve_new_pickup_by("definitely not a time") is None
        assert _resolve_new_pickup_by("") is None


class TestExtendListingDeadline:
    @pytest.mark.asyncio
    async def test_extends_when_owner_matches(self):
        listing_rows = [{
            "id": "lst-1", "title": "Bread", "user_id": "owner-1",
            "pickup_by": "2024-01-01T00:00:00Z", "status": "approved",
        }]
        with patch("backend.ai_engine.supabase_get", new=AsyncMock(return_value=listing_rows)), \
             patch("backend.ai_engine.supabase_patch", new=AsyncMock(return_value={})) as patch_call:
            out = await _extend_listing_deadline("owner-1", "lst-1", "+4h")

        assert out["success"] is True
        assert out["listing_id"] == "lst-1"
        assert "new_pickup_by" in out
        patch_call.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rejects_non_owner(self):
        listing_rows = [{
            "id": "lst-1", "title": "Bread", "user_id": "someone-else",
        }]
        with patch("backend.ai_engine.supabase_get", new=AsyncMock(return_value=listing_rows)):
            out = await _extend_listing_deadline("attacker-1", "lst-1", "+4h")
        assert out["success"] is False
        assert "owner" in out["error"].lower()

    @pytest.mark.asyncio
    async def test_rejects_past_deadline(self):
        listing_rows = [{
            "id": "lst-1", "title": "Bread", "user_id": "owner-1",
        }]
        past = "2000-01-01T00:00:00Z"
        with patch("backend.ai_engine.supabase_get", new=AsyncMock(return_value=listing_rows)):
            out = await _extend_listing_deadline("owner-1", "lst-1", past)
        assert out["success"] is False
        assert "future" in out["error"].lower()

    @pytest.mark.asyncio
    async def test_rejects_unparseable_deadline(self):
        listing_rows = [{
            "id": "lst-1", "title": "Bread", "user_id": "owner-1",
        }]
        with patch("backend.ai_engine.supabase_get", new=AsyncMock(return_value=listing_rows)):
            out = await _extend_listing_deadline("owner-1", "lst-1", "next year sometime")
        assert out["success"] is False
        assert "parse" in out["error"].lower()
