"""
Single-shot self-refine (AGENT_V2 — Phase 7 full).

Given a draft response that the metacognition layer flagged as below the
quality bar (`should_retry(self_eval) is True`), produce ONE improved
version, fed the critique from the prior self-eval.

Design rules (parity with the rest of v2):

- Pure functions; no graph mutations here. Integration point is
  `backend.agent.v2_graph.invoke_agent_v2` (step 6d, after self-eval).
- Every LLM call has a heuristic fallback. `asyncio.wait_for` guards
  wall-clock.
- Local langchain imports keep the module importable in slim test
  environments and offline CI.
- We DO NOT re-run the v1 graph or any tools — that's both expensive
  and a regression risk (multi-action turns would re-execute side-
  effecting writes). The refiner is a text-rewrite head only.

Out of scope (still future work):

- Multi-step refine (critique → refine → critique → refine ...).
  Single shot is the calibrated choice; more shots tends to drift.
- Retrying with new tool calls. If the original turn picked the wrong
  tool, that's a planner problem, not a generation problem.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------

_REFINE_MAX_LEN: int = 1800  # cap on input passed to the LLM
_REFINE_OUTPUT_MAX: int = 4000  # cap on returned text

# Confident openings the heuristic refiner softens when reasoning was uncertain.
_DEFINITIVE_OPENINGS = re.compile(
    r"^\s*(?:here(?:'s| is) the answer|the answer is|definitely|"
    r"absolutely|without (?:a )?doubt|i'?m certain|"
    r"aquí está la respuesta|sin duda|absolutamente)\b[:,]?\s*",
    re.IGNORECASE,
)


# ----------------------------------------------------------------------
# Heuristic refiner — deterministic, no network
# ----------------------------------------------------------------------

def refine_response_heuristic(
    user_message: str,
    original_response: str,
    critique: str,
    *,
    language: str = "en",
) -> str:
    """Best-effort text cleanup when the LLM is unavailable.

    Strategy:
    - Soften any leading definitive opener.
    - Prepend a short "let me clarify" lead-in (EN/ES) so the user can
      see the agent caught its own miss.
    - Append a single follow-up question to invite correction.

    The result is intentionally conservative: we never strip facts,
    never re-order the body, never reword sentences beyond the head.
    """
    text = (original_response or "").strip()
    if not text:
        # Empty input — return a calibrated apology so the response dict
        # still has something user-facing.
        if (language or "").startswith("es"):
            return (
                "Disculpa, no pude generar una respuesta clara. ¿Puedes "
                "darme un poco más de contexto sobre lo que necesitas?"
            )
        return (
            "Sorry — I wasn't able to put together a clear answer. Could "
            "you share a bit more context about what you need?"
        )

    # Strip an opening that asserts certainty so the softened lead-in
    # doesn't read as contradictory.
    text = _DEFINITIVE_OPENINGS.sub("", text, count=1).strip() or text

    if (language or "").startswith("es"):
        lead = "Déjame intentar de nuevo con más cuidado:"
        tail = "¿Esto se acerca a lo que buscas, o me corriges?"
    else:
        lead = "Let me try that again more carefully:"
        tail = "Does that match what you're looking for, or should I adjust?"

    refined = f"{lead}\n\n{text}\n\n{tail}"
    return refined[:_REFINE_OUTPUT_MAX]


# ----------------------------------------------------------------------
# LLM refiner — gpt-4o-mini
# ----------------------------------------------------------------------

_REFINE_SYSTEM_PROMPT = (
    "You are the self-refine head of a food-sharing assistant. The agent "
    "produced a draft response that its own self-eval flagged as below "
    "the quality bar. Produce ONE improved version that:\n"
    "- addresses the critique directly,\n"
    "- preserves any concrete facts / numbers / names from the draft,\n"
    "- never invents new tool results or claims an action was taken if "
    "the draft did not,\n"
    "- matches the user's language,\n"
    "- stays concise (no preamble like 'Here is the improved response').\n"
    "Return ONLY the refined response text — no JSON, no markdown fences, "
    "no apology meta-commentary."
)


def _scrub(text: str) -> str:
    cleaned = re.sub(
        r"(sk-[A-Za-z0-9]{16,}|Bearer\s+[A-Za-z0-9._\-]{16,})",
        "[redacted]", text or "", flags=re.IGNORECASE,
    )
    return cleaned[:_REFINE_MAX_LEN]


async def refine_response_llm(
    user_message: str,
    original_response: str,
    critique: str,
    *,
    language: str = "en",
) -> str:
    """LLM-backed refine. Falls back to heuristic on any failure."""
    if not original_response or not original_response.strip():
        return refine_response_heuristic(
            user_message, original_response, critique, language=language,
        )

    if not os.getenv("OPENAI_API_KEY"):
        return refine_response_heuristic(
            user_message, original_response, critique, language=language,
        )

    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage, SystemMessage
    except Exception as exc:  # noqa: BLE001
        logger.info("refine_response_llm: langchain unavailable (%s) — heuristic", exc)
        return refine_response_heuristic(
            user_message, original_response, critique, language=language,
        )

    user_payload = (
        f"User message ({language or 'en'}):\n{_scrub(user_message)}\n\n"
        f"Draft response:\n{_scrub(original_response)}\n\n"
        f"Self-eval critique:\n{_scrub(critique or 'response was below the quality bar')}"
    )

    try:
        model = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.2,
            api_key=os.getenv("OPENAI_API_KEY"),
            timeout=8,
        )
        resp = await asyncio.wait_for(model.ainvoke([
            SystemMessage(content=_REFINE_SYSTEM_PROMPT),
            HumanMessage(content=user_payload),
        ]), timeout=6.0)
    except Exception as exc:  # noqa: BLE001
        logger.info("refine_response_llm: invoke failed (%s) — heuristic", exc)
        return refine_response_heuristic(
            user_message, original_response, critique, language=language,
        )

    raw = (getattr(resp, "content", "") or "").strip()
    if not raw:
        return refine_response_heuristic(
            user_message, original_response, critique, language=language,
        )

    # Strip accidental fenced code wrappers.
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
        raw = re.sub(r"\n?```\s*$", "", raw)
        raw = raw.strip()

    return raw[:_REFINE_OUTPUT_MAX] or refine_response_heuristic(
        user_message, original_response, critique, language=language,
    )
