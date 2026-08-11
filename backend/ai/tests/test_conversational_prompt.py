"""Guards ensuring Nouri's system prompt stays conversational, not form-like.

If someone re-introduces scripted `Turn 1 / Turn 2 / Step N` language or the
old 1000-line hard-rules block, these tests should catch the regression.
"""
from __future__ import annotations

from backend.ai.ai_engine import (
    _build_action_policy,
    _build_system_prompt,
    _load_training_data,
)


class TestActionPolicyIsConversational:
    """The prompt should give principles, not scripts."""

    def test_no_numbered_turn_language(self):
        policy = _build_action_policy()
        lowered = policy.lower()
        for banned in ("turn 1", "turn 2", "turn 3", "step 1", "step 2", "step 3"):
            assert banned not in lowered, (
                f"Prompt reintroduced scripted turn language: {banned!r}."
            )

    def test_no_full_worked_dialogs(self):
        """The old prompt shipped 3+ full worked dialogs verbatim ('Donor: ... AI: ...').

        Those made the model imitate the wording. Keep worked examples out of
        the live prompt — training data / evals belong elsewhere.
        """
        policy = _build_action_policy()
        assert "Donor: '" not in policy, "Scripted 'Donor:' dialog crept back in."
        assert "AI:    '" not in policy, "Scripted 'AI:' dialog crept back in."

    def test_size_is_bounded(self):
        """Refactor target: keep the behavioural policy compact.

        The previous version was ~40k chars of instructions; this hard cap
        is deliberately generous but catches a regression where someone
        pastes the old giant block back in.
        """
        # Cap allows intentional guidance growth (requests, multi-claim, etc.)
        # while still catching a return to the old ~40k scripted block.
        assert len(_build_action_policy()) < 24_000, (
            "Action policy is drifting back toward the 40k-char scripted prompt."
        )

    def test_preserves_safety_critical_rules(self):
        """Even after slimming, the prompt must still teach the model:

        - never fake success
        - community must be confirmed before posting
        - expiry / expiration is required
        - listing_id must come from prior search / get_user_listings
        - no live GPS
        - photo yes ≠ permission to post
        """
        policy = _build_action_policy().lower()
        for needle in (
            "never fake success",
            "community",
            "expir",
            "listing id resolution",
            "no live gps",
            "ambiguous 'yes'",
        ):
            assert needle in policy, f"Missing safety-critical guidance: {needle!r}"


class TestSystemPromptShape:
    def test_system_prompt_composes_sections(self):
        prompt = _build_system_prompt(_load_training_data(), "warm")
        assert "Nouri" in prompt
        assert "Action-Taking Policy" not in prompt or "How to behave" in prompt

    def test_system_prompt_much_smaller_than_before(self):
        prompt = _build_system_prompt(_load_training_data(), "warm")
        # Historical ~40k; allow modest growth for new flows, still block regression.
        assert len(prompt) < 28_000, (
            f"System prompt grew back to {len(prompt)} chars — check for "
            "scripted dialogs or duplicated rules."
        )
