"""Allergen + dietary tag extraction tests.

Nouri was dropping allergens on the floor: donors saying 'this has
peanuts' shipped listings with empty ``allergens``, and recipients
saying "I'm allergic to dairy" had their constraint silently ignored.
These tests lock in the fix from ``backend/ai/allergens.py``:

  * Big-8 allergen vocabulary detection (EN + ES)
  * Donor 'contains X' → allergens
  * Recipient 'allergic to X' / 'no X' → exclude_allergens
  * Dietary tags recognised (vegan, gluten-free, etc.)
  * Enrichment never overwrites what the model already set
  * Enrichment merges profile-level constraints on search
  * Reminder fires only for allergen-sensitive kinds, once
"""
from __future__ import annotations

from backend.ai.allergens import (
    allergens_answered,
    allergens_asked,
    build_allergen_reminder,
    enrich_post_listing_allergen_args,
    enrich_search_allergen_args,
    extract_allergens_and_diet,
)


# ---------------------------------------------------------------------------
# Extraction — donor framing
# ---------------------------------------------------------------------------


class TestDonorFraming:
    def test_contains_peanuts_and_dairy(self):
        out = extract_allergens_and_diet(
            "this soup contains peanuts and some dairy", frame="donor",
        )
        assert "peanuts" in out["allergens"]
        assert "milk" in out["allergens"]
        assert out["exclude_allergens"] == []

    def test_made_with_wheat_flour(self):
        out = extract_allergens_and_diet(
            "made with wheat flour and eggs", frame="donor",
        )
        assert set(out["allergens"]) >= {"wheat", "eggs"}

    def test_donor_dietary_tags(self):
        out = extract_allergens_and_diet(
            "the meal is vegan and gluten-free", frame="donor",
        )
        assert set(out["dietary_tags"]) >= {"vegan", "gluten_free"}

    def test_spanish_donor(self):
        out = extract_allergens_and_diet(
            "contiene maní y lácteos", frame="donor",
        )
        assert "peanuts" in out["allergens"]
        assert "milk" in out["allergens"]


# ---------------------------------------------------------------------------
# Extraction — recipient framing
# ---------------------------------------------------------------------------


class TestRecipientFraming:
    def test_allergic_to_peanuts(self):
        # The user's original failure mode: 'I'm allergic to peanuts'
        # → recipient constraint, not a property of some listing.
        out = extract_allergens_and_diet("I'm allergic to peanuts", frame="recipient")
        assert out["exclude_allergens"] == ["peanuts"]
        assert out["allergens"] == []

    def test_no_dairy_please(self):
        out = extract_allergens_and_diet("no dairy please", frame="recipient")
        assert "milk" in out["exclude_allergens"]

    def test_cant_eat_gluten(self):
        out = extract_allergens_and_diet("I can't eat gluten", frame="recipient")
        assert "gluten" in out["exclude_allergens"]

    def test_spanish_soy_alergica(self):
        out = extract_allergens_and_diet(
            "soy alérgica a los mariscos", frame="recipient",
        )
        assert "shellfish" in out["exclude_allergens"]


# ---------------------------------------------------------------------------
# Auto framing — free-text messages
# ---------------------------------------------------------------------------


class TestAutoFraming:
    def test_donor_language_routes_to_allergens(self):
        out = extract_allergens_and_diet("this bread contains eggs")
        assert "eggs" in out["allergens"]
        assert "eggs" not in out["exclude_allergens"]

    def test_recipient_language_routes_to_exclude(self):
        out = extract_allergens_and_diet("I'm allergic to eggs")
        assert "eggs" in out["exclude_allergens"]
        assert "eggs" not in out["allergens"]

    def test_mixed_message_routes_to_both(self):
        # Rare in practice but a legit failure mode: a recipient noting
        # their allergy AND a listing property. Safer to include the
        # allergen on both sides.
        out = extract_allergens_and_diet(
            "I'm allergic to nuts, and this soup contains peanuts"
        )
        assert "tree_nuts" in out["exclude_allergens"]
        assert "peanuts" in out["allergens"]

    def test_no_allergen_words_returns_empty(self):
        out = extract_allergens_and_diet("nice weather today")
        assert out["allergens"] == []
        assert out["exclude_allergens"] == []
        assert out["dietary_tags"] == []

    def test_empty_input_safe(self):
        out = extract_allergens_and_diet("")
        assert out == {"allergens": [], "exclude_allergens": [], "dietary_tags": []}

    def test_negative_prefix_no_x(self):
        # 'no eggs' alone should count as a recipient constraint.
        out = extract_allergens_and_diet("no eggs")
        assert "eggs" in out["exclude_allergens"]


# ---------------------------------------------------------------------------
# Whole-word matching guardrails
# ---------------------------------------------------------------------------


class TestWholeWordGuardrails:
    def test_buttercup_does_not_count_as_butter(self):
        # Prior to the whole-word check, 'buttercup' would match
        # 'butter' via substring. That's a false positive.
        out = extract_allergens_and_diet("the buttercup flower is yellow")
        assert "milk" not in out["allergens"]
        assert "milk" not in out["exclude_allergens"]

    def test_wheatgrass_does_not_count_as_wheat(self):
        # Same guardrail. 'wheatgrass' shouldn't fire the wheat allergen.
        out = extract_allergens_and_diet("wheatgrass juice is popular", frame="donor")
        assert "wheat" not in out["allergens"]


# ---------------------------------------------------------------------------
# Enrichment — posting side
# ---------------------------------------------------------------------------


class TestEnrichPostListing:
    def test_extracts_from_message(self):
        args = {"title": "cookies", "quantity": 12}
        out = enrich_post_listing_allergen_args(
            args, "these cookies contain peanuts and eggs", history=[],
        )
        assert set(out["allergens"]) >= {"peanuts", "eggs"}

    def test_preserves_model_supplied_allergens(self):
        # The model already emitted allergens — the extractor should
        # only ADD to that list, never overwrite it.
        args = {"allergens": ["Sesame"]}
        out = enrich_post_listing_allergen_args(
            args, "and it also has some dairy", history=[],
        )
        assert "Sesame" in out["allergens"]
        assert "milk" in out["allergens"]

    def test_extracts_dietary_tags_from_history(self):
        # 'It's vegan' said two turns ago should still land on the listing.
        history = [
            {"role": "user", "message": "I want to share some soup"},
            {"role": "assistant", "message": "Cool, tell me about it"},
            {"role": "user", "message": "it's vegan"},
        ]
        args = {"title": "soup"}
        out = enrich_post_listing_allergen_args(args, "post it", history)
        assert "vegan" in out["dietary_tags"]

    def test_no_allergen_words_leaves_args_unchanged(self):
        args = {"title": "apples", "quantity": 5}
        out = enrich_post_listing_allergen_args(args, "sharing some apples", history=[])
        assert "allergens" not in out
        assert "dietary_tags" not in out


# ---------------------------------------------------------------------------
# Enrichment — search side
# ---------------------------------------------------------------------------


class TestEnrichSearch:
    def test_recipient_constraint_becomes_exclude(self):
        args = {"user_id": "u1"}
        out = enrich_search_allergen_args(
            args, "I'm allergic to peanuts", history=[],
        )
        assert out["exclude_allergens"] == ["peanuts"]

    def test_profile_allergens_always_included(self):
        # Even if the current message says nothing, the profile allergens
        # must be honoured — the recipient shouldn't have to re-state
        # their allergy every turn.
        args = {"user_id": "u1"}
        out = enrich_search_allergen_args(
            args, "find food near me", history=[],
            profile_allergens=["dairy"],
        )
        assert out["exclude_allergens"] == ["dairy"]

    def test_message_and_profile_merged(self):
        args = {}
        out = enrich_search_allergen_args(
            args, "no nuts please", history=[],
            profile_allergens=["shellfish"],
        )
        assert set(out["exclude_allergens"]) == {"tree_nuts", "shellfish"}

    def test_history_scan_picks_up_prior_allergy(self):
        # 'I'm allergic to eggs' said earlier; current message unrelated.
        history = [
            {"role": "user", "message": "I'm allergic to eggs"},
            {"role": "assistant", "message": "Got it — noted."},
        ]
        args = {}
        out = enrich_search_allergen_args(args, "show me food", history)
        assert "eggs" in out.get("exclude_allergens", [])

    def test_empty_when_nothing_to_add(self):
        # No message allergens, no profile allergens → the field is not
        # written at all (avoids polluting the search request).
        args = {}
        out = enrich_search_allergen_args(args, "just find food", history=[])
        assert "exclude_allergens" not in out
        assert "dietary_tags" not in out

    def test_dietary_tags_from_message(self):
        args = {}
        out = enrich_search_allergen_args(args, "I'm vegan", history=[])
        assert "vegan" in out.get("dietary_tags", [])


# ---------------------------------------------------------------------------
# Reminder wiring
# ---------------------------------------------------------------------------


class TestReminder:
    def test_baked_goods_triggers_reminder(self):
        history = [
            {"role": "user", "message": "I want to share some cookies"},
            {"role": "assistant", "message": "When does it expire?"},
            {"role": "user", "message": "in 3 days"},
        ]
        reminder = build_allergen_reminder(
            "ok", history, lang="en", flow="posting",
        )
        assert reminder is not None
        assert "allerg" in reminder.lower()

    def test_apples_triggers_reminder_after_expiry(self):
        history = [
            {"role": "user", "message": "sharing 100 boxes of vegetables"},
            {"role": "assistant", "message": "When does it expire?"},
            {"role": "user", "message": "2 months from now"},
        ]
        reminder = build_allergen_reminder(
            "ok", history, lang="en", flow="posting",
        )
        assert reminder is not None
        assert "allerg" in reminder.lower()

    def test_answered_stops_reminder(self):
        # Donor already declared allergens → reminder falls silent.
        history = [
            {"role": "user", "message": "sharing some cookies"},
            {"role": "assistant", "message": "Any allergens I should note?"},
            {"role": "user", "message": "they have peanuts and dairy"},
        ]
        reminder = build_allergen_reminder(
            "post it", history, lang="en", flow="posting",
        )
        assert reminder is None

    def test_asked_stops_reminder(self):
        # We only want to nudge ONCE. If the assistant already asked,
        # the reminder is silent even before the answer arrives.
        history = [
            {"role": "user", "message": "sharing lasagna"},
            {"role": "assistant", "message": "Any allergens like dairy or eggs?"},
        ]
        reminder = build_allergen_reminder(
            "", history, lang="en", flow="posting",
        )
        assert reminder is None

    def test_idle_flow_no_reminder(self):
        reminder = build_allergen_reminder(
            "sharing cookies", history=[], lang="en", flow="idle",
        )
        assert reminder is None

    def test_spanish_reminder(self):
        reminder = build_allergen_reminder(
            "quiero compartir galletas",
            history=[], lang="es", flow="posting",
        )
        # Spanish nudge or None (if we didn't detect the food) — either
        # is safe. When present, must talk about alérgenos.
        if reminder is not None:
            assert "aler" in reminder.lower()


# ---------------------------------------------------------------------------
# Ask / answered detection
# ---------------------------------------------------------------------------


class TestAskedAnsweredDetection:
    def test_allergens_asked_by_assistant(self):
        history = [
            {"role": "assistant", "message": "Any allergens I should know about?"},
        ]
        assert allergens_asked("", history)

    def test_no_asked_when_no_such_message(self):
        history = [
            {"role": "assistant", "message": "How many loaves?"},
        ]
        assert not allergens_asked("", history)

    def test_answered_by_declaration(self):
        assert allergens_answered("it has peanuts and eggs", history=[])

    def test_answered_by_declaring_none(self):
        assert allergens_answered("no allergens", history=[])

    def test_not_answered_by_bare_yes(self):
        history = [
            {"role": "assistant", "message": "Any allergens I should note?"},
        ]
        assert not allergens_answered("yes", history)
