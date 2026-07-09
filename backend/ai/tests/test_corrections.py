"""Tests for mistake/correction detection and quick-reply chips."""
from backend.ai.ai_engine import (
    _is_correction_reply,
    _is_cancellation_reply,
    generate_quick_replies,
)


def test_correction_phrases_detected():
    assert _is_correction_reply("actually I meant 5 loaves not 3")
    assert _is_correction_reply("wait wrong one")
    assert _is_correction_reply("I meant the bread not the kale")
    assert _is_correction_reply("change it to 2 boxes")
    assert _is_correction_reply("espera, quise decir pan")
    assert _is_correction_reply("5 not 3")


def test_correction_not_cancellation():
    assert _is_cancellation_reply("cancel")
    assert not _is_correction_reply("cancel")
    assert not _is_correction_reply("never mind")


def test_correction_user_message_chips():
    out = generate_quick_replies(
        "Got it — 3 loaves of sourdough at your profile address. Post it?",
        user_message="wait actually 5 loaves not 3",
    )
    assert out
    joined = " ".join(out).lower()
    assert "quantity" in joined or "cantidad" in joined or "address" in joined or "listing" in joined


def test_edit_ask_chips():
    out = generate_quick_replies("No problem — what should I change?")
    assert out
    joined = " ".join(out).lower()
    assert "quantity" in joined or "address" in joined or "food" in joined


def test_destructive_confirm_chips():
    out = generate_quick_replies(
        "Before I go ahead — do you want me to permanently delete 'Duplicate rice'?",
    )
    assert out
    assert "Yes, confirm" in out or "Wait, edit it" in out


def test_claim_lock_in_no_longer_offered():
    """Claims are instant — no 'lock it in' confirmation chips."""
    out = generate_quick_replies(
        "Nice choice — want me to lock it in now? I'll send you a pickup code.",
    )
    joined = " ".join(out).lower()
    assert "lock it in" not in joined


def test_post_confirm_still_has_edit_chip():
    out = generate_quick_replies(
        "I'll post 3 loaves at 1423 Park St — ready to post?"
    )
    assert "Wait, edit it" in out or "Yes, post it" in out
