"""
Brainstorm / Creative Ideation (AGENT_V2 — Phase 5 full)
=========================================================

A dedicated path for "give me ideas for ..." / "brainstorm ..." turns.
Isolated from the action layer: brainstorm responses never trigger
tools or write actions. Higher temperature, divergent output.

Design parity with the rest of v2:

- Pure detection helper + heuristic + LLM generation.
- Heuristic returns a small bank of stock ideas keyed off the topic
  so offline tests have something deterministic to assert against.
- LLM uses gpt-4o-mini at higher temperature (0.85) — calibrated for
  variety. Falls back to heuristic on any failure.
- EN + ES intent detection and output language.

Out of scope:

- Embedding-based topic clustering. The lite version inspects keywords.
- A real `brainstorm` tool registered with the planner. The lite
  version short-circuits at the v2 layer.
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

#: Default number of ideas requested when the user doesn't specify.
DEFAULT_IDEA_COUNT: int = 5

#: Hard cap on number of ideas to prevent runaway outputs.
MAX_IDEA_COUNT: int = 10

#: LLM temperature for divergent ideation.
_BRAINSTORM_TEMPERATURE: float = 0.85

# Regex for explicit brainstorm intent in EN + ES.
_BRAINSTORM_PATTERNS = re.compile(
    r"\b(brainstorm|ideate|generate ideas?|give me ideas?|"
    r"some ideas? for|name ideas? for|come up with|"
    r"what should i (?:call|name)|"
    r"suggest (?:names?|ideas?|titles?)|"
    r"ideas (?:for|sobre|de|para)|"
    r"lluvia de ideas|gen[eé]rame ideas|sug[eé]r[eé](?:me|nme)|"
    r"sug[eé]rencias para|propon(?:me|gan)? ideas?)\b",
    re.IGNORECASE,
)

# Regex used to pull "n ideas" out of the message.
_COUNT_RE = re.compile(r"\b(\d+)\s+(?:ideas?|sugerencias|nombres?|names?)\b", re.IGNORECASE)

# Topic extraction — strip the leading "give me 5 ideas for" / "brainstorm" verb.
_TOPIC_STRIP = re.compile(
    r"^\s*(?:please\s+)?(?:can you\s+)?"
    r"(?:brainstorm|ideate|generate|give me|come up with|"
    r"name|suggest|sug[eé]r[eé](?:me|nme)|propon(?:me|gan)?|"
    r"lluvia de ideas)\s+"
    r"(?:\d+\s+)?(?:ideas?|sugerencias|nombres?|names?)?\s*"
    r"(?:for|about|on|sobre|de|para)?\s*",
    re.IGNORECASE,
)


# ----------------------------------------------------------------------
# Detection
# ----------------------------------------------------------------------

def detect_brainstorm_intent(message: str) -> bool:
    """True when the message reads as an explicit ideation request."""
    if not message or not message.strip():
        return False
    return bool(_BRAINSTORM_PATTERNS.search(message))


def extract_topic(message: str) -> str:
    """Strip the verb + "n ideas for" prefix to leave just the topic."""
    if not message:
        return ""
    cleaned = _TOPIC_STRIP.sub("", message, count=1).strip()
    # Trim trailing punctuation.
    cleaned = re.sub(r"[.!?]+\s*$", "", cleaned).strip()
    return cleaned[:140]


def extract_count(message: str, *, default: int = DEFAULT_IDEA_COUNT) -> int:
    """Pull "n ideas" / "n names" out of the message. Clamped to MAX."""
    m = _COUNT_RE.search(message or "")
    if not m:
        return min(MAX_IDEA_COUNT, max(1, int(default)))
    try:
        return min(MAX_IDEA_COUNT, max(1, int(m.group(1))))
    except (TypeError, ValueError):
        return min(MAX_IDEA_COUNT, max(1, int(default)))


# ----------------------------------------------------------------------
# Heuristic generator
# ----------------------------------------------------------------------

# Generic stock-idea banks for common food-sharing brainstorm topics.
# Kept short on purpose; the heuristic is a fallback, not the main path.
_STOCK_IDEAS_EN: dict[str, list[str]] = {
    "community": [
        "Eastside Pantry Co-op",
        "Neighbourly Plates",
        "GroundSwell Kitchen",
        "Open Table Network",
        "Harvest Hands",
        "Block-by-Block Bites",
        "FreshShare Collective",
        "Common Ground Foods",
    ],
    "event": [
        "Pop-up community pantry on Saturday morning",
        "Recipe-swap potluck with surplus ingredients",
        "Weekly donor-recipient meetup in a local park",
        "Pickup-window challenge — most listings cleared in a week",
        "Seasonal harvest fair with featured donors",
        "Kid-friendly cooking demo using shared produce",
    ],
    "recipe": [
        "Veggie chili using surplus root vegetables",
        "Pantry pasta with whatever's in the fridge",
        "Fridge-clear-out stir-fry over rice",
        "Day-old-bread panzanella salad",
        "Banana-walnut quick bread for over-ripe bananas",
        "One-pot lentil soup from pantry staples",
    ],
}

_STOCK_IDEAS_ES: dict[str, list[str]] = {
    "community": [
        "Despensa Vecinal del Este",
        "Platos del Barrio",
        "Cocina en Movimiento",
        "Red Mesa Abierta",
        "Cosecha Compartida",
        "Manos Vecinas",
    ],
    "event": [
        "Despensa emergente los sábados por la mañana",
        "Potluck de intercambio de recetas con excedentes",
        "Encuentro semanal entre donantes y vecinos en el parque",
        "Reto de ventana de recogida — más publicaciones recogidas en una semana",
        "Feria estacional de cosecha con donantes destacados",
    ],
    "recipe": [
        "Chili vegetal con tubérculos sobrantes",
        "Pasta despensa con lo que haya en el refri",
        "Salteado vacía-refri sobre arroz",
        "Panzanella con pan del día anterior",
        "Pan rápido de plátano para plátanos muy maduros",
        "Sopa de lentejas en una sola olla",
    ],
}


def _detect_topic_bank(topic: str) -> str:
    """Pick the most relevant stock bank for a given free-form topic.

    Event / recipe banks are checked BEFORE community so that
    "community event ideas" routes to event, not community.
    """
    tl = (topic or "").lower()
    if any(kw in tl for kw in ("event", "evento", "meetup", "fair", "feria", "potluck", "popup", "pop-up")):
        return "event"
    if any(kw in tl for kw in ("recipe", "receta", "dish", "platillo", "cook", "cocinar")):
        return "recipe"
    if any(kw in tl for kw in ("community", "comunidad", "neighbourhood", "barrio", "name", "nombre")):
        return "community"
    return "community"  # default


def brainstorm_heuristic(
    topic: str,
    *,
    n: int = DEFAULT_IDEA_COUNT,
    language: str = "en",
) -> list[str]:
    """Pick `n` stock ideas from the bank matching the topic.

    Returns a deterministic ordered slice — easy to assert on.
    """
    n = min(MAX_IDEA_COUNT, max(1, int(n)))
    is_es = (language or "").startswith("es")
    bank_map = _STOCK_IDEAS_ES if is_es else _STOCK_IDEAS_EN
    bank_key = _detect_topic_bank(topic)
    bank = bank_map.get(bank_key) or bank_map["community"]
    # Top up from every other bank in turn so we can serve up to MAX.
    pool = list(bank)
    if len(pool) < n:
        for other_key, other_bank in bank_map.items():
            if other_key == bank_key:
                continue
            for extra in other_bank:
                if extra not in pool:
                    pool.append(extra)
                if len(pool) >= n:
                    break
            if len(pool) >= n:
                break
    return pool[:n]


def format_ideas_as_response(
    ideas: list[str],
    topic: str,
    *,
    language: str = "en",
) -> str:
    """Render an idea list into a user-facing message body."""
    if not ideas:
        if (language or "").startswith("es"):
            return "No se me ocurrieron ideas en este momento. ¿Quieres intentar con un tema más específico?"
        return "I didn't come up with anything just now — want to try a more specific topic?"

    is_es = (language or "").startswith("es")
    topic_clean = (topic or "").strip()
    if is_es:
        header = (
            f"Aquí van {len(ideas)} ideas sobre {topic_clean}:" if topic_clean
            else f"Aquí van {len(ideas)} ideas:"
        )
        tail = "¿Cuál te llama la atención, o quieres que pruebe otro ángulo?"
    else:
        header = (
            f"Here are {len(ideas)} ideas for {topic_clean}:" if topic_clean
            else f"Here are {len(ideas)} ideas:"
        )
        tail = "Which one stands out, or should I try a different angle?"

    body = "\n".join(f"{i+1}. {idea}" for i, idea in enumerate(ideas))
    return f"{header}\n{body}\n\n{tail}"


# ----------------------------------------------------------------------
# LLM generator
# ----------------------------------------------------------------------

_BRAINSTORM_SYSTEM_PROMPT = (
    "You are the creative-ideation head of a food-sharing assistant. "
    "Generate a fresh, diverse list of ideas on the given topic. Rules:\n"
    "- exactly the requested count, one per line, no numbering\n"
    "- each idea is a short noun phrase or one-sentence pitch (<= 14 words)\n"
    "- no preamble, no apology, no markdown bullets or numbering\n"
    "- match the user's language\n"
    "- ideas must NOT be operational actions; never propose claiming, "
    "listing, deleting, or any side-effect — pure ideation only.\n"
    "Return ONLY the lines of ideas."
)


def _scrub(text: str) -> str:
    cleaned = re.sub(
        r"(sk-[A-Za-z0-9]{16,}|Bearer\s+[A-Za-z0-9._\-]{16,})",
        "[redacted]", text or "", flags=re.IGNORECASE,
    )
    return cleaned[:300]


async def brainstorm_llm(
    topic: str,
    *,
    n: int = DEFAULT_IDEA_COUNT,
    language: str = "en",
) -> list[str]:
    """LLM-backed brainstorm. Falls back to heuristic on any failure."""
    n = min(MAX_IDEA_COUNT, max(1, int(n)))
    if not os.getenv("OPENAI_API_KEY"):
        return brainstorm_heuristic(topic, n=n, language=language)

    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage, SystemMessage
    except Exception as exc:  # noqa: BLE001
        logger.info("brainstorm_llm: langchain unavailable (%s) — heuristic", exc)
        return brainstorm_heuristic(topic, n=n, language=language)

    payload = (
        f"Language: {language or 'en'}\n"
        f"Topic: {_scrub(topic) or '(unspecified)'}\n"
        f"Count: {n}"
    )

    try:
        model = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=_BRAINSTORM_TEMPERATURE,
            api_key=os.getenv("OPENAI_API_KEY"),
            timeout=10,
        )
        resp = await asyncio.wait_for(model.ainvoke([
            SystemMessage(content=_BRAINSTORM_SYSTEM_PROMPT),
            HumanMessage(content=payload),
        ]), timeout=8.0)
    except Exception as exc:  # noqa: BLE001
        logger.info("brainstorm_llm: invoke failed (%s) — heuristic", exc)
        return brainstorm_heuristic(topic, n=n, language=language)

    raw = (getattr(resp, "content", "") or "").strip()
    if not raw:
        return brainstorm_heuristic(topic, n=n, language=language)

    # Strip fenced code blocks if any.
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
        raw = re.sub(r"\n?```\s*$", "", raw)
        raw = raw.strip()

    # Parse lines; strip leading bullets / numbering / quote chars.
    ideas: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^[-*\u2022\d\.\)\s]+", "", line).strip()
        line = line.strip('"\'')
        if line:
            ideas.append(line[:160])
        if len(ideas) >= n:
            break

    if not ideas:
        return brainstorm_heuristic(topic, n=n, language=language)

    # Top up from heuristic if the LLM returned fewer than requested.
    if len(ideas) < n:
        for extra in brainstorm_heuristic(topic, n=n, language=language):
            if extra not in ideas:
                ideas.append(extra)
            if len(ideas) >= n:
                break

    return ideas[:n]
