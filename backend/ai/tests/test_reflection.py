"""Reflection / metacognition layer tests.

The reflection module gives Nouri a self-check pass every turn so it
can catch its own mistakes before hitting the user with them:
repeated questions, missed corrections, tool loops, hallucinated
success claims. These tests lock the individual detectors AND the
reminder assembly.

Structure:
  * TestRepeatedQuestion — near-duplicate question detection
  * TestUserCorrection — 'no, I meant…' recognition
  * TestUserFrustration — 'you already asked' / repetition
  * TestShorteningReplies — losing-the-user signal
  * TestTopicPivot — user changed subject mid-flow
  * TestHallucinatedSuccess — assistant claim without a tool call
  * TestToolLoop / TestFailureRate — state-based detectors
  * TestBuildReminder — silent-by-default + firing on real signals
  * TestPostTurnCapture — outcomes recorded, notes stored
"""
from __future__ import annotations

import pytest

from backend.ai.reflection import (
    ReflectionSignals,
    assess_turn,
    build_reflection_reminder,
    capture_post_turn_reflection,
    detect_hallucinated_success,
    detect_repeated_assistant_question,
    detect_shortening_user_replies,
    detect_tool_loop,
    detect_topic_pivot,
    detect_user_correction,
    detect_user_frustration,
    get_reflection_state,
    record_tool_outcome,
    recent_tool_failure_rate,
    reset_reflection_state,
)


@pytest.fixture(autouse=True)
def _fresh_reflection_state():
    """Guarantee each test starts with an empty per-user state."""
    reset_reflection_state("u-test")
    yield
    reset_reflection_state("u-test")


# ---------------------------------------------------------------------------
# Repeated question
# ---------------------------------------------------------------------------


class TestRepeatedQuestion:
    def test_two_near_duplicate_questions_flagged(self):
        history = [
            {"role": "assistant", "message": "Which community should this go under?"},
            {"role": "user", "message": "Alameda Unified"},
            {"role": "assistant", "message": "So — which community should this go under?"},
        ]
        hit = detect_repeated_assistant_question(history)
        assert hit is not None
        assert "community" in hit

    def test_distinct_questions_not_flagged(self):
        history = [
            {"role": "assistant", "message": "Which community?"},
            {"role": "user", "message": "Alameda"},
            {"role": "assistant", "message": "And when does it expire?"},
        ]
        assert detect_repeated_assistant_question(history) is None

    def test_single_question_not_flagged(self):
        history = [
            {"role": "assistant", "message": "Which community?"},
        ]
        assert detect_repeated_assistant_question(history) is None

    def test_empty_history_safe(self):
        assert detect_repeated_assistant_question([]) is None
        assert detect_repeated_assistant_question(None) is None


# ---------------------------------------------------------------------------
# User correction / frustration
# ---------------------------------------------------------------------------


class TestUserCorrection:
    @pytest.mark.parametrize("msg", [
        "no, I meant the oranges",
        "actually, let's do the apples instead",
        "wait, that's not what I said",
        "the other bread listing",
        "no era eso",
        "en realidad, quise decir el pan",
    ])
    def test_correction_positive(self, msg):
        assert detect_user_correction(msg)

    @pytest.mark.parametrize("msg", [
        "yes please",
        "sounds good",
        "post it",
        "here you go",
    ])
    def test_correction_negative(self, msg):
        assert not detect_user_correction(msg)

    def test_empty_safe(self):
        assert not detect_user_correction("")
        assert not detect_user_correction(None)  # type: ignore[arg-type]


class TestUserFrustration:
    @pytest.mark.parametrize("msg", [
        "you already asked me that",
        "I already told you",
        "why are you asking again?",
        "for the third time — Alameda Unified",
        "ya te dije que Alameda",
    ])
    def test_frustration_positive(self, msg):
        assert detect_user_frustration(msg)

    def test_neutral_not_flagged(self):
        assert not detect_user_frustration("sounds good, thanks")


# ---------------------------------------------------------------------------
# Shortening replies
# ---------------------------------------------------------------------------


class TestShorteningReplies:
    def test_three_short_replies_flagged(self):
        history = [
            {"role": "user", "message": "sharing bread"},
            {"role": "assistant", "message": "How many?"},
            {"role": "user", "message": "two"},
            {"role": "assistant", "message": "When does it expire?"},
            {"role": "user", "message": "tomorrow"},
            {"role": "assistant", "message": "What community?"},
            {"role": "user", "message": "ok"},
        ]
        assert detect_shortening_user_replies(history)

    def test_engaged_replies_not_flagged(self):
        history = [
            {"role": "user", "message": "I have two loaves of sourdough"},
            {"role": "assistant", "message": "Nice — when do they expire?"},
            {"role": "user", "message": "good until Friday afternoon"},
            {"role": "assistant", "message": "Great — what community?"},
            {"role": "user", "message": "Alameda Unified School District"},
        ]
        assert not detect_shortening_user_replies(history)

    def test_too_few_turns_safe(self):
        assert not detect_shortening_user_replies([])


# ---------------------------------------------------------------------------
# Topic pivot
# ---------------------------------------------------------------------------


class TestTopicPivot:
    @pytest.mark.parametrize("msg", [
        "actually let's find food instead",
        "changed my mind, I want to claim something",
        "never mind — forget that",
        "en lugar de eso, quiero buscar comida",
    ])
    def test_pivot_positive(self, msg):
        assert detect_topic_pivot(msg)

    def test_pivot_negative(self):
        assert not detect_topic_pivot("Alameda Unified")


# ---------------------------------------------------------------------------
# Hallucinated success
# ---------------------------------------------------------------------------


class TestHallucinatedSuccess:
    def test_posted_claim_without_tool_flagged(self):
        # The exact worst-case: reply says 'Posted!' but no tool ran.
        assert detect_hallucinated_success("Posted! Here's your listing.", tool_actions=[])

    def test_posted_with_matching_tool_ok(self):
        actions = [{"tool": "post_food_listing", "ok": True}]
        assert not detect_hallucinated_success("Posted!", actions)
        assert not detect_hallucinated_success(
            "Posted!", [{"tool": "post_food_listings", "ok": True}],
        )

    def test_posted_with_failed_tool_still_flagged(self):
        # Tool ran but failed → claim is still a hallucination.
        actions = [{"tool": "post_food_listing", "ok": False}]
        assert detect_hallucinated_success("Posted!", actions)

    def test_no_success_words_not_flagged(self):
        assert not detect_hallucinated_success("How many loaves do you have?", [])

    def test_reasoning_chip_does_not_count(self):
        # The 'reasoning' chip in actions has a "type" field and no
        # "tool" — it must NOT count as a real tool call.
        actions = [{"type": "reasoning", "text": "planning to post..."}]
        assert detect_hallucinated_success("Posted!", actions)


# ---------------------------------------------------------------------------
# Tool loop + failure rate
# ---------------------------------------------------------------------------


class TestToolLoopAndFailureRate:
    def test_three_same_tool_calls_detected(self):
        for _ in range(3):
            record_tool_outcome("u-test", "search_food_near_user", ok=True)
        assert detect_tool_loop("u-test") == "search_food_near_user"

    def test_mixed_tool_calls_no_loop(self):
        record_tool_outcome("u-test", "search_food_near_user", ok=True)
        record_tool_outcome("u-test", "get_user_dashboard", ok=True)
        record_tool_outcome("u-test", "get_user_profile", ok=True)
        assert detect_tool_loop("u-test") is None

    def test_high_failure_rate_detected(self):
        for _ in range(4):
            record_tool_outcome("u-test", "post_food_listing", ok=False)
        assert recent_tool_failure_rate("u-test") == 1.0

    def test_zero_failure_rate_when_all_ok(self):
        record_tool_outcome("u-test", "get_user_profile", ok=True)
        record_tool_outcome("u-test", "search_food_near_user", ok=True)
        assert recent_tool_failure_rate("u-test") == 0.0

    def test_state_capped_at_max(self):
        for _ in range(30):
            record_tool_outcome("u-test", "search_food_near_user", ok=True)
        state = get_reflection_state("u-test")
        assert len(state.recent_tool_outcomes) <= 12


# ---------------------------------------------------------------------------
# Assemble / reminder
# ---------------------------------------------------------------------------


class TestBuildReminder:
    def test_no_signals_returns_none(self):
        # Fresh conversation with no history → nothing to reflect on.
        assert build_reflection_reminder("hi there", history=[], user_id="u-test") is None

    def test_correction_triggers_reminder(self):
        reminder = build_reflection_reminder(
            "no, I meant the apples", history=[], user_id="u-test",
        )
        assert reminder is not None
        low = reminder.lower()
        assert "correct" in low or "re-parse" in low

    def test_repeated_question_triggers_reminder(self):
        history = [
            {"role": "assistant", "message": "Which community should this go under?"},
            {"role": "user", "message": "Alameda"},
            {"role": "assistant", "message": "So — which community should this go under?"},
        ]
        reminder = build_reflection_reminder(
            "Alameda Unified", history=history, user_id="u-test",
        )
        assert reminder is not None
        assert "community" in reminder.lower()

    def test_tool_loop_triggers_reminder(self):
        # Prime state: 3 identical tool calls in a row.
        for _ in range(3):
            record_tool_outcome("u-test", "search_food_near_user", ok=True)
        reminder = build_reflection_reminder(
            "find food", history=[], user_id="u-test",
        )
        assert reminder is not None
        assert "search_food_near_user" in reminder

    def test_prior_note_appears_in_reminder(self):
        # A note from the previous turn's post-turn capture should
        # surface as an inner-voice line this turn.
        capture_post_turn_reflection("u-test", "Posted! done.", tool_actions=[])
        reminder = build_reflection_reminder(
            "anything else?", history=[], user_id="u-test",
        )
        assert reminder is not None
        low = reminder.lower()
        assert "note" in low or "last turn" in low

    def test_spanish_reminder(self):
        history = [
            {"role": "assistant", "message": "¿Qué comunidad?"},
            {"role": "user", "message": "Alameda"},
            {"role": "assistant", "message": "¿Qué comunidad?"},
        ]
        reminder = build_reflection_reminder(
            "Alameda", history=history, user_id="u-test", lang="es",
        )
        assert reminder is not None
        low = reminder.lower()
        assert "comunidad" in low or "reflex" in low


# ---------------------------------------------------------------------------
# Post-turn capture
# ---------------------------------------------------------------------------


class TestPostTurnCapture:
    def test_records_tool_outcomes(self):
        actions = [
            {"tool": "search_food_near_user", "ok": True},
            {"tool": "get_user_dashboard", "ok": True},
        ]
        capture_post_turn_reflection("u-test", "Here's what I found.", actions)
        state = get_reflection_state("u-test")
        assert len(state.recent_tool_outcomes) == 2
        assert {o["tool"] for o in state.recent_tool_outcomes} == {
            "search_food_near_user", "get_user_dashboard",
        }

    def test_flags_hallucinated_success(self):
        note = capture_post_turn_reflection(
            "u-test", "Posted! Listing #42 is up.", tool_actions=[],
        )
        assert note is not None
        assert "hallucin" in note or "without a tool" in note

    def test_no_flag_when_reply_had_real_tool(self):
        actions = [{"tool": "post_food_listing", "ok": True}]
        note = capture_post_turn_reflection(
            "u-test", "Posted! done.", tool_actions=actions,
        )
        assert note is None

    def test_note_decays_when_next_turn_clean(self):
        # Note stored on turn 1 (hallucination)
        capture_post_turn_reflection("u-test", "Posted!", tool_actions=[])
        state = get_reflection_state("u-test")
        assert state.last_reflection_note
        # Turn 2 is clean → note should be cleared, not carried forever.
        capture_post_turn_reflection("u-test", "How many loaves?", tool_actions=[])
        assert state.last_reflection_note == ""


# ---------------------------------------------------------------------------
# assess_turn integration
# ---------------------------------------------------------------------------


class TestAssessTurn:
    def test_returns_signals_dataclass(self):
        sig = assess_turn("no, I meant apples", history=[], user_id="u-test")
        assert isinstance(sig, ReflectionSignals)
        assert sig.user_corrected is True

    def test_empty_signals_is_empty(self):
        sig = assess_turn("hi", history=[], user_id="u-test")
        assert sig.is_empty()

    def test_multiple_signals_composable(self):
        # Prime a tool loop.
        for _ in range(3):
            record_tool_outcome("u-test", "search_food_near_user", ok=False)
        history = [
            {"role": "assistant", "message": "Which community?"},
            {"role": "user", "message": "Alameda"},
            {"role": "assistant", "message": "Which community?"},
        ]
        sig = assess_turn(
            "no, I meant the OTHER one", history=history, user_id="u-test",
        )
        assert sig.user_corrected is True
        assert sig.repeated_question is not None
        assert sig.tool_loop == "search_food_near_user"
        assert sig.failure_rate == 1.0
        assert not sig.is_empty()
