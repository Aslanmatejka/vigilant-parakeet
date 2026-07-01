"""
Tests for backend.agent.self_eval (AGENT_V2 Phase 7 lite).

Covers:
- SelfEvaluation.to_dict shape + value clamping.
- should_retry threshold + safety=0 override.
- detect_pushback EN + ES positive / negative cases.
- surface_uncertainty no-op and hedge paths (EN + ES).
- evaluate_response_heuristic across the main score branches.
- Overall formula sanity.
"""
from __future__ import annotations

import asyncio
import math

import pytest

from backend.agent.self_eval import (
    RETRY_THRESHOLD,
    UNCERTAINTY_FLOOR,
    SelfEvaluation,
    detect_pushback,
    evaluate_response_heuristic,
    evaluate_response_llm,
    should_retry,
    surface_uncertainty,
)


# ----------------------------------------------------------------------
# SelfEvaluation dataclass
# ----------------------------------------------------------------------

def test_self_evaluation_to_dict_shape_defaults():
    ev = SelfEvaluation()
    d = ev.to_dict()
    assert set(d.keys()) == {
        "correctness", "helpfulness", "safety", "calibration",
        "overall", "critique", "retry_recommended", "notes",
    }
    for key in ("correctness", "helpfulness", "safety", "calibration", "overall"):
        assert isinstance(d[key], float)
        assert 0.0 <= d[key] <= 1.0
    assert isinstance(d["retry_recommended"], bool)
    assert isinstance(d["notes"], list)


def test_self_evaluation_to_dict_rounds_to_three_places():
    ev = SelfEvaluation(correctness=0.123456, helpfulness=0.7777777)
    d = ev.to_dict()
    # round(0.123456, 3) == 0.123
    assert d["correctness"] == pytest.approx(0.123)
    assert d["helpfulness"] == pytest.approx(0.778)


# ----------------------------------------------------------------------
# should_retry
# ----------------------------------------------------------------------

def test_should_retry_true_when_overall_below_threshold():
    ev = SelfEvaluation(overall=0.40, safety=1.0)
    assert should_retry(ev) is True


def test_should_retry_false_when_overall_above_threshold():
    ev = SelfEvaluation(overall=0.90, safety=1.0)
    assert should_retry(ev) is False


def test_should_retry_safety_zero_forces_retry_even_with_high_overall():
    ev = SelfEvaluation(overall=0.99, safety=0.0)
    assert should_retry(ev) is True


def test_should_retry_respects_threshold_argument():
    ev = SelfEvaluation(overall=0.60, safety=1.0)
    assert should_retry(ev, threshold=0.50) is False
    assert should_retry(ev, threshold=0.80) is True


def test_retry_threshold_constant_is_sane():
    # Sanity guard: ensure the constant stays in a defensible range.
    assert 0.30 <= RETRY_THRESHOLD <= 0.75


# ----------------------------------------------------------------------
# detect_pushback
# ----------------------------------------------------------------------

@pytest.mark.parametrize("msg", [
    "No, that's wrong.",
    "that's incorrect",
    "That isn't right",
    "You said earlier that I had 5 listings",
    "you're wrong about that",
    "I didn't say bananas",
    "that's not what I meant",
    "No es correcto",
    "Estás equivocado",
])
def test_detect_pushback_positive_cases(msg):
    assert detect_pushback(msg) is True


@pytest.mark.parametrize("msg", [
    "",
    "   ",
    "hi",
    "thanks!",
    "Tell me about food sharing",
    "Can you help me claim something?",
    "Yes that sounds right",
])
def test_detect_pushback_negative_cases(msg):
    assert detect_pushback(msg) is False


# ----------------------------------------------------------------------
# surface_uncertainty
# ----------------------------------------------------------------------

def test_surface_uncertainty_noop_high_confidence():
    text = "Here is the result: 3 listings available."
    out = surface_uncertainty(text, confidence=0.9, tool_succeeded=False)
    assert out == text


def test_surface_uncertainty_noop_tool_succeeded():
    text = "Here is the result: 3 listings available."
    out = surface_uncertainty(text, confidence=0.2, tool_succeeded=True)
    assert out == text


def test_surface_uncertainty_noop_when_already_hedged():
    text = "I'm not sure but there may be 3 listings."
    out = surface_uncertainty(text, confidence=0.2, tool_succeeded=False)
    assert out == text


def test_surface_uncertainty_noop_when_not_definitive():
    text = "ok"
    out = surface_uncertainty(text, confidence=0.2, tool_succeeded=False)
    assert out == text


def test_surface_uncertainty_prepends_english_hedge_when_definitive_and_low_conf():
    text = (
        "Here is the answer: you currently have 5 active listings in your "
        "neighbourhood, and three of them are nearing expiry."
    )
    out = surface_uncertainty(text, confidence=0.2, tool_succeeded=False, language="en")
    assert out != text
    assert out.endswith(text)
    assert "not fully sure" in out.lower()


def test_surface_uncertainty_prepends_spanish_hedge_when_language_es():
    text = (
        "Aquí está la respuesta: actualmente tienes 5 publicaciones activas "
        "en tu vecindario y tres están por expirar pronto."
    )
    out = surface_uncertainty(text, confidence=0.2, tool_succeeded=False, language="es")
    assert out != text
    assert out.endswith(text)
    assert "no estoy" in out.lower()


def test_uncertainty_floor_constant_is_sane():
    assert 0.30 <= UNCERTAINTY_FLOOR <= 0.75


# ----------------------------------------------------------------------
# evaluate_response_heuristic
# ----------------------------------------------------------------------

def test_evaluate_heuristic_all_tools_failed_drops_correctness():
    tools = [
        {"tool": "x", "result": {"error": "boom", "success": False}},
        {"tool": "y", "result": {"error": "nope", "success": False}},
    ]
    ev = evaluate_response_heuristic(
        "find food", "Sorry, something broke.",
        tool_results=tools, confidence=0.5,
        persona_ok=True, safe_text_changed=False,
    )
    assert ev.correctness <= 0.35
    assert "tools failed" in " ".join(ev.notes).lower()


def test_evaluate_heuristic_succeeded_tools_lifts_correctness():
    tools = [{"tool": "x", "result": {"success": True, "data": [1, 2]}}]
    ev = evaluate_response_heuristic(
        "find food",
        "Here is the list of items available right now in your area.",
        tool_results=tools, confidence=0.7,
        persona_ok=True, safe_text_changed=False,
    )
    assert ev.correctness >= 0.85


def test_evaluate_heuristic_empty_response_drops_helpfulness():
    ev = evaluate_response_heuristic(
        "any food?", "",
        tool_results=None, confidence=0.5,
        persona_ok=True, safe_text_changed=False,
    )
    assert ev.helpfulness <= 0.20


def test_evaluate_heuristic_safe_text_changed_drops_safety():
    ev = evaluate_response_heuristic(
        "show me",
        "Here are the results in your area.",
        tool_results=None, confidence=0.7,
        persona_ok=True, safe_text_changed=True,
    )
    assert ev.safety < 1.0
    assert any("sanitizer" in n.lower() for n in ev.notes)


def test_evaluate_heuristic_persona_failure_caps_calibration():
    ev = evaluate_response_heuristic(
        "hi", "Some response that breaks persona for whatever reason.",
        tool_results=None, confidence=0.7,
        persona_ok=False, safe_text_changed=False,
    )
    assert ev.calibration <= 0.50
    assert any("persona" in n.lower() for n in ev.notes)


def test_evaluate_heuristic_definitive_low_confidence_drops_calibration():
    ev = evaluate_response_heuristic(
        "how many listings",
        "Here is the answer: you have 7 listings active right now in your area.",
        tool_results=None, confidence=0.20,
        persona_ok=True, safe_text_changed=False,
    )
    assert ev.calibration <= 0.50
    assert any("definitive" in n.lower() for n in ev.notes)


def test_evaluate_heuristic_overall_formula_matches_weighted_sum():
    ev = evaluate_response_heuristic(
        "tell me",
        "Here is a useful and complete answer to your question about food sharing.",
        tool_results=[{"tool": "x", "result": {"success": True}}],
        confidence=0.7, persona_ok=True, safe_text_changed=False,
    )
    expected = (
        ev.correctness * 0.35
        + ev.helpfulness * 0.30
        + ev.safety * 0.20
        + ev.calibration * 0.15
    )
    assert math.isclose(ev.overall, expected, abs_tol=1e-6)


def test_evaluate_heuristic_retry_recommended_flag_consistent_with_should_retry():
    # Force a low-overall path: failed tools + safety scrub + persona fail.
    ev = evaluate_response_heuristic(
        "find food", "",
        tool_results=[{"tool": "x", "result": {"error": "boom"}}],
        confidence=0.2, persona_ok=False, safe_text_changed=True,
    )
    assert ev.retry_recommended is True
    assert should_retry(ev) is True
    assert ev.critique  # non-empty


def test_evaluate_heuristic_good_response_does_not_recommend_retry():
    ev = evaluate_response_heuristic(
        "find food",
        "Here are 3 items available in your neighbourhood with their details.",
        tool_results=[{"tool": "x", "result": {"success": True}}],
        confidence=0.85, persona_ok=True, safe_text_changed=False,
    )
    assert ev.retry_recommended is False
    assert should_retry(ev) is False


# ----------------------------------------------------------------------
# evaluate_response_llm — falls back to heuristic without an API key
# ----------------------------------------------------------------------

def test_evaluate_response_llm_falls_back_to_heuristic_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    ev = asyncio.run(evaluate_response_llm(
        "find food",
        "Here is the list of items available right now in your area.",
        tool_results=[{"tool": "x", "result": {"success": True}}],
        confidence=0.7, persona_ok=True, safe_text_changed=False,
    ))
    assert isinstance(ev, SelfEvaluation)
    # Heuristic gives correctness=0.90 when a tool succeeded and response is non-empty.
    assert ev.correctness >= 0.85


def test_evaluate_response_llm_empty_response_uses_heuristic(monkeypatch):
    # Empty response short-circuits to heuristic even if a key is present.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
    ev = asyncio.run(evaluate_response_llm(
        "tell me", "",
        tool_results=None, confidence=0.5,
        persona_ok=True, safe_text_changed=False,
    ))
    assert isinstance(ev, SelfEvaluation)
    assert ev.helpfulness <= 0.20
