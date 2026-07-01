"""
Tests for backend.agent.curiosity (AGENT_V2 Phase 5 full).

Covers:
- should_ask_followup: actionable intent + low info / low confidence,
  world signal suppresses, non-actionable intent suppresses.
- generate_followup_heuristic: EN/ES, intent lookup, unknown intent
  returns None, generic fallback when intent in actionable set but
  not in the table.
- generate_followup_llm: heuristic fallback paths (no API key,
  langchain import error).
"""
from __future__ import annotations

import asyncio
import sys

import pytest

from backend.agent.curiosity import (
    CURIOSITY_CONFIDENCE_CEIL,
    generate_followup_heuristic,
    generate_followup_llm,
    should_ask_followup,
)


# ----------------------------------------------------------------------
# should_ask_followup
# ----------------------------------------------------------------------

def test_followup_triggers_on_low_info_actionable_intent():
    # 2 short tokens — below the 3-token info threshold.
    assert should_ask_followup(
        intent="search_food", confidence=0.9, message="find stuff",
    ) is True


def test_followup_triggers_on_low_confidence():
    assert should_ask_followup(
        intent="claim_food", confidence=0.3,
        message="please claim the listing for me tonight thanks",
    ) is True


def test_followup_no_trigger_when_high_confidence_and_rich_info():
    assert should_ask_followup(
        intent="search_food", confidence=0.95,
        message="find me organic apples within 5km of midtown please",
    ) is False


def test_followup_no_trigger_on_non_actionable_intent():
    assert should_ask_followup(
        intent="chitchat", confidence=0.2, message="hi",
    ) is False


def test_followup_suppressed_by_world_signal():
    assert should_ask_followup(
        intent="search_food", confidence=0.2, message="rice",
        world_has_signal=True,
    ) is False


def test_followup_empty_intent_no_trigger():
    assert should_ask_followup(
        intent="", confidence=0.1, message="anything",
    ) is False


def test_curiosity_confidence_ceil_sane():
    assert 0.40 <= CURIOSITY_CONFIDENCE_CEIL <= 0.80


# ----------------------------------------------------------------------
# generate_followup_heuristic
# ----------------------------------------------------------------------

def test_heuristic_english_lookup_for_search_food():
    out = generate_followup_heuristic("search_food", "find rice", language="en")
    assert out is not None
    assert "?" in out
    assert "food" in out.lower() or "pick" in out.lower()


def test_heuristic_spanish_lookup_for_search_food():
    out = generate_followup_heuristic("search_food", "buscar arroz", language="es")
    assert out is not None
    assert "?" in out
    assert "comida" in out.lower() or "recogerla" in out.lower()


def test_heuristic_returns_none_for_non_actionable_intent():
    assert generate_followup_heuristic("chitchat", "hi", language="en") is None
    assert generate_followup_heuristic("", "hi", language="en") is None


@pytest.mark.parametrize("intent", [
    "search_food", "find_food", "claim_food", "list_food", "share_food",
    "donate", "donate_food", "schedule", "schedule_pickup",
    "join_community", "leave_community",
])
def test_heuristic_returns_a_question_for_each_actionable_intent(intent):
    out_en = generate_followup_heuristic(intent, "x", language="en")
    out_es = generate_followup_heuristic(intent, "x", language="es")
    assert out_en is not None and "?" in out_en
    assert out_es is not None and "?" in out_es


# ----------------------------------------------------------------------
# generate_followup_llm fallbacks
# ----------------------------------------------------------------------

def test_llm_followup_no_api_key_uses_heuristic(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    out = asyncio.run(generate_followup_llm(
        "search_food", "find rice", language="en",
    ))
    # Equals heuristic since LLM is skipped.
    expected = generate_followup_heuristic("search_food", "find rice", language="en")
    assert out == expected


def test_llm_followup_non_actionable_returns_none(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
    out = asyncio.run(generate_followup_llm("chitchat", "hi", language="en"))
    assert out is None


def test_llm_followup_langchain_import_error_falls_back(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
    real = sys.modules.pop("langchain_openai", None)
    sys.modules["langchain_openai"] = None  # type: ignore[assignment]
    try:
        out = asyncio.run(generate_followup_llm(
            "search_food", "rice", language="en",
        ))
    finally:
        if real is not None:
            sys.modules["langchain_openai"] = real
        else:
            sys.modules.pop("langchain_openai", None)
    expected = generate_followup_heuristic("search_food", "rice", language="en")
    assert out == expected
