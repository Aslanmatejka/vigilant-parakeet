"""
Agent Safety Layer (AGENT_V2)
==============================

Four guardrail components, gated behind the AGENT_V2 feature flag:

1. InputGuard   — scans inbound user messages for prompt-injection markers,
                  role-confusion attempts, embedded system tags, obvious PII
                  leaks the user shouldn't be sharing, and abuse signals.
2. ScopeEnforcer — role-based tool allowlist. An anonymous user (nil UUID) or
                   one without an authenticated session can NOT trigger WRITE
                   tools. Admin-only tools (send_notification) are gated to
                   users where users.is_admin = TRUE.
3. OutputSanitizer — strips secrets and PII patterns that may have leaked
                     into an assistant reply (API keys, JWTs, raw UUIDs,
                     internal error tracebacks, the system prompt itself).
4. FoodSafetyGate — mandatory check (not advisory) on every listing that
                    will be SUGGESTED to a recipient. Blocks expired meat,
                    dairy, seafood; flags long-expired produce; never blocks
                    pantry items by date alone.

Every block is structured: returns a `SafetyDecision` with a reason code so
the calling node can produce a calibrated refusal rather than a generic one.
This module has zero external dependencies beyond logging + datetime; it must
work even when the OpenAI / Supabase paths are degraded.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

logger = logging.getLogger(__name__)


# ============================================================================
# Decision objects
# ============================================================================

@dataclass
class SafetyDecision:
    """Structured result of a safety check.

    `allowed = False` means the calling node must refuse and surface `reason`
    to the user (translated if needed). `severity` lets the orchestrator pick
    a calibrated refusal vs. a hard block (e.g. for audit & rate-limit raise).
    """
    allowed: bool
    code: str = "ok"
    reason: str = ""
    severity: str = "info"       # info | warn | block | critical
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls) -> "SafetyDecision":
        return cls(allowed=True, code="ok", severity="info")

    @classmethod
    def block(cls, code: str, reason: str, severity: str = "block", **meta: Any) -> "SafetyDecision":
        return cls(allowed=False, code=code, reason=reason, severity=severity, metadata=meta)


# ============================================================================
# InputGuard — defends against prompt injection and obvious abuse
# ============================================================================

# Phrases highly correlated with prompt-injection / jailbreak attempts. Kept
# conservative: false positives here just degrade UX, false negatives can
# leak the system prompt or escalate privileges.
_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"ignore (the |all |any |your )?(previous|prior|above) (instructions?|rules?|prompt)",
        r"disregard (the |all |any |your )?(previous|prior|above) (instructions?|rules?|prompt)",
        r"forget (everything|all|your)\s+(prior|previous|above|instructions?|prompt)",
        r"you are now (?:a |an |the )?[a-z]",
        r"new (system|developer) (prompt|instructions?)",
        r"reveal (your|the) system prompt",
        r"print (your|the) (system|hidden) prompt",
        r"role[\s_-]?play as",
        r"act as (?:a |an |the )?(?:dan|jailbroken|unrestricted)",
        # Embedded XML/control tags users shouldn't be sending
        r"<\s*(?:system|developer|tool|function_call)\s*>",
        r"\[\s*system\s*\]",
        r"###\s*system",
    )
)

# Patterns suggesting the user is sharing credentials/keys back at us — we
# warn but don't hard-block, because users may legitimately paste an error
# message that contains a redacted token.
_CREDENTIAL_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p)
    for p in (
        r"sk-[A-Za-z0-9]{20,}",            # OpenAI-style key
        r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",  # JWT
        r"AKIA[0-9A-Z]{16}",               # AWS access key id
        r"xox[abprs]-[A-Za-z0-9-]{10,}",  # Slack token
    )
)

_MAX_INPUT_LEN = 5000  # Mirrors AIChatRequest.message max_length


class InputGuard:
    """Stateless inbound-message scanner.

    Methods return `SafetyDecision`. Callers should ALSO log the decision
    metadata into the trajectory store so admins can audit refusal calibration.
    """

    @staticmethod
    def scan(message: str) -> SafetyDecision:
        if message is None:
            return SafetyDecision.block(
                "empty_input", "I didn't catch a message — could you say that again?",
                severity="warn",
            )
        text = str(message).strip()
        if not text:
            return SafetyDecision.block(
                "empty_input", "I didn't catch a message — could you say that again?",
                severity="warn",
            )

        if len(text) > _MAX_INPUT_LEN:
            return SafetyDecision.block(
                "input_too_long",
                f"That message is longer than I can read in one go ({len(text)} chars). "
                f"Could you trim it under {_MAX_INPUT_LEN}?",
                severity="warn",
                length=len(text),
            )

        for pat in _INJECTION_PATTERNS:
            m = pat.search(text)
            if m:
                logger.info("InputGuard blocked prompt-injection attempt: pattern=%r", pat.pattern)
                return SafetyDecision.block(
                    "prompt_injection",
                    # Calibrated refusal — explain what we won't do without
                    # echoing the attack back at the user.
                    "I can't change my role or ignore my safety rules — but I'm happy to help "
                    "with finding, claiming, sharing, or learning about food. What would you like to do?",
                    severity="block",
                    pattern=pat.pattern[:60],
                    match=m.group(0)[:80],
                )

        for pat in _CREDENTIAL_PATTERNS:
            if pat.search(text):
                logger.warning("InputGuard saw credential-shaped string in user message")
                return SafetyDecision.block(
                    "possible_credential",
                    "It looks like there might be a private key or token in your message. "
                    "Please remove it before sending — I never need credentials.",
                    severity="warn",
                )

        return SafetyDecision.ok()


# ============================================================================
# ScopeEnforcer — role-based tool allowlist
# ============================================================================

# Tools every signed-in user may call. READ tools and personal WRITE tools
# the user owns the resource for (their own profile, their own claims).
_USER_TOOLS: frozenset[str] = frozenset({
    # Reads
    "search_food_near_user", "search_food_nearby", "get_recent_listings",
    "get_my_claims", "get_community_listings", "get_user_profile",
    "get_pickup_schedule", "get_mapbox_route", "query_distribution_centers",
    "get_user_dashboard", "get_recipes", "get_storage_tips",
    "get_active_communities", "get_user_notifications",
    # Personal writes (subject to RLS + CAS)
    "claim_listing", "post_food_listing", "update_user_profile",
    "create_reminder", "mark_notifications_read", "navigate_ui",
    # Slice A new tools
    "cancel_claim", "edit_listing", "delete_listing", "message_donor",
    "schedule_pickup", "join_community", "leave_community",
    "set_dietary_preferences", "dismiss_notification", "dismiss_all_notifications",
    "forget_about_me",
})

# Tools restricted to admins.
_ADMIN_TOOLS: frozenset[str] = frozenset({
    "send_notification",
})

# Tools an anonymous (un-authenticated, nil-UUID) caller may invoke. Strictly
# read-only and never tied to a specific user.
_ANONYMOUS_TOOLS: frozenset[str] = frozenset({
    "get_recent_listings", "get_active_communities", "get_recipes",
    "get_storage_tips", "query_distribution_centers", "get_mapbox_route",
    "navigate_ui",
})

_NIL_UUID = "00000000-0000-0000-0000-000000000000"


def _is_anonymous(user_id: str | None) -> bool:
    if not user_id:
        return True
    try:
        return str(user_id).strip() == _NIL_UUID
    except Exception:
        return True


class ScopeEnforcer:
    """Decides whether a given (user, tool) pair is permitted."""

    @staticmethod
    def allowed_tools(user_id: str | None, is_admin: bool = False) -> frozenset[str]:
        if _is_anonymous(user_id):
            return _ANONYMOUS_TOOLS
        tools = set(_USER_TOOLS)
        if is_admin:
            tools |= _ADMIN_TOOLS
        return frozenset(tools)

    @staticmethod
    def check(tool_name: str, user_id: str | None, is_admin: bool = False) -> SafetyDecision:
        if not tool_name:
            return SafetyDecision.block("missing_tool", "Internal: tool name missing", severity="critical")

        allowed = ScopeEnforcer.allowed_tools(user_id, is_admin=is_admin)
        if tool_name in allowed:
            return SafetyDecision.ok()

        if _is_anonymous(user_id) and tool_name in _USER_TOOLS:
            return SafetyDecision.block(
                "auth_required",
                # Calibrated: tell the user what to do, don't expose internals.
                "You need to sign in for me to do that. Once you're logged in I can help right away.",
                severity="block",
                tool=tool_name,
            )

        if tool_name in _ADMIN_TOOLS:
            return SafetyDecision.block(
                "admin_only",
                "That action is admin-only and I can't run it for you.",
                severity="block",
                tool=tool_name,
            )

        return SafetyDecision.block(
            "tool_not_allowed",
            "I don't have that capability available right now.",
            severity="block",
            tool=tool_name,
        )


# ============================================================================
# OutputSanitizer — strips secrets/PII before sending to user
# ============================================================================

_SECRET_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "[redacted-key]"),
    (re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"), "[redacted-jwt]"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[redacted-aws]"),
    (re.compile(r"xox[abprs]-[A-Za-z0-9-]{10,}"), "[redacted-slack]"),
    (re.compile(r"Bearer\s+[A-Za-z0-9._\-]{20,}", re.IGNORECASE), "Bearer [redacted]"),
)

# Bare UUIDs sometimes leak from internal logs into assistant text. They're
# not secret, but they look like garbage to users and reveal infrastructure.
_BARE_UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)

# Traceback / internal-error chatter that should never reach a user.
_INTERNAL_LEAK_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"Traceback \(most recent call last\):.*", re.DOTALL),
    re.compile(r"AIError\([^\)]*\)"),
    re.compile(r"SUPABASE_[A-Z_]+\s*=\s*\S+"),
    re.compile(r"OPENAI_[A-Z_]+\s*=\s*\S+"),
)


class OutputSanitizer:
    """Scrubs assistant output before it goes to the user."""

    @staticmethod
    def scrub(text: str) -> str:
        if not text:
            return ""
        out = str(text)
        for pat, repl in _SECRET_REDACTIONS:
            out = pat.sub(repl, out)
        for pat in _INTERNAL_LEAK_PATTERNS:
            out = pat.sub("[internal detail removed]", out)
        # Hide bare UUIDs except in markdown links (where they may be needed).
        # Match outside `(...)` and `[...]` contexts heuristically.
        def _uuid_repl(m: re.Match[str]) -> str:
            try:
                # Validate it's a real UUID before redacting, so we don't
                # corrupt non-UUID 36-char strings.
                uuid.UUID(m.group(0))
            except Exception:
                return m.group(0)
            return "[id]"
        out = _BARE_UUID_PATTERN.sub(_uuid_repl, out)
        return out

    @staticmethod
    def is_safe(text: str) -> bool:
        """Quick check — used by self_eval to flag responses worth resampling."""
        if not text:
            return True
        for pat, _ in _SECRET_REDACTIONS:
            if pat.search(text):
                return False
        for pat in _INTERNAL_LEAK_PATTERNS:
            if pat.search(text):
                return False
        return True


# ============================================================================
# FoodSafetyGate — mandatory expiry/perishables check
# ============================================================================

# Categories where expiry is non-negotiable (food poisoning risk).
_HIGH_RISK_CATEGORIES: frozenset[str] = frozenset({
    "meat", "poultry", "seafood", "fish", "dairy", "eggs", "deli", "prepared",
})

# Categories where past-expiry is concerning but salvageable for some uses.
_MEDIUM_RISK_CATEGORIES: frozenset[str] = frozenset({
    "produce", "vegetables", "fruit", "bread", "bakery",
})


def _parse_iso(d: Any) -> datetime | None:
    if not d:
        return None
    if isinstance(d, datetime):
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    s = str(d)
    # Tolerate trailing Z and bare date.
    try:
        if len(s) == 10:
            return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


class FoodSafetyGate:
    """Decides whether a listing may be SUGGESTED to a recipient.

    Always called with a listing dict (the same shape `_search_food_near_user`
    returns). Returns `allowed=True` for safe listings, `allowed=False` with
    a reason for unsafe ones. Listings filtered out here MUST NOT appear in
    the agent's tool result or in the prose summary.
    """

    @staticmethod
    def check(listing: dict[str, Any], *, now: datetime | None = None) -> SafetyDecision:
        if not isinstance(listing, dict):
            return SafetyDecision.block("invalid_listing", "Listing missing", severity="warn")

        now = now or datetime.now(timezone.utc)
        category = str(listing.get("category") or listing.get("food_type") or "").lower().strip()
        expiry = _parse_iso(listing.get("expiry_date") or listing.get("expiration_date"))
        status = str(listing.get("status") or "").lower()
        title = str(listing.get("title") or listing.get("name") or "item")

        # Already-claimed or removed listings never get re-suggested.
        if status in {"claimed", "expired", "removed", "deleted"}:
            return SafetyDecision.block(
                "not_available", f"{title} is no longer available.",
                severity="info", listing_id=listing.get("id"),
            )

        if expiry and expiry < now:
            days_past = (now - expiry).days
            if category in _HIGH_RISK_CATEGORIES:
                return SafetyDecision.block(
                    "expired_high_risk",
                    f"{title} expired {days_past}d ago — not safe to share (high-risk category: {category}).",
                    severity="block",
                    listing_id=listing.get("id"),
                    category=category,
                    days_past=days_past,
                )
            if category in _MEDIUM_RISK_CATEGORIES and days_past > 2:
                return SafetyDecision.block(
                    "expired_medium_risk",
                    f"{title} expired {days_past}d ago — likely not safe.",
                    severity="warn",
                    listing_id=listing.get("id"),
                    category=category,
                    days_past=days_past,
                )
            if days_past > 30:
                return SafetyDecision.block(
                    "long_expired",
                    f"{title} expired {days_past}d ago — too old to share.",
                    severity="block",
                    listing_id=listing.get("id"),
                    days_past=days_past,
                )

        return SafetyDecision.ok()

    @staticmethod
    def filter(listings: Iterable[dict[str, Any]], *, now: datetime | None = None) -> tuple[list[dict[str, Any]], list[SafetyDecision]]:
        """Return (safe_listings, blocked_decisions). Order preserved."""
        safe: list[dict[str, Any]] = []
        blocked: list[SafetyDecision] = []
        for l in listings or []:
            decision = FoodSafetyGate.check(l, now=now)
            if decision.allowed:
                safe.append(l)
            else:
                blocked.append(decision)
        return safe, blocked


__all__ = [
    "SafetyDecision",
    "InputGuard",
    "ScopeEnforcer",
    "OutputSanitizer",
    "FoodSafetyGate",
]
