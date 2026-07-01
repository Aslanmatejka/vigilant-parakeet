"""
Curiosity (AGENT_V2 — Phase 5 full)
====================================

When the agent's reasoning head landed on an action-y intent but doesn't
have enough information to act, attach a single open-ended follow-up
question so the user can fill the gap instead of getting a vague reply.

Design parity with the rest of v2:

- Pure helpers; integration point is `backend.agent.v2_graph.invoke_agent_v2`.
- Heuristic + LLM with `asyncio.wait_for` guard. Heuristic is good
  enough offline; LLM produces a more natural phrasing when a key is
  available.
- One question max — never a barrage. Empty input or already-clear
  intent returns `None`, so the integration point can drop the field.
- EN + ES coverage.

Out of scope:

- Multi-turn slot filling. The follow-up is fire-and-forget; the
  reasoning head will see the user's answer next turn and update its
  belief through the normal pipeline.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------

#: Confidence ceiling under which a follow-up may fire.
CURIOSITY_CONFIDENCE_CEIL: float = 0.65

#: Minimum useful tokens in the user message; below this we always
#: consider info "too low" regardless of intent.
_MIN_INFO_TOKEN_COUNT: int = 3

#: Intents that benefit from clarifying info before acting.
_ACTIONABLE_INTENTS = frozenset({
    "search_food", "find_food",
    "claim_food",
    "list_food", "share_food",
    "donate", "donate_food",
    "schedule", "schedule_pickup",
    "join_community", "leave_community",
})

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _info_tokens(text: str) -> int:
    """Count non-trivial tokens — proxy for "how much did the user tell us?"."""
    return sum(
        1 for t in _TOKEN_RE.findall((text or "").lower()) if len(t) > 2
    )


def should_ask_followup(
    *,
    intent: str,
    confidence: float,
    message: str,
    world_has_signal: bool = False,
) -> bool:
    """Decide whether to attach a curiosity follow-up.

    Triggers when ALL of the following hold:
      - the user's message is short on info (`info_tokens < _MIN`), OR
        the reasoning head's confidence is below the ceiling;
      - the intent is one we actually take action on (so a follow-up
        unblocks a tool call rather than just chatting);
      - the world snapshot didn't already supply the missing signal
        (e.g. dietary preferences already on file).
    """
    if not intent:
        return False
    if intent not in _ACTIONABLE_INTENTS:
        return False
    if world_has_signal:
        return False
    if _info_tokens(message) < _MIN_INFO_TOKEN_COUNT:
        return True
    if float(confidence) < CURIOSITY_CONFIDENCE_CEIL:
        return True
    return False


# ----------------------------------------------------------------------
# Heuristic follow-up generator
# ----------------------------------------------------------------------

# Stock follow-up questions per intent. Kept short (<= 18 words) and
# answerable in one phrase.
_HEURISTIC_FOLLOWUPS_EN: dict[str, str] = {
    "search_food": "Quick question — what kind of food are you hoping to find, and how far would you go to pick it up?",
    "find_food": "Quick question — what kind of food are you hoping to find, and how far would you go to pick it up?",
    "claim_food": "Just to make sure — which listing did you have in mind, and roughly when could you pick it up?",
    "list_food": "Got it. Could you tell me what you're sharing, how much there is, and by when it should be picked up?",
    "share_food": "Got it. Could you tell me what you're sharing, how much there is, and by when it should be picked up?",
    "donate": "Great — what would you like to donate, and is there a community or pickup window you have in mind?",
    "donate_food": "Great — what would you like to donate, and is there a community or pickup window you have in mind?",
    "schedule": "Sure — what day and rough time window works for you?",
    "schedule_pickup": "Sure — what day and rough time window works for you?",
    "join_community": "Which community did you have in mind, or should I look up ones near you?",
    "leave_community": "Which community would you like to leave?",
}

_HEURISTIC_FOLLOWUPS_ES: dict[str, str] = {
    "search_food": "Una pregunta rápida — ¿qué tipo de comida estás buscando y qué tan lejos podrías ir a recogerla?",
    "find_food": "Una pregunta rápida — ¿qué tipo de comida estás buscando y qué tan lejos podrías ir a recogerla?",
    "claim_food": "Para confirmar — ¿qué publicación tenías en mente y aproximadamente cuándo podrías recogerla?",
    "list_food": "Entendido. ¿Puedes contarme qué estás compartiendo, cuánto hay y hasta cuándo se puede recoger?",
    "share_food": "Entendido. ¿Puedes contarme qué estás compartiendo, cuánto hay y hasta cuándo se puede recoger?",
    "donate": "Genial — ¿qué te gustaría donar y tienes en mente alguna comunidad o ventana de recogida?",
    "donate_food": "Genial — ¿qué te gustaría donar y tienes en mente alguna comunidad o ventana de recogida?",
    "schedule": "Claro — ¿qué día y franja horaria te funciona?",
    "schedule_pickup": "Claro — ¿qué día y franja horaria te funciona?",
    "join_community": "¿Qué comunidad tenías en mente, o te busco algunas cerca de ti?",
    "leave_community": "¿Qué comunidad te gustaría dejar?",
}

# Generic fallback when intent isn't in the map.
_GENERIC_FOLLOWUP_EN = "Could you share a bit more about what you have in mind?"
_GENERIC_FOLLOWUP_ES = "¿Puedes contarme un poco más sobre lo que tienes en mente?"


def generate_followup_heuristic(
    intent: str,
    message: str,
    *,
    language: str = "en",
) -> Optional[str]:
    """Pick a stock follow-up keyed off the intent. Returns None when
    the intent isn't in the actionable set."""
    if not intent or intent not in _ACTIONABLE_INTENTS:
        return None
    is_es = (language or "").startswith("es")
    table = _HEURISTIC_FOLLOWUPS_ES if is_es else _HEURISTIC_FOLLOWUPS_EN
    fallback = _GENERIC_FOLLOWUP_ES if is_es else _GENERIC_FOLLOWUP_EN
    return table.get(intent, fallback)


# ----------------------------------------------------------------------
# LLM follow-up generator
# ----------------------------------------------------------------------

_FOLLOWUP_SYSTEM_PROMPT = (
    "You are the curiosity head of a food-sharing assistant. The agent's "
    "reasoning head landed on an actionable intent but doesn't have "
    "enough information from the user to act. Generate ONE short, "
    "open-ended follow-up question (no more than 22 words) that would "
    "unblock the next step. Rules:\n"
    "- match the user's language\n"
    "- single sentence; one question mark\n"
    "- no preamble, no apology, no 'I would like to know'\n"
    "- never mention internal state ('low confidence', 'self_eval', etc.)\n"
    "Return ONLY the question text — no quotes, no markdown."
)


def _scrub(text: str) -> str:
    cleaned = re.sub(
        r"(sk-[A-Za-z0-9]{16,}|Bearer\s+[A-Za-z0-9._\-]{16,})",
        "[redacted]", text or "", flags=re.IGNORECASE,
    )
    return cleaned[:400]


async def generate_followup_llm(
    intent: str,
    message: str,
    *,
    language: str = "en",
) -> Optional[str]:
    """LLM-backed follow-up. Falls back to heuristic on any failure."""
    if not intent or intent not in _ACTIONABLE_INTENTS:
        return None

    if not os.getenv("OPENAI_API_KEY"):
        return generate_followup_heuristic(intent, message, language=language)

    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage, SystemMessage
    except Exception as exc:  # noqa: BLE001
        logger.info("generate_followup_llm: langchain unavailable (%s) — heuristic", exc)
        return generate_followup_heuristic(intent, message, language=language)

    payload = (
        f"User language: {language or 'en'}\n"
        f"User intent: {intent}\n"
        f"User message: {_scrub(message)}"
    )

    try:
        model = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.3,
            api_key=os.getenv("OPENAI_API_KEY"),
            timeout=8,
        )
        resp = await asyncio.wait_for(model.ainvoke([
            SystemMessage(content=_FOLLOWUP_SYSTEM_PROMPT),
            HumanMessage(content=payload),
        ]), timeout=4.0)
    except Exception as exc:  # noqa: BLE001
        logger.info("generate_followup_llm: invoke failed (%s) — heuristic", exc)
        return generate_followup_heuristic(intent, message, language=language)

    raw = (getattr(resp, "content", "") or "").strip()
    if not raw:
        return generate_followup_heuristic(intent, message, language=language)

    # Strip accidental fenced code wrappers.
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
        raw = re.sub(r"\n?```\s*$", "", raw)
        raw = raw.strip()

    # Strip surrounding quotes that occasionally leak.
    if (raw.startswith('"') and raw.endswith('"')) or \
       (raw.startswith("'") and raw.endswith("'")):
        raw = raw[1:-1].strip()

    # Cap at one question — keep the first sentence only.
    if "?" in raw:
        head, _sep, _tail = raw.partition("?")
        raw = head.strip() + "?"
    return raw[:300] or generate_followup_heuristic(intent, message, language=language)
