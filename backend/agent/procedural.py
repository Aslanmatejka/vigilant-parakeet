"""Procedural memory miner (Phase 6 mid) — heuristic, no embeddings.

Mines repeating (intent, action) patterns from past successful trajectories
and emits `ProceduralRule` recommendations. v2_graph consults the miner
when planning a turn and injects the best matching rule into the prompt
context block so gpt-4o sees a learned "you've done well at X by doing Y"
hint instead of just a few-shot list.

This module is pure and synchronous except for the optional async
`fetch_recent_trajectories` helper which mirrors `adaptation.retrieve_similar_trajectories`
for Supabase. The miner itself accepts any iterable of `TrajectoryRecord`,
so tests feed in synthetic lists.

Design rules:
  - No new schema; relies on the existing `agent_trajectories` table.
  - Graceful failure: any Supabase error → empty list.
  - Rules are scored composite (support × mean_reward × success_rate) and
    sorted DESC. Caller picks the best rule for current intent.
  - Deterministic for a given input list — easy to unit-test.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from backend.agent.adaptation import TrajectoryRecord

logger = logging.getLogger(__name__)

# Tunable thresholds — public so tests can override.
MIN_SUPPORT: int = 2          # at least N trajectories per (intent, action)
MIN_REWARD: float = 0.6       # mean reward must clear this
MIN_SUCCESS_RATE: float = 0.6 # fraction of trajectories with outcome="success"
MAX_RULES: int = 20           # cap output size
_NIL_UUID = "00000000-0000-0000-0000-000000000000"
_FETCH_SCAN_CAP: int = 200

# Anti-pattern thresholds (Phase 6 extension). A pair becomes an
# `AntiPatternRule` when the user has tried it >= ANTIPATTERN_MIN_SUPPORT
# times and either the mean reward is low OR the failure rate is high.
ANTIPATTERN_MIN_SUPPORT: int = 2
ANTIPATTERN_MAX_REWARD: float = 0.3      # mean reward must stay AT OR BELOW this
ANTIPATTERN_MIN_FAILURE_RATE: float = 0.5  # failure rate must clear this
ANTIPATTERN_MAX_RULES: int = 10


@dataclass
class ProceduralRule:
    """One learned (intent, action) → success pattern.

    `confidence` is a composite score in [0, 1]:
        clamp(mean_reward) * success_rate * support_weight
    where support_weight = min(support_count / 5, 1.0) — so the rule
    only gets credit for being broadly attested.
    """
    intent: str
    action: str
    support_count: int
    mean_reward: float
    mean_confidence: float
    success_rate: float
    confidence: float
    sample_summaries: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "action": self.action,
            "support_count": int(self.support_count),
            "mean_reward": round(float(self.mean_reward), 3),
            "mean_confidence": round(float(self.mean_confidence), 3),
            "success_rate": round(float(self.success_rate), 3),
            "confidence": round(float(self.confidence), 3),
            "sample_summaries": list(self.sample_summaries),
        }


@dataclass
class AntiPatternRule:
    """One learned (intent, action) → failure pattern.

    `severity` is a composite score in [0, 1] indicating how strongly to
    AVOID this action for this intent. Computed as:
        (1 - max(0, mean_reward)) * failure_rate * support_weight
    where support_weight = min(support_count / 5, 1.0). High severity
    means "the user has tried this several times and it consistently
    fails".
    """
    intent: str
    action: str
    support_count: int
    mean_reward: float
    mean_confidence: float
    failure_rate: float
    success_rate: float
    severity: float
    sample_summaries: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "action": self.action,
            "support_count": int(self.support_count),
            "mean_reward": round(float(self.mean_reward), 3),
            "mean_confidence": round(float(self.mean_confidence), 3),
            "failure_rate": round(float(self.failure_rate), 3),
            "success_rate": round(float(self.success_rate), 3),
            "severity": round(float(self.severity), 3),
            "sample_summaries": list(self.sample_summaries),
        }


def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return float(x)


def mine_procedural_rules(
    trajectories: Iterable[TrajectoryRecord] | None,
    *,
    min_support: int = MIN_SUPPORT,
    min_reward: float = MIN_REWARD,
    min_success_rate: float = MIN_SUCCESS_RATE,
    max_rules: int = MAX_RULES,
) -> list[ProceduralRule]:
    """Group trajectories by (intent, action) and emit qualifying rules.

    Filters:
      - Skip entries without intent or action.
      - Group must have >= min_support rows.
      - Group mean_reward >= min_reward.
      - Group success_rate >= min_success_rate.

    Returns rules sorted by composite confidence DESC, capped at max_rules.
    """
    if not trajectories:
        return []

    groups: dict[tuple[str, str], list[TrajectoryRecord]] = {}
    for t in trajectories:
        if not isinstance(t, TrajectoryRecord):
            continue
        intent = (t.intent or "").strip()
        action = (t.action or "").strip()
        if not intent or not action:
            continue
        groups.setdefault((intent, action), []).append(t)

    rules: list[ProceduralRule] = []
    for (intent, action), items in groups.items():
        n = len(items)
        if n < int(min_support):
            continue
        mean_reward = sum(float(t.reward) for t in items) / n
        if mean_reward < float(min_reward):
            continue
        successes = sum(1 for t in items if (t.outcome or "").strip() == "success")
        success_rate = successes / n
        if success_rate < float(min_success_rate):
            continue
        mean_confidence = sum(float(t.confidence) for t in items) / n
        support_weight = min(n / 5.0, 1.0)
        composite = _clamp01(mean_reward) * success_rate * support_weight

        # Pull up to 2 short summaries for explainability.
        samples: list[str] = []
        for t in sorted(items, key=lambda r: float(r.reward), reverse=True):
            s = (t.message_summary or "").strip()
            if s and s not in samples:
                samples.append(s)
            if len(samples) >= 2:
                break

        rules.append(ProceduralRule(
            intent=intent,
            action=action,
            support_count=n,
            mean_reward=mean_reward,
            mean_confidence=mean_confidence,
            success_rate=success_rate,
            confidence=composite,
            sample_summaries=samples,
        ))

    rules.sort(key=lambda r: r.confidence, reverse=True)
    return rules[: max(0, int(max_rules))]


def select_rule_for_intent(
    rules: Iterable[ProceduralRule] | None,
    intent: str,
) -> Optional[ProceduralRule]:
    """Return the highest-confidence rule whose intent matches, or None."""
    if not rules or not intent:
        return None
    target = intent.strip()
    if not target:
        return None
    best: Optional[ProceduralRule] = None
    for r in rules:
        if not isinstance(r, ProceduralRule):
            continue
        if r.intent != target:
            continue
        if best is None or r.confidence > best.confidence:
            best = r
    return best


_HINT_TEMPLATES = {
    "en": (
        "Procedural hint: in {n} past turn(s) for intent `{intent}`, you "
        "succeeded by calling `{action}` (mean reward {reward:.2f}, "
        "{success}% success). Prefer that path if it still fits."
    ),
    "es": (
        "Pista procedimental: en {n} turno(s) pasado(s) con intent "
        "`{intent}`, tuviste éxito al usar `{action}` (recompensa media "
        "{reward:.2f}, {success}% éxito). Prefiérelo si encaja."
    ),
}


def format_procedural_hint(
    rule: Optional[ProceduralRule],
    *,
    language: str = "en",
) -> str:
    """Render a one-line prompt hint for the given rule. Empty if no rule."""
    if rule is None or not isinstance(rule, ProceduralRule):
        return ""
    lang = "es" if language == "es" else "en"
    tmpl = _HINT_TEMPLATES[lang]
    return tmpl.format(
        n=int(rule.support_count),
        intent=rule.intent,
        action=rule.action,
        reward=float(rule.mean_reward),
        success=int(round(rule.success_rate * 100)),
    )


# ============================================================================
# Anti-pattern mining (Phase 6 extension)
# ============================================================================

def mine_antipatterns(
    trajectories: Iterable[TrajectoryRecord] | None,
    *,
    min_support: int = ANTIPATTERN_MIN_SUPPORT,
    max_reward: float = ANTIPATTERN_MAX_REWARD,
    min_failure_rate: float = ANTIPATTERN_MIN_FAILURE_RATE,
    max_rules: int = ANTIPATTERN_MAX_RULES,
) -> list[AntiPatternRule]:
    """Group trajectories by (intent, action) and emit failing-pattern rules.

    Filters:
      - Skip entries without intent or action.
      - Group must have >= min_support rows.
      - Group mean_reward <= max_reward.
      - Group failure_rate >= min_failure_rate.

    Failure is any outcome that isn't "success" (i.e. failed, refused,
    partial, unknown). Returns rules sorted by severity DESC, capped at
    max_rules.
    """
    if not trajectories:
        return []

    groups: dict[tuple[str, str], list[TrajectoryRecord]] = {}
    for t in trajectories:
        if not isinstance(t, TrajectoryRecord):
            continue
        intent = (t.intent or "").strip()
        action = (t.action or "").strip()
        if not intent or not action:
            continue
        groups.setdefault((intent, action), []).append(t)

    rules: list[AntiPatternRule] = []
    for (intent, action), items in groups.items():
        n = len(items)
        if n < int(min_support):
            continue
        mean_reward = sum(float(t.reward) for t in items) / n
        if mean_reward > float(max_reward):
            continue
        successes = sum(1 for t in items if (t.outcome or "").strip() == "success")
        success_rate = successes / n
        failure_rate = 1.0 - success_rate
        if failure_rate < float(min_failure_rate):
            continue
        mean_confidence = sum(float(t.confidence) for t in items) / n
        support_weight = min(n / 5.0, 1.0)
        # Severity penalises high reward (mean_reward could be slightly
        # positive but still flagged because failure_rate is high) and
        # weights by support so a 2-sample pattern only earns 0.4x.
        normalised_reward_gap = 1.0 - max(0.0, min(1.0, mean_reward))
        severity = _clamp01(normalised_reward_gap * failure_rate * support_weight)

        # Pull up to 2 short summaries representative of the failure:
        # take the LOWEST-reward entries so the hint shows what failed.
        samples: list[str] = []
        for t in sorted(items, key=lambda r: float(r.reward)):
            s = (t.message_summary or "").strip()
            if s and s not in samples:
                samples.append(s)
            if len(samples) >= 2:
                break

        rules.append(AntiPatternRule(
            intent=intent,
            action=action,
            support_count=n,
            mean_reward=mean_reward,
            mean_confidence=mean_confidence,
            failure_rate=failure_rate,
            success_rate=success_rate,
            severity=severity,
            sample_summaries=samples,
        ))

    rules.sort(key=lambda r: r.severity, reverse=True)
    return rules[: max(0, int(max_rules))]


def select_antipattern_for_intent(
    rules: Iterable[AntiPatternRule] | None,
    intent: str,
) -> Optional[AntiPatternRule]:
    """Return the highest-severity anti-pattern whose intent matches, or None."""
    if not rules or not intent:
        return None
    target = intent.strip()
    if not target:
        return None
    best: Optional[AntiPatternRule] = None
    for r in rules:
        if not isinstance(r, AntiPatternRule):
            continue
        if r.intent != target:
            continue
        if best is None or r.severity > best.severity:
            best = r
    return best


_ANTIPATTERN_TEMPLATES = {
    "en": (
        "Avoid hint: in {n} past turn(s) for intent `{intent}`, calling "
        "`{action}` failed {failure}% of the time (mean reward {reward:.2f}). "
        "Pick a different approach."
    ),
    "es": (
        "Evita: en {n} turno(s) pasado(s) con intent `{intent}`, usar "
        "`{action}` falló el {failure}% de las veces (recompensa media "
        "{reward:.2f}). Elige otra estrategia."
    ),
}


def format_antipattern_hint(
    rule: Optional[AntiPatternRule],
    *,
    language: str = "en",
) -> str:
    """Render a one-line avoid-hint for the given rule. Empty if no rule."""
    if rule is None or not isinstance(rule, AntiPatternRule):
        return ""
    lang = "es" if language == "es" else "en"
    tmpl = _ANTIPATTERN_TEMPLATES[lang]
    return tmpl.format(
        n=int(rule.support_count),
        intent=rule.intent,
        action=rule.action,
        reward=float(rule.mean_reward),
        failure=int(round(rule.failure_rate * 100)),
    )


# ============================================================================
# Async Supabase fetch — mirror adaptation.retrieve_similar_trajectories shape
# ============================================================================

async def fetch_recent_trajectories(
    user_id: str,
    *,
    limit: int = 50,
) -> list[TrajectoryRecord]:
    """Fetch the user's most recent N trajectories (no similarity filter).

    Used by the miner to mine across a wider slice than the few-shot
    retrieval window. Falls back to `[]` on every failure path.
    """
    if not user_id or user_id == _NIL_UUID:
        return []

    cap = max(1, min(int(limit), _FETCH_SCAN_CAP))

    try:
        from backend.ai_engine import supabase_get
    except Exception as exc:  # noqa: BLE001
        logger.info("fetch_recent_trajectories: ai_engine unavailable (%s)", exc)
        return []

    try:
        rows = await supabase_get("agent_trajectories", {
            "user_id": f"eq.{user_id}",
            "select": (
                "id,turn_id,intent,message_summary,action,outcome,"
                "reward,confidence,language,retried,pushback_detected,created_at"
            ),
            "order": "created_at.desc",
            "limit": str(cap),
        })
    except Exception as exc:  # noqa: BLE001
        logger.info("fetch_recent_trajectories: fetch failed (%s)", exc)
        return []

    if not rows:
        return []

    out: list[TrajectoryRecord] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        try:
            out.append(TrajectoryRecord(
                id=r.get("id"),
                user_id=user_id,
                turn_id=r.get("turn_id"),
                intent=str(r.get("intent") or ""),
                message_summary=str(r.get("message_summary") or ""),
                action=str(r.get("action") or ""),
                outcome=str(r.get("outcome") or "unknown"),
                reward=float(r.get("reward") or 0.0),
                confidence=float(r.get("confidence") or 0.0),
                language=str(r.get("language") or "en"),
                retried=bool(r.get("retried")),
                pushback_detected=bool(r.get("pushback_detected")),
                created_at=r.get("created_at"),
            ))
        except Exception as exc:  # noqa: BLE001
            logger.info("fetch_recent_trajectories: row parse failed (%s)", exc)
            continue
    return out


__all__ = [
    "MIN_SUPPORT",
    "MIN_REWARD",
    "MIN_SUCCESS_RATE",
    "MAX_RULES",
    "ANTIPATTERN_MIN_SUPPORT",
    "ANTIPATTERN_MAX_REWARD",
    "ANTIPATTERN_MIN_FAILURE_RATE",
    "ANTIPATTERN_MAX_RULES",
    "ProceduralRule",
    "AntiPatternRule",
    "mine_procedural_rules",
    "mine_antipatterns",
    "select_rule_for_intent",
    "select_antipattern_for_intent",
    "format_procedural_hint",
    "format_antipattern_hint",
    "fetch_recent_trajectories",
]
