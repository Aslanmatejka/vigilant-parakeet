"""
Learning & Adaptation (AGENT_V2 — Phase 6 lite)
================================================

Closes the loop on the agent's behaviour: every completed turn becomes
a trajectory row with a computed reward; subsequent turns retrieve the
top few-shot examples ("situation → action → outcome") to ground the
reasoning head, and a per-user style summary feeds the register
selector.

Design parity with the rest of v2:

- Pure helpers; the only side effects are best-effort Supabase reads
  and writes. Every Supabase call is wrapped in try/except so a DB
  outage degrades to empty context, never a turn failure.
- No new infrastructure required at runtime. The trajectory table is
  expected to exist as `agent_trajectories` (parallel with
  `agent_user_facts`); if it doesn't, retrieval returns `[]` and
  recording is a no-op.
- Keyword-overlap Jaccard for trajectory similarity. Embeddings can
  swap in later without changing the public signature.
- No LLM calls in this module — reward + similarity are fully
  deterministic.

Naming note: the v1 `learning.py` module is a separate legacy module
that maintains a JSONB preference blob in `user_preferences`. This
module is the v2 replacement and runs only behind `AGENT_V2`.

Out of scope for Phase 6 lite:

- Procedural memory miner (offline nightly job).
- Embedding-based trajectory similarity.
- Migration of the v1 `learning.py` JSONB blob into the new schema.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# Constants
# ============================================================================

#: Below this reward we don't surface a trajectory as a few-shot example.
FEW_SHOT_MIN_REWARD: float = 0.40

#: Trajectories with reward >= this are "highly successful" — used by the
#: future procedural-memory miner and as a sanity floor in tests.
HIGH_REWARD_THRESHOLD: float = 0.80

#: Maximum number of recent trajectories pulled for style summarisation.
_STYLE_WINDOW: int = 20

#: Hard cap on the number of trajectory rows scanned for retrieval.
_RETRIEVAL_SCAN_CAP: int = 200

# Stop tokens reused from the memory module — keeping the constant local
# avoids a hard dependency for offline test runs.
_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "to", "of", "in", "for", "with",
    "is", "are", "was", "were", "be", "been", "being",
    "i", "me", "my", "we", "you", "your", "user", "users",
    "do", "does", "did", "have", "has", "had",
    "this", "that", "these", "those", "it", "its",
    "on", "at", "by", "as", "but", "if", "so", "not",
    "can", "cannot", "cant", "will", "would", "could", "should",
})

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_EMOJI_RE = re.compile(
    "["
    "\U0001f300-\U0001f6ff"  # symbols & pictographs / transport
    "\U0001f900-\U0001f9ff"  # supplemental symbols & pictographs
    "\U0001f600-\U0001f64f"  # emoticons
    "\U00002700-\U000027bf"  # dingbats
    "]"
)
_FORMAL_MARKERS = re.compile(
    r"\b(please|kindly|would you|could you|thank you|sincerely|"
    r"por favor|gracias|usted)\b",
    re.IGNORECASE,
)
_NIL_UUID = "00000000-0000-0000-0000-000000000000"


# ============================================================================
# Types
# ============================================================================

@dataclass
class TrajectoryRecord:
    """A single completed-turn trajectory ready to be persisted / scored."""
    id: Optional[str] = None
    user_id: str = ""
    turn_id: Optional[str] = None
    intent: str = ""
    message_summary: str = ""
    action: str = ""
    outcome: str = "unknown"  # success | partial | failed | refused | unknown
    reward: float = 0.0
    confidence: float = 0.0
    language: str = "en"
    retried: bool = False
    pushback_detected: bool = False
    created_at: Optional[str] = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "turn_id": self.turn_id,
            "intent": self.intent,
            "message_summary": self.message_summary,
            "action": self.action,
            "outcome": self.outcome,
            "reward": round(float(self.reward), 3),
            "confidence": round(float(self.confidence), 3),
            "language": self.language,
            "retried": bool(self.retried),
            "pushback_detected": bool(self.pushback_detected),
            "created_at": self.created_at,
            "notes": list(self.notes),
        }


@dataclass
class UserStyle:
    """Aggregate per-user communication style summary."""
    sample_size: int = 0
    avg_message_length: float = 0.0
    primary_language: str = "en"
    formality: float = 0.5     # 0 = casual, 1 = formal
    emoji_rate: float = 0.0    # emojis per message (avg)
    avg_reward: float = 0.0
    success_rate: float = 0.0  # fraction of trajectories with outcome=success

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_size": int(self.sample_size),
            "avg_message_length": round(float(self.avg_message_length), 1),
            "primary_language": self.primary_language,
            "formality": round(float(self.formality), 3),
            "emoji_rate": round(float(self.emoji_rate), 3),
            "avg_reward": round(float(self.avg_reward), 3),
            "success_rate": round(float(self.success_rate), 3),
        }


# ============================================================================
# Pure helpers
# ============================================================================

def _tokenize(text: str) -> set[str]:
    return {
        t for t in _TOKEN_RE.findall((text or "").lower())
        if t and t not in _STOPWORDS and len(t) > 1
    }


def _clamp(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))


def compute_reward(
    *,
    reflection_outcome: str,
    self_eval_overall: float,
    pushback_detected: bool,
    retried: bool,
    succeeded_tools: int,
    failed_tools: int,
    persona_ok: bool = True,
    safe_text_changed: bool = False,
) -> float:
    """Deterministic reward in `[-1, 1]` blending outcome + self-eval.

    Signal weights (chosen empirically — easy to retune later):

    - outcome: success +0.50, partial +0.20, failed -0.40, refused 0,
      unknown 0
    - self_eval overall: linearly maps [0..1] to [-0.20..+0.30]
    - tools succeeded > 0 and failed == 0: +0.10
    - tools all failed: -0.15
    - pushback_detected: -0.20
    - retried: -0.10 (we had to fix our own draft)
    - persona_ok=False: -0.10
    - safe_text_changed: -0.10
    """
    outcome_map = {
        "success": 0.50,
        "partial": 0.20,
        "failed": -0.40,
        "refused": 0.0,
        "unknown": 0.0,
    }
    reward = outcome_map.get(str(reflection_outcome or "unknown"), 0.0)
    # Map [0,1] → [-0.20, +0.30]
    eval_norm = max(0.0, min(1.0, float(self_eval_overall)))
    reward += (eval_norm * 0.50) - 0.20

    if succeeded_tools > 0 and failed_tools == 0:
        reward += 0.10
    elif failed_tools > 0 and succeeded_tools == 0:
        reward -= 0.15

    if pushback_detected:
        reward -= 0.20
    if retried:
        reward -= 0.10
    if not persona_ok:
        reward -= 0.10
    if safe_text_changed:
        reward -= 0.10

    return round(_clamp(reward), 3)


def _summarise_message(message: str, *, max_len: int = 140) -> str:
    """Lossy one-line summary used for trajectory similarity scoring."""
    text = (message or "").strip().replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text[:max_len]


def score_trajectory_similarity(
    record_summary: str,
    record_intent: str,
    query_message: str,
    query_intent: str,
) -> float:
    """Jaccard over message tokens with a bonus for matching intent.

    Returns `[0, 1.2]` — intent match adds a small boost beyond 1.0 so
    same-intent trajectories outrank token-similar but off-intent ones.
    """
    q_tokens = _tokenize(query_message)
    if not q_tokens:
        # Fall back to intent-only scoring so empty-message edge cases
        # still surface anything useful.
        return 0.20 if (
            query_intent and record_intent and query_intent == record_intent
        ) else 0.0
    r_tokens = _tokenize(record_summary)
    if not r_tokens:
        base = 0.0
    else:
        inter = q_tokens & r_tokens
        union = q_tokens | r_tokens
        base = (len(inter) / len(union)) if union else 0.0

    if query_intent and record_intent and query_intent == record_intent:
        base += 0.20  # intent match bonus
    return round(base, 4)


def format_few_shot_examples(
    trajectories: Iterable[TrajectoryRecord],
    *,
    limit: int = 3,
) -> str:
    """Compress trajectories into a `<few_shot>` prompt block.

    Empty input or zero-limit returns "" so the v1 prompt builder can
    drop the section entirely.
    """
    items = [t for t in (trajectories or []) if isinstance(t, TrajectoryRecord)]
    if not items or limit <= 0:
        return ""
    lines = ["<few_shot_examples>"]
    for tr in items[:limit]:
        msg = (tr.message_summary or "").strip()
        action = (tr.action or "").strip() or tr.intent or "responded"
        outcome = (tr.outcome or "unknown").strip()
        reward = round(float(tr.reward), 2)
        lines.append(
            f"- situation: {msg!r} | action: {action} | "
            f"outcome: {outcome} (reward={reward})"
        )
    lines.append("</few_shot_examples>")
    return "\n".join(lines)


# ============================================================================
# Supabase-backed retrieval + recording (graceful fallback)
# ============================================================================

async def retrieve_similar_trajectories(
    user_id: str,
    query_message: str,
    *,
    query_intent: str = "",
    limit: int = 3,
    min_reward: float = FEW_SHOT_MIN_REWARD,
) -> list[TrajectoryRecord]:
    """Fetch the user's recent trajectories and rank by similarity * reward.

    Falls back to `[]` on any Supabase failure (table missing, network,
    nil-UUID user, etc.). Only trajectories with `reward >= min_reward`
    are eligible — we don't teach the agent from its own failures here;
    that's the procedural miner's job in Phase 6 full.
    """
    if not user_id or user_id == _NIL_UUID:
        return []

    try:
        from backend.ai_engine import supabase_get
    except Exception as exc:  # noqa: BLE001
        logger.info("retrieve_similar_trajectories: ai_engine unavailable (%s)", exc)
        return []

    try:
        rows = await supabase_get("agent_trajectories", {
            "user_id": f"eq.{user_id}",
            "select": (
                "id,turn_id,intent,message_summary,action,outcome,"
                "reward,confidence,language,retried,pushback_detected,created_at"
            ),
            "order": "created_at.desc",
            "limit": str(_RETRIEVAL_SCAN_CAP),
        })
    except Exception as exc:  # noqa: BLE001
        logger.info("retrieve_similar_trajectories: fetch failed (%s)", exc)
        return []

    if not rows:
        return []

    scored: list[tuple[float, TrajectoryRecord]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        reward = float(r.get("reward") or 0.0)
        if reward < float(min_reward):
            continue
        summary = str(r.get("message_summary") or "")
        intent = str(r.get("intent") or "")
        sim = score_trajectory_similarity(summary, intent, query_message, query_intent)
        if sim <= 0.0:
            continue
        # Combined score: similarity * 0.7 + reward * 0.3
        combined = sim * 0.7 + reward * 0.3
        scored.append((combined, TrajectoryRecord(
            id=r.get("id"),
            user_id=user_id,
            turn_id=r.get("turn_id"),
            intent=intent,
            message_summary=summary,
            action=str(r.get("action") or ""),
            outcome=str(r.get("outcome") or "unknown"),
            reward=reward,
            confidence=float(r.get("confidence") or 0.0),
            language=str(r.get("language") or "en"),
            retried=bool(r.get("retried")),
            pushback_detected=bool(r.get("pushback_detected")),
            created_at=r.get("created_at"),
        )))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [t for _, t in scored[: max(0, int(limit))]]


async def record_trajectory(
    user_id: str,
    *,
    turn_id: Optional[str],
    intent: str,
    message: str,
    action: str,
    outcome: str,
    reward: float,
    confidence: float,
    language: str = "en",
    retried: bool = False,
    pushback_detected: bool = False,
) -> Optional[TrajectoryRecord]:
    """Persist a single trajectory row. Best-effort.

    Returns the persisted record (with `id` populated) on success or
    `None` on any failure / nil-UUID / empty user.
    """
    if not user_id or user_id == _NIL_UUID:
        return None

    record = TrajectoryRecord(
        user_id=user_id,
        turn_id=turn_id,
        intent=(intent or "").strip()[:120],
        message_summary=_summarise_message(message),
        action=(action or "").strip()[:140],
        outcome=str(outcome or "unknown"),
        reward=round(_clamp(reward), 3),
        confidence=round(max(0.0, min(1.0, float(confidence))), 3),
        language=str(language or "en"),
        retried=bool(retried),
        pushback_detected=bool(pushback_detected),
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    try:
        from backend.ai_engine import supabase_post
    except Exception as exc:  # noqa: BLE001
        logger.info("record_trajectory: ai_engine unavailable (%s)", exc)
        return None

    body = {
        "user_id": record.user_id,
        "turn_id": record.turn_id,
        "intent": record.intent,
        "message_summary": record.message_summary,
        "action": record.action,
        "outcome": record.outcome,
        "reward": record.reward,
        "confidence": record.confidence,
        "language": record.language,
        "retried": record.retried,
        "pushback_detected": record.pushback_detected,
        "created_at": record.created_at,
    }
    try:
        rows = await supabase_post("agent_trajectories", body)
    except Exception as exc:  # noqa: BLE001
        logger.info("record_trajectory: insert failed (%s)", exc)
        return None
    if rows and isinstance(rows, list) and isinstance(rows[0], dict):
        record.id = rows[0].get("id") or record.id
    return record


# ============================================================================
# Per-user style summarisation
# ============================================================================

def _formality_score(message: str) -> float:
    """0..1 score: 1.0 when message contains formal markers, scaled by length."""
    if not message:
        return 0.5
    has_marker = bool(_FORMAL_MARKERS.search(message))
    # Long messages with no contractions also read as more formal.
    no_contractions = ("'" not in message and "\u2019" not in message)
    long_message = len(message) > 80
    score = 0.5
    if has_marker:
        score += 0.30
    if long_message and no_contractions:
        score += 0.10
    if message.endswith("."):
        score += 0.05
    return min(1.0, score)


async def summarise_user_style(
    user_id: str,
    *,
    window: int = _STYLE_WINDOW,
) -> UserStyle:
    """Aggregate recent trajectories into a `UserStyle` snapshot.

    Returns an empty `UserStyle()` on any failure or nil-UUID.
    """
    if not user_id or user_id == _NIL_UUID:
        return UserStyle()

    try:
        from backend.ai_engine import supabase_get
    except Exception as exc:  # noqa: BLE001
        logger.info("summarise_user_style: ai_engine unavailable (%s)", exc)
        return UserStyle()

    try:
        rows = await supabase_get("agent_trajectories", {
            "user_id": f"eq.{user_id}",
            "select": "message_summary,language,outcome,reward",
            "order": "created_at.desc",
            "limit": str(max(1, int(window))),
        })
    except Exception as exc:  # noqa: BLE001
        logger.info("summarise_user_style: fetch failed (%s)", exc)
        return UserStyle()

    items = [r for r in (rows or []) if isinstance(r, dict)]
    if not items:
        return UserStyle()

    total_len = 0
    emoji_count = 0
    formality_sum = 0.0
    success_count = 0
    reward_sum = 0.0
    lang_counts: dict[str, int] = {}

    for r in items:
        msg = str(r.get("message_summary") or "")
        total_len += len(msg)
        emoji_count += len(_EMOJI_RE.findall(msg))
        formality_sum += _formality_score(msg)
        if str(r.get("outcome") or "") == "success":
            success_count += 1
        reward_sum += float(r.get("reward") or 0.0)
        lang = str(r.get("language") or "en")
        lang_counts[lang] = lang_counts.get(lang, 0) + 1

    n = len(items)
    primary_lang = max(lang_counts.items(), key=lambda kv: kv[1])[0] if lang_counts else "en"

    return UserStyle(
        sample_size=n,
        avg_message_length=total_len / n,
        primary_language=primary_lang,
        formality=formality_sum / n,
        emoji_rate=emoji_count / n,
        avg_reward=reward_sum / n,
        success_rate=success_count / n,
    )
