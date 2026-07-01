"""
Procedural Rule Persistence (AGENT_V2 — Phase 6 mid)
=====================================================

Read/write helpers for the `agent_procedural_rules` and
`agent_procedural_antipatterns` tables. Bridges the pure-Python miners
in `procedural.py` with Supabase so the v2 hot path can serve cached
rules instead of re-mining every turn.

Public API:

    upsert_procedural_rules(user_id, rules, *, run_id=None)
    upsert_antipattern_rules(user_id, rules, *, run_id=None)
    fetch_procedural_rules(user_id, *, intent=None, limit=25)
    fetch_antipattern_rules(user_id, *, intent=None, limit=25)

All Supabase calls are best-effort — any error logs + returns None / [].
Persistence is *strictly additive*: v2_graph still falls back to inline
mining if these tables are empty (e.g. before the migration is applied).
"""

from __future__ import annotations

import logging
from typing import Iterable, Optional

from backend.agent.procedural import AntiPatternRule, ProceduralRule

logger = logging.getLogger(__name__)


# ============================================================================
# Writers
# ============================================================================

async def upsert_procedural_rules(
    user_id: Optional[str],
    rules: Iterable[ProceduralRule],
    *,
    run_id: Optional[str] = None,
) -> int:
    """Upsert positive rules keyed by (user_id, intent, action).

    `user_id=None` writes GLOBAL rules (aggregated across users) — those
    live in the same table via the partial unique index.
    Returns the number of rows successfully written (0 on any failure).
    """
    payload = [_rule_row(user_id, r, run_id) for r in rules if r]
    if not payload:
        return 0

    # Two conflict targets — the partial unique indexes differ for
    # per-user vs global rows. PostgREST's on_conflict clause requires a
    # single column list, so split.
    per_user = [p for p in payload if p.get("user_id")]
    global_ = [p for p in payload if not p.get("user_id")]

    written = 0
    if per_user:
        written += await _upsert(
            "agent_procedural_rules", per_user,
            on_conflict="user_id,intent,action",
        )
    if global_:
        written += await _upsert(
            "agent_procedural_rules", global_,
            on_conflict="intent,action",
        )
    return written


async def upsert_antipattern_rules(
    user_id: Optional[str],
    rules: Iterable[AntiPatternRule],
    *,
    run_id: Optional[str] = None,
) -> int:
    """Upsert anti-pattern rules keyed by (user_id, intent, action)."""
    payload = [_anti_row(user_id, r, run_id) for r in rules if r]
    if not payload:
        return 0

    per_user = [p for p in payload if p.get("user_id")]
    global_ = [p for p in payload if not p.get("user_id")]

    written = 0
    if per_user:
        written += await _upsert(
            "agent_procedural_antipatterns", per_user,
            on_conflict="user_id,intent,action",
        )
    if global_:
        written += await _upsert(
            "agent_procedural_antipatterns", global_,
            on_conflict="intent,action",
        )
    return written


# ============================================================================
# Readers
# ============================================================================

async def fetch_procedural_rules(
    user_id: Optional[str],
    *,
    intent: Optional[str] = None,
    limit: int = 25,
) -> list[ProceduralRule]:
    """Return cached positive rules for the user (or global when NULL).

    Prefers per-user rows; falls back to global rows when the user has
    none for the requested intent. Returns [] on any Supabase failure.
    """
    rows = await _select(
        "agent_procedural_rules", user_id, intent, limit,
        select_cols=(
            "id,user_id,intent,action,support_count,mean_reward,"
            "mean_confidence,success_rate,confidence,sample_summaries"
        ),
        order_col="confidence",
    )
    out: list[ProceduralRule] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        try:
            out.append(ProceduralRule(
                intent=str(r.get("intent") or ""),
                action=str(r.get("action") or ""),
                support_count=int(r.get("support_count") or 0),
                mean_reward=float(r.get("mean_reward") or 0.0),
                mean_confidence=float(r.get("mean_confidence") or 0.0),
                success_rate=float(r.get("success_rate") or 0.0),
                confidence=float(r.get("confidence") or 0.0),
                sample_summaries=list(r.get("sample_summaries") or []),
            ))
        except (ValueError, TypeError) as exc:
            logger.debug("skip malformed procedural row: %s", exc)
    return out


async def fetch_antipattern_rules(
    user_id: Optional[str],
    *,
    intent: Optional[str] = None,
    limit: int = 25,
) -> list[AntiPatternRule]:
    """Return cached anti-pattern rules for the user."""
    rows = await _select(
        "agent_procedural_antipatterns", user_id, intent, limit,
        select_cols=(
            "id,user_id,intent,action,support_count,mean_reward,"
            "mean_confidence,failure_rate,success_rate,severity,sample_summaries"
        ),
        order_col="severity",
    )
    out: list[AntiPatternRule] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        try:
            out.append(AntiPatternRule(
                intent=str(r.get("intent") or ""),
                action=str(r.get("action") or ""),
                support_count=int(r.get("support_count") or 0),
                mean_reward=float(r.get("mean_reward") or 0.0),
                mean_confidence=float(r.get("mean_confidence") or 0.0),
                failure_rate=float(r.get("failure_rate") or 0.0),
                success_rate=float(r.get("success_rate") or 0.0),
                severity=float(r.get("severity") or 0.0),
                sample_summaries=list(r.get("sample_summaries") or []),
            ))
        except (ValueError, TypeError) as exc:
            logger.debug("skip malformed antipattern row: %s", exc)
    return out


# ============================================================================
# Row builders (pure)
# ============================================================================

def _rule_row(
    user_id: Optional[str],
    r: ProceduralRule,
    run_id: Optional[str],
) -> dict:
    row = {
        "user_id": user_id,
        "intent": (r.intent or "")[:120],
        "action": (r.action or "")[:140],
        "support_count": int(r.support_count),
        "mean_reward": float(r.mean_reward),
        "mean_confidence": float(r.mean_confidence),
        "success_rate": float(r.success_rate),
        "confidence": float(r.confidence),
        "sample_summaries": list(r.sample_summaries or []),
    }
    if run_id:
        row["run_id"] = run_id
    return row


def _anti_row(
    user_id: Optional[str],
    r: AntiPatternRule,
    run_id: Optional[str],
) -> dict:
    row = {
        "user_id": user_id,
        "intent": (r.intent or "")[:120],
        "action": (r.action or "")[:140],
        "support_count": int(r.support_count),
        "mean_reward": float(r.mean_reward),
        "mean_confidence": float(r.mean_confidence),
        "failure_rate": float(r.failure_rate),
        "success_rate": float(r.success_rate),
        "severity": float(r.severity),
        "sample_summaries": list(r.sample_summaries or []),
    }
    if run_id:
        row["run_id"] = run_id
    return row


# ============================================================================
# Supabase adapters
# ============================================================================

async def _upsert(table: str, rows: list[dict], *, on_conflict: str) -> int:
    """POST to Supabase with `Prefer: resolution=merge-duplicates` — the
    PostgREST way to upsert. Returns rows written (best-effort)."""
    if not rows:
        return 0
    try:
        import httpx
        from backend.ai_engine import (
            SUPABASE_URL, SUPABASE_SERVICE_KEY, SUPABASE_TIMEOUT,
        )
    except Exception as exc:  # noqa: BLE001
        logger.info("procedural upsert: ai_engine unavailable (%s)", exc)
        return 0

    if not (SUPABASE_URL and SUPABASE_SERVICE_KEY):
        return 0

    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=representation",
    }
    try:
        async with httpx.AsyncClient(timeout=SUPABASE_TIMEOUT) as client:
            resp = await client.post(
                f"{SUPABASE_URL}/rest/v1/{table}",
                params={"on_conflict": on_conflict},
                json=rows,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            return len(data) if isinstance(data, list) else 0
    except Exception as exc:  # noqa: BLE001
        logger.warning("procedural upsert into %s failed: %s", table, exc)
        return 0


async def _select(
    table: str,
    user_id: Optional[str],
    intent: Optional[str],
    limit: int,
    *,
    select_cols: str,
    order_col: str,
) -> list[dict]:
    try:
        from backend.ai_engine import supabase_get
    except Exception as exc:  # noqa: BLE001
        logger.info("procedural select: ai_engine unavailable (%s)", exc)
        return []

    params: dict[str, str] = {
        "select": select_cols,
        "order": f"{order_col}.desc",
        "limit": str(max(1, min(int(limit), 100))),
    }
    if user_id:
        # Include the user's own rules PLUS global (user_id IS NULL) rows.
        params["or"] = f"(user_id.eq.{user_id},user_id.is.null)"
    else:
        params["user_id"] = "is.null"
    if intent:
        params["intent"] = f"eq.{intent}"
    try:
        return await supabase_get(table, params) or []
    except Exception as exc:  # noqa: BLE001
        logger.info("procedural select from %s failed: %s", table, exc)
        return []


__all__ = [
    "upsert_procedural_rules",
    "upsert_antipattern_rules",
    "fetch_procedural_rules",
    "fetch_antipattern_rules",
]
