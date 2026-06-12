"""
DoGoods AI Conversation Engine — Supabase edition.

Talks to:
  - OpenAI GPT-4.1 (reasoning + tool calls)
  - OpenAI Whisper (speech-to-text)
  - OpenAI TTS (text-to-speech)

Conversation history, user profile, and reminders are persisted via the
Supabase REST API (PostgREST). Relevant tables (RLS-protected):
ai_conversations, ai_reminders, ai_feedback, users.
"""
# This module deals with dynamically-shaped JSON from Supabase / OpenAI.
# Fully typing every dict shape would require TypedDicts across hundreds
# of lines for zero runtime benefit, so we relax the noisier "unknown
# type" reports for this file only.
# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportMissingTypeArgument=false, reportUnnecessaryIsInstance=false, reportUnusedVariable=false, reportUnusedFunction=false
from __future__ import annotations


import asyncio
import json
import logging
import os
import re
import time
from collections import deque
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

import httpx
from dotenv import load_dotenv

# Load .env from project root (this file lives in <root>/backend/ai_engine.py)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai_engine")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = "https://api.openai.com/v1"
# Chat / tool-calling: gpt-4.1 has stronger reasoning and more reliable
# tool-calling than gpt-4o, with the same JSON-schema function-calling
# API. Override via AI_CHAT_MODEL if you want a different model.
CHAT_MODEL = os.getenv("AI_CHAT_MODEL", "gpt-4.1")
# Follow-up summary after tool execution doesn't need full-size model;
# gpt-4.1-mini is a good cost/quality balance.
FOLLOWUP_MODEL = os.getenv("AI_FOLLOWUP_MODEL", "gpt-4.1-mini")
WHISPER_MODEL = os.getenv("AI_WHISPER_MODEL", "whisper-1")
TTS_MODEL = os.getenv("AI_TTS_MODEL", "tts-1")
TTS_VOICE_EN = os.getenv("AI_TTS_VOICE", "nova")
TTS_VOICE_ES = os.getenv("AI_TTS_VOICE_ES", "nova")

# Fallback model chains: if the primary model is unavailable on this API key
# (404 / model_not_found), the backend automatically tries the next model in
# the list so users never see the "AI service down" message just because the
# account can't access gpt-4.1.
CHAT_MODEL_FALLBACKS: list[str] = [
    m.strip() for m in
    os.getenv("AI_CHAT_MODEL_FALLBACKS", "gpt-4o,gpt-4o-mini").split(",")
    if m.strip()
]
FOLLOWUP_MODEL_FALLBACKS: list[str] = [
    m.strip() for m in
    os.getenv("AI_FOLLOWUP_MODEL_FALLBACKS", "gpt-4o-mini").split(",")
    if m.strip()
]

MAX_RETRIES = int(os.getenv("AI_MAX_RETRIES", "3"))
TIMEOUT_SECONDS = int(os.getenv("AI_TIMEOUT", "60"))

RATE_LIMIT_DEFAULT = int(os.getenv("AI_RATE_LIMIT", "50"))
RATE_LIMIT_WINDOW = 60

# ---------------------------------------------------------------------------
# Supabase configuration (PostgREST)
# ---------------------------------------------------------------------------
# Falls back to the VITE_-prefixed names so the same .env that powers the
# frontend works for the backend too (DoGoods ships a single .env file).

SUPABASE_URL = (
    os.getenv("SUPABASE_URL")
    or os.getenv("VITE_SUPABASE_URL", "")
).rstrip("/")
SUPABASE_SERVICE_KEY = (
    os.getenv("SUPABASE_SERVICE_KEY")
    or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
)
SUPABASE_ANON_KEY = (
    os.getenv("SUPABASE_ANON_KEY")
    or os.getenv("VITE_SUPABASE_ANON_KEY", "")
)
SUPABASE_TIMEOUT = float(os.getenv("SUPABASE_TIMEOUT", "10"))

# Backwards-compatible alias imported by backend/tools.py.
DEFAULT_MODEL = CHAT_MODEL

TRAINING_DATA_PATH = os.path.join(os.path.dirname(__file__), "ai_training_data.json")

# Shared HTTP client
_http_client: Optional[httpx.AsyncClient] = None


def _get_http_client(timeout: float = TIMEOUT_SECONDS) -> httpx.AsyncClient:
    """Return the shared HTTP client, creating it with a generous default timeout.

    NOTE: callers MUST pass an explicit per-request timeout to client.request()
    because the client's default is locked at construction time. This function
    no longer recreates the client when a different timeout is requested.
    """
    global _http_client
    if _http_client is None or _http_client.is_closed:
        # Use the largest sane timeout as the client default so it never
        # under-times a long OpenAI tool-calling round even if the first
        # caller asked for a smaller window.
        client_timeout = max(timeout, TIMEOUT_SECONDS, 60.0)
        _http_client = httpx.AsyncClient(timeout=client_timeout)
    return _http_client


async def close_http_client() -> None:
    global _http_client
    if _http_client and not _http_client.is_closed:
        await _http_client.aclose()


# ---------------------------------------------------------------------------
# Supabase REST helpers (used by ai_engine, app.py, and tools.py)
# ---------------------------------------------------------------------------

def _supabase_headers(extra: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Accept": "application/json",
    }
    if extra:
        headers.update(extra)
    return headers


async def supabase_get(table: str, params: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    """GET rows from a Supabase table via PostgREST.

    Returns the parsed JSON array. Returns [] (instead of raising) when
    Supabase isn't configured so the backend degrades gracefully in dev.
    Also returns [] on 4xx (missing table/column, RLS denial) so a single
    bad query doesn't take down an entire feature.
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return []
    client = _get_http_client(SUPABASE_TIMEOUT)
    try:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/{table}",
            params=params or {},
            headers=_supabase_headers(),
            timeout=SUPABASE_TIMEOUT,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("supabase_get %s network error: %s", table, exc)
        return []
    if resp.status_code >= 400:
        # Log and degrade gracefully instead of raising.
        logger.warning(
            "supabase_get %s -> %s: %s",
            table,
            resp.status_code,
            resp.text[:200],
        )
        return []
    try:
        data = resp.json()
    except Exception:  # noqa: BLE001
        return []
    return data if isinstance(data, list) else []


async def supabase_post(table: str, body: Any) -> Any:
    """Insert one or more rows into a Supabase table via PostgREST."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return {}
    client = _get_http_client(SUPABASE_TIMEOUT)
    resp = await client.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        json=body,
        headers=_supabase_headers({
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }),
        timeout=SUPABASE_TIMEOUT,
    )
    resp.raise_for_status()
    try:
        return resp.json()
    except Exception:
        return {}


async def supabase_patch(table: str, params: dict[str, Any], body: dict[str, Any]) -> Any:
    """Update rows matching the given PostgREST filter params."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return {}
    client = _get_http_client(SUPABASE_TIMEOUT)
    resp = await client.patch(
        f"{SUPABASE_URL}/rest/v1/{table}",
        params=params,
        json=body,
        headers=_supabase_headers({
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }),
        timeout=SUPABASE_TIMEOUT,
    )
    resp.raise_for_status()
    try:
        return resp.json()
    except Exception:
        return {}


async def supabase_delete(table: str, params: dict[str, Any]) -> int:
    """Delete rows matching the given PostgREST params. Returns row count."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return 0
    client = _get_http_client(SUPABASE_TIMEOUT)
    resp = await client.delete(
        f"{SUPABASE_URL}/rest/v1/{table}",
        params=params,
        headers=_supabase_headers({"Prefer": "return=representation"}),
        timeout=SUPABASE_TIMEOUT,
    )
    resp.raise_for_status()
    try:
        rows = resp.json()
        return len(rows) if isinstance(rows, list) else 0
    except Exception:
        return 0


async def fetch_donor_listing_defaults(user_id: str) -> dict[str, Any]:
    """Load donor profile fields to stamp onto new food_listings rows."""
    if not user_id:
        return {}
    rows = await supabase_get("users", {
        "id": f"eq.{user_id}",
        # Only select columns that actually exist on `users`. Requesting
        # missing columns (city/state/zip) makes PostgREST 400 the whole
        # query, which silently returned {} and left AI-posted listings with
        # no location / map pin. Use `address` (text) for the pickup address;
        # `location` is a JSON {lat,lng} column and is excluded intentionally.
        "select": (
            "id,name,email,phone,address,organization,"
            "community_id,latitude,longitude"
        ),
        "limit": "1",
    })
    return rows[0] if rows else {}


def apply_donor_defaults_to_listing(row: dict[str, Any], donor: dict[str, Any] | None) -> dict[str, Any]:
    """Copy donor profile + coordinates onto a listing row when missing."""
    if not donor:
        return row

    if donor.get("community_id") and not row.get("community_id"):
        row["community_id"] = donor["community_id"]

    for src, dest in (
        ("name", "donor_name"),
        ("email", "donor_email"),
        ("phone", "donor_phone"),
        ("organization", "donor_type"),
    ):
        if donor.get(src) and not row.get(dest):
            row[dest] = donor[src]

    lat = donor.get("latitude")
    lng = donor.get("longitude")
    try:
        if lat is not None and lng is not None and row.get("latitude") is None:
            row["latitude"] = float(lat)
            row["longitude"] = float(lng)
    except (TypeError, ValueError):
        pass

    # When the donor didn't dictate a pickup address, fall back to the address
    # saved on their profile so the listing still shows a location on the card
    # and a pin on the map.
    # IMPORTANT: use only `address` (plain text) — `location` in the users table
    # is a JSON {latitude, longitude} column and must NOT be used as an address
    # string. Coordinates are already applied above from latitude/longitude.
    if not row.get("location") and not row.get("full_address"):
        donor_addr = str(donor.get("address") or "").strip()
        if donor_addr:
            row["location"] = donor_addr[:200]
            row["full_address"] = donor_addr[:200]

    return row


# ---------------------------------------------------------------------------
# Spanish detection
# ---------------------------------------------------------------------------

_SPANISH_MARKERS = {
    "hola", "gracias", "por favor", "ayuda", "comida", "buscar",
    "quiero", "necesito", "dónde", "donde", "cómo", "como",
    "cuándo", "cuando", "tengo", "puedo", "buenos", "buenas",
    "qué", "que", "disponible", "recoger", "compartir",
    "alimentos", "comunidad", "recordatorio", "horario",
    "muéstrame", "muestrame", "muestra", "mostrar", "dame",
    "panel", "mi", "tu", "para", "con", "sin", "una", "uno",
    "soy", "eres", "estoy", "está", "ser", "hacer", "tiene",
}

# English-only markers used to flip sticky language back to English
# when the user clearly writes in English. These are words that don't
# also exist in Spanish, so any single occurrence is a strong signal.
_ENGLISH_MARKERS = {
    "hi", "hello", "hey", "thanks", "thank", "please", "yes", "yeah",
    "no", "nope", "ok", "okay", "sure", "the", "a", "an", "is", "are",
    "was", "were", "be", "been", "being", "have", "has", "had", "do",
    "does", "did", "will", "would", "should", "could", "can", "may",
    "might", "must", "i", "you", "your", "yours", "me", "my", "mine",
    "we", "us", "our", "they", "them", "their", "he", "she", "him",
    "her", "what", "where", "when", "why", "how", "which", "who",
    "show", "find", "get", "give", "send", "make", "want", "need",
    "help", "tell", "ask", "see", "look", "food", "near", "nearby",
    "around", "here", "there", "today", "tomorrow", "now", "later",
    "directions", "listing", "listings", "claim", "pickup", "drop",
    "off", "on", "in", "at", "to", "from", "with", "without", "for",
    "and", "or", "but", "if", "because", "so", "than", "then",
}


def detect_spanish(text: str) -> bool:
    lower = text.lower()
    words = set(re.split(r"\W+", lower))
    marker_hits = len(words & _SPANISH_MARKERS)
    # Spanish-specific punctuation is a strong standalone signal
    if re.search(r"[¿¡ñ]", lower):
        return True
    # Two or more accented Latin chars → very likely Spanish
    accent_hits = len(re.findall(r"[áéíóúü]", lower))
    if accent_hits >= 2:
        return True
    has_accent = accent_hits >= 1
    return marker_hits >= 2 or (marker_hits >= 1 and has_accent)


def detect_english(text: str) -> bool:
    """Symmetric to detect_spanish — returns True when the message
    contains at least one English-only marker word and has no Spanish-
    specific characters. Used so short messages like 'hi', 'thanks',
    'ok' are correctly identified as English even when the user has a
    Spanish profile or Spanish conversation history."""
    if not text:
        return False
    lower = text.lower()
    if re.search(r"[¿¡ñáéíóúü]", lower):
        return False
    words = set(re.split(r"\W+", lower))
    return bool(words & _ENGLISH_MARKERS)


# ---------------------------------------------------------------------------
# Canned fallback responses
# ---------------------------------------------------------------------------

CANNED_RESPONSES = {
    "en": {
        "timeout": "I'm taking longer than usual — please try again in a moment. In the meantime you can browse food on the Find Food page.",
        "api_down": "I can't reach my AI service right now. You can still browse listings and check your dashboard — I'll be back shortly!",
        "general_error": "Something went wrong on my end. Please try again, or contact support if the issue persists.",
        "tool_error": "I couldn't look that up right now, but I can still help with general questions.",
    },
    "es": {
        "timeout": "Estoy tardando más de lo normal — inténtalo de nuevo en un momento. Mientras tanto puedes explorar comida en Buscar Comida.",
        "api_down": "No puedo conectarme a mi servicio de IA en este momento. Aún puedes explorar los listados y revisar tu panel.",
        "general_error": "Algo salió mal. Inténtalo de nuevo o contacta a soporte.",
        "tool_error": "No pude buscar esa información, pero puedo ayudarte con preguntas generales.",
    },
}


def get_canned_response(error_type: str, lang: str = "en") -> str:
    lang_key = "es" if lang == "es" else "en"
    return CANNED_RESPONSES[lang_key].get(error_type, CANNED_RESPONSES[lang_key]["general_error"])


# ---------------------------------------------------------------------------
# Rate limiter (per-IP, in-memory)
# ---------------------------------------------------------------------------

_rate_store: dict[str, list[float]] = {}
_user_rate_store: dict[str, list[float]] = {}


def check_rate_limit(client_ip: str, limit: int = RATE_LIMIT_DEFAULT) -> bool:
    now = time.time()
    timestamps = _rate_store.setdefault(client_ip, [])
    _rate_store[client_ip] = [t for t in timestamps if now - t < RATE_LIMIT_WINDOW]
    if len(_rate_store[client_ip]) >= limit:
        return False
    _rate_store[client_ip].append(now)
    return True


def check_user_rate_limit(user_id: str, limit: int = RATE_LIMIT_DEFAULT) -> bool:
    """Per-user-id bucket so shared-IP (NAT, school, mobile) users don't
    throttle each other and a single authenticated abuser can't drain a
    shared IP's budget for legitimate neighbours."""
    if not user_id:
        return True
    now = time.time()
    timestamps = _user_rate_store.setdefault(user_id, [])
    _user_rate_store[user_id] = [t for t in timestamps if now - t < RATE_LIMIT_WINDOW]
    if len(_user_rate_store[user_id]) >= limit:
        return False
    _user_rate_store[user_id].append(now)
    return True


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, reset_timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: float = 0

    def record_success(self) -> None:
        self.failure_count = 0
        self.state = CircuitState.CLOSED

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN

    def allow_request(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.reset_timeout:
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        return True


_circuit = CircuitBreaker()


class _UpstreamMetrics:
    """Rolling success/error counter for upstream (OpenAI) calls.

    Tracks the outcome of the last ``window`` requests so operations can verify
    the live error rate (target < 5%). In-process only; resets on restart.
    """

    def __init__(self, window: int = 200):
        self._outcomes: deque[bool] = deque(maxlen=window)
        self.total = 0
        self.errors = 0

    def record(self, ok: bool) -> None:
        self._outcomes.append(ok)
        self.total += 1
        if not ok:
            self.errors += 1

    @property
    def error_rate(self) -> float:
        """Error rate over the rolling window (0.0–1.0)."""
        if not self._outcomes:
            return 0.0
        return sum(1 for ok in self._outcomes if not ok) / len(self._outcomes)

    def snapshot(self) -> dict[str, Any]:
        window = len(self._outcomes)
        rate = self.error_rate
        return {
            "window": window,
            "window_errors": sum(1 for ok in self._outcomes if not ok),
            "error_rate": round(rate, 4),
            "error_rate_pct": round(rate * 100, 2),
            "within_threshold": rate < 0.05,
            "total_requests": self.total,
            "total_errors": self.errors,
        }


_upstream_metrics = _UpstreamMetrics()


# ---------------------------------------------------------------------------
# Structured errors — machine-readable codes so the frontend can decide
# whether to offer Retry, escalate to support, or auto-back-off.
#
# All public /api/ai/* endpoints translate uncaught exceptions through
# `classify_exception` and return the resulting AIError as JSON with the
# matching HTTP status. The frontend reads `error_code` / `retryable` and
# renders an appropriate inline action (Retry button, rate-limit hint, etc.).
# ---------------------------------------------------------------------------

class AIErrorCode(str, Enum):
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    MODEL_UNAVAILABLE = "model_unavailable"
    AUTH = "auth"
    INVALID_INPUT = "invalid_input"
    CIRCUIT_OPEN = "circuit_open"
    INTERNAL = "internal"


class AIError(Exception):
    """Structured error raised by the AI engine.

    Carries enough metadata (code, retryability, retry-after, HTTP status)
    that the API layer can produce a consistent JSON response without each
    endpoint repeating mapping logic.
    """

    def __init__(
        self,
        code: AIErrorCode,
        message: str,
        *,
        retryable: bool = False,
        retry_after_seconds: Optional[int] = None,
        http_status: int = 500,
        cause: Optional[BaseException] = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds
        self.http_status = http_status
        self.cause = cause

    def to_dict(self) -> dict[str, Any]:
        body = {
            "error_code": self.code.value,
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.retry_after_seconds is not None:
            body["retry_after_seconds"] = self.retry_after_seconds
        return body


def classify_exception(exc: BaseException) -> AIError:
    """Map any exception into a structured AIError suitable for API responses.

    Already-typed AIErrors pass through unchanged so callers can both raise
    AIError directly and rely on this for catch-all conversion in the
    endpoint layer.
    """
    if isinstance(exc, AIError):
        return exc

    msg = str(exc) or exc.__class__.__name__

    if isinstance(exc, httpx.TimeoutException):
        return AIError(
            AIErrorCode.TIMEOUT,
            "The AI service took too long to respond. Please try again.",
            retryable=True,
            retry_after_seconds=5,
            http_status=504,
            cause=exc,
        )

    if isinstance(exc, httpx.HTTPStatusError):
        sc = exc.response.status_code
        if sc == 429:
            retry_after = exc.response.headers.get("retry-after")
            try:
                retry_after_int = int(retry_after) if retry_after else 10
            except (TypeError, ValueError):
                retry_after_int = 10
            return AIError(
                AIErrorCode.RATE_LIMIT,
                "The AI is rate-limited right now. Please try again in a moment.",
                retryable=True,
                retry_after_seconds=retry_after_int,
                http_status=429,
                cause=exc,
            )
        if sc in (401, 403):
            return AIError(
                AIErrorCode.AUTH,
                "The AI service rejected our credentials. Please contact support.",
                retryable=False,
                http_status=502,  # upstream auth failure — not the user's fault
                cause=exc,
            )
        if sc in (400, 422):
            return AIError(
                AIErrorCode.INVALID_INPUT,
                "The AI service rejected the request as invalid.",
                retryable=False,
                http_status=400,
                cause=exc,
            )
        if sc >= 500:
            return AIError(
                AIErrorCode.MODEL_UNAVAILABLE,
                "The AI model is temporarily unavailable. Please try again.",
                retryable=True,
                retry_after_seconds=8,
                http_status=503,
                cause=exc,
            )

    # Our retry helper raises RuntimeError after exhausting attempts.
    if isinstance(exc, RuntimeError):
        lower = msg.lower()
        if "openai" in lower or "api key" in lower or "api_key" in lower:
            return AIError(
                AIErrorCode.MODEL_UNAVAILABLE,
                "The AI model is temporarily unavailable. Please try again.",
                retryable=True,
                retry_after_seconds=8,
                http_status=503,
                cause=exc,
            )

    if "circuit" in msg.lower():
        return AIError(
            AIErrorCode.CIRCUIT_OPEN,
            "AI service is recovering. Please try again in a few seconds.",
            retryable=True,
            retry_after_seconds=10,
            http_status=503,
            cause=exc,
        )

    # Default: unclassified internal error.
    return AIError(
        AIErrorCode.INTERNAL,
        "An unexpected AI error occurred.",
        retryable=False,
        http_status=500,
        cause=exc,
    )


# ---------------------------------------------------------------------------
# Token usage logging — lightweight observability so we notice cost regressions
# without needing to wire up a metrics backend yet.
# ---------------------------------------------------------------------------

# Soft warning threshold — adjust via env var. When a single chat completion
# burns more than this many total tokens, we log a WARNING so it surfaces in
# Railway/Sentry. Defaults to 12k which is well below model context limits but
# high enough that legitimate long conversations don't trigger noise.
_TOKEN_WARN_THRESHOLD = int(os.getenv("AI_TOKEN_WARN_THRESHOLD", "12000"))


def _log_token_usage(resp: "httpx.Response", label: str = "openai") -> None:
    """Peek at the OpenAI JSON response for the `usage` block and log it.

    Cheap (response body is already buffered by httpx); skips non-JSON
    responses (e.g. TTS audio) and never raises.
    """
    try:
        ct = resp.headers.get("content-type", "")
        if "application/json" not in ct:
            return
        data = resp.json()
        if not isinstance(data, dict):
            return
        usage = data.get("usage")
        if not isinstance(usage, dict):
            return
        prompt = int(usage.get("prompt_tokens", 0) or 0)
        completion = int(usage.get("completion_tokens", 0) or 0)
        total = int(usage.get("total_tokens", 0) or (prompt + completion))
        model = data.get("model") or "?"
        log_fn = logger.warning if total > _TOKEN_WARN_THRESHOLD else logger.info
        log_fn(
            "[%s] tokens prompt=%d completion=%d total=%d model=%s",
            label, prompt, completion, total, model,
        )
    except Exception:  # logging must never break the request
        pass


# ---------------------------------------------------------------------------
# OpenAI request helper
# ---------------------------------------------------------------------------

async def _openai_with_retry(
    method: str,
    url: str,
    *,
    headers: dict[str, Any],
    json_payload: dict[str, Any] | None = None,
    files: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    timeout: float = TIMEOUT_SECONDS,
    retries: int = MAX_RETRIES,
    label: str = "openai",
) -> httpx.Response:
    NON_RETRYABLE = {401, 403, 404, 422}
    last_exc: Exception | None = None

    for attempt in range(retries):
        try:
            client = _get_http_client(timeout)
            kwargs: dict[str, Any] = {"headers": headers, "timeout": timeout}
            if json_payload is not None:
                kwargs["json"] = json_payload
            if files is not None:
                kwargs["files"] = files
            if data is not None:
                kwargs["data"] = data

            resp = await client.request(method, url, **kwargs)

            if resp.status_code == 429:
                logger.warning("OpenAI 429 (rate limit) attempt %d/%d", attempt + 1, retries)
                _circuit.record_failure()
                await asyncio.sleep(min(2 ** attempt + 1, 10))
                continue
            if resp.status_code in NON_RETRYABLE:
                logger.error(
                    "OpenAI non-retryable %s: %s",
                    resp.status_code,
                    resp.text[:300],
                )
                resp.raise_for_status()
            if resp.status_code >= 500:
                logger.warning(
                    "OpenAI 5xx (%s) attempt %d/%d: %s",
                    resp.status_code, attempt + 1, retries, resp.text[:200],
                )
                _circuit.record_failure()
                await asyncio.sleep(min(2 ** attempt + 1, 10))
                continue

            resp.raise_for_status()
            _circuit.record_success()
            _upstream_metrics.record(ok=True)
            _log_token_usage(resp, label=label)
            return resp
        except httpx.HTTPStatusError:
            _upstream_metrics.record(ok=False)
            raise
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            last_exc = exc
            logger.warning(
                "OpenAI network error attempt %d/%d (timeout=%ss): %s",
                attempt + 1, retries, timeout, exc,
            )
            _circuit.record_failure()
            if attempt < retries - 1:
                await asyncio.sleep(min(2 ** attempt + 1, 10))

    _upstream_metrics.record(ok=False)
    raise RuntimeError(f"OpenAI request failed after {retries} attempts: {last_exc}")


def _is_model_access_error(exc: httpx.HTTPStatusError) -> bool:
    """Return True when OpenAI says the model is unknown / not available."""
    if exc.response.status_code not in (404, 422):
        return False
    try:
        body = exc.response.json()
        msg = str(body.get("error", {}).get("message", "")).lower()
        code = str(body.get("error", {}).get("code", "")).lower()
        return "model" in msg or code in ("model_not_found", "invalid_model")
    except Exception:
        return exc.response.status_code == 404


async def _openai_chat_with_model_fallback(
    primary_model: str,
    fallbacks: list[str],
    json_payload: dict[str, Any],
    headers: dict[str, Any],
    label: str = "openai",
) -> httpx.Response:
    """Try primary_model; on model-access error, try each fallback in order.

    All other errors (network, rate-limit, 5xx, auth) are raised immediately
    so the caller can apply its own retry / fallback logic.
    """
    models_to_try = [primary_model] + fallbacks
    for model in models_to_try:
        payload = {**json_payload, "model": model}
        try:
            resp = await _openai_with_retry(
                "POST",
                f"{OPENAI_BASE_URL}/chat/completions",
                headers=headers,
                json_payload=payload,
                label=label,
            )
            if model != primary_model:
                logger.info("Chat succeeded with fallback model %s (primary=%s)", model, primary_model)
            return resp
        except httpx.HTTPStatusError as exc:
            if _is_model_access_error(exc) and model != models_to_try[-1]:
                logger.warning(
                    "Model %s not accessible (%s), trying next fallback",
                    model, exc.response.status_code,
                )
                # Don't count a model-access error as a circuit failure —
                # it's a permanent config issue, not a transient outage.
                _circuit.failure_count = max(0, _circuit.failure_count - 1)
                continue
            raise
    # Should never reach here, but satisfy the type-checker
    raise RuntimeError("All models in fallback chain failed")


def _extract_content(response: dict[str, Any]) -> str:
    try:
        return response["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError("Unexpected AI response format") from exc


async def legacy_ai_request(endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Fire a simple OpenAI chat/completions call (used by recipes, storage tips)."""
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not configured")
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    resp = await _openai_with_retry(
        "POST",
        f"{OPENAI_BASE_URL}{endpoint}",
        headers=headers,
        json_payload=payload,
    )
    return resp.json()


# ---------------------------------------------------------------------------
# Training data + system prompt builder
# ---------------------------------------------------------------------------

def _load_training_data() -> dict[str, Any]:
    try:
        with open(TRAINING_DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning("Training data not found: %s", TRAINING_DATA_PATH)
        return {}


def _build_system_prompt(training_data: dict[str, Any]) -> str:
    sections: list[str] = []

    if "platform_overview" in training_data:
        sections.append(f"## Platform Overview\n{training_data['platform_overview']}")

    if "user_roles" in training_data:
        roles = "\n".join(
            f"- **{r['role']}**: {r['description']}"
            for r in training_data["user_roles"]
        )
        sections.append(f"## User Roles\n{roles}")

    if "processes" in training_data:
        procs = "\n".join(f"- {p}" for p in training_data["processes"])
        sections.append(f"## Key Processes\n{procs}")

    if "food_safety" in training_data:
        safety = "\n".join(f"- {s}" for s in training_data["food_safety"])
        sections.append(f"## Food Safety Guidelines\n{safety}")

    if "tone_guidelines" in training_data:
        sections.append(f"## Communication Style\n{training_data['tone_guidelines']}")

    if "spanish_guidelines" in training_data:
        sections.append(f"## Spanish Response Guidelines\n{training_data['spanish_guidelines']}")

    base = training_data.get(
        "system_base",
        "You are the DoGoods AI Assistant, a warm and helpful community food sharing assistant for the DoGoods platform. Always refer to the product as DoGoods.",
    )
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Hard rule: when the user asks the assistant to *do* something, the
    # assistant must call the matching tool instead of describing how the
    # user could do it themselves. Several user reports traced back to the
    # model replying with instructions ("go to the listing and tap Claim")
    # instead of calling claim_listing / post_food_listing / cancel_claim.
    action_policy = (
        "## Action-Taking Policy (CRITICAL)\n"
        "You are an AGENT, not a help article. When the user asks you to do "
        "something the platform supports, you MUST call the corresponding tool "
        "and report the result. Do NOT respond with step-by-step instructions "
        "telling the user to do it themselves.\n"
        "- 'claim X for me' / 'I want that one' / 'reserve it' -> FIRST ask "
        "'Ready to claim it?', then call claim_listing only after explicit yes\n"
        "- 'I got the code 1234' / 'confirm 1234' -> call confirm_claim\n"
        "- 'cancel my claim' / 'release it' -> call cancel_claim\n"
        "- 'post a listing for X' / 'donate Y' -> call post_food_listing\n"
        "- 'update my address/phone/diet' -> call update_user_profile\n"
        "- 'open/go to/take me to/show me the <page>' (Find Food, Share, "
        "Dashboard, Profile, Settings, Recipes, Notifications, My Listings, "
        "Receipts, etc.) -> call navigate_ui(action='navigate', path=...). "
        "Actually MOVE the user there — don't just tell them where to click. "
        "Then confirm in one short line ('Opened Find Food for you.').\n"
        "- 'open the map' / 'show me the map' -> navigate_ui(action='open_map')\n"
        "- 'what can I cook' / 'recipes from my food' -> "
        "navigate_ui(action='open_modal', target='meal-suggestions')\n"
        "Only ask a clarifying question if a REQUIRED parameter is genuinely "
        "missing (e.g. you don't know which listing they mean). Otherwise, "
        "call the tool first, then summarize what happened.\n"
        "\n"
        "### CLAIM VERIFICATION (ZERO-TOLERANCE POLICY)\n"
        "NEVER claim food without explicit user authorization. Before calling "
        "claim_listing, you MUST:\n"
        "  1. Present the food options from search_food_near_user results\n"
        "  2. Let the user pick one by name or number\n"
        "  3. Ask how many (if quantity > 1)\n"
        "  4. Ask 'Ready to claim it?' or 'Want me to lock it in?'\n"
        "  5. Wait for explicit affirmative: 'yes', 'go ahead', 'claim it'\n"
        "FORBIDDEN: Claiming when user says 'that one', 'sounds good', 'ok', "
        "'nice', 'I like that', or any ambiguous response. These express "
        "INTEREST, not authorization. Re-ask: 'Just to confirm — should I "
        "claim the <title> for you now?'\n"
        "If you claim food without following all 5 steps above in sequence, "
        "that is a CRITICAL ERROR and violates user trust.\n"
        "\n"
        "### NO-STALL RULE (ZERO TOLERANCE)\n"
        "NEVER reply with placeholder/stall text like 'one moment please', "
        "'I'll do that for you', 'let me check', 'hang on' WITHOUT also "
        "emitting a tool_call in the SAME response. If you announce an "
        "action, the tool_call MUST accompany the announcement — the user "
        "will not send another message to 'unblock' you. Either:\n"
        "  (a) call the tool now (preferred), or\n"
        "  (b) ask the single specific clarifying question you need.\n"
        "Stalling without a tool_call is a critical failure.\n"
        "\n"
        "### LISTING ID RESOLUTION\n"
        "When the user picks a listing by name (e.g. 'claim the kale', "
        "'I want the Fresh Organic Kale'), find the matching listing in "
        "the most recent search_food_near_user / get_recent_listings "
        "result you have in this conversation, and pass its numeric id as "
        "claim_listing's listing_id. If you do not yet have a listing list "
        "in context, call search_food_near_user FIRST (in the same turn) "
        "to fetch candidates — do not ask the user for the id.\n"
        "\n"
        "### ALWAYS PRESENT OPTIONS BEFORE CLAIMING (CRITICAL)\n"
        "Whenever the user expresses interest in food without naming a "
        "specific listing — e.g. 'I'm hungry', 'find me food', 'what's "
        "available?', 'I need produce', 'claim something for me', 'any "
        "bread nearby?', 'I want to eat' — you MUST:\n"
        "  1. Call search_food_near_user FIRST (do not claim anything yet). "
        "ALWAYS search when the user asks 'what's available' or similar — "
        "do NOT reuse cached search results because listings change as "
        "others claim food. The memory snapshot listings are for resolving "
        "'claim #3' or 'claim the bread' AFTER you already showed them "
        "options THIS turn, not for answering 'what's available'.\n"
        "  2. In your reply, list the available options as a NUMBERED list. "
        "For each item include: the title, distance (if available), and a "
        "short detail (quantity, expiration, or category). Keep it to the "
        "top 3-5 closest results so the user can scan quickly.\n"
        "  3. End with a clear question like 'Which one would you like to "
        "claim? Reply with the number or the name.'\n"
        "  4. ONLY after the user picks one, call claim_listing with the "
        "matching listing_id resolved from the list you just showed.\n"
        "Never claim a listing on the user's behalf without first showing "
        "them the options and getting an explicit pick. The single exception "
        "is when the user already names or numbers a specific listing in "
        "their current message AND that listing is in your most recent "
        "search result — then you may claim directly.\n"
        "When the user asks what's new, asks you to check new listings, "
        "or wants the latest recently-posted food, call get_recent_listings "
        "instead of search_food_near_user unless they specifically ask for "
        "nearby results.\n"
        "Example response format:\n"
        "  Here are the closest options near you:\n"
        "  1. Fresh Organic Kale — 0.4 mi, 2 bunches, expires tomorrow\n"
        "  2. Sourdough Loaves — 0.7 mi, 3 loaves, baked today\n"
        "  3. Mixed Berries — 1.1 mi, 1 pint, expires in 2 days\n"
        "  Which one would you like to claim? Reply with the number or name.\n"
        "\n"
        "### CONVERSATIONAL CLAIM FLOW (CRITICAL — TONE)\n"
        "Claiming should feel like texting a friend, not filing a ticket. "
        "Use the same one-question-at-a-time, warm-acknowledgement rhythm "
        "as the donor flow. ONE short question per turn. Mirror what the "
        "user said. Use defaults from their profile when sensible.\n"
        "\n"
        "Reference dialog (the model MUST emulate this rhythm):\n"
        "  Recipient: 'I'm hungry, what's nearby?'\n"
        "  AI:        <calls search_food_near_user, then>\n"
        "             'Here's what's close to you right now:\n"
        "              1. Sourdough Loaves — 0.4 mi, 3 loaves, baked today\n"
        "              2. Fresh Kale — 0.7 mi, 2 bunches, expires tomorrow\n"
        "              3. Mixed Berries — 1.1 mi, 1 pint\n"
        "              Which one sounds good?'\n"
        "  Recipient: 'the bread'\n"
        "  AI:        'Nice choice — how many loaves do you want? They have 3.'\n"
        "  Recipient: '2'\n"
        "  AI:        'Got it, 2 loaves. Picking them up yourself, or "
        "want to schedule a delivery?'\n"
        "  Recipient: 'pickup'\n"
        "  AI:        'Perfect. Want me to lock it in now?'\n"
        "  Recipient: 'yes'\n"
        "  AI:        <calls claim_listing(listing_id=...), then>\n"
        "             'Done! I claimed the Sourdough Loaves for you — "
        "pick them up at 379 S Pole St. Just let me know once you've "
        "got them. Want directions?'\n"
        "  Recipient: 'picked it up'\n"
        "  AI:        <calls confirm_claim>\n"
        "             'Pickup confirmed! Enjoy the bread 🍞'\n"
        # TODO(twilio): once Twilio SMS is wired up, claim_listing will
        # return a `confirm_code` + `sms_delivered` flag and start a
        # short auto-release timer. Restore the 4-digit-code narration
        # (e.g. 'Your pickup code is 4729 — show it to the donor … you
        # have N minutes to confirm before it auto-releases.') and the
        # 'I got the code 4729' confirm path at that point.
        "\n"
        "Hard rules for this flow:\n"
        "  1. ONE QUESTION PER TURN once the options are on screen. Don't "
        "ask 'how many AND pickup or delivery AND when' all at once.\n"
        "  2. ACKNOWLEDGE the recipient's pick warmly ('Nice choice', "
        "'Good pick', 'Perfect') before asking the next thing.\n"
        "  3. HANDLE STALE SEARCH DATA (CRITICAL) — Search results show "
        "quantities at the time of search, but listings can be claimed by "
        "others while you're talking. When the user picks a listing from "
        "search results that showed '5 loaves', DO NOT say 'They have 5' "
        "as if it's current. Instead say 'They had 5 when I last checked' "
        "or skip mentioning the number entirely and ask 'How many would "
        "you like?'. The claim_listing tool will fetch real-time data and "
        "return the actual availability. If the tool returns "
        "`quantity_clamped: true`, it means less was available than "
        "requested — relay this clearly: 'I claimed X for you (that's all "
        "that was left)' using the actual `quantity` from the tool result.\n"
        "  4. INFER QUANTITY DEFAULT — if the listing has only 1 unit "
        "available, skip the qty question. Otherwise ask how many they "
        "want, but understand that claim_listing claims the whole listing "
        "(no partial-claim API today). If the recipient wants fewer than "
        "are listed, just acknowledge that and proceed; the donor will "
        "hand them the right amount at pickup.\n"
        "  5. ALWAYS CONFIRM BEFORE CLAIMING (CRITICAL) — You MUST ask an "
        "explicit confirmation question before calling claim_listing. Use "
        "clear language like 'Ready to claim it?' or 'Want me to lock it "
        "in now?' or 'Shall I reserve this for you?'. ONLY proceed with "
        "the claim when the user responds with an explicit affirmative: "
        "'yes', 'yeah', 'yep', 'sure', 'go ahead', 'claim it', 'reserve "
        "it', 'lock it in', 'I'll take it'. DO NOT claim if the user just "
        "says 'that one', 'sounds good', 'nice', 'ok' (ambiguous — ask "
        "confirmation), or any message that could be expressing interest "
        "rather than authorizing action. If uncertain whether their reply "
        "is a clear yes, ask again: 'Just to confirm — should I claim the "
        "<title> for you now?'. Claiming food without explicit user "
        "authorization is a serious error.\n"
        "  6. AFTER CLAIMING, follow the ANNOUNCE CLAIM SUCCESS rules "
        "below — lead with the confirmation, tell them where to pick up, "
        "then offer a helpful next step ('Want directions?', 'Need the "
        "donor's number?'). Do NOT invent a confirmation code or a "
        "countdown timer.\n"
        # TODO(twilio): when SMS is live, re-add 'share the code (inline
        # if SMS failed), mention the auto-release window' to rule 5.

        "  7. CANCEL FLOW — if the user says 'cancel' / 'never mind' / "
        "'release it', acknowledge ('No problem, releasing it now…'), "
        "call cancel_claim, then confirm ('Released — it's back up for "
        "someone else.').\n"
        "  8. NEVER ask about technical fields (listing_id numbers, "
        "claim status enums). The recipient should never see an id.\n"
        "  9. STICK TO ONE LISTING (CRITICAL). Once the user has picked a "
        "specific listing and you are mid-claim for it (you asked 'how "
        "many?', 'pickup or delivery?', or 'want me to lock it in?'), a "
        "bare number in their next reply is the ANSWER to your pending "
        "question (the quantity / a confirmation) — it is NOT a new "
        "numbered selection from the earlier options list. Keep claiming "
        "the SAME listing. Do NOT switch to a different item, do NOT "
        "re-present the options, and do NOT start a new claim flow. Only "
        "treat a number as a fresh listing pick when NO claim is in "
        "progress (i.e. you just showed the numbered options and have not "
        "yet asked any per-item question). Example: you asked 'There are "
        "10 cans of Canned Beans available. How many would you like?' and "
        "the user says '5' -> that means 5 cans of Canned Beans, so "
        "proceed to confirm/claim the Canned Beans. It does NOT mean "
        "listing #5. If a number is impossible as a quantity (e.g. larger "
        "than what's available, or clearly a typo like '13510'), gently "
        "re-ask 'They have 10 — how many of those would you like?' rather "
        "than jumping to another listing.\n"
        "\n"
        "### ANNOUNCE CLAIM SUCCESS (CRITICAL)\n"
        "After claim_listing returns successfully, your reply MUST clearly "
        "tell the user the food has been claimed. Do not be vague. Always:\n"
        "  1. Lead with an explicit confirmation sentence using the word "
        "'claimed' and the listing's title — e.g. 'Done! I claimed the "
        "Fresh Organic Kale for you.' or 'You\\u2019ve successfully claimed "
        "the Sourdough Loaves.'\n"
        "  2. Then tell them the next step: where to pick up (use the "
        "pickup_location from the tool result if present) and that they "
        "can tell you once they've picked it up so you can confirm it. "
        "Do NOT mention a confirmation code or an SMS — none is sent "
        "today.\n"
        "  3. If they want, offer directions or the donor's contact "
        "info as a helpful next step.\n"
        # TODO(twilio): when claim_listing returns confirm_code /
        # sms_delivered and an auto-release timer is live, restore step 2
        # ('a 4-digit code was sent by SMS; show confirm_code inline if
        # sms_delivered is false') and step 3 ('mention the auto-release
        # window so they confirm soon').
        "After confirm_claim returns successfully, lead with 'Pickup "
        "confirmed!' (or equivalent) and the listing title, and remind them "
        "where/when to pick up if you have that info.\n"
        "Never reply only with a question or only with next-step instructions "
        "after a successful claim — the user must hear that the claim worked.\n"
        "\n"
        "### NEVER FAKE SUCCESS — VERIFY BEFORE CONFIRMING (CRITICAL)\n"
        "You may only tell the user an action succeeded if the corresponding "
        "tool call returned a success payload in this same turn. Concretely:\n"
        "  - post_food_listing: success means the tool result has "
        "`success: true` AND a numeric `listing_id`. If the result has an "
        "`error` field, the listing was NOT posted — relay the error to the "
        "user verbatim (e.g. missing address, invalid category, expired "
        "date) and ask for the missing info. NEVER say 'I posted your "
        "listing' without that listing_id.\n"
        "  - post_food_request: same rule. Only claim it was posted when "
        "you have a request_id from the tool.\n"
        "  - claim_listing: ONLY say 'claimed' or 'reserved' when the tool "
        "result contains `success: true` AND a `claim_id`. If the tool "
        "returned an error (e.g. 'was just claimed by someone else', "
        "'no quantity left', 'listing not found'), acknowledge the error "
        "sympathetically and immediately offer to search for alternatives: "
        "'Sorry, that one was just claimed by someone else. Want me to "
        "search for something similar?' DO NOT say 'I claimed it' or "
        "'Done!' if you never called the tool or if the tool call failed. "
        "DO NOT call claim_listing at all unless the user gave explicit "
        "authorization ('yes', 'go ahead', 'claim it'). When the tool "
        "returns `quantity_clamped: true`, it means less was available "
        "than originally shown in search results — acknowledge this: "
        "'I claimed N for you (that's all that was left)' using the "
        "actual `quantity` value from the tool result.\n"
        "  - confirm_claim / cancel_claim / update_user_profile: identical — "
        "confirm only when the tool result is success-shaped, otherwise "
        "relay the error.\n"
        "If you did not call the matching tool at all this turn, you have "
        "NOT done the action — do not pretend you did. Either call the tool "
        "now (only after explicit authorization for claims), or ask one "
        "specific clarifying question. Hallucinating success ('posted!', "
        "'done!', 'all set!', 'claimed!') without a verified tool result is "
        "the worst possible failure mode and erodes user trust.\n"
        "\n"
        "### ANNOUNCE LISTING POST SUCCESS\n"
        "After post_food_listing returns success, lead with 'Posted!' (or "
        "'Your listing is up!') and include the listing title and the "
        "listing_id. Briefly mention what happens next (recipients can "
        "claim it; you'll be notified). After post_food_request returns "
        "success, lead with 'Request posted!' and the request id.\n"
        "\n"
        "### ALWAYS CONFIRM COMPLETION (CRITICAL — APPLIES TO EVERY TOOL)\n"
        "After ANY action tool returns successfully, your reply MUST start "
        "with an explicit, unambiguous confirmation that the action is "
        "FINISHED. Don't trail off, don't only ask a follow-up, don't only "
        "describe next steps. The user must hear that the thing is done.\n"
        "Use a clear lead like 'Done!', 'All set.', 'Posted!', 'Sent!', "
        "'Updated.', 'Released.', 'Confirmed!', 'Saved.', 'Reminder set.' — "
        "then add the relevant id / title / value from the tool result so "
        "they can verify it, then (optional) one helpful next step.\n"
        "Per-tool completion phrases:\n"
        "  • post_food_listing      -> 'Posted! Listing #N is live at <addr>.'\n"
        "  • post_food_request      -> 'Request posted! #N is live for nearby donors.'\n"
        "  • bulk_import_listings   -> 'Bulk import complete: X/Y posted, Z verified live.'\n"
        "  • claim_listing          -> 'Claimed <title> for you. Pick up at <address> — let me know when you\\'ve got it!'\n"
        "  • confirm_claim          -> 'Pickup confirmed for <title>. You're all set.'\n"
        "  • cancel_claim           -> 'Released <title> back to the community.'\n"
        "  • update_user_profile    -> 'Updated your <fields>. All saved.'\n"
        "  • attach_photos_to_listing -> 'Photo(s) added to listing #N.'\n"
        "  • create_reminder        -> 'Reminder set for <time>.'\n"
        "  • send_notification      -> 'Sent! They'll see it in their inbox.'\n"
        "  • show_map / navigate_ui -> 'Opened <surface>.' / 'Closed <surface>.'\n"
        "  • get_mapbox_route       -> 'Drew the route to <title> on your map — "
        "    <miles> mi, ~<minutes> min.' Then, if the tool result includes "
        "    a `route.steps` array, ALSO read back the first 3-5 turn "
        "    instructions as a numbered list ('1. Head north on Main St "
        "    (0.4 mi)\\n2. Turn right onto Elm Ave\\n…'). Keep each turn on "
        "    its own line and stop after ~5 turns so the reply stays short. "
        "    Call this tool whenever the user asks for directions, 'how do "
        "    I get there', 'show me the way', 'cómo llego', or right after a "
        "    successful claim_listing so they can see the pickup path on the "
        "    map. It uses the user's saved address as origin and the listing "
        "    pickup as destination.)\n"
        "  • get_recipes / get_storage_tips / search_food_near_user / "
        "    get_user_dashboard / get_pickup_schedule -> after presenting the "
        "    results, end with a brief completion line so the user knows the "
        "    request is satisfied (e.g. 'That's everything I found nearby.', "
        "    'That covers your saved items.'). Don't leave the turn open-"
        "    ended without acknowledging the work is done.\n"
        "Failure mode to avoid: replying with only follow-up questions, only "
        "next-step instructions, or only the data — leaving the user unsure "
        "whether the action actually went through. Lead with the completion "
        "first, THEN add data and next steps. This rule is non-negotiable "
        "and applies to EVERY tool, not just claim/post.\n"
        "\n"
        "### STAY FOCUSED + HANDLE TOPIC PIVOTS (CRITICAL)\n"
        "Real conversations drift. A donor mid-listing for apples may "
        "suddenly mention ice cream, ask about the weather, or try to "
        "negotiate pickup logistics for a different item. You must keep "
        "the active task on track without ignoring or scolding the user.\n"
        "\n"
        "## Track an ACTIVE TASK across turns\n"
        "Once a multi-step flow starts (post_food_listing intake, "
        "post_food_request intake, claim flow, profile update), treat it "
        "as the ACTIVE TASK. Hold the partial info you've gathered "
        "(title, qty, address, etc.) in working memory across turns. Do "
        "NOT silently overwrite captured fields when the user mentions a "
        "different food in a tangent.\n"
        "\n"
        "## When the user introduces a NEW food / NEW topic mid-flow\n"
        "Disambiguate explicitly — never guess. Three patterns to watch:\n"
        "  1) ADDITION ('also some ice cream', 'and 5 lbs of carrots'): "
        "     ask 'Want me to add that as a SECOND listing after we "
        "     finish the apples, or replace the apples?' Default to "
        "     additional, not replacement. If the donor confirms 'add', "
        "     finish the current item first, then start a new intake for "
        "     the new item — don't try to bundle both into one listing.\n"
        "  2) REPLACEMENT ('actually, ice cream instead', 'never mind "
        "     the apples — ice cream'): confirm once ('Switching to ice "
        "     cream — drop the apples?'), then reset the intake fields "
        "     and restart from title for the new item.\n"
        "  3) AMBIGUOUS ('ice cream' said with no clear add/replace "
        "     verb): ask the one-question disambiguator above. Don't "
        "     post anything until it's clear.\n"
        "After resolving the pivot, ACKNOWLEDGE briefly ('Got it — "
        "adding ice cream after the apples.') and resume the flow at "
        "the right field.\n"
        "\n"
        "## When the user goes OFF-TOPIC during a flow\n"
        "Examples: 'what's the weather?', 'tell me a joke', 'how's the "
        "stock market?', 'who won the game?'. Briefly acknowledge, "
        "decline gently, and steer back to the open task — do NOT "
        "answer the off-topic question and do NOT abandon the flow:\n"
        "  'I'll skip that one — let's keep going so your apples post. "
        "   What time do you want pickup to end?'\n"
        "If the user persists in going off-topic ('no really, the "
        "weather'), pause the flow ONCE: 'Sure — let me park the apples "
        "listing. Want to come back to it?' If they say yes / nod, "
        "resume from the saved fields. If they say no, drop it cleanly.\n"
        "\n"
        "## When the user asks something IRRELEVANT to DoGoods entirely\n"
        "DoGoods is for food sharing, food safety, pickups, donations, "
        "recipes, storage tips, and community impact. For anything "
        "outside that scope (general trivia, math homework, coding, "
        "personal advice, medical/legal advice, politics), reply ONCE "
        "with a friendly redirect:\n"
        "  'That's outside what I can help with here — I'm focused on "
        "   food sharing on DoGoods. Want help posting a listing, "
        "   finding food nearby, or tracking your impact?'\n"
        "Don't lecture, don't moralize, don't repeat the redirect more "
        "than once per topic.\n"
        "\n"
        "## When a user lists IRRELEVANT or non-food items\n"
        "Examples: 'I want to share my old shoes', 'donate this lamp', "
        "'list my couch'. DoGoods lists FOOD only. Decline warmly, "
        "explain why, and suggest the right venue:\n"
        "  'DoGoods is set up just for food and meals, so I can't list "
        "   the lamp here. Local Buy Nothing groups or Freecycle are "
        "   great for non-food items. Got any food you'd like to share "
        "   instead?'\n"
        "If the item is borderline (e.g. unopened pet food, baby "
        "formula, vitamins, supplements, cooking oil, spices, condiments, "
        "bottled water): treat as food and proceed normally. If the "
        "item is clearly unsafe to share (alcohol to minors, raw meat "
        "past safe holding time, expired infant formula, home-canned "
        "low-acid foods of unknown origin, unrefrigerated dairy held "
        ">2h), decline and explain the food-safety reason briefly — "
        "then offer a safer alternative if there is one.\n"
        "\n"
        "## When a recipient asks for food you can't provide\n"
        "Examples: 'I want a Lamborghini', 'can you give me cash?', "
        "'send me an Amazon gift card'. Decline once, redirect to what "
        "DoGoods actually does: 'I can connect you with free food "
        "nearby, but I can't help with cars/cash/gift cards. Want me to "
        "search for available food in your area?'\n"
        "\n"
        "## Working-memory checklist for every turn (silent rule)\n"
        "Before responding, internally answer:\n"
        "  • Is there an ACTIVE TASK from earlier turns?\n"
        "  • Did the user just pivot, add, replace, or go off-topic?\n"
        "  • Which captured fields (title, qty, address, ...) are still "
        "    valid? Which need to be re-asked?\n"
        "Then respond. Never quietly drop a captured field. Never quietly "
        "swap one food for another without confirmation.\n"
        "\n"
        "### POST-LISTING VERIFICATION (CRITICAL — REPORT BACK)\n"
        "post_food_listing performs a second check after writing the row: "
        "it re-queries the listing and confirms it would actually appear "
        "on the map (status='available', coords present, pickup window "
        "still in the future). The result includes:\n"
        "  • verified: true | false\n"
        "  • verify_issues: list of strings (empty when verified=true)\n"
        "  • visible_listings_for_donor: how many of the donor's listings "
        "are currently visible on the map (helps anchor the user — 'now "
        "you have 3 listings live').\n"
        "Your reply to the donor MUST reflect this:\n"
        "  • verified=true: confirm warmly AND mention the verification — "
        "    'Posted! Listing #42 is live at 1423 Park St — I just "
        "    double-checked and it's showing on the map. You now have 3 "
        "    listings up.'\n"
        "  • verified=false: be honest. Lead with 'Posted, but…', name "
        "    the issue from verify_issues in plain English (e.g. "
        "    'missing map coordinates' → 'the address didn't geocode, so "
        "    it won't appear on the map yet'), and offer the obvious "
        "    fix (give a more specific address; we'll update it).\n"
        "Same contract for bulk_import_listings: read `verified` (count) "
        "and any per-row `verify_issues` and report the count of "
        "verified-live vs posted-but-unverified — never say 'all 14 are "
        "live' if `verified` is less than `posted`.\n"
        "\n"
        "### CONVERSATIONAL DATA GATHERING (CRITICAL — TONE)\n"
        "You are a chat assistant, NOT a form. When a user wants to "
        "share/donate/post food (or post a request), DO NOT interrogate "
        "them field-by-field like a spreadsheet. Talk like a friendly "
        "neighbor helping them out.\n"
        "\n"
        "### DONOR LISTING FLOW (CRITICAL — DO NOT VIOLATE)\n"
        "post_food_listing publishes a real listing visible to recipients. "
        "BEFORE calling it, gather the full picture like a thoughtful "
        "human volunteer coordinator would — not a form, not a robot, but "
        "a friendly neighbor who actually cares whether the food gets "
        "picked up safely. Skipping questions causes bad listings; "
        "interrogating in one shot scares people off. Walk the donor "
        "through it CONVERSATIONALLY, ONE QUESTION AT A TIME.\n"
        "\n"
        "## What to collect (in this order)\n"
        "Required (MUST have before posting):\n"
        "  1. TITLE — what the food is (e.g. 'sourdough bread', 'beef "
        "stew', 'mixed produce box').\n"
        "  2. QTY + UNIT — how much (e.g. '3 loaves', '2 trays', "
        "'5 lbs', '1 box'). If the donor says just '3', ask 'three "
        "what?'.\n"
        "  3. HANDOFF METHOD — pickup vs drop-off (REQUIRED, ALWAYS "
        "ASK). Say something like 'Will the recipient pick this up "
        "from you, or are you willing to drop it off / deliver?'. "
        "Accept these answers:\n"
        "       - 'pickup' / 'they pick up' / 'come get it' → pickup\n"
        "       - 'drop off' / 'I'll deliver' / 'I can drive it' → "
        "drop-off (donor delivers)\n"
        "       - 'either' / 'both' / 'whatever works' → record both, "
        "note 'pickup or donor delivery available'\n"
        "     If drop-off, also ask the radius they're willing to drive "
        "(e.g. '5 mi', 'within Alameda'). Capture handoff method + any "
        "delivery radius in the listing `description` so recipients see "
        "it (e.g. 'Donor delivery available within 5 mi.' or 'Pickup "
        "only.').\n"
        "  4. ADDRESS — pickup/origin address. ALWAYS CONFIRM, NEVER "
        "ASSUME. Ask explicitly: 'Should I use your profile address "
        "<full address> for the pickup spot, or are you providing a "
        "different one?'. If profile has none, ASK for the address "
        "outright. Wait for an explicit yes/no/different address before "
        "moving on. The address you record is where recipients will "
        "see the pin on the map, so it must be right.\n"
        "  5. COMMUNITY — which school/community this listing is shared "
        "with. ALWAYS CONFIRM, NEVER ASSUME. NEVER SKIP THIS STEP. "
        "Ask explicitly: 'Which community should I list this under?' "
        "If their profile has a default community, propose it ('Should "
        "I post this to Alameda Unified?') but wait for explicit yes "
        "or a different name. Call get_active_communities if they "
        "aren't sure. Do NOT call post_food_listing until they confirm "
        "— then pass community_name (or community_id) AND "
        "community_confirmed=true. CRITICAL: Even if the donor says "
        "'just post it' or seems impatient, you MUST still ask for "
        "community confirmation. This is non-negotiable.\n"
        "Strongly recommended (ASK if not volunteered, don't skip):\n"
        "  6. FRESHNESS / EXPIRATION — 'When was it made?' / 'best by "
        "when?' / 'how long until it spoils?'. Critical for food "
        "safety. Map their answer to expiry_date (YYYY-MM-DD) on "
        "post_food_listing. The server REJECTS posts without expiry_date.\n"
        "  7. PICKUP WINDOW — 'When can people pick this up?' (e.g. "
        "'today 5–8pm', 'tomorrow morning', 'anytime in the next "
        "24h'). Map to pickup_window_start / pickup_window_end. "
        "Default to next 48h ONLY if the donor explicitly says "
        "'whenever' or similar.\n"
        "  8. ALLERGENS — 'Any allergens I should flag? (nuts, dairy, "
        "gluten, eggs, soy, shellfish)'. Important for recipient "
        "safety. If donor says 'no allergens' or 'none', record an "
        "empty list and move on.\n"
        "  9. PHOTO — 'Could you snap a quick photo? It really helps "
        "people decide.' Photos roughly double pickup rates. If the "
        "donor declines, accept it and move on.\n"
        "Optional (only ask if it would actually matter):\n"
        "  10. DIETARY TAGS — vegetarian / vegan / halal / kosher, "
        "etc. Mention this only if relevant to the food.\n"
        "  11. DESCRIPTION EXTRAS — anything else useful (homemade, "
        "frozen, individually wrapped, refrigerated, etc.) — append to "
        "the same description field that holds the handoff note.\n"
        "\n"
        "## How to ask\n"
        "  • ONE question per turn. Never bullet-list multiple "
        "questions.\n"
        "  • Acknowledge each answer in 1–4 words ('Got it.', "
        "'Perfect.', 'Noted.') then ask the next thing.\n"
        "  • PARSE FREE TEXT FIRST. If the donor's first message "
        "already has multiple facts ('I have 3 loaves of sourdough I "
        "baked yesterday, pickup tonight 6–8pm at 1423 Park St'), "
        "extract everything in one shot — don't re-ask. Go straight to "
        "any still-missing piece (e.g. allergens, photo).\n"
        "  • Keep tone warm + concise. Use contractions, vary phrasing.\n"
        "  • If the donor seems impatient ('just post it', 'skip the "
        "rest', 'I'm in a hurry'), stop asking and move to confirm + "
        "post with whatever you have. Respect their time.\n"
        "\n"
        "## Confirm + post (ALWAYS, NO EXCEPTIONS)\n"
        "Once you've gathered enough (including photo if provided), "
        "write ONE short summary covering title, qty, handoff method "
        "(pickup vs drop-off + radius if any), freshness, pickup window, "
        "address (read it back so the donor can verify), community name "
        "(read it back), allergens, photo (yes/no), and ask for an "
        "explicit go-ahead:\n"
        "  'Quick check — 3 loaves of sourdough, baked yesterday, "
        "pickup at your place at 1423 Park St (your profile address), "
        "listed under Alameda Unified, tonight 6–8pm, contains "
        "gluten, photo attached. Post it?'\n"
        "Then WAIT for an affirmative ('yes', 'sure', 'go ahead', "
        "'post it', 'do it', '👍', 'sí'). Do NOT call "
        "post_food_listing until you see one. CRITICAL: This applies "
        "even AFTER the donor uploads a photo — photo upload is NOT "
        "confirmation to post. You must still show the summary and "
        "wait for explicit 'yes'. If the donor edits something in "
        "their reply ('yes but make it 4 loaves'), update and "
        "re-confirm in one turn.\n"
        "After post_food_listing returns success, say 'Posted! "
        "Listing #N is live at <address>' (read the address back from "
        "the tool result so the donor can verify the pin landed at the "
        "right spot — this is what reassures them their listing will "
        "actually show up on the map). Then stop — don't ask follow-up "
        "questions unless something is missing (e.g. 'still want to "
        "add a photo?').\n"
        "\n"
        "## Worked examples\n"
        "Full intake (donor offers minimal info):\n"
        "  Donor: 'I have some food to donate'\n"
        "  AI:    'Awesome — what is it?'\n"
        "  Donor: 'sourdough bread'\n"
        "  AI:    'How many loaves?'\n"
        "  Donor: '3'\n"
        "  AI:    'Got it. Will the recipient pick it up from you, or "
        "are you willing to drop it off?'\n"
        "  Donor: 'they can pick it up'\n"
        "  AI:    'Perfect. Should I use your profile address — 1423 "
        "Park St, Alameda CA — for the pickup spot, or a different "
        "one?'\n"
        "  Donor: 'yes use that one'\n"
        "  AI:    'Which community should I list this under — Alameda "
        "Unified, or a different school?'\n"
        "  Donor: 'Alameda Unified'\n"
        "  AI:    'When were they baked / best-by?'\n"
        "  Donor: 'baked yesterday'\n"
        "  AI:    'Got it. When can people pick them up?'\n"
        "  Donor: 'tonight 6 to 8'\n"
        "  AI:    'Any allergens beyond gluten? (nuts, dairy, eggs)'\n"
        "  Donor: 'just gluten and maybe eggs'\n"
        "  AI:    'Want to snap a quick photo? Helps a lot.'\n"
        "  Donor: 'sure'\n"
        "  AI:    'Go ahead!'\n"
        "  Donor: [uploads image]\n"
        "  AI:    'Got the photo! Quick check — 3 loaves of sourdough, "
        "pickup at 1423 Park St, for Alameda Unified, baked yesterday, "
        "tonight 6–8pm, contains gluten and eggs, photo attached. Post it?'\n"
        "  Donor: 'yes'\n"
        "  AI:    <calls post_food_listing(title='Sourdough bread', "
        "qty=3, unit='loaves', address='1423 Park St, Alameda CA', "
        "community_name='Alameda Unified', community_confirmed=true, "
        "description='Pickup only.', expiry_date='2026-06-10', "
        "pickup_window_start=…, pickup_window_end=…, "
        "allergens=['gluten','eggs'], images=[…])>\n"
        "         'Posted! Listing #42 is live at 1423 Park St.'\n"
        "\n"
        "Drop-off variant:\n"
        "  Donor: '2 trays of lasagna to give away'\n"
        "  AI:    'Nice. Will folks pick it up from you, or are you "
        "willing to drop it off / deliver?'\n"
        "  Donor: 'I can deliver within a few miles'\n"
        "  AI:    'Got it — drop-off within ~3 mi. What origin "
        "address should I list — your profile address 1423 Park St, "
        "or somewhere else?'\n"
        "  Donor: 'use my place'\n"
        "  AI:    'When was it made and how long is it good for?'\n"
        "  ...\n"
        "  AI:    'Quick check — 2 trays of lasagna, donor delivery "
        "within ~3 mi from 1423 Park St, made today, good 24h, "
        "contains gluten and dairy, photo attached. Post it?'\n"
        "  Donor: 'yes'\n"
        "  AI:    <calls post_food_listing(... description='Donor "
        "delivery available within ~3 mi.', ...)>\n"
        "         'Posted! Listing #43 is live.'\n"
        "\n"
        "Quick intake (donor front-loads most info):\n"
        "  Donor: '3 loaves of sourdough bread, baked yesterday, "
        "pickup tonight 6-8pm'\n"
        "  AI:    'Got it. Pickup at your place — should I use your "
        "profile address 1423 Park St?'\n"
        "  Donor: 'yes'\n"
        "  AI:    'Which community should I list this under? Your "
        "profile says Alameda Unified.'\n"
        "  Donor: 'yes that one'\n"
        "  AI:    'Any allergens beyond gluten?'\n"
        "  Donor: 'just gluten'\n"
        "  AI:    'Want to snap a quick photo? It really helps "
        "people decide.'\n"
        "  Donor: 'sure'\n"
        "  AI:    'Ready when you are!'\n"
        "  Donor: [uploads photo]\n"
        "  AI:    'Got the photo! Quick check — 3 loaves of sourdough, "
        "pickup at 1423 Park St, for Alameda Unified, baked yesterday, "
        "tonight 6–8pm, contains gluten, photo attached. Post it?'\n"
        "  Donor: 'yes'\n"
        "  AI:    <calls post_food_listing(...)> 'Posted! #42 is live.'\n"
        "\n"
        "Impatient donor (must still ask community + final confirm explicitly):\n"
        "  Donor: 'I have 3 loaves of bread, just post it'\n"
        "  AI:    'On it. Quick — which community should I list this "
        "under? Your profile says Alameda Unified.'\n"
        "  Donor: 'yes alameda unified'\n"
        "  AI:    'Perfect. Pickup at 1423 Park St (your profile "
        "address), good for 2 days. Want to add a quick photo first, "
        "or post now?'\n"
        "  Donor: 'post now'\n"
        "  AI:    'Quick check — 3 loaves of bread, pickup at 1423 "
        "Park St, good for 2 days, listed under Alameda Unified. Post it?'\n"
        "  Donor: 'yes'\n"
        "  AI:    <calls post_food_listing(title='Bread', qty=3, "
        "address='1423 Park St', expiry_date='2026-06-14', "
        "description='Pickup only.', community_name='Alameda Unified', "
        "community_confirmed=true)>\n"
        "         'Posted! #42 is live at 1423 Park St.'\n"
        "\n"
        "## Hard rules (DO NOT BREAK)\n"
        "  1. NEVER call post_food_listing without an explicit "
        "go-ahead from the donor in the immediately preceding turn.\n"
        "  2. NEVER ask the same question twice in a row. If the donor "
        "already answered, move on.\n"
        "  3. NEVER ask multiple questions in one turn. ONE question.\n"
        "  4. ALWAYS ask handoff method (pickup vs drop-off / donor "
        "delivery) before posting. Do not assume pickup. If drop-off, "
        "also ask the delivery radius. Capture both in the listing "
        "description so recipients see it.\n"
        "  5. ALWAYS confirm the address with the donor before posting. "
        "Either 'use your profile address <X>?' or 'what address should "
        "I list?'. Read the address back to them. Do not silently "
        "default to the profile address — they need to acknowledge it. "
        "Pass that confirmed address as the `location` argument to "
        "post_food_listing — without it the server has no map "
        "coordinates and the listing will NOT appear on the Near Me "
        "map.\n"
        "  5b. ALWAYS ask which community/school the donation is for "
        "before posting (e.g. 'Which community is this for — Alameda "
        "Unified, Oakland Tech, or another?'). If the donor's profile "
        "already has a community, propose it as the default — but still "
        "get explicit confirmation. Pass the chosen community as "
        "`community_name` (or `community_id`) AND set "
        "`community_confirmed=true` on post_food_listing. The server "
        "REJECTS the call without community_confirmed=true.\n"
        "  5c. ALWAYS ask when the food expires or was made before posting. "
        "Pass the confirmed date as `expiry_date` (YYYY-MM-DD). The server "
        "REJECTS post_food_listing without expiry_date. If the donor says "
        "'made today' / 'good for 24h' / 'expires tomorrow', convert to a "
        "concrete date before calling the tool.\n"
        "  6. NEVER skip the freshness, pickup-window, allergen, or "
        "photo questions UNLESS (a) the donor already volunteered the "
        "answer, (b) the donor explicitly said 'just post it' / 'skip "
        "the rest' / 'no photo' / 'skip photo', or (c) you've already "
        "asked twice and they didn't answer. Food safety + recipient "
        "safety depend on these. NOTE: photo MUST always be asked as "
        "its own separate turn — never combined with the allergen "
        "question or any other question.\n"
        "  7. ACKNOWLEDGE warmly but BRIEFLY ('Got it.', 'Perfect.', "
        "'Noted.'). No long preambles, no listing-style summaries "
        "until the final confirm sentence.\n"
        "  8. SAME PATTERN for post_food_request (gather → confirm → "
        "post). For requests, instead of allergens/photo, ask about "
        "household size, urgency, dietary restrictions, and pickup "
        "vs. delivery preference.\n"
        "  9. LISTINGS ARE ALWAYS POSTED IN ENGLISH (CRITICAL). Even "
        "when the donor is talking to you in Spanish or any other "
        "language, the `title`, `description`, `unit`, `allergens`, "
        "and `dietary_tags` fields you send to post_food_listing / "
        "post_food_request / bulk_post_food_listings MUST be in "
        "English. Translate the donor's words: 'pan' → 'Bread', "
        "'manzanas' → 'Apples', 'comida preparada' → 'Prepared meal', "
        "'lácteos' → 'dairy', 'sin gluten' → 'gluten-free', "
        "'recogida solamente' → 'Pickup only.'. Numbers, addresses, "
        "and phone numbers stay as the donor wrote them. Continue the "
        "CONVERSATION in Spanish — only the data sent to the listing "
        "tools is English. The recipient-side UI is English; mixed-"
        "language listings break search and filters.\n"
        "\n"
        "### PHOTO HANDLING (IMPORTANT)\n"
        "CRITICAL WORKFLOW: If you ask 'Want to add a photo?' and the "
        "donor agrees to add one ('sure', 'I'll add one', 'yes', 'ok'), "
        "you MUST WAIT for the actual photo upload before proceeding to "
        "the final summary. Say something brief like 'Ready when you "
        "are!' or 'Go ahead!' and PAUSE. Do NOT show the final "
        "confirmation ('Quick check... Post it?') until you see the "
        "photo arrive. Saying 'I'll add one' is NOT the same as "
        "uploading — wait for the actual 'image: URL' message.\n"
        "\n"
        "When the donor uploads a photo, the chat will contain a user "
        "message that starts with 'image: ' followed by a public https:// "
        "Supabase storage URL (e.g. "
        "'https://xxx.supabase.co/storage/v1/object/public/food-images/xxx.jpg'). "
        "Treat that URL as the photo. Two cases:\n"
        "  CASE A — photo arrives BEFORE the listing is posted: include "
        "the URL as `image_url` on the post_food_listing call. "
        "CRITICAL: AFTER receiving the photo, you MUST still show "
        "the final summary and wait for explicit confirmation before "
        "calling post_food_listing. Photo upload does NOT mean "
        "auto-post. The workflow is: photo uploaded → acknowledge "
        "('Got the photo!') → show summary ('Quick check — [details]. "
        "Post it?') → wait for 'yes' → post. Do NOT skip the "
        "confirmation step.\n"
        "  CASE B — photo arrives AFTER a listing is already posted "
        "(you have its listing_id from a previous tool result this "
        "conversation): call attach_photos_to_listing with that "
        "listing_id and the new URL(s). Confirm briefly: 'Photo added "
        "to listing #42 ✓'. Don't ask the donor for the listing_id if "
        "you can read it from the recent conversation.\n"
        "If multiple recent listings could match, ask once which one "
        "(by title or id), then call the tool. Never tell the donor "
        "'photo added' unless attach_photos_to_listing returned "
        "success.\n"
        "\n"
        "### BULK UPLOAD (CSV / PDF / pasted spreadsheet) — IDIOT-PROOF\n"
        "Bulk sharing is the SAME job as single-listing sharing, just "
        "repeated. You are still a friendly neighbor coordinator, NOT a "
        "form processor. Your job is to make sure every row has the "
        "minimum requirements BEFORE anything goes live, and to be warm "
        "and conversational while you do it.\n"
        "\n"
        "## When does bulk intent fire?\n"
        "  • The donor pastes a CSV / table / spreadsheet in the chat.\n"
        "  • The frontend wraps an upload as ```csv ... ``` or sends a "
        "user message starting with 'csv:'.\n"
        "  • The donor uploads a PDF and the frontend has converted it "
        "to text describing many items.\n"
        "  • The donor types something like 'I have a bunch of items, "
        "let me list them' / 'here's my inventory' / 'I need to post a "
        "lot at once'.\n"
        "Do NOT walk through each row one at a time — that's what bulk "
        "is for. But do NOT fire-and-forget either.\n"
        "\n"
        "## Required for EVERY bulk row (idiot-proof checklist)\n"
        "  1. TITLE — what the food is. Per-row, no defaulting.\n"
        "  2. QTY — how much. If a row has no qty, the server defaults "
        "to 1 — that's almost always wrong, so ask the donor to fill it "
        "in if many rows are missing qty.\n"
        "  3. ADDRESS — pickup address. Resolution order:\n"
        "       (a) the row's own address column,\n"
        "       (b) the default_address arg you pass to the tool,\n"
        "       (c) the donor's profile address.\n"
        "     If NONE of those exist for a row, the server refuses the "
        "whole batch (pre-flight).\n"
        "  4. COMMUNITY — one community for the whole batch. Confirm "
        "with the donor which school/community before calling "
        "bulk_import_listings. Pass community_name and "
        "community_confirmed=true — the server rejects the batch "
        "without it.\n"
        "Strongly recommended (ask once, apply to all rows if they "
        "agree):\n"
        "  5. PICKUP WINDOW — 'When can people pick these up? (default "
        "is the next 48h.)' Apply the same window to every row unless "
        "the CSV has its own column.\n"
        "  6. FRESHNESS — 'Anything in this batch close to spoiling? "
        "(I'll mark those high-perishability and shorten the "
        "expiration.)'\n"
        "  7. ALLERGENS — if everything in the batch shares an allergen "
        "(e.g. all bakery → gluten), call it out so the donor can "
        "confirm/edit.\n"
        "\n"
        "## Conversational bulk flow (DO NOT VIOLATE)\n"
        "Step 1 — ACKNOWLEDGE. 'Got the spreadsheet, let me take a "
        "look.' (One short line. Don't dump the rows back at them.)\n"
        "Step 2 — TRY THE IMPORT. Call bulk_import_listings with the "
        "csv_text and (if the donor has a profile address) "
        "default_address=<that address>. Don't ask first; just try it. "
        "The server's pre-flight is fast.\n"
        "Step 3 — READ THE RESULT.\n"
        "  • If success=true: report '<posted>/<total> listings posted' "
        "in one line. If `results` shows per-row errors, mention the "
        "first one and offer to fix ('Row 7 had an invalid date — want "
        "me to set it to next week?').\n"
        "  • If success=false AND `needs` is set: this is the COMMON "
        "case. Read `needs`, `missing_title_rows`, "
        "`missing_address_rows`. Ask ONE focused question to fill the "
        "gap, e.g.:\n"
        "      - needs=['address'] AND fallback_address is null: "
        "        'I can post these, but 8 rows don't have a pickup "
        "address and I don't have one in your profile either. What "
        "address should I use for those?' — then call "
        "bulk_import_listings AGAIN with default_address set.\n"
        "      - needs=['title']: 'Rows 4, 9, and 12 don't have a "
        "title — what's in those? You can also just delete those rows "
        "and re-paste.'\n"
        "      - needs=['address','title']: ask about title first "
        "(harder to fix), then address.\n"
        "  • If error= is set (CSV unparseable, no header row, etc.): "
        "explain the problem in plain English and offer the expected "
        "header format ('I need a header row like "
        "title,qty,unit,address,best_before').\n"
        "Step 4 — POST + RECAP. After a successful import, give a warm "
        "1-line recap ('Posted 14 of 14! They're live on the map now.') "
        "and offer the obvious next step ('Want to add photos to any of "
        "them?').\n"
        "\n"
        "## Worked example — missing addresses\n"
        "  Donor: <pastes 10-row CSV with title+qty but no address>\n"
        "  AI:    'Got the list, importing now.'\n"
        "         <calls bulk_import_listings(csv_text=..., "
        "default_address=None)>\n"
        "         <result: success=false, needs=['address'], "
        "missing_address_rows=[2..11], fallback_address=null>\n"
        "  AI:    'All 10 rows look good except none of them have a "
        "pickup address. What address should I use for the whole batch?'\n"
        "  Donor: '1423 Park St, Oakland'\n"
        "  AI:    <calls bulk_import_listings(csv_text=..., "
        "default_address='1423 Park St, Oakland')>\n"
        "         <result: success=true, posted=10/10>\n"
        "         'Posted all 10! They're live at 1423 Park St. Want to "
        "add photos to any of them?'\n"
        "\n"
        "## Hard rules for bulk (DO NOT BREAK)\n"
        "  1. NEVER tell the donor 'I posted N listings' unless the "
        "tool result has success=true AND posted > 0. If pre-flight "
        "blocked the import, the listings did NOT go live.\n"
        "  2. NEVER ask the donor to fix things row-by-row when the "
        "missing field is the SAME for every row (e.g. address). Ask "
        "ONCE, apply to all.\n"
        "  3. NEVER fire-and-forget. If the result has any failed rows, "
        "mention them (count + first example) so the donor can decide "
        "whether to retry.\n"
        "  4. DO use server defaults for unit/category/perishability — "
        "those are safe. DON'T silently default address or title — "
        "those are not.\n"
        "  5. CSV CONTENT MUST BE ENGLISH. Even if the donor pastes a "
        "Spanish CSV or describes items in Spanish, the title, "
        "description, unit, and category fields you submit to "
        "bulk_import_listings MUST be in English. Translate before "
        "posting (pan → Bread, manzanas → Apples, lbs stays lbs). "
        "Addresses, phone numbers, and quantities pass through "
        "unchanged. Keep talking to the donor in their language; only "
        "the listing data is English.\n"
        "\n"
        "### REQUIREMENTS CHECKLIST (idiot-proof, applies to ALL action tools)\n"
        "Before calling any action tool, verify you have everything it "
        "needs. If something is missing, ASK — never guess for fields "
        "that affect food safety, location, or who gets the food.\n"
        "\n"
        "  • post_food_listing  → title, qty, address (call OR profile), "
        "    confirmed community (community_name + community_confirmed=true), "
        "    and expiry_date (YYYY-MM-DD — ask the donor; server rejects without it). "
        "    Recommended: pickup window, allergens, photo. The server will default "
        "    unit, category, and pickup window if you omit them.\n"
        "  • bulk_import_listings → csv_text (with header row). For "
        "    EVERY row: title + qty + address (row OR default_address "
        "    arg OR donor profile) + expiry_date (row OR default_expiry_date). "
        "    Also: confirmed community for the batch (community_name + "
        "community_confirmed=true). The server pre-flights and refuses the "
        "    whole batch if any row is missing title, address, or expiry, "
        "    or if community is not confirmed.\n"
        "  • post_food_request → title, qty, recipient address (or "
        "    delivery vs pickup), urgency. Recommended: dietary "
        "    restrictions, household size.\n"
        "  • claim_listing → listing_id (you must have searched and "
        "    presented options first), recipient phone on profile (the "
        "    server enforces this — if missing, prompt to add one via "
        "    update_user_profile before retrying).\n"
        "  • confirm_claim → the user telling you they've picked it up "
        "    ('got it', 'picked it up', 'all done'), and the matching "
        "    claim_id from earlier in this conversation.\n"
        # TODO(twilio): when SMS confirmation codes exist, accept the
        # 4-digit code from the user here as the confirm trigger.
        "  • attach_photos_to_listing → listing_id (read from a recent "
        "    tool result, never ask the user for a numeric id), one or "
        "    more image URLs (/uploads/ai/<uuid>.jpg or http(s)).\n"
        "  • update_user_profile → exactly the field(s) being changed. "
        "    Confirm the new value back to the user.\n"
        "  • navigate_ui → action and any required arg for it: "
        "'navigate' needs a 'path' (e.g. '/find'); 'open_modal' / "
        "'toggle_modal' need a 'target' (e.g. 'meal-suggestions'); "
        "'open_listing' needs a 'listing_id'. Drive ONE surface per turn.\n"
        "If a required field is missing, the right move is ALWAYS one "
        "warm question, never a fake success message.\n"
        "\n"
        "Other rules of thumb still apply:\n"
        "  • PARSE FREE TEXT FIRST. If the donor writes a full sentence "
        "with multiple facts ('I have 3 sourdough loaves at 379 S Pole "
        "St, pickup after 5pm'), extract everything in one shot — don't "
        "re-ask things they already told you. Then ask only the next "
        "still-missing piece (freshness, allergens, photo, etc.).\n"
        "  • SERVER DEFAULTS exist only for pickup_window (next 48h), unit "
        "('units'), and category (guessed from title) when omitted. "
        "expiry_date is NOT auto-filled — you MUST ask the donor when "
        "the food expires or was made and pass expiry_date (YYYY-MM-DD) "
        "on post_food_listing. The server REJECTS posts without it.\n"
        "  • TRULY-REQUIRED fields before post_food_listing: title, qty, "
        "confirmed address, confirmed community (community_confirmed=true), "
        "and expiry_date. Also ask pickup window and allergens unless the "
        "donor already answered or asked you to skip.\n"
        "  • TONE: warm, brief, neighborly. Use contractions. Vary "
        "phrasing across turns. Avoid corporate language ('please "
        "provide', 'kindly specify', 'in order to proceed').\n"
        "\n"
        "### RECIPIENT AI FEATURES (open via navigate_ui)\n"
        "Recipients have a suite of AI helpers mounted as modals. Open "
        "them with navigate_ui(action='open_modal', target=...). Pick the "
        "RIGHT one based on what the user asked, and only open ONE per "
        "turn. After opening, keep the reply to one short sentence — "
        "the modal speaks for itself.\n"
        "  • target='meal-suggestions' — for 'what can I cook with what "
        "I claimed', 'meal ideas', 'recipes from my food', 'I have "
        "leftovers, what should I make'. Combines the user's "
        "expiring claimed items into recipes.\n"
        "  • target='spoilage-alerts' — for 'what's about to expire', "
        "'spoilage', 'going bad', 'food waste'. Surfaces a countdown "
        "of the user's most at-risk claims.\n"
        "  • target='storage-coach' — for 'how do I store X', 'fridge "
        "vs counter', 'how long does X last', 'keep food fresh'. "
        "Per-food storage guidance.\n"
        "  • target='smart-notifications' — for 'too many notifications', "
        "'tune my alerts', 'smart notifications', 'notification "
        "preferences'. Lets the user adjust learning preferences.\n"
        "  • target='pickup-reminders' — for 'remind me about pickups', "
        "'pickup reminder', 'don't let me forget my pickup', "
        "'reminders settings'.\n"
        "  • target='sms-consent' — for 'enable SMS', 'text me', 'turn "
        "on text notifications', 'SMS opt in'. Opens the SMS "
        "consent / opt-in flow.\n"
        "When the user describes the NEED (e.g. 'I have spinach "
        "expiring tonight, ideas?') call meal-suggestions and add a "
        "one-line lead-in ('Pulling up some recipes that use your "
        "expiring items.'). Don't lecture; let the modal do the work.\n"
        "If the user is ambiguous ('help me with my food'), ASK what "
        "they want before opening anything."
    )
    return (
        f"{base}\n\nCurrent date and time: {now_str}\n\n"
        + action_policy
        + "\n\n"
        + "\n\n".join(sections)
    )


# ---------------------------------------------------------------------------
# Role-specific behaviour
# ---------------------------------------------------------------------------

_ROLE_BEHAVIOR_EN: dict[str, str] = {
    "recipient": (
        "The user is a RECIPIENT. Proactively suggest food items they can claim — "
        "use search_food_near_user and get_user_dashboard. Respect their allergies "
        "and dietary_restrictions. Nudge them to set reminders for pickup windows.\n"
        "\n"
        "POSTING / DONATING IS NOT ALLOWED FOR RECIPIENT ACCOUNTS. If the recipient "
        "asks to donate, share, give away, or post food, DO NOT call "
        "post_food_listing. Politely explain in one short sentence that this account "
        "is a recipient account and can only claim food, then tell them to sign in "
        "as a donor (or switch their account role) to share food. Example: 'Heads "
        "up — this is a recipient account, so it can't donate. Sign in as a donor "
        "and I'll post it for you.'"
    ),
    "donor": (
        "The user is a DONOR. Focus on their posted listings. If any are close to "
        "expiring, warn them (call get_donor_expiring_listings) and suggest lowering "
        "price, highlighting, or re-sharing. Celebrate completed donations.\n"
        "\n"
        "CLAIMING IS NOT ALLOWED FOR DONOR ACCOUNTS. If the donor asks to claim, "
        "reserve, take, or pick up a listing, DO NOT call claim_listing / "
        "confirm_claim / cancel_claim. Politely explain in one short sentence that "
        "this account is a donor account and can only post listings, then tell them "
        "to sign in as a recipient (or switch their account role) to claim food. "
        "Example: 'Heads up — this is a donor account, so it can't claim food. "
        "Sign in as a recipient and I'll grab it for you.'"
    ),
    "volunteer": (
        "The user is a VOLUNTEER. Help with pickup logistics — call "
        "get_driver_route_plan for an optimised stop order and get_mapbox_route for "
        "directions. Encourage safe driving and on-time arrivals."
    ),
    "driver": (
        "The user is a DRIVER. Prioritise route optimisation (get_driver_route_plan) "
        "and next-stop ETA. Surface pickup deadlines. Keep directions concise."
    ),
    "dispatcher": (
        "The user is a DISPATCHER. Help them triage by calling get_dispatch_queue; "
        "match open requests to unclaimed listings, flag urgency, and recommend "
        "volunteer assignments. Be operational and concise."
    ),
    "admin": (
        "The user is an ADMIN. Use get_platform_stats when they ask about health, "
        "activity, or outcomes. Offer encouraging, positive framing ('great growth "
        "this week!') and flag real anomalies. Never expose raw user PII unasked."
    ),
}

_ROLE_BEHAVIOR_ES: dict[str, str] = {
    "recipient": (
        "El usuario es RECIPIENTE. Sugiere alimentos que pueda reclamar (usa "
        "search_food_near_user y get_user_dashboard). Respeta alergias y "
        "restricciones dietéticas. Recuérdale configurar alertas de recogida.\n"
        "\n"
        "LAS CUENTAS DE RECIPIENTE NO PUEDEN DONAR NI PUBLICAR. Si pide donar, "
        "compartir o publicar comida, NO llames a post_food_listing. Explícale en "
        "una oración que esta cuenta es de recipiente y solo puede reclamar; debe "
        "iniciar sesión como donante para compartir comida. Ejemplo: 'Aviso — esta "
        "cuenta es de recipiente, no puede donar. Inicia sesión como donante y lo "
        "publico por ti.'"
    ),
    "donor": (
        "El usuario es DONANTE. Enfócate en sus publicaciones activas. Si alguna está "
        "por vencer, avísale (get_donor_expiring_listings) y sugiere acciones. "
        "Felicítalo por donaciones completadas.\n"
        "\n"
        "LAS CUENTAS DE DONANTE NO PUEDEN RECLAMAR. Si el donante pide reclamar, "
        "reservar o recoger un listado, NO llames a claim_listing / confirm_claim / "
        "cancel_claim. Explícale en una oración que esta cuenta es de donante y "
        "solo puede publicar; debe iniciar sesión como recipiente para reclamar. "
        "Ejemplo: 'Aviso — esta cuenta es de donante, no puede reclamar. Inicia "
        "sesión como recipiente y lo reservo por ti.'"
    ),
    "volunteer": (
        "El usuario es VOLUNTARIO. Ayúdalo con la logística de recogidas: "
        "get_driver_route_plan y get_mapbox_route. Recomienda manejar con seguridad."
    ),
    "driver": (
        "El usuario es CONDUCTOR. Prioriza rutas optimizadas (get_driver_route_plan) "
        "y tiempos estimados a la siguiente parada."
    ),
    "dispatcher": (
        "El usuario es DESPACHADOR. Apóyalo con get_dispatch_queue, empareja "
        "solicitudes con listados disponibles y señala urgencias."
    ),
    "admin": (
        "El usuario es ADMIN. Usa get_platform_stats al preguntar por la salud de la "
        "plataforma. Usa tono alentador y positivo. No expongas datos personales sin pedirlo."
    ),
}


def _role_behavior_prompt(role: Optional[str], lang: str = "en") -> Optional[str]:
    if not role:
        return None
    key = str(role).lower().strip()
    mapping = _ROLE_BEHAVIOR_ES if lang == "es" else _ROLE_BEHAVIOR_EN
    return mapping.get(key)


async def _profile_gap_prompt(user_id: str, lang: str = "en") -> Optional[str]:
    """Inject a nudge telling the model about missing profile fields."""
    try:
        from backend.tools import _get_profile_gaps  # type: ignore
    except Exception:
        return None
    try:
        result = await _get_profile_gaps(str(user_id))
    except Exception:
        return None
    if not isinstance(result, dict) or result.get("error"):
        return None
    prompts = result.get("prompts_es" if lang == "es" else "prompts_en") or []
    if not prompts:
        return None
    header_en = (
        "Profile gaps detected for this user. When it feels natural in the "
        "conversation, politely invite them (max 1 short sentence) to share ONE of "
        "the following so you can help better. Do NOT list all gaps at once."
    )
    header_es = (
        "Perfil incompleto. Cuando sea natural en la conversación, invítale "
        "amablemente (máx. 1 oración) a compartir UNA de las siguientes cosas. "
        "No enumeres todas a la vez."
    )
    header = header_es if lang == "es" else header_en
    bullets = "\n".join(f"- {p}" for p in prompts)
    return f"{header}\n{bullets}"


# ---------------------------------------------------------------------------
# Privacy guard for run_safe_query
# ---------------------------------------------------------------------------

# Each entity that the run_safe_query whitelist exposes is mapped to the
# column that identifies the owning/participating user, plus an optional
# role-based "is this the caller?" test. The AI is forced to filter on
# the authenticated user for any of these entities so one user can never
# enumerate another user's listings, requests, or profile data.
_SAFE_QUERY_USER_SCOPE = {
    # donor_id OR recipient_id must equal auth user
    "listings": ("donor_id", "recipient_id"),
    # recipient_id must equal auth user
    "requests": ("recipient_id",),
    # id must equal auth user (no enumerating the users table)
    "users": ("id",),
}


def _scope_safe_query(fn_args: dict[str, Any], auth_user_id: str) -> dict[str, Any]:
    """Ensure run_safe_query is always scoped to the authenticated user.

    If the caller (an LLM) does not already include a filter binding the
    query to its own user_id via one of the accepted columns, we inject
    an ``eq`` filter so the result cannot span other accounts. Centers are
    public directory data and are left unchanged.

    User IDs are compared as strings so UUIDs (DoGoods/Supabase) and
    integer ids (legacy) both work.
    """
    if not isinstance(fn_args, dict):
        return {"entity": "centers"}
    entity = str(fn_args.get("entity") or "").lower()
    accepted_cols = _SAFE_QUERY_USER_SCOPE.get(entity)
    if not accepted_cols:
        # Centers (or unknown entity — handler will reject) — no scoping.
        return fn_args

    filters = fn_args.get("filters") or []
    if not isinstance(filters, list):
        filters = []

    auth_str = str(auth_user_id)

    def _binds_to_auth(f: dict[str, Any]) -> bool:
        if not isinstance(f, dict):
            return False
        field = str(f.get("field", ""))
        op = str(f.get("op", "eq")).lower()
        val = f.get("value")
        if field not in accepted_cols or op != "eq":
            return False
        return str(val) == auth_str

    # Drop any filter on one of the scope columns that targets a *different*
    # user, then append our own eq-filter if none already binds us.
    cleaned = [
        f for f in filters
        if not (isinstance(f, dict)
                and str(f.get("field", "")) in accepted_cols
                and not _binds_to_auth(f))
    ]
    if not any(_binds_to_auth(f) for f in cleaned):
        cleaned.append({
            "field": accepted_cols[0],
            "op": "eq",
            "value": auth_str,
        })

    new_args = dict(fn_args)
    new_args["filters"] = cleaned
    return new_args


# ---------------------------------------------------------------------------
# Conversation Engine
# ---------------------------------------------------------------------------


def _build_memory_snapshot(history: list[dict[str, Any]]) -> Optional[str]:
    """Distill recent tool calls into a compact context block.

    Walks the assistant messages newest-first, collects the latest
    listings, claims, posts, and reminders the model produced, and
    returns a short markdown-ish summary the next chat turn can use to
    answer "claim it", "what was the address", "show me #3", etc.

    Returns None if there's nothing worth replaying.
    """
    if not isinstance(history, list) or not history:
        return None

    latest_listings: list[dict[str, Any]] = []
    recent_claims: list[dict[str, Any]] = []
    recent_posts: list[dict[str, Any]] = []
    recent_cancels: list[dict[str, Any]] = []
    # claim_id → cancelled flag, so we can hide claims the user already
    # cancelled from the "Recent successful claims" section instead of
    # showing them and letting the model double-cancel.
    cancelled_claim_ids: set[str] = set()
    last_search_summary: Optional[str] = None

    # Tool names match the live handler names in backend/tools.py.
    # Do NOT include legacy aliases here — if a row in history has an
    # unknown tool name it just won't contribute, which is the safe behavior.
    SEARCH_TOOLS = {
        "search_food_near_user",
        "get_recent_listings",
        "query_distribution_centers",
    }
    CLAIM_TOOLS = {"claim_listing", "claim_food", "confirm_claim"}
    CANCEL_TOOLS = {"cancel_claim"}
    POST_TOOLS = {"post_food_listing", "create_food_listing", "post_food_request"}

    for msg in reversed(history):
        if msg.get("role") != "assistant":
            continue
        meta = msg.get("metadata") or {}
        # Skip silent congratulation turns triggered by non-AI events
        # (bulk upload, photo enrichment). Their actions aren't real user
        # context — they were synthesized to make the assistant react.
        if meta.get("silent_trigger"):
            continue
        actions = meta.get("actions") or []
        if not isinstance(actions, list):
            continue
        for a in actions:
            if not isinstance(a, dict):
                continue
            tool = a.get("tool")
            if tool in SEARCH_TOOLS and a.get("listings") and not latest_listings:
                latest_listings = a.get("listings") or []
                last_search_summary = a.get("summary")
            elif tool in CLAIM_TOOLS and a.get("ok"):
                cid = a.get("claim_id")
                # Drop earlier successful claims that the user later cancelled.
                if not cid or cid not in cancelled_claim_ids:
                    recent_claims.append(a)
            elif tool in CANCEL_TOOLS and a.get("ok"):
                cid = a.get("claim_id")
                if cid:
                    cancelled_claim_ids.add(cid)
                recent_cancels.append(a)
            elif tool in POST_TOOLS and a.get("ok"):
                recent_posts.append(a)
        if (
            latest_listings
            and len(recent_claims) >= 3
            and len(recent_posts) >= 3
            and len(recent_cancels) >= 2
        ):
            break

    if not (latest_listings or recent_claims or recent_posts or recent_cancels):
        return None

    lines: list[str] = ["RECENT CONTEXT (use this to resolve references like 'claim it', '#3', 'that one', 'the bread'):"]
    if latest_listings:
        lines.append(
            "Last search results — ONLY use these listing_ids when the user "
            "picks one from the list you JUST showed them THIS turn (e.g. "
            "'claim #3', 'I want the bread'). If the user asks 'what's "
            "available' or 'show me food', call search_food_near_user again "
            "because listings change as others claim food. These cached "
            "results are for resolving picks within the same conversation "
            "flow, NOT for answering availability questions:"
        )
        for i, item in enumerate(latest_listings, 1):
            parts = [f"#{i}"]
            if item.get("title"):
                parts.append(str(item["title"]))
            if item.get("quantity") and item.get("unit"):
                parts.append(f"{item['quantity']} {item['unit']}")
            elif item.get("quantity"):
                parts.append(str(item["quantity"]))
            if item.get("category"):
                parts.append(item["category"])
            if item.get("distance_km") is not None:
                parts.append(f"{item['distance_km']} km")
            if item.get("address"):
                parts.append(f"at {item['address']}")
            if item.get("id"):
                parts.append(f"id={item['id']}")
            if item.get("donor_name"):
                parts.append(f"donor={item['donor_name']}")
            lines.append("  - " + " · ".join(parts))
        if last_search_summary:
            lines.append(f"  (search said: {last_search_summary})")

    if recent_claims:
        lines.append("Recent successful claims by this user (use claim_id for cancel/confirm flows):")
        for a in recent_claims[:3]:
            title = a.get("title") or "(item)"
            cid = a.get("claim_id") or "?"
            lid = a.get("listing_id") or "?"
            lines.append(f"  - claim_id={cid} listing_id={lid} title={title}")

    if recent_posts:
        lines.append("Recent successful posts by this user (use listing_id for follow-ups like attaching a photo):")
        for a in recent_posts[:3]:
            title = a.get("title") or "(item)"
            lid = a.get("listing_id") or "?"
            lines.append(f"  - listing_id={lid} title={title}")

    if recent_cancels:
        lines.append(
            "Recently cancelled claims (DO NOT try to cancel these again or "
            "treat them as active):"
        )
        for a in recent_cancels[:3]:
            title = a.get("title") or "(item)"
            cid = a.get("claim_id") or "?"
            lid = a.get("listing_id") or "?"
            lines.append(f"  - claim_id={cid} listing_id={lid} title={title}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Context-window management, anonymous gating, and TTS normalization
# ---------------------------------------------------------------------------

# Nil UUID marks an anonymous (not-logged-in) landing-page session. Personal
# data tools must refuse to run for it.
NIL_UUID = "00000000-0000-0000-0000-000000000000"


def _is_anonymous_user(user_id: Optional[str]) -> bool:
    """True when the caller is the explicit anonymous landing-page session.

    Only the nil-UUID marks an anonymous user. A ``None`` here means auth was
    not enforced (dev/test harness), NOT an anonymous end-user, so it is left
    ungated — the real chat flow always passes a concrete user_id.
    """
    return str(user_id) == NIL_UUID


# Tools that read or write a specific person's private data. The anonymous
# landing-page assistant must NOT be able to invoke these — it has no
# verified identity, so any result would be empty (best case) or leak/scribble
# on whatever id the model hallucinated (worst case). We short-circuit them
# with a `login_required` signal so the model asks the user to sign in.
_PERSONAL_DATA_TOOLS = frozenset({
    "get_user_profile",
    "update_user_profile",
    "get_user_dashboard",
    "get_pickup_schedule",
    "check_pickup_schedule",
    "create_reminder",
    "get_user_notifications",
    "send_notification",
    "mark_notifications_read",
    "claim_listing",
    "confirm_claim",
    "cancel_claim",
    "create_food_listing",
    "post_food_listing",
    "post_food_request",
    "bulk_import_listings",
    "bulk_post_food_listings",
    "get_donor_expiring_listings",
    "attach_photos_to_listing",
    "search_food_near_user",  # needs the user's saved location → personal
})

# Tools whose primary payload is a list of results. Used to detect the
# "no_results" case so the model handles an empty search gracefully instead
# of inventing listings or claiming nothing was searched.
_LIST_RESULT_TOOLS = frozenset({
    "search_food_near_user",
    "get_recent_listings",
    "query_distribution_centers",
    "get_pickup_schedule",
    "check_pickup_schedule",
    "get_user_notifications",
    "get_active_communities",
    "get_donor_expiring_listings",
    "get_recipes",
    "meal_suggestions",
})

# Total character budget for replayed conversation history (a sliding window).
# Re-injecting the full 30-message history unbounded let long multi-step
# chats grow past the model's effective attention span, causing "context
# drift" (the model forgetting or contradicting earlier facts). We keep the
# MOST RECENT messages that fit in this budget; the system prompt, profile
# block, and memory snapshot are ALWAYS re-injected separately and are never
# part of this budget, so the model never loses its training/profile grounding.
_HISTORY_CHAR_BUDGET = int(os.getenv("AI_HISTORY_CHAR_BUDGET", "12000"))
_HISTORY_PER_MSG_CAP = int(os.getenv("AI_HISTORY_PER_MSG_CAP", "4000"))


def _apply_sliding_window(
    history: list[dict[str, Any]],
    char_budget: int = _HISTORY_CHAR_BUDGET,
    per_msg_cap: int = _HISTORY_PER_MSG_CAP,
) -> list[dict[str, Any]]:
    """Trim conversation history to the most recent messages that fit a budget.

    Walks newest → oldest, accumulating the (capped) length of each message,
    and drops everything older than the budget allows. Returns the kept
    messages in chronological order (oldest → newest). This bounds total
    context size so older turns can't crowd out the system/profile prompts
    or push the live message out of the model's effective window.
    """
    if not history:
        return []
    kept: list[dict[str, Any]] = []
    used = 0
    for msg in reversed(history):
        content = msg.get("message") or msg.get("content") or ""
        length = min(len(content), per_msg_cap)
        # Always keep at least the single most recent message, even if it
        # alone exceeds the budget, so the model never sees an empty history.
        if kept and used + length > char_budget:
            break
        kept.append(msg)
        used += length
    kept.reverse()
    return kept


def _annotate_no_results(fn_name: str, result: dict[str, Any]) -> dict[str, Any]:
    """Tag empty list-style tool results with status='no_results'.

    Searches/lookups that legitimately find nothing return an empty list, not
    an error. Without a clear signal the model sometimes invents listings or
    tells the user it "couldn't search". A `status: no_results` marker makes
    the empty case unambiguous so the model says "nothing found right now"
    and suggests a next step (widen radius, check back later).
    """
    if not isinstance(result, dict) or result.get("error"):
        return result
    if fn_name not in _LIST_RESULT_TOOLS:
        return result
    # The list payload lives under one of these keys depending on the tool.
    payload = None
    for key in ("results", "listings", "centers", "notifications",
                "communities", "recipes", "items", "schedule"):
        if key in result and isinstance(result[key], list):
            payload = result[key]
            break
    if payload is not None and len(payload) == 0:
        result.setdefault("status", "no_results")
        result.setdefault("total", 0)
    return result


# Markdown / formatting artefacts that should never be spoken aloud.
_TTS_MARKDOWN_RE = re.compile(r"[*_`#~]+")
_TTS_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_TTS_MULTISPACE_RE = re.compile(r"[ \t]{2,}")
_TTS_MULTINEWLINE_RE = re.compile(r"\n{2,}")

# Common abbreviations expanded so TTS pronounces them naturally. Spanish
# entries fix the most frequent mispronunciations (e.g. "kg", "min", ordinals).
_TTS_ABBREV_EN = {
    "min": "minutes",
    "hr": "hours",
    "hrs": "hours",
    "kg": "kilograms",
    "approx": "approximately",
}
_TTS_ABBREV_ES = {
    "kg": "kilogramos",
    "g": "gramos",
    "min": "minutos",
    "hr": "horas",
    "hrs": "horas",
    "km": "kilómetros",
    "aprox": "aproximadamente",
    "ud": "unidad",
    "uds": "unidades",
    "1ro": "primero",
    "2do": "segundo",
    "3ro": "tercero",
}


def _normalize_for_tts(text: str, lang: str = "en") -> str:
    """Clean and normalize text before sending it to the TTS engine.

    Strips markdown/symbols, expands abbreviations, and collapses whitespace
    so the spoken output sounds natural. For Spanish this also fixes the most
    common mispronunciations (units, ordinals) that the raw text would
    otherwise read out letter-by-letter or in English.
    """
    if not text:
        return ""
    # Render markdown links as just their label.
    out = _TTS_LINK_RE.sub(r"\1", text)
    # Drop emphasis / heading / code markers.
    out = _TTS_MARKDOWN_RE.sub("", out)
    # Expand whole-word abbreviations (case-insensitive, word-boundary safe).
    abbrevs = _TTS_ABBREV_ES if lang == "es" else _TTS_ABBREV_EN
    for short, full in abbrevs.items():
        out = re.sub(rf"(?<![\wáéíóúñ]){re.escape(short)}(?![\wáéíóúñ])", full, out, flags=re.IGNORECASE)
    # Collapse newlines into sentence breaks and squeeze runs of spaces.
    out = _TTS_MULTINEWLINE_RE.sub(". ", out)
    out = out.replace("\n", ". ")
    out = _TTS_MULTISPACE_RE.sub(" ", out)
    return out.strip()


class ConversationEngine:
    """Supabase-backed conversation engine."""

    def __init__(self) -> None:
        self.training_data = _load_training_data()
        from backend.tools import TOOL_DEFINITIONS, execute_tool
        self.tool_definitions = TOOL_DEFINITIONS
        self._execute_tool = execute_tool
        # Derived at boot: every tool whose JSON schema declares a `user_id`
        # property. The dispatch layer overwrites that argument with the
        # authenticated user_id *unconditionally* (even if the model omitted
        # it) so action tools like claim_listing / post_food_listing can never
        # silently fail with "missing required positional argument: 'user_id'".
        self._tools_taking_user_id: frozenset[str] = frozenset(
            t["function"]["name"]
            for t in self.tool_definitions
            if isinstance(t, dict)
            and isinstance(t.get("function"), dict)
            and "user_id" in (
                (t["function"].get("parameters") or {}).get("properties") or {}
            )
        )
        # Built once. The prompt body only depends on training_data, which
        # is loaded from disk at boot and never mutated per-turn. Rebuilding
        # it on every chat round wastes ~8KB of string work and 2–5k tokens
        # of recomputed context per tool round.
        self._system_prompt_cached: str = _build_system_prompt(self.training_data)

    @property
    def system_prompt(self) -> str:
        return self._system_prompt_cached

    def _detect_lang(self, text: str) -> str:
        return "es" if detect_spanish(text) else "en"

    def _detect_lang_sticky(
        self,
        message: str,
        history: Optional[list] = None,
        profile: Optional[dict[str, Any]] = None,
    ) -> str:
        """Sticky language detection.

        Short replies like 'sí', 'ok', 'gracias', 'vale' don't carry
        enough Spanish markers for the per-message detector, which makes
        the assistant flip back to English mid-conversation. Resolve
        language using (in priority order):
          1) the current message itself, if confidently Spanish;
          2) the user's profile.language preference, if set;
          3) any recent user/assistant turn that was Spanish;
          4) default English.
        """
        if message and detect_spanish(message):
            return "es"
        # If the current message contains ANY English-only marker word
        # (and no Spanish chars), treat it as English. This catches
        # short greetings like 'hi', 'hello', 'thanks', 'ok' that don't
        # have 3+ words but are obviously English. The user reported the
        # AI replying in Spanish to plain English messages — this is the
        # fix: English markers beat Spanish profile / Spanish history.
        if message and detect_english(message):
            return "en"
        # Multi-word ASCII-only messages without Spanish chars also win.
        if message:
            lower = message.lower()
            has_spanish_chars = bool(re.search(r"[¿¡ñáéíóúü]", lower))
            ascii_words = re.findall(r"[a-z]{2,}", lower)
            if not has_spanish_chars and len(ascii_words) >= 3:
                return "en"
        try:
            pref = (profile or {}).get("language")
            if isinstance(pref, str) and pref.lower().startswith("es"):
                return "es"
        except Exception:
            pass
        if history:
            for h in reversed(history[-8:]):
                # History items use either "message" (DB rows) or
                # "content" (chat-style dicts). Accept both.
                content = (h or {}).get("message") or (h or {}).get("content") or ""
                if not isinstance(content, str) or not content.strip():
                    continue
                if detect_spanish(content):
                    return "es"
        return "en"

    # ---- Profile lookup via Supabase --------------------------------------

    async def get_user_profile(self, user_id: str) -> Optional[dict[str, Any]]:
        try:
            rows = await supabase_get("users", {
                "id": f"eq.{user_id}",
                "select": "*",
                "limit": "1",
            })
        except Exception as exc:
            logger.error("get_user_profile failed for %s: %s", user_id, exc)
            return None
        if not rows:
            return None
        user = rows[0]
        # Normalised snapshot the rest of the engine relies on. Missing
        # columns simply come through as None so the AI never crashes on
        # an older schema — it just gets fewer facts.
        role = user.get("role")
        is_admin = bool(user.get("is_admin")) or (str(role).lower() == "admin")
        return {
            "id": user.get("id"),
            "name": user.get("name") or user.get("full_name"),
            "email": user.get("email"),
            "role": role,
            "community_role": user.get("community_role"),
            "organization": user.get("organization"),
            "is_admin": is_admin,
            "created_at": user.get("created_at"),
            # Prefer the geocoded `latitude`/`longitude` columns populated by
            # the address-geocoding pipeline; fall back to legacy keys so
            # older rows still work.
            "lat": (
                user.get("latitude")
                or user.get("coords_lat")
                or user.get("lat")
            ),
            "lng": (
                user.get("longitude")
                or user.get("coords_lng")
                or user.get("lng")
            ),
            "address_geocoded_at": user.get("address_geocoded_at"),
            "phone": user.get("phone"),
            "address": user.get("address"),
            "dietary_restrictions": user.get("dietary_restrictions"),
            # DB column is `allergies`; older rows may have used `allergens` —
            # accept both so migrated profiles work without a data fix.
            "allergens": user.get("allergies") or user.get("allergens"),
            "household_size": user.get("household_size"),
            "sms_consent": (
                user.get("sms_consent")
                or user.get("sms_opt_in")
                or user.get("sms_notifications_enabled")
            ),
            "language": user.get("language"),
        }

    # ---- History via Supabase ---------------------------------------------

    async def get_conversation_history(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        try:
            rows = await supabase_get("ai_conversations", {
                "user_id": f"eq.{user_id}",
                "select": "id,role,message,metadata,created_at",
                "order": "created_at.desc",
                "limit": str(limit),
            })
        except Exception as exc:
            logger.error("get_conversation_history failed for %s: %s", user_id, exc)
            return []
        # Caller expects chronological order (oldest → newest).
        rows.reverse()
        return [
            {
                "id": r.get("id"),
                "role": r.get("role", "user"),
                "message": r.get("message", ""),
                "metadata": r.get("metadata") or {},
                "created_at": r.get("created_at", ""),
            }
            for r in rows
        ]

    async def store_message(
        self,
        user_id: str,
        role: str,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> Optional[str]:
        try:
            result = await supabase_post("ai_conversations", {
                "user_id": user_id,
                "role": role,
                "message": message,
                "metadata": metadata or {},
            })
        except Exception as exc:
            logger.error("store_message failed for %s: %s", user_id, exc)
            return None
        if isinstance(result, list) and result:
            return result[0].get("id")
        if isinstance(result, dict):
            return result.get("id")
        return None

    async def clear_history(self, user_id: str) -> int:
        try:
            return await supabase_delete("ai_conversations", {
                "user_id": f"eq.{user_id}",
            })
        except Exception as exc:
            logger.error("clear_history failed for %s: %s", user_id, exc)
            return 0

    # ---- Main chat --------------------------------------------------------

    async def chat(
        self,
        user_id: str,
        message: str,
        include_audio: bool = False,
        silent: bool = False,
    ) -> dict[str, Any]:
        profile_task = asyncio.create_task(self.get_user_profile(user_id))
        # Pull 30 messages (~15 turns) so multi-step flows — like "find food,
        # show me #3, what's the address, claim it" spread across breaks —
        # don't lose context. Each message is also kept much longer below
        # (4000 char cap instead of 800) so listing IDs / titles survive.
        history_task = asyncio.create_task(self.get_conversation_history(user_id, limit=30))
        profile, history = await asyncio.gather(profile_task, history_task)

        # Sticky language: use the message, then profile preference, then
        # recent history. Prevents short replies like 'sí' / 'ok' from
        # flipping a Spanish conversation back to English.
        lang = self._detect_lang_sticky(message, history=history, profile=profile)

        messages: list[dict[str, Any]] = [{"role": "system", "content": self.system_prompt}]

        if lang == "es":
            messages.append({
                "role": "system",
                "content": (
                    "The user is communicating in Spanish. You MUST respond "
                    "ENTIRELY in Spanish for this turn and every following "
                    "turn unless the user explicitly switches to another "
                    "language. This includes: your reply text, any natural-"
                    "language summaries of tool results, error explanations, "
                    "confirmation prompts, and follow-up questions. Do NOT "
                    "slip into English even for short phrases (e.g. say "
                    "'¡Listo!' not 'Done!', 'Reclamado' not 'Claimed', "
                    "'Publicado' not 'Posted'). Maintain a warm, helpful "
                    "personality."
                ),
            })
        else:
            # Symmetric English lock. Without this, if any prior assistant
            # turn in history was Spanish, the model copies that style and
            # keeps replying in Spanish even though the user just wrote in
            # English. This system message overrides that drift.
            messages.append({
                "role": "system",
                "content": (
                    "The user is communicating in English. You MUST respond "
                    "ENTIRELY in English for this turn, even if earlier turns "
                    "in the conversation history were in Spanish or another "
                    "language. The user has switched (or always was) writing "
                    "in English — match them. This applies to your reply "
                    "text, tool-result summaries, confirmation prompts, "
                    "follow-up questions, and error explanations. Do not "
                    "include Spanish phrases or translations. Only switch "
                    "back to Spanish if the user explicitly writes in Spanish "
                    "again."
                ),
            })

        if profile:
            # Build a rich, conversational context block so the model has
            # the same situational awareness a human assistant would. Skip
            # null/blank fields so we don't pollute the prompt.
            facts = [f"Current user: {profile.get('name') or 'Community Member'} (ID: {user_id})"]
            role = profile.get("role") or "member"
            facts.append(f"role: {role}")
            community_role = profile.get("community_role")
            if community_role:
                facts.append(
                    f"community role: {community_role} — tailor suggestions accordingly "
                    f"(donor=help them share food, recipient=help them find/claim food, "
                    f"volunteer/driver/organizer=help with logistics, sponsor=focus on community impact)"
                )
            if profile.get("address"):
                facts.append(f"profile address on file: {profile['address']}")
            else:
                facts.append("NO profile address on file (will need one to post listings/requests)")
            # Surface the geocoded coordinates so the model can pass them to
            # distance / route / nearby-search tools without having to ask
            # the user for their location every turn.
            try:
                _raw_lat = profile.get("lat")
                _raw_lng = profile.get("lng")
                p_lat = float(_raw_lat) if _raw_lat is not None else None
                p_lng = float(_raw_lng) if _raw_lng is not None else None
            except (TypeError, ValueError):
                p_lat, p_lng = None, None
            if p_lat is not None and p_lng is not None:
                facts.append(
                    f"profile coordinates (geocoded from address): lat={p_lat:.6f}, "
                    f"lng={p_lng:.6f} — USE THESE as the origin for "
                    "search_food_near_user, get_mapbox_route, and any "
                    "distance calculation. Do NOT ask the user where they are."
                )
            elif profile.get("address"):
                facts.append(
                    "address is saved but not yet geocoded — search_food_near_user "
                    "may not return distance-sorted results. Suggest re-saving the "
                    "address in Settings if nearby search fails."
                )
            if profile.get("phone"):
                facts.append(f"phone on file: {profile['phone']} (recommended for pickup coordination)")
            else:
                # TODO(twilio): once SMS confirmation is live, a phone will be
                # required to claim — restore the 'claim will fail' warning then.
                facts.append("NO phone on file (suggest adding one so the donor can coordinate pickup)")
            if profile.get("dietary_restrictions"):
                facts.append(f"dietary restrictions: {profile['dietary_restrictions']}")
            if profile.get("allergens"):
                facts.append(f"allergens: {profile['allergens']} — NEVER suggest food matching these")
            if profile.get("household_size"):
                facts.append(f"household size: {profile['household_size']}")
            if profile.get("language"):
                # Annotate the saved preference with the *currently
                # detected* language so the model doesn't get a mixed
                # signal (e.g. saved 'es' but they're typing English
                # right now → reply in English).
                saved = str(profile.get("language"))
                if lang == "es":
                    facts.append(
                        f"preferred language: {saved} — they ARE writing in "
                        f"Spanish this turn, respond in Spanish."
                    )
                else:
                    facts.append(
                        f"preferred language: {saved} (saved), but they are "
                        f"writing in English this turn — RESPOND IN ENGLISH. "
                        f"Saved preference does not override the live message."
                    )
            facts.append(
                f"When calling tools that require user_id, always use \"{user_id}\" "
                "— NEVER ask the user for their id or any other field listed above. "
                "You already know it."
            )
            context = "\n".join(facts)
        else:
            context = (
                f"Current user ID: {user_id}. "
                f"When calling tools that require user_id, always use \"{user_id}\"."
            )
        messages.append({"role": "system", "content": context})

        # Conversation-awareness reminder. Without this the model treats
        # every turn as fresh and re-asks for things the user already
        # answered earlier in the same chat.
        messages.append({
            "role": "system",
            "content": (
                "CONVERSATION AWARENESS (CRITICAL — read this every turn):\n"
                "• Before responding, SCAN the full conversation above for "
                "facts the user already provided. Reuse them silently.\n"
                "• Multi-turn form filling: when you are gathering fields "
                "for a tool (post_food_listing, post_food_request, "
                "create_reminder, etc.), TRACK every field across turns. "
                "If turn 1 the user said 'I want to share apples', turn 2 "
                "you asked 'how many?', and turn 3 they said '10', you "
                "ALREADY know title=apples qty=10 — proceed to the next "
                "missing field. Never re-ask what is already answered.\n"
                "• Pronouns + references: 'it', 'that', 'that one', '#3', "
                "'the bread', 'the one near me' refer to items from "
                "earlier turns OR the RECENT CONTEXT block below. Resolve "
                "them locally; do NOT search again unless the user asks.\n"
                "• Numbered selections after a search ('the 2nd', '#3', "
                "'the kale'): match against the last list you showed; "
                "claim_listing directly with that listing_id. BUT this only "
                "applies when no claim is in progress. If you have already "
                "locked onto one listing and asked a per-item question "
                "('how many?', 'pickup or delivery?', 'lock it in?'), a bare "
                "number is the ANSWER to that question (the quantity / a "
                "yes-style confirmation) — NOT a new selection. Stay on the "
                "same listing; never silently switch items mid-claim.\n"
                "• If a tool returned an error, acknowledge what went "
                "wrong and ask only for the MISSING piece, not the full "
                "form again.\n"
                "• NEVER ask for fields already shown in the user-profile "
                "context above (address, phone, dietary_restrictions, "
                "allergens). Use them silently.\n"
                "• If asked 'what did I just claim/post?' or 'what was "
                "the address?', answer from the RECENT CONTEXT block or "
                "the prior assistant turn — do NOT call a tool to "
                "re-fetch unless the user explicitly asks for fresh data."
            ),
        })

        # Action policy: let the AI actually DO things on the user's behalf.
        # Always inject for authenticated users — gating on keyword match
        # caused the model to silently fall back to text-only replies
        # whenever the user phrased a donation in an unfamiliar way (e.g.
        # 'I have a few cans of soup spare'), making listings 'sometimes
        # work, sometimes not'.
        if True:
            action_policy_en = (
                "You can take actions for the user through tool calls. Use the ACTION "
                "tools (claim_listing, cancel_claim, update_user_profile, post_food_request, "
                "post_food_listing, send_notification) whenever the user asks — you do not "
                "need to ask them to click buttons. "
                "Rules: "
                "(1) The server enforces the authenticated user_id; still pass the id shown above. "
                "(2) For destructive / irreversible actions (cancel_claim, post_food_listing, "
                "post_food_request), confirm briefly once before calling. "
                "(3) For small updates (e.g. adding an allergy, opting into SMS), act immediately and report what changed. "
                "(4) When the user says things like 'I'll take it', 'reserve that', 'grab #42', "
                "call claim_listing. Then tell them where to pick up and to let you know once "
                "they've got it so you can confirm the pickup. "
                "(5) If a tool returns an error, explain it plainly and suggest the next step. "
                "(6) ALWAYS CONFIRM COMPLETION: after a tool returns success, lead your reply "
                "with an explicit completion phrase ('Done!', 'Posted!', 'Sent!', 'Updated.', "
                "'Released.', 'Confirmed!', 'Saved.', 'Reminder set.') so the user clearly hears "
                "the action FINISHED. Never leave the turn open-ended after a write tool — the "
                "user must know the work is complete before any follow-up question or next step. "
                "(7) STAY FOCUSED: if a multi-step flow is in progress (e.g. listing apples) and "
                "the user mentions a different food (e.g. 'ice cream'), DO NOT silently swap "
                "items. Ask one disambiguator: 'Add ice cream as a second listing after the "
                "apples, or switch to ice cream instead?' Default assumption is ADD, not "
                "replace. Carry captured fields (title, qty, address, etc.) across turns; never "
                "quietly drop them. "
                "(8) IGNORE-AND-STEER: if the user asks something off-topic mid-flow (weather, "
                "trivia, jokes, unrelated chat), briefly decline and steer back to the open "
                "task. If they persist, ask once whether to pause the flow. "
                "(9) FOOD ONLY: DoGoods lists FOOD. If a user tries to list non-food items "
                "(furniture, electronics, clothes), decline warmly and suggest Buy Nothing / "
                "Freecycle. If a recipient asks for cash/cars/gift cards, decline and offer to "
                "search for available food instead. Stay scoped to food sharing, food safety, "
                "pickups, recipes, storage, and community impact."
            )
            action_policy_es = (
                "Puedes realizar acciones por el usuario mediante tool calls. Usa las herramientas "
                "de ACCIÓN (claim_listing, cancel_claim, update_user_profile, post_food_request, "
                "post_food_listing, send_notification) cuando el usuario lo pida — no le digas que "
                "haga clic en botones. Reglas: (1) El servidor impone el user_id autenticado. "
                "(2) Confirma brevemente antes de acciones destructivas. (3) Para cambios pequeños, "
                "actúa de inmediato y reporta el resultado. (4) Frases como 'lo tomo', 'resérvalo' "
                "deben disparar claim_listing. (5) Si una herramienta falla, explícalo y sugiere el "
                "siguiente paso. (6) CONFIRMA SIEMPRE QUE TERMINASTE: después de un éxito, comienza "
                "tu respuesta con una frase clara de finalización ('¡Listo!', '¡Publicado!', "
                "'¡Enviado!', 'Actualizado.', 'Liberado.', '¡Confirmado!', 'Guardado.', "
                "'Recordatorio creado.') para que el usuario sepa que la acción YA TERMINÓ antes "
                "de cualquier siguiente paso. "
                "(7) MANTÉN EL FOCO: si hay un flujo en curso (p.ej. publicando manzanas) y el "
                "usuario menciona otra comida (p.ej. 'helado'), NO cambies en silencio. Pregunta "
                "una sola vez: '¿Agrego el helado como un SEGUNDO anuncio después de las "
                "manzanas, o cambias a helado?' Por defecto: AGREGAR, no reemplazar. Conserva "
                "los campos ya capturados (título, cantidad, dirección) entre turnos. "
                "(8) IGNORAR Y REDIRIGIR: si en medio del flujo el usuario pregunta algo fuera "
                "de tema (clima, chistes, trivia), declina brevemente y vuelve a la tarea. Si "
                "insiste, pregunta una vez si pausamos el flujo. "
                "(9) SOLO COMIDA: DoGoods es para comida. Si intenta publicar objetos no "
                "alimenticios (muebles, ropa, electrónicos), declina con amabilidad y sugiere "
                "Buy Nothing o Freecycle. Si pide dinero/coches/tarjetas de regalo, declina y "
                "ofrece buscar comida disponible. Mantente en el ámbito de comida, seguridad "
                "alimentaria, recogidas, recetas, almacenamiento e impacto comunitario."
            )
            messages.append({
                "role": "system",
                "content": action_policy_es if lang == "es" else action_policy_en,
            })

        # Role-specific behaviour + profile-gap nudges (best-effort; non-fatal)
        try:
            # community_role ("donor","recipient","volunteer","dispatcher","admin")
            # is the field that determines which role-behavior block fires.
            # profile["role"] is the Supabase auth role ("member","admin") and
            # does NOT match the _ROLE_BEHAVIOR_EN keys — using it meant the
            # entire block (including the "POSTING/CLAIMING NOT ALLOWED" safety
            # guardrails) was silently skipped for every non-admin user.
            role_prompt = _role_behavior_prompt(
                (profile or {}).get("community_role") or (profile or {}).get("role"),
                lang=lang,
            )
            if role_prompt:
                messages.append({"role": "system", "content": role_prompt})
        except Exception as exc:  # pragma: no cover
            logger.debug("role prompt build failed: %s", exc)

        try:
            gap_prompt = await _profile_gap_prompt(user_id, lang=lang)
            if gap_prompt:
                messages.append({"role": "system", "content": gap_prompt})
        except Exception as exc:  # pragma: no cover
            logger.debug("profile gap prompt failed: %s", exc)

        # Skip legacy silent-prompt user rows (created before the silent
        # flag existed) and silent-trigger assistant rows so the model
        # never sees orphaned "[Action completed]…" turns or a
        # congratulatory assistant turn with no preceding user message.
        _SILENT_USER_PREFIXES = (
            "[action completed]",
            "[acción completada]",
            "[accion completada]",
        )
        # Sliding window: keep only the most recent turns that fit the char
        # budget so a long conversation can't push the system prompt / live
        # message out of the model's effective attention (context drift). The
        # system prompt, profile facts, and memory snapshot are re-injected
        # separately below and are never trimmed.
        windowed_history = _apply_sliding_window(history)
        for msg in windowed_history:
            role = msg.get("role", "user")
            content = msg.get("message", "")
            if role == "user" and isinstance(content, str) and content.strip().lower().startswith(_SILENT_USER_PREFIXES):
                continue
            if role == "assistant" and (msg.get("metadata") or {}).get("silent_trigger"):
                continue
            # Per-message cap so previous assistant turns that enumerated
            # listings (with ids/titles/distances) survive intact. Without
            # this, "claim #3" can't be resolved because the original list
            # was sliced mid-item.
            if len(content) > _HISTORY_PER_MSG_CAP:
                content = content[:_HISTORY_PER_MSG_CAP] + "... [truncated]"
            messages.append({"role": role, "content": content})

        # Replay recent tool-result summaries so the model retains the
        # structured facts that were never persisted as message text.
        # Without this, after a page refresh the user can say "claim it"
        # and the model has no listing_id, no donor name, no address.
        memory_snapshot = _build_memory_snapshot(history)
        if memory_snapshot:
            messages.append({
                "role": "system",
                "content": memory_snapshot,
            })

        lower_message = (message or "").lower()
        wants_new_listings = any(
            phrase in lower_message
            for phrase in (
                "new listings",
                "new listing",
                "latest listings",
                "latest listing",
                "recent listings",
                "recent listing",
                "check new listings",
                "check latest listings",
                "what's new",
                "whats new",
            )
        )
        if wants_new_listings:
            messages.append({
                "role": "system",
                "content": (
                    "This request is specifically about newly posted listings. "
                    "You MUST call get_recent_listings for this turn unless the "
                    "user explicitly asked for nearby distance-based results."
                ),
            })

        messages.append({"role": "user", "content": message})

        response_text, actions = await self._call_with_fallbacks(messages, lang, auth_user_id=user_id)

        conversation_id = await self._persist_conversation(
            user_id, message, response_text, lang, actions=actions, silent=silent,
        )

        audio_b64 = None
        if include_audio:
            audio_b64 = await self._generate_audio_b64(response_text, lang=lang)

        # Quick-reply chips always follow the sticky conversation language
        # (`lang`) from the user's own messages — never re-detect from the
        # assistant reply. Mixed-language replies (e.g. English prose ending
        # in "¿Quieres que lo publique?") must not flip chips to Spanish.
        return {
            "text": response_text,
            "audio_url": audio_b64,  # data URL, or None
            "user_id": str(user_id),
            "lang": lang,
            "conversation_id": str(conversation_id) if conversation_id else None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tool_results": actions,
            "actions": actions,
            "suggestions": generate_quick_replies(response_text, lang),
        }

    async def _persist_conversation(
        self,
        user_id: str,
        user_msg: str,
        assistant_msg: str,
        lang: str,
        actions: Optional[list[dict[str, Any]]] = None,
        silent: bool = False,
    ) -> Optional[str]:
        # Anonymous sessions all share the nil UUID — the ai_conversations.user_id
        # FK references auth.users(id), so the insert would fail anyway AND
        # different users would end up reading each other's rows under the
        # same fake id. Skip persistence cleanly instead of relying on the
        # swallowed error path.
        if not user_id or user_id == "00000000-0000-0000-0000-000000000000":
            return None
        try:
            assistant_metadata: dict[str, Any] = {"lang": lang}
            if silent:
                assistant_metadata["silent_trigger"] = True
            # Strip large payloads but keep the lightweight facts the next
            # turn needs to resolve "claim it" / "show me the 3rd one" /
            # "what was the address again". We persist titles, ids, and
            # short summaries — not full geometries / arrays — so the row
            # stays small but the model regains context after a refresh.
            if actions:
                compact: list[dict[str, Any]] = []
                for a in actions[-8:]:  # last 8 tool calls per turn is plenty
                    if not isinstance(a, dict):
                        continue
                    res = a.get("result") or {}
                    listings = res.get("listings") or res.get("results") or []
                    compact_listings = []
                    # Persist the full visible search page (up to 12) — search
                    # tools return up to max_results=10. Capping at 5 here meant
                    # that after a page refresh the model only had IDs for the
                    # first 5 listings, so "claim #7" silently picked one of
                    # the first 5 instead — the user saw the wrong item
                    # claimed.
                    for item in (listings[:12] if isinstance(listings, list) else []):
                        if not isinstance(item, dict):
                            continue
                        compact_listings.append({
                            "id": item.get("id"),
                            "title": item.get("title") or item.get("name"),
                            "category": item.get("category"),
                            "quantity": item.get("quantity"),
                            "unit": item.get("unit"),
                            "latitude": item.get("latitude") or item.get("lat"),
                            "longitude": item.get("longitude") or item.get("lng"),
                            "distance_km": item.get("distance_km"),
                            "address": item.get("full_address") or item.get("address"),
                            "donor_name": item.get("donor_name"),
                        })
                    entry_compact: dict[str, Any] = {
                        "tool": a.get("tool"),
                        "ok": a.get("ok"),
                        "summary": (a.get("summary") or "")[:240],
                        # Mirror `ok` as a success flag so ToolResultCard
                        # checks like `result?.success` work on re-hydrated rows.
                        "success": bool(a.get("ok")),
                        "listing_id": res.get("listing_id") or a.get("listing_id"),
                        "claim_id": res.get("claim_id") or a.get("claim_id"),
                        "receipt_id": res.get("receipt_id") or a.get("receipt_id"),
                        "title": res.get("title"),
                        "quantity": res.get("quantity"),
                        "unit": res.get("unit"),
                        "pickup_location": res.get("pickup_location"),
                        "listings": compact_listings,
                    }
                    # Preserve UI-control + route fields so map markers and
                    # navigation actions can re-fire after a page refresh.
                    for k in ("action", "path", "target", "view", "focus", "target_id", "lang"):
                        if a.get(k) is not None:
                            entry_compact[k] = a[k]
                    if isinstance(a.get("route"), dict):
                        entry_compact["route"] = {
                            "geometry": a["route"].get("geometry"),
                            "origin": a["route"].get("origin"),
                            "destination": a["route"].get("destination"),
                            "distance_km": a["route"].get("distance_km"),
                            "duration_text": a["route"].get("duration_text"),
                            "profile": a["route"].get("profile"),
                        }
                    compact.append(entry_compact)
                if compact:
                    assistant_metadata["actions"] = compact
            # Silent prompts (e.g. "[Action completed] I just published…")
            # are internal context, not something the user typed. Skip the
            # user-side store so the prompt never appears in chat history.
            if silent:
                row_id = await self.store_message(
                    user_id, "assistant", assistant_msg, metadata=assistant_metadata,
                )
            else:
                # Store SEQUENTIALLY (user first, then assistant) — NOT via
                # asyncio.gather. created_at defaults to now() at insert time;
                # two concurrent inserts can land on the same microsecond or
                # even invert, which makes get_conversation_history (ordered
                # by created_at) render the assistant bubble BEFORE the user's
                # message after a refresh. Awaiting in order guarantees the
                # user row commits with a strictly-earlier timestamp.
                await self.store_message(user_id, "user", user_msg)
                row_id = await self.store_message(
                    user_id, "assistant", assistant_msg, metadata=assistant_metadata,
                )
            return row_id
        except Exception as exc:
            logger.error("Persistence failed: %s", exc)
            return None

    # ---- GPT call with fallback ------------------------------------------

    async def _call_with_fallbacks(self, messages: list[dict[str, Any]], lang: str = "en", auth_user_id: Optional[str] = None) -> tuple[str, list[dict[str, Any]]]:
        actions: list[dict[str, Any]] = []
        try:
            text = await self._call_openai_chat(messages, lang=lang, auth_user_id=auth_user_id, actions_out=actions)
            return text, actions
        except httpx.TimeoutException as exc:
            logger.warning("GPT timeout after %ss: %s", TIMEOUT_SECONDS, exc)
            return get_canned_response("timeout", lang), actions
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            body_preview = ""
            try:
                body_preview = exc.response.text[:300]
            except Exception:
                body_preview = ""
            logger.error("GPT HTTP %s error: %s | body=%s", status, exc, body_preview)
            return get_canned_response("api_down", lang), actions
        except RuntimeError as exc:
            logger.error("GPT runtime error: %s", exc)
            return get_canned_response("api_down", lang), actions
        except Exception as exc:
            logger.exception("GPT unexpected error: %s", exc)
            return get_canned_response("general_error", lang), actions

    async def public_chat_reply(self, messages: list[dict[str, Any]], lang: str = "en") -> str:
        """Stateless OpenAI call with NO tools and NO persistence.

        Used by the anonymous landing-page chat. Safe to expose without auth.
        """
        if not OPENAI_API_KEY:
            return get_canned_response("api_down", lang)
        payload = {
            "model": CHAT_MODEL,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 600,
        }
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }
        try:
            resp = await _openai_chat_with_model_fallback(
                primary_model=CHAT_MODEL,
                fallbacks=CHAT_MODEL_FALLBACKS,
                json_payload=payload,
                headers=headers,
                label="public-chat",
            )
            data = resp.json()
            return data["choices"][0]["message"].get("content", "").strip() or get_canned_response("general_error", lang)
        except httpx.TimeoutException:
            return get_canned_response("timeout", lang)
        except httpx.HTTPStatusError:
            return get_canned_response("api_down", lang)
        except Exception as exc:
            logger.error("public_chat_reply error: %s", exc)
            return get_canned_response("general_error", lang)

    @staticmethod
    def _needs_tools(message: str) -> bool:
        lower = message.lower()
        tool_keywords = {
            "dashboard", "profile", "my account", "my info",
            "pickup", "schedule", "claim", "claimed",
            "remind", "reminder", "set a reminder",
            "near me", "nearby", "find food", "available food",
            "search food", "food near", "listings near",
            "direction", "directions", "route", "routes",
            "distribution", "community", "communities", "center",
            "my listings", "my food",
            # role-specific
            "expiring", "expire", "expiry", "about to expire",
            "queue", "dispatch", "assignment", "assign", "unassigned",
            "stats", "metrics", "platform", "how are we doing",
            "complete my profile", "fill my profile", "profile gap",
            "dietary", "allergies", "preferences",
            # voice / GPS / routing / query
            "current location", "here", "my location", "gps",
            "urgent", "urgency", "most urgent",
            "optimize", "optimise", "best route", "plan route",
            "recipe", "recipes", "cook", "meal",
            "how many", "how much", "query", "list all", "show me",
            # actions (write)
            "reserve", "take it", "grab it", "i'll take",
            "cancel", "release", "unclaim", "drop",
            "update my", "change my", "set my", "save my",
            "add allergy", "add allergies", "add dietary",
            "opt in", "opt out", "sms", "text me",
            "post a request", "request food", "ask for",
            "post a listing", "list my", "donate", "share food", "give away",
            "loaves", "loaf", "bread", "fruit", "produce", "vegetables",
            "send message", "tell admin", "tell donor", "message them",
        }
        return any(kw in lower for kw in tool_keywords)

    async def _call_openai_chat(self, messages: list[dict[str, Any]], lang: str = "en", auth_user_id: Optional[str] = None, actions_out: Optional[list] = None) -> str:
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY not configured")

        user_text = ""
        for m in reversed(messages):
            if m["role"] == "user":
                user_text = m.get("content", "")
                break
        # Look at recent assistant turns too: if we just asked the user a
        # data-gathering question (e.g. 'how many?'), their reply will be
        # short ('3', 'yes') and won't match the keyword check on its own.
        # Tools must stay attached or the model can only emit text and will
        # hallucinate 'Posted!' without actually calling post_food_listing.
        recent_assistant = ""
        for m in reversed(messages[-6:]):
            if m["role"] == "assistant" and m.get("content"):
                recent_assistant = m["content"]
                break
        use_tools = True

        payload = {
            "model": CHAT_MODEL,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 1024,
        }
        if use_tools:
            payload["tools"] = self.tool_definitions

        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }

        resp = await _openai_chat_with_model_fallback(
            primary_model=CHAT_MODEL,
            fallbacks=CHAT_MODEL_FALLBACKS,
            json_payload=payload,
            headers=headers,
        )
        data = resp.json()
        choice = data["choices"][0]
        msg = choice["message"]

        # Multi-round tool calling. The previous single-round design meant
        # that if the FIRST tool call returned an error (bad address, past
        # date, unknown category, etc.) the followup model had no tools
        # attached and could only apologize in text — the listing would
        # silently fail. With up to 3 rounds the model can self-correct
        # once or twice (e.g. retry post_food_listing with a fuller
        # address) before giving up.
        MAX_TOOL_ROUNDS = 3
        round_idx = 0
        # Defense-in-depth against runaway tool loops: if the model keeps
        # invoking the same tool with byte-identical args we stop short of
        # MAX_TOOL_ROUNDS to protect quota and tail latency.
        _recent_calls: list[tuple[str, str]] = []
        # Per-conversation tool-result cache. Same tool + same args inside
        # one turn returns the cached result instead of hitting the DB/API
        # twice. Cheap memory, big quota savings.
        _tool_cache: dict[tuple[str, str], dict[str, Any]] = {}
        while msg.get("tool_calls") and round_idx < MAX_TOOL_ROUNDS:
            round_idx += 1
            tool_messages = list(messages)
            tool_messages.append(msg)
            for tool_call in msg["tool_calls"]:
                fn_name = tool_call["function"]["name"]
                try:
                    fn_args = json.loads(tool_call["function"]["arguments"])
                except (json.JSONDecodeError, TypeError) as parse_err:
                    tool_messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": json.dumps({"error": f"Invalid arguments: {parse_err}"}),
                    })
                    continue
                # Security: the AI must never operate on another user's
                # behalf. Whenever a tool call carries a `user_id` argument,
                # force it to the authenticated user so prompt-injection
                # (or a hallucinated id) cannot pivot to another account.
                # This covers BOTH read tools (profile, dashboard, history,
                # pickups) and write tools (claim, cancel, update, post).
                #
                # Inject UNCONDITIONALLY for any tool whose schema accepts
                # user_id, not just when the model included it. The model
                # often omits user_id (it has no reliable way to know its
                # own UUID), and the bare `_claim_food_listing` /
                # `_post_food_listing` handlers take user_id as a required
                # positional argument — without injection they raise
                # TypeError and the AI replies "I couldn't claim that"
                # while no food_claims row is ever created.
                if not isinstance(fn_args, dict):
                    fn_args = {}
                if auth_user_id is not None and fn_name in self._tools_taking_user_id:
                    fn_args["user_id"] = str(auth_user_id)
                # run_safe_query: force a caller-scoped filter on any entity
                # that has a user column, so the model can't enumerate other
                # users' listings/requests or read the users table freely.
                if fn_name == "run_safe_query" and auth_user_id is not None:
                    fn_args = _scope_safe_query(fn_args, auth_user_id)
                # Same-tool-same-args repetition guard. If the model has
                # called this exact (name, args) 3 times already inside
                # this turn, return a short error instead of hitting the
                # backend again so the model is forced to change tack.
                try:
                    _args_key = json.dumps(fn_args, sort_keys=True, default=str)[:2000]
                except Exception:
                    _args_key = str(fn_args)[:2000]
                _call_key = (fn_name, _args_key)
                if _recent_calls.count(_call_key) >= 2:
                    tool_messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": json.dumps({
                            "error": (
                                f"{fn_name} was already called with these arguments. "
                                "Try a different tool or different arguments, or answer the user directly."
                            )
                        }),
                    })
                    _recent_calls.append(_call_key)
                    continue
                _recent_calls.append(_call_key)
                # Anonymous gate: the landing-page assistant (nil-UUID / no
                # auth) must not touch personal data. Refuse the tool with a
                # structured login_required signal so the model asks the user
                # to sign in instead of operating on an empty/forged identity.
                if fn_name in _PERSONAL_DATA_TOOLS and _is_anonymous_user(auth_user_id):
                    login_msg = (
                        "Inicia sesión para que pueda hacer eso por ti."
                        if lang == "es"
                        else "Please sign in so I can do that for you."
                    )
                    tool_messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": json.dumps({
                            "error": "login_required",
                            "message": (
                                f"{fn_name} requires the user to be logged in. "
                                "Politely tell the user they need to sign in or "
                                "create an account to use this, and offer to help "
                                "with general (non-personal) questions meanwhile."
                            ),
                            "user_message": login_msg,
                        }),
                    })
                    continue
                # Per-turn tool-result cache: skip duplicate work cleanly.
                cached_result = _tool_cache.get(_call_key)
                if cached_result is not None:
                    result: dict[str, Any] = cached_result
                else:
                    try:
                        result = await self._execute_tool(fn_name, fn_args)
                        # Validate the shape: handlers must return a dict. A
                        # non-dict (None, list, str) means a buggy/legacy tool
                        # path — coerce it into a structured error so the model
                        # never tries to read fields off a bad value.
                        if not isinstance(result, dict):
                            logger.warning(
                                "Tool %s returned non-dict %s; coercing to error",
                                fn_name, type(result).__name__,
                            )
                            result = {
                                "success": False,
                                "error": f"{fn_name} returned an unexpected result. Please try again.",
                            }
                        # Annotate empty list-style results so the model
                        # explicitly handles the "no_results" case instead of
                        # hallucinating items or claiming it didn't search.
                        result = _annotate_no_results(fn_name, result)
                        if isinstance(result, dict) and not result.get("error"):
                            _tool_cache[_call_key] = result
                    except Exception as tool_exc:
                        # Log full traceback server-side; surface a generic
                        # message so internal exception text doesn't reach
                        # the user via the AI's reply.
                        logger.exception("Tool %s failed", fn_name)
                        result = {
                            "success": False,
                            "error": f"{fn_name} failed. Please try again.",
                        }

                # Trace tool calls so we can debug why the model picked a tool.
                try:
                    logger.info(
                        "AI tool call: %s args=%s ok=%s",
                        fn_name,
                        {k: v for k, v in fn_args.items() if k != "user_id"},
                        not (isinstance(result, dict) and result.get("error")),
                    )
                except Exception:
                    pass

                # Record this tool call so the UI can surface progress /
                # done indicators (claiming, listing posted, etc.).
                if actions_out is not None and isinstance(result, dict):
                    err_val = result.get("error")
                    if err_val is True:
                        ok = False
                    elif err_val:
                        ok = False
                    elif result.get("success") is False or result.get("created") is False:
                        ok = False
                    else:
                        ok = True
                    # Suppress noisy "✗ Claim failed" chips when the model
                    # hallucinates a listing the user never asked for. The
                    # backend returned an error and the chat reply itself
                    # already explains it; an additional red chip just
                    # confuses the user.
                    suppress_chip = (
                        not ok
                        and fn_name in {"claim_listing", "confirm_claim", "cancel_claim"}
                        and isinstance(err_val, str)
                        and (
                            "not found" in err_val.lower()
                            or "invalid" in err_val.lower()
                            or "no listing_id" in err_val.lower()
                        )
                    )
                    if not suppress_chip:
                        summary_val = result.get("summary")
                        if not summary_val and err_val:
                            summary_val = err_val if isinstance(err_val, str) else None
                        entry = {
                            "tool": fn_name,
                            "ok": bool(ok),
                            "summary": summary_val,
                            "result": result,
                            "listing_id": result.get("listing_id"),
                        }
                        # Forward extra UI-control / map fields at the top level
                        # so legacy consumers can read them without unwrapping.
                        for extra_key in (
                            "action", "target", "view", "focus", "path",
                            "listing_id", "lang", "target_id",
                            "geometry", "origin", "destination",
                            "coords_lat", "coords_lng", "address",
                            "verified", "verify_issues", "duplicate_of_recent",
                            "claim_id", "receipt_id",
                        ):
                            if extra_key in result and result[extra_key] is not None:
                                entry[extra_key] = result[extra_key]
                        if isinstance(result.get("route"), dict):
                            entry["route"] = result["route"]
                        elif result.get("geometry"):
                            entry["route"] = {
                                "geometry": result.get("geometry"),
                                "origin": result.get("origin"),
                                "destination": result.get("destination"),
                                "distance_km": result.get("distance_km"),
                                "duration_text": result.get("duration_text"),
                                "profile": result.get("profile"),
                            }
                        actions_out.append(entry)

                result_str = json.dumps(result, default=str)
                if len(result_str) > 4000:
                    # For bulk operations, the per-row `results` array can be
                    # huge. Drop it and keep the summary so the AI can still
                    # report success/failure counts without blowing the
                    # context window. For other tools, fall back to a hard
                    # truncate.
                    if isinstance(result, dict) and isinstance(result.get("results"), list):
                        trimmed = {k: v for k, v in result.items() if k != "results"}
                        trimmed["results_omitted"] = len(result["results"])
                        result_str = json.dumps(trimmed, default=str)
                    if len(result_str) > 4000:
                        result_str = result_str[:4000] + "...[truncated]"
                tool_messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": result_str,
                })

            followup_payload = {
                "model": FOLLOWUP_MODEL,
                "messages": tool_messages,
                "temperature": 0.7,
                "max_tokens": 1024,
                # Keep tools attached so the model can retry after a tool
                # error (e.g. correct an address, switch category) instead
                # of silently giving up in text.
                "tools": self.tool_definitions,
            }
            try:
                resp = await _openai_chat_with_model_fallback(
                    primary_model=FOLLOWUP_MODEL,
                    fallbacks=FOLLOWUP_MODEL_FALLBACKS,
                    json_payload=followup_payload,
                    headers=headers,
                    label="openai-followup",
                )
                followup_data = resp.json()
                msg = followup_data["choices"][0]["message"]
                # The followup response becomes the seed for the next loop
                # iteration. Persist conversation context too so subsequent
                # tool rounds reference both the original messages AND the
                # tool results from this round.
                messages = tool_messages
            except Exception as followup_exc:
                logger.error("Follow-up failed: %s", followup_exc)
                return get_canned_response("tool_error", lang)

        content = (msg.get("content") or "").strip()
        if content:
            return content
        # We get here with empty content in two cases:
        #   1. The model hit MAX_TOOL_ROUNDS with a pending tool_calls message
        #      (no text yet), or
        #   2. the model returned an empty assistant message.
        # Either way, never hand the user a blank reply — fall back to a
        # helpful canned line so the chat bubble always has content.
        if msg.get("tool_calls"):
            logger.warning("Tool loop exhausted (%s rounds) with no final text", round_idx)
        return get_canned_response("tool_error", lang)

    # ---- Whisper + TTS ---------------------------------------------------

    async def transcribe_audio(self, audio_bytes: bytes, filename: str = "audio.webm") -> str:
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY not configured")
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
        resp = await _openai_with_retry(
            "POST",
            f"{OPENAI_BASE_URL}/audio/transcriptions",
            headers=headers,
            files={"file": (filename, audio_bytes)},
            data={"model": WHISPER_MODEL, "response_format": "json"},
            timeout=60,
        )
        return resp.json()["text"]

    async def generate_speech(self, text: str, lang: str = "en") -> bytes:
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY not configured")
        # Normalize markdown/abbreviations before TTS so the spoken output
        # sounds natural and Spanish is pronounced correctly (units, ordinals)
        # rather than read out letter-by-letter or in English.
        normalized = _normalize_for_tts(text, lang=lang)
        truncated = normalized[:4096]
        voice = TTS_VOICE_ES if lang == "es" else TTS_VOICE_EN
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }
        resp = await _openai_with_retry(
            "POST",
            f"{OPENAI_BASE_URL}/audio/speech",
            headers=headers,
            json_payload={"model": TTS_MODEL, "input": truncated, "voice": voice},
            timeout=30,
        )
        return resp.content

    async def _generate_audio_b64(self, text: str, lang: str = "en") -> Optional[str]:
        """Return the TTS audio as a base64 data URL (no external storage needed)."""
        try:
            audio_bytes = await self.generate_speech(text, lang=lang)
            import base64
            b64 = base64.b64encode(audio_bytes).decode("ascii")
            return f"data:audio/mpeg;base64,{b64}"
        except Exception as exc:
            logger.warning("Audio generation failed: %s", exc)
            return None


def _chip_language(reply_text: str, conv_lang: str) -> str:
    """Decide which language the quick-reply chips should render in.

    The conversation language (``conv_lang``) — derived by sticky detection
    from the *user's own* messages — is the baseline and is trusted. We only
    override it when the AI's reply is *unambiguously* in the other language,
    judged by a dominance score rather than a stray accent or loan-word.

    This fixes Spanish chips leaking into English conversations: an English
    reply that merely mentions "jalapeño", "piña", "café" or "résumé" must
    NOT flip the chips (and their tapped input) to Spanish. ``detect_spanish``
    treats a single ``ñ`` / two accents as conclusive, which is correct for
    classifying a user's own message but too eager for re-classifying the
    assistant's reply against an already-established conversation language.
    """
    base = "es" if conv_lang == "es" else "en"
    if not reply_text:
        return base

    lower = reply_text.lower()

    # Inverted question/exclamation marks only ever appear in genuine Spanish
    # prose — never inside an English loan-word — so they are conclusive.
    strong_es_punct = bool(re.search(r"[¿¡]", lower))

    words = set(re.split(r"\W+", lower))
    es_hits = len(words & _SPANISH_MARKERS)
    en_hits = len(words & _ENGLISH_MARKERS)

    if base == "es":
        # Established Spanish chat: stay Spanish unless the reply is clearly,
        # predominantly English (model ignored a Spanish profile).
        if not strong_es_punct and en_hits >= 2 and en_hits > es_hits:
            return "en"
        return "es"

    # Established English (or unknown) chat: only switch to Spanish on a
    # strong, dominant Spanish signal — not a lone accented loan-word.
    if strong_es_punct or (es_hits >= 3 and es_hits > en_hits):
        return "es"
    return "en"


def generate_quick_replies(text: str, lang: str = "en") -> list[str]:
    """Heuristic 'smart reply' / autofill chips for the chat UI.

    Looks at the last AI message and returns up to 4 short tappable
    suggestions the user is likely to want to reply with. Pure string
    matching — no extra LLM call, so it's free and instant.

    Rule of thumb: it is better to return [] (no chips) than to return
    chips that don't match the question. Yes/No/Later under "what food
    would you like to share?" is worse than no chips at all.
    """
    if not text:
        return []
    full = text.lower()
    # Only suggest when the AI is actually asking the user something,
    # otherwise chips would clutter every reply.
    if "?" not in full and "¿" not in full:
        return []

    # Scope keyword matching to the LAST question in the message. The AI
    # often mentions things like "no allergens noted" or "added the photo"
    # in earlier sentences, which would otherwise mis-trigger chip
    # branches keyed on those words. The chips should answer the question
    # the user is actually being asked.
    import re as _re
    # Split on sentence terminators while keeping '?' attached.
    parts = _re.split(r"(?<=[.!?¿])\s+", full)
    last_q = ""
    for seg in reversed(parts):
        if "?" in seg or "¿" in seg:
            last_q = seg
            break
    # Fall back to the full text if we couldn't isolate a question.
    t = last_q or full

    es = lang == "es"
    out: list[str] = []

    def add(*items: str) -> None:
        for it in items:
            if it and it not in out and len(out) < 4:
                out.append(it)

    # An "open-ended" question is one that asks WHAT / WHICH / WHEN /
    # WHERE / HOW MANY / HOW MUCH — never answerable with yes/no.
    # NOTE on Spanish: only match accented "qué " (the question word).
    # Unaccented "que " is a connector/pronoun ("¿Quieres que…?") and
    # would mis-fire as open-ended on yes/no questions.
    open_ended = any(
        k in t for k in (
            "what ", "which ", "when ", "where ", "how many", "how much",
            "what's", "what is",
            "qué ", "cuál", "cuándo", "dónde", "cuántos", "cuántas",
        )
    )

    # ---- Specific intent branches (run before any generic fallback) -----

    # Listing selection — "which one would you like" / "which one sounds good"
    # when presenting food options. Check for numbered list indicators +
    # selection prompt. Run BEFORE open-ended check since "which" triggers
    # that but we want chips here.
    has_numbered_list = any(
        marker in full for marker in (
            "1.", "1)", "2.", "2)", "3.", "3)", "• ", "- ",
            # Look for patterns like "Here's what's close" / "Here are the"
            "here's what", "here are the", "here's the", "closest options",
            "available options", "nearby", "opciones", "las opciones",
        )
    )
    selection_prompt = any(
        k in t for k in (
            "which one", "which one would you like", "which one sounds good",
            "which would you like", "pick one", "choose one", "reply with the number",
            "cuál", "cual", "elige uno", "escoge uno", "responde con el número",
        )
    )
    if has_numbered_list and selection_prompt:
        if es:
            add("1", "2", "3", "Más detalles")
        else:
            add("1", "2", "3", "More details")
        return out

    # Address confirmation — run BEFORE post-confirm so "does that look good?"
    # about a street address doesn't mis-fire as a publish prompt.
    address_cues = (
        "address", "street", " st ", " st.", " ave", "location", "pickup at",
        "dirección", "direccion", "calle", "main st", "your profile",
    )
    has_address_cue = any(c in full for c in address_cues)
    if has_address_cue and any(k in t for k in (
            "profile address", "use your address", "what address",
            "address on file", "saved address", "a different address",
            "does that look good", "does this look good", "look good to you",
            "look right", "right address", "correct address", "that address",
            "dirección de tu perfil", "dirección del perfil", "tu dirección guardada",
            "uso tu dirección", "uso la dirección", "qué dirección", "que direccion",
            "otra dirección", "¿es correcta", "es correcta",
    )):
        if es:
            add("Sí, usa esa", "Es otra dirección", "No tengo una guardada")
        else:
            add("Yes, use that one", "Use a different address", "I don't have one saved")
        return out

    # Community confirmation — before final post confirm.
    # Extract community names from the text for dynamic chips.
    community_cues = (
        "community", "school", "district", "neighborhood", "comunidad",
        "escuela", "distrito",
    )
    if any(c in full for c in community_cues) and any(k in t for k in (
            "which community", "what community", "community is this", "community should",
            "post to", "share with", "listed under", "list this under", "list under",
            "for which community", "profile community", "your community",
            "confirm the community", "is this for",
            "qué comunidad", "que comunidad", "cuál comunidad", "cual comunidad",
            "para qué comunidad", "a qué comunidad", "tu comunidad",
            "comunidad de tu perfil", "bajo qué comunidad",
    )):
        # Try to extract community names from the text.
        # Pattern: capitalized words (2-4 words) near community keywords.
        # Examples: "Alameda Unified", "Oakland Tech", "Lincoln Elementary"
        import re as _re_comm
        # Look for patterns like "post this to Oakland Tech" or
        # "Alameda Unified, Oakland Tech, or another"
        # Match 1-4 capitalized words in sequence
        pattern = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b'
        matches = _re_comm.findall(full)
        
        # Filter matches: exclude common false positives
        exclude = {
            'Should', 'Which', 'What', 'Community', 'School', 'District',
            'Post', 'Share', 'List', 'Under', 'Profile', 'Your',
            'I', 'Oakland', 'Alameda', 'San', 'The', # Single city names
            'Qué', 'Cuál', 'Para', 'Tu', 'Comunidad', 'Escuela',
        }
        community_names = []
        for match in matches:
            words = match.split()
            # Keep if: 2+ words OR (1 word with 5+ chars AND not in exclude list)
            if len(words) >= 2 or (len(words) == 1 and len(match) >= 5 and match not in exclude):
                # Further filter: must not be a question word at start
                if words[0] not in exclude and match not in community_names:
                    community_names.append(match)
        
        # Use extracted names as chips, max 3 + "Other"
        if community_names:
            for name in community_names[:3]:
                add(name)
            if es:
                add("Otra comunidad")
            else:
                add("Other")
            return out
        
        # Fallback to generic chips if no names extracted
        if es:
            add("Sí, esa comunidad", "Es otra comunidad", "No estoy seguro")
        else:
            add("Yes, that community", "Different community", "Not sure")
        return out

    # Final confirm: explicit post/publish phrasing only — avoid bare
    # "look good" / "sounds good" which appear in unrelated questions.
    confirm_post_keys = (
        "post it", "post that", "post this", "post the listing",
        "publish it", "publish that", "publish this", "publish the listing",
        "should i post", "shall i post", "want me to post", "ok to post",
        "ready to post", "ready to publish", "go ahead and post",
        "good to post", "good to publish",
        "confirm and post", "shall i go ahead", "should i go ahead",
        # Spanish
        "publicarlo", "publicar la", "publicar el", "publico la", "publico el",
        "lo publique", "que lo publique", "quieres que lo publique",
        "¿lo publico", "¿lo publicamos", "¿publicamos",
        "listo para publicar",
    )
    if any(k in t for k in confirm_post_keys):
        if es:
            add("Sí, publícalo", "Espera, edítalo", "Cancelar")
        else:
            add("Yes, post it", "Wait, edit it", "Cancel")
        return out

    # Handoff method (pickup vs drop-off). Skip if the question is about
    # WHEN — "¿cuándo pueden recogerlo?" is a pickup-window question, not
    # a handoff question, even though it contains "recoger".
    is_when_question = any(
        k in t for k in ("when can", "what time", "cuándo", "cuando", "qué horario", "que horario")
    )
    if (not is_when_question) and any(
        k in t for k in ("pick this up", "pick it up", "picking them up", "picking it up",
                         "drop it off", "drop-off", "drop off",
                         "deliver", "pickup or", "recoger", "entregar", "entrega")
    ):
        if es:
            add("Recogida", "Yo lo entrego", "Cualquiera")
        else:
            add("Pickup", "I'll drop it off", "Either works")
        if any(k in t for k in ("radius", "how far", "miles", "millas", "qué tan lejos")):
            if es:
                add("5 millas", "10 millas")
            else:
                add("Within 5 mi", "Within 10 mi")
        return out

    # Allergens
    if "allerg" in t or "alérgen" in t or "alergia" in t:
        if es:
            add("Sin alérgenos", "Solo gluten", "Lácteos", "Frutos secos")
        else:
            add("No allergens", "Just gluten", "Dairy", "Nuts")
        return out

    # Photo — only when the AI asks the donor to ATTACH one. Viewing /
    # reviewing an existing photo ("Can I see the photo first?") must not
    # offer add/skip chips.
    photo_view_keys = (
        "see the photo", "see photo", "view the photo", "view photo",
        "show me the photo", "show the photo", "can i see", "look at the photo",
        "ver la foto", "ver foto", "mostrar la foto", "mirar la foto",
    )
    photo_add_keys = (
        "add a photo", "add photo", "attach a photo", "attach photo",
        "include a photo", "upload a photo", "send a photo", "add an image",
        "like to add a photo", "want to add a photo", "would you like to add",
        "añadir foto", "adjuntar foto", "subir foto", "agregar foto",
        "quieres agregar una foto", "te gustaría agregar", "te gustaria agregar",
    )
    if (
        not any(k in t for k in photo_view_keys)
        and any(k in t for k in photo_add_keys)
    ):
        if es:
            add("Adjuntar foto", "Sin foto", "Después")
        else:
            add("I'll add one", "Skip the photo", "Maybe later")
        return out

    # Pickup window / when
    if any(k in t for k in ("when can", "pick them up", "pickup window", "what time",
                            "cuándo pueden", "cuando pueden", "qué horario", "que horario")):
        if es:
            add("Hoy 5–8pm", "Mañana", "Próximas 24h", "Cuando sea")
        else:
            add("Today 5–8pm", "Tomorrow morning", "Next 24h", "Whenever")
        return out

    # Freshness / expiration
    if any(k in t for k in ("best by", "expir", "fresh", "baked", "made it",
                            "when was", "how long", "good for", "spoils",
                            "caduc", "vence", "fresco", "horneado", "preparado")):
        if es:
            add("Hecho hoy", "Hecho ayer", "Vence mañana")
        else:
            add("Made today", "Made yesterday", "Good for 24h")
        return out

    # Quantity prompt — require an explicit count cue. "how much"
    # appears in many non-numeric questions like "how much does it
    # weigh?" or "how much time do you have?".
    if any(k in t for k in ("how many", "what unit", "three what",
                            "cuántos", "cuántas", "qué unidad")):
        if es:
            add("1", "3", "5", "10")
        else:
            add("1", "3", "5", "10")
        return out

    # "What food / what would you like to share / what is it / what are you donating"
    if any(k in t for k in (
            "what food", "what would you like to share", "what would you like to donate",
            "what are you sharing", "what are you donating", "what is it", "what's the food",
            "what do you have", "what kind of food",
            # Spanish
            "qué comida", "que comida",
            "qué quieres compartir", "que quieres compartir",
            "qué te gustaría compartir", "que te gustaria compartir",
            "qué tienes", "que tienes",
            "qué vas a donar", "que vas a donar",
            "qué quieres donar", "que quieres donar",
            "qué te gustaría donar", "que te gustaria donar",
            "qué tipo de comida", "que tipo de comida",
            "qué vas a compartir", "que vas a compartir",
    )):
        if es:
            add("Pan", "Frutas", "Verduras", "Comida preparada")
        else:
            add("Bread", "Fruit", "Vegetables", "Prepared meal")
        return out

    # "What are you looking for" (recipient side)
    if any(k in t for k in (
            "what are you looking for", "what do you need",
            "qué buscas", "que buscas",
            "qué necesitas", "que necesitas",
            "qué te hace falta", "que te hace falta",
            "qué estás buscando", "que estas buscando",
    )):
        if es:
            add("Pan", "Frutas", "Verduras", "Comida preparada")
        else:
            add("Bread", "Fruit", "Vegetables", "Prepared meal")
        return out

    # Claim confirmation — "claim it / reserve it / shall I claim"
    claim_confirm_keys = (
        "claim it", "claim that", "claim this", "shall i claim",
        "want me to claim", "reserve it", "reserve that", "should i reserve",
        "confirm the claim", "go ahead and claim", "lock it in", "ready to claim",
        "reclamarlo", "reservarlo", "lo reclamo", "lo reservo", "asegurarlo",
        "confirmar el reclamo", "confirmo el reclamo", "lo reclamo?",
        "¿lo reclamo", "¿lo reservo", "¿lo aseguro",
    )
    if any(k in t for k in claim_confirm_keys):
        if es:
            add("Sí, reclamarlo", "No, busca otro", "Cancelar")
        else:
            add("Yes, claim it", "Find me something else", "Cancel")
        return out

    # Pickup schedule (after claiming) — "when can you pick it up"
    pickup_schedule_keys = (
        "when can you pick", "when will you pick", "pickup time",
        "what time will you", "schedule your pickup",
        "cuándo puedes recoger", "cuando puedes recoger",
        "a qué hora recoges", "horario de recogida",
    )
    if any(k in t for k in pickup_schedule_keys):
        if es:
            add("Hoy", "Mañana", "En las próximas 24h")
        else:
            add("Today", "Tomorrow", "Within 24h")
        return out

    # Quantity for claiming — "how many would you like" / "how much do you need"
    claim_qty_keys = (
        "how many would you like", "how many do you need", "how much do you need",
        "how many would you want", "how many do you want", "quantity would you like",
        "how many", "cuántos quieres", "cuántas quieres", "cuánto necesitas",
        "cuántos necesitas", "cuántas necesitas",
    )
    if any(k in t for k in claim_qty_keys):
        if es:
            add("1", "2", "3", "Todos")
        else:
            add("1", "2", "3", "All of them")
        return out

    # Cancel / release claim — "cancel the claim" / "release it"
    cancel_claim_keys = (
        "cancel the claim", "release the claim", "release it",
        "cancel your claim", "should i cancel",
        "cancelar el reclamo", "liberar el reclamo",
        "¿cancelo el reclamo", "cancelo el reclamo",
    )
    if any(k in t for k in cancel_claim_keys):
        if es:
            add("Sí, cancelar", "No, mantenlo")
        else:
            add("Yes, cancel it", "No, keep it")
        return out

    # Post-claim assistance — "want directions?" / "need help?"
    # Check for claim success indicators + help offer
    claim_success_indicators = (
        "claimed", "reserved", "locked in", "reclamado", "reservado",
        "done!", "all set", "you're all set", "pick it up", "pickup at",
    )
    help_offers = (
        "want directions", "need directions", "need the donor", "need help",
        "anything else", "what else", "help with", "assistance",
        "quieres direcciones", "necesitas direcciones", "necesitas el",
        "algo más", "qué más", "ayuda con",
    )
    if any(ind in full for ind in claim_success_indicators) and any(offer in t for offer in help_offers):
        if es:
            add("Sí, direcciones", "No, estoy bien", "Recogí la comida")
        else:
            add("Yes, directions", "No, I'm good", "I picked it up")
        return out

    # Open-ended wh-question with no specific branch above: don't guess.
    # Empty chips > wrong chips.
    if open_ended:
        return out

    # Generic yes/no question — only safe when NOT open-ended. Don't
    # include "can i" here: it appears in many user-direction questions
    # like "Can I see the photo first?" where Yes/No/Later is wrong.
    if any(k in t for k in (
            "would you like", "do you want", "ready to", "should i",
            "shall i", "want me to",
            "¿quieres", "quieres que", "¿te gustaría", "te gustaría que",
            "¿listo", "¿debo", "¿lo hago", "¿lo hacemos",
    )):
        if es:
            add("Sí", "No", "Más tarde")
        else:
            add("Yes", "No", "Later")
        return out

    return out


conversation_engine = ConversationEngine()

