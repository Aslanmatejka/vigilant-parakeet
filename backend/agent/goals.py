"""
Goal Stack & Adaptive Planning (AGENT_V2 — Phase 2 lite)
==========================================================

Phase 1 (`reasoning.py`) lets the agent think about a *single* turn. Phase 2
adds a thin **goal stack**: every user message produces one or more typed
`Goal` objects (parent + optional children for compound asks), and the
reflection from Phase 1 grades the parent's outcome so the next turn can
resume an open goal instead of starting from scratch.

This module is intentionally lite for the first ship:

- **In-memory only.** Goals live on `AgentState.goals` for the duration of
  a turn. A future PR can persist them to an `agent_goals` Supabase table
  (migration sketched in `supabase/migrations/<TBD>_agent_goals.sql`) —
  the dataclass already mirrors that schema.
- **Pure functions + heuristic + LLM pair**, same shape as
  `reasoning.py`. Every LLM call has a deterministic fallback so unit
  tests stay green offline.
- **No graph mutations.** Integration point is
  `backend.agent.v2_graph.invoke_agent_v2`. v1 nodes are untouched.

Public API:

    Goal                                # dataclass
    GoalStatus = "open" | "in_progress" | "blocked" | "done" | "abandoned"
    GoalPriority = "low" | "normal" | "high" | "urgent"
    extract_goals_heuristic(message, user_id) -> list[Goal]
    extract_goals_llm(message, *, user_id, language) -> list[Goal]
    decompose_compound(message) -> list[str]
    prioritize_goals(goals) -> list[Goal]            # stable sort
    update_status_from_reflection(goals, reflection) -> list[Goal]
    replan_suggestion(thought, reflection) -> Optional[str]
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Literal, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# Types
# ============================================================================

GoalStatus = Literal["open", "in_progress", "blocked", "done", "abandoned"]
GoalPriority = Literal["low", "normal", "high", "urgent"]

#: Ordering used by `prioritize_goals` (lower index = handle first).
_PRIORITY_ORDER: dict[str, int] = {
    "urgent": 0, "high": 1, "normal": 2, "low": 3,
}


@dataclass
class Goal:
    """One unit of user intent the agent has committed to.

    The dataclass mirrors the eventual `agent_goals` Supabase row so the
    persistence layer can land later without changing any callers.
    """
    id: str
    user_id: str
    description: str
    intent: str = "chitchat"           # mirrors reasoning.Intent (str for forward-compat)
    status: GoalStatus = "open"
    priority: GoalPriority = "normal"
    parent_goal_id: Optional[str] = None
    success_criteria: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "description": self.description,
            "intent": self.intent,
            "status": self.status,
            "priority": self.priority,
            "parent_goal_id": self.parent_goal_id,
            "success_criteria": self.success_criteria,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "notes": list(self.notes),
        }

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc).isoformat()


# ============================================================================
# Heuristic extraction (no LLM, used as fallback + in tests)
# ============================================================================

#: Conjunctions we split on when decomposing a compound user message into
#: multiple goal-sized chunks. We deliberately keep this short — over-
#: aggressive splitting wrecks search-style messages like "rice and beans".
#: Hard delimiters (`;`, `&&`) don't require leading whitespace; soft
#: conjunctions (`and also`, `then`, `, and then`) do, so they don't fire
#: inside ingredient lists.
_COMPOUND_SPLITTERS = re.compile(
    r"\s*(?:;|&&)\s+"
    r"|\s+(?:and (?:also|then)|then|also,?|, then|, and then)\s+",
    re.IGNORECASE,
)

#: Words that signal a high-priority / time-sensitive ask.
_URGENT_TOKENS = re.compile(
    r"\b(urgent|asap|right now|emergency|today|tonight|need.*now|"
    r"urgente|ahora mismo|hoy|esta noche)\b",
    re.IGNORECASE,
)

_HIGH_TOKENS = re.compile(
    r"\b(soon|this week|tomorrow|priority|important|"
    r"pronto|esta semana|ma[nñ]ana|importante)\b",
    re.IGNORECASE,
)


def decompose_compound(message: str) -> list[str]:
    """Split a user message into separate goal candidates.

    Returns a list of at least one trimmed chunk. Empty input yields `[]`.
    We never split inside ingredient-list-style phrases (rice and beans);
    the splitter requires "AND ALSO/THEN" or a semicolon, not bare "and".
    """
    if not message or not message.strip():
        return []
    parts = [p.strip(" ,.;\n") for p in _COMPOUND_SPLITTERS.split(message)]
    return [p for p in parts if p]


def _priority_from_text(text: str) -> GoalPriority:
    if _URGENT_TOKENS.search(text):
        return "urgent"
    if _HIGH_TOKENS.search(text):
        return "high"
    return "normal"


def extract_goals_heuristic(
    message: str,
    user_id: str,
    *,
    parent_goal_id: Optional[str] = None,
) -> list[Goal]:
    """Pure-Python goal extractor.

    Strategy:
      1.  Decompose the message into clauses on AND-ALSO/THEN/semicolon.
      2.  Classify each clause's intent with `reasoning.classify_intent_heuristic`.
      3.  Pick a priority from urgency tokens.
      4.  Drop chitchat/meta clauses — they don't earn a goal slot.

    For a single-intent message you get exactly one Goal. For compound
    asks ("post my bread AND remind me Friday") you get one parent goal
    that wraps the original message plus one child goal per non-trivial
    clause, all sharing `parent_goal_id`.
    """
    # Local import to avoid a hard module-level dep cycle.
    from backend.agent.reasoning import classify_intent_heuristic

    raw = (message or "").strip()
    if not raw:
        return []

    chunks = decompose_compound(raw)
    if not chunks:
        return []

    # Treat the original message as the parent if we actually decomposed.
    is_compound = len(chunks) > 1
    parent: Optional[Goal] = None
    if is_compound and parent_goal_id is None:
        parent = Goal(
            id=str(uuid.uuid4()),
            user_id=user_id,
            description=raw[:280],
            intent="meta",           # compound wrapper; child intents carry real work
            status="open",
            priority=_priority_from_text(raw),
            parent_goal_id=None,
            success_criteria="all child goals completed",
        )

    out: list[Goal] = []
    for chunk in chunks:
        intent = classify_intent_heuristic(chunk)
        # chitchat/meta singletons still earn a goal so the trace is
        # complete, but on a compound message we drop them as children.
        if is_compound and intent in ("chitchat", "meta"):
            continue
        out.append(Goal(
            id=str(uuid.uuid4()),
            user_id=user_id,
            description=chunk[:280],
            intent=intent,
            status="open",
            priority=_priority_from_text(chunk),
            parent_goal_id=(parent.id if parent else parent_goal_id),
        ))

    if parent is not None:
        return [parent, *out]
    return out


# ============================================================================
# LLM extraction (gpt-4o-mini, strict-JSON, falls back to heuristic)
# ============================================================================

_EXTRACT_SYSTEM_PROMPT = (
    "You are the goal-extraction head of a food-sharing assistant. Read "
    "the user's message and return STRICT JSON only:\n"
    '{"goals": [{"description": "<verb-phrase>", '
    '"intent": "search|claim|donate|profile|support|chitchat|meta", '
    '"priority": "low|normal|high|urgent", '
    '"success_criteria": "<short phrase or null>"}]}\n'
    "Rules:\n"
    "- One goal per distinct user ask. Compound messages produce multiple.\n"
    "- Skip pure greetings (\"hi\", \"thanks\") — return an empty list.\n"
    "- Never invent goals the user didn't state.\n"
    "- Output nothing outside the JSON object."
)


def _scrub(text: str) -> str:
    """Drop obvious secrets and truncate for LLM input."""
    cleaned = re.sub(
        r"(sk-[A-Za-z0-9]{16,}|Bearer\s+[A-Za-z0-9._\-]{16,})",
        "[redacted]", text or "", flags=re.IGNORECASE,
    )
    return cleaned[:1500]


_VALID_INTENTS = {
    "search", "claim", "donate", "profile", "support", "chitchat", "meta",
}
_VALID_PRIORITIES = {"low", "normal", "high", "urgent"}


async def extract_goals_llm(
    message: str,
    *,
    user_id: str,
    language: str = "en",
) -> list[Goal]:
    """LLM goal extractor. Falls back to heuristic on any failure."""
    raw = (message or "").strip()
    if not raw:
        return []
    if not os.getenv("OPENAI_API_KEY"):
        return extract_goals_heuristic(raw, user_id)

    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage, SystemMessage
    except Exception as exc:  # noqa: BLE001
        logger.info("extract_goals_llm: langchain unavailable (%s) — heuristic", exc)
        return extract_goals_heuristic(raw, user_id)

    try:
        model = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.0,
            api_key=os.getenv("OPENAI_API_KEY"),
            timeout=8,
        )
        payload = f"[language={language}]\n{_scrub(raw)}"
        resp = await asyncio.wait_for(model.ainvoke([
            SystemMessage(content=_EXTRACT_SYSTEM_PROMPT),
            HumanMessage(content=payload),
        ]), timeout=6.0)
    except Exception as exc:  # noqa: BLE001
        logger.info("extract_goals_llm: invoke failed (%s) — heuristic", exc)
        return extract_goals_heuristic(raw, user_id)

    body = (getattr(resp, "content", "") or "").strip()
    if body.startswith("```"):
        body = re.sub(r"^```(?:json)?\s*|\s*```$", "", body, flags=re.DOTALL)
    try:
        data = json.loads(body)
    except Exception as exc:  # noqa: BLE001
        logger.info("extract_goals_llm: bad JSON (%s) — heuristic", exc)
        return extract_goals_heuristic(raw, user_id)

    items = data.get("goals") if isinstance(data, dict) else None
    if not isinstance(items, list) or not items:
        # LLM said "no goals" — respect that for greetings/etc.
        return []

    out: list[Goal] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        intent = str(it.get("intent") or "chitchat").strip().lower()
        if intent not in _VALID_INTENTS:
            intent = "chitchat"
        priority = str(it.get("priority") or "normal").strip().lower()
        if priority not in _VALID_PRIORITIES:
            priority = "normal"
        desc = str(it.get("description") or "").strip()[:280]
        if not desc:
            continue
        out.append(Goal(
            id=str(uuid.uuid4()),
            user_id=user_id,
            description=desc,
            intent=intent,
            priority=priority,  # type: ignore[arg-type]
            status="open",
            success_criteria=(
                str(it["success_criteria"])[:200]
                if it.get("success_criteria") else None
            ),
        ))
    # If LLM produced multiple, synthesise a parent wrapper for stable IDs.
    if len(out) >= 2:
        parent = Goal(
            id=str(uuid.uuid4()),
            user_id=user_id,
            description=raw[:280],
            intent="meta",
            priority=_priority_from_text(raw),
            success_criteria="all child goals completed",
        )
        for child in out:
            child.parent_goal_id = parent.id
        return [parent, *out]
    return out


# ============================================================================
# Prioritisation + status transitions
# ============================================================================

def prioritize_goals(goals: Iterable[Goal]) -> list[Goal]:
    """Return a stable-sorted copy: urgent → high → normal → low.

    Parents stay before their children. Goals at the same priority preserve
    their insertion order so reflection observations read naturally.
    """
    src = list(goals)
    # Mark parents to keep them ahead of their own children.
    parent_ids = {g.id for g in src if any(c.parent_goal_id == g.id for c in src)}
    def sort_key(g: Goal) -> tuple[int, int]:
        prio = _PRIORITY_ORDER.get(g.priority, 2)
        # Parents sort just ahead of their children at the same priority.
        return (prio, 0 if g.id in parent_ids else 1)
    return sorted(src, key=sort_key)


def update_status_from_reflection(
    goals: list[Goal],
    reflection_outcome: str,
    *,
    needs_retry: bool = False,
) -> list[Goal]:
    """Map a Phase 1 reflection outcome onto every open goal in this turn.

    Rules:
      - `success`  → status=done for every open/in_progress child goal.
      - `partial`  → first open child goes done; rest go in_progress.
      - `failed`   → status=blocked, needs_retry recorded as note.
      - `deferred` → status stays open; note recorded.
    Parents are graded after their children:
      - all children done   → parent done
      - any child blocked   → parent blocked
      - any child in_progress→ parent in_progress
      - otherwise           → unchanged
    """
    children = [g for g in goals if g.parent_goal_id is not None]
    parents = [g for g in goals if g.parent_goal_id is None]

    target = children if children else parents  # singleton case operates on parents

    if reflection_outcome == "success":
        for g in target:
            if g.status in ("open", "in_progress"):
                g.status = "done"
                g.touch()
    elif reflection_outcome == "partial":
        flipped = False
        for g in target:
            if g.status in ("open", "in_progress"):
                if not flipped:
                    g.status = "done"
                    flipped = True
                else:
                    g.status = "in_progress"
                g.touch()
    elif reflection_outcome == "failed":
        for g in target:
            if g.status in ("open", "in_progress"):
                g.status = "blocked"
                if needs_retry:
                    g.notes.append("reflection requested retry")
                g.touch()
    elif reflection_outcome == "deferred":
        for g in target:
            g.notes.append("deferred this turn")
            g.touch()

    # Reconcile parents only when this turn actually had children.
    if children:
        for parent in parents:
            kids = [g for g in children if g.parent_goal_id == parent.id]
            if not kids:
                continue
            statuses = {k.status for k in kids}
            if statuses == {"done"}:
                parent.status = "done"
            elif "blocked" in statuses:
                parent.status = "blocked"
            elif "in_progress" in statuses:
                parent.status = "in_progress"
            parent.touch()

    return goals


# ============================================================================
# Replan suggestion (Phase 2 lite — pure helper, no graph mutation)
# ============================================================================

def replan_suggestion(
    thought_next_action: str,
    reflection_outcome: str,
    *,
    needs_retry: bool,
    intent: str,
) -> Optional[str]:
    """Return a short hint about what the agent should try next.

    The actual `replan` graph node arrives in a later phase; for now we
    surface a `next_step` string on the response envelope so the
    frontend can show it as a "Try this next" affordance and the next
    turn's `think()` can read it as context.
    """
    if not needs_retry and reflection_outcome == "success":
        return None
    if reflection_outcome == "failed":
        if intent in ("search",):
            return "Ask the user to broaden the search criteria (location, dietary, or freshness)."
        if intent in ("claim", "donate"):
            return "Re-fetch the listing state and confirm with the user before retrying the write."
        if intent == "profile":
            return "Confirm the field the user wants to change before retrying the profile update."
        return "Ask the user to clarify their request, then retry with the updated information."
    if reflection_outcome == "deferred":
        if thought_next_action == "use_tool":
            return "The tool did not fire — confirm the request and try again next turn."
        return "Continue the conversation; no tool action was required this turn."
    if reflection_outcome == "partial":
        return "Surface what worked and ask the user how to handle the remaining piece."
    return None


__all__ = [
    "Goal",
    "GoalPriority",
    "GoalStatus",
    "decompose_compound",
    "extract_goals_heuristic",
    "extract_goals_llm",
    "prioritize_goals",
    "replan_suggestion",
    "update_status_from_reflection",
]
