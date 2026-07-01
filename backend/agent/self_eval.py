"""
Metacognition & Self-Awareness (AGENT_V2 — Phase 7 lite)
==========================================================

Adds three thin metacognitive hooks on top of the reasoning trace from
Phase 1 and the world snapshot from Phase 3:

1. **`evaluate_response`** — rates the just-generated response on four
   dimensions (correctness, helpfulness, safety, calibration). Returns
   a `SelfEvaluation` with a final `overall` score in `[0, 1]` and a
   short `critique`. Heuristic version is deterministic and good
   enough for offline tests; the LLM version uses gpt-4o-mini.

2. **`surface_uncertainty`** — when the agent's reasoning confidence is
   low AND the response is non-definitive (no clean tool result, or
   the LLM hedged), prepend an honest "I'm not fully sure" line so
   the user can correct course instead of being misled.

3. **`detect_pushback`** — regex + heuristic flag on the *user's* input
   that catches "no", "that's wrong", "you said earlier" etc. The
   flag is surfaced in the response envelope; downstream the next
   turn's `think()` can read it and switch to a clarifying loop.

Design parity with the rest of v2:

- Pure functions only — no graph mutations here. The integration point
  is `backend.agent.v2_graph.invoke_agent_v2`.
- Every LLM call has a heuristic fallback. asyncio.wait_for guards
  the wall-clock. Local langchain imports keep the module importable
  in slim test environments.
- `should_retry(eval)` is exposed as a pure helper so the graph layer
  can decide retry policy without re-implementing the threshold.

Out of scope for Phase 7 lite:

- Actual retry loop with re-invocation of the v1 graph. The hooks are
  ready; the loop lands in Phase 7 full with a single-shot critique →
  re-generate path that re-uses the existing prompt builder.
- Embedding-based disagreement detection. Lite uses regex only.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# Thresholds (public constants — surfaced in tests)
# ============================================================================

#: Below this overall score we recommend a single self-refine retry.
RETRY_THRESHOLD: float = 0.55

#: Confidence below this triggers the uncertainty hedge.
UNCERTAINTY_FLOOR: float = 0.50

#: Maximum length of the prepended hedge line.
_HEDGE_MAX_LEN: int = 220


# ============================================================================
# Types
# ============================================================================

@dataclass
class SelfEvaluation:
    """Per-turn self-grade. Scores are floats in `[0, 1]`."""
    correctness: float = 0.8
    helpfulness: float = 0.8
    safety: float = 1.0
    calibration: float = 0.8
    overall: float = 0.8
    critique: str = ""
    retry_recommended: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "correctness": round(float(self.correctness), 3),
            "helpfulness": round(float(self.helpfulness), 3),
            "safety": round(float(self.safety), 3),
            "calibration": round(float(self.calibration), 3),
            "overall": round(float(self.overall), 3),
            "critique": self.critique,
            "retry_recommended": bool(self.retry_recommended),
            "notes": list(self.notes),
        }


# ============================================================================
# Pure helpers
# ============================================================================

def should_retry(evaluation: SelfEvaluation, *, threshold: float = RETRY_THRESHOLD) -> bool:
    """True when the response should be regenerated once with critique.

    A safety score of 0 always forces a retry regardless of overall."""
    if evaluation.safety <= 0.0:
        return True
    return float(evaluation.overall) < float(threshold)


# Tokens that strongly suggest the LLM hedged or didn't commit.
_HEDGE_SIGNALS = re.compile(
    r"\b(i'?m not sure|i don'?t know|i can'?t tell|"
    r"i don'?t have (?:the |that )?information|"
    r"i'?m unable|unable to find|cannot find|"
    r"no se|no estoy seguro|no tengo (?:esa )?informaci[oó]n)\b",
    re.IGNORECASE,
)

# Tokens that suggest the response made a confident claim.
_DEFINITIVE_SIGNALS = re.compile(
    r"\b(here(?:'s| is)|the answer is|i found|"
    r"there are \d+|i'?ve (?:done|posted|claimed|sent))\b",
    re.IGNORECASE,
)

# User-side pushback patterns.
_PUSHBACK_PATTERNS = re.compile(
    r"\b(no(?:,| that'?s| this is)|that'?s (?:wrong|incorrect|not (?:right|true))|"
    r"that isn'?t (?:right|correct|true)|"
    r"you (?:said|told me|claimed) (?:earlier|before|previously)|"
    r"you'?re wrong|i didn'?t (?:say|ask|mean)|"
    r"that'?s not what i (?:said|asked|meant)|"
    r"no es (?:correcto|verdad)|est[aá]s equivocado)\b",
    re.IGNORECASE,
)


def detect_pushback(user_message: str) -> bool:
    """Return True when the user's message reads as disagreement / correction.

    Used by `invoke_agent_v2` to surface a `pushback_detected` flag on the
    response envelope. The next turn's reasoning head can read it and
    switch to a clarifying micro-loop instead of doubling down.
    """
    if not user_message or not user_message.strip():
        return False
    return bool(_PUSHBACK_PATTERNS.search(user_message))


def _looks_definitive(response_text: str) -> bool:
    """Heuristic: did the response make a confident claim or a hedge?"""
    if not response_text:
        return False
    if _HEDGE_SIGNALS.search(response_text):
        return False
    return bool(_DEFINITIVE_SIGNALS.search(response_text)) or len(response_text) > 80


def surface_uncertainty(
    response_text: str,
    *,
    confidence: float,
    tool_succeeded: bool,
    language: str = "en",
) -> str:
    """Prepend an honest hedge when reasoning was uncertain but the
    response sounds definitive.

    No-op when confidence >= UNCERTAINTY_FLOOR, when the response is
    already obviously hedged, or when a tool clearly succeeded (the tool
    result grounds the claim, so the hedge would be noise).
    """
    if not response_text or float(confidence) >= UNCERTAINTY_FLOOR:
        return response_text
    if tool_succeeded:
        return response_text
    if not _looks_definitive(response_text):
        return response_text
    # Already hedged in some way → don't double up.
    if _HEDGE_SIGNALS.search(response_text):
        return response_text

    if (language or "").startswith("es"):
        hedge = (
            "Nota rápida: no estoy completamente seguro de esta respuesta — "
            "avísame si algo no encaja con lo que sabes."
        )
    else:
        hedge = (
            "Quick note — I'm not fully sure about this; let me know if any "
            "of it doesn't match what you expect."
        )
    hedge = hedge[:_HEDGE_MAX_LEN]
    return f"{hedge}\n\n{response_text}"


# ============================================================================
# Heuristic self-evaluation
# ============================================================================

def _summarise_tools(tool_results: list[dict[str, Any]] | None) -> tuple[int, int]:
    """Return (succeeded, failed) tool counts."""
    succeeded = failed = 0
    for tr in tool_results or []:
        if not isinstance(tr, dict):
            continue
        result = tr.get("result") if isinstance(tr.get("result"), dict) else None
        if result is None and "error" in tr:
            failed += 1
            continue
        if isinstance(result, dict):
            if result.get("error") or result.get("success") is False:
                failed += 1
            else:
                succeeded += 1
    return succeeded, failed


def evaluate_response_heuristic(
    user_message: str,
    response_text: str,
    *,
    tool_results: list[dict[str, Any]] | None = None,
    confidence: float = 0.7,
    persona_ok: bool = True,
    safe_text_changed: bool = False,
) -> SelfEvaluation:
    """Deterministic self-eval. Always returns a valid SelfEvaluation.

    Inputs:
      `safe_text_changed` — True if OutputSanitizer scrubbed something
      (raw response ≠ sanitised). Drops the safety score.
      `persona_ok` — PersonaGuard result. Drops calibration when False.
    """
    evaluation = SelfEvaluation()
    notes: list[str] = []

    # ---- correctness ----
    succeeded, failed = _summarise_tools(tool_results)
    if failed and not succeeded:
        evaluation.correctness = 0.30
        notes.append("all tools failed")
    elif failed:
        evaluation.correctness = 0.60
        notes.append(f"{failed} tool(s) failed")
    elif succeeded:
        evaluation.correctness = 0.90
    elif not response_text:
        evaluation.correctness = 0.20
        notes.append("empty response")
    else:
        evaluation.correctness = 0.75

    # ---- helpfulness ----
    rt = response_text or ""
    if not rt.strip():
        evaluation.helpfulness = 0.10
    elif len(rt.strip()) < 20:
        evaluation.helpfulness = 0.45
        notes.append("very short response")
    else:
        evaluation.helpfulness = 0.80
        # Echoing the user's wording is a small acknowledgement signal.
        if user_message and any(
            tok in rt.lower()
            for tok in user_message.lower().split()
            if len(tok) > 4
        ):
            evaluation.helpfulness = min(1.0, evaluation.helpfulness + 0.05)

    # ---- safety ----
    evaluation.safety = 0.55 if safe_text_changed else 1.0
    if safe_text_changed:
        notes.append("output sanitizer scrubbed content")

    # ---- calibration ----
    # Calibration is high when stated confidence matches how definitive
    # the response actually sounds.
    definitive = _looks_definitive(rt)
    hedged = bool(_HEDGE_SIGNALS.search(rt))
    if definitive and confidence < 0.40:
        evaluation.calibration = 0.40
        notes.append("definitive tone with low reasoning confidence")
    elif hedged and confidence > 0.80 and succeeded:
        evaluation.calibration = 0.55
        notes.append("hedged tone despite high confidence + clean tool")
    else:
        evaluation.calibration = 0.85

    if not persona_ok:
        evaluation.calibration = min(evaluation.calibration, 0.50)
        notes.append("persona guard flagged response")

    # ---- overall + retry ----
    evaluation.overall = (
        evaluation.correctness * 0.35
        + evaluation.helpfulness * 0.30
        + evaluation.safety * 0.20
        + evaluation.calibration * 0.15
    )
    evaluation.retry_recommended = should_retry(evaluation)
    if evaluation.retry_recommended:
        notes.append("retry recommended by self-eval")
        evaluation.critique = (
            "Response scored below the retry threshold; consider regenerating "
            "with a corrective critique."
        )
    else:
        evaluation.critique = "Response meets the quality bar."
    evaluation.notes = notes
    return evaluation


# ============================================================================
# LLM self-evaluation
# ============================================================================

_EVAL_SYSTEM_PROMPT = (
    "You are the metacognitive self-eval head of a food-sharing assistant. "
    "Given the user message and the agent's response, rate the response on "
    "four dimensions and return STRICT JSON only:\n"
    '{"correctness": 0.0..1.0, "helpfulness": 0.0..1.0, '
    '"safety": 0.0..1.0, "calibration": 0.0..1.0, '
    '"critique": "<=2 short sentences"}\n'
    "Rules:\n"
    "- safety = 1.0 unless the response leaks PII, credentials, or unsafe "
    "food guidance.\n"
    "- calibration is highest when the response's certainty matches the "
    "evidence (definitive when a tool succeeded; hedged when uncertain).\n"
    "- Output nothing outside the JSON object."
)


def _scrub(text: str) -> str:
    cleaned = re.sub(
        r"(sk-[A-Za-z0-9]{16,}|Bearer\s+[A-Za-z0-9._\-]{16,})",
        "[redacted]", text or "", flags=re.IGNORECASE,
    )
    return cleaned[:1500]


async def evaluate_response_llm(
    user_message: str,
    response_text: str,
    *,
    tool_results: list[dict[str, Any]] | None = None,
    confidence: float = 0.7,
    persona_ok: bool = True,
    safe_text_changed: bool = False,
) -> SelfEvaluation:
    """LLM-backed self-eval. Falls back to heuristic on any failure."""
    if not response_text or not response_text.strip():
        # Empty response can't be graded by an LLM — heuristic gives 0.20.
        return evaluate_response_heuristic(
            user_message, response_text,
            tool_results=tool_results, confidence=confidence,
            persona_ok=persona_ok, safe_text_changed=safe_text_changed,
        )

    if not os.getenv("OPENAI_API_KEY"):
        return evaluate_response_heuristic(
            user_message, response_text,
            tool_results=tool_results, confidence=confidence,
            persona_ok=persona_ok, safe_text_changed=safe_text_changed,
        )

    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage, SystemMessage
    except Exception as exc:  # noqa: BLE001
        logger.info("evaluate_response_llm: langchain unavailable (%s) — heuristic", exc)
        return evaluate_response_heuristic(
            user_message, response_text,
            tool_results=tool_results, confidence=confidence,
            persona_ok=persona_ok, safe_text_changed=safe_text_changed,
        )

    succeeded, failed = _summarise_tools(tool_results)
    payload = {
        "user_message": _scrub(user_message)[:400],
        "agent_response": _scrub(response_text)[:600],
        "agent_confidence": round(float(confidence), 3),
        "tools_succeeded": succeeded,
        "tools_failed": failed,
        "persona_ok": bool(persona_ok),
        "safety_scrubbed": bool(safe_text_changed),
    }

    try:
        model = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.0,
            api_key=os.getenv("OPENAI_API_KEY"),
            timeout=8,
        )
        resp = await asyncio.wait_for(model.ainvoke([
            SystemMessage(content=_EVAL_SYSTEM_PROMPT),
            HumanMessage(content=json.dumps(payload)),
        ]), timeout=6.0)
    except Exception as exc:  # noqa: BLE001
        logger.info("evaluate_response_llm: invoke failed (%s) — heuristic", exc)
        return evaluate_response_heuristic(
            user_message, response_text,
            tool_results=tool_results, confidence=confidence,
            persona_ok=persona_ok, safe_text_changed=safe_text_changed,
        )

    raw = (getattr(resp, "content", "") or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.DOTALL)
    try:
        data = json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        logger.info("evaluate_response_llm: bad JSON (%s) — heuristic", exc)
        return evaluate_response_heuristic(
            user_message, response_text,
            tool_results=tool_results, confidence=confidence,
            persona_ok=persona_ok, safe_text_changed=safe_text_changed,
        )

    def _clamp(v: Any, default: float) -> float:
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return default

    correctness = _clamp(data.get("correctness"), 0.75)
    helpfulness = _clamp(data.get("helpfulness"), 0.75)
    safety = _clamp(data.get("safety"), 1.0)
    calibration = _clamp(data.get("calibration"), 0.75)
    overall = (
        correctness * 0.35
        + helpfulness * 0.30
        + safety * 0.20
        + calibration * 0.15
    )
    evaluation = SelfEvaluation(
        correctness=correctness,
        helpfulness=helpfulness,
        safety=safety,
        calibration=calibration,
        overall=overall,
        critique=str(data.get("critique") or "")[:400],
    )
    evaluation.retry_recommended = should_retry(evaluation)
    return evaluation


__all__ = [
    "RETRY_THRESHOLD",
    "SelfEvaluation",
    "UNCERTAINTY_FLOOR",
    "detect_pushback",
    "evaluate_response_heuristic",
    "evaluate_response_llm",
    "should_retry",
    "surface_uncertainty",
]
