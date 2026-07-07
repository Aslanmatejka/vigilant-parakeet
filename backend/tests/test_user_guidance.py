"""Tests for confused / vague user guidance heuristics."""

from backend.agent.user_guidance import (
    assess_user_turn,
    format_welcome_menu,
    resolve_guided_response,
)


class TestAssessUserTurn:
    def test_greeting_gets_menu(self):
        a = assess_user_turn("hi", [], "general", confidence=0.9)
        assert a.guide_mode == "menu"

    def test_orphan_yes_without_question(self):
        prior = [{"role": "assistant", "content": "Here are some listings."}]
        a = assess_user_turn("yes", prior, "claim", confidence=0.9)
        assert a.is_orphan_reply
        assert a.guide_mode == "orphan_reply"

    def test_yes_after_confirm_question_ok(self):
        prior = [{"role": "assistant", "content": "Want me to claim the bread for you?"}]
        a = assess_user_turn("yes", prior, "claim", confidence=0.9)
        assert not a.is_orphan_reply

    def test_hungry_overrides_to_search(self):
        a = assess_user_turn("I'm hungry", [], "general", confidence=0.8)
        assert a.override_intent == "search"

    def test_vague_claim_searches_first(self):
        a = assess_user_turn("claim", [], "claim", confidence=0.8)
        assert a.override_intent == "search"
        assert a.guide_mode == "claim_needs_pick"

    def test_numbered_claim_is_actionable(self):
        a = assess_user_turn("Claim #1", [], "claim", confidence=0.9)
        assert a.override_intent == "claim"
        assert a.guide_mode != "claim_needs_pick"


class TestGuidedResponses:
    def test_menu_not_empty(self):
        assert "Find food" in format_welcome_menu("en")
        assert "Buscar comida" in format_welcome_menu("es")

    def test_resolve_returns_none_llm_handles(self):
        assert resolve_guided_response("menu", "en") is None
