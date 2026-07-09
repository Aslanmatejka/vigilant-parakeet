"""Repeat-last-action: 'and this too' / 'same for #2'."""
from __future__ import annotations

from backend.ai.conversation_flow import (
    enrich_repeat_write_action,
    is_repeat_followup,
    set_last_donor_listings,
    set_last_write_action,
)


def test_is_repeat_followup_detects_and_this_too():
    assert is_repeat_followup("and this too", [{"role": "assistant", "message": "Updated apples."}])
    assert is_repeat_followup("same for #3", [])
    assert not is_repeat_followup("thanks", [])


def test_enrich_repeat_write_action_applies_last_fields_to_new_listing():
    listings = [
        {"id": "aaaa-1111", "title": "Apples", "display_index": 1},
        {"id": "bbbb-2222", "title": "Milk", "display_index": 2},
    ]
    set_last_donor_listings("u1", listings)
    set_last_write_action(
        "u1",
        "update_food_listing",
        {"listing_id": "aaaa-1111", "community_name": "Alameda USD"},
        {"listing_id": "aaaa-1111", "success": True},
    )
    args = enrich_repeat_write_action(
        "update_food_listing",
        {},
        "and the milk one too",
        [],
        "u1",
    )
    assert args.get("community_name") == "Alameda USD"
    assert args.get("listing_id") == "bbbb-2222"


def test_enrich_repeat_skips_when_not_followup():
    set_last_write_action(
        "u1",
        "update_food_listing",
        {"community_name": "Alameda USD"},
        {"listing_id": "aaaa-1111"},
    )
    args = enrich_repeat_write_action(
        "update_food_listing",
        {"listing_id": "bbbb-2222", "quantity": 5},
        "change quantity to 5",
        [],
        "u1",
    )
    assert args.get("quantity") == 5
    assert "community_name" not in args
