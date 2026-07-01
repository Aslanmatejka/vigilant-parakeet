"""
AGENT_V2 — Memory + World Model Tests (Phase 3)
================================================

Unit tests for `backend.agent.memory` and `backend.agent.world_model`.

We reuse the `FakeSupabase` pattern from `test_agent_v2_actions.py` to
exercise the supabase-backed paths without touching the real network.

Scenarios:
  Memory module:
   1.  extract_salient_facts — dietary / allergy / preference / style /
        location patterns + dedup + non-matching messages.
   2.  score_memory_relevance — empty / no-overlap / full-overlap /
        partial / stopword robustness.
   3.  retrieve_relevant_memories — ranks by relevance + keeps high-
        importance dietary facts even with no keyword overlap.
   4.  write_memories — writes new rows, skips duplicates, ignores
        empty content.
   5.  privacy_disclosure_text — en / es.

  World model:
   6.  build_world_snapshot — empty user / nil-UUID short-circuit.
   7.  build_world_snapshot — populated profile + claims + listings.
   8.  WorldSnapshot.render_block — empty vs populated.
   9.  Status filtering — only "open" claims and "active" listings
        are counted.

Run:
    python -m pytest backend/tests/test_agent_v2_memory.py -v
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import pytest

from backend.agent.memory import (
    KIND_DIETARY,
    MemoryItem,
    extract_salient_facts,
    privacy_disclosure_text,
    retrieve_relevant_memories,
    score_memory_relevance,
    write_memories,
)
from backend.agent.world_model import (
    WorldSnapshot,
    build_world_snapshot,
)


USER = "33333333-3333-3333-3333-333333333333"


# ============================================================================
# FakeSupabase — copy of the helper from test_agent_v2_actions.py, scoped
# to just the GET/POST methods this suite needs.
# ============================================================================

class FakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {}

    @staticmethod
    def _matches(row: dict[str, Any], filters: dict[str, Any]) -> bool:
        for k, v in filters.items():
            if k in ("select", "limit", "order"):
                continue
            if not isinstance(v, str):
                continue
            if v.startswith("eq."):
                if str(row.get(k)) != v[3:]:
                    return False
        return True

    async def supabase_get(self, table: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        rows = list(self.tables.get(table, []))
        out = [r for r in rows if self._matches(r, params)]
        limit = params.get("limit")
        if limit:
            try:
                out = out[: int(limit)]
            except Exception:
                pass
        return out

    async def supabase_post(self, table: str, body: dict[str, Any]) -> list[dict[str, Any]]:
        rows = self.tables.setdefault(table, [])
        body = dict(body)
        body.setdefault("id", str(uuid.uuid4()))
        rows.append(body)
        return [body]


@pytest.fixture
def fake_supabase(monkeypatch: pytest.MonkeyPatch) -> FakeSupabase:
    fake = FakeSupabase()
    import backend.ai_engine as ai_engine

    monkeypatch.setattr(ai_engine, "supabase_get", fake.supabase_get, raising=False)
    monkeypatch.setattr(ai_engine, "supabase_post", fake.supabase_post, raising=False)
    return fake


# ============================================================================
# 1. extract_salient_facts
# ============================================================================

def test_extract_dietary_vegan() -> None:
    facts = extract_salient_facts("hey, by the way I'm vegan", user_id=USER)
    assert len(facts) == 1
    assert facts[0].kind == "dietary"
    assert "vegan" in facts[0].content.lower()
    assert facts[0].importance >= 0.8


def test_extract_allergy_high_importance() -> None:
    facts = extract_salient_facts("I'm allergic to peanuts and shellfish", user_id=USER)
    assert any(f.kind == "dietary" and "peanuts" in f.content.lower() for f in facts)
    # Allergies should be the highest-importance bucket.
    allergy = next(f for f in facts if "allergic" in f.content.lower())
    assert allergy.importance >= 0.9


def test_extract_preference() -> None:
    facts = extract_salient_facts("I really like sourdough bread", user_id=USER)
    assert any(f.kind == "preference" for f in facts)


def test_extract_style_brief() -> None:
    facts = extract_salient_facts("please keep it short", user_id=USER)
    assert any(f.kind == "style" and "short" in f.content.lower() for f in facts)


def test_extract_style_language() -> None:
    facts = extract_salient_facts("please reply in Spanish from now on", user_id=USER)
    assert any(f.kind == "style" and "spanish" in f.content.lower() for f in facts)


def test_extract_relationship_location() -> None:
    facts = extract_salient_facts("I live in Austin, Texas", user_id=USER)
    assert any(f.kind == "relationship" for f in facts)


def test_extract_chitchat_returns_empty() -> None:
    assert extract_salient_facts("hi how are you", user_id=USER) == []


def test_extract_empty_string() -> None:
    assert extract_salient_facts("", user_id=USER) == []
    assert extract_salient_facts("   ", user_id=USER) == []


def test_extract_dedups_identical_content() -> None:
    """If two regex paths happen to surface the same content for a single
    message, we should only return one MemoryItem."""
    facts = extract_salient_facts(
        "I'm vegan. I'm vegan. I'm vegan.", user_id=USER,
    )
    contents = {f.content.lower() for f in facts}
    assert len(facts) == len(contents)  # no dupes after lowercasing


# ============================================================================
# 2. score_memory_relevance
# ============================================================================

def test_score_empty_query() -> None:
    assert score_memory_relevance("User is vegan", "") == 0.0


def test_score_no_overlap() -> None:
    assert score_memory_relevance("User is vegan", "nearest bus stop") == 0.0


def test_score_identical() -> None:
    assert score_memory_relevance("vegan bread", "vegan bread") == 1.0


def test_score_partial_overlap() -> None:
    s = score_memory_relevance("User is vegan", "vegan options nearby")
    assert 0.0 < s < 1.0


def test_score_ignores_stopwords() -> None:
    """The /me/I/the tokens should not lift the score on their own."""
    s = score_memory_relevance("User", "the the the the")
    assert s == 0.0


# ============================================================================
# 3. retrieve_relevant_memories
# ============================================================================

@pytest.mark.asyncio
async def test_retrieve_ranks_by_relevance(fake_supabase: FakeSupabase) -> None:
    fake_supabase.tables["agent_user_facts"] = [
        {"id": "a", "user_id": USER, "kind": "preference",
         "content": "User prefers sourdough", "importance": 0.5},
        {"id": "b", "user_id": USER, "kind": "preference",
         "content": "User prefers pizza", "importance": 0.5},
        {"id": "c", "user_id": "other", "kind": "preference",
         "content": "User prefers sourdough", "importance": 0.9},  # different user
    ]
    out = await retrieve_relevant_memories(USER, "looking for sourdough bread", limit=3)
    contents = [m.content for m in out]
    assert "User prefers sourdough" in contents
    # Other user's row must never leak.
    assert all(m.user_id == USER for m in out)


@pytest.mark.asyncio
async def test_retrieve_keeps_high_importance_allergy(
    fake_supabase: FakeSupabase,
) -> None:
    """Allergies must survive retrieval even with zero keyword overlap."""
    fake_supabase.tables["agent_user_facts"] = [
        {"id": "a", "user_id": USER, "kind": KIND_DIETARY,
         "content": "User is allergic to peanuts", "importance": 0.95},
        {"id": "b", "user_id": USER, "kind": "preference",
         "content": "User prefers pizza", "importance": 0.4},
    ]
    out = await retrieve_relevant_memories(USER, "tell me about Friday's pickup", limit=3)
    assert any(m.kind == "dietary" and "peanut" in m.content.lower() for m in out)


@pytest.mark.asyncio
async def test_retrieve_empty_user_returns_empty() -> None:
    assert await retrieve_relevant_memories("", "anything", limit=3) == []


@pytest.mark.asyncio
async def test_retrieve_no_rows(fake_supabase: FakeSupabase) -> None:
    """User with no facts → empty list, not a crash."""
    out = await retrieve_relevant_memories(USER, "vegan bread", limit=3)
    assert out == []


# ============================================================================
# 4. write_memories
# ============================================================================

@pytest.mark.asyncio
async def test_write_inserts_new_rows(fake_supabase: FakeSupabase) -> None:
    facts = [
        MemoryItem(user_id=USER, kind="dietary",
                   content="User is vegan", importance=0.85),
        MemoryItem(user_id=USER, kind="style",
                   content="User prefers brief replies", importance=0.5),
    ]
    written = await write_memories(USER, facts, source_turn_id="t-1")
    assert len(written) == 2
    table = fake_supabase.tables.get("agent_user_facts", [])
    assert len(table) == 2
    # Every persisted row carries the turn id.
    assert all(r.get("source_turn_id") == "t-1" for r in table)


@pytest.mark.asyncio
async def test_write_skips_duplicates(fake_supabase: FakeSupabase) -> None:
    fake_supabase.tables["agent_user_facts"] = [
        {"id": "x", "user_id": USER, "kind": "dietary",
         "content": "User is vegan", "importance": 0.85},
    ]
    facts = [
        MemoryItem(user_id=USER, kind="dietary",
                   content="User is vegan", importance=0.85),
    ]
    written = await write_memories(USER, facts)
    assert written == []
    # Still just one row.
    assert len(fake_supabase.tables["agent_user_facts"]) == 1


@pytest.mark.asyncio
async def test_write_ignores_empty_content(fake_supabase: FakeSupabase) -> None:
    facts = [MemoryItem(user_id=USER, content="")]
    written = await write_memories(USER, facts)
    assert written == []


@pytest.mark.asyncio
async def test_write_empty_user_returns_empty() -> None:
    facts = [MemoryItem(user_id="", content="x")]
    assert await write_memories("", facts) == []


# ============================================================================
# 5. privacy_disclosure_text
# ============================================================================

def test_privacy_disclosure_en() -> None:
    s = privacy_disclosure_text("en")
    assert "remember" in s.lower()
    assert "forget about me" in s.lower()


def test_privacy_disclosure_es() -> None:
    s = privacy_disclosure_text("es")
    assert "recordar" in s.lower()
    assert "olvídate de mí" in s.lower()


# ============================================================================
# 6. build_world_snapshot — empty user / anonymous
# ============================================================================

@pytest.mark.asyncio
async def test_world_snapshot_anonymous_short_circuits() -> None:
    snap = await build_world_snapshot("00000000-0000-0000-0000-000000000000")
    assert snap.is_empty()
    assert snap.render_block() == ""


@pytest.mark.asyncio
async def test_world_snapshot_unknown_user_returns_empty(
    fake_supabase: FakeSupabase,
) -> None:
    snap = await build_world_snapshot(USER)
    assert snap.is_empty()


# ============================================================================
# 7 + 9. build_world_snapshot populated
# ============================================================================

@pytest.mark.asyncio
async def test_world_snapshot_populated(fake_supabase: FakeSupabase) -> None:
    fake_supabase.tables["users"] = [{
        "id": USER,
        "full_name": "Alex",
        "address": "123 Main St",
        "dietary_restrictions": ["vegan"],
        "allergies": "peanuts, shellfish",
        "communities": ["austin-food-share"],
    }]
    fake_supabase.tables["food_claims"] = [
        {"id": "c1", "claimer_id": USER, "status": "pending",
         "created_at": "2026-06-25", "listing_id": "L1"},
        {"id": "c2", "claimer_id": USER, "status": "cancelled",
         "created_at": "2026-06-24", "listing_id": "L2"},
        {"id": "c3", "claimer_id": USER, "status": "approved",
         "created_at": "2026-06-23", "listing_id": "L3"},
    ]
    fake_supabase.tables["food_listings"] = [
        {"id": "L4", "donor_id": USER, "title": "bread", "status": "available"},
        {"id": "L5", "donor_id": USER, "title": "soup", "status": "expired"},
    ]

    snap = await build_world_snapshot(USER, is_admin=False)

    assert snap.user_name == "Alex"
    assert snap.address == "123 Main St"
    assert "vegan" in snap.dietary_restrictions
    assert {"peanuts", "shellfish"}.issubset(set(snap.allergies))
    assert snap.communities == ["austin-food-share"]
    # Only pending+approved should count; cancelled is filtered.
    assert snap.open_claims_count == 2
    # Only available listings should count.
    assert snap.open_listings_count == 1
    assert not snap.is_empty()


@pytest.mark.asyncio
async def test_world_snapshot_render_block(fake_supabase: FakeSupabase) -> None:
    fake_supabase.tables["users"] = [{
        "id": USER, "full_name": "Sam",
        "dietary_restrictions": ["vegetarian"],
        "allergies": [],
    }]
    snap = await build_world_snapshot(USER)
    block = snap.render_block()
    assert block.startswith("<world>")
    assert block.endswith("</world>")
    assert "Sam" in block
    assert "vegetarian" in block


def test_world_snapshot_empty_renders_blank() -> None:
    snap = WorldSnapshot(user_id=USER)
    assert snap.render_block() == ""
    assert snap.is_empty()
