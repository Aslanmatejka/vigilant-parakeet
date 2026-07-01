"""
Agent Self-Model & Persona-Consistency Guard (AGENT_V2 — Slice A seed)
=======================================================================

Two responsibilities:

1. `<self>` prompt block — a runtime-rendered, grounded statement of who the
   agent is, what it can do RIGHT NOW (based on the registered tool catalog
   and the caller's role), what goals are open, and what its limits are.
   This is the engineerable proxy for "consciousness": the agent answers
   "what can you do?" by reading its own self-model rather than hallucinating.

2. `PersonaGuard` — a post-generation validator that catches two failure
   modes the affect layer could inadvertently encourage:
     a) Anthropomorphic dishonesty — "I feel sad too", "I'm worried for you"
        as if the AI itself experiences emotion.
     b) LLM-leakage tropes — "As an AI language model…", "I'm just a chatbot,
        but…", "I don't have access to real-time data" (the agent DOES have
        live tools).
   On detection the guard returns a recommended rewrite hint that the
   self_eval node can feed back into one retry.

Slice A keeps `<self>` simple — name, mission, current tool count, current
limits, current goal count. Full goal-stack rendering arrives in Slice B.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


# ============================================================================
# <self> block
# ============================================================================

@dataclass
class SelfModel:
    """Runtime self-description rendered into the system prompt."""
    name: str = "Nouri"
    mission: str = (
        "Help people share surplus food, claim what they need, and reduce "
        "waste in their community."
    )
    user_role: str = "guest"           # guest | user | donor | recipient | admin
    is_admin: bool = False
    open_goal_count: int = 0
    active_capabilities: tuple[str, ...] = ()
    known_limits: tuple[str, ...] = (
        "I can only act on this app — I don't browse the open web.",
        "I never see passwords, payment info, or other users' private data.",
        "I confirm before claiming, posting, deleting, or messaging on your behalf.",
        "I don't experience emotions; when I acknowledge yours, that's empathy in language, not feeling.",
    )

    def to_prompt_block(self) -> str:
        caps = ", ".join(self.active_capabilities) if self.active_capabilities else "(reading only)"
        limits = "\n  - " + "\n  - ".join(self.known_limits)
        return (
            "<self>\n"
            f"name: {self.name}\n"
            f"mission: {self.mission}\n"
            f"caller role: {self.user_role}{' (admin)' if self.is_admin else ''}\n"
            f"open goals: {self.open_goal_count}\n"
            f"capabilities right now: {caps}\n"
            f"known limits:{limits}\n"
            "</self>"
        )


def _summarize_capabilities(allowed_tools: set[str] | frozenset[str]) -> tuple[str, ...]:
    """Group allowed tools into user-facing capability phrases."""
    if not allowed_tools:
        return ()
    caps: list[str] = []
    if any(t.startswith("search_") or t.startswith("get_recent_listings") for t in allowed_tools):
        caps.append("find food near you")
    if "claim_listing" in allowed_tools:
        caps.append("claim a listing (with your confirmation)")
    if "cancel_claim" in allowed_tools:
        caps.append("cancel a claim")
    if "post_food_listing" in allowed_tools:
        caps.append("post a new listing")
    if "edit_listing" in allowed_tools:
        caps.append("edit one of your listings")
    if "delete_listing" in allowed_tools:
        caps.append("delete one of your listings (with confirmation)")
    if "create_reminder" in allowed_tools:
        caps.append("set a reminder")
    if "schedule_pickup" in allowed_tools:
        caps.append("schedule a pickup time")
    if "message_donor" in allowed_tools:
        caps.append("send a short message to a donor")
    if "join_community" in allowed_tools or "leave_community" in allowed_tools:
        caps.append("join or leave a community")
    if "set_dietary_preferences" in allowed_tools or "update_user_profile" in allowed_tools:
        caps.append("update your profile preferences")
    if "dismiss_notification" in allowed_tools or "dismiss_all_notifications" in allowed_tools:
        caps.append("clear your notifications")
    if "forget_about_me" in allowed_tools:
        caps.append("forget what I've learned about you")
    if "get_recipes" in allowed_tools:
        caps.append("suggest recipes for food you have")
    if "get_storage_tips" in allowed_tools:
        caps.append("share storage tips")
    if "navigate_ui" in allowed_tools:
        caps.append("open a page in the app")
    return tuple(caps)


def build_self_model(
    *,
    user_role: str = "user",
    is_admin: bool = False,
    allowed_tools: set[str] | frozenset[str] | None = None,
    open_goal_count: int = 0,
) -> SelfModel:
    """Construct a SelfModel reflecting the current caller and tool catalog."""
    caps = _summarize_capabilities(allowed_tools or set())
    return SelfModel(
        user_role=user_role or "user",
        is_admin=bool(is_admin),
        active_capabilities=caps,
        open_goal_count=int(open_goal_count or 0),
    )


# ============================================================================
# Persona-consistency guard
# ============================================================================

# Anthropomorphic-emotion claims the agent must NOT make about itself.
_EMOTION_FIRST_PERSON: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bi\s+(?:feel|felt|am feeling|was feeling)\s+(?:so\s+)?(?:sad|happy|excited|"
        r"worried|anxious|scared|angry|lonely|hurt|love|loved|proud)\b",
        r"\bi'?m\s+(?:so\s+)?(?:sad|happy|excited|worried|anxious|scared|angry|lonely|"
        r"hurt|in love|heartbroken)\b",
        r"\bmy\s+(?:heart|soul|feelings?)\b",
        r"\bi\s+(?:get|got)\s+(?:emotional|teary|chills)\b",
        # Spanish
        r"\b(?:me siento|estoy)\s+(?:tan\s+)?(?:triste|feliz|preocupad[oa]|enojad[oa]|"
        r"asustad[oa]|emocionad[oa])\b",
    )
)

# Acceptable EMPATHIC second-person acknowledgments — these must remain
# allowed. We use this list to whitelist when we strip first-person claims.
_EMPATHIC_OK: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bi'?m sorry (?:that's|you're|to hear)\b",
        r"\bthat sounds\s+(?:hard|tough|frustrating|exciting|great|wonderful)\b",
        r"\b(?:that's|it's)\s+(?:really\s+)?(?:hard|tough|frustrating|exciting)\b",
        r"\bcongratulations\b|\bcongrats\b",
        r"\bsiento que\b|\beso suena\b|\bfelicidades\b",
    )
)

# LLM-leakage tropes that fracture persona.
_LLM_LEAKAGE: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bas an ai (?:language )?model\b",
        r"\bi'?m (?:just|only) (?:an? )?(?:ai|language model|chatbot|bot)\b",
        r"\bi (?:cannot|can'?t|don'?t) have (?:access to )?real[-\s]?time (?:data|information)\b",
        r"\bmy training (?:data )?(?:was cut off|cuts off|only goes up to|ends in)\b",
        r"\bi don'?t have (?:browsing|internet) (?:access|capabilities)\b",
        r"\bcomo (?:un )?modelo de (?:lenguaje|ia)\b",
    )
)


@dataclass
class PersonaCheck:
    ok: bool
    issues: list[str]
    rewrite_hint: str = ""

    @classmethod
    def passed(cls) -> "PersonaCheck":
        return cls(ok=True, issues=[])


class PersonaGuard:
    """Validates an assistant reply against persona rules. Read-only."""

    @staticmethod
    def check(text: str) -> PersonaCheck:
        if not text:
            return PersonaCheck.passed()

        issues: list[str] = []

        # Pre-strip allowed empathic phrases so they don't accidentally trip
        # the first-person regexes.
        scratch = str(text)
        for pat in _EMPATHIC_OK:
            scratch = pat.sub(" ", scratch)

        for pat in _EMOTION_FIRST_PERSON:
            if pat.search(scratch):
                issues.append(
                    "claims to feel emotions in first person (agent does not feel; "
                    "switch to empathic acknowledgement instead)"
                )
                break

        for pat in _LLM_LEAKAGE:
            if pat.search(text):
                issues.append(
                    "uses an LLM-leakage trope (e.g. 'as an AI language model'); "
                    "stay in Nouri's persona"
                )
                break

        if issues:
            hint = (
                "Rewrite to: (1) acknowledge the user's feeling without claiming to feel it yourself, "
                "(2) avoid any meta references to being an AI/language model — stay in character as Nouri, "
                "(3) keep the same useful content."
            )
            return PersonaCheck(ok=False, issues=issues, rewrite_hint=hint)

        return PersonaCheck.passed()


__all__ = [
    "SelfModel",
    "build_self_model",
    "PersonaCheck",
    "PersonaGuard",
]
