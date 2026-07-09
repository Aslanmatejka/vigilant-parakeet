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

    def test_rejects_unrelated_query(self):
        rows = [{"id": "1", "name": "Alameda Unified School District"}]
        assert _best_community_name_match("xyz nonsense", rows) is None
