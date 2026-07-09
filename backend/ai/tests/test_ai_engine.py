"""Pure-logic tests for backend.ai.ai_engine — no DB, no network."""
from __future__ import annotations

import time
import pytest

from backend.ai import ai_engine
from backend.ai.ai_engine import (
    CircuitBreaker,
    CircuitState,
    check_rate_limit,
    detect_spanish,
    get_canned_response,
)


# ---------------------------------------------------------------------------
# detect_spanish
# ---------------------------------------------------------------------------

class TestDetectSpanish:
    @pytest.mark.parametrize("text", [
        "¿Qué comida está disponible cerca de mí?",
        "Necesito ayuda con mi panel",
        "Hola, quiero compartir alimentos",
        "¡Buenos días! ¿Cómo estás?",
        "Muéstrame mi perfil por favor",
    ])
    def test_spanish_detected(self, text: str):
        assert detect_spanish(text) is True

    @pytest.mark.parametrize("text", [
        "Show me my dashboard",
        "Find urgent food near me",
        "What recipes can I make with apples and oats?",
        "Hello, I need help claiming a listing",
        "",
    ])
    def test_english_not_flagged(self, text: str):
        assert detect_spanish(text) is False

    def test_accented_chars_alone_trigger_es(self):
        # Two or more accented chars → Spanish even without marker words
        assert detect_spanish("árbol está bién") is True

    def test_single_tilde_punct_triggers_es(self):
        assert detect_spanish("mañana") is True


# ---------------------------------------------------------------------------
# get_canned_response
# ---------------------------------------------------------------------------

class TestCannedResponse:
    def test_english_timeout(self):
        msg = get_canned_response("timeout", "en")
        assert "try again" in msg.lower()

    def test_spanish_timeout(self):
        msg = get_canned_response("timeout", "es")
        assert "inténtalo" in msg.lower() or "tardando" in msg.lower()

    def test_unknown_error_falls_back_to_general(self):
        msg_en = get_canned_response("does_not_exist", "en")
        msg_es = get_canned_response("does_not_exist", "es")
        assert msg_en == ai_engine.CANNED_RESPONSES["en"]["general_error"]
        assert msg_es == ai_engine.CANNED_RESPONSES["es"]["general_error"]

    def test_unknown_lang_defaults_to_english(self):
        msg = get_canned_response("timeout", "fr")
        assert msg == ai_engine.CANNED_RESPONSES["en"]["timeout"]


# ---------------------------------------------------------------------------
# check_rate_limit
# ---------------------------------------------------------------------------

class TestRateLimit:
    def test_allows_within_limit(self):
        ip = "1.1.1.1"
        for _ in range(3):
            assert check_rate_limit(ip, limit=5) is True

    def test_blocks_over_limit(self):
        ip = "2.2.2.2"
        for _ in range(5):
            assert check_rate_limit(ip, limit=5) is True
        # 6th should be blocked
        assert check_rate_limit(ip, limit=5) is False

    def test_different_ips_isolated(self):
        for _ in range(5):
            check_rate_limit("a", limit=5)
        # "a" blocked, "b" should be clean
        assert check_rate_limit("a", limit=5) is False
        assert check_rate_limit("b", limit=5) is True


# ---------------------------------------------------------------------------
# CircuitBreaker
# ---------------------------------------------------------------------------

class TestCircuitBreaker:
    def test_starts_closed_and_allows(self):
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert cb.allow_request() is True

    def test_opens_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3, reset_timeout=60.0)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.allow_request() is False

    def test_success_resets_state(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.failure_count == 0
        assert cb.state == CircuitState.CLOSED

    def test_transitions_to_half_open_after_timeout(self):
        cb = CircuitBreaker(failure_threshold=2, reset_timeout=0.01)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        time.sleep(0.02)
        assert cb.allow_request() is True
        assert cb.state == CircuitState.HALF_OPEN


# ---------------------------------------------------------------------------
# _role_behavior_prompt
# ---------------------------------------------------------------------------

class TestRoleBehaviorPrompt:
    def test_returns_string_for_known_roles(self):
        for role in ("donor", "recipient", "volunteer", "admin"):
            out = ai_engine._role_behavior_prompt(role, "en")
            assert out is None or isinstance(out, str)

    def test_none_role_ok(self):
        out = ai_engine._role_behavior_prompt(None, "en")
        assert out is None or isinstance(out, str)
