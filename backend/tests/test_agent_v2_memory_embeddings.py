"""
AGENT_V2 (Phase 3 full) — memory embeddings tests
==================================================

Verifies:
  * `embeddings_enabled()` honors the env flag.
  * `retrieve_relevant_memories` transparently uses the pgvector RPC when
    embeddings are on AND the RPC returns rows.
  * On RPC failure it falls back to keyword scoring — no exception, no
    silent memory loss.
  * `write_memories` attaches an embedding to the insert body when the
    flag is on.

Run:
    python -m pytest backend/tests/test_agent_v2_memory_embeddings.py -v
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from backend.agent import memory as memory_mod
from backend.agent import memory_embeddings as emb_mod
from backend.agent.memory import MemoryItem


USER = "aaaaaaaa-0000-0000-0000-000000000001"


class _FakeSupabase:
    def __init__(self):
        self.get_rows: list[dict] = []
        self.rpc_rows: Any = None
        self.rpc_raises: Exception | None = None
        self.rpc_calls: list[tuple[str, dict]] = []
        self.posts: list[tuple[str, dict]] = []

    async def supabase_get(self, table, params):
        if table == "agent_user_facts":
            return list(self.get_rows)
        return []

    async def supabase_rpc(self, fn_name, body):
        self.rpc_calls.append((fn_name, body))
        if self.rpc_raises:
            raise self.rpc_raises
        return self.rpc_rows

    async def supabase_post(self, table, body):
        self.posts.append((table, body))
        return [{"id": "new-1", **body}]


@pytest.fixture()
def fake(monkeypatch):
    f = _FakeSupabase()
    import backend.ai_engine as ai_engine
    monkeypatch.setattr(ai_engine, "supabase_get", f.supabase_get, raising=False)
    monkeypatch.setattr(ai_engine, "supabase_rpc", f.supabase_rpc, raising=False)
    monkeypatch.setattr(ai_engine, "supabase_post", f.supabase_post, raising=False)
    return f


class TestFlag:
    def test_off_by_default(self, monkeypatch):
        monkeypatch.delenv("AGENT_V2_MEMORY_EMBEDDINGS", raising=False)
        assert emb_mod.embeddings_enabled() is False

    def test_on_variants(self, monkeypatch):
        for val in ("true", "1", "yes", "on"):
            monkeypatch.setenv("AGENT_V2_MEMORY_EMBEDDINGS", val)
            assert emb_mod.embeddings_enabled() is True


class TestRetrieveViaRPC:
    def test_uses_rpc_when_embeddings_on(self, fake, monkeypatch):
        monkeypatch.setenv("AGENT_V2_MEMORY_EMBEDDINGS", "true")

        # Stub embed_text to return a plausible 1536-dim vector.
        async def _fake_embed(text: str):
            return [0.1] * emb_mod.EMBEDDING_DIMENSIONS
        monkeypatch.setattr(emb_mod, "embed_text", _fake_embed)

        fake.rpc_rows = [
            {"id": "m1", "user_id": USER, "kind": "dietary", "content": "is vegan",
             "importance": 8, "confirmed_by_user": True, "created_at": "2026-06-01"},
            {"id": "m2", "user_id": USER, "kind": "preference", "content": "likes rye bread",
             "importance": 5, "confirmed_by_user": False, "created_at": "2026-06-02"},
        ]

        results = asyncio.run(memory_mod.retrieve_relevant_memories(
            USER, "what should I eat?", limit=5,
        ))
        assert [m.id for m in results] == ["m1", "m2"]
        # RPC must have been invoked with our target user and vector.
        assert fake.rpc_calls[0][0] == "match_agent_user_facts"
        assert fake.rpc_calls[0][1]["target_user_id"] == USER
        assert len(fake.rpc_calls[0][1]["query_embedding"]) == emb_mod.EMBEDDING_DIMENSIONS

    def test_falls_back_to_keyword_on_rpc_error(self, fake, monkeypatch):
        monkeypatch.setenv("AGENT_V2_MEMORY_EMBEDDINGS", "true")

        async def _fake_embed(text: str):
            return [0.1] * emb_mod.EMBEDDING_DIMENSIONS
        monkeypatch.setattr(emb_mod, "embed_text", _fake_embed)

        fake.rpc_raises = RuntimeError("pgvector extension missing")
        # Populate keyword-search fallback data.
        fake.get_rows = [{
            "id": "kw-1", "kind": "preference", "content": "likes bread and cheese",
            "importance": 0.6, "confirmed_by_user": False, "created_at": "2026-06-01",
        }]

        results = asyncio.run(memory_mod.retrieve_relevant_memories(
            USER, "bread", limit=3,
        ))
        assert len(results) == 1
        assert results[0].id == "kw-1"

    def test_falls_back_when_flag_off(self, fake, monkeypatch):
        monkeypatch.delenv("AGENT_V2_MEMORY_EMBEDDINGS", raising=False)

        fake.get_rows = [{
            "id": "kw-2", "kind": "preference", "content": "likes tea",
            "importance": 0.5, "confirmed_by_user": False, "created_at": "2026-06-01",
        }]
        results = asyncio.run(memory_mod.retrieve_relevant_memories(
            USER, "tea", limit=3,
        ))
        assert len(results) == 1
        # RPC must NOT have been called when flag is off.
        assert not fake.rpc_calls


class TestWriteAttachesEmbedding:
    def test_embedding_included_on_insert(self, fake, monkeypatch):
        monkeypatch.setenv("AGENT_V2_MEMORY_EMBEDDINGS", "true")

        async def _fake_embed_texts(texts):
            return [[0.2] * emb_mod.EMBEDDING_DIMENSIONS for _ in texts]
        monkeypatch.setattr(emb_mod, "embed_texts", _fake_embed_texts)

        # No existing content — force a real insert path.
        fake.get_rows = []
        item = MemoryItem(
            user_id=USER, kind="preference",
            content="hates cilantro", importance=0.7,
        )
        written = asyncio.run(memory_mod.write_memories(USER, [item]))
        assert len(written) == 1
        # The POST body must carry an embedding.
        assert fake.posts, "expected an insert to agent_user_facts"
        table, body = fake.posts[0]
        assert table == "agent_user_facts"
        assert "embedding" in body
        assert len(body["embedding"]) == emb_mod.EMBEDDING_DIMENSIONS

    def test_no_embedding_when_flag_off(self, fake, monkeypatch):
        monkeypatch.delenv("AGENT_V2_MEMORY_EMBEDDINGS", raising=False)
        fake.get_rows = []
        item = MemoryItem(
            user_id=USER, kind="preference",
            content="prefers oat milk", importance=0.7,
        )
        written = asyncio.run(memory_mod.write_memories(USER, [item]))
        assert len(written) == 1
        _, body = fake.posts[0]
        assert "embedding" not in body
