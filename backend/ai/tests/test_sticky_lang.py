"""Tests for sticky language detection."""
from backend.ai.ai_engine import ConversationEngine


def test_sticky_short_si_with_spanish_history():
    eng = ConversationEngine()
    history = [
        {"role": "user", "message": "Hola, quiero compartir comida"},
        {"role": "assistant", "message": "¡Genial! ¿Qué tipo de comida?"},
    ]
    # Bare "sí" is not detectable as Spanish on its own; history must win.
    assert eng._detect_lang_sticky("sí", history=history, profile=None) == "es"


def test_sticky_short_ok_with_profile_es_now_returns_en():
    """Policy change (May 2026): 'ok' is an English marker, so it wins
    over profile.language='es'. Previously sticky-language returned
    'es' here, which caused the AI to reply in Spanish to plain English
    'ok' / 'thanks' / 'hi' acknowledgements. Users complained, so
    English markers now beat profile preference."""
    eng = ConversationEngine()
    profile = {"language": "es"}
    assert eng._detect_lang_sticky("ok", history=None, profile=profile) == "en"


def test_sticky_truly_ambiguous_short_token_with_profile_es():
    """A non-English non-Spanish single token (e.g. an emoji or '...')
    should still fall through to profile.language."""
    eng = ConversationEngine()
    profile = {"language": "es"}
    assert eng._detect_lang_sticky("...", history=None, profile=profile) == "es"


def test_sticky_english_message_overrides_when_strong():
    eng = ConversationEngine()
    # Strong English with no Spanish history → English.
    assert eng._detect_lang_sticky("Hello, can you help me find food?") == "en"


def test_sticky_spanish_message_wins_over_english_history():
    eng = ConversationEngine()
    history = [{"role": "user", "message": "Hello there"}]
    assert eng._detect_lang_sticky("¿Qué tienes disponible?", history=history) == "es"


def test_sticky_no_signals_defaults_english():
    eng = ConversationEngine()
    assert eng._detect_lang_sticky("ok", history=None, profile=None) == "en"


def test_sticky_history_dict_with_content_key_also_works():
    """An ambiguous token with Spanish history still falls back to es.
    Note 'ok' is now an English marker so we use an emoji here for a
    truly ambiguous case."""
    eng = ConversationEngine()
    history = [{"role": "assistant", "content": "Por supuesto, déjame buscar."}]
    assert eng._detect_lang_sticky("👍", history=history) == "es"


def test_clear_english_message_beats_spanish_history():
    """Regression: user reported the AI was replying in Spanish even
    when they asked in English. Cause was sticky-language sticking to
    Spanish whenever ANY recent history turn was Spanish. Now a clearly
    English current message (3+ ASCII words, no Spanish chars) wins."""
    eng = ConversationEngine()
    history = [
        {"role": "user", "message": "Hola, ¿qué tienes disponible?"},
        {"role": "assistant", "message": "Tenemos manzanas y pan."},
    ]
    assert eng._detect_lang_sticky(
        "show me directions to listing 5", history=history
    ) == "en"


def test_clear_english_message_beats_spanish_profile():
    """profile.language='es' should not override a clearly English
    current message — the user is writing in English right now."""
    eng = ConversationEngine()
    profile = {"language": "es"}
    assert eng._detect_lang_sticky(
        "can you help me find vegetables nearby", profile=profile
    ) == "en"


def test_short_english_greetings_beat_spanish_profile_and_history():
    """Reported May 17, 2026: AI was replying in Spanish to short
    English messages like 'hi', 'hello', 'thanks', 'help', 'okay'
    when the user had any Spanish profile or history. English markers
    must now win for these too."""
    eng = ConversationEngine()
    history = [
        {"role": "user", "message": "Hola"},
        {"role": "assistant", "message": "¿En qué te ayudo?"},
    ]
    profile = {"language": "es"}
    for msg in ["hi", "hello", "hey", "thanks", "help", "okay", "yes", "no"]:
        assert eng._detect_lang_sticky(
            msg, history=history, profile=profile
        ) == "en", f"expected 'en' for {msg!r}"
