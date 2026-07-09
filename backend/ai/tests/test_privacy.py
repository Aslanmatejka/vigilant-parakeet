"""Privacy tests: the AI must only ever act on the authenticated user.

Covers:
- every tool call has its ``user_id`` argument forced to ``auth_user_id``
- ``run_safe_query`` is auto-scoped so one user cannot enumerate another
  user's listings, requests, or profile.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.ai.ai_engine import ConversationEngine, _scope_safe_query


# ---------------------------------------------------------------------------
# _scope_safe_query
# ---------------------------------------------------------------------------

class TestScopeSafeQuery:
    def test_users_entity_injects_self_id(self):
        out = _scope_safe_query({"entity": "users", "filters": []}, 42)
        assert {"field": "id", "op": "eq", "value": 42} in out["filters"]

    def test_users_entity_drops_foreign_id_filter(self):
        out = _scope_safe_query(
            {"entity": "users",
             "filters": [{"field": "id", "op": "eq", "value": 7}]},
            42,
        )
        # Foreign id dropped, self id injected
        assert {"field": "id", "op": "eq", "value": 7} not in out["filters"]
        assert {"field": "id", "op": "eq", "value": 42} in out["filters"]

    def test_users_entity_injects_uuid_self_id(self):
        uid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        out = _scope_safe_query({"entity": "users", "filters": []}, uid)
        assert {"field": "id", "op": "eq", "value": uid} in out["filters"]

    def test_listings_scopes_to_donor_or_recipient(self):
        out = _scope_safe_query({"entity": "listings", "filters": []}, 9)
        fields = {f["field"] for f in out["filters"]}
        assert "donor_id" in fields or "recipient_id" in fields
        match = next(f for f in out["filters"]
                     if f["field"] in ("donor_id", "recipient_id"))
        assert match["value"] == 9

    def test_listings_honors_existing_self_recipient_filter(self):
        args = {
            "entity": "listings",
            "filters": [{"field": "recipient_id", "op": "eq", "value": 9}],
        }
        out = _scope_safe_query(args, 9)
        scope_filters = [f for f in out["filters"]
                         if f["field"] in ("donor_id", "recipient_id")]
        assert len(scope_filters) == 1

    def test_listings_drops_foreign_recipient_filter(self):
        args = {
            "entity": "listings",
            "filters": [{"field": "recipient_id", "op": "eq", "value": 11}],
        }
        out = _scope_safe_query(args, 9)
        assert {"field": "recipient_id", "op": "eq", "value": 11} not in out["filters"]
        scope = [f for f in out["filters"]
                 if f["field"] in ("donor_id", "recipient_id")]
        assert scope and scope[0]["value"] == 9

    def test_requests_injects_recipient_id(self):
        out = _scope_safe_query({"entity": "requests"}, 5)
        assert {"field": "recipient_id", "op": "eq", "value": 5} in out["filters"]

    def test_centers_unchanged(self):
        args = {"entity": "centers", "filters": [{"field": "is_active",
                                                  "op": "eq", "value": True}]}
        out = _scope_safe_query(args, 5)
        assert out == args

    def test_unknown_entity_unchanged(self):
        args = {"entity": "bogus", "filters": []}
        out = _scope_safe_query(args, 5)
        assert out == args

    def test_non_dict_input_safe(self):
        out = _scope_safe_query("not a dict", 5)
        assert out == {"entity": "centers"}


# ---------------------------------------------------------------------------
# user_id enforcement in _call_openai_chat
# ---------------------------------------------------------------------------

class TestUserIdEnforcement:
    @pytest.mark.asyncio
    async def test_read_tool_user_id_forced_to_auth(self):
        """A prompt-injection passing a foreign user_id must be overwritten."""
        engine = ConversationEngine()

        captured = {}

        async def fake_execute(name, args):
            captured["name"] = name
            captured["args"] = dict(args)
            return {"ok": True}

        engine._execute_tool = fake_execute

        # Fake OpenAI: first response asks for get_user_profile(user_id=999),
        # second response returns assistant text.
        first_resp = MagicMock()
        first_resp.json.return_value = {
            "choices": [{"message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "get_user_profile",
                        "arguments": json.dumps({"user_id": "999"}),
                    },
                }],
            }}]
        }
        second_resp = MagicMock()
        second_resp.json.return_value = {
            "choices": [{"message": {"content": "done"}}]
        }

        async def fake_retry(*_a, **_kw):
            if "responses" not in captured:
                captured["responses"] = [first_resp, second_resp]
            return captured["responses"].pop(0)

        with patch("backend.ai.ai_engine._openai_with_retry",
                   new=AsyncMock(side_effect=fake_retry)), \
             patch("backend.ai.ai_engine.OPENAI_API_KEY", "sk-test"):
            text = await engine._call_openai_chat(
                [{"role": "user", "content": "show me my profile please"}],
                lang="en",
                auth_user_id=42,
            )

        assert captured["name"] == "get_user_profile"
        # user_id forced from "999" to "42"
        assert captured["args"]["user_id"] == "42"
        assert text == "done"

    @pytest.mark.asyncio
    async def test_run_safe_query_scoped_for_users_entity(self):
        engine = ConversationEngine()

        captured = {}

        async def fake_execute(name, args):
            captured["name"] = name
            captured["args"] = dict(args)
            return {"rows": []}

        engine._execute_tool = fake_execute

        tool_msg = {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call_2",
                "type": "function",
                "function": {
                    "name": "run_safe_query",
                    "arguments": json.dumps({
                        "entity": "users",
                        "filters": [{"field": "id", "op": "eq", "value": 13}],
                    }),
                },
            }],
        }
        first = MagicMock(); first.json.return_value = {"choices": [{"message": tool_msg}]}
        second = MagicMock(); second.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        responses = [first, second]

        async def fake_retry(*_a, **_kw):
            return responses.pop(0)

        with patch("backend.ai.ai_engine._openai_with_retry",
                   new=AsyncMock(side_effect=fake_retry)), \
             patch("backend.ai.ai_engine.OPENAI_API_KEY", "sk-test"):
            await engine._call_openai_chat(
                [{"role": "user", "content": "look up user 13"}],
                lang="en",
                auth_user_id=77,
            )

        filters = captured["args"]["filters"]
        # The foreign filter was dropped, our auth id injected
        assert {"field": "id", "op": "eq", "value": 13} not in filters
        assert {"field": "id", "op": "eq", "value": 77} in filters
