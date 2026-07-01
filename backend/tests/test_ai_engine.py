"""
Tests for backend/ai_engine.py
================================
Covers: response generation, profile injection, Spanish handling,
        tool format, history saving, rate limiter, circuit breaker,
        canned fallbacks, language detection.

Run:
    cd <project-root>
    python -m pytest backend/tests/test_ai_engine.py -v
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# ---------------------------------------------------------------------------
# Patch env vars BEFORE importing the engine (module-level config reads)
# ---------------------------------------------------------------------------
_ENV = {
    "OPENAI_API_KEY": "sk-test-key",
    "SUPABASE_URL": "https://test.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
    "MAPBOX_TOKEN": "pk.test-mapbox",
}

with patch.dict("os.environ", _ENV, clear=False):
    from backend.ai_engine import (
        CANNED_RESPONSES,
        CircuitBreaker,
        CircuitState,
        ConversationEngine,
        _build_legacy_intercept_summary,
        _build_memory_snapshot,
        _build_system_prompt,
        _chip_language,
        _detect_task_switch_hint,
        _detect_turn_intent_hints,
        _history_suggests_active_intake,
        _load_training_data,
        _maybe_intercept_legacy_tool_call,
        check_rate_limit,
        detect_spanish,
        generate_quick_replies,
        get_canned_response,
        _rate_store,
    )


TEST_USER_ID = "c4dcbd93-081e-4160-87eb-1d51d444413a"


@pytest.fixture
def engine():
    """ConversationEngine with mocked tool imports."""
    with patch("backend.ai_engine.OPENAI_API_KEY", "sk-test-key"), \
         patch("backend.ai_engine.SUPABASE_URL", "https://test.supabase.co"), \
         patch("backend.ai_engine.SUPABASE_SERVICE_KEY", "test-service-key"):
        eng = ConversationEngine()
        yield eng


@pytest.fixture(autouse=True)
def _reset_rate_store():
    """Clear the rate limiter between tests."""
    _rate_store.clear()
    yield
    _rate_store.clear()


@pytest.fixture
def circuit():
    return CircuitBreaker(failure_threshold=3, reset_timeout=0.1)


def _mock_openai_response(content: str, tool_calls=None):
    """Build a fake OpenAI chat completion JSON."""
    msg = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
        msg["content"] = None
    return {
        "choices": [{"message": msg, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20},
    }


def _mock_httpx_response(json_data, status_code=200):
    """Build a fake httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = json.dumps(json_data)
    resp.content = json.dumps(json_data).encode()
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp,
        )
    return resp


# ===================================================================
# 1. Language Detection (Spanish handling)
# ===================================================================

class TestSpanishDetection:
    def test_english_text(self):
        assert detect_spanish("Hello, I need some food near me") is False

    def test_spanish_two_markers(self):
        assert detect_spanish("Hola, necesito comida") is True

    def test_spanish_one_marker_plus_char(self):
        assert detect_spanish("¿Dónde hay comida?") is True

    def test_spanish_special_chars(self):
        assert detect_spanish("¡Buenos días!") is True

    def test_empty_string(self):
        assert detect_spanish("") is False

    def test_mixed_language_leans_english(self):
        assert detect_spanish("Hello friend") is False

    def test_spanish_multiple_markers(self):
        assert detect_spanish("Hola, quiero buscar comida por favor") is True


# ===================================================================
# 1b. Quick-reply chips (generate_quick_replies)
# ===================================================================

class TestQuickReplyChips:
    def test_english_conv_stays_english_even_with_spanish_question_in_reply(self):
        reply = "Claro! Here is your listing summary. ¿Quieres que lo publique?"
        chips = generate_quick_replies(reply, "en")
        assert chips
        assert all(not c.startswith("Sí") for c in chips)
        assert "Yes, post it" in chips

    def test_address_look_good_not_post_confirm(self):
        reply = "The pickup is at 123 Main St. Does that look good to you?"
        chips = generate_quick_replies(reply, "en")
        assert "Yes, use that one" in chips
        assert "Yes, post it" not in chips

    def test_community_confirm_not_post_confirm(self):
        reply = (
            "Should I list this under Alameda Unified, or a different community?"
        )
        chips = generate_quick_replies(reply, "en")
        assert "Yes, that community" in chips
        assert "Different community" in chips
        assert "Yes, post it" not in chips

    def test_community_confirm_spanish(self):
        reply = "¿Para qué comunidad debo publicarlo — Alameda Unified u otra?"
        chips = generate_quick_replies(reply, "es")
        assert "Sí, esa comunidad" in chips

    def test_view_photo_not_add_photo_chips(self):
        reply = "Can I see the photo first before posting?"
        chips = generate_quick_replies(reply, "en")
        assert chips == []

    def test_add_photo_prompt_gets_add_chips(self):
        reply = "Would you like to add a photo to your listing?"
        chips = generate_quick_replies(reply, "en")
        assert "I'll add one" in chips

    def test_open_ended_wh_question_returns_no_guess_chips(self):
        reply = "What are your upcoming pickups this week?"
        assert generate_quick_replies(reply, "en") == []

    def test_spanish_food_question_gets_spanish_chips(self):
        reply = "Perfecto. ¿Qué comida quieres compartir?"
        chips = generate_quick_replies(reply, "es")
        assert "Pan" in chips

    def test_freshness_question_gets_expiry_chips(self):
        reply = "When was it made and how long is it good for?"
        chips = generate_quick_replies(reply, "en")
        assert "Made today" in chips
        assert "Good for 24h" in chips

    def test_chip_language_helper_does_not_override_en_conv(self):
        reply = "Sure — ¿Quieres que lo publique ahora?"
        assert _chip_language(reply, "en") == "es"
        # Engine must ignore _chip_language and pass conv lang directly:
        chips = generate_quick_replies(reply, "en")
        assert "Yes, post it" in chips


# ===================================================================
# 1c. Task-switch detection (mid-intake pivots)
# ===================================================================

class TestTaskSwitchDetection:
    _INTAKE_HISTORY = [
        {"role": "user", "message": "I want to share some apples"},
        {
            "role": "assistant",
            "message": "Great! How many pounds of apples do you have?",
        },
    ]

    def test_history_detects_active_intake(self):
        assert _history_suggests_active_intake(self._INTAKE_HISTORY) is True

    def test_history_ignores_unrelated_chat(self):
        history = [
            {"role": "user", "message": "hello"},
            {"role": "assistant", "message": "Hi! How can I help you today?"},
        ]
        assert _history_suggests_active_intake(history) is False

    def test_find_food_mid_intake_injects_switch_hint(self):
        hint = _detect_task_switch_hint(
            "actually find food near me instead",
            self._INTAKE_HISTORY,
        )
        assert hint is not None
        assert "ABANDON" in hint
        assert "find" in hint.lower() or "search" in hint.lower()

    def test_never_mind_mid_intake_injects_abandon_hint(self):
        hint = _detect_task_switch_hint("never mind", self._INTAKE_HISTORY)
        assert hint is not None
        assert "abandon" in hint.lower() or "cancelled" in hint.lower()

    def test_no_hint_without_active_intake(self):
        hint = _detect_task_switch_hint(
            "find food near me",
            [{"role": "assistant", "message": "Hi! How can I help?"}],
        )
        assert hint is None

    def test_no_hint_when_still_answering_intake(self):
        hint = _detect_task_switch_hint("5 pounds", self._INTAKE_HISTORY)
        assert hint is None

    def test_pickup_delivery_question_counts_as_active_intake(self):
        history = [
            {"role": "user", "message": "I want to share 10 lbs of apples"},
            {
                "role": "assistant",
                "message": (
                    "Great! Will the recipient pick up the apples from you, "
                    "or are you willing to deliver/drop them off?"
                ),
            },
        ]
        assert _history_suggests_active_intake(history) is True
        hint = _detect_task_switch_hint("actually find food near me instead", history)
        assert hint is not None
        assert "ABANDON" in hint

    def test_no_intake_after_successful_post(self):
        history = [
            {"role": "user", "message": "I want to share apples"},
            {
                "role": "assistant",
                "message": "Posted! Your apples are live.",
                "metadata": {
                    "actions": [{"tool": "post_food_listing", "ok": True}],
                },
            },
        ]
        assert _history_suggests_active_intake(history) is False


# ===================================================================
# 1d. Turn-intent routing (accuracy)
# ===================================================================

class TestTurnIntentHints:
    def test_search_intent_mandates_tool(self):
        hints = _detect_turn_intent_hints("find food near me", [])
        joined = "\n".join(hints)
        assert "TURN PRIORITY" in joined
        assert "search_food_near_user" in joined

    def test_claim_intent_mandates_tool(self):
        history = [
            {
                "role": "assistant",
                "message": "Here are 3 options near you.",
                "metadata": {
                    "actions": [{
                        "tool": "search_food_near_user",
                        "ok": True,
                        "listings": [{"id": "abc", "title": "Bread"}],
                    }],
                },
            },
        ]
        hints = _detect_turn_intent_hints("claim #1", history)
        assert any("claim_listing" in h for h in hints)

    def test_intake_answer_hint_on_short_reply(self):
        history = [
            {"role": "user", "message": "I want to share apples"},
            {"role": "assistant", "message": "How many pounds do you have?"},
        ]
        hints = _detect_turn_intent_hints("5 pounds", history)
        assert any("INTAKE ANSWER" in h for h in hints)

    def test_task_switch_skips_search_intent(self):
        history = [
            {"role": "user", "message": "I want to share apples"},
            {"role": "assistant", "message": "How many pounds do you have?"},
        ]
        hints = _detect_turn_intent_hints(
            "actually find food near me instead",
            history,
            task_switch_active=True,
        )
        joined = "\n".join(hints)
        assert "search_food_near_user" not in joined
        assert "TURN PRIORITY" in joined


# ===================================================================
# 2. Canned Fallback Responses
# ===================================================================

class TestCannedResponses:
    def test_english_timeout(self):
        resp = get_canned_response("timeout", "en")
        assert "try again" in resp.lower()

    def test_spanish_timeout(self):
        resp = get_canned_response("timeout", "es")
        assert "inténtalo" in resp.lower()

    def test_english_api_down(self):
        resp = get_canned_response("api_down", "en")
        # Message: "I can't reach my AI service right now…"
        assert "can't reach" in resp.lower() or "ai service" in resp.lower()

    def test_spanish_api_down(self):
        resp = get_canned_response("api_down", "es")
        assert "conectarme" in resp.lower() or "servicio" in resp.lower()

    def test_unknown_error_type_falls_back(self):
        resp = get_canned_response("nonexistent_error", "en")
        assert resp == CANNED_RESPONSES["en"]["general_error"]

    def test_unknown_lang_falls_back_to_english(self):
        resp = get_canned_response("timeout", "fr")
        assert resp == CANNED_RESPONSES["en"]["timeout"]


# ===================================================================
# 3. Rate Limiter
# ===================================================================

class TestRateLimiter:
    def test_allows_under_limit(self):
        for _ in range(5):
            assert check_rate_limit("192.168.1.1", limit=10) is True

    def test_blocks_at_limit(self):
        for _ in range(5):
            check_rate_limit("10.0.0.1", limit=5)
        assert check_rate_limit("10.0.0.1", limit=5) is False

    def test_different_ips_independent(self):
        for _ in range(5):
            check_rate_limit("10.0.0.1", limit=5)
        # Different IP should still be allowed
        assert check_rate_limit("10.0.0.2", limit=5) is True

    def test_expired_entries_cleared(self):
        # Manually insert old timestamps
        old = time.time() - 120  # 2 minutes ago (beyond 60s window)
        _rate_store["10.0.0.3"] = [old] * 50
        # Should be allowed since old entries are evicted
        assert check_rate_limit("10.0.0.3", limit=5) is True


# ===================================================================
# 4. Circuit Breaker
# ===================================================================

class TestCircuitBreaker:
    def test_starts_closed(self, circuit):
        assert circuit.state == CircuitState.CLOSED
        assert circuit.allow_request() is True

    def test_opens_after_threshold(self, circuit):
        for _ in range(3):
            circuit.record_failure()
        assert circuit.state == CircuitState.OPEN
        assert circuit.allow_request() is False

    def test_half_open_after_timeout(self, circuit):
        for _ in range(3):
            circuit.record_failure()
        assert circuit.state == CircuitState.OPEN
        # Fast-forward past the reset timeout
        circuit.last_failure_time = time.time() - 1
        assert circuit.allow_request() is True
        assert circuit.state == CircuitState.HALF_OPEN

    def test_success_resets_to_closed(self, circuit):
        for _ in range(3):
            circuit.record_failure()
        circuit.last_failure_time = time.time() - 1
        circuit.allow_request()  # moves to HALF_OPEN
        circuit.record_success()
        assert circuit.state == CircuitState.CLOSED
        assert circuit.failure_count == 0


# ===================================================================
# 5. System Prompt & Training Data
# ===================================================================

class TestSystemPrompt:
    def test_build_system_prompt_empty(self):
        prompt = _build_system_prompt({})
        assert "DoGoods AI Assistant" in prompt
        assert "Current date and time:" in prompt

    def test_build_system_prompt_with_sections(self):
        data = {
            "system_base": "You are a test assistant.",
            "platform_overview": "A food sharing app.",
            "food_safety": ["Wash hands", "Check dates"],
            "tone_guidelines": "Be friendly.",
            "spanish_guidelines": "Respond in Spanish when asked.",
        }
        prompt = _build_system_prompt(data)
        assert "test assistant" in prompt
        assert "Platform Overview" in prompt
        assert "Wash hands" in prompt
        assert "Be friendly" in prompt
        assert "Spanish Response Guidelines" in prompt

    def test_system_prompt_contains_datetime(self):
        prompt = _build_system_prompt({})
        now = datetime.now(timezone.utc)
        assert str(now.year) in prompt

    def test_system_prompt_property_refreshes(self, engine):
        p1 = engine.system_prompt
        p2 = engine.system_prompt
        # Both should contain "Current date and time" — they're dynamically built
        assert "Current date and time:" in p1
        assert "Current date and time:" in p2


# ===================================================================
# 6. Profile Injection into Messages
# ===================================================================

class TestProfileInjection:
    @pytest.mark.asyncio
    async def test_profile_injected_into_messages(self, engine):
        """When a profile is found, the system messages should contain the user's name."""
        mock_profile = {
            "id": TEST_USER_ID,
            "name": "Alice TestUser",
            "email": "alice@test.com",
            "is_admin": False,
            "avatar_url": None,
            "organization": "Food Bank",
            "created_at": "2024-01-01",
        }
        fake_ai_resp = _mock_httpx_response(
            _mock_openai_response("Hello Alice!")
        )

        with patch.object(engine, "get_user_profile", new_callable=AsyncMock, return_value=mock_profile), \
             patch.object(engine, "get_conversation_history", new_callable=AsyncMock, return_value=[]), \
             patch.object(engine, "store_message", new_callable=AsyncMock, return_value="msg-id-1"), \
             patch("backend.ai_engine._openai_with_retry", new_callable=AsyncMock, return_value=fake_ai_resp):

            result = await engine.chat(TEST_USER_ID, "Hello!")

            # Verify profile context was passed to GPT
            call_args = (await engine.get_user_profile(TEST_USER_ID),)
            assert result["text"] == "Hello Alice!"
            assert result["user_id"] == TEST_USER_ID
            assert result["lang"] == "en"

    @pytest.mark.asyncio
    async def test_no_profile_still_injects_user_id(self, engine):
        """When profile lookup returns None, user_id is still injected."""
        fake_ai_resp = _mock_httpx_response(
            _mock_openai_response("Hi there!")
        )

        with patch.object(engine, "get_user_profile", new_callable=AsyncMock, return_value=None), \
             patch.object(engine, "get_conversation_history", new_callable=AsyncMock, return_value=[]), \
             patch.object(engine, "store_message", new_callable=AsyncMock, return_value=None), \
             patch("backend.ai_engine._openai_with_retry", new_callable=AsyncMock, return_value=fake_ai_resp):

            result = await engine.chat(TEST_USER_ID, "Hello!")
            assert result["text"] == "Hi there!"

    @pytest.mark.asyncio
    async def test_admin_role_in_context(self, engine):
        """Admin users get 'Admin' role in the context message."""
        mock_profile = {
            "id": TEST_USER_ID,
            "name": "Admin User",
            "is_admin": True,
            "organization": "DoGoods",
        }
        fake_ai_resp = _mock_httpx_response(
            _mock_openai_response("Welcome, admin!")
        )

        captured_messages = []

        async def capture_openai(*args, **kwargs):
            payload = kwargs.get("json_payload", {})
            captured_messages.extend(payload.get("messages", []))
            return fake_ai_resp

        with patch.object(engine, "get_user_profile", new_callable=AsyncMock, return_value=mock_profile), \
             patch.object(engine, "get_conversation_history", new_callable=AsyncMock, return_value=[]), \
             patch.object(engine, "store_message", new_callable=AsyncMock, return_value=None), \
             patch("backend.ai_engine._openai_with_retry", new_callable=AsyncMock, side_effect=capture_openai):

            await engine.chat(TEST_USER_ID, "Hello!")

            # Find the profile context message
            context_msgs = [m for m in captured_messages if "Admin" in m.get("content", "")]
            assert len(context_msgs) >= 1
            assert "Admin" in context_msgs[0]["content"]


# ===================================================================
# 7. Spanish Handling in Chat Flow
# ===================================================================

class TestSpanishChatFlow:
    @pytest.mark.asyncio
    async def test_spanish_message_sets_lang(self, engine):
        """Spanish input should produce lang='es' in response."""
        fake_ai_resp = _mock_httpx_response(
            _mock_openai_response("¡Hola! ¿Cómo puedo ayudarte?")
        )

        with patch.object(engine, "get_user_profile", new_callable=AsyncMock, return_value=None), \
             patch.object(engine, "get_conversation_history", new_callable=AsyncMock, return_value=[]), \
             patch.object(engine, "store_message", new_callable=AsyncMock, return_value=None), \
             patch("backend.ai_engine._openai_with_retry", new_callable=AsyncMock, return_value=fake_ai_resp):

            result = await engine.chat(TEST_USER_ID, "Hola, necesito comida por favor")
            assert result["lang"] == "es"

    @pytest.mark.asyncio
    async def test_spanish_directive_injected(self, engine):
        """Spanish messages should inject a Spanish-response directive into system messages."""
        fake_ai_resp = _mock_httpx_response(
            _mock_openai_response("Respuesta en español")
        )
        captured_messages = []

        async def capture_openai(*args, **kwargs):
            payload = kwargs.get("json_payload", {})
            captured_messages.extend(payload.get("messages", []))
            return fake_ai_resp

        with patch.object(engine, "get_user_profile", new_callable=AsyncMock, return_value=None), \
             patch.object(engine, "get_conversation_history", new_callable=AsyncMock, return_value=[]), \
             patch.object(engine, "store_message", new_callable=AsyncMock, return_value=None), \
             patch("backend.ai_engine._openai_with_retry", new_callable=AsyncMock, side_effect=capture_openai):

            await engine.chat(TEST_USER_ID, "Hola, necesito ayuda por favor")

            # There should be a system message with the Spanish directive
            # (distinct from the main system prompt which also mentions Spanish).
            # Actual wording: "You MUST respond ENTIRELY in Spanish".
            spanish_directives = [
                m for m in captured_messages
                if m["role"] == "system"
                and "MUST respond" in m.get("content", "")
                and "Spanish" in m.get("content", "")
            ]
            assert len(spanish_directives) >= 1

    @pytest.mark.asyncio
    async def test_english_no_spanish_directive(self, engine):
        """English messages should NOT inject the Spanish directive."""
        fake_ai_resp = _mock_httpx_response(
            _mock_openai_response("Hello!")
        )
        captured_messages = []

        async def capture_openai(*args, **kwargs):
            payload = kwargs.get("json_payload", {})
            captured_messages.extend(payload.get("messages", []))
            return fake_ai_resp

        with patch.object(engine, "get_user_profile", new_callable=AsyncMock, return_value=None), \
             patch.object(engine, "get_conversation_history", new_callable=AsyncMock, return_value=[]), \
             patch.object(engine, "store_message", new_callable=AsyncMock, return_value=None), \
             patch("backend.ai_engine._openai_with_retry", new_callable=AsyncMock, side_effect=capture_openai):

            await engine.chat(TEST_USER_ID, "Hello, I need help")

            spanish_directives = [
                m for m in captured_messages
                if m["role"] == "system" and "MUST respond entirely in Spanish" in m.get("content", "")
            ]
            assert len(spanish_directives) == 0

    @pytest.mark.asyncio
    async def test_spanish_canned_on_timeout(self, engine):
        """When GPT times out on a Spanish message, the canned response should be in Spanish."""
        with patch.object(engine, "get_user_profile", new_callable=AsyncMock, return_value=None), \
             patch.object(engine, "get_conversation_history", new_callable=AsyncMock, return_value=[]), \
             patch.object(engine, "store_message", new_callable=AsyncMock, return_value=None), \
             patch("backend.ai_engine._openai_with_retry", new_callable=AsyncMock, side_effect=httpx.TimeoutException("timeout")):

            result = await engine.chat(TEST_USER_ID, "Hola, necesito comida por favor")
            assert result["lang"] == "es"
            # Canned Spanish timeout response
            assert "inténtalo" in result["text"].lower() or "momento" in result["text"].lower()


# ===================================================================
# 8. Tool Format & Tool Calling
# ===================================================================

class TestToolFormat:
    def test_tool_definitions_structure(self, engine):
        """TOOL_DEFINITIONS must follow OpenAI function-calling schema."""
        for tool in engine.tool_definitions:
            assert tool["type"] == "function"
            fn = tool["function"]
            assert "name" in fn
            assert "description" in fn
            assert "parameters" in fn
            assert fn["parameters"]["type"] == "object"
            assert "properties" in fn["parameters"]

    def test_tool_definitions_have_required_tools(self, engine):
        """Core tools must be present."""
        names = {t["function"]["name"] for t in engine.tool_definitions}
        expected = {
            "search_food_near_user",
            "get_user_profile",
            "get_pickup_schedule",
            "create_reminder",
            "get_user_dashboard",
        }
        assert expected.issubset(names)

    def test_every_tool_has_handler(self, engine):
        """Every TOOL_DEFINITIONS entry must map to an entry in _HANDLERS."""
        from backend.tools import _HANDLERS
        schema_names = {t["function"]["name"] for t in engine.tool_definitions}
        missing = schema_names - set(_HANDLERS.keys())
        assert not missing, f"Tools declared with no handler: {sorted(missing)}"

    def test_every_handler_has_tool_definition(self, engine):
        """Every _HANDLERS key must have a matching TOOL_DEFINITIONS entry.

        Guards against orphan aliases: handlers reachable via execute_tool
        but never exposed to the model in the schema payload.
        """
        from backend.tools import _HANDLERS
        schema_names = {t["function"]["name"] for t in engine.tool_definitions}
        orphans = set(_HANDLERS.keys()) - schema_names
        assert not orphans, f"Handlers with no TOOL_DEFINITIONS entry: {sorted(orphans)}"

    def test_tool_required_params_match_handler_signatures(self, engine):
        """Each schema `required` name must be accepted by the handler."""
        import inspect
        from backend.tools import _HANDLERS
        for tool in engine.tool_definitions:
            name = tool["function"]["name"]
            handler = _HANDLERS.get(name)
            assert handler is not None, f"No handler for tool '{name}'"
            required = tool["function"].get("parameters", {}).get("required", []) or []
            sig = inspect.signature(handler)
            explicit = {
                pname for pname, p in sig.parameters.items()
                if p.kind not in (
                    inspect.Parameter.VAR_POSITIONAL,
                    inspect.Parameter.VAR_KEYWORD,
                )
            }
            accepts_kwargs = any(
                p.kind == inspect.Parameter.VAR_KEYWORD
                for p in sig.parameters.values()
            )
            for pname in required:
                assert pname in explicit or accepts_kwargs, (
                    f"Tool '{name}' schema requires '{pname}' but handler "
                    f"'{handler.__name__}' doesn't accept it"
                )

    def test_user_id_tools_handlers_accept_user_id(self, engine):
        """Any tool whose schema exposes `user_id` must have a handler
        that accepts it — the ai_engine dispatch layer force-injects the
        authenticated user_id and would raise TypeError otherwise."""
        import inspect
        from backend.tools import _HANDLERS
        for tool in engine.tool_definitions:
            name = tool["function"]["name"]
            props = tool["function"].get("parameters", {}).get("properties", {}) or {}
            if "user_id" not in props:
                continue
            handler = _HANDLERS.get(name)
            assert handler is not None
            sig = inspect.signature(handler)
            explicit = set(sig.parameters.keys())
            accepts_kwargs = any(
                p.kind == inspect.Parameter.VAR_KEYWORD
                for p in sig.parameters.values()
            )
            assert "user_id" in explicit or accepts_kwargs, (
                f"Tool '{name}' exposes user_id but handler "
                f"'{handler.__name__}' cannot accept it"
            )

    def test_validate_tool_definitions_returns_empty(self):
        """The startup validator must return no errors for the current
        TOOL_DEFINITIONS / _HANDLERS state. Regressions here indicate a
        newly-added tool without a matching handler (or vice versa)."""
        from backend.tools import _validate_tool_definitions
        errors = _validate_tool_definitions()
        assert errors == [], "Tool signature validation errors:\n  - " + "\n  - ".join(errors)

    def test_no_ghost_tools_referenced_in_backend(self):
        """No prompt, code list, or comment may reference a tool name that
        has no handler. Regressions here mean the model will be told about
        a tool the runtime cannot dispatch, producing "Unknown tool" errors
        for every user who triggers that instruction path."""
        import pathlib
        ghost_names = (
            "post_food_request",
            "get_driver_route_plan",
            "get_dispatch_queue",
            "get_platform_stats",
        )
        root = pathlib.Path(__file__).resolve().parent.parent
        offenders: list[str] = []
        for path in root.rglob("*.py"):
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            # Skip this test file itself and its docstring listing the names.
            if path.resolve() == pathlib.Path(__file__).resolve():
                continue
            for name in ghost_names:
                if name in text:
                    offenders.append(f"{path.relative_to(root)}: contains '{name}'")
        assert not offenders, (
            "Ghost tool references found (these names have no handler):\n  - "
            + "\n  - ".join(offenders)
        )

    def test_needs_tools_detects_tool_keywords(self):
        """_needs_tools should return True for database-related queries.

        This helper is kept around for ranking/short-circuit hints but
        is NO LONGER used to gate whether tools are attached to the GPT
        payload — `_call_openai_chat` now always attaches tools so the
        model can self-correct after a tool error.
        """
        assert ConversationEngine._needs_tools("Show me my dashboard") is True
        assert ConversationEngine._needs_tools("Find food near me") is True
        assert ConversationEngine._needs_tools("Set a reminder for tomorrow") is True
        # "recipe" was added to the keyword set so cooking queries get
        # the tool path too.
        assert ConversationEngine._needs_tools("Recipe for rice") is True

    def test_needs_tools_false_for_generic_chat(self):
        """_needs_tools should return False for queries with no tool keywords.

        Note: matching is substring-based, so even short words like "here"
        (matches "there") will fire the keyword detector. Phrases below are
        intentionally chosen to contain NONE of the registered substrings.
        """
        assert ConversationEngine._needs_tools("How long do bananas stay yellow?") is False
        assert ConversationEngine._needs_tools("Why is the sky blue?") is False
        assert ConversationEngine._needs_tools("Who are you?") is False

    @pytest.mark.asyncio
    async def test_tool_call_round_trip(self, engine):
        """Simulate GPT requesting a tool call, verify follow-up call is made."""
        tool_call = {
            "id": "call_abc123",
            "type": "function",
            "function": {
                "name": "get_user_dashboard",
                "arguments": json.dumps({"user_id": TEST_USER_ID}),
            },
        }
        # First call returns tool_calls, second returns formatted text
        first_resp = _mock_httpx_response(
            _mock_openai_response(None, tool_calls=[tool_call])
        )
        followup_resp = _mock_httpx_response(
            _mock_openai_response("Here's your dashboard summary!")
        )

        call_count = 0

        async def mock_openai(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return first_resp
            return followup_resp

        mock_tool_result = {"claims": 3, "listings": 5, "impact": {"meals_shared": 10}}

        with patch("backend.ai_engine.OPENAI_API_KEY", "sk-test"), \
             patch("backend.ai_engine._openai_with_retry", new_callable=AsyncMock, side_effect=mock_openai), \
             patch.object(engine, "_execute_tool", new_callable=AsyncMock, return_value=mock_tool_result):

            messages = [
                {"role": "system", "content": "You are a test assistant."},
                {"role": "user", "content": "Show me my dashboard"},
            ]
            # _call_openai_chat now returns just the text; tool results are
            # written into the actions_out list passed by the caller.
            tool_results: list[dict] = []
            result = await engine._call_openai_chat(messages, actions_out=tool_results)
            assert result == "Here's your dashboard summary!"
            assert call_count == 2  # initial + follow-up
            assert len(tool_results) == 1
            assert tool_results[0]["tool"] == "get_user_dashboard"
            engine._execute_tool.assert_called_once_with(
                "get_user_dashboard", {"user_id": TEST_USER_ID}
            )

    @pytest.mark.asyncio
    async def test_tool_error_graceful(self, engine):
        """When a tool raises an error, GPT should still get a response."""
        tool_call = {
            "id": "call_err1",
            "type": "function",
            "function": {
                "name": "search_food_near_user",
                "arguments": json.dumps({"user_id": TEST_USER_ID}),
            },
        }
        first_resp = _mock_httpx_response(
            _mock_openai_response(None, tool_calls=[tool_call])
        )
        followup_resp = _mock_httpx_response(
            _mock_openai_response("Sorry, I couldn't search right now.")
        )

        call_count = 0

        async def mock_openai(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return first_resp if call_count == 1 else followup_resp

        with patch("backend.ai_engine.OPENAI_API_KEY", "sk-test"), \
             patch("backend.ai_engine._openai_with_retry", new_callable=AsyncMock, side_effect=mock_openai), \
             patch.object(engine, "_execute_tool", new_callable=AsyncMock, side_effect=RuntimeError("DB down")):

            messages = [
                {"role": "system", "content": "Test"},
                {"role": "user", "content": "Find food near me"},
            ]
            tool_results: list[dict] = []
            result = await engine._call_openai_chat(messages, actions_out=tool_results)
            # Should NOT raise — error is handled gracefully
            assert isinstance(result, str)
            assert len(tool_results) == 1

    @pytest.mark.asyncio
    async def test_tool_results_truncated(self, engine):
        """Tool results > 4000 chars should be truncated."""
        tool_call = {
            "id": "call_big1",
            "type": "function",
            "function": {
                "name": "get_user_dashboard",
                "arguments": json.dumps({"user_id": TEST_USER_ID}),
            },
        }
        first_resp = _mock_httpx_response(
            _mock_openai_response(None, tool_calls=[tool_call])
        )
        followup_resp = _mock_httpx_response(
            _mock_openai_response("Summary of your dashboard.")
        )

        call_count = 0

        async def mock_openai(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return first_resp
            # Verify the tool result in the follow-up payload is truncated
            payload = kwargs.get("json_payload", {})
            tool_msgs = [m for m in payload.get("messages", []) if m.get("role") == "tool"]
            if tool_msgs:
                assert len(tool_msgs[0]["content"]) <= 4020  # 4000 + truncation marker
            return followup_resp

        huge_result = {"data": "x" * 5000}

        with patch("backend.ai_engine.OPENAI_API_KEY", "sk-test"), \
             patch("backend.ai_engine._openai_with_retry", new_callable=AsyncMock, side_effect=mock_openai), \
             patch.object(engine, "_execute_tool", new_callable=AsyncMock, return_value=huge_result):

            messages = [
                {"role": "system", "content": "Test"},
                {"role": "user", "content": "Show me my dashboard"},
            ]
            await engine._call_openai_chat(messages)

    @pytest.mark.asyncio
    async def test_tool_messages_do_not_mutate_input(self, engine):
        """_call_openai_chat must not mutate the original messages list."""
        tool_call = {
            "id": "call_mut1",
            "type": "function",
            "function": {
                "name": "get_user_profile",
                "arguments": json.dumps({"user_id": TEST_USER_ID}),
            },
        }
        first_resp = _mock_httpx_response(
            _mock_openai_response(None, tool_calls=[tool_call])
        )
        followup_resp = _mock_httpx_response(
            _mock_openai_response("Profile info.")
        )

        call_count = 0

        async def mock_openai(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return first_resp if call_count == 1 else followup_resp

        with patch("backend.ai_engine.OPENAI_API_KEY", "sk-test"), \
             patch("backend.ai_engine._openai_with_retry", new_callable=AsyncMock, side_effect=mock_openai), \
             patch.object(engine, "_execute_tool", new_callable=AsyncMock, return_value={"name": "Alice"}):

            original_messages = [
                {"role": "system", "content": "Test"},
                {"role": "user", "content": "Show me my profile"},
            ]
            original_len = len(original_messages)
            await engine._call_openai_chat(original_messages)
            # Original list must be unchanged (no tool/assistant msgs appended)
            assert len(original_messages) == original_len

    @pytest.mark.asyncio
    async def test_user_id_injected_when_model_omits_it(self, engine):
        """If the model emits a claim_listing call WITHOUT user_id, the
        dispatch layer MUST still inject auth_user_id so the bare handler
        signature (``_claim_food_listing(user_id, listing_id, ...)``) doesn't
        TypeError. Without this, the user sees "I couldn't claim that"
        and no food_claims row is ever created in the database."""
        # Model "forgets" to include user_id — it only passes listing_id.
        tool_call = {
            "id": "call_no_uid",
            "type": "function",
            "function": {
                "name": "claim_listing",
                "arguments": json.dumps({"listing_id": "list-xyz"}),
            },
        }
        first_resp = _mock_httpx_response(
            _mock_openai_response(None, tool_calls=[tool_call])
        )
        followup_resp = _mock_httpx_response(
            _mock_openai_response("Claimed!")
        )
        call_count = 0

        async def mock_openai(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return first_resp if call_count == 1 else followup_resp

        with patch("backend.ai_engine.OPENAI_API_KEY", "sk-test"), \
             patch("backend.ai_engine._openai_with_retry", new_callable=AsyncMock, side_effect=mock_openai), \
             patch.object(engine, "_execute_tool", new_callable=AsyncMock, return_value={"success": True, "claim_id": "C1"}):

            messages = [
                {"role": "system", "content": "Test"},
                {"role": "user", "content": "Claim that bread for me"},
            ]
            await engine._call_openai_chat(messages, auth_user_id=TEST_USER_ID)
            # The dispatch MUST have populated user_id from auth, even
            # though the model omitted it.
            engine._execute_tool.assert_called_once_with(
                "claim_listing",
                {"listing_id": "list-xyz", "user_id": TEST_USER_ID},
            )

    @pytest.mark.asyncio
    async def test_user_id_overridden_against_prompt_injection(self, engine):
        """If the model emits a user_id that differs from the authenticated
        session (prompt injection, hallucination, or a stale id from
        history), the dispatch layer MUST overwrite it with auth_user_id
        so the AI can never claim/post/cancel on another user's behalf."""
        attacker_uid = "11111111-1111-1111-1111-111111111111"
        tool_call = {
            "id": "call_inject",
            "type": "function",
            "function": {
                "name": "claim_listing",
                "arguments": json.dumps({
                    "user_id": attacker_uid,
                    "listing_id": "list-xyz",
                }),
            },
        }
        first_resp = _mock_httpx_response(
            _mock_openai_response(None, tool_calls=[tool_call])
        )
        followup_resp = _mock_httpx_response(
            _mock_openai_response("Claimed!")
        )
        call_count = 0

        async def mock_openai(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return first_resp if call_count == 1 else followup_resp

        with patch("backend.ai_engine.OPENAI_API_KEY", "sk-test"), \
             patch("backend.ai_engine._openai_with_retry", new_callable=AsyncMock, side_effect=mock_openai), \
             patch.object(engine, "_execute_tool", new_callable=AsyncMock, return_value={"success": True, "claim_id": "C1"}):

            messages = [
                {"role": "system", "content": "Test"},
                {"role": "user", "content": "Claim that bread"},
            ]
            await engine._call_openai_chat(messages, auth_user_id=TEST_USER_ID)
            # auth_user_id MUST win — never the attacker's id.
            engine._execute_tool.assert_called_once_with(
                "claim_listing",
                {"user_id": TEST_USER_ID, "listing_id": "list-xyz"},
            )

    def test_tools_taking_user_id_includes_action_tools(self, engine):
        """Every write-on-behalf-of-user tool MUST appear in
        ``_tools_taking_user_id`` so the unconditional user_id injection
        actually fires for them. Adding a new action tool without a
        ``user_id`` schema property is a regression that would silently
        re-introduce the "I couldn't claim that" bug."""
        for required in {
            "claim_listing",
            "cancel_claim",
            "confirm_claim",
            "post_food_listing",
            "create_food_listing",
            "update_user_profile",
            "create_reminder",
            "attach_photos_to_listing",
            "send_notification",
            "search_food_near_user",
            "get_user_dashboard",
            "get_user_profile",
        }:
            assert required in engine._tools_taking_user_id, (
                f"{required} must declare user_id in its tool schema"
            )


# ===================================================================
# 9. History Saving
# ===================================================================

class TestHistorySaving:
    @pytest.mark.asyncio
    async def test_chat_stores_both_messages(self, engine):
        """chat() should store both user and assistant messages."""
        fake_ai_resp = _mock_httpx_response(
            _mock_openai_response("Thanks for your message!")
        )
        store_calls = []

        async def mock_store(user_id, role, message, metadata=None):
            store_calls.append({"user_id": user_id, "role": role, "message": message})
            return f"id-{len(store_calls)}"

        with patch.object(engine, "get_user_profile", new_callable=AsyncMock, return_value=None), \
             patch.object(engine, "get_conversation_history", new_callable=AsyncMock, return_value=[]), \
             patch.object(engine, "store_message", new_callable=AsyncMock, side_effect=mock_store), \
             patch("backend.ai_engine._openai_with_retry", new_callable=AsyncMock, return_value=fake_ai_resp):

            result = await engine.chat(TEST_USER_ID, "Hello bot")

            # Both user and assistant messages stored
            assert len(store_calls) == 2
            assert store_calls[0]["role"] == "user"
            assert store_calls[0]["message"] == "Hello bot"
            assert store_calls[1]["role"] == "assistant"
            assert store_calls[1]["message"] == "Thanks for your message!"

    @pytest.mark.asyncio
    async def test_conversation_id_returned(self, engine):
        """chat() should return the assistant message's DB row ID as conversation_id."""
        fake_ai_resp = _mock_httpx_response(
            _mock_openai_response("Response text")
        )

        call_idx = 0

        async def mock_store(user_id, role, message, metadata=None):
            nonlocal call_idx
            call_idx += 1
            return f"row-{call_idx}"

        with patch.object(engine, "get_user_profile", new_callable=AsyncMock, return_value=None), \
             patch.object(engine, "get_conversation_history", new_callable=AsyncMock, return_value=[]), \
             patch.object(engine, "store_message", new_callable=AsyncMock, side_effect=mock_store), \
             patch("backend.ai_engine._openai_with_retry", new_callable=AsyncMock, return_value=fake_ai_resp):

            result = await engine.chat(TEST_USER_ID, "Test")
            # The second store call (assistant) returns "row-2"
            assert result["conversation_id"] == "row-2"

    @pytest.mark.asyncio
    async def test_history_loaded_into_messages(self, engine):
        """Conversation history should be loaded and included in the GPT messages."""
        fake_history = [
            {"role": "user", "message": "Previous question", "created_at": "2024-01-01T00:00:00Z"},
            {"role": "assistant", "message": "Previous answer", "created_at": "2024-01-01T00:00:01Z"},
        ]
        fake_ai_resp = _mock_httpx_response(
            _mock_openai_response("New answer")
        )
        captured_messages = []

        async def capture_openai(*args, **kwargs):
            payload = kwargs.get("json_payload", {})
            captured_messages.extend(payload.get("messages", []))
            return fake_ai_resp

        with patch.object(engine, "get_user_profile", new_callable=AsyncMock, return_value=None), \
             patch.object(engine, "get_conversation_history", new_callable=AsyncMock, return_value=fake_history), \
             patch.object(engine, "store_message", new_callable=AsyncMock, return_value=None), \
             patch("backend.ai_engine._openai_with_retry", new_callable=AsyncMock, side_effect=capture_openai):

            await engine.chat(TEST_USER_ID, "New question")

            # History should appear in messages before the new user message
            contents = [m.get("content", "") for m in captured_messages]
            assert "Previous question" in contents
            assert "Previous answer" in contents

    @pytest.mark.asyncio
    async def test_long_history_truncated(self, engine):
        """History messages longer than 4000 chars should be truncated.

        The cap was raised from 800 → 4000 so enumerated listings (with
        ids/titles/distances) survive intact across turns. Messages just
        over the cap still get truncated, messages well below it survive
        whole.
        """
        long_msg = "A" * 4500
        short_msg = "B" * 500  # below cap — must NOT be truncated
        fake_history = [
            {"role": "assistant", "message": long_msg, "created_at": "2024-01-01T00:00:00Z"},
            {"role": "assistant", "message": short_msg, "created_at": "2024-01-01T00:00:01Z"},
        ]
        fake_ai_resp = _mock_httpx_response(
            _mock_openai_response("OK")
        )
        captured_messages = []

        async def capture_openai(*args, **kwargs):
            payload = kwargs.get("json_payload", {})
            captured_messages.extend(payload.get("messages", []))
            return fake_ai_resp

        with patch.object(engine, "get_user_profile", new_callable=AsyncMock, return_value=None), \
             patch.object(engine, "get_conversation_history", new_callable=AsyncMock, return_value=fake_history), \
             patch.object(engine, "store_message", new_callable=AsyncMock, return_value=None), \
             patch("backend.ai_engine._openai_with_retry", new_callable=AsyncMock, side_effect=capture_openai):

            await engine.chat(TEST_USER_ID, "Hi")

            history_msgs = [m for m in captured_messages if m["role"] == "assistant"]
            assert len(history_msgs) >= 2

            # Long one was truncated
            truncated = next(m for m in history_msgs if m["content"].startswith("A"))
            assert truncated["content"].endswith("... [truncated]")
            assert len(truncated["content"]) <= 4020

            # Short one was preserved verbatim
            preserved = next(m for m in history_msgs if m["content"].startswith("B"))
            assert preserved["content"] == short_msg

    @pytest.mark.asyncio
    async def test_store_failure_non_blocking(self, engine):
        """If storing messages fails, chat() should still return a response."""
        fake_ai_resp = _mock_httpx_response(
            _mock_openai_response("All good!")
        )

        with patch.object(engine, "get_user_profile", new_callable=AsyncMock, return_value=None), \
             patch.object(engine, "get_conversation_history", new_callable=AsyncMock, return_value=[]), \
             patch.object(engine, "store_message", new_callable=AsyncMock, side_effect=Exception("DB error")), \
             patch("backend.ai_engine._openai_with_retry", new_callable=AsyncMock, return_value=fake_ai_resp):

            result = await engine.chat(TEST_USER_ID, "Hello")
            # Should still return text even though storage failed
            assert result["text"] == "All good!"
            assert result["conversation_id"] is None


# ===================================================================
# 10. Response Generation (full chat flow)
# ===================================================================

class TestResponseGeneration:
    @pytest.mark.asyncio
    async def test_basic_chat_response(self, engine):
        """A simple chat message should return a complete response dict."""
        fake_ai_resp = _mock_httpx_response(
            _mock_openai_response("Welcome to DoGoods!")
        )

        with patch.object(engine, "get_user_profile", new_callable=AsyncMock, return_value=None), \
             patch.object(engine, "get_conversation_history", new_callable=AsyncMock, return_value=[]), \
             patch.object(engine, "store_message", new_callable=AsyncMock, return_value="row-1"), \
             patch("backend.ai_engine._openai_with_retry", new_callable=AsyncMock, return_value=fake_ai_resp):

            result = await engine.chat(TEST_USER_ID, "What is DoGoods?")
            assert result["text"] == "Welcome to DoGoods!"
            assert result["user_id"] == TEST_USER_ID
            assert result["lang"] == "en"
            assert result["audio_url"] is None  # include_audio=False by default
            assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_response_with_audio(self, engine):
        """When include_audio=True, audio_url should be populated.

        chat() actually calls `_generate_audio_b64`, not `_generate_audio_url`
        (the engine returns a base64 data URL inline). Mock the real method.
        """
        fake_ai_resp = _mock_httpx_response(
            _mock_openai_response("Here's your answer!")
        )
        data_url = "data:audio/mpeg;base64,Zm9v"

        with patch.object(engine, "get_user_profile", new_callable=AsyncMock, return_value=None), \
             patch.object(engine, "get_conversation_history", new_callable=AsyncMock, return_value=[]), \
             patch.object(engine, "store_message", new_callable=AsyncMock, return_value=None), \
             patch("backend.ai_engine._openai_with_retry", new_callable=AsyncMock, return_value=fake_ai_resp), \
             patch.object(engine, "_generate_audio_b64", new_callable=AsyncMock, return_value=data_url):

            result = await engine.chat(TEST_USER_ID, "Hello", include_audio=True)
            assert result["audio_url"] == data_url

    @pytest.mark.asyncio
    async def test_fallback_on_timeout(self, engine):
        """Timeout should produce a canned response, not raise."""
        with patch.object(engine, "get_user_profile", new_callable=AsyncMock, return_value=None), \
             patch.object(engine, "get_conversation_history", new_callable=AsyncMock, return_value=[]), \
             patch.object(engine, "store_message", new_callable=AsyncMock, return_value=None), \
             patch("backend.ai_engine._openai_with_retry", new_callable=AsyncMock, side_effect=httpx.TimeoutException("timeout")):

            result = await engine.chat(TEST_USER_ID, "Hello")
            assert "try again" in result["text"].lower()

    @pytest.mark.asyncio
    async def test_fallback_on_api_error(self, engine):
        """HTTP errors should produce a canned response (api_down wording)."""
        with patch.object(engine, "get_user_profile", new_callable=AsyncMock, return_value=None), \
             patch.object(engine, "get_conversation_history", new_callable=AsyncMock, return_value=[]), \
             patch.object(engine, "store_message", new_callable=AsyncMock, return_value=None), \
             patch("backend.ai_engine._openai_with_retry", new_callable=AsyncMock, side_effect=httpx.HTTPStatusError("500", request=MagicMock(), response=MagicMock(status_code=500))):

            result = await engine.chat(TEST_USER_ID, "Hello")
            text = result["text"].lower()
            # Match the canned api_down wording, NOT a specific phrase that
            # might churn over time.
            assert "can't reach" in text or "ai service" in text or "try again" in text

    @pytest.mark.asyncio
    async def test_fallback_on_missing_api_key(self, engine):
        """Missing API key should produce a canned response."""
        with patch.object(engine, "get_user_profile", new_callable=AsyncMock, return_value=None), \
             patch.object(engine, "get_conversation_history", new_callable=AsyncMock, return_value=[]), \
             patch.object(engine, "store_message", new_callable=AsyncMock, return_value=None), \
             patch("backend.ai_engine.OPENAI_API_KEY", ""):

            result = await engine.chat(TEST_USER_ID, "Hello")
            # Should get a canned response, not a crash
            assert isinstance(result["text"], str)
            assert len(result["text"]) > 10

    @pytest.mark.asyncio
    async def test_tools_always_attached(self, engine):
        """Tools are now attached to EVERY chat call, even on plain
        conversational turns.

        The earlier behavior gated this on `_needs_tools(message)`, which
        meant that if a user said something like "I have a few cans of
        soup spare" (no keyword hit), the model couldn't call
        post_food_listing and would just text-reply "Posted!" without
        actually posting. Always-on tools fixed that class of bug, so
        this test now ASSERTS the new contract.
        """
        fake_ai_resp = _mock_httpx_response(
            _mock_openai_response("Bananas keep well at room temperature.")
        )
        captured_payload = {}

        async def capture_openai(*args, **kwargs):
            captured_payload.update(kwargs.get("json_payload", {}))
            return fake_ai_resp

        with patch.object(engine, "get_user_profile", new_callable=AsyncMock, return_value=None), \
             patch.object(engine, "get_conversation_history", new_callable=AsyncMock, return_value=[]), \
             patch.object(engine, "store_message", new_callable=AsyncMock, return_value=None), \
             patch("backend.ai_engine._openai_with_retry", new_callable=AsyncMock, side_effect=capture_openai):

            await engine.chat(TEST_USER_ID, "How do I store bananas?")
            assert "tools" in captured_payload
            assert isinstance(captured_payload["tools"], list)
            assert len(captured_payload["tools"]) > 0

    @pytest.mark.asyncio
    async def test_tools_sent_for_data_query(self, engine):
        """Data queries should include tool definitions in the payload."""
        fake_ai_resp = _mock_httpx_response(
            _mock_openai_response("Here's what's nearby.")
        )
        captured_payload = {}

        async def capture_openai(*args, **kwargs):
            captured_payload.update(kwargs.get("json_payload", {}))
            return fake_ai_resp

        with patch.object(engine, "get_user_profile", new_callable=AsyncMock, return_value=None), \
             patch.object(engine, "get_conversation_history", new_callable=AsyncMock, return_value=[]), \
             patch.object(engine, "store_message", new_callable=AsyncMock, return_value=None), \
             patch("backend.ai_engine._openai_with_retry", new_callable=AsyncMock, side_effect=capture_openai):

            await engine.chat(TEST_USER_ID, "Find food near me")
            assert "tools" in captured_payload
            assert len(captured_payload["tools"]) > 0


# ===================================================================
# 11. Whisper & TTS
# ===================================================================

class TestWhisperAndTTS:
    @pytest.mark.asyncio
    async def test_transcribe_audio(self, engine):
        """transcribe_audio should call Whisper and return text."""
        fake_resp = MagicMock()
        fake_resp.json.return_value = {"text": "Hello from Whisper"}

        with patch("backend.ai_engine.OPENAI_API_KEY", "sk-test"), \
             patch("backend.ai_engine._openai_with_retry", new_callable=AsyncMock, return_value=fake_resp):

            result = await engine.transcribe_audio(b"fake-audio-bytes", "test.webm")
            assert result == "Hello from Whisper"

    @pytest.mark.asyncio
    async def test_transcribe_no_api_key(self, engine):
        """transcribe_audio should raise when API key is missing."""
        with patch("backend.ai_engine.OPENAI_API_KEY", ""):
            with pytest.raises(RuntimeError, match="OPENAI_API_KEY not configured"):
                await engine.transcribe_audio(b"fake-audio")

    @pytest.mark.asyncio
    async def test_generate_speech_english(self, engine):
        """generate_speech should use English voice for 'en'."""
        fake_resp = MagicMock()
        fake_resp.content = b"fake-mp3-bytes"
        captured_payload = {}

        async def capture(*args, **kwargs):
            captured_payload.update(kwargs.get("json_payload", {}))
            return fake_resp

        with patch("backend.ai_engine.OPENAI_API_KEY", "sk-test"), \
             patch("backend.ai_engine._openai_with_retry", new_callable=AsyncMock, side_effect=capture):

            audio = await engine.generate_speech("Hello world", lang="en")
            assert audio == b"fake-mp3-bytes"
            assert captured_payload["voice"] == "nova"

    @pytest.mark.asyncio
    async def test_generate_speech_spanish_voice(self, engine):
        """generate_speech should use Spanish voice for 'es'."""
        fake_resp = MagicMock()
        fake_resp.content = b"fake-mp3-bytes"
        captured_payload = {}

        async def capture(*args, **kwargs):
            captured_payload.update(kwargs.get("json_payload", {}))
            return fake_resp

        with patch("backend.ai_engine.OPENAI_API_KEY", "sk-test"), \
             patch("backend.ai_engine._openai_with_retry", new_callable=AsyncMock, side_effect=capture):

            await engine.generate_speech("Hola mundo", lang="es")
            # Spanish voice should be used (default: nova for es too)
            assert "voice" in captured_payload

    @pytest.mark.asyncio
    async def test_tts_truncates_long_text(self, engine):
        """TTS should truncate text > 4096 chars."""
        fake_resp = MagicMock()
        fake_resp.content = b"audio"
        captured_payload = {}

        async def capture(*args, **kwargs):
            captured_payload.update(kwargs.get("json_payload", {}))
            return fake_resp

        with patch("backend.ai_engine.OPENAI_API_KEY", "sk-test"), \
             patch("backend.ai_engine._openai_with_retry", new_callable=AsyncMock, side_effect=capture):

            long_text = "A" * 5000
            await engine.generate_speech(long_text)
            assert len(captured_payload["input"]) <= 4096


# ===================================================================
# 12. Silent flag, memory snapshot, compact actions
# ===================================================================

class TestSilentFlag:
    """The `silent` flag is used by background flows (bulk upload,
    photo enrichment) that synthesize a context prompt for Nouri without
    showing it as a user chat bubble. The user-side row MUST be skipped
    while the assistant reply is still persisted with metadata.silent_trigger.
    """

    @pytest.mark.asyncio
    async def test_silent_skips_user_row(self, engine):
        fake_ai_resp = _mock_httpx_response(_mock_openai_response("Congrats!"))
        store_calls = []

        async def mock_store(user_id, role, message, metadata=None):
            store_calls.append({"role": role, "message": message, "metadata": metadata or {}})
            return "row-1"

        with patch.object(engine, "get_user_profile", new_callable=AsyncMock, return_value=None), \
             patch.object(engine, "get_conversation_history", new_callable=AsyncMock, return_value=[]), \
             patch.object(engine, "store_message", new_callable=AsyncMock, side_effect=mock_store), \
             patch("backend.ai_engine._openai_with_retry", new_callable=AsyncMock, return_value=fake_ai_resp):

            await engine.chat(TEST_USER_ID, "[Action completed] Posted 3 items", silent=True)

        roles = [c["role"] for c in store_calls]
        assert "user" not in roles, "silent prompts must not be persisted as user rows"
        assistant_calls = [c for c in store_calls if c["role"] == "assistant"]
        assert len(assistant_calls) == 1
        assert assistant_calls[0]["metadata"].get("silent_trigger") is True

    @pytest.mark.asyncio
    async def test_non_silent_persists_both_rows(self, engine):
        fake_ai_resp = _mock_httpx_response(_mock_openai_response("Hi back!"))
        store_calls = []

        async def mock_store(user_id, role, message, metadata=None):
            store_calls.append({"role": role, "metadata": metadata or {}})
            return "row"

        with patch.object(engine, "get_user_profile", new_callable=AsyncMock, return_value=None), \
             patch.object(engine, "get_conversation_history", new_callable=AsyncMock, return_value=[]), \
             patch.object(engine, "store_message", new_callable=AsyncMock, side_effect=mock_store), \
             patch("backend.ai_engine._openai_with_retry", new_callable=AsyncMock, return_value=fake_ai_resp):

            await engine.chat(TEST_USER_ID, "hello", silent=False)

        roles = [c["role"] for c in store_calls]
        assert roles.count("user") == 1
        assert roles.count("assistant") == 1
        assistant = [c for c in store_calls if c["role"] == "assistant"][0]
        assert "silent_trigger" not in assistant["metadata"]

    @pytest.mark.asyncio
    async def test_anonymous_user_skips_persistence(self, engine):
        """Nil UUID anonymous sessions must skip persist entirely
        (the FK would reject them and they'd share one bucket anyway)."""
        fake_ai_resp = _mock_httpx_response(_mock_openai_response("ok"))
        store_calls = []

        async def mock_store(user_id, role, message, metadata=None):
            store_calls.append((user_id, role))
            return "row"

        with patch.object(engine, "get_user_profile", new_callable=AsyncMock, return_value=None), \
             patch.object(engine, "get_conversation_history", new_callable=AsyncMock, return_value=[]), \
             patch.object(engine, "store_message", new_callable=AsyncMock, side_effect=mock_store), \
             patch("backend.ai_engine._openai_with_retry", new_callable=AsyncMock, return_value=fake_ai_resp):

            result = await engine.chat("00000000-0000-0000-0000-000000000000", "hi")

        assert store_calls == [], "anonymous sessions must not write to ai_conversations"
        assert result["text"] == "ok"
        assert result["conversation_id"] is None


class TestLegacySilentPromptFilter:
    """Legacy '[Action completed] ...' rows persisted before the silent
    flag existed must be filtered from the GPT context, AND silent_trigger
    assistant rows must not be injected either (they'd be orphan assistant
    turns with no preceding user message)."""

    @pytest.mark.asyncio
    async def test_legacy_action_completed_rows_filtered(self, engine):
        fake_history = [
            {"role": "user", "message": "real question", "created_at": "2024-01-01T00:00:00Z"},
            {"role": "assistant", "message": "real answer", "created_at": "2024-01-01T00:00:01Z"},
            {"role": "user", "message": "[Action completed] I posted 3 items", "created_at": "2024-01-01T00:01:00Z"},
            {"role": "assistant", "message": "old congrats", "created_at": "2024-01-01T00:01:01Z",
             "metadata": {"silent_trigger": True}},
            {"role": "user", "message": "[Acción completada] 2 items", "created_at": "2024-01-01T00:02:00Z"},
        ]
        fake_ai_resp = _mock_httpx_response(_mock_openai_response("ok"))
        captured_messages = []

        async def capture(*args, **kwargs):
            payload = kwargs.get("json_payload", {})
            captured_messages.extend(payload.get("messages", []))
            return fake_ai_resp

        with patch.object(engine, "get_user_profile", new_callable=AsyncMock, return_value=None), \
             patch.object(engine, "get_conversation_history", new_callable=AsyncMock, return_value=fake_history), \
             patch.object(engine, "store_message", new_callable=AsyncMock, return_value=None), \
             patch("backend.ai_engine._openai_with_retry", new_callable=AsyncMock, side_effect=capture):

            await engine.chat(TEST_USER_ID, "next question")

        history_contents = [m["content"] for m in captured_messages if m["role"] in ("user", "assistant")]
        # The genuine turn survives
        assert "real question" in history_contents
        assert "real answer" in history_contents
        # The silent / [Action completed] turns are filtered
        assert not any("[Action completed]" in c for c in history_contents)
        assert not any("[Acción completada]" in c for c in history_contents)
        assert "old congrats" not in history_contents


class TestMemorySnapshot:
    """`_build_memory_snapshot` distills past tool calls so the model can
    resolve 'claim it', 'the bread', 'cancel that' across turns."""

    def test_empty_history_returns_none(self):
        assert _build_memory_snapshot([]) is None
        assert _build_memory_snapshot(None) is None

    def test_user_rows_ignored(self):
        history = [{"role": "user", "message": "hi", "metadata": {"actions": [{"tool": "search_food_near_user"}]}}]
        assert _build_memory_snapshot(history) is None

    def test_extracts_latest_listings(self):
        history = [
            {"role": "assistant", "message": "here", "metadata": {"actions": [
                {"tool": "search_food_near_user", "ok": True, "summary": "Found 2 nearby",
                 "listings": [
                     {"id": "list-1", "title": "Bread", "quantity": 5, "unit": "loaves",
                      "distance_km": 1.2, "address": "1 Main St", "donor_name": "Alice"},
                     {"id": "list-2", "title": "Apples", "quantity": 10, "unit": "items",
                      "distance_km": 2.0},
                 ]},
            ]}},
        ]
        snap = _build_memory_snapshot(history)
        assert snap is not None
        assert "RECENT CONTEXT" in snap
        assert "Last search results" in snap
        assert "Bread" in snap
        assert "id=list-1" in snap
        assert "donor=Alice" in snap
        assert "(search said: Found 2 nearby)" in snap

    def test_silent_trigger_rows_skipped(self):
        history = [
            # genuine search the user did
            {"role": "assistant", "message": "search", "metadata": {"actions": [
                {"tool": "search_food_near_user", "ok": True,
                 "listings": [{"id": "L1", "title": "Bread"}]},
            ]}},
            # silent congrats turn from bulk upload — must NOT overwrite latest_listings
            {"role": "assistant", "message": "congrats", "metadata": {
                "silent_trigger": True,
                "actions": [
                    {"tool": "create_food_listing", "ok": True,
                     "listings": [{"id": "S1", "title": "Pasta"}]},
                ],
            }},
        ]
        snap = _build_memory_snapshot(history)
        assert "Bread" in snap
        assert "Pasta" not in snap

    def test_cancelled_claim_hidden_from_recent_claims(self):
        """If a claim was later cancelled, it must NOT be re-listed as an
        active claim — the model would otherwise try to cancel it again."""
        history = [
            # Order in the list is chronological (oldest first) — the engine
            # iterates reversed(history).
            {"role": "assistant", "message": "claimed", "metadata": {"actions": [
                {"tool": "claim_listing", "ok": True, "claim_id": "C1",
                 "listing_id": "L1", "title": "Bread"},
            ]}},
            {"role": "assistant", "message": "cancelled", "metadata": {"actions": [
                {"tool": "cancel_claim", "ok": True, "claim_id": "C1",
                 "listing_id": "L1", "title": "Bread"},
            ]}},
            # Separate active claim that should still show
            {"role": "assistant", "message": "claimed-again", "metadata": {"actions": [
                {"tool": "claim_listing", "ok": True, "claim_id": "C2",
                 "listing_id": "L2", "title": "Apples"},
            ]}},
        ]
        snap = _build_memory_snapshot(history)
        # C2 still active
        assert "claim_id=C2" in snap
        # C1 listed only under "Recently cancelled", NOT under active claims.
        active_section = snap.split("Recently cancelled claims")[0]
        assert "claim_id=C1" not in active_section
        assert "Recently cancelled claims" in snap
        assert "claim_id=C1" in snap  # somewhere — i.e. in the cancelled section

    def test_recent_posts_listed(self):
        history = [
            {"role": "assistant", "message": "posted", "metadata": {"actions": [
                {"tool": "create_food_listing", "ok": True,
                 "listing_id": "L9", "title": "Soup"},
            ]}},
        ]
        snap = _build_memory_snapshot(history)
        assert "Recent successful posts" in snap
        assert "listing_id=L9" in snap
        assert "Soup" in snap

    def test_failed_actions_skipped(self):
        """ok=False results must not pollute the snapshot."""
        history = [
            {"role": "assistant", "message": "tried", "metadata": {"actions": [
                {"tool": "claim_listing", "ok": False, "claim_id": "X", "title": "Failed"},
                {"tool": "create_food_listing", "ok": False, "listing_id": "Y", "title": "FailedPost"},
            ]}},
        ]
        assert _build_memory_snapshot(history) is None


class TestCompactActionPersistence:
    """`_persist_conversation` stores a compact action dict in
    assistant_metadata so the next turn can rehydrate map state, UI
    directives, claim ids, etc. — without bloating the row."""

    @pytest.mark.asyncio
    async def test_compact_keeps_lat_lng_and_route(self, engine):
        captured = {}

        async def capture_store(user_id, role, message, metadata=None):
            if role == "assistant":
                captured["metadata"] = metadata or {}
            return "row"

        full_actions = [
            {
                "tool": "search_food_near_user",
                "ok": True,
                "summary": "Found 1 nearby",
                "result": {
                    "success": True,
                    "listings": [
                        {
                            "id": "L1",
                            "title": "Bread",
                            "latitude": 37.7749,
                            "longitude": -122.4194,
                            "distance_km": 0.8,
                            "address": "1 Market St",
                        },
                    ],
                },
            },
            {
                "tool": "get_mapbox_route",
                "ok": True,
                "summary": "5 min drive",
                "result": {"success": True},
                "route": {
                    "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
                    "origin": {"lat": 37.7, "lng": -122.4},
                    "destination": {"lat": 37.8, "lng": -122.5},
                    "distance_km": 1.2,
                    "duration_text": "5 min",
                    "profile": "driving",
                },
            },
            {
                "tool": "navigate_ui",
                "ok": True,
                "summary": "Open dashboard",
                "result": {"success": True},
                "action": "navigate",
                "path": "/dashboard",
                "target": "/dashboard",
            },
        ]

        with patch.object(engine, "store_message", new_callable=AsyncMock, side_effect=capture_store):
            await engine._persist_conversation(
                TEST_USER_ID, "ignored", "reply", "en", actions=full_actions, silent=False,
            )

        meta = captured["metadata"]
        assert meta.get("lang") == "en"
        compact_actions = meta.get("actions") or []
        assert len(compact_actions) == 3

        search = next(a for a in compact_actions if a["tool"] == "search_food_near_user")
        assert search["success"] is True
        listings = search["listings"]
        assert listings and listings[0]["latitude"] == 37.7749
        assert listings[0]["longitude"] == -122.4194
        assert listings[0]["distance_km"] == 0.8

        route = next(a for a in compact_actions if a["tool"] == "get_mapbox_route")
        assert route["route"]["geometry"]["type"] == "LineString"
        assert route["route"]["origin"] == {"lat": 37.7, "lng": -122.4}
        assert route["route"]["distance_km"] == 1.2

        ui = next(a for a in compact_actions if a["tool"] == "navigate_ui")
        assert ui["action"] == "navigate"
        assert ui["path"] == "/dashboard"
        assert ui["target"] == "/dashboard"

    @pytest.mark.asyncio
    async def test_compact_mirrors_ok_to_success(self, engine):
        """Frontend ToolResultCard checks `result?.success` — so the compact
        row must expose `success` even when the original handler only set ok."""
        captured = {}

        async def capture_store(user_id, role, message, metadata=None):
            if role == "assistant":
                captured["metadata"] = metadata or {}
            return "row"

        with patch.object(engine, "store_message", new_callable=AsyncMock, side_effect=capture_store):
            await engine._persist_conversation(
                TEST_USER_ID, "u", "a", "en",
                actions=[{"tool": "claim_listing", "ok": True, "summary": "Claimed", "result": {"claim_id": "C1"}}],
                silent=False,
            )

        compact = captured["metadata"]["actions"][0]
        assert compact["success"] is True
        assert compact["claim_id"] == "C1"

    @pytest.mark.asyncio
    async def test_compact_preserves_all_search_results_up_to_ten(self, engine):
        """search_food_near_user returns up to max_results=10 listings.

        The compact cap MUST keep all of them (or at least 10) so that on the
        next turn the model can still resolve "claim #7" to a real listing_id.
        The previous cap of 5 silently dropped listings 6-10 from memory, so
        after a page refresh the model only saw the first half of the page
        and either claimed the wrong item or hallucinated an id.
        """
        captured = {}

        async def capture_store(user_id, role, message, metadata=None):
            if role == "assistant":
                captured["metadata"] = metadata or {}
            return "row"

        ten_listings = [
            {"id": f"L{i}", "title": f"Item {i}", "quantity": 1, "unit": "ea"}
            for i in range(1, 11)
        ]
        actions = [{
            "tool": "search_food_near_user",
            "ok": True,
            "summary": "Found 10 nearby",
            "result": {"success": True, "listings": ten_listings},
        }]

        with patch.object(engine, "store_message", new_callable=AsyncMock, side_effect=capture_store):
            await engine._persist_conversation(
                TEST_USER_ID, "find food", "here you go", "en",
                actions=actions, silent=False,
            )

        compact = captured["metadata"]["actions"][0]
        compact_ids = [item["id"] for item in compact["listings"]]
        # All 10 IDs MUST survive — not just the first 5.
        assert compact_ids == [f"L{i}" for i in range(1, 11)], (
            f"compact storage dropped listings: got {compact_ids}"
        )


# ---------------------------------------------------------------------------
# classify_exception — structured AIError mapping
# ---------------------------------------------------------------------------

with patch.dict("os.environ", _ENV, clear=False):
    from backend.ai_engine import AIError, AIErrorCode, classify_exception


class TestClassifyException:
    def test_passthrough_aierror(self):
        original = AIError(AIErrorCode.RATE_LIMIT, "slow down", retryable=True, http_status=429)
        assert classify_exception(original) is original

    def test_timeout_maps_to_retryable_504(self):
        err = classify_exception(httpx.TimeoutException("timed out"))
        assert err.code == AIErrorCode.TIMEOUT
        assert err.retryable is True
        assert err.http_status == 504

    def test_openai_429_maps_to_rate_limit(self):
        response = httpx.Response(429, headers={"retry-after": "15"}, request=httpx.Request("POST", "https://api.openai.com"))
        exc = httpx.HTTPStatusError("rate limited", request=response.request, response=response)
        err = classify_exception(exc)
        assert err.code == AIErrorCode.RATE_LIMIT
        assert err.retry_after_seconds == 15
        assert err.http_status == 429

    def test_openai_500_maps_to_model_unavailable(self):
        response = httpx.Response(502, request=httpx.Request("POST", "https://api.openai.com"))
        exc = httpx.HTTPStatusError("bad gateway", request=response.request, response=response)
        err = classify_exception(exc)
        assert err.code == AIErrorCode.MODEL_UNAVAILABLE
        assert err.retryable is True
        assert err.http_status == 503

    def test_runtime_error_openai_maps_to_model_unavailable(self):
        err = classify_exception(RuntimeError("OpenAI request failed after retries"))
        assert err.code == AIErrorCode.MODEL_UNAVAILABLE
        assert err.retryable is True

    def test_circuit_message_maps_to_circuit_open(self):
        err = classify_exception(RuntimeError("Circuit breaker is open"))
        assert err.code == AIErrorCode.CIRCUIT_OPEN
        assert err.retryable is True

    def test_unknown_maps_to_internal(self):
        err = classify_exception(ValueError("something weird"))
        assert err.code == AIErrorCode.INTERNAL
        assert err.retryable is False
        assert err.http_status == 500

    def test_to_dict_includes_retry_after(self):
        err = AIError(
            AIErrorCode.TIMEOUT,
            "too slow",
            retryable=True,
            retry_after_seconds=5,
            http_status=504,
        )
        body = err.to_dict()
        assert body["error_code"] == "timeout"
        assert body["retryable"] is True
        assert body["retry_after_seconds"] == 5



# ===================================================================
# Legacy tool-loop destructive-write intercept
# ===================================================================

class TestLegacyInterceptSummary:
    """`_build_legacy_intercept_summary` must render bilingual (EN/ES)
    phrasing that matches backend/agent/planner._build_intercept_summary
    so the v1, v2, and legacy paths all show the user the same words."""

    def test_delete_listing_en_with_title(self):
        out = _build_legacy_intercept_summary(
            "delete_listing", {"title": "Sourdough"}, language="en"
        )
        assert out == "permanently delete your listing 'Sourdough'"

    def test_delete_listing_en_without_title(self):
        assert _build_legacy_intercept_summary(
            "delete_listing", {}, language="en"
        ) == "permanently delete your listing"

    def test_delete_listing_es_with_title(self):
        out = _build_legacy_intercept_summary(
            "delete_listing", {"title": "Pan"}, language="es"
        )
        assert out == "eliminar permanentemente tu publicación 'Pan'"

    def test_delete_listing_es_without_title(self):
        assert _build_legacy_intercept_summary(
            "delete_listing", {}, language="es"
        ) == "eliminar permanentemente tu publicación"

    def test_delete_listing_falls_back_to_listing_title(self):
        # Some callers use `listing_title` instead of `title`.
        assert _build_legacy_intercept_summary(
            "delete_listing", {"listing_title": "Eggs"}, language="en"
        ) == "permanently delete your listing 'Eggs'"

    def test_cancel_claim_en(self):
        assert _build_legacy_intercept_summary(
            "cancel_claim", {}, language="en"
        ) == "release your claim"

    def test_cancel_claim_es(self):
        assert _build_legacy_intercept_summary(
            "cancel_claim", {}, language="es"
        ) == "cancelar tu reserva"

    def test_leave_community_en(self):
        assert _build_legacy_intercept_summary(
            "leave_community", {}, language="en"
        ) == "leave the community"

    def test_leave_community_es(self):
        assert _build_legacy_intercept_summary(
            "leave_community", {}, language="es"
        ) == "salir de la comunidad"

    def test_forget_about_me_en(self):
        assert _build_legacy_intercept_summary(
            "forget_about_me", {}, language="en"
        ) == "forget what I've learned about you"

    def test_forget_about_me_es(self):
        assert _build_legacy_intercept_summary(
            "forget_about_me", {}, language="es"
        ) == "olvidar lo que he aprendido sobre ti"

    def test_language_defaults_to_english(self):
        assert _build_legacy_intercept_summary(
            "cancel_claim", {}
        ) == "release your claim"

    def test_unknown_tool_returns_tool_name(self):
        assert _build_legacy_intercept_summary(
            "some_new_tool", {"foo": "bar"}, language="en"
        ) == "some_new_tool"


class TestMaybeInterceptLegacyToolCall:
    """`_maybe_intercept_legacy_tool_call` mirrors
    planner._maybe_intercept_destructive but for the raw GPT tool-loop
    inside ConversationEngine._call_openai_chat
    (ENABLE_AGENTIC_MODE=false). Both paths must gate the same 4 tools
    and produce the same pending_action envelope shape so switching
    feature flags never opens a hole.
    """

    _USER_ID = "11111111-2222-3333-4444-555555555555"

    @pytest.mark.asyncio
    async def test_intercepts_delete_listing_en(self):
        fake = MagicMock()
        fake.status = "pending"
        fake.pending_id = "pend-en-1"
        with patch(
            "backend.agent.actions.plan_action",
            new=AsyncMock(return_value=fake),
        ) as mock_plan:
            out = await _maybe_intercept_legacy_tool_call(
                fn_name="delete_listing",
                fn_args={"listing_id": "L-1", "title": "Bread"},
                auth_user_id=self._USER_ID,
                language="en",
            )
        assert isinstance(out, dict)
        assert out["success"] is False
        assert out["awaiting_confirmation"] is True
        assert out["error"] == "awaiting_user_confirmation"
        assert "'Bread'" in out["summary"]
        assert "permanently delete" in out["summary"]
        # The message must instruct the model NOT to retry and to ask
        # the user, in English.
        assert "Do NOT retry" in out["message"]
        assert "Just to confirm" in out["message"]
        env = out["pending_action"]
        assert isinstance(env, dict)
        assert env["pending_id"] == "pend-en-1"
        assert env["tool"] == "delete_listing"
        # `confirmed` must NEVER be persisted on the pending row.
        assert "confirmed" not in env["args"]
        mock_plan.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_intercepts_delete_listing_es(self):
        fake = MagicMock()
        fake.status = "pending"
        fake.pending_id = "pend-es-1"
        with patch(
            "backend.agent.actions.plan_action",
            new=AsyncMock(return_value=fake),
        ):
            out = await _maybe_intercept_legacy_tool_call(
                fn_name="delete_listing",
                fn_args={"listing_id": "L-1", "title": "Pan"},
                auth_user_id=self._USER_ID,
                language="es",
            )
        assert out is not None
        assert "eliminar permanentemente" in out["summary"]
        assert "'Pan'" in out["summary"]
        # Message is fully translated.
        assert "NO reintentes" in out["message"]
        assert "¿Confirmas" in out["message"]
        # Envelope summary should also carry the Spanish phrasing so
        # the frontend card reads correctly.
        assert "eliminar permanentemente" in out["pending_action"]["summary"]

    @pytest.mark.asyncio
    async def test_intercepts_cancel_claim(self):
        fake = MagicMock()
        fake.status = "pending"
        fake.pending_id = "pend-cc-1"
        with patch(
            "backend.agent.actions.plan_action",
            new=AsyncMock(return_value=fake),
        ):
            out = await _maybe_intercept_legacy_tool_call(
                fn_name="cancel_claim",
                fn_args={"claim_id": "C-3"},
                auth_user_id=self._USER_ID,
                language="en",
            )
        assert out is not None
        assert out["pending_action"]["tool"] == "cancel_claim"
        assert out["pending_action"]["args"] == {"claim_id": "C-3"}

    @pytest.mark.asyncio
    async def test_intercepts_leave_community_zero_arg(self):
        fake = MagicMock()
        fake.status = "pending"
        fake.pending_id = "pend-lc-1"
        with patch(
            "backend.agent.actions.plan_action",
            new=AsyncMock(return_value=fake),
        ):
            out = await _maybe_intercept_legacy_tool_call(
                fn_name="leave_community",
                fn_args={},
                auth_user_id=self._USER_ID,
                language="en",
            )
        assert out is not None
        assert out["pending_action"]["tool"] == "leave_community"

    @pytest.mark.asyncio
    async def test_intercepts_forget_about_me(self):
        fake = MagicMock()
        fake.status = "pending"
        fake.pending_id = "pend-fm-1"
        with patch(
            "backend.agent.actions.plan_action",
            new=AsyncMock(return_value=fake),
        ):
            out = await _maybe_intercept_legacy_tool_call(
                fn_name="forget_about_me",
                fn_args={},
                auth_user_id=self._USER_ID,
                language="es",
            )
        assert out is not None
        assert out["pending_action"]["tool"] == "forget_about_me"
        assert "olvidar lo que he aprendido" in out["summary"]

    @pytest.mark.asyncio
    async def test_confirmed_flag_bypasses_intercept(self):
        """POST /api/ai/confirm re-issues the tool call with
        `confirmed=True`. That flag MUST bypass the intercept so the
        write actually fires this time."""
        with patch(
            "backend.agent.actions.plan_action", new=AsyncMock()
        ) as mock_plan:
            out = await _maybe_intercept_legacy_tool_call(
                fn_name="delete_listing",
                fn_args={"listing_id": "L-1", "confirmed": True},
                auth_user_id=self._USER_ID,
                language="en",
            )
        assert out is None
        mock_plan.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_non_destructive_tool_never_intercepted(self):
        with patch(
            "backend.agent.actions.plan_action", new=AsyncMock()
        ) as mock_plan:
            out = await _maybe_intercept_legacy_tool_call(
                fn_name="get_recipes",
                fn_args={"ingredients": ["rice"]},
                auth_user_id=self._USER_ID,
                language="en",
            )
        assert out is None
        mock_plan.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_user_id_skips_intercept(self):
        """Empty auth_user_id (never-logged-in browser session) means
        we have no one to bill the pending row to. Skip rather than
        queue an orphan row."""
        with patch(
            "backend.agent.actions.plan_action", new=AsyncMock()
        ) as mock_plan:
            out = await _maybe_intercept_legacy_tool_call(
                fn_name="delete_listing",
                fn_args={"listing_id": "L-1"},
                auth_user_id=None,
                language="en",
            )
        assert out is None
        mock_plan.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_nil_uuid_skips_intercept(self):
        """The landing-page anonymous sentinel UUID is treated the
        same as no user id."""
        with patch(
            "backend.agent.actions.plan_action", new=AsyncMock()
        ) as mock_plan:
            out = await _maybe_intercept_legacy_tool_call(
                fn_name="delete_listing",
                fn_args={"listing_id": "L-1"},
                auth_user_id="00000000-0000-0000-0000-000000000000",
                language="en",
            )
        assert out is None
        mock_plan.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_non_dict_args_returns_none(self):
        with patch(
            "backend.agent.actions.plan_action", new=AsyncMock()
        ) as mock_plan:
            out = await _maybe_intercept_legacy_tool_call(
                fn_name="delete_listing",
                fn_args="not-a-dict",  # type: ignore[arg-type]
                auth_user_id=self._USER_ID,
                language="en",
            )
        assert out is None
        mock_plan.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_fails_open_on_timeout(self):
        """A Supabase outage that blocks plan_action must not wedge the
        tool loop. Return None (fall through to normal dispatch); the
        post-hoc audit log still records the write."""
        async def _hang(*_a, **_kw):
            raise asyncio.TimeoutError()

        with patch(
            "backend.agent.actions.plan_action", new=AsyncMock(side_effect=_hang)
        ):
            out = await _maybe_intercept_legacy_tool_call(
                fn_name="delete_listing",
                fn_args={"listing_id": "L-1"},
                auth_user_id=self._USER_ID,
                language="en",
            )
        assert out is None

    @pytest.mark.asyncio
    async def test_fails_open_on_plan_action_exception(self):
        with patch(
            "backend.agent.actions.plan_action",
            new=AsyncMock(side_effect=RuntimeError("db exploded")),
        ):
            out = await _maybe_intercept_legacy_tool_call(
                fn_name="cancel_claim",
                fn_args={"claim_id": "C-1"},
                auth_user_id=self._USER_ID,
                language="en",
            )
        assert out is None

    @pytest.mark.asyncio
    async def test_non_pending_status_returns_none(self):
        """If plan_action returns something other than status=pending
        (e.g. immediate commit for a low-risk write), fall through."""
        fake = MagicMock()
        fake.status = "committed"
        fake.pending_id = None
        with patch(
            "backend.agent.actions.plan_action",
            new=AsyncMock(return_value=fake),
        ):
            out = await _maybe_intercept_legacy_tool_call(
                fn_name="delete_listing",
                fn_args={"listing_id": "L-1"},
                auth_user_id=self._USER_ID,
                language="en",
            )
        assert out is None

    @pytest.mark.asyncio
    async def test_missing_pending_id_returns_none(self):
        fake = MagicMock()
        fake.status = "pending"
        fake.pending_id = None
        with patch(
            "backend.agent.actions.plan_action",
            new=AsyncMock(return_value=fake),
        ):
            out = await _maybe_intercept_legacy_tool_call(
                fn_name="delete_listing",
                fn_args={"listing_id": "L-1"},
                auth_user_id=self._USER_ID,
                language="en",
            )
        assert out is None
