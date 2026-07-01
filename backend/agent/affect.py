"""
Affective Communication Layer (AGENT_V2 — Slice A, lite)
=========================================================

A tiny module that:

1. **Classifies inbound affect** — sentiment, urgency, frustration, joy —
   from the user's current message. Uses a cheap LLM call (gpt-4o-mini) with
   strict JSON output. Falls back to a deterministic keyword heuristic when
   the LLM is unavailable (circuit breaker open, no key, etc.) so the agent
   stays usable in degraded mode.

2. **Selects a communication register** — `tone`, `verbosity`, `formality` —
   based on the classified affect and a few lightweight user-style hints
   (their average message length, whether they prefer Spanish, voice vs.
   text channel). The register is injected into the system prompt at
   generation time.

3. **Enforces honesty about emotion** — the persona-consistency guard
   (in `self_model.py`) catches any reply that claims the agent itself
   feels emotion ("I feel sad too"). Affect SHAPES the register but never
   licenses anthropomorphic dishonesty.

Out of scope for Slice A:
- Long-term affect history (Slice B/Phase 6).
- Cross-turn affect smoothing (Slice C).
- Voice-tone modulation in the TTS layer (the existing TTS uses Nova voice
  uniformly; future work).
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Literal

logger = logging.getLogger(__name__)

Tone = Literal["warm", "deescalating", "celebratory", "neutral", "energetic", "supportive"]
Verbosity = Literal["concise", "balanced", "detailed"]
Formality = Literal["casual", "neutral", "formal"]


# ============================================================================
# Affect classification
# ============================================================================

@dataclass
class Affect:
    """Inbound user-message affect snapshot.

    All scalar fields are in [0, 1]. `dominant` is the strongest single
    signal — used to pick a register quickly without weighing all four.
    """
    sentiment: float = 0.0       # 0 = very negative, 1 = very positive, 0.5 = neutral
    urgency: float = 0.0         # 0 = none, 1 = emergency-level
    frustration: float = 0.0
    joy: float = 0.0
    confusion: float = 0.0       # high when user seems lost / re-asking
    dominant: str = "neutral"

    @classmethod
    def neutral(cls) -> "Affect":
        return cls(sentiment=0.5, dominant="neutral")

    def to_dict(self) -> dict[str, Any]:
        return {
            "sentiment": self.sentiment,
            "urgency": self.urgency,
            "frustration": self.frustration,
            "joy": self.joy,
            "confusion": self.confusion,
            "dominant": self.dominant,
        }


# Deterministic keyword fallback. Conservative — only fires for very clear
# signals so the LLM-classified path remains primary in production.
_KEYWORDS_FRUSTRATION = re.compile(
    r"\b(angry|annoyed|frustrat\w*|pissed|fed up|stupid|useless|broken|"
    r"not working|doesn'?t work|why won'?t|i hate|terrible|awful|"
    r"enojad\w*|frustr\w*|harto|no funciona|por qu[eé] no)\b",
    re.IGNORECASE,
)
_KEYWORDS_URGENCY = re.compile(
    r"\b(urgent|asap|right now|immediately|hurry|quickly|emergency|"
    r"urgente|ya|ahora mismo|r[aá]pido|emergencia)\b",
    re.IGNORECASE,
)
_KEYWORDS_JOY = re.compile(
    r"\b(thanks?|thank you|awesome|great|love it|amazing|wonderful|"
    r"gracias|excelente|genial|me encanta|maravilloso)\b",
    re.IGNORECASE,
)
_KEYWORDS_CONFUSION = re.compile(
    r"\b(what do you mean|i don'?t understand|confused|lost|how do i|"
    r"no entiendo|no s[eé] c[oó]mo|c[oó]mo (puedo|hago))\b",
    re.IGNORECASE,
)


def classify_affect_heuristic(text: str) -> Affect:
    """Deterministic fallback classifier. Never raises.

    Used when:
    - OPENAI_API_KEY is missing
    - the LLM call is rate-limited / circuit-broken
    - we're in tests / offline
    """
    if not text or not str(text).strip():
        return Affect.neutral()
    s = str(text)
    frustration = 0.85 if _KEYWORDS_FRUSTRATION.search(s) else 0.0
    urgency = 0.8 if _KEYWORDS_URGENCY.search(s) else 0.0
    joy = 0.75 if _KEYWORDS_JOY.search(s) else 0.0
    confusion = 0.7 if _KEYWORDS_CONFUSION.search(s) else 0.0

    sentiment = 0.5
    if frustration > 0:
        sentiment = min(sentiment, 0.2)
    if joy > 0:
        sentiment = max(sentiment, 0.85)

    # Pick the dominant signal — prefer frustration > urgency > confusion > joy.
    dominant = "neutral"
    for label, val in (
        ("frustration", frustration), ("urgency", urgency),
        ("confusion", confusion), ("joy", joy),
    ):
        if val >= 0.6:
            dominant = label
            break

    return Affect(
        sentiment=sentiment,
        urgency=urgency,
        frustration=frustration,
        joy=joy,
        confusion=confusion,
        dominant=dominant,
    )


_AFFECT_SYSTEM_PROMPT = (
    "You are an affect classifier. Read the user message and return strict JSON "
    "with sentiment, urgency, frustration, joy, confusion each in [0,1], plus "
    "dominant in {neutral, frustration, urgency, joy, confusion, sadness}. "
    "Do NOT include any other text."
)


async def classify_affect_llm(text: str) -> Affect:
    """LLM-backed classifier. Uses gpt-4o-mini for cost. Falls back to the
    heuristic on any failure so the calling node never breaks.
    """
    if not text or not str(text).strip():
        return Affect.neutral()
    if not os.getenv("OPENAI_API_KEY"):
        return classify_affect_heuristic(text)

    try:
        # Local import — keep this module importable without langchain at
        # test time.
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage, SystemMessage

        model = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.0,
            api_key=os.getenv("OPENAI_API_KEY"),
            timeout=8,
        )
        resp = await model.ainvoke([
            SystemMessage(content=_AFFECT_SYSTEM_PROMPT),
            HumanMessage(content=str(text)[:1500]),
        ])
        raw = (resp.content or "").strip()
        # Strip code fences if present.
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.DOTALL)
        data = json.loads(raw)
        return Affect(
            sentiment=float(data.get("sentiment", 0.5)),
            urgency=float(data.get("urgency", 0.0)),
            frustration=float(data.get("frustration", 0.0)),
            joy=float(data.get("joy", 0.0)),
            confusion=float(data.get("confusion", 0.0)),
            dominant=str(data.get("dominant", "neutral")),
        )
    except Exception as exc:  # noqa: BLE001
        logger.info("affect LLM classify failed (%s) — falling back to heuristic", exc)
        return classify_affect_heuristic(text)


# ============================================================================
# Register selection
# ============================================================================

@dataclass
class Register:
    """Communication register: how the agent should sound this turn.

    Injected into the system prompt as a `<affect>` block. The generator must
    obey these without claiming to feel.
    """
    tone: Tone = "warm"
    verbosity: Verbosity = "balanced"
    formality: Formality = "neutral"
    acknowledgement_required: bool = True
    notes: list[str] = field(default_factory=list)

    def to_prompt_block(self) -> str:
        notes = ""
        if self.notes:
            notes = "\n- " + "\n- ".join(self.notes)
        return (
            "<affect>\n"
            f"tone: {self.tone}\n"
            f"verbosity: {self.verbosity}\n"
            f"formality: {self.formality}\n"
            f"acknowledge user intent first: {'yes' if self.acknowledgement_required else 'no'}"
            f"{notes}\n"
            "</affect>"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "tone": self.tone,
            "verbosity": self.verbosity,
            "formality": self.formality,
            "acknowledgement_required": self.acknowledgement_required,
            "notes": list(self.notes),
        }


def select_register(
    affect: Affect,
    *,
    channel: str = "text",          # "text" | "voice"
    user_avg_message_len: int | None = None,
) -> Register:
    """Pick a register based on classified affect + channel + user style.

    Slice A keeps the rules simple and explainable; later phases may learn
    per-user adjustments from trajectories.
    """
    # Voice answers are always shorter than text.
    base_verbosity: Verbosity = "concise" if channel == "voice" else "balanced"

    # Frustration → deescalating + concise + warm acknowledgement first.
    if affect.frustration >= 0.6:
        return Register(
            tone="deescalating",
            verbosity="concise",
            formality="neutral",
            acknowledgement_required=True,
            notes=[
                "User is frustrated. Acknowledge that explicitly without claiming to feel emotions.",
                "Be brief and offer one concrete next step.",
                "Avoid emojis.",
            ],
        )

    # Urgency → concise + neutral, lead with the action.
    if affect.urgency >= 0.6:
        return Register(
            tone="neutral",
            verbosity="concise",
            formality="neutral",
            acknowledgement_required=True,
            notes=[
                "User signaled urgency. Lead with the action; skip preamble.",
            ],
        )

    # Confusion → supportive + slightly more detailed, ask one clarifying question.
    if affect.confusion >= 0.6:
        return Register(
            tone="supportive",
            verbosity="balanced",
            formality="neutral",
            acknowledgement_required=True,
            notes=[
                "User seems confused. Ask one clarifying question if intent is unclear.",
                "Use plain language; avoid jargon.",
            ],
        )

    # Joy → celebratory, short.
    if affect.joy >= 0.6:
        return Register(
            tone="celebratory",
            verbosity="concise",
            formality="casual",
            acknowledgement_required=True,
            notes=["Match the user's positive energy briefly; don't overdo it."],
        )

    # Default — warm and balanced. Tighten verbosity for habitually short users.
    verb: Verbosity = base_verbosity
    if user_avg_message_len is not None and user_avg_message_len < 40:
        verb = "concise"
    return Register(
        tone="warm",
        verbosity=verb,
        formality="neutral",
        acknowledgement_required=True,
        notes=[],
    )


__all__ = [
    "Affect",
    "Register",
    "classify_affect_llm",
    "classify_affect_heuristic",
    "select_register",
]
