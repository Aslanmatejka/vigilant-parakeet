"""Accessibility profile prompt builder."""
from backend.agent.user_guidance import build_accessibility_profile_prompt


def test_empty_profile_returns_empty():
    assert build_accessibility_profile_prompt(None) == ""
    assert build_accessibility_profile_prompt({}) == ""


def test_simple_language_and_easy_mode():
    block = build_accessibility_profile_prompt({
        "simpleLanguage": True,
        "easyMode": True,
        "preferredLanguage": "en",
    })
    assert "simple language" in block.lower()
    assert "Easy Mode" in block


def test_preferred_language_non_english():
    block = build_accessibility_profile_prompt({
        "preferredLanguage": "vi",
    })
    assert "Vietnamese" in block
    assert "vi" in block


def test_screen_reader_and_text_only():
    block = build_accessibility_profile_prompt({
        "screenReaderOptimized": True,
        "preferTextOverVoice": True,
        "preferredLanguage": "en",
    })
    assert "Screen reader" in block
    assert "text over voice" in block.lower()
