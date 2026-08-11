"""Standing instructions — durable "always do X" / reminders / verify-me memory.

Users tell Nouri things like:
  * "always confirm the quantity"
  * "remember I prefer miles"
  * "you didn't open the map"
  * "I'm not seeing that listing"
  * "check step by step — make sure nothing's missing"

This module:
  1. Detects those phrases deterministically (don't rely on the model calling
     ``save_user_memory``).
  2. Upserts them into ``ai_user_preferences`` with typed keys
     (``always_do:…``, ``remind:…``, ``procedure:verify_steps``).
  3. Builds a compact MUST-FOLLOW system reminder for the current turn
     (visibility / omitted action / verify-steps), matching the same
     advisory injection pattern as reflection / allergen reminders.

Non-breaking: silent by default, all wiring should be ``try/except``.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Optional


ALWAYS_DO_PREFIX = "always_do:"
REMIND_PREFIX = "remind:"
VERIFY_STEPS_KEY = "procedure:verify_steps"

_STANDING_KEY_PREFIXES = (ALWAYS_DO_PREFIX, REMIND_PREFIX, "procedure:")


# ---------------------------------------------------------------------------
# Detection patterns
# ---------------------------------------------------------------------------

_ALWAYS_RE = re.compile(
    r"(?:"
    r"\balways\b|"
    r"\bfrom\s+now\s+on\b|"
    r"\bgoing\s+forward\b|"
    r"\bdon'?t\s+forget\s+to\b|"
    r"\bmake\s+sure\s+you\s+always\b|"
    r"\bplease\s+always\b|"
    r"\byou\s+should\s+always\b|"
    r"\bnever\s+forget\s+to\b|"
    # Spanish
    r"\bsiempre\b|"
    r"\bdesde\s+ahora\b|"
    r"\bno\s+olvides\s+(?:de\s+)?|"
    r"\basegurate\s+de\s+siempre\b|"
    r"\basegúrate\s+de\s+siempre\b"
    r")",
    re.IGNORECASE,
)

_REMEMBER_RE = re.compile(
    r"(?:"
    r"\bremember\s+(?:that|this|to|i)\b|"
    r"\bremind\s+(?:me|yourself|nouri)\b|"
    r"\bkeep\s+in\s+mind\b|"
    r"\bnote\s+that\b|"
    r"\bdon'?t\s+forget\s+(?:that|i|my|the)\b|"
    # Spanish
    r"\brecuerda\s+(?:que|esto|me)?\b|"
    r"\bten\s+en\s+cuenta\b|"
    r"\brecuerdame\b|"
    r"\brecuérdame\b"
    r")",
    re.IGNORECASE,
)

_OMISSION_RE = re.compile(
    r"(?:"
    r"\byou\s+didn'?t\b|"
    r"\byou\s+forgot\b|"
    r"\byou\s+missed\b|"
    r"\byou\s+never\b|"
    r"\bwhy\s+didn'?t\s+you\b|"
    r"\byou\s+still\s+haven'?t\b|"
    r"\bstill\s+waiting\s+(?:for\s+)?(?:you\s+to|on)\b|"
    # Spanish
    r"\bno\s+(?:hiciste|pusiste|mostraste|abriste|buscaste)\b|"
    r"\bolvidaste\b|"
    r"\bpor\s+qué\s+no\b|"
    r"\baún\s+no\s+(?:has|hiciste)\b"
    r")",
    re.IGNORECASE,
)

_VISIBILITY_RE = re.compile(
    r"(?:"
    r"\bi(?:'?m|\s+am)\s+not\s+seeing\b|"
    r"\bi\s+don'?t\s+see\b|"
    r"\bi\s+can'?t\s+see\b|"
    r"\bcan'?t\s+see\s+(?:it|them|the|that|this|my)\b|"
    r"\bnot\s+(?:showing|appearing|visible)\b|"
    r"\bwhere\s+(?:is|are)\s+(?:it|they|my|the)\b|"
    r"\bnothing\s+(?:shows|showing|appeared|on\s+the\s+map)\b|"
    r"\bmissing\s+(?:from|on)\s+(?:the\s+)?(?:map|list|page|screen)\b|"
    # Spanish
    r"\bno\s+(?:veo|aparece|aparece|está)\b|"
    r"\bno\s+lo\s+veo\b|"
    r"\bdónde\s+(?:está|están)\b|"
    r"\bno\s+aparece\b"
    r")",
    re.IGNORECASE,
)

_VERIFY_RE = re.compile(
    r"(?:"
    r"\bcheck\s+step\s+by\s+step\b|"
    r"\bstep\s+by\s+step\b|"
    r"\bmake\s+sure\b|"
    r"\bdouble[\s-]?check\b|"
    r"\bverify\b|"
    r"\bdon'?t\s+miss\b|"
    r"\bif\s+you(?:'?re|\s+are)\s+not\s+missing\b|"
    r"\bare\s+you\s+(?:missing|sure)\b|"
    r"\bwalk\s+(?:me\s+)?through\b|"
    r"\bgo\s+through\s+(?:each|every|the)\s+step\b|"
    r"\bchecklist\b|"
    # Spanish
    r"\brevisa\s+(?:paso\s+a\s+paso|bien)\b|"
    r"\bpaso\s+a\s+paso\b|"
    r"\basegúrate\b|"
    r"\basegurate\b|"
    r"\bverifica\b|"
    r"\bno\s+te\s+olvides\s+de\s+nada\b"
    r")",
    re.IGNORECASE,
)

_FORGET_RE = re.compile(
    r"(?:"
    r"\bforget\s+(?:that|this|what\s+i\s+said|the\s+rule)\b|"
    r"\bstop\s+always\b|"
    r"\bdon'?t\s+always\b|"
    r"\bno\s+longer\s+always\b|"
    r"\bclear\s+(?:that\s+)?(?:reminder|preference|instruction)\b|"
    # Spanish
    r"\bolvida\s+(?:eso|eso\s+que\s+dije|la\s+regla)\b|"
    r"\bya\s+no\s+siempre\b"
    r")",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class StandingHit:
    """One detected standing-instruction signal for the current turn."""

    kind: str  # always_do | remind | omission | visibility | verify | forget
    key: Optional[str]
    value: Optional[str]
    persist: bool
    turn_only: bool = False


def _slug(text: str, max_len: int = 48) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
    if not cleaned:
        digest = hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:10]
        return digest
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip("_")
    return cleaned


def _extract_instruction_tail(message: str, match: re.Match) -> str:
    """Grab the actionable clause after the trigger phrase."""
    tail = (message or "")[match.end():].strip(" \t\n\r:—,.-")
    # Truncate at sentence boundary when the rest is long chat.
    cut = re.split(r"(?<=[.!?])\s+", tail, maxsplit=1)[0].strip()
    cut = re.sub(r"\s+", " ", cut).strip(" \"'")
    return cut[:240]


def detect_standing_hits(message: str) -> list[StandingHit]:
    """Return zero or more standing-instruction hits for *message*."""
    text = (message or "").strip()
    if not text or len(text) < 4:
        return []

    hits: list[StandingHit] = []
    lower = text.lower()

    if _FORGET_RE.search(text):
        hits.append(StandingHit(
            kind="forget",
            key=None,
            value=text[:200],
            persist=False,
            turn_only=True,
        ))

    m_always = _ALWAYS_RE.search(text)
    if m_always:
        instruction = _extract_instruction_tail(text, m_always) or text[:200]
        # "always" alone / noise
        if len(instruction.split()) >= 2 or len(instruction) >= 8:
            hits.append(StandingHit(
                kind="always_do",
                key=f"{ALWAYS_DO_PREFIX}{_slug(instruction)}",
                value=instruction,
                persist=True,
            ))

    m_remember = _REMEMBER_RE.search(text)
    if m_remember and not m_always:
        instruction = _extract_instruction_tail(text, m_remember) or text[:200]
        if len(instruction.split()) >= 2 or len(instruction) >= 8:
            hits.append(StandingHit(
                kind="remind",
                key=f"{REMIND_PREFIX}{_slug(instruction)}",
                value=instruction,
                persist=True,
            ))

    if _OMISSION_RE.search(text):
        # Persist as always_do when they also say "always", else turn-only fix.
        instruction = text[:220]
        persist = bool(m_always) or "always" in lower or "siempre" in lower
        hits.append(StandingHit(
            kind="omission",
            key=f"{ALWAYS_DO_PREFIX}{_slug(instruction)}" if persist else None,
            value=instruction,
            persist=persist,
            turn_only=True,
        ))

    if _VISIBILITY_RE.search(text):
        hits.append(StandingHit(
            kind="visibility",
            key=None,
            value=text[:220],
            persist=False,
            turn_only=True,
        ))

    if _VERIFY_RE.search(text):
        standing_verify = bool(
            m_always
            or "always" in lower
            or "from now on" in lower
            or "siempre" in lower
            or "desde ahora" in lower
        )
        hits.append(StandingHit(
            kind="verify",
            key=VERIFY_STEPS_KEY if standing_verify else None,
            value="true" if standing_verify else text[:220],
            persist=standing_verify,
            turn_only=True,
        ))

    return hits


def is_standing_memory_key(key: str) -> bool:
    k = (key or "").strip().lower()
    return any(k.startswith(p) for p in _STANDING_KEY_PREFIXES)


def format_standing_memories_block(
    memories: list[dict],
    lang: str = "en",
) -> Optional[str]:
    """Split standing instructions from soft prefs; return a MUST-FOLLOW block."""
    standing: list[str] = []
    for m in memories or []:
        key = str(m.get("key") or "")
        val = str(m.get("value") or "").strip()
        if not key or not val:
            continue
        if is_standing_memory_key(key):
            if key == VERIFY_STEPS_KEY:
                standing.append(
                    "Verify every multi-step action checklist-style before "
                    "claiming success (and confirm with the user when unsure)."
                    if lang != "es"
                    else "Verifica cada acción multi-paso como lista de "
                    "comprobación antes de afirmar éxito."
                )
            else:
                label = key.split(":", 1)[-1].replace("_", " ")
                standing.append(f"{label}: {val}" if label else val)

    if not standing:
        return None

    if lang == "es":
        header = (
            "INSTRUCCIONES PERMANENTES del usuario — OBLIGATORIAS este turno "
            "(no las preguntes de nuevo; síguelas):"
        )
    else:
        header = (
            "STANDING INSTRUCTIONS from this user — MUST follow this turn "
            "(do not re-ask; obey these):"
        )
    body = "\n".join(f"  • {s}" for s in standing[:12])
    return f"{header}\n{body}"


def format_soft_preferences_block(
    memories: list[dict],
    lang: str = "en",
) -> Optional[str]:
    """Non-standing learned prefs (tone, diet notes, etc.)."""
    soft: list[str] = []
    for m in memories or []:
        key = str(m.get("key") or "")
        val = str(m.get("value") or "").strip()
        if not key or not val or is_standing_memory_key(key):
            continue
        # Tone is injected separately via tone module.
        if key == "conversation_tone":
            continue
        soft.append(f"{key}: {val}")
    if not soft:
        return None
    if lang == "es":
        header = (
            "Preferencias aprendidas sobre este usuario (de conversaciones "
            "anteriores):"
        )
        footer = (
            "Aplícalas automáticamente — NO vuelvas a preguntar lo que ya sabes."
        )
    else:
        header = "Learned preferences about this user (from prior conversations):"
        footer = (
            "Apply these automatically — do NOT ask again for things you "
            "already know."
        )
    body = "\n".join(f"  - {s}" for s in soft[:10])
    return f"{header}\n{body}\n{footer}"


def build_standing_turn_reminder(
    hits: list[StandingHit],
    *,
    memories: list[dict] | None = None,
    lang: str = "en",
) -> Optional[str]:
    """This-turn MUST-FIX reminder for visibility / omission / verify."""
    lines: list[str] = []
    kinds = {h.kind for h in hits}
    _ = memories  # reserved for future preference gating

    if "visibility" in kinds:
        if lang == "es":
            lines.append(
                "El usuario NO VE algo que espera. NO digas 'ya está' sin "
                "verificar: vuelve a buscar / mira el listing_id + status, "
                "usa show_map o navigate_ui, y reporta qué hay realmente "
                "en pantalla."
            )
        else:
            lines.append(
                "The user is NOT SEEING something they expect. Do NOT claim "
                "it's there — re-search or load the listing, check "
                "listing_id + status, call show_map / navigate_ui if needed, "
                "and report what is actually available."
            )

    if "omission" in kinds:
        if lang == "es":
            lines.append(
                "El usuario dice que TE FALTÓ hacer algo. Discúlpate breve, "
                "hazlo AHORA con la herramienta correcta, y confirma con "
                "hechos (ids / resultados de tool) — no solo palabras."
            )
        else:
            lines.append(
                "The user says you MISSED or DIDN'T do something. Apologise "
                "briefly, DO IT NOW with the right tool, and confirm with "
                "facts (ids / tool results) — not prose alone."
            )

    if "verify" in kinds:
        if lang == "es":
            lines.append(
                "Verifica PASO A PASO antes de afirmar éxito: repasa lo "
                "pedido, confirma que cada paso/tool ocurrió, y dile al "
                "usuario qué faltaba si algo falló."
            )
        else:
            lines.append(
                "Work STEP BY STEP before claiming success: enumerate what "
                "was asked, confirm each required tool/result actually ran, "
                "and tell the user plainly if anything is still missing."
            )

    if "forget" in kinds:
        if lang == "es":
            lines.append(
                "El usuario quiere que olvidas una instrucción previa. "
                "Confirma qué regla dejas de aplicar y no la sigas este turno."
            )
        else:
            lines.append(
                "The user wants you to drop a prior standing instruction. "
                "Confirm which rule you are clearing and do not apply it "
                "this turn."
            )

    saved = [h for h in hits if h.persist and h.value]
    if saved:
        if lang == "es":
            lines.append(
                "Acabas de recibir instrucción(es) permanentes — guárdalas "
                "mentalmente este turno y síguelas de inmediato: "
                + "; ".join(h.value for h in saved[:3] if h.value)
            )
        else:
            lines.append(
                "You just received standing instruction(s) — treat them as "
                "saved and follow them immediately: "
                + "; ".join(h.value for h in saved[:3] if h.value)
            )

    if not lines:
        return None

    header = (
        "STANDING / USER-COACHING — follow before you reply:"
        if lang != "es"
        else "INSTRUCCIONES / CORRECCIÓN DEL USUARIO — síguelas antes de responder:"
    )
    return header + "\n  • " + "\n  • ".join(lines)


async def persist_standing_hits(user_id: str, hits: list[StandingHit]) -> list[dict]:
    """Upsert durable hits via the existing save_user_memory path."""
    if not user_id or not hits:
        return []
    from backend.ai.tools import _save_user_memory

    saved: list[dict] = []
    for hit in hits:
        if not hit.persist or not hit.key or not hit.value:
            continue
        try:
            result = await _save_user_memory(
                user_id=str(user_id),
                key=hit.key,
                value=str(hit.value)[:500],
                confidence="high",
            )
            if result.get("saved"):
                saved.append({"key": hit.key, "value": hit.value})
        except Exception:
            continue
    return saved


async def sync_standing_instructions(
    user_id: str,
    message: str,
    *,
    memories: list[dict] | None = None,
    lang: str = "en",
) -> dict:
    """Detect → optionally persist → build this-turn reminder.

    Returns ``{"hits": [...], "saved": [...], "reminder": str|None}``.
    """
    hits = detect_standing_hits(message)
    saved = await persist_standing_hits(user_id, hits) if user_id else []
    reminder = build_standing_turn_reminder(
        hits, memories=memories, lang=lang,
    )
    # Even with no new hit text, durable verify_steps still needs a nudge
    # when the user asks a complex multi-step thing. Reminder builder handles
    # has_verify_pref when hits is empty only if we pass memories — also
    # fire a soft verify reminder when preference is on and message looks
    # action-y.
    if reminder is None and memories:
        if any(str(m.get("key") or "") == VERIFY_STEPS_KEY for m in memories):
            if _looks_like_action_request(message):
                reminder = build_standing_turn_reminder(
                    [StandingHit(
                        kind="verify", key=None, value=None,
                        persist=False, turn_only=True,
                    )],
                    memories=memories,
                    lang=lang,
                )
    return {
        "hits": hits,
        "saved": saved,
        "reminder": reminder,
    }


def _looks_like_action_request(message: str) -> bool:
    t = (message or "").lower()
    triggers = (
        "post", "share", "claim", "find", "search", "delete", "cancel",
        "update", "show", "map", "list", "publish", "reserve",
        "publica", "comparte", "busca", "reserva", "cancela", "elimina",
    )
    return any(w in t for w in triggers)


__all__ = [
    "ALWAYS_DO_PREFIX",
    "REMIND_PREFIX",
    "VERIFY_STEPS_KEY",
    "StandingHit",
    "build_standing_turn_reminder",
    "detect_standing_hits",
    "format_soft_preferences_block",
    "format_standing_memories_block",
    "is_standing_memory_key",
    "persist_standing_hits",
    "sync_standing_instructions",
]
