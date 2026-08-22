"""Metacognition / conscious layer for Nouri.

The rest of Nouri is stateless-per-turn: read the message + history,
call tools, emit a reply. That leaves a whole class of failure modes
invisible to the model:

  * asking the same question twice ("what community?" → user answered
    → the model asks again because it didn't reread history);
  * missing a correction ("no, I meant the OTHER apples") and doubling
    down on the wrong target;
  * declaring success in prose without a matching tool call
    (hallucination);
  * looping — same tool three turns in a row, no progress;
  * losing the user (short, terse, single-word replies indicate we're
    drifting);
  * pivoting flows silently (user was posting, now they're claiming —
    the reminder stack was still stuck on posting).

This module gives Nouri a small, deterministic **reflection layer**:
per-turn detection helpers that surface those signals as compact
system messages the model reads *before* generating its reply. It also
captures a lightweight post-turn reflection (was that turn productive?
was a claimed action actually taken?) that primes the next turn.

Non-breaking properties:

  * Pure functions where possible.
  * All wiring wraps ``try/except`` — a bug here can't take the turn
    down.
  * No tool schemas change, no argument coercion.
  * Silent by default — reminders only fire when a specific signal is
    actually present.
  * Per-user state kept in the same process-local dict pattern as
    ``_last_write_action_by_user`` in ``conversation_flow.py``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional


# ---------------------------------------------------------------------------
# Per-user reflection state
# ---------------------------------------------------------------------------


@dataclass
class ReflectionState:
    """Small rolling state for one user's session-in-memory.

    Kept intentionally small: we only need the last few tool-call
    outcomes (for loop detection) and the last reflection note (so it
    can prime the next turn).
    """

    # Most recent tool outcomes, newest last. Each item:
    #   {"tool": str, "ok": bool, "turn": int}
    recent_tool_outcomes: list[dict] = field(default_factory=list)
    # A compact free-text note the model should read next turn.
    last_reflection_note: str = ""
    # Turn counter, incremented every time chat_reply runs.
    turn_index: int = 0


_REFLECTION_BY_USER: dict[str, ReflectionState] = {}
_MAX_TOOL_OUTCOMES = 12


def get_reflection_state(user_id: str) -> ReflectionState:
    key = str(user_id or "")
    if key not in _REFLECTION_BY_USER:
        _REFLECTION_BY_USER[key] = ReflectionState()
    return _REFLECTION_BY_USER[key]


def reset_reflection_state(user_id: str) -> None:
    """Clear reflection state for a user — useful for tests."""
    _REFLECTION_BY_USER.pop(str(user_id or ""), None)


def record_tool_outcome(user_id: str, tool: str, ok: bool) -> None:
    """Store a tool call outcome for loop/streak detection."""
    state = get_reflection_state(user_id)
    state.recent_tool_outcomes.append({
        "tool": tool,
        "ok": bool(ok),
        "turn": state.turn_index,
    })
    if len(state.recent_tool_outcomes) > _MAX_TOOL_OUTCOMES:
        state.recent_tool_outcomes = state.recent_tool_outcomes[-_MAX_TOOL_OUTCOMES:]


def bump_turn(user_id: str) -> int:
    state = get_reflection_state(user_id)
    state.turn_index += 1
    return state.turn_index


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


_QUESTION_TAIL_RE = re.compile(r"([^?!.]{4,}?\?)")


def _last_assistant_messages(history: list | None, n: int = 6) -> list[str]:
    return [
        str(m.get("message") or "")
        for m in (history or [])[-n * 2 :]
        if m.get("role") == "assistant"
    ][-n:]


def _last_user_messages(history: list | None, n: int = 6) -> list[str]:
    return [
        str(m.get("message") or "")
        for m in (history or [])[-n * 2 :]
        if m.get("role") == "user"
    ][-n:]


def _extract_question(text: str) -> str:
    """Return the last question sentence in *text*, or "" if none."""
    if "?" not in (text or ""):
        return ""
    matches = _QUESTION_TAIL_RE.findall(text)
    if matches:
        return matches[-1].strip().lower()
    return ""


def _normalize_question(q: str) -> str:
    """Collapse punctuation/whitespace and drop filler for similarity."""
    q = (q or "").lower()
    q = re.sub(r"[^\w\s]", " ", q)
    q = re.sub(r"\s+", " ", q).strip()
    # Drop common polite-filler words that create false differences
    # between "hey, which community?" and "which community?".
    fillers = {"hey", "hi", "so", "just", "also", "and", "also,", "well",
               "please", "por favor", "hola"}
    return " ".join(w for w in q.split() if w not in fillers)


def _jaccard(a: str, b: str) -> float:
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------


def detect_repeated_assistant_question(
    history: list | None,
    similarity: float = 0.7,
) -> Optional[str]:
    """Detect the model asking the *same* question multiple recent turns.

    Returns the near-duplicate question text (normalized) or None. This
    is the biggest signal for 'the model didn't read history' or 'the
    user's answer got lost.'
    """
    assistants = _last_assistant_messages(history, n=6)
    questions = [_normalize_question(_extract_question(m)) for m in assistants]
    questions = [q for q in questions if q]
    if len(questions) < 2:
        return None
    for i in range(len(questions) - 1):
        for j in range(i + 1, len(questions)):
            if _jaccard(questions[i], questions[j]) >= similarity:
                return questions[i]
    return None


_CORRECTION_PATTERNS = (
    r"\bno,?\s+i\s+(?:meant|said|want|asked)\b",
    r"\bthat'?s?\s+not\s+what\b",
    r"\bactually,?\s+(?:i|the|it|no|let'?s|nope)\b",
    r"\bwait,?\s+",
    r"\bi\s+said\s+",
    r"\bnot\s+that\s+one\b",
    r"\bthe\s+other\s+",
    # Missed / incomplete action — user coaching the agent
    r"\byou\s+didn'?t\b",
    r"\byou\s+forgot\b",
    r"\byou\s+missed\b",
    r"\bwhy\s+didn'?t\s+you\b",
    r"\bi(?:'?m|\s+am)\s+not\s+seeing\b",
    r"\bi\s+don'?t\s+see\b",
    # Spanish
    r"\bno,?\s+(?:quise|me refería|es)\b",
    r"\bespera,?\s+",
    r"\ben realidad,?\s+",
    r"\bno era eso\b",
    r"\bno\s+(?:hiciste|mostraste|veo)\b",
    r"\bolvidaste\b",
)
_CORRECTION_RE = re.compile("|".join(_CORRECTION_PATTERNS), re.IGNORECASE)


def detect_user_correction(message: str) -> bool:
    """True when the user is correcting a misunderstanding.

    Correction signals ('no, I meant', 'actually', 'wait') should make
    Nouri STOP the current action, acknowledge, and re-read what the
    user actually wants — not double down on the misparse.
    """
    if not message:
        return False
    return bool(_CORRECTION_RE.search(message))


_FRUSTRATION_PATTERNS = (
    r"\byou\s+(?:keep|already)\s+(?:asked|asking|said)\b",
    r"\bi\s+(?:already|just)\s+(?:told|said|answered)\b",
    r"\bwhy\s+are\s+you\s+asking\b",
    r"\blisten,?\s+",
    r"\bcome\s+on\b",
    r"\bfor\s+the\s+(?:third|fourth|last)\s+time\b",
    # Spanish
    r"\bya\s+te\s+(?:dije|contesté|respondí)\b",
    r"\bpor\s+qué\s+me\s+preguntas\s+otra\s+vez\b",
    r"\bescucha,?\s+",
)
_FRUSTRATION_RE = re.compile("|".join(_FRUSTRATION_PATTERNS), re.IGNORECASE)


def detect_user_frustration(message: str) -> bool:
    """True when the user is expressing frustration or repeating themselves."""
    if not message:
        return False
    return bool(_FRUSTRATION_RE.search(message))


def detect_shortening_user_replies(history: list | None) -> bool:
    """Losing-the-user signal: last three user replies each under 3 words.

    Very short replies in sequence suggest the user is either giving
    yes/no answers or has disengaged. The model should proactively
    summarise + confirm rather than keep drilling questions.
    """
    users = _last_user_messages(history, n=4)
    if len(users) < 3:
        return False
    short = [u for u in users[-3:] if len(u.strip().split()) <= 2]
    return len(short) == 3


def detect_topic_pivot(message: str) -> bool:
    """True when the user is explicitly changing topic mid-flow."""
    if not message:
        return False
    text = message.lower()
    patterns = (
        "actually let", "instead of", "instead let", "changed my mind",
        "forget that", "never mind", "en lugar de", "cambié de opinión",
        "olvida eso", "mejor",
    )
    return any(p in text for p in patterns)


def detect_hallucinated_success(
    assistant_text: str,
    tool_actions: list | None,
) -> bool:
    """After a turn: assistant said 'Posted!' / 'Claimed!' but no
    corresponding successful tool call actually ran.

    This is the WORST failure mode — telling the user something
    happened when it didn't. We record it in the reflection state so
    the next turn's reminder can course-correct: "You claimed success
    last turn but no tool ran; be honest with the user this turn."
    """
    if not assistant_text:
        return False
    text = assistant_text.lower()
    claims = (
        "posted!", "posted your", "listing posted", "claimed!",
        "reserved!", "cancelled", "canceled!", "deleted",
        "updated!", "updated your", "removed", "published!",
        "publicado!", "reservado!", "cancelado!",
    )
    if not any(c in text for c in claims):
        return False
    actions = tool_actions or []
    ok_tools = {
        str(a.get("tool") or "")
        for a in actions
        if isinstance(a, dict) and a.get("ok")
    }
    write_tools = {
        "post_food_listing", "post_food_listings", "create_food_listing",
        "claim_listing", "claim_listings", "cancel_claim",
        "delete_listing", "deactivate_listing", "update_food_listing",
        "post_food_request", "update_food_request",
        "attach_photos_to_listing",
    }
    return not bool(ok_tools & write_tools)


def detect_tool_loop(user_id: str, min_calls: int = 3) -> Optional[str]:
    """Detect the same tool called 3+ times in the last 4 turns.

    Returns the tool name if a loop is detected. This is the signal to
    change strategy — broaden the search query, ask a clarifier, or
    escalate to a different tool.
    """
    state = get_reflection_state(user_id)
    outs = state.recent_tool_outcomes[-4:]
    if len(outs) < min_calls:
        return None
    counter: dict[str, int] = {}
    for o in outs:
        counter[o["tool"]] = counter.get(o["tool"], 0) + 1
    for tool, count in counter.items():
        if count >= min_calls:
            return tool
    return None


def recent_tool_failure_rate(user_id: str, window: int = 4) -> float:
    """Fraction of recent tool calls that returned an error.

    High failure rate → the model is guessing at args or picking the
    wrong tool. Reminder should encourage stepping back and asking.
    """
    state = get_reflection_state(user_id)
    outs = state.recent_tool_outcomes[-window:]
    if not outs:
        return 0.0
    fails = sum(1 for o in outs if not o["ok"])
    return fails / len(outs)


# ---------------------------------------------------------------------------
# Reflection assembly
# ---------------------------------------------------------------------------


@dataclass
class ReflectionSignals:
    """Structured summary of what the reflection layer noticed this turn."""

    repeated_question: Optional[str] = None
    user_corrected: bool = False
    user_frustrated: bool = False
    shortening_replies: bool = False
    topic_pivot: bool = False
    tool_loop: Optional[str] = None
    failure_rate: float = 0.0
    prior_note: str = ""

    def is_empty(self) -> bool:
        return not any((
            self.repeated_question,
            self.user_corrected,
            self.user_frustrated,
            self.shortening_replies,
            self.topic_pivot,
            self.tool_loop,
            self.failure_rate > 0.5,
            bool(self.prior_note),
        ))


def assess_turn(
    message: str,
    history: list | None,
    user_id: str = "",
) -> ReflectionSignals:
    """Run all detectors for the current turn and return a signals object."""
    state = get_reflection_state(user_id) if user_id else None
    return ReflectionSignals(
        repeated_question=detect_repeated_assistant_question(history),
        user_corrected=detect_user_correction(message),
        user_frustrated=detect_user_frustration(message),
        shortening_replies=detect_shortening_user_replies(history),
        topic_pivot=detect_topic_pivot(message),
        tool_loop=detect_tool_loop(user_id) if user_id else None,
        failure_rate=recent_tool_failure_rate(user_id) if user_id else 0.0,
        prior_note=(state.last_reflection_note if state else ""),
    )


# ---------------------------------------------------------------------------
# Prompt reminder builder
# ---------------------------------------------------------------------------


def _en_lines(sig: ReflectionSignals) -> list[str]:
    lines: list[str] = []
    if sig.repeated_question:
        lines.append(
            f"You asked '{sig.repeated_question[:80]}' more than once — the "
            "user's answer may be in an earlier turn. RE-READ history "
            "before asking again. Consider apologising ('sorry, I lost "
            "track — you said X?') instead of re-asking."
        )
    if sig.user_corrected:
        lines.append(
            "The user is CORRECTING you this turn ('no, I meant…' / "
            "'actually…'). Drop the previous target, apologise briefly, "
            "and re-parse from the correction — do NOT proceed with the "
            "misparse."
        )
    if sig.user_frustrated:
        lines.append(
            "The user sounds frustrated — they may be repeating themselves. "
            "Step back: acknowledge their last answer plainly, don't "
            "re-ask what they've already given, and move the conversation "
            "forward with the info you already have."
        )
    if sig.shortening_replies:
        lines.append(
            "The user's replies are getting terse (single words). You're "
            "losing them. Stop drilling — give a one-line recap of what "
            "you know + one clear next step, then wait."
        )
    if sig.topic_pivot:
        lines.append(
            "The user PIVOTED topic this turn. Abandon the previous flow "
            "state (no 'as we were saying' — that's noise). Follow the "
            "new intent from scratch."
        )
    if sig.tool_loop:
        lines.append(
            f"You've called '{sig.tool_loop}' 3+ times recently without "
            "progress. Change strategy: broaden the search query, ask a "
            "clarifier, or escalate to a different tool. Do NOT call it "
            "a fourth time with the same args."
        )
    if sig.failure_rate > 0.5:
        lines.append(
            f"Recent tool calls are failing at {int(sig.failure_rate * 100)}%. "
            "You're likely guessing args or picking the wrong tool. Stop "
            "and ask the user for the missing/ambiguous piece."
        )
    if sig.prior_note:
        lines.append(f"Note from your last turn: {sig.prior_note}")
    return lines


def _es_lines(sig: ReflectionSignals) -> list[str]:
    lines: list[str] = []
    if sig.repeated_question:
        lines.append(
            f"Ya preguntaste '{sig.repeated_question[:80]}' antes — la "
            "respuesta puede estar en un turno anterior. RELÉE la "
            "historia antes de volver a preguntar."
        )
    if sig.user_corrected:
        lines.append(
            "El usuario te está CORRIGIENDO ('no, quise decir…'). "
            "Suelta el objetivo anterior, discúlpate brevemente y "
            "re-interpreta desde la corrección."
        )
    if sig.user_frustrated:
        lines.append(
            "El usuario suena frustrado — probablemente se está "
            "repitiendo. Reconoce lo que ya dijo, no vuelvas a preguntar "
            "lo mismo, y avanza con la información disponible."
        )
    if sig.shortening_replies:
        lines.append(
            "Las respuestas del usuario son cada vez más cortas. Estás "
            "perdiendo su atención. Deja de preguntar y da un resumen "
            "breve + un siguiente paso claro."
        )
    if sig.topic_pivot:
        lines.append(
            "El usuario CAMBIÓ de tema. Abandona el flujo anterior y "
            "sigue la nueva intención sin arrastrar el estado previo."
        )
    if sig.tool_loop:
        lines.append(
            f"Llamaste '{sig.tool_loop}' 3+ veces sin progreso. Cambia "
            "estrategia: amplía radio, pide un aclarador o usa otra "
            "herramienta."
        )
    if sig.failure_rate > 0.5:
        lines.append(
            f"Las llamadas recientes fallan al {int(sig.failure_rate * 100)}%. "
            "Detente y pregunta al usuario por la pieza que falta."
        )
    if sig.prior_note:
        lines.append(f"Nota de tu turno anterior: {sig.prior_note}")
    return lines


def build_reflection_reminder(
    message: str,
    history: list | None,
    user_id: str = "",
    lang: str = "en",
) -> Optional[str]:
    """Return the compact reflection system-message for this turn, or None
    when there's nothing interesting to say.

    Silent-by-default: only fires when at least one detector triggered.
    The output is small (2-6 short lines) — the goal is to nudge the
    model, not to bury it in noise.
    """
    signals = assess_turn(message, history, user_id=user_id)
    if signals.is_empty():
        return None
    lines = _es_lines(signals) if lang == "es" else _en_lines(signals)
    if not lines:
        return None
    header = (
        "REFLECTION — self-check before you reply:"
        if lang != "es"
        else "REFLEXIÓN — auto-verificación antes de responder:"
    )
    return header + "\n  • " + "\n  • ".join(lines)


# ---------------------------------------------------------------------------
# Post-turn reflection capture
# ---------------------------------------------------------------------------


def capture_post_turn_reflection(
    user_id: str,
    assistant_text: str,
    tool_actions: Iterable[dict] | None,
) -> Optional[str]:
    """After the model finishes a turn, note anything worth remembering
    for the next one.

    Returns the note that got stored (or None). Notes are short —
    they'll appear inline in next turn's REFLECTION block, so anything
    over ~200 chars is trimmed.
    """
    actions_list = list(tool_actions or [])
    notes: list[str] = []

    if detect_hallucinated_success(assistant_text, actions_list):
        notes.append(
            "last turn you claimed an action succeeded without a tool "
            "call — be honest with the user this turn about what "
            "actually happened."
        )

    for act in actions_list:
        if not isinstance(act, dict):
            continue
        tool = str(act.get("tool") or "")
        if not tool or act.get("type"):
            continue  # skip reasoning chips etc.
        record_tool_outcome(user_id, tool, bool(act.get("ok")))

    note = "; ".join(notes)
    state = get_reflection_state(user_id)
    if note:
        state.last_reflection_note = note[:200]
    else:
        # Decay: clear old notes so they don't linger forever.
        state.last_reflection_note = ""
    return note or None


__all__ = [
    "ReflectionSignals",
    "ReflectionState",
    "assess_turn",
    "build_reflection_reminder",
    "bump_turn",
    "capture_post_turn_reflection",
    "detect_hallucinated_success",
    "detect_repeated_assistant_question",
    "detect_shortening_user_replies",
    "detect_tool_loop",
    "detect_topic_pivot",
    "detect_user_correction",
    "detect_user_frustration",
    "get_reflection_state",
    "record_tool_outcome",
    "recent_tool_failure_rate",
    "reset_reflection_state",
]
