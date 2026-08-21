"""Tests for accessibility profile persistence helpers."""
from backend.ai.accessibility_profile import (
    ACCESSIBILITY_PREF_KEY,
    merge_accessibility_profiles,
    preferred_language_from_profile,
)


def test_merge_accessibility_profiles():
    merged = merge_accessibility_profiles(
        {"simpleLanguage": True, "preferredLanguage": "en"},
        {"preferredLanguage": "vi", "easyMode": True},
    )
    assert merged["simpleLanguage"] is True
    assert merged["preferredLanguage"] == "vi"
    assert merged["easyMode"] is True


def test_merge_empty_returns_none():
    assert merge_accessibility_profiles(None, None) is None


def test_preferred_language_from_profile():
    assert preferred_language_from_profile({"preferredLanguage": "FR"}) == "fr"
    assert preferred_language_from_profile({"language": "es-MX"}) == "es-mx"
    assert preferred_language_from_profile({}) is None


def test_accessibility_pref_key_constant():
    assert ACCESSIBILITY_PREF_KEY == "accessibility"
