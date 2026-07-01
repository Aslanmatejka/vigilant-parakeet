"""Confirmation policy (Phase 4 mid) — centralized per-turn decision module
for whether a tool call should require explicit user confirmation.

The action framework (`backend/agent/actions.py`) already supports both an
inline confirmation default per `ActionSpec` and a per-request override via
`ActionRequest.requires_confirmation`. What's missing is a *centralized
policy layer* that decides whether to override the spec default based on
the live turn signal (intent classification, reasoning confidence, args
shape). This module IS that layer.

Two main entry points:

    decide_for_intent(intent, confidence)
        Pre-execution. Pure intent-level call. Used by v2_graph to decide
        whether to short-circuit *before* invoking v1 (future work).

    evaluate_tool_results(intent, confidence, tool_results)
        Post-execution. Walks the v1 tool trace and emits one
        `ConfirmationDecision` per writeable tool call. Used by v2_graph
        for observability — surfaces whether a destructive write was just
        executed so the frontend can show an undo banner.

This module is pure / synchronous / no IO. Tests feed in synthetic data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional


# ============================================================================
# Policy constants
# ============================================================================

#: Reasoning confidence below this floor flips a mutating tool into "confirm".
CONFIRM_CONFIDENCE_FLOOR: float = 0.75

#: Tools that are destructive or impossible to roll back — always confirm.
_DESTRUCTIVE_TOOLS: frozenset[str] = frozenset({
    "delete_listing",
    "cancel_claim",
    "dismiss_all_notifications",
    "forget_about_me",
})

#: Tools that mutate user-facing state. Confirm when confidence is low OR
#: when args indicate a high-impact change (handled per-tool below).
_MUTATING_TOOLS: frozenset[str] = frozenset({
    "claim_listing",
    "post_food_listing",
    "create_food_listing",
    "update_food_listing",
    "edit_listing",
    "deactivate_listing",
    "update_user_profile",
    "set_dietary_preferences",
})

#: Tools whose effect is trivially undoable from the UI — never auto-confirm.
_LOW_IMPACT_TOOLS: frozenset[str] = frozenset({
    "send_notification",
    "mark_notifications_read",
    "dismiss_notification",
    "create_reminder",
})

#: Intents that imply a destructive action even when no tool call has fired
#: yet. Used by `decide_for_intent` for pre-execution gating.
_DESTRUCTIVE_INTENTS: frozenset[str] = frozenset({
    "delete_listing",
    "cancel_claim",
    "leave_community",
    "forget_about_me",
})

#: Intents that imply a non-destructive write. Confirm only when confidence
#: is below the floor.
_MUTATING_INTENTS: frozenset[str] = frozenset({
    "claim_food",
    "share_food",
    "donate",
    "donate_food",
    "schedule_pickup",
    "join_community",
    "update_profile",
    "set_dietary_preferences",
    "edit_listing",
})

#: Decision "kinds" — semantic tag for the reason a confirm is required.
_KIND_DESTRUCTIVE = "destructive"
_KIND_LOW_CONFIDENCE = "low_confidence"
_KIND_HIGH_IMPACT = "high_impact"
_KIND_NONE = "none"

# Tunable: args quantity beyond which a claim is considered "bulk".
_BULK_QUANTITY_THRESHOLD: int = 5


# ============================================================================
# Data classes
# ============================================================================

@dataclass
class ConfirmationDecision:
    """The policy verdict for a single (intent, tool, args, confidence) tuple."""
    required: bool
    kind: str                       # one of the _KIND_* tags above
    reason_en: str
    reason_es: str
    tool: Optional[str] = None
    intent: Optional[str] = None
    confidence: Optional[float] = None
    args_snapshot: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "required": bool(self.required),
            "kind": str(self.kind),
            "reason_en": str(self.reason_en),
            "reason_es": str(self.reason_es),
            "tool": self.tool,
            "intent": self.intent,
            "confidence": (
                round(float(self.confidence), 3) if self.confidence is not None else None
            ),
            "args_snapshot": dict(self.args_snapshot),
        }


# ============================================================================
# Pure helpers
# ============================================================================

def _norm(value: Optional[str]) -> str:
    return (value or "").strip()


def _is_bulk_claim(tool_name: str, args: dict[str, Any] | None) -> bool:
    """Heuristic: claim of N>5 items is high-impact, deserves confirm."""
    if tool_name not in {"claim_listing", "create_food_claim"}:
        return False
    if not args:
        return False
    qty = args.get("quantity") or args.get("count") or args.get("qty")
    try:
        return int(qty) > _BULK_QUANTITY_THRESHOLD
    except (TypeError, ValueError):
        return False


def _is_address_change(tool_name: str, args: dict[str, Any] | None) -> bool:
    """Profile update that changes the user's stored address is high-impact."""
    if tool_name not in {"update_user_profile", "edit_listing", "update_food_listing"}:
        return False
    if not args:
        return False
    return any(k in args for k in ("address", "location", "coordinates", "lat", "lng"))


# ============================================================================
# Public decision API
# ============================================================================

def decide_for_intent(
    intent: Optional[str],
    confidence: Optional[float],
) -> ConfirmationDecision:
    """Pre-execution intent-level decision.

    Returns required=False for read-only / unknown intents so callers
    can safely default to "no gate" when in doubt.
    """
    intent_n = _norm(intent)
    if not intent_n:
        return ConfirmationDecision(
            required=False,
            kind=_KIND_NONE,
            reason_en="No actionable intent classified.",
            reason_es="Sin intent accionable clasificado.",
            intent=intent_n or None,
            confidence=confidence,
        )

    if intent_n in _DESTRUCTIVE_INTENTS:
        return ConfirmationDecision(
            required=True,
            kind=_KIND_DESTRUCTIVE,
            reason_en=f"Intent `{intent_n}` is destructive — always confirm.",
            reason_es=f"El intent `{intent_n}` es destructivo — siempre confirmar.",
            intent=intent_n,
            confidence=confidence,
        )

    if intent_n in _MUTATING_INTENTS:
        conf = float(confidence) if confidence is not None else 0.0
        if conf < CONFIRM_CONFIDENCE_FLOOR:
            return ConfirmationDecision(
                required=True,
                kind=_KIND_LOW_CONFIDENCE,
                reason_en=(
                    f"Mutating intent `{intent_n}` with low confidence "
                    f"({conf:.2f} < {CONFIRM_CONFIDENCE_FLOOR:.2f})."
                ),
                reason_es=(
                    f"Intent mutador `{intent_n}` con baja confianza "
                    f"({conf:.2f} < {CONFIRM_CONFIDENCE_FLOOR:.2f})."
                ),
                intent=intent_n,
                confidence=conf,
            )
        return ConfirmationDecision(
            required=False,
            kind=_KIND_NONE,
            reason_en=(
                f"Mutating intent `{intent_n}` with adequate confidence "
                f"({conf:.2f}); confirmation not required."
            ),
            reason_es=(
                f"Intent mutador `{intent_n}` con confianza adecuada "
                f"({conf:.2f}); no requiere confirmación."
            ),
            intent=intent_n,
            confidence=conf,
        )

    # Non-mutating intent (search, navigate, help, general, ...).
    return ConfirmationDecision(
        required=False,
        kind=_KIND_NONE,
        reason_en=f"Intent `{intent_n}` is read-only.",
        reason_es=f"El intent `{intent_n}` es de solo lectura.",
        intent=intent_n,
        confidence=confidence,
    )


def decide_for_tool_call(
    *,
    intent: Optional[str],
    tool_name: Optional[str],
    confidence: Optional[float],
    args: dict[str, Any] | None = None,
) -> ConfirmationDecision:
    """Decision for a single concrete tool call.

    Order of precedence:
      1. Destructive tool → always confirm.
      2. High-impact args → confirm.
      3. Mutating tool + low confidence → confirm.
      4. Otherwise → no confirm.
    """
    tool_n = _norm(tool_name)
    intent_n = _norm(intent)
    args_snap = dict(args) if isinstance(args, dict) else {}

    if not tool_n:
        return ConfirmationDecision(
            required=False,
            kind=_KIND_NONE,
            reason_en="No tool to evaluate.",
            reason_es="No hay herramienta que evaluar.",
            tool=None,
            intent=intent_n or None,
            confidence=confidence,
            args_snapshot=args_snap,
        )

    if tool_n in _DESTRUCTIVE_TOOLS:
        return ConfirmationDecision(
            required=True,
            kind=_KIND_DESTRUCTIVE,
            reason_en=f"Tool `{tool_n}` is destructive — always confirm.",
            reason_es=f"La herramienta `{tool_n}` es destructiva — siempre confirmar.",
            tool=tool_n,
            intent=intent_n or None,
            confidence=confidence,
            args_snapshot=args_snap,
        )

    if _is_bulk_claim(tool_n, args_snap):
        return ConfirmationDecision(
            required=True,
            kind=_KIND_HIGH_IMPACT,
            reason_en=(
                f"Bulk claim via `{tool_n}` (quantity > {_BULK_QUANTITY_THRESHOLD}) "
                f"is high-impact — confirm."
            ),
            reason_es=(
                f"Reclamo en masa vía `{tool_n}` (cantidad > {_BULK_QUANTITY_THRESHOLD}) "
                f"es de alto impacto — confirmar."
            ),
            tool=tool_n,
            intent=intent_n or None,
            confidence=confidence,
            args_snapshot=args_snap,
        )

    if _is_address_change(tool_n, args_snap):
        return ConfirmationDecision(
            required=True,
            kind=_KIND_HIGH_IMPACT,
            reason_en=(
                f"Tool `{tool_n}` is changing address/location — confirm."
            ),
            reason_es=(
                f"La herramienta `{tool_n}` está cambiando "
                "dirección/ubicación — confirmar."
            ),
            tool=tool_n,
            intent=intent_n or None,
            confidence=confidence,
            args_snapshot=args_snap,
        )

    if tool_n in _MUTATING_TOOLS:
        conf = float(confidence) if confidence is not None else 0.0
        if conf < CONFIRM_CONFIDENCE_FLOOR:
            return ConfirmationDecision(
                required=True,
                kind=_KIND_LOW_CONFIDENCE,
                reason_en=(
                    f"Mutating tool `{tool_n}` with low confidence "
                    f"({conf:.2f} < {CONFIRM_CONFIDENCE_FLOOR:.2f})."
                ),
                reason_es=(
                    f"Herramienta mutadora `{tool_n}` con baja confianza "
                    f"({conf:.2f} < {CONFIRM_CONFIDENCE_FLOOR:.2f})."
                ),
                tool=tool_n,
                intent=intent_n or None,
                confidence=conf,
                args_snapshot=args_snap,
            )
        return ConfirmationDecision(
            required=False,
            kind=_KIND_NONE,
            reason_en=(
                f"Mutating tool `{tool_n}` ran with adequate confidence "
                f"({conf:.2f})."
            ),
            reason_es=(
                f"La herramienta mutadora `{tool_n}` corrió con confianza "
                f"adecuada ({conf:.2f})."
            ),
            tool=tool_n,
            intent=intent_n or None,
            confidence=conf,
            args_snapshot=args_snap,
        )

    # Low-impact or unknown tool — never auto-flag.
    return ConfirmationDecision(
        required=False,
        kind=_KIND_NONE,
        reason_en=f"Tool `{tool_n}` is low-impact or non-mutating.",
        reason_es=f"La herramienta `{tool_n}` es de bajo impacto o no mutadora.",
        tool=tool_n,
        intent=intent_n or None,
        confidence=confidence,
        args_snapshot=args_snap,
    )


def evaluate_tool_results(
    *,
    intent: Optional[str],
    confidence: Optional[float],
    tool_results: Iterable[Any] | None,
) -> list[ConfirmationDecision]:
    """Apply `decide_for_tool_call` to every dict-shaped entry in tool_results.

    Returns a list (possibly empty) of decisions, one per tool call.
    Skips malformed entries silently — observability must never crash.
    """
    out: list[ConfirmationDecision] = []
    if not tool_results:
        return out
    for tr in tool_results:
        if not isinstance(tr, dict):
            continue
        tool_name = tr.get("tool") or tr.get("name")
        args = tr.get("args") if isinstance(tr.get("args"), dict) else None
        out.append(decide_for_tool_call(
            intent=intent,
            tool_name=str(tool_name) if tool_name else None,
            confidence=confidence,
            args=args,
        ))
    return out


def any_confirmation_required(
    decisions: Iterable[ConfirmationDecision] | None,
) -> bool:
    """True iff any decision in the list says required=True."""
    if not decisions:
        return False
    return any(getattr(d, "required", False) for d in decisions if isinstance(d, ConfirmationDecision))


def format_decision_summary(
    decisions: Iterable[ConfirmationDecision] | None,
    *,
    language: str = "en",
) -> str:
    """Render a single human-readable line summarising required confirmations.

    Returns "" when nothing requires confirmation. Used by the v2_graph
    response so the frontend can show a single banner instead of N rows.
    """
    if not decisions:
        return ""
    flagged = [d for d in decisions if isinstance(d, ConfirmationDecision) and d.required]
    if not flagged:
        return ""
    lang = "es" if language == "es" else "en"
    if lang == "es":
        head = "Confirmación recomendada: "
        tools = ", ".join(f"`{d.tool}`" for d in flagged if d.tool)
        if not tools:
            return head + "operación de alto impacto en este turno."
        return head + tools + "."
    head = "Confirmation recommended: "
    tools = ", ".join(f"`{d.tool}`" for d in flagged if d.tool)
    if not tools:
        return head + "high-impact operation on this turn."
    return head + tools + "."


__all__ = [
    "CONFIRM_CONFIDENCE_FLOOR",
    "ConfirmationDecision",
    "decide_for_intent",
    "decide_for_tool_call",
    "evaluate_tool_results",
    "any_confirmation_required",
    "format_decision_summary",
]
