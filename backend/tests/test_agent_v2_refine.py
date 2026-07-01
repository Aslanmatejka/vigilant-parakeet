"""
Tests for backend.agent.refine (AGENT_V2 Phase 7 full).

Covers:
- Heuristic refiner: empty input, definitive-opener softening, EN/ES
  lead-in and tail, fact preservation, length cap.
- LLM refiner: falls back to heuristic without API key, with empty
  input, and with langchain unavailable (simulated via monkeypatch).
"""
from __future__ import annotations

import asyncio

import pytest

from backend.agent.refine import (
    refine_response_heuristic,
    refine_response_llm,
)


# ----------------------------------------------------------------------
# Heuristic refiner
# ----------------------------------------------------------------------

def test_heuristic_empty_response_returns_english_apology():
    out = refine_response_heuristic(
        "find food", "", critique="below bar", language="en",
    )
    assert out
    assert "sorry" in out.lower()
    assert "more context" in out.lower()


def test_heuristic_empty_response_returns_spanish_apology():
    out = refine_response_heuristic(
        "buscar comida", "", critique="por debajo del límite", language="es",
    )
    assert out
    assert "disculpa" in out.lower()


def test_heuristic_strips_definitive_opener_english():
    draft = "Here is the answer: there are 3 listings available right now."
    out = refine_response_heuristic("how many?", draft, "too confident", language="en")
    assert "Here is the answer" not in out
    # Preserve the underlying fact
    assert "3 listings" in out


def test_heuristic_strips_definitive_opener_spanish():
    draft = "Aquí está la respuesta: hay 3 publicaciones disponibles."
    out = refine_response_heuristic("¿cuántas?", draft, "demasiado seguro", language="es")
    assert "Aquí está la respuesta" not in out
    assert "3 publicaciones" in out


def test_heuristic_prepends_english_lead_in_and_tail():
    draft = "There are 5 items available in your area."
    out = refine_response_heuristic("any food?", draft, "improve", language="en")
    assert out.startswith("Let me try")
    assert out.rstrip().endswith("?")
    assert "5 items" in out


def test_heuristic_prepends_spanish_lead_in_and_tail():
    draft = "Hay 5 artículos disponibles en tu zona."
    out = refine_response_heuristic("¿comida?", draft, "mejorar", language="es")
    assert out.startswith("Déjame intentar")
    assert out.rstrip().endswith("?")
    assert "5 artículos" in out


def test_heuristic_preserves_arbitrary_body_text():
    draft = (
        "There are three pickups scheduled for tomorrow at 9am, noon, and 4pm "
        "across the eastside community."
    )
    out = refine_response_heuristic("schedule?", draft, "vague", language="en")
    assert "9am" in out
    assert "noon" in out
    assert "4pm" in out
    assert "eastside" in out


def test_heuristic_caps_output_length():
    huge = "x" * 10000
    out = refine_response_heuristic("ok", huge, "long", language="en")
    assert len(out) <= 4000


# ----------------------------------------------------------------------
# LLM refiner — heuristic fallback paths
# ----------------------------------------------------------------------

def test_llm_refine_no_api_key_falls_back_to_heuristic(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    out = asyncio.run(refine_response_llm(
        "find food",
        "Here is the answer: 3 listings nearby.",
        "too confident",
        language="en",
    ))
    # Heuristic adds the lead-in
    assert out.startswith("Let me try")
    assert "3 listings" in out


def test_llm_refine_empty_response_uses_heuristic(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake-not-used")
    out = asyncio.run(refine_response_llm(
        "find food", "", "no draft", language="en",
    ))
    assert out
    assert "sorry" in out.lower()


def test_llm_refine_empty_response_spanish_uses_heuristic(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake-not-used")
    out = asyncio.run(refine_response_llm(
        "buscar", "", "sin borrador", language="es",
    ))
    assert "disculpa" in out.lower()


def test_llm_refine_langchain_import_error_falls_back(monkeypatch):
    # Force the local langchain import inside refine_response_llm to fail.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
    import sys
    # Inject a sentinel module that raises on attribute access to mimic an
    # import error mid-function. Simpler: just block the import path.
    real_langchain = sys.modules.pop("langchain_openai", None)
    sys.modules["langchain_openai"] = None  # type: ignore[assignment]
    try:
        out = asyncio.run(refine_response_llm(
            "find food",
            "Here is the answer: 7 items nearby.",
            "too confident",
            language="en",
        ))
    finally:
        if real_langchain is not None:
            sys.modules["langchain_openai"] = real_langchain
        else:
            sys.modules.pop("langchain_openai", None)
    assert out.startswith("Let me try")
    assert "7 items" in out
