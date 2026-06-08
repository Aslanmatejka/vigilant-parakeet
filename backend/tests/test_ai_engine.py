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
        _build_memory_snapshot,
        _build_system_prompt,
        _chip_language,
        _load_training_data,
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
