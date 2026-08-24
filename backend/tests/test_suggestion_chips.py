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
        assert any(
            l and ("Claim #1 & #2" in l or "Claim both" in l)
            for l in labels
        )
        assert not any("Find food near me" in (l or "") for l in labels)
        # Prefer Claim #N over duplicate bare "1"/"2" quick-replies.
        assert "1" not in labels

    def test_flat_nouri_search_actions_get_claim_chips(self):
        """Live engine flattens listings onto the action (no nested result)."""
        tool_results = [{
            "tool": "search_food_near_user",
            "ok": True,
            "listings": [
                {"title": "Sourdough"},
                {"title": "Apples"},
            ],
            "total": 2,
        }]
        chips = build_turn_suggestions(
            "Here are the closest options. Which number?",
            "en",
            tool_results=tool_results,
        )
        labels = [c if isinstance(c, str) else c.get("label") for c in chips]
        assert any("Claim #1" in (l or "") for l in labels)
        assert any("Sourdough" in (l or "") for l in labels)
        assert any(
            l and ("Claim #1 & #2" in l or "Claim both" in l)
            for l in labels
        )

    def test_multi_claim_confirm_chips(self):
        chips = build_turn_suggestions(
            "Ready to claim these? 2× bread and 3× apples.",
            "en",
            tool_results=[],
        )
        labels = [c if isinstance(c, str) else c.get("label") for c in chips]
        assert any(l and "Yes, claim these" in l for l in labels)

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
        assert "Different one" in labels
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
        assert "Different one" not in labels
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


    def test_guided_step_gets_done_chips(self):
        text = (
            "GUIDED — STEP 1 of 9 (SHARE FOOD — Open Share Food):\n"
            "Click Name / Organization and type your name. "
            "When finished, say 'done' or 'what's next'."
        )
        chips = build_turn_suggestions(text, "en", tool_results=[], min_chips=0)
        labels = [c if isinstance(c, str) else c.get("label") for c in chips]
        assert "Done" in labels
        assert "What's next?" in labels
        assert "Yes" not in labels
        assert "Yes, post it" not in labels

    def test_headerless_guided_open_page_not_fork_chips(self):
        """After Guide me, model often drops GUIDED header — still not fork chips."""
        text = (
            "You got it! First, please open the Share Food page by tapping "
            "Share Food on the main menu. Let me know when you see the form "
            "and we'll go to the next step together."
        )
        chips = build_turn_suggestions(
            text,
            "en",
            tool_results=[],
            min_chips=0,
            last_user_message="Guide me step by step",
            assistance_reminder="GUIDED MODE: coach one baby step at a time.",
        )
        labels = [c if isinstance(c, str) else c.get("label") for c in chips]
        assert "Open the form" not in labels
        assert "Do it for me" not in labels
        assert "Guide me step by step" not in labels
        assert "Done" in labels
        assert "I see the form" in labels or "What's next?" in labels

    def test_guided_donor_type_gets_role_chips(self):
        text = (
            "GUIDED — STEP 2 of 9 (SHARE FOOD — Donor Information):\n"
            "Find Donor Type and choose Individual/Family or Organization. "
            "Say 'done' when selected."
        )
        chips = build_turn_suggestions(text, "en", tool_results=[], min_chips=0)
        labels = [c if isinstance(c, str) else c.get("label") for c in chips]
        assert any("Individual" in (l or "") for l in labels)
        assert any("Organization" in (l or "") for l in labels)

    def test_single_claim_qty_not_multi_each_chips(self):
        text = "Nice choice! How many of the Fresh Bread would you like? They have 5 available."
        chips = build_turn_suggestions(text, "en", tool_results=[], min_chips=0)
        labels = [c if isinstance(c, str) else c.get("label") for c in chips]
        assert "2 each" not in labels
        assert "1" in labels or "2" in labels or "All of them" in labels

    def test_ready_to_claim_no_generic_yes_no(self):
        chips = build_turn_suggestions(
            "Ready to claim these? 2× bread and 3× apples.",
            "en",
            tool_results=[],
            min_chips=0,
        )
        labels = [c if isinstance(c, str) else c.get("label") for c in chips]
        assert any(l and "Yes, claim these" in l for l in labels)
        assert "Yes" not in labels
        assert "Later" not in labels

    def test_community_question_not_post_chips(self):
        text = (
            "Which community should I list the 10 loaves of bread under? "
            "Your profile is set to Alameda Unified—should I post it there?"
        )
        chips = build_turn_suggestions(text, "en", tool_results=[], min_chips=0)
        labels = [c if isinstance(c, str) else c.get("label") for c in chips]
        assert "Alameda Unified" in labels
        assert "Yes, post it" not in labels

    def test_photo_required_no_question_gets_upload_chips(self):
        chips = build_turn_suggestions(
            "Please upload a photo of the food — required before posting.",
            "en",
            tool_results=[],
            min_chips=0,
        )
        labels = [c if isinstance(c, str) else c.get("label") for c in chips]
        assert any(l and "attach" in (l or "").lower() for l in labels)
        assert not any(l and ("skip" in (l or "").lower() or "already" in (l or "").lower()) for l in labels)

    def test_assistance_reminder_forces_fork(self):
        chips = build_turn_suggestions(
            "Sure — happy to help.",
            "en",
            tool_results=[],
            min_chips=0,
            last_user_message="I want to share food",
            assistance_reminder=(
                "ASSISTANCE MODE (required this turn):\nAsk ONCE how they want help."
            ),
        )
        labels = [c if isinstance(c, str) else c.get("label") for c in chips]
        assert labels == [
            "Open the form",
            "Do it for me",
            "Guide me step by step",
        ]

    def test_single_claim_confirm_not_multi(self):
        chips = build_turn_suggestions(
            "Shall I claim listing #12 for you?",
            "en",
            tool_results=[],
            min_chips=0,
        )
        labels = [c if isinstance(c, str) else c.get("label") for c in chips]
        assert "Yes, claim it" in labels
        assert "Yes, claim these" not in labels
        assert "Yes" not in labels

    def test_vague_share_proceed_not_yes_no(self):
        chips = build_turn_suggestions(
            "How would you like to proceed with sharing?",
            "en",
            tool_results=[],
            min_chips=0,
            last_user_message="I want to share food",
        )
        labels = [c if isinstance(c, str) else c.get("label") for c in chips]
        assert "Open the form" in labels
        assert "Yes" not in labels
        assert "Later" not in labels

    def test_find_fork_not_open_the_form(self):
        chips = build_turn_suggestions(
            "Want me to handle the search for you, or guide you on Find Food step by step?",
            "en",
            tool_results=[],
            min_chips=0,
            last_user_message="I want to find food",
        )
        labels = [c if isinstance(c, str) else c.get("label") for c in chips]
        assert labels[0] == "Open Find Food"
        assert "Open the form" not in labels
        assert "Do it for me" in labels

    def test_find_fork_already_on_page_omits_open(self):
        chips = build_turn_suggestions(
            "Want me to handle the search, or guide you step by step?",
            "en",
            tool_results=[],
            min_chips=0,
            last_user_message="find food near me",
            user_context={"pageKey": "find", "path": "/find"},
        )
        labels = [c if isinstance(c, str) else c.get("label") for c in chips]
        assert "Open the form" not in labels
        assert labels == ["Open Find Food", "Do it for me", "Guide me step by step"]
