"""
Tests for backend.agent.brainstorm (AGENT_V2 Phase 5 full).

Covers:
- detect_brainstorm_intent: positive (EN+ES) / negative cases.
- extract_topic / extract_count.
- brainstorm_heuristic: count, language, bank routing (community /
  event / recipe), top-up when n exceeds bank.
- format_ideas_as_response: EN/ES, empty list path, numbering.
- brainstorm_llm: fallback when no API key or langchain unavailable.
"""
from __future__ import annotations

import asyncio
import sys

import pytest

from backend.agent.brainstorm import (
    DEFAULT_IDEA_COUNT,
    MAX_IDEA_COUNT,
    brainstorm_heuristic,
    brainstorm_llm,
    detect_brainstorm_intent,
    extract_count,
    extract_topic,
    format_ideas_as_response,
)


# ----------------------------------------------------------------------
# detect_brainstorm_intent
# ----------------------------------------------------------------------

@pytest.mark.parametrize("msg", [
    "Brainstorm some names for our pantry",
    "Can you give me ideas for a community event?",
    "Generate ideas for recipes using surplus apples",
    "Come up with names for a food share group",
    "What should I call my neighbourhood pantry?",
    "Suggest names for our community kitchen",
    "Ideas para nombres de la despensa",
    "Lluvia de ideas sobre eventos",
    "Sugiéreme ideas para una receta",
    "Propónme ideas para un evento comunitario",
])
def test_detect_brainstorm_positive(msg):
    assert detect_brainstorm_intent(msg) is True


@pytest.mark.parametrize("msg", [
    "",
    "   ",
    "find me rice",
    "claim the listing",
    "post a new listing",
    "thanks!",
    "what's available right now",
])
def test_detect_brainstorm_negative(msg):
    assert detect_brainstorm_intent(msg) is False


# ----------------------------------------------------------------------
# extract_topic
# ----------------------------------------------------------------------

def test_extract_topic_strips_verb_prefix():
    assert "pantry name" in extract_topic("brainstorm pantry names").lower() or \
           "name" in extract_topic("brainstorm pantry names").lower()


def test_extract_topic_handles_n_ideas_for():
    out = extract_topic("give me 5 ideas for a community kitchen")
    assert "community" in out.lower() or "kitchen" in out.lower()


def test_extract_topic_handles_spanish():
    out = extract_topic("lluvia de ideas para un evento")
    assert "evento" in out.lower() or "un evento" in out.lower()


def test_extract_topic_strips_trailing_punctuation():
    out = extract_topic("brainstorm ideas for recipes!!")
    assert not out.endswith("!")


def test_extract_topic_empty_message():
    assert extract_topic("") == ""
    assert extract_topic(None) == ""  # type: ignore[arg-type]


# ----------------------------------------------------------------------
# extract_count
# ----------------------------------------------------------------------

def test_extract_count_explicit_number():
    assert extract_count("give me 7 ideas for x") == 7
    assert extract_count("3 nombres por favor") == 3


def test_extract_count_defaults_when_absent():
    assert extract_count("brainstorm community names") == DEFAULT_IDEA_COUNT


def test_extract_count_clamped_to_max():
    assert extract_count("give me 100 ideas") == MAX_IDEA_COUNT


def test_extract_count_clamped_to_min():
    # 0 should clamp up to 1 via the max(1, ...) gate
    assert extract_count("give me 0 ideas") >= 1


# ----------------------------------------------------------------------
# brainstorm_heuristic
# ----------------------------------------------------------------------

def test_heuristic_default_count_and_bank():
    ideas = brainstorm_heuristic("community pantry names", language="en")
    assert len(ideas) == DEFAULT_IDEA_COUNT
    # No duplicates
    assert len(set(ideas)) == len(ideas)


def test_heuristic_respects_explicit_count():
    ideas = brainstorm_heuristic("community names", n=3, language="en")
    assert len(ideas) == 3


def test_heuristic_clamps_to_max():
    ideas = brainstorm_heuristic("community", n=99, language="en")
    assert len(ideas) <= MAX_IDEA_COUNT


def test_heuristic_event_bank_routes_correctly():
    ideas = brainstorm_heuristic("community event ideas", n=3, language="en")
    # Event bank entries mention "pop-up" / "potluck" / "park" / "fair" / etc.
    assert any(
        any(kw in idea.lower() for kw in ("pop-up", "potluck", "park", "fair", "demo", "challenge"))
        for idea in ideas
    )


def test_heuristic_recipe_bank_routes_correctly():
    ideas = brainstorm_heuristic("recipe ideas using surplus", n=3, language="en")
    assert any(
        any(kw in idea.lower() for kw in ("chili", "pasta", "salad", "soup", "stir-fry", "bread"))
        for idea in ideas
    )


def test_heuristic_spanish_returns_spanish_ideas():
    ideas = brainstorm_heuristic("nombres de comunidad", n=3, language="es")
    assert len(ideas) == 3
    # At least one idea should contain a Spanish-distinctive accented char
    # or Spanish word.
    joined = " ".join(ideas).lower()
    assert any(tok in joined for tok in ("é", "ó", "í", "á", "barrio", "cosecha", "vecinal", "vecinas"))


def test_heuristic_tops_up_from_community_bank_when_short():
    # event bank has ~6 entries; ask for 9
    ideas = brainstorm_heuristic("community event names", n=9, language="en")
    assert len(ideas) == 9
    assert len(set(ideas)) == len(ideas)


# ----------------------------------------------------------------------
# format_ideas_as_response
# ----------------------------------------------------------------------

def test_format_response_empty_list_english():
    out = format_ideas_as_response([], "anything", language="en")
    assert "didn't come up with" in out.lower() or "more specific" in out.lower()


def test_format_response_empty_list_spanish():
    out = format_ideas_as_response([], "lo que sea", language="es")
    assert "no se me ocurrieron" in out.lower() or "específico" in out.lower()


def test_format_response_numbers_ideas_english():
    ideas = ["alpha", "beta", "gamma"]
    out = format_ideas_as_response(ideas, "pantry names", language="en")
    assert "1. alpha" in out
    assert "2. beta" in out
    assert "3. gamma" in out
    assert "pantry names" in out.lower()
    assert "?" in out  # trailing question


def test_format_response_numbers_ideas_spanish():
    ideas = ["uno", "dos"]
    out = format_ideas_as_response(ideas, "nombres", language="es")
    assert "1. uno" in out
    assert "2. dos" in out
    assert "nombres" in out.lower()
    assert "?" in out


# ----------------------------------------------------------------------
# brainstorm_llm fallback paths
# ----------------------------------------------------------------------

def test_llm_no_api_key_uses_heuristic(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    out = asyncio.run(brainstorm_llm("community names", n=4, language="en"))
    expected = brainstorm_heuristic("community names", n=4, language="en")
    assert out == expected


def test_llm_langchain_import_error_falls_back(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
    real = sys.modules.pop("langchain_openai", None)
    sys.modules["langchain_openai"] = None  # type: ignore[assignment]
    try:
        out = asyncio.run(brainstorm_llm("event ideas", n=3, language="en"))
    finally:
        if real is not None:
            sys.modules["langchain_openai"] = real
        else:
            sys.modules.pop("langchain_openai", None)
    expected = brainstorm_heuristic("event ideas", n=3, language="en")
    assert out == expected


def test_llm_clamps_n_to_max(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    out = asyncio.run(brainstorm_llm("community", n=999, language="en"))
    assert len(out) <= MAX_IDEA_COUNT
