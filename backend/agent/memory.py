"""
Long-term Memory (AGENT_V2 — Phase 3 lite)
============================================

Persistent per-user memory backed by Supabase `agent_user_facts`. The
schema is shared with `_forget_about_me` (see `backend/tools.py`):

    {id, user_id, kind, content, importance, confirmed_by_user, created_at}

Public API:

    MemoryItem                                 # dataclass mirror of the row
    KIND_PREFERENCE / KIND_DIETARY / ...       # constants
    extract_salient_facts(message)             # heuristic
    extract_salient_facts_llm(message, ...)    # gpt-4o-mini + fallback
    retrieve_relevant_memories(user_id, query, *, limit=3)
    write_memories(user_id, facts, *, source_turn_id=None)
    privacy_disclosure_text(language)

Design choices for the lite ship:

- **No embeddings yet.** Relevance scoring is a simple keyword-overlap
  Jaccard over normalised tokens. This is *good enough* for under ~200
  facts per user and ships without pgvector / extra infra. The
  signature for `retrieve_relevant_memories` is stable so a future
  swap to embedding similarity is a pure-internal change.
- **Heuristic + LLM pair**, same shape as `reasoning.py` and
  `goals.py`. Heuristic is deterministic and covers the most
  common surface forms ("I'm vegan", "my address is X").
- **Graceful Supabase fallback.** If `supabase_get` / `supabase_post`
  raise (RLS error, network blip, offline test env) we log + return
  empty / no-op. Memory must never block a turn.
- **Privacy:** first write surfaces a disclosure string the caller
  (v2_graph) appends to the response so the user knows we're learning.
  `forget_about_me` already exists as the user-initiated wipe.
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

KIND_PREFERENCE = "preference"
KIND_DIETARY = "dietary"
KIND_STYLE = "style"
KIND_RELATIONSHIP = "relationship"
KIND_OTHER = "other"

_VALID_KINDS = {
    KIND_PREFERENCE, KIND_DIETARY, KIND_STYLE,
    KIND_RELATIONSHIP, KIND_OTHER,
}

MemoryKind = Literal[
    "preference", "dietary", "style", "relationship", "other",
]


@dataclass
class MemoryItem:
    """One row of long-term user memory.

    Mirrors the `agent_user_facts` schema. Keep `id` optional so callers
    can build a candidate before Supabase assigns a uuid.
    """
    user_id: str
    kind: MemoryKind = "other"           # type: ignore[assignment]
    content: str = ""
    importance: float = 0.5              # 0..1 — affects retrieval ordering
    confirmed_by_user: bool = False
    id: Optional[str] = None
    created_at: Optional[str] = None
    source_turn_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "user_id": self.user_id,
            "kind": self.kind,
            "content": self.content,
            "importance": round(float(self.importance), 3),
            "confirmed_by_user": self.confirmed_by_user,
        }
        if self.id:
            out["id"] = self.id
        if self.created_at:
            out["created_at"] = self.created_at
        if self.source_turn_id:
            out["source_turn_id"] = self.source_turn_id
        return out


# ============================================================================
# Heuristic salient-fact extraction
# ============================================================================

#: Patterns ordered most-specific first. Each (kind, regex, importance, fmt).
#: `fmt` is called with the match groups to format the persisted content.
_FACT_PATTERNS: list[tuple[MemoryKind, re.Pattern[str], float, Any]] = [
    # ---- dietary ----
    (
        "dietary",
        re.compile(
            r"\bi(?:'|\s+a)?m\s+(vegan|vegetarian|pescatarian|kosher|halal)\b",
            re.IGNORECASE,
        ),
        0.85,
        lambda m: f"User is {m.group(1).lower()}",
    ),
    (
        "dietary",
        re.compile(
            r"\bi(?:'|\s+a)?m\s+allergic\s+to\s+([a-z][a-z\s,]{1,60})",
            re.IGNORECASE,
        ),
        0.95,
        lambda m: f"User is allergic to {m.group(1).strip().rstrip('.').lower()}",
    ),
    (
        "dietary",
        re.compile(
            r"\bi\s+(?:can'?t|cannot|don'?t)\s+eat\s+([a-z][a-z\s,]{1,60})",
            re.IGNORECASE,
        ),
        0.80,
        lambda m: f"User can't eat {m.group(1).strip().rstrip('.').lower()}",
    ),
    # ---- preference ----
    (
        "preference",
        re.compile(
            r"\bi\s+(?:prefer|love|really like|always want)\s+([a-z][a-z\s,]{1,60})",
            re.IGNORECASE,
        ),
        0.60,
        lambda m: f"User prefers {m.group(1).strip().rstrip('.').lower()}",
    ),
    (
        "preference",
        re.compile(
            r"\bi\s+(?:hate|dislike|can'?t stand)\s+([a-z][a-z\s,]{1,60})",
            re.IGNORECASE,
        ),
        0.55,
        lambda m: f"User dislikes {m.group(1).strip().rstrip('.').lower()}",
    ),
    # ---- style ----
    (
        "style",
        re.compile(
            r"\b(?:please|always)?\s*(?:keep it|reply|respond|answer|be)\s+"
            r"(short|brief|concise|detailed|long)\b",
            re.IGNORECASE,
        ),
        0.50,
        lambda m: f"User prefers {m.group(1).lower()} replies",
    ),
    (
        "style",
        re.compile(
            r"\b(?:speak|reply|respond|answer|talk to me)\s+in\s+(spanish|english)\b",
            re.IGNORECASE,
        ),
        0.70,
        lambda m: f"User prefers replies in {m.group(1).lower()}",
    ),
    # ---- relationship / location ----
    (
        "relationship",
        re.compile(
            r"\bi\s+live\s+(?:in|at|near)\s+([A-Za-z][A-Za-z0-9\s,]{2,60})",
            re.IGNORECASE,
        ),
        0.65,
        lambda m: f"User lives in/near {m.group(1).strip().rstrip('.')}",
    ),
    (
        "relationship",
        re.compile(
            r"\bmy\s+(?:family|household|group)\s+(?:has|is|are)\s+"
            r"([a-z][a-z0-9\s,]{1,60})",
            re.IGNORECASE,
        ),
        0.60,
        lambda m: f"User's household: {m.group(1).strip().rstrip('.').lower()}",
    ),
]


def extract_salient_facts(
    message: str,
    *,
    user_id: str,
    source_turn_id: Optional[str] = None,
) -> list[MemoryItem]:
    """Pure-Python salient-fact extractor.

    Scans the message for high-signal personal-fact patterns and returns
    one `MemoryItem` per match. Caller is responsible for dedup against
    existing rows before persisting.
    """
    if not message or not message.strip():
        return []

    out: list[MemoryItem] = []
    seen_contents: set[str] = set()
    for kind, pat, importance, fmt in _FACT_PATTERNS:
        for m in pat.finditer(message):
            try:
                content = fmt(m)
            except Exception:  # noqa: BLE001
                continue
            content = str(content).strip()
            if not content or len(content) < 6:
                continue
            key = content.lower()
            if key in seen_contents:
                continue
            seen_contents.add(key)
            out.append(MemoryItem(
                user_id=user_id,
                kind=kind,
                content=content[:280],
                importance=importance,
                source_turn_id=source_turn_id,
            ))
    return out


# ============================================================================
# LLM-backed extraction
# ============================================================================

_EXTRACT_SYSTEM_PROMPT = (
    "You extract stable, personal facts from a single user message for a "
    "food-sharing assistant's long-term memory. Return STRICT JSON only:\n"
    '{"facts": [{"kind": "preference|dietary|style|relationship|other", '
    '"content": "<short fact, third-person>", '
    '"importance": 0.0..1.0}]}\n'
    "Rules:\n"
    "- Only persist facts that are likely to stay true for weeks (vegan, "
    "lives in X, prefers brief replies). NEVER persist one-off requests, "
    "ongoing claims, or session-level state.\n"
    "- Skip greetings, gratitude, and small talk → return an empty list.\n"
    "- Write content in third person (\"User is vegan\"), max 200 chars.\n"
    "- Output nothing outside the JSON object."
)


def _scrub(text: str) -> str:
    cleaned = re.sub(
        r"(sk-[A-Za-z0-9]{16,}|Bearer\s+[A-Za-z0-9._\-]{16,})",
        "[redacted]", text or "", flags=re.IGNORECASE,
    )
    return cleaned[:1500]


async def extract_salient_facts_llm(
    message: str,
    *,
    user_id: str,
    source_turn_id: Optional[str] = None,
) -> list[MemoryItem]:
    """LLM extractor. Falls back to heuristic on any failure."""
    raw = (message or "").strip()
    if not raw:
        return []
    if not os.getenv("OPENAI_API_KEY"):
        return extract_salient_facts(raw, user_id=user_id, source_turn_id=source_turn_id)

    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage, SystemMessage
    except Exception as exc:  # noqa: BLE001
        logger.info("extract_salient_facts_llm: langchain unavailable (%s) — heuristic", exc)
        return extract_salient_facts(raw, user_id=user_id, source_turn_id=source_turn_id)

    try:
        model = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.0,
            api_key=os.getenv("OPENAI_API_KEY"),
            timeout=8,
        )
        resp = await asyncio.wait_for(model.ainvoke([
            SystemMessage(content=_EXTRACT_SYSTEM_PROMPT),
            HumanMessage(content=_scrub(raw)),
        ]), timeout=6.0)
    except Exception as exc:  # noqa: BLE001
        logger.info("extract_salient_facts_llm: invoke failed (%s) — heuristic", exc)
        return extract_salient_facts(raw, user_id=user_id, source_turn_id=source_turn_id)

    body = (getattr(resp, "content", "") or "").strip()
    if body.startswith("```"):
        body = re.sub(r"^```(?:json)?\s*|\s*```$", "", body, flags=re.DOTALL)
    try:
        data = json.loads(body)
    except Exception as exc:  # noqa: BLE001
        logger.info("extract_salient_facts_llm: bad JSON (%s) — heuristic", exc)
        return extract_salient_facts(raw, user_id=user_id, source_turn_id=source_turn_id)

    items = data.get("facts") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []

    out: list[MemoryItem] = []
    seen: set[str] = set()
    for it in items:
        if not isinstance(it, dict):
            continue
        kind = str(it.get("kind") or "other").strip().lower()
        if kind not in _VALID_KINDS:
            kind = "other"
        content = str(it.get("content") or "").strip()
        if len(content) < 6:
            continue
        key = content.lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            importance = float(it.get("importance", 0.5))
        except (TypeError, ValueError):
            importance = 0.5
        importance = max(0.0, min(1.0, importance))
        out.append(MemoryItem(
            user_id=user_id,
            kind=kind,  # type: ignore[arg-type]
            content=content[:280],
            importance=importance,
            source_turn_id=source_turn_id,
        ))
    return out


# ============================================================================
# Relevance scoring (keyword-overlap Jaccard, no embeddings yet)
# ============================================================================

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


def _tokenize(text: str) -> set[str]:
    return {
        t for t in _TOKEN_RE.findall((text or "").lower())
        if t and t not in _STOPWORDS and len(t) > 1
    }


def score_memory_relevance(memory_content: str, query: str) -> float:
    """Jaccard similarity over content tokens.

    Returns a value in `[0, 1]`. Empty query → 0.0; identical bags → 1.0.
    """
    q_tokens = _tokenize(query)
    if not q_tokens:
        return 0.0
    m_tokens = _tokenize(memory_content)
    if not m_tokens:
        return 0.0
    inter = q_tokens & m_tokens
    if not inter:
        return 0.0
    union = q_tokens | m_tokens
    return len(inter) / len(union)


# ============================================================================
# Supabase-backed retrieval + write (graceful fallback)
# ============================================================================

async def retrieve_relevant_memories(
    user_id: str,
    query: str,
    *,
    limit: int = 3,
    min_score: float = 0.05,
) -> list[MemoryItem]:
    """Fetch the user's facts and rank by relevance.

    Two-tier retrieval:
      1. When `AGENT_V2_MEMORY_EMBEDDINGS` is on AND we can produce an
         embedding for the query, call the `match_agent_user_facts` RPC
         which does cosine similarity in Postgres against the pgvector
         column.
      2. Otherwise (or on RPC failure) fall back to the pure-Python
         keyword-Jaccard scoring path that shipped in Slice A.

    Falls back to `[]` if Supabase is unreachable. Dietary facts with
    `importance >= 0.85` always survive the cutoff (allergies must never
    silently drop out of context).
    """
    if not user_id:
        return []

    # ---------- Tier 1: pgvector semantic search ----------
    semantic_hits = await _retrieve_via_embeddings(
        user_id, query, limit=limit,
    )
    if semantic_hits:
        return semantic_hits

    # ---------- Tier 2: keyword-Jaccard fallback ----------
    try:
        from backend.ai_engine import supabase_get
    except Exception as exc:  # noqa: BLE001
        logger.info("retrieve_relevant_memories: ai_engine unavailable (%s)", exc)
        return []

    try:
        rows = await supabase_get("agent_user_facts", {
            "user_id": f"eq.{user_id}",
            "select": "id,kind,content,importance,confirmed_by_user,created_at",
            "limit": "200",
        })
    except Exception as exc:  # noqa: BLE001
        logger.info("retrieve_relevant_memories: fetch failed (%s)", exc)
        return []

    if not rows:
        return []

    scored: list[tuple[float, MemoryItem]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        content = str(r.get("content") or "")
        importance = float(r.get("importance") or 0.5)
        # Combined score: relevance * 0.7 + importance * 0.3.
        rel = score_memory_relevance(content, query)
        combined = rel * 0.7 + importance * 0.3
        # Allergies / strong dietary facts are always relevant.
        is_safety_critical = (
            str(r.get("kind")) == "dietary" and importance >= 0.85
        )
        if not is_safety_critical and rel < min_score:
            continue
        scored.append((combined, MemoryItem(
            id=r.get("id"),
            user_id=user_id,
            kind=str(r.get("kind") or "other"),  # type: ignore[arg-type]
            content=content,
            importance=importance,
            confirmed_by_user=bool(r.get("confirmed_by_user")),
            created_at=r.get("created_at"),
        )))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in scored[: max(0, int(limit))]]


async def _retrieve_via_embeddings(
    user_id: str,
    query: str,
    *,
    limit: int,
) -> list[MemoryItem]:
    """Semantic memory hit via `match_agent_user_facts` RPC.

    Returns [] on any failure (disabled flag, no embedding, RPC missing,
    Supabase error). Caller then falls through to keyword search.
    """
    try:
        from backend.agent.memory_embeddings import embed_text, embeddings_enabled
    except Exception:  # noqa: BLE001
        return []

    if not embeddings_enabled():
        return []
    vector = await embed_text(query)
    if not vector:
        return []

    try:
        from backend.ai_engine import supabase_rpc
    except Exception as exc:  # noqa: BLE001
        logger.info("_retrieve_via_embeddings: supabase_rpc unavailable (%s)", exc)
        return []

    try:
        rows = await supabase_rpc("match_agent_user_facts", {
            "target_user_id": user_id,
            "query_embedding": vector,
            "match_count": max(1, int(limit)),
        })
    except Exception as exc:  # noqa: BLE001
        logger.info("_retrieve_via_embeddings: RPC failed (%s)", exc)
        return []

    if not rows or not isinstance(rows, list):
        return []

    out: list[MemoryItem] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        out.append(MemoryItem(
            id=r.get("id"),
            user_id=r.get("user_id") or user_id,
            kind=str(r.get("kind") or "other"),  # type: ignore[arg-type]
            content=str(r.get("content") or ""),
            importance=float(r.get("importance") or 0.5),
            confirmed_by_user=bool(r.get("confirmed_by_user")),
            created_at=r.get("created_at"),
        ))
    return out


async def _existing_contents(user_id: str) -> set[str]:
    """Return lowercase content strings already stored for this user.

    Used by `write_memories` to skip duplicates without burning a write."""
    try:
        from backend.ai_engine import supabase_get
        rows = await supabase_get("agent_user_facts", {
            "user_id": f"eq.{user_id}",
            "select": "content",
            "limit": "500",
        })
        return {
            str(r.get("content") or "").strip().lower()
            for r in (rows or []) if isinstance(r, dict)
        }
    except Exception as exc:  # noqa: BLE001
        logger.info("_existing_contents failed (%s)", exc)
        return set()


async def write_memories(
    user_id: str,
    facts: Iterable[MemoryItem],
    *,
    source_turn_id: Optional[str] = None,
) -> list[MemoryItem]:
    """Persist new memory rows. Returns the rows actually written.

    Skips facts whose `content.lower()` already exists for the user.
    Caller is expected to have already filtered out garbage.
    """
    if not user_id:
        return []
    candidates = [f for f in facts if f and f.content]
    if not candidates:
        return []

    existing = await _existing_contents(user_id)

    try:
        from backend.ai_engine import supabase_post
    except Exception as exc:  # noqa: BLE001
        logger.info("write_memories: ai_engine unavailable (%s)", exc)
        return []

    # Batch-embed all candidate contents up front (best-effort). Order is
    # preserved; None slots simply skip the embedding column on insert.
    new_texts = [
        f.content[:280] for f in candidates
        if f.content.strip().lower() not in existing
    ]
    embeddings_by_key: dict[str, Optional[list[float]]] = {}
    if new_texts:
        try:
            from backend.agent.memory_embeddings import embed_texts, embeddings_enabled
            if embeddings_enabled():
                vectors = await embed_texts(new_texts)
                for text, vec in zip(new_texts, vectors):
                    embeddings_by_key[text.strip().lower()] = vec
        except Exception as exc:  # noqa: BLE001
            logger.info("write_memories: embedding batch failed (%s)", exc)

    written: list[MemoryItem] = []
    for f in candidates:
        key = f.content.strip().lower()
        if key in existing:
            continue
        body = {
            "user_id": f.user_id or user_id,
            "kind": f.kind,
            "content": f.content[:280],
            "importance": round(float(f.importance), 3),
            "confirmed_by_user": bool(f.confirmed_by_user),
            "created_at": (
                f.created_at or datetime.now(timezone.utc).isoformat()
            ),
        }
        if source_turn_id or f.source_turn_id:
            body["source_turn_id"] = source_turn_id or f.source_turn_id
        vec = embeddings_by_key.get(f.content[:280].strip().lower())
        if vec:
            body["embedding"] = vec
        try:
            rows = await supabase_post("agent_user_facts", body)
        except Exception as exc:  # noqa: BLE001
            logger.warning("write_memories: insert failed (%s)", exc)
            continue
        existing.add(key)  # don't double-write if facts list has duplicates
        if rows and isinstance(rows, list):
            row = rows[0]
            written.append(MemoryItem(
                id=row.get("id"),
                user_id=row.get("user_id") or user_id,
                kind=row.get("kind") or f.kind,  # type: ignore[arg-type]
                content=str(row.get("content") or f.content),
                importance=float(row.get("importance") or f.importance),
                confirmed_by_user=bool(row.get("confirmed_by_user")),
                created_at=row.get("created_at"),
                source_turn_id=row.get("source_turn_id") or source_turn_id,
            ))
        else:
            written.append(f)
    return written


# ============================================================================
# Privacy disclosure
# ============================================================================

def privacy_disclosure_text(language: str = "en") -> str:
    """One-liner the caller can append to the response on the *first*
    memory write of a session. Localised."""
    if (language or "").startswith("es"):
        return (
            "(Voy a recordar esto para futuras conversaciones. "
            "Si prefieres que no lo haga, dime \"olvídate de mí\".)"
        )
    return (
        "(I'll remember this for future conversations. If you'd rather I "
        "didn't, just say \"forget about me\".)"
    )


__all__ = [
    "KIND_DIETARY",
    "KIND_OTHER",
    "KIND_PREFERENCE",
    "KIND_RELATIONSHIP",
    "KIND_STYLE",
    "MemoryItem",
    "MemoryKind",
    "extract_salient_facts",
    "extract_salient_facts_llm",
    "privacy_disclosure_text",
    "retrieve_relevant_memories",
    "score_memory_relevance",
    "write_memories",
]
