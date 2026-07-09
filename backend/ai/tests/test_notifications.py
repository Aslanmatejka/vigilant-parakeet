"""Pure-logic tests for backend.ai.notifications helpers (no DB, no Twilio)."""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from backend.ai import notifications as N


# ---------------------------------------------------------------------------
# _safe_json_loads
# ---------------------------------------------------------------------------

class TestSafeJsonLoads:
    def test_none_returns_none(self):
        assert N._safe_json_loads(None) is None

    def test_empty_returns_none(self):
        assert N._safe_json_loads("") is None

    def test_valid_list(self):
        assert N._safe_json_loads('["a", "b"]') == ["a", "b"]

    def test_valid_dict(self):
        assert N._safe_json_loads('{"a": 1}') == {"a": 1}

    def test_invalid_returns_none(self):
        assert N._safe_json_loads("not json") is None


# ---------------------------------------------------------------------------
# _as_lower_set
# ---------------------------------------------------------------------------

class TestAsLowerSet:
    def test_empty(self):
        assert N._as_lower_set(None) == set()
        assert N._as_lower_set("") == set()
        assert N._as_lower_set([]) == set()

    def test_list_input(self):
        assert N._as_lower_set(["Peanuts", "SHELLFISH"]) == {"peanuts", "shellfish"}

    def test_json_string(self):
        assert N._as_lower_set('["Peanuts", "Milk"]') == {"peanuts", "milk"}

    def test_csv_fallback(self):
        assert N._as_lower_set("Peanuts, Milk ,Eggs") == {"peanuts", "milk", "eggs"}

    def test_strips_whitespace(self):
        assert N._as_lower_set(["  Peanuts  ", "", "  "]) == {"peanuts"}


# ---------------------------------------------------------------------------
# _user_prefers_language
# ---------------------------------------------------------------------------

class TestUserPrefersLanguage:
    def test_defaults_to_english(self):
        u = SimpleNamespace(notification_preferences=None)
        assert N._user_prefers_language(u) == "en"

    def test_spanish_explicit(self):
        u = SimpleNamespace(notification_preferences='{"language": "es"}')
        assert N._user_prefers_language(u) == "es"

    def test_spanish_locale_variant(self):
        u = SimpleNamespace(notification_preferences='{"language": "es-MX"}')
        assert N._user_prefers_language(u) == "es"

    def test_fr_defaults_to_en(self):
        u = SimpleNamespace(notification_preferences='{"language": "fr"}')
        assert N._user_prefers_language(u) == "en"


# ---------------------------------------------------------------------------
# _user_wants_new_listings
# ---------------------------------------------------------------------------

class TestUserWantsNewListings:
    def test_default_opt_in(self):
        u = SimpleNamespace(notification_preferences=None, sms_notification_types=None)
        assert N._user_wants_new_listings(u) is True

    def test_explicit_true(self):
        u = SimpleNamespace(
            notification_preferences='{"new_listings": true}',
            sms_notification_types=None,
        )
        assert N._user_wants_new_listings(u) is True

    def test_explicit_false(self):
        u = SimpleNamespace(
            notification_preferences='{"new_listings": false}',
            sms_notification_types=None,
        )
        assert N._user_wants_new_listings(u) is False

    def test_sms_types_new_listings(self):
        u = SimpleNamespace(
            notification_preferences=None,
            sms_notification_types='["new_listings"]',
        )
        assert N._user_wants_new_listings(u) is True

    def test_sms_types_all(self):
        u = SimpleNamespace(
            notification_preferences=None,
            sms_notification_types='["all"]',
        )
        assert N._user_wants_new_listings(u) is True


# ---------------------------------------------------------------------------
# _user_sms_ok
# ---------------------------------------------------------------------------

class TestUserSmsOk:
    def test_full_consent(self):
        u = SimpleNamespace(sms_consent_given=True, sms_opt_out_date=None, phone="+15551234")
        assert N._user_sms_ok(u) is True

    def test_no_consent(self):
        u = SimpleNamespace(sms_consent_given=False, sms_opt_out_date=None, phone="+15551234")
        assert N._user_sms_ok(u) is False

    def test_opted_out(self):
        u = SimpleNamespace(sms_consent_given=True,
                            sms_opt_out_date=datetime.utcnow(),
                            phone="+15551234")
        assert N._user_sms_ok(u) is False

    def test_no_phone(self):
        u = SimpleNamespace(sms_consent_given=True, sms_opt_out_date=None, phone=None)
        assert N._user_sms_ok(u) is False


# ---------------------------------------------------------------------------
# _allergen_conflict
# ---------------------------------------------------------------------------

class TestAllergenConflict:
    def test_no_user_allergies_no_conflict(self):
        u = SimpleNamespace(allergies=None)
        f = SimpleNamespace(allergens='["peanuts"]')
        assert N._allergen_conflict(u, f) is False

    def test_overlap_is_conflict(self):
        u = SimpleNamespace(allergies='["Peanuts", "Milk"]')
        f = SimpleNamespace(allergens='["peanuts"]')
        assert N._allergen_conflict(u, f) is True

    def test_disjoint_no_conflict(self):
        u = SimpleNamespace(allergies='["shellfish"]')
        f = SimpleNamespace(allergens='["peanuts"]')
        assert N._allergen_conflict(u, f) is False


# ---------------------------------------------------------------------------
# _dietary_conflict
# ---------------------------------------------------------------------------

class TestDietaryConflict:
    def test_no_restrictions(self):
        u = SimpleNamespace(dietary_restrictions=None)
        f = SimpleNamespace(dietary_tags=None)
        assert N._dietary_conflict(u, f) is False

    def test_vegan_user_non_vegan_food(self):
        u = SimpleNamespace(dietary_restrictions='["vegan"]')
        f = SimpleNamespace(dietary_tags='["vegetarian"]')
        assert N._dietary_conflict(u, f) is True

    def test_vegan_user_vegan_food(self):
        u = SimpleNamespace(dietary_restrictions='["vegan"]')
        f = SimpleNamespace(dietary_tags='["vegan", "vegetarian"]')
        assert N._dietary_conflict(u, f) is False

    def test_unknown_restriction_does_not_conflict(self):
        # Missing info on unknown custom restriction => no conflict
        u = SimpleNamespace(dietary_restrictions='["low-sodium"]')
        f = SimpleNamespace(dietary_tags=None)
        assert N._dietary_conflict(u, f) is False


# ---------------------------------------------------------------------------
# _category_match
# ---------------------------------------------------------------------------

class TestCategoryMatch:
    def test_no_prefs_matches_all(self):
        u = SimpleNamespace(preferred_categories=None)
        f = SimpleNamespace(category=SimpleNamespace(value="produce"))
        assert N._category_match(u, f) is True

    def test_category_in_prefs(self):
        u = SimpleNamespace(preferred_categories='["produce", "bakery"]')
        f = SimpleNamespace(category=SimpleNamespace(value="produce"))
        assert N._category_match(u, f) is True

    def test_category_not_in_prefs(self):
        u = SimpleNamespace(preferred_categories='["produce"]')
        f = SimpleNamespace(category=SimpleNamespace(value="dairy"))
        assert N._category_match(u, f) is False

    def test_no_food_category_matches(self):
        u = SimpleNamespace(preferred_categories='["produce"]')
        f = SimpleNamespace(category=None)
        assert N._category_match(u, f) is True


# ---------------------------------------------------------------------------
# Template builders
# ---------------------------------------------------------------------------

class TestTemplates:
    def _make_food(self, **kw):
        defaults = dict(title="Fresh Apples", address="123 Main St, Springfield",
                        pickup_window_end=None)
        defaults.update(kw)
        return SimpleNamespace(**defaults)

    def test_english_template_contains_name_and_title(self):
        food = self._make_food()
        text = N._template_en("Alice Smith", food, "Bob's Bakery")
        assert "Alice" in text
        assert "Fresh Apples" in text
        assert "Bob's Bakery" in text
        assert "STOP" in text  # opt-out notice

    def test_spanish_template_contains_name_and_title(self):
        food = self._make_food(title="Manzanas frescas")
        text = N._template_es("Ana Gómez", food, "Panadería Bob")
        assert "Ana" in text
        assert "Manzanas frescas" in text
        assert "Panadería Bob" in text
        assert "STOP" in text

    def test_template_handles_missing_name(self):
        food = self._make_food()
        text = N._template_en(None, food, None)
        assert "Hi there" in text or "there" in text
