"""
DoGoods AI (Nouri) — FastAPI router (mounted onto the main app).

Endpoints:
  POST /api/ai/chat            - Text conversation
  POST /api/ai/recipes         - Recipe suggestions for listings / claimed food
  GET  /api/ai/history/{uid}   - Retrieve conversation history
  DELETE /api/ai/history/{uid} - Clear history
  POST /api/ai/voice           - Whisper transcribe + chat
  POST /api/ai/tts             - Text-to-speech
  POST /api/ai/feedback        - Rate a message
  GET  /api/ai/health          - Health check
  POST /api/ai/confirm         - Execute a pending confirmation
  GET  /api/ai/goals/{uid}     - User goal history

Authentication: uses the main app's JWT (Bearer token). If the token's "sub"
matches the request body's user_id, the call is authorised.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timezone

from typing import Optional, List

import httpx
import jwt
from fastapi import APIRouter, HTTPException, Request, Response, UploadFile, File, Form, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from backend.aws_secrets import load_aws_secrets

from backend.ai.ai_engine import (
    conversation_engine,
    check_rate_limit,
    close_http_client,
)
from backend.ai.errors import (
    AIDatabaseError,
    AIError,
    AIServiceUnavailable,
    AITimeout,
    AIUpstreamError,
    resolve_lang,
)

logger = logging.getLogger("ai_routes")


def _utcnow() -> datetime:
    """Naive UTC datetime replacement for the deprecated ``_utcnow()``."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


load_aws_secrets()

# The main app (`backend/app.py:130-138`) already fails at import time
# when JWT_SECRET is missing in production. Do NOT fall back to a hard-
# coded string here — that used to silently degrade to `"your-secret-key"`
# and let unsigned tokens sail through in any deploy that forgot to set
# the env var.
JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    # Defer failure to first request so the module can still be imported
    # by tests that stub out authentication. In prod, the app.py check
    # already crashes at boot when JWT_SECRET is missing.
    JWT_SECRET = ""
JWT_ALGORITHM = "HS256"

# Supabase-issued JWTs are HS256, signed with the project's JWT secret
# (Dashboard → Settings → API → "JWT Secret"). If that secret is
# available, verifying locally is fast and offline. If it isn't, we
# fall back to hitting Supabase's GoTrue /auth/v1/user endpoint so
# real deploys keep working while ops rotates keys.
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET") or ""
SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL") or ""
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY") or ""

# When `AI_REQUIRE_AUTH=true` (production default) every user-scoped
# AI endpoint MUST present a valid Bearer token and the token's `sub`
# must match the body `user_id`. When "false" (only intended for the
# in-process test harness that stubs Supabase auth) we degrade to a
# best-effort ownership check — a token, if present, is verified, but
# missing tokens do not block requests.
AI_REQUIRE_AUTH = os.getenv("AI_REQUIRE_AUTH", "true").lower() not in {"0", "false", "no", ""}

REMINDER_CHECK_INTERVAL = int(os.getenv("REMINDER_CHECK_INTERVAL", "900"))

router = APIRouter(prefix="/api/ai", tags=["ai"])
# auto_error=False so we can craft a language-aware 401 body ourselves
# instead of the default "Not authenticated" HTML-ish detail.
security = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _enforce_rate_limit(request: Request) -> None:
    if not check_rate_limit(_client_ip(request)):
        raise HTTPException(429, "Rate limit exceeded. Try again later.")


_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _parse_user_id(raw: str) -> str:
    """Accept any non-empty user_id string (integer or Supabase UUID)."""
    if not raw:
        raise HTTPException(400, "user_id required")
    return str(raw).strip()


def _require_uuid(user_id: str) -> None:
    """Reject non-UUID user_ids on endpoints that only serve real users.

    Legacy endpoints still accept numeric IDs for backwards compat with
    the in-memory test fixtures, but user-facing surfaces (voice, chat
    with real Supabase auth) should require a proper UUID so a garbled
    input yields 400 (bad request) rather than 403 (forbidden) after the
    ownership check fails.
    """
    if not _UUID_RE.match(user_id):
        raise HTTPException(400, "user_id must be a UUID")


# --- Bearer token verification -------------------------------------
#
# The frontend authenticates with Supabase Auth
# (``supabase.auth.signInWithPassword``) which issues HS256 JWTs signed
# with the project's JWT secret — NOT the same secret this backend uses
# for its own local login tokens. We therefore try three strategies in
# order:
#
#   1) Verify with our local ``JWT_SECRET`` (backwards compat for any
#      HS256 tokens minted by ``backend/app.py`` login endpoints).
#   2) Verify with ``SUPABASE_JWT_SECRET`` if configured — fast, offline,
#      no network round-trip per request.
#   3) Ask Supabase's GoTrue REST endpoint (``/auth/v1/user``) to
#      validate the token, with a short in-process cache so we don't
#      burn a REST call on every AI turn. This path keeps working when
#      ops hasn't provisioned SUPABASE_JWT_SECRET yet.
#
# All three return the token's ``sub`` (user UUID) on success or None.

# Verified-token cache: token → (sub, expires_at). Bounded and short-lived
# so a compromised token can't be replayed indefinitely, but long enough
# that a burst of AI chat turns doesn't spam GoTrue.
_SUPABASE_TOKEN_CACHE: dict[str, tuple[str, float]] = {}
_SUPABASE_TOKEN_CACHE_TTL_S = 60.0
_SUPABASE_TOKEN_CACHE_MAX = 512


def _cache_get(token: str) -> str | None:
    import time
    entry = _SUPABASE_TOKEN_CACHE.get(token)
    if not entry:
        return None
    sub, expires_at = entry
    if time.time() >= expires_at:
        _SUPABASE_TOKEN_CACHE.pop(token, None)
        return None
    return sub


def _cache_put(token: str, sub: str) -> None:
    import time
    if len(_SUPABASE_TOKEN_CACHE) >= _SUPABASE_TOKEN_CACHE_MAX:
        # Evict the oldest entry — dict preserves insertion order in
        # CPython 3.7+, so `next(iter(...))` is the FIFO victim.
        try:
            _SUPABASE_TOKEN_CACHE.pop(next(iter(_SUPABASE_TOKEN_CACHE)))
        except (StopIteration, KeyError):
            pass
    _SUPABASE_TOKEN_CACHE[token] = (sub, time.time() + _SUPABASE_TOKEN_CACHE_TTL_S)


def _try_hs256(token: str, secret: str) -> str | None:
    """Decode an HS256 token with ``secret`` and return its ``sub`` on success."""
    if not secret or not token:
        return None
    try:
        payload = jwt.decode(
            token, secret, algorithms=[JWT_ALGORITHM],
            # Supabase JWTs carry `aud: "authenticated"`. PyJWT rejects
            # tokens with an `aud` claim unless we either pass audience=
            # or disable that check. We disable because we already vet
            # tokens via `sub` matching the requested user_id.
            options={"verify_aud": False},
        )
        sub = payload.get("sub")
        return str(sub) if sub is not None else None
    except (jwt.PyJWTError, ValueError, TypeError):
        return None


async def _verify_via_supabase_rest(token: str) -> str | None:
    """Ask Supabase GoTrue to validate a Bearer token.

    Returns the user's UUID on success or None. Used only when the
    fast HS256 paths don't yield a decode (SUPABASE_JWT_SECRET not
    configured, or token wasn't minted by us OR by our Supabase project).
    """
    if not token or not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return None
    cached = _cache_get(token)
    if cached is not None:
        return cached
    url = f"{SUPABASE_URL.rstrip('/')}/auth/v1/user"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    # GoTrue requires the anon key on top of the user
                    # bearer even for /user calls; without it you get 401.
                    "apikey": SUPABASE_ANON_KEY,
                },
            )
        if resp.status_code != 200:
            return None
        data = resp.json()
        sub = data.get("id") or data.get("sub")
        if sub:
            sub = str(sub)
            _cache_put(token, sub)
            return sub
        return None
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        logger.debug("Supabase REST verify failed: %s", exc)
        return None


def _auth_user_id(credentials: HTTPAuthorizationCredentials | None) -> str | None:
    """Synchronous best-effort verify — used from sync code paths.

    Tries the two HS256 secrets we know about. Callers that need
    Supabase REST fallback should use :func:`_auth_user_id_async`.
    """
    if credentials is None:
        return None
    token = credentials.credentials
    return _try_hs256(token, JWT_SECRET) or _try_hs256(token, SUPABASE_JWT_SECRET)


async def _auth_user_id_async(
    credentials: HTTPAuthorizationCredentials | None,
) -> str | None:
    """Async variant that adds Supabase REST fallback verification."""
    sub = _auth_user_id(credentials)
    if sub is not None:
        return sub
    if credentials is None:
        return None
    return await _verify_via_supabase_rest(credentials.credentials)


def _check_ownership(auth_uid: str | None, requested_uid: str) -> None:
    """Enforce that the JWT (if provided) matches the requested user_id.

    Legacy behaviour retained for backwards compat: when NO token is
    present, we skip the check. New auth-required flows should use
    :func:`_require_owner` instead, which rejects unauthenticated
    requests up-front.
    """
    if auth_uid is not None and auth_uid != requested_uid:
        raise HTTPException(403, "user_id does not match authenticated user")


async def _require_owner(
    credentials: HTTPAuthorizationCredentials | None,
    requested_uid: str,
) -> None:
    """Require a valid Bearer token whose `sub` matches ``requested_uid``.

    Applied to endpoints that read or mutate a specific user's data
    (chat, history, confirm claims, TTS, etc.). Fails closed:
      - No token → 401
      - Bad token / wrong sub → 403

    Tests that need to bypass this can either mint a JWT with
    ``JWT_SECRET`` from the conftest, or set ``AI_REQUIRE_AUTH=false``.

    Async so it can transparently fall back to Supabase REST
    verification when neither local secret decodes the token.
    """
    if not AI_REQUIRE_AUTH:
        _check_ownership(await _auth_user_id_async(credentials), requested_uid)
        return
    if credentials is None:
        raise HTTPException(401, "Authentication required")
    auth_uid = await _auth_user_id_async(credentials)
    if auth_uid is None:
        raise HTTPException(401, "Invalid or expired token")
    if auth_uid != requested_uid:
        raise HTTPException(403, "user_id does not match authenticated user")


async def _require_authenticated(
    credentials: HTTPAuthorizationCredentials | None,
) -> str:
    """Require a valid Bearer token; return the token's `sub`.

    Used by endpoints (e.g. ``/api/ai/tts``) that need SOME authenticated
    caller but don't take a body ``user_id``. In test mode
    (``AI_REQUIRE_AUTH=false``) we allow anonymous callers and return
    a placeholder ``"anonymous"`` id so downstream logic still gets a
    string.
    """
    if not AI_REQUIRE_AUTH:
        return (await _auth_user_id_async(credentials)) or "anonymous"
    if credentials is None:
        raise HTTPException(401, "Authentication required")
    auth_uid = await _auth_user_id_async(credentials)
    if auth_uid is None:
        raise HTTPException(401, "Invalid or expired token")
    return auth_uid


# ---------------------------------------------------------------------------
# Pydantic request/response schemas
# ---------------------------------------------------------------------------

class AIChatRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    # 200KB cap so users can paste/upload CSV inventories for bulk import.
    # Photo uploads use /api/ai/upload_image and only send a short URL.
    message: str = Field(min_length=1, max_length=200000)
    include_audio: bool = False
    tone: Optional[str] = Field(default=None, max_length=32)


class AIChatResponse(BaseModel):
    text: str
    audio_url: Optional[str] = None
    user_id: str
    lang: str = "en"
    tone: str = "warm"
    conversation_id: Optional[str] = None
    transcript: Optional[str] = None
    timestamp: str
    # List of tool calls executed during this turn so the UI can show
    # action indicators (claiming, listing, posted, etc). Each entry is
    # {tool: str, ok: bool, summary: Optional[str]}.
    actions: List[dict] = []
    # Up to 4 short tappable quick replies the UI can show under the
    # assistant bubble (autofill / smart reply chips). Generated from the
    # reply text + intent of the last AI question.
    suggestions: List[str] = []
    # Agentic confirmation gate: True when the engine intercepted a
    # destructive tool and is waiting for an explicit user confirmation
    # before executing it.  The frontend should surface a "Confirm / Cancel"
    # dialog.  Call POST /api/ai/confirm to proceed.
    requires_confirmation: bool = False
    pending_action: Optional[dict] = None


class AIFeedbackRequest(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=32)
    user_id: str = Field(min_length=1, max_length=64)
    rating: str = Field(min_length=1, max_length=20)
    comment: Optional[str] = None


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    lang: str = "en"


class AIPublicChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1500)


class AIPublicChatResponse(BaseModel):
    text: str
    lang: str = "en"
    timestamp: str


class AIRecipesRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    ingredients: Optional[List[str]] = None
    use_claimed: bool = True
    low_resource: bool = True
    household_size: Optional[int] = Field(default=None, ge=1, le=20)
    max_recipes: int = Field(default=3, ge=1, le=5)
    dietary_overrides: Optional[List[str]] = None
    notes: Optional[str] = Field(default=None, max_length=500)


class AIRecipesResponse(BaseModel):
    headline: str = ""
    recipes: List[dict] = []
    source: str = "empty"
    ingredients_used: List[str] = []
    household_size: Optional[int] = None
    low_resource: bool = True
    dietary_restrictions: List[str] = []
    allergens_avoided: List[str] = []
    generated_at: str
    error: Optional[str] = None


class AIToneResponse(BaseModel):
    user_id: str
    tone: str


class AIToneUpdateRequest(BaseModel):
    tone: str = Field(min_length=1, max_length=32)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/health")
async def ai_health() -> dict:
    from backend.ai.ai_engine import OPENAI_API_KEY, CHAT_MODEL, _circuit
    return {
        "status": "ok",
        "openai_configured": bool(OPENAI_API_KEY),
        "chat_model": CHAT_MODEL,
        "circuit_state": _circuit.state.value,
    }


@router.post("/chat", response_model=AIChatResponse)
async def ai_chat(
    body: AIChatRequest,
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    _enforce_rate_limit(request)
    uid = _parse_user_id(body.user_id)
    await _require_owner(credentials, uid)
    lang = resolve_lang(request, body.message)

    try:
        return await conversation_engine.chat(
            user_id=uid,
            message=body.message,
            include_audio=body.include_audio,
            tone=body.tone,
        )
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise AITimeout(lang) from exc
    except httpx.HTTPError as exc:
        raise AIUpstreamError(lang) from exc
    except RuntimeError as exc:
        logger.error("AI chat RuntimeError: %s", exc)
        raise AIServiceUnavailable(lang) from exc
    except Exception as exc:
        logger.exception("AI chat error")
        raise AIError(lang) from exc


@router.post("/recipes", response_model=AIRecipesResponse)
async def ai_recipes(
    body: AIRecipesRequest,
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Generate household-aware recipe suggestions from ingredients or claimed food."""
    _enforce_rate_limit(request)
    uid = _parse_user_id(body.user_id)
    await _require_owner(credentials, uid)

    from backend.ai.recipes import generate_recipes

    try:
        result = await generate_recipes(
            user_id=uid,
            ingredients=body.ingredients,
            use_claimed=body.use_claimed,
            low_resource=body.low_resource,
            household_size=body.household_size,
            max_recipes=body.max_recipes,
            dietary_overrides=body.dietary_overrides,
            notes=body.notes,
        )
    except RuntimeError as exc:
        logger.error("AI recipes RuntimeError: %s", exc)
        raise AIServiceUnavailable("en") from exc
    except Exception as exc:
        logger.exception("AI recipes error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if result.get("error"):
        raise HTTPException(status_code=502, detail=result["error"])

    return result


@router.post("/public_chat", response_model=AIPublicChatResponse)
async def ai_public_chat(
    body: AIPublicChatRequest,
    request: Request,
) -> dict:
    """Anonymous chat for landing page visitors.

    - No authentication required
    - No conversation history stored
    - No tools / user-specific data access
    - IP-based rate limited
    """
    _enforce_rate_limit(request)

    from backend.ai.ai_engine import detect_spanish

    lang = "es" if detect_spanish(body.message) else "en"
    messages = [
        {"role": "system", "content": conversation_engine.system_prompt},
        {
            "role": "system",
            "content": (
                "You are Nouri, talking to an anonymous visitor on the DoGoods landing page. "
                "They are not signed in. Do NOT call any tools. Do NOT ask for or reference "
                "their account, pickups, listings, or reminders. Answer general questions about "
                "how DoGoods works, food sharing, food safety, and community impact in Alameda County. "
                "Keep replies concise (2-4 sentences) and friendly. If they need account-specific "
                "help, politely suggest they sign up or sign in at dogoods.store."
            ),
        },
        {"role": "user", "content": body.message},
    ]
    if lang == "es":
        messages.insert(1, {
            "role": "system",
            "content": "The user wrote in Spanish. Respond entirely in Spanish.",
        })

    try:
        text = await conversation_engine.public_chat_reply(messages, lang=lang)
    except httpx.TimeoutException as exc:
        raise AITimeout(lang) from exc
    except httpx.HTTPError as exc:
        raise AIUpstreamError(lang) from exc
    except Exception as exc:
        logger.exception("Public chat error")
        raise AIError(lang) from exc

    return {
        "text": text,
        "lang": lang,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/history/{user_id}")
async def ai_history(
    user_id: str,
    request: Request,
    limit: int = 50,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    _enforce_rate_limit(request)
    uid = _parse_user_id(user_id)
    await _require_owner(credentials, uid)

    if limit < 1 or limit > 200:
        raise HTTPException(400, "limit must be between 1 and 200")
    lang = resolve_lang(request)

    try:
        history = await conversation_engine.get_conversation_history(uid, limit=limit)
        return {"user_id": user_id, "messages": history, "count": len(history)}
    except SQLAlchemyError as exc:
        logger.exception("History DB error")
        raise AIDatabaseError(lang) from exc
    except Exception as exc:
        logger.exception("History fetch error")
        raise AIError(lang) from exc


@router.delete("/history/{user_id}")
async def ai_clear_history(
    user_id: str,
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    _enforce_rate_limit(request)
    uid = _parse_user_id(user_id)
    await _require_owner(credentials, uid)
    lang = resolve_lang(request)

    try:
        count = await conversation_engine.clear_history(uid)
        return {"user_id": user_id, "cleared": True, "removed": count}
    except SQLAlchemyError as exc:
        logger.exception("Clear history DB error")
        raise AIDatabaseError(lang) from exc
    except Exception as exc:
        logger.exception("Clear history error")
        raise AIError(lang) from exc


@router.get("/tone/{user_id}", response_model=AIToneResponse)
async def ai_get_tone(
    user_id: str,
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    _enforce_rate_limit(request)
    uid = _parse_user_id(user_id)
    await _require_owner(credentials, uid)
    lang = resolve_lang(request)

    try:
        tone = await conversation_engine.get_conversation_tone(uid)
        return {"user_id": user_id, "tone": tone}
    except Exception as exc:
        logger.exception("Get tone error")
        raise AIError(lang) from exc


@router.put("/tone/{user_id}", response_model=AIToneResponse)
async def ai_set_tone(
    user_id: str,
    body: AIToneUpdateRequest,
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    from backend.ai.tone import normalize_tone, VALID_TONES

    _enforce_rate_limit(request)
    uid = _parse_user_id(user_id)
    await _require_owner(credentials, uid)
    lang = resolve_lang(request)

    normalized = normalize_tone(body.tone)
    if body.tone.strip().lower() not in VALID_TONES:
        raise HTTPException(
            400,
            f"tone must be one of: {', '.join(sorted(VALID_TONES))}",
        )

    try:
        saved = await conversation_engine.set_conversation_tone(uid, normalized)
        return {"user_id": user_id, "tone": saved}
    except Exception as exc:
        logger.exception("Set tone error")
        raise AIError(lang) from exc


# ---- Whisper noise filter -------------------------------------------------

# Common Whisper hallucinations on silent or near-silent audio. These
# come from Whisper's training on YouTube-style content: end-card lines,
# subscribe prompts, filler acknowledgements. Keep the set focused; over-
# filtering starts eating real short user utterances.
_WHISPER_NOISE_PHRASES: set[str] = {
    # YouTube / video artifacts
    "thanks for watching", "thank you for watching", "subscribe",
    "music", "applause", "gracias por ver",
    # Polite short filler
    "thank you", "thanks", "bye", "bye bye", "goodbye",
    "silence",
    # Whisper-specific artifact tokens observed in the wild
    "gwynple",
}


# Single filler words. When the ENTIRE utterance is only these tokens (in
# any combination) it's almost certainly noise, not intent. Includes short
# polite words that Whisper strings together on silent audio ("thank you
# very much please" → all-filler → filtered).
_WHISPER_FILLER_WORDS: set[str] = {
    "um", "uh", "hmm", "mmm", "ah", "oh", "eh", "er",
    "yeah", "yea", "yep", "nope",
    "ok", "okay",
    # Polite filler run — Whisper's classic silent-audio hallucination.
    "thank", "thanks", "you", "very", "much", "please", "bye",
}


def _is_whisper_noise(text: str) -> bool:
    """True when a Whisper transcript is almost certainly a hallucination.

    Strategy:
      1. Reject empty / whitespace-only inputs.
      2. Reject tiny transcripts (< 3 chars after stripping punctuation).
      3. Reject exact matches against known noise phrases.
      4. Reject utterances made ENTIRELY of filler words.
      5. Reject transcripts where the same short token repeats (whisper
         degrades to "thank thank thank" on silence).
      6. Reject text where > 50% of characters are non-ASCII (Whisper
         mis-transcribes silence into random CJK/Cyrillic runs).
    """
    if not text:
        return True
    stripped = re.sub(r"[^\w\s]", " ", text.strip().lower())
    stripped = re.sub(r"\s+", " ", stripped).strip()
    if len(stripped) < 3:
        return True
    if stripped in _WHISPER_NOISE_PHRASES:
        return True
    tokens = stripped.split()
    if tokens and all(t in _WHISPER_FILLER_WORDS for t in tokens):
        return True
    # 5. Repeated-token noise: "thank thank thank" / "yeah yeah yeah".
    if len(tokens) >= 3 and len(set(tokens)) == 1:
        return True
    # 6. High non-ASCII ratio (silence hallucinated as CJK/Cyrillic).
    # Ignore ASCII whitespace when computing ratio.
    letters = [ch for ch in text if not ch.isspace()]
    if letters:
        non_ascii = sum(1 for ch in letters if ord(ch) > 127)
        if non_ascii / len(letters) > 0.5:
            return True
    return False


UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "uploads", "ai")
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/gif", "image/webp"}
MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8MB upload cap


@router.post("/upload_image")
async def ai_upload_image(
    request: Request,
    image: UploadFile = File(...),
    user_id: str = Form(..., min_length=1, max_length=64),
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Store a chat-uploaded photo on disk and return a short public URL.

    The AI chat endpoint caps message length at 5KB, so data URLs are
    too big to inline. The frontend posts the raw file here, gets back
    a tidy URL like /uploads/ai/<uuid>.jpg, then sends that URL to the
    chat as 'image: <url>' for the AI to attach to the listing.
    """
    _enforce_rate_limit(request)
    uid = _parse_user_id(user_id)
    await _require_owner(credentials, uid)

    base_type = (image.content_type or "").split(";")[0].strip().lower()
    if base_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(400, f"Unsupported image type: {image.content_type or 'unknown'}")

    data = await image.read()
    if len(data) == 0:
        raise HTTPException(400, "Empty image file")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(400, f"Image too large (max {MAX_IMAGE_BYTES // (1024 * 1024)}MB)")

    # Defense-in-depth: don't trust the client-declared Content-Type. Sniff
    # the first few bytes and confirm they match a known image format. This
    # blocks an attacker from uploading a script/HTML file labelled
    # 'image/jpeg' that could be served back and executed by a misbehaving
    # browser or downstream consumer.
    def _sniff_image_type(buf: bytes) -> str | None:
        if len(buf) < 12:
            return None
        if buf[:3] == b"\xff\xd8\xff":
            return "image/jpeg"
        if buf[:8] == b"\x89PNG\r\n\x1a\n":
            return "image/png"
        if buf[:6] in (b"GIF87a", b"GIF89a"):
            return "image/gif"
        if buf[:4] == b"RIFF" and buf[8:12] == b"WEBP":
            return "image/webp"
        return None

    sniffed = _sniff_image_type(data)
    expected = "image/jpeg" if base_type == "image/jpg" else base_type
    if sniffed is None or sniffed != expected:
        raise HTTPException(400, "File contents do not match a supported image format.")

    import uuid as _uuid
    ext = {"image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png", "image/gif": ".gif", "image/webp": ".webp"}[base_type]
    filename = f"{_uuid.uuid4().hex}{ext}"
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    full_path = os.path.join(UPLOAD_DIR, filename)
    try:
        with open(full_path, "wb") as fh:
            fh.write(data)
    except OSError as exc:
        logger.exception("Failed to write upload")
        raise HTTPException(500, f"Could not save image: {exc}") from exc

    url = f"/uploads/ai/{filename}"
    return {"url": url, "size": len(data), "content_type": base_type}


@router.post("/voice", response_model=AIChatResponse)
async def ai_voice(
    request: Request,
    audio: UploadFile = File(...),
    user_id: str = Form(..., min_length=1, max_length=64),
    include_audio: bool = Form(default=True),
    tone: Optional[str] = Form(default=None),
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    _enforce_rate_limit(request)
    uid = _parse_user_id(user_id)
    # Voice is a real-user only surface (recording audio requires an
    # active session). Validate the user_id looks like a UUID BEFORE
    # running the ownership check so obviously malformed inputs return
    # 400 (bad request) instead of 403 (forbidden).
    _require_uuid(uid)
    await _require_owner(credentials, uid)

    allowed = {
        "audio/webm", "audio/wav", "audio/mpeg", "audio/mp4",
        "audio/ogg", "audio/x-m4a", "audio/mp3",
    }
    base_type = (audio.content_type or "").split(";")[0].strip().lower()
    if base_type and base_type not in allowed:
        raise HTTPException(400, f"Unsupported audio type: {audio.content_type}")

    audio_bytes = await audio.read()
    if len(audio_bytes) > 25 * 1024 * 1024:
        raise HTTPException(400, "Audio file too large (max 25MB)")
    if len(audio_bytes) == 0:
        raise HTTPException(400, "Empty audio file")

    lang = resolve_lang(request)
    try:
        transcript = await conversation_engine.transcribe_audio(
            audio_bytes=audio_bytes,
            filename=audio.filename or "audio.webm",
        )
        if _is_whisper_noise(transcript):
            raise HTTPException(400, "Could not understand the audio. Try again or switch to text.")

        result = await conversation_engine.chat(
            user_id=uid,
            message=transcript,
            include_audio=include_audio,
            tone=tone,
        )
        result["transcript"] = transcript
        return result
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise AITimeout(lang) from exc
    except httpx.HTTPError as exc:
        raise AIUpstreamError(lang) from exc
    except RuntimeError as exc:
        raise AIServiceUnavailable(lang) from exc
    except Exception as exc:
        logger.exception("Voice processing error")
        raise AIError(lang) from exc


@router.post("/tts")
async def ai_tts(
    body: TTSRequest,
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Generate TTS audio and return it as raw ``audio/mpeg`` bytes.

    The frontend (`utils/openaiVoice.js`) consumes the response as a
    Blob and pipes it into an ``<audio>`` element; returning raw bytes
    is what enables that path to work.

    Authentication is required in production so anonymous callers
    can't burn our OpenAI TTS budget. The audit at line ~600 flagged
    this as a high-severity cost-abuse vector.
    """
    from fastapi.responses import Response
    _enforce_rate_limit(request)
    await _require_authenticated(credentials)
    lang = resolve_lang(request, body.text)
    try:
        audio_bytes = await conversation_engine.generate_speech(body.text, lang=body.lang)
        return Response(content=audio_bytes, media_type="audio/mpeg")
    except httpx.TimeoutException as exc:
        raise AITimeout(lang) from exc
    except httpx.HTTPStatusError as exc:
        # Upstream 5xx from OpenAI is a transient outage we can retry;
        # surface it as 503 model_unavailable so the frontend backs off.
        raise AIServiceUnavailable(lang) from exc
    except httpx.HTTPError as exc:
        raise AIUpstreamError(lang) from exc
    except RuntimeError as exc:
        raise AIServiceUnavailable(lang) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("TTS error")
        raise AIError(lang) from exc


@router.post("/transcribe")
async def ai_transcribe(
    request: Request,
    audio: UploadFile = File(...),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Transcribe audio via Whisper and return ``{transcript, filtered}``.

    Unlike ``/api/ai/voice`` this endpoint does *not* run a chat turn or
    require a ``user_id`` — it is a pure STT service used by non-chat
    features (e.g. voice search on the map). Whisper hallucinations
    (see :func:`_is_whisper_noise`) return ``filtered: True`` with an
    empty transcript so callers can distinguish silence from real speech.

    Requires an authenticated caller so anonymous requests can't burn
    our Whisper quota.
    """
    _enforce_rate_limit(request)
    await _require_authenticated(credentials)

    allowed_audio = {
        "audio/webm", "audio/wav", "audio/mpeg", "audio/mp4",
        "audio/ogg", "audio/x-m4a", "audio/mp3",
    }
    base_type = (audio.content_type or "").split(";")[0].strip().lower()
    if base_type and base_type not in allowed_audio:
        raise HTTPException(400, f"Unsupported audio type: {audio.content_type}")

    audio_bytes = await audio.read()
    if len(audio_bytes) > 25 * 1024 * 1024:
        raise HTTPException(400, "Audio file too large (max 25MB)")
    if len(audio_bytes) == 0:
        raise HTTPException(400, "Empty audio file")

    lang = resolve_lang(request)
    try:
        transcript = await conversation_engine.transcribe_audio(
            audio_bytes=audio_bytes,
            filename=audio.filename or "audio.webm",
        )
        transcript = (transcript or "").strip()
        if _is_whisper_noise(transcript):
            return {"transcript": "", "filtered": True}
        return {"transcript": transcript, "filtered": False}
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise AITimeout(lang) from exc
    except httpx.HTTPError as exc:
        raise AIUpstreamError(lang) from exc
    except RuntimeError as exc:
        raise AIServiceUnavailable(lang) from exc
    except Exception as exc:
        logger.exception("Transcribe error")
        raise AIError(lang) from exc


@router.post("/feedback")
async def ai_feedback(
    body: AIFeedbackRequest,
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    _enforce_rate_limit(request)
    uid = _parse_user_id(body.user_id)
    await _require_owner(credentials, uid)

    try:
        conv_id = int(body.conversation_id)
    except (ValueError, TypeError):
        raise HTTPException(400, "conversation_id must be an integer")

    def _save():
        from backend.app import SessionLocal
        from backend.ai.models import AIFeedback
        db = SessionLocal()
        try:
            row = AIFeedback(
                conversation_id=conv_id,
                user_id=uid,
                rating=body.rating,
                comment=body.comment,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return row.id
        except Exception as exc:
            db.rollback()
            logger.error("Feedback save failed: %s", exc)
            return None
        finally:
            db.close()

    feedback_id = await asyncio.get_event_loop().run_in_executor(None, _save)
    if feedback_id is None:
        raise HTTPException(500, "Failed to save feedback")
    return {"success": True, "feedback_id": feedback_id}


# ---------------------------------------------------------------------------
# Agentic confirmation gate
# ---------------------------------------------------------------------------

class AIConfirmRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    confirmed: bool


@router.post("/confirm", response_model=AIChatResponse)
async def ai_confirm(
    body: AIConfirmRequest,
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Execute or cancel a pending destructive action.

    When the AI engine intercepts a destructive tool call (claim_listing,
    post_food_listing, etc.) it pauses execution and returns
    ``requires_confirmation: True`` in the chat response.  The frontend
    shows a Confirm / Cancel dialog and POSTs here.

    ``confirmed=true``  → executes the stored tool call and returns a
                          chat-style response with the result.
    ``confirmed=false`` → discards the pending action and returns a
                          "Cancelled" response.
    """
    _enforce_rate_limit(request)
    uid = _parse_user_id(body.user_id)
    await _require_owner(credentials, uid)
    lang = resolve_lang(request)

    pending = conversation_engine.get_pending_confirmation(uid)
    if not pending:
        raise HTTPException(
            400,
            "No pending confirmation found. It may have expired (5-minute window). "
            "Please repeat your original request.",
        )

    # Check expiry (5-minute window)
    try:
        expiry = datetime.fromisoformat(pending["expires_at"])
        if _utcnow() > expiry:
            conversation_engine.cancel_pending_confirmation(uid)
            raise HTTPException(
                400,
                "Confirmation expired. Please repeat your original request.",
            )
    except (KeyError, ValueError):
        pass

    if not body.confirmed:
        conversation_engine.cancel_pending_confirmation(uid)
        cancelled_text = await conversation_engine._agentic_reply_from_context(
            lang=lang,
            tone="warm",
            user_message="Cancel",
            situation="User cancelled a pending action via the confirm button.",
            facts={"pending_action": pending.get("summary"), "cancelled": True},
        )
        await conversation_engine.store_message(
            uid, "assistant", cancelled_text, metadata={"lang": lang}
        )
        return {
            "text": cancelled_text,
            "audio_url": None,
            "user_id": body.user_id,
            "lang": lang,
            "conversation_id": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actions": [{"tool": pending.get("tool"), "ok": False, "summary": "Cancelled by user"}],
            "suggestions": [],
            "requires_confirmation": False,
            "pending_action": None,
        }

    # Execute the confirmed action (enrich args, set confirmed flags, etc.)
    confirm_msg = "Sí, confirmar" if lang == "es" else "Yes, confirm"
    return await conversation_engine._execute_pending_confirmation(
        uid, pending, confirm_msg, lang, include_audio=False, tone="warm",
    )


# ---------------------------------------------------------------------------
# Goal history
# ---------------------------------------------------------------------------

@router.get("/goals/{user_id}")
async def get_user_goals(
    user_id: str,
    request: Request,
    limit: int = 20,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Return the authenticated user's completed AI-agent goals."""
    _enforce_rate_limit(request)
    uid = _parse_user_id(user_id)
    await _require_owner(credentials, uid)
    lang = resolve_lang(request)

    if limit < 1 or limit > 50:
        raise HTTPException(400, "limit must be between 1 and 50")

    def _fetch() -> list[dict]:
        from backend.app import SessionLocal
        from backend.ai.models import AIGoal
        db = SessionLocal()
        try:
            goals = (
                db.query(AIGoal)
                .filter(AIGoal.user_id == uid)
                .order_by(AIGoal.created_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": g.id,
                    "description": g.description,
                    "status": g.status,
                    "created_at": g.created_at.isoformat() if g.created_at else None,
                    "completed_at": g.completed_at.isoformat() if g.completed_at else None,
                }
                for g in goals
            ]
        except Exception as exc:
            logger.error("Get goals failed: %s", exc)
            return []
        finally:
            db.close()

    try:
        goals = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        return {"user_id": user_id, "goals": goals, "count": len(goals)}
    except Exception as exc:
        logger.exception("Goals fetch error")
        raise AIError(lang) from exc


# ---------------------------------------------------------------------------
# Background reminder job
# ---------------------------------------------------------------------------

async def _send_sms_via_main_app(to_phone: str, message: str) -> bool:
    """Send SMS using the main app's Twilio service (sms_service.py)."""
    try:
        from backend.sms_service import send_sms_real  # type: ignore
    except ImportError:
        logger.warning("sms_service not available — skipping SMS to %s", to_phone)
        return False
    try:
        # run sync function in thread pool
        result = await asyncio.get_event_loop().run_in_executor(
            None, send_sms_real, to_phone, message
        )
        return bool(result)
    except Exception as exc:
        logger.error("SMS send failed: %s", exc)
        return False


async def process_pending_reminders() -> int:
    """Find due AIReminders, look up user phone, send SMS, mark sent."""
    from backend.app import SessionLocal
    from backend.models import User
    from backend.ai.models import AIReminder

    def _fetch_and_mark() -> list[dict]:
        db = SessionLocal()
        try:
            now = _utcnow()
            due = (
                db.query(AIReminder)
                .filter(AIReminder.sent == False)  # noqa: E712
                .filter(AIReminder.trigger_time <= now)
                .order_by(AIReminder.trigger_time.asc())
                .limit(50)
                .all()
            )
            tasks = []
            for r in due:
                user = db.query(User).filter(User.id == r.user_id).first()
                tasks.append({
                    "id": r.id,
                    "user_id": r.user_id,
                    "phone": user.phone if user else None,
                    "sms_consent": user.sms_consent_given if user else False,
                    "message": r.message,
                    "reminder_type": r.reminder_type,
                })
                r.sent = True
                r.sent_at = now
            db.commit()
            return tasks
        except Exception as exc:
            logger.error("Reminder fetch failed: %s", exc)
            db.rollback()
            return []
        finally:
            db.close()

    tasks = await asyncio.get_event_loop().run_in_executor(None, _fetch_and_mark)

    prefix_map = {
        "pickup": "🍎 Pickup Reminder",
        "listing_expiry": "⏰ Listing Expiry",
        "distribution_event": "📍 Event Reminder",
        "general": "📋 Reminder",
    }
    sent = 0
    for t in tasks:
        if t["phone"] and t["sms_consent"]:
            prefix = prefix_map.get(t["reminder_type"], "📋 Reminder")
            body = f"[DoGoods] {prefix}: {t['message']}"
            if await _send_sms_via_main_app(t["phone"], body):
                sent += 1
        else:
            logger.info("Skipping SMS for reminder %s (no phone or no consent)", t["id"])

    if tasks:
        logger.info("Processed %d reminder(s), sent %d SMS", len(tasks), sent)
    return len(tasks)


async def reminder_loop() -> None:
    """Background loop with exponential backoff on failures."""
    logger.info("AI reminder loop started (interval=%ds)", REMINDER_CHECK_INTERVAL)
    consecutive_failures = 0
    while True:
        try:
            await process_pending_reminders()
            consecutive_failures = 0
        except Exception as exc:
            consecutive_failures += 1
            logger.error("Reminder loop error (#%d): %s", consecutive_failures, exc)

        if consecutive_failures > 0:
            backoff = min(REMINDER_CHECK_INTERVAL * (2 ** consecutive_failures), 3600)
            await asyncio.sleep(backoff)
        else:
            await asyncio.sleep(REMINDER_CHECK_INTERVAL)


# ---------------------------------------------------------------------------
# Startup/shutdown hooks the main app can call
# ---------------------------------------------------------------------------

_background_task: asyncio.Task | None = None
_broadcast_task: asyncio.Task | None = None


async def start_background_jobs() -> None:
    global _background_task, _broadcast_task
    if _background_task is None or _background_task.done():
        _background_task = asyncio.create_task(reminder_loop())
        logger.info("AI reminder loop scheduled")
    if _broadcast_task is None or _broadcast_task.done():
        try:
            from backend.ai.notifications import broadcast_loop
            _broadcast_task = asyncio.create_task(broadcast_loop())
            logger.info("AI broadcast loop scheduled")
        except Exception as exc:
            logger.error("Failed to start broadcast loop: %s", exc)


async def stop_background_jobs() -> None:
    global _background_task, _broadcast_task
    for name, task in (("reminder", _background_task), ("broadcast", _broadcast_task)):
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            logger.info("AI %s loop stopped", name)
    _background_task = None
    _broadcast_task = None
    await close_http_client()


# ---------------------------------------------------------------------------
# Admin-facing broadcast endpoints
# ---------------------------------------------------------------------------

def _require_admin(credentials: HTTPAuthorizationCredentials | None) -> int:
    """Return the admin user_id or raise 401/403."""
    if credentials is None:
        raise HTTPException(401, "Authentication required")
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(401, "Invalid token") from exc
    sub = payload.get("sub")
    try:
        uid = int(sub)
    except (TypeError, ValueError) as exc:
        raise HTTPException(401, "Invalid token") from exc

    def _check():
        from backend.app import SessionLocal
        from backend.models import User, UserRole
        db = SessionLocal()
        try:
            u = db.query(User).filter(User.id == uid).first()
            return bool(u and u.role == UserRole.ADMIN)
        finally:
            db.close()

    if not _check():
        raise HTTPException(403, "Admin role required")
    return uid


def _broadcast_to_dict(b) -> dict:
    return {
        "id": b.id,
        "food_resource_id": b.food_resource_id,
        "user_id": b.user_id,
        "channel": b.channel,
        "language": b.language,
        "message": b.message,
        "status": b.status,
        "batch_id": b.batch_id,
        "created_at": b.created_at.isoformat() if b.created_at else None,
        "approved_by": b.approved_by,
        "approved_at": b.approved_at.isoformat() if b.approved_at else None,
        "sent_at": b.sent_at.isoformat() if b.sent_at else None,
        "error": b.error,
    }


@router.get("/broadcasts")
async def list_broadcasts(
    request: Request,
    response: Response,
    status: str = "pending",
    limit: int = 100,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Admin: list broadcasts by status."""
    _enforce_rate_limit(request)
    _require_admin(credentials)
    if limit < 1 or limit > 500:
        raise HTTPException(400, "limit must be 1..500")
    # This is admin-only mutable state. Never let any intermediate cache
    # serve a stale row order — the AI Broadcasts panel polls this endpoint
    # immediately after approve/reject, and a cached response would make
    # rows appear "stuck" in Pending.
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"

    def _fetch():
        from backend.app import SessionLocal
        from backend.ai.models import AIBroadcast
        db = SessionLocal()
        try:
            q = db.query(AIBroadcast)
            if status and status != "all":
                q = q.filter(AIBroadcast.status == status)
            rows = q.order_by(AIBroadcast.created_at.desc()).limit(limit).all()
            return [_broadcast_to_dict(r) for r in rows]
        finally:
            db.close()

    data = await asyncio.get_event_loop().run_in_executor(None, _fetch)
    return {"status": status, "count": len(data), "broadcasts": data}


class BroadcastEditRequest(BaseModel):
    message: Optional[str] = Field(default=None, max_length=1000)
    channel: Optional[str] = None  # 'sms' | 'chat' | 'both'


@router.post("/broadcasts/{broadcast_id}/approve")
async def approve_broadcast(
    broadcast_id: int,
    body: BroadcastEditRequest,
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Admin: approve (optionally edit) and send a pending broadcast."""
    _enforce_rate_limit(request)
    admin_uid = _require_admin(credentials)

    def _approve():
        from backend.app import SessionLocal
        from backend.ai.models import AIBroadcast
        db = SessionLocal()
        try:
            b = db.query(AIBroadcast).filter(AIBroadcast.id == broadcast_id).first()
            if not b:
                return "not_found"
            if b.status not in ("pending", "failed"):
                return f"bad_status:{b.status}"
            if body.message:
                b.message = body.message.strip()
            if body.channel in ("sms", "chat", "both"):
                b.channel = body.channel
            b.status = "approved"
            b.approved_by = admin_uid
            b.approved_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.commit()
            return "ok"
        finally:
            db.close()

    outcome = await asyncio.get_event_loop().run_in_executor(None, _approve)
    if outcome == "not_found":
        raise HTTPException(404, "broadcast not found")
    if outcome.startswith("bad_status"):
        raise HTTPException(409, f"cannot approve: {outcome}")

    # Send now
    from backend.ai.notifications import send_broadcast
    result = await send_broadcast(broadcast_id)
    return {"id": broadcast_id, "approved": True, "delivery": result}


@router.post("/broadcasts/{broadcast_id}/reject")
async def reject_broadcast(
    broadcast_id: int,
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Admin: reject a pending broadcast (will not be sent)."""
    _enforce_rate_limit(request)
    admin_uid = _require_admin(credentials)

    def _reject():
        from backend.app import SessionLocal
        from backend.ai.models import AIBroadcast
        db = SessionLocal()
        try:
            b = db.query(AIBroadcast).filter(AIBroadcast.id == broadcast_id).first()
            if not b:
                return "not_found"
            if b.status != "pending":
                return f"bad_status:{b.status}"
            b.status = "rejected"
            b.approved_by = admin_uid
            b.approved_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.commit()
            return "ok"
        finally:
            db.close()

    outcome = await asyncio.get_event_loop().run_in_executor(None, _reject)
    if outcome == "not_found":
        raise HTTPException(404, "broadcast not found")
    if outcome.startswith("bad_status"):
        raise HTTPException(409, f"cannot reject: {outcome}")
    return {"id": broadcast_id, "rejected": True}


@router.post("/broadcasts/approve_batch")
async def approve_batch(
    request: Request,
    batch_id: Optional[str] = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Admin: approve + send every pending broadcast (optionally by batch)."""
    _enforce_rate_limit(request)
    _require_admin(credentials)
    from backend.ai.notifications import auto_send_pending
    sent = await auto_send_pending(batch_id=batch_id)
    return {"sent": sent, "batch_id": batch_id}


@router.post("/broadcasts/run_now")
async def run_broadcast_job(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Admin: trigger the hourly scan-and-draft job on-demand."""
    _enforce_rate_limit(request)
    _require_admin(credentials)
    from backend.ai.notifications import scan_and_draft_new_listings
    stats = await scan_and_draft_new_listings()
    return {"ok": True, "stats": stats}

