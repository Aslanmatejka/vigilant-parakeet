"""Donate flow entity enrichment across multi-turn conversations."""

from backend.agent.planner import enrich_entities_from_conversation


def test_prepared_meal_persists_from_history():
    messages = [
        {"role": "user", "content": "I want to share some food"},
        {"role": "assistant", "content": "What kind of food?"},
        {"role": "user", "content": "Prepared meal"},
        {"role": "assistant", "content": "About how much?"},
        {"role": "user", "content": "4 servings"},
    ]
    entities = enrich_entities_from_conversation(
        "donate", {}, "Pickup", messages,
    )
    assert entities.get("title") == "Prepared meal"
    assert entities.get("quantity") == 4


def test_affirmative_confirms_community_for_post():
    messages = [
        {"role": "assistant", "content": "Should I post this under Alameda Unified?"},
    ]
    entities = enrich_entities_from_conversation(
        "donate",
        {"title": "Prepared meal", "quantity": 4, "community_name": "Alameda Unified"},
        "yes",
        messages,
    )
    assert entities.get("community_confirmed") is True


def test_expiry_from_until_tomorrow():
    entities = enrich_entities_from_conversation(
        "donate",
        {"title": "Prepared meal", "quantity": 4},
        "can stay fresh until tomorrow",
        [{"role": "user", "content": "made today"}],
    )
    assert entities.get("expiry_date")
    assert entities["expiry_date"] > "2020-01-01"


def test_list_under_chip_confirms_community():
    entities = enrich_entities_from_conversation(
        "donate",
        {"title": "Prepared meal", "quantity": 4},
        "Yes, list under Alameda Unified",
        [],
    )
    assert entities.get("community_name") == "Alameda Unified"
    assert entities.get("community_confirmed") is True


def test_does_not_scrape_community_from_assistant_prompt():
    """Regression: assistant 'community' questions must not become community_name."""
    messages = [
        {"role": "assistant", "content": "Great — you want to share food with your community! What food are you sharing?"},
    ]
    entities = enrich_entities_from_conversation(
        "donate", {}, "Rice", messages,
    )
    assert not entities.get("community_name") or entities.get("community_name") == "Alameda Unified"


def test_fresh_share_one_shot_rice():
    entities = enrich_entities_from_conversation(
        "donate",
        {"title": "Eggs", "quantity": 10, "awaiting_post_confirm": True, "community_confirmed": True},
        "i want to share 1 lbs of rice",
        [],
    )
    assert entities.get("title") == "Rice"
    assert entities.get("quantity") == 1
    assert entities.get("awaiting_post_confirm") is not True
    assert entities.get("community_confirmed") is not True


def test_fresh_share_clears_stale_community_confirm():
    entities = enrich_entities_from_conversation(
        "donate",
        {"community_confirmed": True, "community_name": "Alameda Unified", "title": "Rice", "quantity": 5},
        "I want to share food",
        [],
    )
    assert entities.get("community_confirmed") is not True


def test_classifier_quantity_dropped_without_user_number():
    entities = enrich_entities_from_conversation(
        "donate",
        {"title": "eggs", "quantity": 1},
        "eggs",
        [],
    )
    assert entities.get("quantity") is None


def test_user_quantity_kept():
    entities = enrich_entities_from_conversation(
        "donate",
        {"title": "eggs"},
        "10",
        [{"role": "user", "content": "eggs"}],
    )
    assert entities.get("quantity") == 10
    assert entities.get("quantity_stated") is True


def test_skip_photo_sets_flag():
    entities = enrich_entities_from_conversation(
        "donate",
        {"title": "Bread", "quantity": 2, "photo_prompted": True},
        "no photo",
        [{"role": "assistant", "content": "Would you like to add a photo?"}],
    )
    assert entities.get("skip_photo") is True


def test_awaiting_post_confirm_yes():
    entities = enrich_entities_from_conversation(
        "donate",
        {
            "title": "Eggs", "quantity": 10, "quantity_stated": True,
            "community_confirmed": True, "community_name": "Alameda Unified",
            "skip_photo": True, "awaiting_post_confirm": True,
        },
        "yes",
        [],
    )
    assert entities.get("post_confirmed") is True


def test_address_yes_does_not_confirm_community():
    messages = [
        {"role": "assistant", "content": "Should I use your profile address for the pickup spot, or a different address?"},
    ]
    entities = enrich_entities_from_conversation(
        "donate",
        {"title": "Rice", "quantity": 5, "food_type": "rice"},
        "Yes, use that one",
        messages,
    )
    assert entities.get("community_confirmed") is not True

