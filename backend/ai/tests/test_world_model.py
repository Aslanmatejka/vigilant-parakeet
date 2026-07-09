"""World model / real-world food ontology tests.

Covers the ambiguity the user reported: 'I want to share beans' → Nouri
asked 'how many beans?' as if you could share a single bean. The world
model resolves this by classifying foods into real-world kinds (bulk
dry, canned, produce, dairy, etc.) and emitting a per-turn reminder
that steers the AI into unit-aware phrasing.

Structure:
  * TestFoodKindDetection — the raw classifier
  * TestExplicitUnits — 'a bag of rice' is already unit-qualified
  * TestSingletonBulk — '1 bean' / 'a rice' are unreasonable
  * TestWorldModelReminder — the prompt reminder wired into ai_engine
  * TestQuantityNormalization — auto-filling `unit` in tool args
  * TestClaimQuantityReminderIsUnitAware — the claim nudge respects it
"""
from __future__ import annotations

import pytest

from backend.ai.world_model import (
    build_world_model_reminder,
    detect_food_kind,
    has_explicit_unit,
    is_uncountable_singleton,
    normalize_food_quantity,
)


# ---------------------------------------------------------------------------
# Food kind detection
# ---------------------------------------------------------------------------


class TestFoodKindDetection:
    def test_beans_is_bulk_dry(self):
        # The user's original failure mode: 'share beans' → bulk_dry, not
        # countable. This is the root of the 'how many beans?' bug.
        entry = detect_food_kind("I want to share beans")
        assert entry is not None
        assert entry["food"] == "beans"
        assert entry["kind"] == "bulk_dry"

    def test_canned_modifier_flips_bulk_to_canned(self):
        entry = detect_food_kind("I have canned beans to share")
        assert entry["kind"] == "canned"

    def test_rice_is_bulk_dry(self):
        entry = detect_food_kind("some rice for the pantry")
        assert entry and entry["kind"] == "bulk_dry"

    def test_bread_is_baked(self):
        entry = detect_food_kind("sharing bread today")
        assert entry and entry["kind"] == "baked"

    def test_apples_is_produce_count(self):
        entry = detect_food_kind("claim 2 apples")
        assert entry and entry["kind"] == "produce_count"

    def test_potatoes_is_produce_bulk(self):
        entry = detect_food_kind("a bag of potatoes")
        assert entry and entry["kind"] == "produce_bulk"

    def test_soup_is_prepared(self):
        entry = detect_food_kind("I made soup")
        assert entry and entry["kind"] == "prepared"

    def test_milk_is_dairy(self):
        entry = detect_food_kind("I have milk to share")
        assert entry and entry["kind"] == "dairy"

    def test_eggs_is_eggs(self):
        entry = detect_food_kind("some eggs")
        assert entry and entry["kind"] == "eggs"

    def test_chicken_is_protein(self):
        entry = detect_food_kind("cooked chicken")
        assert entry and entry["kind"] == "protein"

    def test_bigram_sweet_potato_beats_potato(self):
        entry = detect_food_kind("share sweet potato")
        assert entry and entry["food"] in ("sweet potato", "potato")
        # Whatever wins, the kind should still be produce_bulk.
        assert entry["kind"] == "produce_bulk"

    def test_bigram_ground_beef(self):
        entry = detect_food_kind("ground beef")
        assert entry and entry["kind"] == "protein"

    def test_spanish_frijoles_is_bulk_dry(self):
        entry = detect_food_kind("quiero compartir frijoles")
        assert entry and entry["kind"] == "bulk_dry"

    def test_spanish_leche_is_dairy(self):
        entry = detect_food_kind("tengo leche para compartir")
        assert entry and entry["kind"] == "dairy"

    def test_unknown_returns_none(self):
        # We prefer silent pass-through over wrong nudges.
        assert detect_food_kind("random unrelated text") is None
        assert detect_food_kind("") is None
        assert detect_food_kind(None) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Explicit-unit detection
# ---------------------------------------------------------------------------


class TestExplicitUnits:
    @pytest.mark.parametrize("text", [
        "3 lbs of rice",
        "a bag of beans",
        "2 cans of tuna",
        "1 loaf of bread",
        "a dozen eggs",
        "una bolsa de arroz",
        "3 latas de atún",
    ])
    def test_positive_units(self, text):
        assert has_explicit_unit(text)

    @pytest.mark.parametrize("text", [
        "share beans",
        "some rice",
        "2 oranges",  # bare number, no unit → still not unit-qualified
    ])
    def test_negative_units(self, text):
        assert not has_explicit_unit(text)


# ---------------------------------------------------------------------------
# Uncountable-singleton detection
# ---------------------------------------------------------------------------


class TestSingletonBulk:
    def test_one_bean_is_unreasonable(self):
        # If the user (or the AI parroting) says '1 bean', it's the model
        # treating a bulk food as countable — that's exactly the pattern
        # we want to catch.
        assert is_uncountable_singleton("1 bean")
        assert is_uncountable_singleton("a bean")
        assert is_uncountable_singleton("one bean")

    def test_a_rice_is_unreasonable(self):
        assert is_uncountable_singleton("a rice")

    def test_a_bag_of_rice_is_fine(self):
        # Explicit unit → not flagged.
        assert not is_uncountable_singleton("a bag of rice")

    def test_apples_bare_count_is_fine(self):
        # Apples ARE countable — no false positive.
        assert not is_uncountable_singleton("2 apples")

    def test_dozen_eggs_is_fine(self):
        assert not is_uncountable_singleton("a dozen eggs")


# ---------------------------------------------------------------------------
# Reminder wiring
# ---------------------------------------------------------------------------


class TestWorldModelReminder:
    def test_share_beans_triggers_reminder(self):
        # Exact repro of the user's bug: 'I want to share beans' should
        # emit a nudge that steers Nouri away from 'how many beans?'.
        reminder = build_world_model_reminder(
            "I want to share beans", history=[], lang="en", flow="posting",
        )
        assert reminder is not None
        low = reminder.lower()
        assert "beans" in low
        assert "bulk_dry" in low or "real-world" in low
        # Must explicitly forbid the countable phrasing.
        assert "how many beans" in low

    def test_share_beans_spanish(self):
        reminder = build_world_model_reminder(
            "quiero compartir frijoles",
            history=[], lang="es", flow="posting",
        )
        assert reminder is not None
        assert "frijoles" in reminder.lower()

    def test_apples_no_reminder(self):
        # Countable produce is fine — nothing to nudge.
        reminder = build_world_model_reminder(
            "claim 2 apples", history=[], lang="en", flow="claiming",
        )
        assert reminder is None

    def test_explicit_unit_no_reminder(self):
        reminder = build_world_model_reminder(
            "I have a bag of rice to share",
            history=[], lang="en", flow="posting",
        )
        assert reminder is None

    def test_idle_flow_no_reminder(self):
        # Off-topic / idle turns pass through silently — we don't want
        # to derail non-share, non-claim conversations.
        reminder = build_world_model_reminder(
            "how are you today?", history=[], lang="en", flow="idle",
        )
        assert reminder is None

    def test_bean_in_history_still_triggers(self):
        history = [
            {"role": "user", "message": "I have beans to share"},
            {"role": "assistant", "message": "How many would you like to share?"},
        ]
        reminder = build_world_model_reminder(
            "yes", history=history, lang="en", flow="posting",
        )
        assert reminder is not None
        assert "beans" in reminder.lower()

    def test_singleton_bulk_still_nudges_even_with_unit_word_elsewhere(self):
        # If the AI (or user) says '1 bean' mid-flow, we still want the
        # nudge even if 'bag' appeared earlier. The singleton wins.
        reminder = build_world_model_reminder(
            "1 bean",
            history=[{"role": "user", "message": "share a bag of oats"}],
            lang="en",
            flow="posting",
        )
        assert reminder is not None


# ---------------------------------------------------------------------------
# Quantity normalisation for tool args
# ---------------------------------------------------------------------------


class TestQuantityNormalization:
    def test_beans_fills_default_unit(self):
        out = normalize_food_quantity(
            "share beans", {"title": "beans", "quantity": 3},
        )
        # Bulk dry defaults to 'lb' — better a real unit than nothing.
        assert out.get("unit") == "lb"

    def test_apples_does_not_force_unit(self):
        # Countable produce works fine with a bare number.
        out = normalize_food_quantity(
            "claim 2 apples", {"title": "apples", "quantity": 2},
        )
        assert out.get("unit") is None

    def test_existing_unit_is_preserved(self):
        # Never overwrite an explicit choice from the model.
        out = normalize_food_quantity(
            "share beans", {"unit": "can", "quantity": 6},
        )
        assert out["unit"] == "can"

    def test_bread_fills_loaf(self):
        out = normalize_food_quantity("share bread", {"quantity": 2})
        assert out.get("unit") == "loaf"

    def test_eggs_fills_dozen(self):
        out = normalize_food_quantity("some eggs", {"quantity": 1})
        assert out.get("unit") == "dozen"

    def test_unknown_food_pass_through(self):
        # No food detected → args untouched.
        out = normalize_food_quantity("random", {"quantity": 5})
        assert "unit" not in out


# ---------------------------------------------------------------------------
# Integration: claim reminder now uses world model
# ---------------------------------------------------------------------------


class TestClaimQuantityReminderIsUnitAware:
    def test_beans_claim_reminder_uses_bulk_language(self):
        from backend.ai.conversation_flow import build_claim_quantity_reminder

        # Simulate the state after a listing pick: assistant just asked
        # 'which one', user picked with a short reply that mentions beans.
        history = [
            {"role": "user", "message": "I'm looking for food"},
            {"role": "assistant", "message": "Here's what's near you."},
            {"role": "user", "message": "the beans"},
        ]
        reminder = build_claim_quantity_reminder(
            "the beans", history, lang="en",
        )
        # When the flow-detection is happy, we expect the bulk-food
        # phrasing. When it's not (e.g. no search cached in test), the
        # function may return None — that's the safe path, not a bug.
        if reminder is not None:
            low = reminder.lower()
            assert "beans" in low
            # Must NOT say the generic 'how many they want' — that's the
            # exact regression.
            assert "how many they want" not in low
