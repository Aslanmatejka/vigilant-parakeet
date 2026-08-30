"""Heuristics for confused, vague, or non-logical user messages.

Many users do not know platform vocabulary, send one-word replies, or answer
yes/no when nothing was asked. This module detects those patterns and returns
simple, deterministic guidance so the agent does not guess wrong.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

# User seems hungry / wants food but did not say "search"
_HUNGER_RE = re.compile(
    r"\b(hungry|starving|need food|want food|something to eat|feed me|"
    r"got anything|anything available|what'?s available|whats available|"
    r"tengo hambre|necesito comida|hay comida|qué hay|que hay)\b",
    re.I,
)

# Greeting or "I don't know what to do"
_VAGUE_MENU_RE = re.compile(
    r"^(?:help(?: me)?|menu|options|start|what can you do|what do you do|"
    r"how does this work|how do i use this|i'?m lost|i dont know|i don't know|"
    r"idk|no idea|what now|\?+|hola|hi|hello|hey|yo|"
    r"ayuda|no sé|no se|qué hago|que hago)\.?!?\s*$",
    re.I,
)

# Orphan yes/no — dangerous if we treat as claim confirmation
_ORPHAN_REPLY_RE = re.compile(
    r"^(?:yes|yeah|yep|yup|sure|ok|okay|please|do it|go ahead|"
    r"no|nope|nah|never mind|nevermind|cancel|"
    r"sí|si|vale|claro|no gracias|gracias|thanks|thank you)\.?!?\s*$",
    re.I,
)

# Claim-ish words without a concrete target
_VAGUE_CLAIM_RE = re.compile(
    r"^(?:claim|reserve|take|get|i want (?:that|it|one)|give me|"
    r"reclamar|reservar|quiero|dame)\.?!?\s*$",
    re.I,
)

# Explicit numbered pick from a list the assistant just showed
_NUMBERED_CLAIM_RE = re.compile(
    r"(?:\b(claim|reclamar|reserve|reservar|take|quiero)\s*#?\s*\d+\b|"
    r"^#\s*\d+\.?!?\s*$|\b(the\s+)?(first|second|third|\d+(?:st|nd|rd|th))\b)",
    re.I,
)

# Random short noun — might be food type or might be nonsense
_SHORT_FRAGMENT_RE = re.compile(r"^[\w\s\-']{1,24}$")


@dataclass
class TurnAssessment:
    """How to handle a user turn that may be unclear."""

    is_vague: bool = False
    is_orphan_reply: bool = False
    override_intent: Optional[str] = None
    guide_mode: Optional[str] = None
    guidance_hint: str = ""
    confidence_cap: float = 1.0


def _last_assistant_asked_question(prior: list[Any]) -> bool:
    """True if the last assistant turn expected a specific answer."""
    for msg in reversed(prior or []):
        role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", None)
        if role != "assistant":
            continue
        content = (
            (msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", None))
            or ""
        ).strip()
        meta = (msg.get("metadata") if isinstance(msg, dict) else None) or {}
        if "?" in content:
            return True
        if meta.get("pending_action") or meta.get("awaiting_confirmation"):
            return True
        # Tool results with ask_user question in last turn
        if "confirm" in content.lower() or "just to confirm" in content.lower():
            return True
        if "¿confirm" in content.lower() or "confirma" in content.lower():
            return True
        return False
    return False


def assess_user_turn(
    message: str,
    prior_messages: list[Any],
    intent: Optional[str],
    *,
    confidence: float = 1.0,
) -> TurnAssessment:
    """Classify whether the user needs hand-holding this turn."""
    text = (message or "").strip()
    if not text:
        return TurnAssessment(is_vague=True, guide_mode="menu", guidance_hint="empty message")

    lo = text.lower()

    # Orphan yes/no — do NOT treat as claim authorization
    if _ORPHAN_REPLY_RE.match(text) and not _last_assistant_asked_question(prior_messages):
        return TurnAssessment(
            is_orphan_reply=True,
            is_vague=True,
            guide_mode="orphan_reply",
            guidance_hint="yes/no without a pending question",
            confidence_cap=0.3,
        )

    # Explicit menu / lost / help with no topic
    if _VAGUE_MENU_RE.match(text) or (len(text) <= 3 and "?" in text):
        return TurnAssessment(
            is_vague=True,
            guide_mode="menu",
            guidance_hint="user asked for help or sent greeting only",
        )

    if lo.startswith("help") and len(text.split()) <= 4:
        if not any(kw in lo for kw in ("cancel", "claim", "post", "donate", "listing", "pickup")):
            return TurnAssessment(
                is_vague=True,
                guide_mode="menu",
                guidance_hint="generic help request",
            )

    # Explicit numbered claim — user picked from the list (#1, Claim #2, "the first")
    if _NUMBERED_CLAIM_RE.search(text):
        return TurnAssessment(
            override_intent="claim",
            guidance_hint="numbered listing reference — resolve from prior search",
        )

    # Vague claim with no listing named
    if _VAGUE_CLAIM_RE.match(text) or (
        intent == "claim" and len(text.split()) <= 3 and not _NUMBERED_CLAIM_RE.search(text)
    ):
        return TurnAssessment(
            is_vague=True,
            override_intent="search",
            guide_mode="claim_needs_pick",
            guidance_hint="claim without naming a listing — search first",
            confidence_cap=min(confidence, 0.6),
        )

    # Hungry / available food — search, but remind to show numbered list
    if _HUNGER_RE.search(text) and intent in (None, "general", "help"):
        return TurnAssessment(
            override_intent="search",
            guidance_hint="hunger/availability phrasing → search then numbered list",
        )

    # Very low classifier confidence + short message
    if confidence < 0.45 and len(text.split()) <= 4:
        return TurnAssessment(
            is_vague=True,
            guide_mode="clarify",
            guidance_hint=f"low confidence ({confidence:.2f}) on short message",
            confidence_cap=confidence,
        )

    # Single vague word that is not clearly food
    if (
        intent == "general"
        and _SHORT_FRAGMENT_RE.match(text)
        and len(text.split()) == 1
        and text.lower() not in {"bread", "milk", "eggs", "fruit", "pan", "leche"}
    ):
        return TurnAssessment(
            is_vague=True,
            guide_mode="clarify",
            guidance_hint="single ambiguous word",
        )

    return TurnAssessment()


def format_welcome_menu(language: str = "en") -> str:
    """Simple numbered menu — no jargon."""
    if language.startswith("es"):
        return (
            "¡Hola! Soy Nouri. Puedo ayudarte con cosas concretas — elige una opción "
            "o escribe lo que necesitas con tus palabras:\n\n"
            "1️⃣ **Buscar comida** cerca de ti (escribe «buscar comida» o «tengo hambre»)\n"
            "2️⃣ **Compartir comida** que te sobre (escribe «donar comida» o «publicar»)\n"
            "3️⃣ **Ver mis reservas** / recogidas (escribe «mis reservas»)\n"
            "4️⃣ **Cómo funciona** DoGoods (escribe «cómo funciona»)\n\n"
            "No hace falta ser perfecto — una frase corta está bien. "
            "¿Qué te gustaría hacer?"
        )
    return (
        "Hi! I'm Nouri. I can help with a few simple things — pick a number "
        "or just tell me in your own words:\n\n"
        "1️⃣ **Find food** near you (try «find food» or «I'm hungry»)\n"
        "2️⃣ **Share food** you have extra (try «donate food» or «post a listing»)\n"
        "3️⃣ **My pickups / claims** (try «my pickups» or «my claims»)\n"
        "4️⃣ **How DoGoods works** (try «how does this work»)\n\n"
        "You don't need the perfect words — a short sentence is fine. "
        "What would you like to do?"
    )


def format_orphan_reply_help(language: str = "en") -> str:
    """When user says yes/no but we didn't ask anything specific."""
    if language.startswith("es"):
        return (
            "No estoy seguro de a qué te refieres con eso — no te hice una pregunta "
            "concreta en el mensaje anterior.\n\n"
            "Dime qué quieres hacer:\n"
            "• «buscar comida» — ver qué hay cerca\n"
            "• «donar comida» — publicar lo que compartes\n"
            "• «mis reservas» — ver tus recogidas\n\n"
            "¿Cuál prefieres?"
        )
    return (
        "I'm not sure what you mean by that — I didn't ask you a specific "
        "yes/no question on my last message.\n\n"
        "Tell me what you'd like to do:\n"
        "• «find food» — see what's available nearby\n"
        "• «donate food» — post something you're sharing\n"
        "• «my pickups» — check your claims\n\n"
        "Which one sounds right?"
    )


def format_claim_needs_pick(language: str = "en") -> str:
    """Before claiming, user must pick from a list."""
    if language.startswith("es"):
        return (
            "Para reservar algo, primero necesito mostrarte qué hay disponible. "
            "Buscaré comida cerca de ti y te listaré opciones numeradas — "
            "después dime el número o el nombre (por ejemplo «el 2» o «el pan»)."
        )
    return (
        "To claim something, I first need to show you what's available. "
        "I'll search for food near you and list numbered options — then tell me "
        "the number or name (like «#2» or «the bread»)."
    )


def format_simple_clarify(language: str = "en", user_message: str = "") -> str:
    if language.startswith("es"):
        return (
            "Quiero ayudarte, pero no entendí del todo. ¿Buscas **comida cerca**, "
            "quieres **compartir comida**, o necesitas **ayuda con la app**? "
            "Responde con una de esas tres palabras o elige 1, 2 o 3 del menú."
        )
    return (
        "I want to help, but I'm not fully sure what you need. Are you trying to "
        "**find food nearby**, **share food**, or get **help using the app**? "
        "Reply with one of those three, or pick 1, 2, or 3 from the menu."
    )


def resolve_guided_response(guide_mode: Optional[str], language: str = "en") -> Optional[str]:
    """Deprecated: responses are LLM-generated. Kept for tests / legacy imports."""
    return None


def simplify_question(question: str, language: str = "en") -> str:
    """Short, plain-language ask_user prompts for donate/intake."""
    if not question:
        return question
    if language.startswith("es"):
        return question
    # Already simple enough if under ~120 chars
    if len(question) <= 120:
        return question
    return question.split(".")[0].strip() + "?"


ACCESSIBILITY_GUIDANCE = """**Guiding confused or non-technical users (CRITICAL):**
- Assume the user may NOT know app terms (listing, claim, donor, intake).
  Use plain words: "food post", "reserve", "pick up", "share".
- ONE simple question per turn. Never stack three questions in one message.
- When intent is unclear, offer a numbered menu (find / share / my pickups / help)
  instead of guessing and running the wrong tool.
- NEVER treat bare "yes", "ok", or "sure" as permission to claim or post unless
  YOUR IMMEDIATELY PREVIOUS message asked a clear yes/no confirmation question.
- After search, ALWAYS show a NUMBERED list (1, 2, 3…) before any claim.
- If the user sends gibberish, emoji-only, or a single ambiguous word, ask what
  they want using the menu — do not call write tools.
- Prefer doing the safe read-only action (search, get_my_claims) over guessing
  a destructive/write action when confused.
- Repeat the user's goal in one short line before acting ("Got it — finding food near you").
- Never scold. Never say "invalid" or "that doesn't make sense". Stay warm.
"""

_LANG_LABELS = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "vi": "Vietnamese",
    "zh": "Chinese (Simplified)",
}


def build_accessibility_profile_prompt(profile: dict | None) -> str:
    """Turn client accessibility_profile JSON into a system prompt block."""
    if not profile or not isinstance(profile, dict):
        return ""

    lines: list[str] = ["**User accessibility preferences (honor on every reply):**"]

    lang = str(profile.get("preferredLanguage") or profile.get("language") or "").strip().lower()
    if lang and lang != "en":
        label = _LANG_LABELS.get(lang, lang)
        lines.append(
            f"- Preferred response language: {label} ({lang}). "
            f"Respond ENTIRELY in this language unless the user clearly switches."
        )

    if profile.get("simpleLanguage"):
        lines.append(
            "- Use simple language at roughly a 6th-grade reading level: "
            "short sentences, everyday words, no jargon."
        )

    if profile.get("preferTextOverVoice"):
        lines.append(
            "- User prefers text over voice: keep replies concise, scannable, "
            "and suitable for on-screen reading (they may not hear audio)."
        )
    elif profile.get("formVoiceGuideEnabled"):
        lines.append(
            "- Form voice guide is ON: the user wants spoken field hints on "
            "forms — keep written text clear too."
        )
    else:
        lines.append(
            "- Form voice guide is OFF: give form help as text only; do not "
            "assume they hear spoken field hints."
        )

    if profile.get("easyMode"):
        lines.append(
            "- Easy Mode is ON: one step at a time, never overwhelm with "
            "multiple tasks or long paragraphs."
        )

    if profile.get("screenReaderOptimized"):
        lines.append(
            "- Screen reader optimized: describe actions in words, avoid "
            "emoji-only replies, and name buttons/links clearly."
        )

    if profile.get("alwaysShowCaptions"):
        lines.append("- Captions are enabled — pair spoken guidance with clear written text.")

    if profile.get("largeText") or profile.get("highContrast"):
        lines.append("- Visual accessibility is enabled — favor clarity over dense UI instructions.")

    if profile.get("listFirstFind"):
        lines.append(
            "- Find Food uses list-first layout: describe listings before map directions."
        )

    if len(lines) <= 1:
        return ""
    return "\n".join(lines)


__all__ = [
    "ACCESSIBILITY_GUIDANCE",
    "build_accessibility_profile_prompt",
    "TurnAssessment",
    "assess_user_turn",
    "format_welcome_menu",
    "resolve_guided_response",
    "simplify_question",
]
