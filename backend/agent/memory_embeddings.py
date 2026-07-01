"""
Memory Embeddings (AGENT_V2 — Phase 3 full)
============================================

Optional OpenAI-embedding layer for `agent_user_facts`. Enabled per env:

    AGENT_V2_MEMORY_EMBEDDINGS=true

When on, `write_memories` computes a text-embedding-3-small vector for
each new fact and stores it in the pgvector column. `retrieve_relevant_memories`
first tries the `match_agent_user_facts` RPC; on any failure it falls back
to the pure-Python keyword-Jaccard scoring already in `memory.py`.

Design:
- Pure best-effort: any failure (no key, HTTP error, timeout, disabled
  flag, missing extension) returns None / [] and the caller degrades to
  keyword-only. Memory MUST NEVER break a turn.
- Model + dimensions locked to text-embedding-3-small (1536). The
  migration hardcodes the same dimension in the vector column.
- Batching: `embed_texts` accepts up to 100 strings per call. Above that
  we chunk to stay well under the OpenAI request limit.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Iterable, Optional

logger = logging.getLogger(__name__)


EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536
_BATCH_SIZE = 100
_TIMEOUT_S = 8.0


def embeddings_enabled() -> bool:
    """Master switch. Default off so existing deployments keep working."""
    return os.getenv("AGENT_V2_MEMORY_EMBEDDINGS", "false").strip().lower() in (
        "true", "1", "yes", "on",
    )


def _chunks(items: list[str], n: int) -> Iterable[list[str]]:
    for i in range(0, len(items), n):
        yield items[i : i + n]


async def embed_text(text: str) -> Optional[list[float]]:
    """Embed a single string. Returns None on any failure."""
    if not text or not text.strip():
        return None
    if not embeddings_enabled():
        return None
    vectors = await embed_texts([text])
    if vectors and vectors[0]:
        return vectors[0]
    return None


async def embed_texts(texts: list[str]) -> list[Optional[list[float]]]:
    """Batch-embed a list of strings. Returns a list the same length as
    the input, with None slots for empty inputs or failed batches.

    Uses OpenAI directly — cheaper than routing through the chat pipeline
    and independent of the LLM temperature knobs.
    """
    if not texts:
        return []
    if not embeddings_enabled():
        return [None] * len(texts)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return [None] * len(texts)

    # Normalise + record indexes so we can slot None back for empty inputs.
    cleaned: list[str] = []
    index_map: list[int] = []
    for i, t in enumerate(texts):
        s = (t or "").strip()
        if s:
            cleaned.append(s[:8000])   # OpenAI hard cap ~8k tokens; be safe
            index_map.append(i)
    if not cleaned:
        return [None] * len(texts)

    out: list[Optional[list[float]]] = [None] * len(texts)

    try:
        # Prefer the modern AsyncOpenAI client if present; fall back to httpx.
        try:
            from openai import AsyncOpenAI  # type: ignore
            client = AsyncOpenAI(api_key=api_key)
            for batch in _chunks(cleaned, _BATCH_SIZE):
                try:
                    resp = await asyncio.wait_for(
                        client.embeddings.create(
                            model=EMBEDDING_MODEL,
                            input=batch,
                        ),
                        timeout=_TIMEOUT_S,
                    )
                    for k, item in enumerate(resp.data):
                        # Reconstruct the original position.
                        original_pos = index_map[cleaned.index(batch[k])]
                        vec = list(item.embedding)
                        if len(vec) == EMBEDDING_DIMENSIONS:
                            out[original_pos] = vec
                except asyncio.TimeoutError:
                    logger.info("embed_texts: batch timed out")
                except Exception as exc:  # noqa: BLE001
                    logger.info("embed_texts: batch failed (%s)", exc)
            return out
        except ImportError:
            # Fall through to httpx path.
            pass

        import httpx
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as http:
            for batch in _chunks(cleaned, _BATCH_SIZE):
                try:
                    resp = await http.post(
                        "https://api.openai.com/v1/embeddings",
                        headers=headers,
                        json={"model": EMBEDDING_MODEL, "input": batch},
                    )
                    resp.raise_for_status()
                    data = resp.json().get("data") or []
                    for k, item in enumerate(data):
                        original_pos = index_map[cleaned.index(batch[k])]
                        vec = list(item.get("embedding") or [])
                        if len(vec) == EMBEDDING_DIMENSIONS:
                            out[original_pos] = vec
                except Exception as exc:  # noqa: BLE001
                    logger.info("embed_texts httpx batch failed (%s)", exc)
        return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("embed_texts unexpected error (%s)", exc)
        return [None] * len(texts)


__all__ = [
    "EMBEDDING_MODEL",
    "EMBEDDING_DIMENSIONS",
    "embed_text",
    "embed_texts",
    "embeddings_enabled",
]
