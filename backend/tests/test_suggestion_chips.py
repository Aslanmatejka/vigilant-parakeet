"""Tests for unified suggestion chip generation."""

from backend.agent.suggestion_chips import (
    build_turn_suggestions,
    get_lazy_default_chips,
    get_menu_chips,
)


class TestMenuChips:
    def test_english_menu(self):
        chips = get_menu_chips("en")
        assert "Find food near me" in chips
        assert len(chips) >= 4

    def test_spanish_menu(self):
        chips = get_menu_chips("es")
        assert any("comida" in c.lower() for c in chips)


class TestLazyDefaults:
    def test_no_generic_fallback_chips(self):
        assert get_lazy_default_chips("en") == []
        assert get_lazy_default_chips("en", guide_mode="menu") == []


class TestBuildTurnSuggestions:
    def test_yes_no_question_gets_chips(self):
        text = "Would you like me to claim this listing for you?"
        chips = build_turn_suggestions(text, "en", tool_results=[])
        labels = [c if isinstance(c, str) else c.get("label") for c in chips]
        assert any("yes" in (l or "").lower() for l in labels)

    def test_empty_response_no_generic_chips(self):
        chips = build_turn_suggestions("", "en", tool_results=[])
        assert chips == []

    def test_search_results_get_claim_chips(self):
        tool_results = [{
            "tool": "search_food_listings",
            "ok": True,
            "result": {
                "results": [
                    {"title": "Fresh Bread"},
                    {"title": "Vegetable Box"},
                ],
            },
        }]
        chips = build_turn_suggestions(
            "Which one would you like? 1. Fresh Bread 2. Vegetable Box",
            "en",
            tool_results=tool_results,
        )
        labels = [c if isinstance(c, str) else c.get("label") for c in chips]
        assert any("Claim #1" in (l or "") for l in labels)
        assert not any("Find food near me" in (l or "") for l in labels)

    def test_contextual_chips_not_padded_with_lazy_defaults(self):
        text = "Would you like me to claim this listing for you?"
        chips = build_turn_suggestions(text, "en", tool_results=[])
        labels = [c if isinstance(c, str) else c.get("label") for c in chips]
        assert any("yes" in (l or "").lower() for l in labels)
        assert not any("Find food near me" in (l or "") for l in labels)

    def test_proactive_objects_normalized(self):
        chips = build_turn_suggestions(
            "Hello!",
            "en",
            pending_suggestions=[{
                "type": "reminder",
                "message": "You have a pickup tomorrow",
                "action_label": "View pickup",
                "priority": "high",
                "action_required": True,
            }],
            min_chips=1,
        )
        assert any(
            (c.get("label") if isinstance(c, dict) else c) == "View pickup"
            for c in chips
        )

    def test_dedupes_labels(self):
        chips = build_turn_suggestions(
            "",
            "en",
            pending_suggestions=["Find food near me", "Find food near me"],
            min_chips=4,
        )
        labels = [c if isinstance(c, str) else c.get("label") for c in chips]
        assert labels.count("Find food near me") <= 1

    def test_community_prompt_shows_named_chips(self):
        text = (
            "Which community should I list the 10 loaves of bread under? "
            "Your profile is set to Alameda Unified—should I post it there, "
            "or would you like a different community?"
        )
        chips = build_turn_suggestions(text, "en", tool_results=[])
        labels = [c if isinstance(c, str) else c.get("label") for c in chips]
        assert "Alameda Unified" in labels
        assert "Different community" in labels
        assert not any("Yes, post it" == (l or "") for l in labels)

    def test_community_chips_from_tool_suggestion(self):
        text = "Which community should I list this under?"
        tool_results = [{
            "tool": "post_food_listing",
            "ok": False,
            "result": {"suggested_community_name": "Oakland USD"},
        }]
        chips = build_turn_suggestions(
            text,
            "en",
            tool_results=tool_results,
            user_context={"last_intent_entities": {"community_name": "Oakland USD"}},
        )
        labels = [c if isinstance(c, str) else c.get("label") for c in chips]
        assert "Oakland USD" in labels

    def test_community_chip_message_is_confirming(self):
        text = (
            "Which community should I list this under? "
            "Your profile is connected to Alameda Unified — should I post there?"
        )
        chips = build_turn_suggestions(text, "en", tool_results=[])
        named = next(c for c in chips if isinstance(c, dict) and c.get("label") == "Alameda Unified")
        assert "Alameda Unified" in named.get("message", "")

    def test_community_chips_filter_address_and_greeting_noise(self):
        text = (
            "Perfect, pickup at 1423 Park St, Alameda, CA. "
            "Which community should I list these oranges under? "
            "Your profile is linked to Alameda Unified—should I use that, or "
            "would you like a different community?"
        )
        chips = build_turn_suggestions(text, "en", tool_results=[])
        labels = [c if isinstance(c, str) else c.get("label") for c in chips]
        assert "Alameda Unified" in labels
        assert "Perfect" not in labels
        assert "Park St" not in labels
        assert "linked to Alameda Unified" not in labels

    def test_community_followup_shows_all_communities_after_different(self):
        text = (
            "Thanks for letting me know! Which community should I list your "
            "basket of oranges under? Just tell me the name of the school or "
            "group you want to share with."
        )
        active = [
            {"id": "1", "name": "DoGoods Warehouse"},
            {"id": "2", "name": "Oakland USD"},
            {"id": "3", "name": "Alameda Unified"},
        ]
        chips = build_turn_suggestions(
            text,
            "en",
            tool_results=[],
            user_context={
                "last_intent_entities": {"community_name": "Alameda Unified"},
                "active_communities": active,
            },
            last_user_message="Use a different community",
        )
        labels = [c if isinstance(c, str) else c.get("label") for c in chips]
        assert "DoGoods Warehouse" in labels
        assert "Oakland USD" in labels
        assert "Alameda Unified" not in labels
        assert "Different community" not in labels
        assert "Thanks" not in labels

    def test_community_list_from_get_active_communities_tool(self):
        text = (
            "Which community should I list this under? "
            "Pick one from the active communities below."
        )
        tool_results = [{
            "tool": "get_active_communities",
            "ok": True,
            "result": {
                "communities": [
                    {"id": "a", "name": "DoGoods Warehouse"},
                    {"id": "b", "name": "Mission Hub"},
                ],
            },
        }]
        chips = build_turn_suggestions(
            text,
            "en",
            tool_results=tool_results,
            last_user_message="Use a different community",
        )
        labels = [c if isinstance(c, str) else c.get("label") for c in chips]
        assert "DoGoods Warehouse" in labels
        assert "Mission Hub" in labels
