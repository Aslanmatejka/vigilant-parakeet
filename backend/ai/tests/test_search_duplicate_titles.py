"""Tests for duplicate listing title grouping in search results."""
from backend.tools import _annotate_duplicate_listings, _normalize_listing_title_key


def test_normalize_title_strips_test_prefix():
    assert _normalize_listing_title_key("Test Tomatoes") == _normalize_listing_title_key("Tomatoes")


def test_annotate_duplicate_listings_tags_same_title():
    rows = [
        {"id": "a", "title": "Tomatoes", "quantity": 10},
        {"id": "b", "title": "Tomatoes", "quantity": 10},
        {"id": "c", "title": "Eggs", "quantity": 5},
    ]
    dupes = _annotate_duplicate_listings(rows)
    assert len(dupes) == 1
    assert rows[0]["same_title_count"] == 2
    assert rows[1]["same_title_count"] == 2
    assert rows[2]["same_title_count"] == 1
    assert set(rows[0]["same_title_listing_ids"]) == {"a", "b"}
