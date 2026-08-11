"""Tests for standing instructions (always-do / verify / visibility coaching)."""
from __future__ import annotations

import pytest

from backend.ai.standing_instructions import (
    VERIFY_STEPS_KEY,
    build_standing_turn_reminder,
    detect_standing_hits,
    format_soft_preferences_block,
    format_standing_memories_block,
    is_standing_memory_key,
)


class TestDetectStandingHits:
    def test_always_do(self):
        hits = detect_standing_hits("Always confirm the quantity before posting.")
        kinds = {h.kind for h in hits}
        assert "always_do" in kinds
        always = next(h for h in hits if h.kind == "always_do")
        assert always.persist
        assert always.key and always.key.startswith("always_do:")
        assert "confirm" in (always.value or "").lower() or "quantity" in (always.value or "").lower()

    def test_remember(self):
        hits = detect_standing_hits("Remember that I prefer miles, not kilometers.")
        assert any(h.kind == "remind" and h.persist for h in hits)

    def test_omission(self):
        hits = detect_standing_hits("You didn't open the map after searching.")
        assert any(h.kind == "omission" and h.turn_only for h in hits)

    def test_visibility(self):
        hits = detect_standing_hits("I'm not seeing the apples listing on Find Food.")
        assert any(h.kind == "visibility" for h in hits)

    def test_verify_steps_turn_only(self):
        hits = detect_standing_hits("Check step by step if you're not missing anything.")
        assert any(h.kind == "verify" for h in hits)
        verify = next(h for h in hits if h.kind == "verify")
        assert verify.persist is False

    def test_always_verify_persists(self):
        hits = detect_standing_hits("From now on always check step by step.")
        assert any(
            h.kind == "verify" and h.persist and h.key == VERIFY_STEPS_KEY
            for h in hits
        )

    def test_forget(self):
        hits = detect_standing_hits("Forget that — stop always confirming.")
        assert any(h.kind == "forget" for h in hits)

    def test_neutral_message(self):
        assert detect_standing_hits("Find food near me") == []
        assert detect_standing_hits("hi") == []


class TestFormatBlocks:
    def test_standing_block_must_follow(self):
        block = format_standing_memories_block([
            {"key": "always_do:confirm_qty", "value": "confirm quantity first"},
            {"key": VERIFY_STEPS_KEY, "value": "true"},
            {"key": "preferred_radius_km", "value": "10"},
        ])
        assert block
        assert "MUST follow" in block or "OBLIGATORIAS" in block
        assert "confirm quantity" in block.lower() or "quantity" in block.lower()
        assert "preferred_radius" not in block

    def test_soft_excludes_standing(self):
        block = format_soft_preferences_block([
            {"key": "always_do:x", "value": "do x"},
            {"key": "preferred_radius_km", "value": "10"},
            {"key": "conversation_tone", "value": "warm"},
        ])
        assert block
        assert "preferred_radius_km" in block
        assert "always_do" not in block
        assert "conversation_tone" not in block

    def test_is_standing_key(self):
        assert is_standing_memory_key("always_do:foo")
        assert is_standing_memory_key("remind:bar")
        assert is_standing_memory_key(VERIFY_STEPS_KEY)
        assert not is_standing_memory_key("preferred_radius_km")


class TestTurnReminder:
    def test_visibility_and_omission(self):
        hits = detect_standing_hits(
            "You didn't post it and I'm not seeing anything on the map."
        )
        reminder = build_standing_turn_reminder(hits, lang="en")
        assert reminder
        assert "NOT SEEING" in reminder or "not seeing" in reminder.lower()
        assert "MISSED" in reminder or "DIDN'T" in reminder or "missed" in reminder.lower()

    def test_verify_pref_via_sync_on_action(self):
        # Preference alone does not spam every greeting; trigger words do.
        assert build_standing_turn_reminder(
            [],
            memories=[{"key": VERIFY_STEPS_KEY, "value": "true"}],
            lang="en",
        ) is None
        reminder2 = build_standing_turn_reminder(
            detect_standing_hits("make sure nothing is missing"),
            memories=[{"key": VERIFY_STEPS_KEY, "value": "true"}],
            lang="en",
        )
        assert reminder2 and "STEP BY STEP" in reminder2


@pytest.mark.asyncio
async def test_sync_persists_always_do(monkeypatch):
    from backend.ai import standing_instructions as si

    saved = []

    async def fake_save(user_id, key, value, confidence="medium"):
        saved.append({"user_id": user_id, "key": key, "value": value, "confidence": confidence})
        return {"saved": True, "key": key, "value": value}

    monkeypatch.setattr(si, "persist_standing_hits", si.persist_standing_hits)
    monkeypatch.setattr("backend.ai.tools._save_user_memory", fake_save)

    out = await si.sync_standing_instructions(
        "user-1",
        "Always open the map after a search.",
        lang="en",
    )
    assert out["saved"]
    assert any(s["key"].startswith("always_do:") for s in out["saved"])
    assert out["reminder"]
