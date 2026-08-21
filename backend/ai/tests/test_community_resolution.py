"""Community pick + resolve during donor posting flow."""
from __future__ import annotations

import pytest

from backend.ai.conversation_flow import (
    _extract_community_name_from_history,
    _extract_community_name_from_text,
    _match_community_in_catalog,
    enrich_post_food_listing_args,
)
from backend.tools import _best_community_name_match


class TestCommunityExtraction:
    def test_extracts_different_community_from_user_reply(self):
        history = [
            {"role": "assistant", "message": "Should this go under Alameda Unified School District?"},
            {"role": "user", "message": "no, use Do Good Warehouse instead"},
        ]
        name = _extract_community_name_from_history(history)
        assert name is not None
        assert "do good" in name.lower()
        assert "alameda" not in name.lower()

    def test_extracts_list_under_phrase(self):
        assert _extract_community_name_from_text(
            "list it under Oakland High School please"
        ) == "Oakland High School"

    def test_yes_confirms_assistant_suggestion(self):
        history = [
            {"role": "assistant", "message": "List under Alameda Unified School District?"},
            {"role": "user", "message": "yes"},
        ]
        name = _extract_community_name_from_history(history)
        assert name is not None
        assert "alameda" in name.lower()

    def test_picks_by_number_from_catalog(self):
        catalog = [
            {"id": "c1", "name": "Alameda Unified School District"},
            {"id": "c2", "name": "Do Good Warehouse"},
        ]
        hit = _match_community_in_catalog("2", catalog)
        assert hit is not None
        assert hit["id"] == "c2"
        assert "warehouse" in hit["name"].lower()

    def test_fuzzy_match_partial_name(self):
        catalog = [
            {"id": "c1", "name": "Alameda Unified School District"},
            {"id": "c2", "name": "Do Good Warehouse"},
        ]
        hit = _match_community_in_catalog("Do Good", catalog)
        assert hit is not None
        assert hit["id"] == "c2"


class TestEnrichDifferentCommunity:
    def test_enrich_sets_name_and_confirmed_for_different_pick(self):
        history = [
            {"role": "user", "message": "share 5 loaves of bread"},
            {"role": "assistant", "message": "Should this go under Alameda Unified?"},
            {"role": "user", "message": "list it under Do Good Warehouse"},
            {"role": "assistant", "message": "When does it expire?"},
            {"role": "user", "message": "2026-07-15"},
        ]
        out = enrich_post_food_listing_args(
            {"title": "Bread", "qty": 5},
            "yes post it",
            history,
        )
        assert out.get("community_confirmed") is True
        assert out.get("community_name")
        assert "warehouse" in out["community_name"].lower()

    def test_enrich_resolves_from_community_list_in_metadata(self):
        history = [
            {"role": "assistant", "message": "Which community?", "metadata": {"actions": [{
                "tool": "get_active_communities",
                "communities": [
                    {"id": "c1", "name": "Alameda Unified School District"},
                    {"id": "c2", "name": "Do Good Warehouse"},
                ],
            }]}},
            {"role": "user", "message": "the warehouse one"},
        ]
        out = enrich_post_food_listing_args(
            {"title": "Rice", "qty": 10},
            "the warehouse one",
            history,
        )
        assert out.get("community_id") == "c2"
        assert "warehouse" in (out.get("community_name") or "").lower()


class TestBestCommunityNameMatch:
    def test_partial_token_overlap(self):
        rows = [
            {"id": "1", "name": "Do Good Warehouse"},
            {"id": "2", "name": "Alameda Unified School District"},
        ]
        hit = _best_community_name_match("Do Good", rows)
        assert hit is not None
        assert hit["id"] == "1"

    def test_county_maps_to_unified_school(self):
        rows = [
            {"id": "1", "name": "Alameda Unified School District"},
            {"id": "2", "name": "Do Good Warehouse"},
            {"id": "3", "name": "Oakland Unified School District"},
        ]
        hit = _best_community_name_match("Alameda County", rows)
        assert hit is not None
        assert "Alameda" in hit["name"]
        # Unknown county with no catalog match must not invent Alameda.
        assert _best_community_name_match("Contra Costa County", rows) is None

    def test_rejects_unrelated_query(self):
        rows = [{"id": "1", "name": "Alameda Unified School District"}]
        assert _best_community_name_match("xyz nonsense", rows) is None

    def test_nea_aclc_slash_variants(self):
        rows = [
            {"id": "3", "name": "NEA/ACLC CC"},
            {"id": "1", "name": "Alameda Unified School District"},
        ]
        for q in ("NEA/ACLC CC", "NEA / ACLC CC", "nea/aclc", "NEA/ACLC"):
            hit = _best_community_name_match(q, rows)
            assert hit is not None
            assert hit["id"] == "3"

    def test_sanitize_keeps_school_district_suffix(self):
        from backend.tools import _sanitize_community_query
        assert "District" in _sanitize_community_query(
            "Alameda Unified School District"
        )


@pytest.mark.asyncio
async def test_resolve_treats_name_stuffed_into_community_id(monkeypatch):
    from backend.tools import _resolve_community

    catalog = [
        {"id": "3", "name": "NEA/ACLC CC"},
        {"id": "1", "name": "Alameda Unified School District"},
    ]

    async def fake_supabase_get(table, params):
        if table != "communities":
            return []
        name_q = str(params.get("name") or "")
        if name_q.startswith("ilike."):
            needle = name_q[len("ilike."):].strip("%").lower()
            for row in catalog:
                if needle and needle in row["name"].lower():
                    return [row]
        return []

    async def fake_fetch_rows(**_kwargs):
        return catalog

    monkeypatch.setattr("backend.ai_engine.supabase_get", fake_supabase_get)
    monkeypatch.setattr("backend.tools._fetch_all_active_community_rows", fake_fetch_rows)

    cid, cname = await _resolve_community(None, "NEA/ACLC CC")
    assert cid == "3"
    assert cname == "NEA/ACLC CC"

    cid2, cname2 = await _resolve_community('"NEA/ACLC CC"', None)
    assert cid2 == "3"
    assert cname2 == "NEA/ACLC CC"


@pytest.mark.asyncio
async def test_get_active_communities_returns_full_catalog_by_default(monkeypatch):
    from backend.tools import _get_active_communities

    catalog = [
        {"id": "3", "name": "NEA/ACLC CC"},
        {"id": "1", "name": "Alameda Unified School District"},
        {"id": "2", "name": "Do Good Warehouse"},
    ] + [{"id": str(i), "name": f"School {i}"} for i in range(10, 25)]

    async def fake_fetch_rows(**_kwargs):
        return catalog

    monkeypatch.setattr("backend.tools._fetch_all_active_community_rows", fake_fetch_rows)

    result = await _get_active_communities(max_results=100)
    assert not result.get("error")
    names = [c.get("name") for c in (result.get("communities") or [])]
    assert "NEA/ACLC CC" in names
    assert "Alameda Unified School District" in names
    assert (result.get("total") or 0) >= len(names)
    assert len(names) >= 15


@pytest.mark.asyncio
async def test_create_listing_rejects_non_catalog_community(monkeypatch):
    from backend.tools import _create_food_listing

    async def fake_resolve(name, cid):
        return None, None

    async def fake_defaults(uid):
        return {}

    async def fetch_rows(**kwargs):
        return [{"id": "3", "name": "NEA/ACLC CC"}]

    monkeypatch.setattr("backend.tools._resolve_community", fake_resolve)
    monkeypatch.setattr(
        "backend.ai_engine.fetch_donor_listing_defaults", fake_defaults,
    )
    monkeypatch.setattr("backend.tools._fetch_all_active_community_rows", fetch_rows)

    result = await _create_food_listing(
        user_id="00000000-0000-0000-0000-000000000001",
        title="Pizza",
        quantity=1,
        unit="items",
        category="prepared",
        expiry_date="2099-01-01",
        community_name="Fake County",
        community_confirmed=True,
        image_url="https://example.com/p.jpg",
    )
    assert result.get("success") is False
    assert result.get("error") == "community_required"
    assert "NEA/ACLC CC" in (result.get("active_communities") or [])
