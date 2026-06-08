"""
Tests for backend audio endpoints: /api/ai/voice, /api/ai/transcribe, /api/ai/tts
==================================================================================
Also covers the Whisper hallucination filter (_is_whisper_noise).

Run:
    cd <project-root>
    python -m pytest backend/tests/test_audio_endpoints.py -v
"""

import io
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Patch env vars BEFORE importing the app (module-level config reads)
# ---------------------------------------------------------------------------
_ENV = {
    "OPENAI_API_KEY": "sk-test-key",
    "SUPABASE_URL": "https://test.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
    "MAPBOX_TOKEN": "pk.test-mapbox",
}

with patch.dict("os.environ", _ENV, clear=False):
    from backend.app import app, _is_whisper_noise

TEST_USER_ID = "c4dcbd93-081e-4160-87eb-1d51d444413a"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """Synchronous TestClient for FastAPI (uses httpx under the hood)."""
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _authenticated():
    """Treat HTTP requests as authenticated as TEST_USER_ID.

    The voice endpoint enforces ``_require_auth_for_user``: any real (non
    nil-UUID) user_id must present a matching Supabase JWT. The TestClient
    can't mint a real token, so we patch the JWT validator to return the
    test user. Production auth is unchanged — this only affects the harness.
    """
    with patch("backend.app._authenticate_request", new_callable=AsyncMock,
               return_value=TEST_USER_ID):
        yield


def _fake_audio_file(content: bytes = b"fake-audio-data", filename: str = "test.webm", content_type: str = "audio/webm"):
    """Build an UploadFile-compatible tuple for TestClient multipart."""
    return ("audio", (filename, io.BytesIO(content), content_type))


def _chat_result(text="Hello!", lang="en", transcript=None):
    """Minimal dict matching AIChatResponse."""
    return {
        "text": text,
        "audio_url": None,
        "user_id": TEST_USER_ID,
        "lang": lang,
        "conversation_id": "conv-123",
        "transcript": transcript,
        "timestamp": "2026-04-15T00:00:00+00:00",
    }


# ===================================================================
# 1. Whisper Hallucination Filter (_is_whisper_noise)
# ===================================================================

class TestWhisperNoiseFilter:
    def test_short_text_is_noise(self):
        assert _is_whisper_noise("hi") is True
        assert _is_whisper_noise("") is True
        assert _is_whisper_noise("  ") is True

    def test_exact_noise_phrases(self):
        assert _is_whisper_noise("Thank you.") is True
        assert _is_whisper_noise("Thanks for watching") is True
        assert _is_whisper_noise("Subscribe") is True
        assert _is_whisper_noise("Music") is True
        assert _is_whisper_noise("Bye bye") is True

    def test_all_noise_words(self):
        assert _is_whisper_noise("um uh oh yeah") is True
        assert _is_whisper_noise("thank you very much please") is True

    def test_repeated_phrase(self):
        assert _is_whisper_noise("thank thank thank") is True
        assert _is_whisper_noise("you you you you") is True

    def test_high_non_ascii_ratio(self):
        # More than 50% non-ASCII chars
        assert _is_whisper_noise("日本語のテキスト") is True

    def test_real_speech_not_filtered(self):
        assert _is_whisper_noise("I need food near downtown") is False
        assert _is_whisper_noise("Where can I pick up groceries today?") is False
        assert _is_whisper_noise("Hola, necesito ayuda con mi pedido") is False

    def test_punctuation_stripped_for_matching(self):
        assert _is_whisper_noise("Thank you!!!") is True
        assert _is_whisper_noise("...silence...") is True

    def test_gwynple_whisper_artifact(self):
        assert _is_whisper_noise("Gwynple") is True

    def test_mixed_real_and_noise_passes(self):
        assert _is_whisper_noise("Thank you for sharing food with us today") is False


# ===================================================================
# 2. /api/ai/voice endpoint
# ===================================================================

class TestVoiceEndpoint:
    @patch("backend.app.conversation_engine")
    def test_voice_success(self, mock_engine, client):
        """Valid audio → transcribe → chat → response with transcript."""
        mock_engine.transcribe_audio = AsyncMock(return_value="Find food near me")
        mock_engine.chat = AsyncMock(return_value=_chat_result(
            text="Here's food nearby!", transcript="Find food near me"
        ))

        resp = client.post(
            "/api/ai/voice",
            files=[_fake_audio_file()],
            data={"user_id": TEST_USER_ID, "include_audio": "false"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["text"] == "Here's food nearby!"
        assert data["transcript"] == "Find food near me"

    @patch("backend.app.conversation_engine")
    def test_voice_filters_noise(self, mock_engine, client):
        """Whisper noise should be rejected with 400."""
        mock_engine.transcribe_audio = AsyncMock(return_value="Thank you")

        resp = client.post(
            "/api/ai/voice",
            files=[_fake_audio_file()],
            data={"user_id": TEST_USER_ID},
        )
        assert resp.status_code == 400
        assert "could not understand" in resp.json()["detail"].lower()

    def test_voice_invalid_uuid(self, client):
        """Non-UUID user_id should be rejected."""
        resp = client.post(
            "/api/ai/voice",
            files=[_fake_audio_file()],
            data={"user_id": "not-a-uuid"},
        )
        assert resp.status_code == 400

    def test_voice_unsupported_audio_type(self, client):
        """Non-audio content types should be rejected."""
        resp = client.post(
            "/api/ai/voice",
            files=[("audio", ("test.txt", io.BytesIO(b"data"), "text/plain"))],
            data={"user_id": TEST_USER_ID},
        )
        assert resp.status_code == 400
        assert "unsupported audio type" in resp.json()["detail"].lower()

    def test_voice_empty_audio(self, client):
        """Empty audio file should be rejected."""
        resp = client.post(
            "/api/ai/voice",
            files=[_fake_audio_file(content=b"")],
            data={"user_id": TEST_USER_ID},
        )
        assert resp.status_code == 400
        assert "empty" in resp.json()["detail"].lower()

    @patch("backend.app.conversation_engine")
    def test_voice_timeout_returns_504(self, mock_engine, client):
        """Whisper timeout should return 504."""
        mock_engine.transcribe_audio = AsyncMock(
            side_effect=httpx.TimeoutException("timeout")
        )

        resp = client.post(
            "/api/ai/voice",
            files=[_fake_audio_file()],
            data={"user_id": TEST_USER_ID},
        )
        assert resp.status_code == 504
        body = resp.json()
        assert body.get("error_code") == "timeout"
        assert body.get("retryable") is True

    @patch("backend.app.conversation_engine")
    def test_voice_runtime_error_returns_503(self, mock_engine, client):
        """RuntimeError (e.g. missing API key) should return 503."""
        mock_engine.transcribe_audio = AsyncMock(
            side_effect=RuntimeError("OPENAI_API_KEY not configured")
        )

        resp = client.post(
            "/api/ai/voice",
            files=[_fake_audio_file()],
            data={"user_id": TEST_USER_ID},
        )
        assert resp.status_code == 503
        assert resp.json().get("error_code") == "model_unavailable"

    @patch("backend.app.conversation_engine")
    def test_voice_codec_params_stripped(self, mock_engine, client):
        """Content-type with codec params (e.g. audio/webm;codecs=opus) should be accepted."""
        mock_engine.transcribe_audio = AsyncMock(return_value="Hello there")
        mock_engine.chat = AsyncMock(return_value=_chat_result(text="Hi!"))

        resp = client.post(
            "/api/ai/voice",
            files=[("audio", ("test.webm", io.BytesIO(b"audio-data"), "audio/webm;codecs=opus"))],
            data={"user_id": TEST_USER_ID, "include_audio": "false"},
        )
        assert resp.status_code == 200

    @patch("backend.app.conversation_engine")
    def test_voice_spanish_transcript(self, mock_engine, client):
        """Spanish audio should flow through correctly."""
        mock_engine.transcribe_audio = AsyncMock(return_value="Necesito comida cerca de aquí")
        mock_engine.chat = AsyncMock(return_value=_chat_result(
            text="Aquí hay comida disponible.", lang="es",
            transcript="Necesito comida cerca de aquí",
        ))

        resp = client.post(
            "/api/ai/voice",
            files=[_fake_audio_file()],
            data={"user_id": TEST_USER_ID, "include_audio": "false"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["lang"] == "es"
        assert data["transcript"] == "Necesito comida cerca de aquí"


# ===================================================================
# 3. /api/ai/transcribe endpoint
# ===================================================================

class TestTranscribeEndpoint:
    @patch("backend.app.conversation_engine")
    def test_transcribe_success(self, mock_engine, client):
        """Valid audio should return transcript text."""
        mock_engine.transcribe_audio = AsyncMock(return_value="I want to share food")

        resp = client.post(
            "/api/ai/transcribe",
            files=[_fake_audio_file()],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["transcript"] == "I want to share food"
        assert data["filtered"] is False

    @patch("backend.app.conversation_engine")
    def test_transcribe_filters_noise(self, mock_engine, client):
        """Whisper noise should return empty transcript with filtered=True."""
        mock_engine.transcribe_audio = AsyncMock(return_value="Thank you for watching")

        resp = client.post(
            "/api/ai/transcribe",
            files=[_fake_audio_file()],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["transcript"] == ""
        assert data["filtered"] is True

    def test_transcribe_unsupported_type(self, client):
        """Non-audio types should be rejected."""
        resp = client.post(
            "/api/ai/transcribe",
            files=[("audio", ("test.pdf", io.BytesIO(b"data"), "application/pdf"))],
        )
        assert resp.status_code == 400

    def test_transcribe_empty_file(self, client):
        """Empty audio should be rejected."""
        resp = client.post(
            "/api/ai/transcribe",
            files=[_fake_audio_file(content=b"")],
        )
        assert resp.status_code == 400

    @patch("backend.app.conversation_engine")
    def test_transcribe_timeout_returns_504(self, mock_engine, client):
        """Whisper timeout should return 504."""
        mock_engine.transcribe_audio = AsyncMock(
            side_effect=httpx.TimeoutException("timeout")
        )

        resp = client.post(
            "/api/ai/transcribe",
            files=[_fake_audio_file()],
        )
        assert resp.status_code == 504

    @patch("backend.app.conversation_engine")
    def test_transcribe_runtime_error_returns_503(self, mock_engine, client):
        """RuntimeError should return 503."""
        mock_engine.transcribe_audio = AsyncMock(
            side_effect=RuntimeError("API key missing")
        )

        resp = client.post(
            "/api/ai/transcribe",
            files=[_fake_audio_file()],
        )
        assert resp.status_code == 503
        assert resp.json().get("error_code") == "model_unavailable"

    @patch("backend.app.conversation_engine")
    def test_transcribe_strips_whitespace(self, mock_engine, client):
        """Transcript should be stripped of leading/trailing whitespace."""
        mock_engine.transcribe_audio = AsyncMock(return_value="  Hello world  ")

        resp = client.post(
            "/api/ai/transcribe",
            files=[_fake_audio_file()],
        )
        assert resp.status_code == 200
        assert resp.json()["transcript"] == "Hello world"

    def test_transcribe_all_audio_types_accepted(self, client):
        """All allowed audio MIME types should pass validation."""
        allowed = [
            ("audio/webm", "test.webm"),
            ("audio/wav", "test.wav"),
            ("audio/mpeg", "test.mp3"),
            ("audio/mp4", "test.m4a"),
            ("audio/ogg", "test.ogg"),
            ("audio/mp3", "test.mp3"),
        ]
        for mime, fname in allowed:
            with patch("backend.app.conversation_engine") as mock_eng:
                mock_eng.transcribe_audio = AsyncMock(return_value="Test transcript")
                resp = client.post(
                    "/api/ai/transcribe",
                    files=[("audio", (fname, io.BytesIO(b"audio-data"), mime))],
                )
                assert resp.status_code == 200, f"Failed for {mime}"


# ===================================================================
# 4. /api/ai/tts endpoint
# ===================================================================

class TestTTSEndpoint:
    @patch("backend.app.conversation_engine")
    def test_tts_success(self, mock_engine, client):
        """Valid text should return audio/mpeg bytes."""
        mock_engine.generate_speech = AsyncMock(return_value=b"\xff\xfb\x90\x00fake-mp3")

        resp = client.post(
            "/api/ai/tts",
            json={"text": "Hello world", "lang": "en"},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "audio/mpeg"
        assert len(resp.content) > 0

    @patch("backend.app.conversation_engine")
    def test_tts_spanish(self, mock_engine, client):
        """Spanish TTS should pass lang='es' to the engine."""
        mock_engine.generate_speech = AsyncMock(return_value=b"fake-audio")

        resp = client.post(
            "/api/ai/tts",
            json={"text": "Hola mundo", "lang": "es"},
        )
        assert resp.status_code == 200
        mock_engine.generate_speech.assert_called_once_with("Hola mundo", lang="es")

    @patch("backend.app.conversation_engine")
    def test_tts_default_lang_is_english(self, mock_engine, client):
        """Omitting lang should default to 'en'."""
        mock_engine.generate_speech = AsyncMock(return_value=b"fake-audio")

        resp = client.post(
            "/api/ai/tts",
            json={"text": "Hello"},
        )
        assert resp.status_code == 200
        mock_engine.generate_speech.assert_called_once_with("Hello", lang="en")

    def test_tts_empty_text_rejected(self, client):
        """Empty text should fail Pydantic validation."""
        resp = client.post(
            "/api/ai/tts",
            json={"text": ""},
        )
        assert resp.status_code == 422  # Pydantic validation error

    @patch("backend.app.conversation_engine")
    def test_tts_runtime_error_returns_503(self, mock_engine, client):
        """RuntimeError (API key issue) should return 503."""
        mock_engine.generate_speech = AsyncMock(
            side_effect=RuntimeError("OPENAI_API_KEY not configured")
        )

        resp = client.post(
            "/api/ai/tts",
            json={"text": "Hello"},
        )
        assert resp.status_code == 503
        assert resp.json().get("error_code") == "model_unavailable"

    @patch("backend.app.conversation_engine")
    def test_tts_upstream_error_returns_503(self, mock_engine, client):
        """HTTP 5xx from OpenAI should return retryable model_unavailable."""
        mock_resp = httpx.Response(500, request=httpx.Request("POST", "http://test"))
        mock_engine.generate_speech = AsyncMock(
            side_effect=httpx.HTTPStatusError("500", request=mock_resp.request, response=mock_resp)
        )

        resp = client.post(
            "/api/ai/tts",
            json={"text": "Hello"},
        )
        assert resp.status_code == 503
        assert resp.json().get("error_code") == "model_unavailable"

    @patch("backend.app.conversation_engine")
    def test_tts_generic_error_returns_500(self, mock_engine, client):
        """Unexpected errors should return structured internal error."""
        mock_engine.generate_speech = AsyncMock(
            side_effect=ValueError("unexpected")
        )

        resp = client.post(
            "/api/ai/tts",
            json={"text": "Hello"},
        )
        assert resp.status_code == 500
        assert resp.json().get("error_code") == "internal"
