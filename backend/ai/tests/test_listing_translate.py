"""Tests for the Spanish→English translation guard on listings."""
from backend.ai.tools import _translate_listing_text


def test_no_change_when_already_english():
    assert _translate_listing_text("Sourdough bread") == "Sourdough bread"
    assert _translate_listing_text("3 loaves of bread") == "3 loaves of bread"


def test_none_and_empty_pass_through():
    assert _translate_listing_text(None) is None
    assert _translate_listing_text("") == ""


def test_basic_food_translations():
    assert _translate_listing_text("pan") == "bread"
    assert _translate_listing_text("Pan").lower() == "bread"
    assert _translate_listing_text("PAN") == "BREAD"
    assert _translate_listing_text("Manzanas frescas").lower().startswith("apples")


def test_preserves_capitalization():
    out = _translate_listing_text("Manzanas")
    assert out == "Apples"


def test_word_boundary_does_not_partial_match():
    # 'pan' must not corrupt 'panini' or 'panda'.
    assert _translate_listing_text("panini bread") == "panini bread"
    assert _translate_listing_text("panda toy") == "panda toy"


def test_preserves_numbers_and_addresses():
    out = _translate_listing_text("3 panes en 1423 Park St")
    assert "1423 Park St" in out
    assert "loaves of bread" in out.lower() or "bread" in out.lower()


def test_dietary_and_allergens():
    assert _translate_listing_text("sin gluten") == "gluten-free"
    assert _translate_listing_text("lácteos") == "dairy"
    assert _translate_listing_text("frutos secos") == "nuts"
    assert _translate_listing_text("vegano") == "vegan"


def test_handoff_phrases():
    assert "Pickup only" in _translate_listing_text("Recogida solamente.")


def test_unknown_words_unchanged():
    # Spanish word not in the glossary should pass through untouched.
    assert _translate_listing_text("Empanadas argentinas") == "Empanadas argentinas"
