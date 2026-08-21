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
  POST /api/ai/bulk-listings   - Create listings from CSV / photo confirm UI
  POST /api/ai/enrich-listings - AI gap-fill on parsed listing drafts
  POST /api/ai/vision-listing  - Photo → draft listing via vision model

Authentication: uses the main app's JWT (Bearer token). If the token's "sub"
matches the request body's user_id, the call is authorised.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timezone

from typing import Optional, List, Union

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
    AIInvalidInput,
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
# Fail closed: unset or blank → require auth. Only explicit falsey values disable.
_ai_auth_raw = os.getenv("AI_REQUIRE_AUTH")
if _ai_auth_raw is None or str(_ai_auth_raw).strip() == "":
    AI_REQUIRE_AUTH = True
else:
    AI_REQUIRE_AUTH = str(_ai_auth_raw).strip().lower() in {"1", "true", "yes", "on"}

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
    accessibility_profile: Optional[dict] = None
    guide_state: Optional[dict] = None


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
    # Up to 6 short tappable quick replies under the assistant bubble.
    # Strings or {label, message[, kind, action, target]} objects — never
    # padded with generic menu chips when nothing contextual matches.
    suggestions: List[Union[str, dict]] = []
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


# ---- CSV / photo bulk listing helpers (chat attach flow) --------------------
_VALID_FOOD_CATEGORIES = {
    "produce", "bakery", "dairy", "pantry", "meat", "prepared", "other",
}
_DEFAULT_FOOD_CATEGORY = "other"
_MAX_BULK_LISTINGS = 100

_ENRICH_LISTINGS_PROMPT = (
    "You help donors clean up bulk food-listing rows before they are published. "
    "For each row, FILL ONLY MISSING OR EMPTY OPTIONAL FIELDS. NEVER overwrite a "
    "field the user already provided.\n"
    "Allowed optional fields you may add: description (<=200 chars, neutral tone), "
    "dietary_tags (lowercase strings like 'vegetarian','vegan','gluten-free','halal','kosher'), "
    "allergens (lowercase strings like 'nuts','dairy','gluten','eggs','soy','shellfish'), "
    "expiry_date (ISO 'YYYY-MM-DD' in the FUTURE only — never invent a past date).\n"
    "You MAY also correct an obviously-wrong category to one of "
    "['produce','bakery','dairy','pantry','meat','prepared','other'] — but ONLY if "
    "the existing value is missing or 'other'. Never invent allergens you cannot "
    "infer from the title/description.\n"
    "Output STRICT JSON: {\"rows\":[{...same fields..., \"_filled\":[\"field1\",...]}], "
    "\"summary\":\"short human sentence in the requested language\"}.\n"
    "Echo every input row, in order. Keep the user's title, quantity, and unit "
    "EXACTLY as given. Do NOT add image_url."
)

_VISION_LISTING_PROMPT = (
    "You are a food-donation listing assistant. Look at the attached photo and "
    "extract a single food-listing draft as STRICT JSON with EXACTLY these keys:\n"
    "{\n"
    "  \"title\": string (<=80 chars, plain product name),\n"
    "  \"description\": string (<=240 chars, what you see + condition),\n"
    "  \"category\": one of ['produce','bakery','dairy','pantry','meat','prepared','other'],\n"
    "  \"quantity\": number (your best estimate, >0),\n"
    "  \"unit\": string (e.g. 'items','kg','lbs','loaves','servings','boxes'),\n"
    "  \"dietary_tags\": string[] (e.g. ['vegetarian','vegan','gluten-free'] or []),\n"
    "  \"allergens\": string[] (e.g. ['nuts','dairy','gluten'] or []),\n"
    "  \"confidence\": number 0..1\n"
    "}\n"
    "Rules: if the image is not food, return confidence=0 and title=''. "
    "Never invent allergens you cannot see. Output JSON only — no prose."
)


class BulkListingItem(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    quantity: float = Field(gt=0, le=100000)
    unit: str = Field(min_length=1, max_length=40)
    category: str = Field(min_length=1, max_length=40)
    description: Optional[str] = Field(default=None, max_length=2000)
    expiry_date: Optional[str] = Field(default=None, max_length=40)
    location: Optional[str] = Field(default=None, max_length=200)
    dietary_tags: Optional[List[str]] = None
    allergens: Optional[List[str]] = None
    image_url: Optional[str] = Field(default=None, max_length=2000)
    # Preview community picker — MUST be accepted or every photo/CSV listing
    # silently inherits the donor profile community (often Do Good Warehouse).
    community_id: Optional[Union[int, str]] = Field(default=None)
    community_name: Optional[str] = Field(default=None, max_length=200)


class BulkListingsRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    listings: List[BulkListingItem] = Field(min_length=1, max_length=_MAX_BULK_LISTINGS)


class EnrichListingsRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    rows: List[BulkListingItem] = Field(min_length=1, max_length=_MAX_BULK_LISTINGS)
    language: Optional[str] = Field(default="en", max_length=8)


def _normalize_listing_row(
    item: BulkListingItem,
    user_id: str,
    donor: dict | None = None,
    status: str = "approved",
) -> dict:
    """Map a validated BulkListingItem into a Supabase food_listings row."""
    from datetime import date, timedelta

    from backend.ai_engine import apply_donor_defaults_to_listing

    category = (item.category or "").strip().lower()
    if category not in _VALID_FOOD_CATEGORIES:
        category = _DEFAULT_FOOD_CATEGORY
    row: dict = {
        "user_id": user_id,
        "title": item.title.strip()[:200],
        "quantity": float(item.quantity),
        "unit": item.unit.strip()[:40],
        "category": category,
        "listing_type": "donation",
        "status": status if status in {"approved", "pending"} else "approved",
    }
    if item.description:
        row["description"] = item.description.strip()[:2000]

    # Find Food hides expiry_date < today — never persist a past expiry from
    # stale CSV templates / AI gap-fill, or most of a bulk import vanishes.
    _CATEGORY_EXPIRY_DAYS = {
        "produce": 5,
        "bakery": 3,
        "dairy": 7,
        "meat": 3,
        "prepared": 2,
        "pantry": 180,
        "other": 14,
    }
    today = date.today()
    expiry_raw = (item.expiry_date or "").strip()[:40]
    expiry_ok = False
    if expiry_raw:
        try:
            parsed = date.fromisoformat(expiry_raw[:10])
            if parsed >= today:
                row["expiry_date"] = parsed.isoformat()
                expiry_ok = True
        except ValueError:
            expiry_ok = False
    if not expiry_ok:
        days = _CATEGORY_EXPIRY_DAYS.get(category, 14)
        row["expiry_date"] = (today + timedelta(days=days)).isoformat()

    if item.location:
        row["location"] = item.location.strip()[:200]
    if item.dietary_tags:
        row["dietary_tags"] = [
            str(t).strip()[:40] for t in item.dietary_tags if str(t).strip()
        ][:20]
    if item.allergens:
        row["allergens"] = [
            str(t).strip()[:40] for t in item.allergens if str(t).strip()
        ][:20]
    if item.image_url:
        row["image_url"] = item.image_url.strip()[:2000]

    # Picker/community from the chat preview wins over the donor profile default.
    # Previously BulkListingItem dropped community_id, so every photo/CSV listing
    # silently inherited users.community_id (often Do Good Warehouse = 1).
    cid = item.community_id
    pending_name = None
    if cid is not None and str(cid).strip() not in ("", "null", "None"):
        cid_s = str(cid).strip()
        if cid_s.isdigit():
            try:
                row["community_id"] = int(cid_s)
            except (TypeError, ValueError):
                pass
        else:
            # Non-numeric community_id is treated as a school name.
            pending_name = cid_s[:200]
    if not row.get("community_id") and item.community_name and str(item.community_name).strip():
        pending_name = str(item.community_name).strip()[:200]
    if pending_name:
        row["_community_name_pending"] = pending_name

    # When a community_name still needs resolving, do not stamp the donor's
    # community_id yet — that would block name resolution and leak warehouse
    # food to every school.
    if donor and row.get("_community_name_pending") and not row.get("community_id"):
        donor_sans_community = {k: v for k, v in donor.items() if k != "community_id"}
        return apply_donor_defaults_to_listing(row, donor_sans_community)
    return apply_donor_defaults_to_listing(row, donor)


def _address_worth_geocoding(addr: str) -> bool:
    """Skip vague template addresses that Mapbox pins in the wrong country."""
    s = (addr or "").strip()
    if len(s) < 12:
        return False
    # Need at least one digit (street number) to be worth a dedicated geocode.
    if not any(ch.isdigit() for ch in s):
        return False
    # Bare "123 Main St" style stubs geocode unpredictably — require a comma
    # (city/state) or a recognizable region token.
    lower = s.lower()
    if "," in s:
        return True
    return any(
        tok in lower
        for tok in (
            " ca", "california", "alameda", "oakland", "berkeley",
            "san francisco", "usa", "united states",
        )
    )


def _row_for_enrich_prompt(item: BulkListingItem) -> dict:
    """Compact dict for the model — drops empty fields so it knows what to fill."""
    out: dict = {
        "title": item.title,
        "quantity": item.quantity,
        "unit": item.unit,
        "category": item.category,
    }
    if item.description:
        out["description"] = item.description
    if item.expiry_date:
        out["expiry_date"] = item.expiry_date
    if item.location:
        out["location"] = item.location
    if item.dietary_tags:
        out["dietary_tags"] = list(item.dietary_tags)
    if item.allergens:
        out["allergens"] = list(item.allergens)
    return out


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


@router.post("/enrich-listings")
async def ai_enrich_listings(
    body: EnrichListingsRequest,
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    Fill missing optional fields on parsed listing rows before bulk insert.
    Never overwrites user-provided values. Falls back to originals if AI is down.
    """
    import json as _json

    from backend.ai.ai_engine import (
        FOLLOWUP_MODEL,
        OPENAI_API_KEY,
        OPENAI_BASE_URL,
        _get_http_client,
    )

    _enforce_rate_limit(request)
    uid = _parse_user_id(body.user_id)
    await _require_owner(credentials, uid)

    originals = [item.model_dump() for item in body.rows]
    fallback = {
        "rows": originals,
        "summary": "AI gap-fill unavailable — rows returned unchanged.",
        "filled": [],
    }
    if not OPENAI_API_KEY:
        return fallback

    compact = [_row_for_enrich_prompt(item) for item in body.rows]
    language = (body.language or "en").lower()[:2]
    user_msg = (
        f"Language for summary: {language}.\n"
        f"Rows to review (JSON array):\n{_json.dumps(compact, ensure_ascii=False)}"
    )
    client = _get_http_client(45)
    payload = {
        "model": FOLLOWUP_MODEL,
        "messages": [
            {"role": "system", "content": _ENRICH_LISTINGS_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.2,
        "max_tokens": 2200,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        resp = await client.post(
            f"{OPENAI_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.exception("enrich-listings OpenAI call failed: %s", exc)
        return fallback

    content_str = (data.get("choices") or [{}])[0].get("message", {}).get("content") or "{}"
    try:
        parsed = _json.loads(content_str)
        ai_rows = parsed.get("rows") or []
        summary = str(parsed.get("summary") or "").strip()[:400]
        if not isinstance(ai_rows, list):
            ai_rows = []
    except Exception:
        ai_rows = []
        summary = ""

    merged: List[dict] = []
    filled_log: List[dict] = []
    for idx, original in enumerate(originals):
        ai_row = (
            ai_rows[idx]
            if idx < len(ai_rows) and isinstance(ai_rows[idx], dict)
            else {}
        )
        out = dict(original)
        added_fields: List[str] = []

        for f in ("description", "expiry_date", "location"):
            if not out.get(f) and ai_row.get(f):
                val = str(ai_row[f]).strip()
                if val:
                    cap = 2000 if f == "description" else (40 if f == "expiry_date" else 200)
                    out[f] = val[:cap]
                    added_fields.append(f)

        for f in ("dietary_tags", "allergens"):
            existing = out.get(f) or []
            if not existing or len(existing) == 0:
                ai_val = ai_row.get(f) or []
                if isinstance(ai_val, list) and ai_val:
                    clean = [
                        str(t).strip().lower()[:40] for t in ai_val if str(t).strip()
                    ][:10]
                    if clean:
                        out[f] = clean
                        added_fields.append(f)

        cur_cat = (out.get("category") or "").strip().lower()
        ai_cat = (ai_row.get("category") or "").strip().lower()
        if (
            ai_cat in _VALID_FOOD_CATEGORIES
            and cur_cat in ("", "other")
            and ai_cat != cur_cat
        ):
            out["category"] = ai_cat
            added_fields.append("category")

        merged.append(out)
        if added_fields:
            filled_log.append({"index": idx, "fields": added_fields})

    if not summary:
        n_rows = len(filled_log)
        if language == "es":
            summary = (
                f"Rellené {n_rows} fila(s) con datos faltantes."
                if n_rows
                else "No encontré huecos que rellenar."
            )
        else:
            summary = (
                f"Filled gaps on {n_rows} row(s)."
                if n_rows
                else "No gaps to fill — your rows look complete."
            )

    return {"rows": merged, "summary": summary, "filled": filled_log}


@router.post("/bulk-listings")
async def ai_bulk_listings(
    body: BulkListingsRequest,
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    Create one or more food_listings rows from a vetted JSON payload
    (chat UI photo + CSV upload confirm flow).

    Returns: { created, failed, ids, errors }
    """
    from backend.ai_engine import fetch_donor_listing_defaults, supabase_post
    from backend.tools import _forward_geocode, _resolve_create_listing_status

    _enforce_rate_limit(request)
    uid = _parse_user_id(body.user_id)
    await _require_owner(credentials, uid)

    donor = await fetch_donor_listing_defaults(uid)
    listing_status = await _resolve_create_listing_status()
    geocode_cache: dict[str, tuple | None] = {}
    created_ids: List[str] = []
    created_statuses: List[str] = []
    errors: List[dict] = []

    for idx, item in enumerate(body.listings):
        try:
            addr = str(item.location or "").strip()
            pre_coords = None
            # Only geocode solid pickup addresses. Vague stubs like
            # "123 Main St" get wrong-country pins and hide nearby listings.
            if addr and _address_worth_geocoding(addr):
                if addr not in geocode_cache:
                    geocode_cache[addr] = await _forward_geocode(addr)
                pre_coords = geocode_cache[addr]
            row = _normalize_listing_row(item, uid, donor=donor, status=listing_status)
            pending_name = row.pop("_community_name_pending", None)
            if pending_name and not row.get("community_id"):
                try:
                    from backend.tools import _resolve_community
                    cid, _cname = await _resolve_community(pending_name, None)
                    if cid:
                        row["community_id"] = int(cid)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("bulk community_name resolve failed: %s", exc)
            # After name resolve, fill donor community only if still unset.
            if row.get("community_id") is None and donor and donor.get("community_id") is not None:
                try:
                    row["community_id"] = int(donor["community_id"])
                except (TypeError, ValueError):
                    row["community_id"] = donor["community_id"]
            if pre_coords:
                row["latitude"], row["longitude"] = pre_coords
            elif addr and _address_worth_geocoding(addr):
                # Own solid address but geocode failed — don't keep donor home pin.
                row.pop("latitude", None)
                row.pop("longitude", None)
            elif addr and not _address_worth_geocoding(addr):
                # Drop the stub address so donor profile location/coords apply.
                from backend.ai_engine import apply_donor_defaults_to_listing
                row.pop("location", None)
                row.pop("full_address", None)
                row.pop("latitude", None)
                row.pop("longitude", None)
                row = apply_donor_defaults_to_listing(row, donor)
            result = await supabase_post("food_listings", row)
            if isinstance(result, list) and result:
                rid = result[0].get("id")
                if rid:
                    created_ids.append(str(rid))
                    created_statuses.append(str(result[0].get("status") or listing_status))
                    continue
            errors.append({"index": idx, "error": "no row returned"})
        except Exception as exc:  # noqa: BLE001
            errors.append({"index": idx, "error": str(exc)[:200]})

    if created_ids:
        try:
            from backend.ai.conversation_flow import set_last_bulk_posted_ids
            set_last_bulk_posted_ids(uid, created_ids)
        except Exception:  # noqa: BLE001
            pass

    return {
        "created": len(created_ids),
        "failed": len(errors),
        "ids": created_ids,
        "statuses": created_statuses,
        "awaiting_approval": listing_status == "pending",
        "errors": errors,
    }


@router.post("/vision-listing")
async def ai_vision_listing(
    request: Request,
    user_id: str = Form(..., min_length=1, max_length=128),
    image: UploadFile = File(..., description="Photo of the food item (jpg/png/webp)"),
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    Send a photo to vision and return a draft food_listings row for preview.
    Returns: { draft, confidence, raw }
    """
    import base64 as _b64
    import json as _json

    from backend.ai.ai_engine import (
        FOLLOWUP_MODEL,
        OPENAI_API_KEY,
        OPENAI_BASE_URL,
        _get_http_client,
    )

    _enforce_rate_limit(request)
    uid = _parse_user_id(user_id)
    await _require_owner(credentials, uid)
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")

    raw = await image.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty image upload")
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image too large (max 8 MB)")

    content_type = (image.content_type or "image/jpeg").split(";")[0].strip().lower()
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File is not an image")

    b64 = _b64.b64encode(raw).decode("ascii")
    data_url = f"data:{content_type};base64,{b64}"

    client = _get_http_client(45)
    payload = {
        "model": FOLLOWUP_MODEL,
        "messages": [
            {"role": "system", "content": _VISION_LISTING_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Extract the listing JSON for this photo."},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
        "temperature": 0.2,
        "max_tokens": 500,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        resp = await client.post(
            f"{OPENAI_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
        )
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.exception("vision-listing OpenAI call failed")
        raise HTTPException(status_code=502, detail=f"Vision call failed: {exc}") from exc

    data = resp.json()
    content_str = (data.get("choices") or [{}])[0].get("message", {}).get("content") or "{}"
    try:
        parsed = _json.loads(content_str)
        if not isinstance(parsed, dict):
            parsed = {}
    except Exception:
        parsed = {}

    confidence = parsed.get("confidence")
    try:
        confidence_val = float(confidence) if confidence is not None else 0.0
    except (TypeError, ValueError):
        confidence_val = 0.0

    category = str(parsed.get("category") or "").strip().lower()
    if category not in _VALID_FOOD_CATEGORIES:
        category = _DEFAULT_FOOD_CATEGORY

    quantity_raw = parsed.get("quantity")
    try:
        quantity_val = float(quantity_raw) if quantity_raw is not None else 1.0
        if quantity_val <= 0:
            quantity_val = 1.0
    except (TypeError, ValueError):
        quantity_val = 1.0

    def _str_list(v):
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()][:10]
        return []

    draft = {
        "title": str(parsed.get("title") or "").strip()[:200],
        "description": str(parsed.get("description") or "").strip()[:2000],
        "category": category,
        "quantity": quantity_val,
        "unit": str(parsed.get("unit") or "items").strip()[:40] or "items",
        "dietary_tags": _str_list(parsed.get("dietary_tags")),
        "allergens": _str_list(parsed.get("allergens")),
    }
    # Prefill pickup + community from the donor profile so the preview
    # selector is not empty / forced onto Do Good Warehouse only.
    try:
        from backend.ai_engine import fetch_donor_listing_defaults
        donor = await fetch_donor_listing_defaults(uid)
        if donor.get("address") and not draft.get("location"):
            draft["location"] = str(donor["address"])[:200]
        if donor.get("community_id") is not None:
            draft["community_id"] = str(donor["community_id"])
    except Exception as exc:  # noqa: BLE001
        logger.debug("vision-listing donor defaults skipped: %s", exc)

    return {
        "draft": draft,
        "confidence": confidence_val,
        "raw": content_str[:2000],
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
            accessibility_profile=body.accessibility_profile,
            guide_state=body.guide_state,
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
    # Polite short filler (multi-word only — single "thanks" can be real)
    "thank you", "bye bye", "goodbye",
    "silence",
    # Whisper-specific artifact tokens observed in the wild
    "gwynple",
}


# Single filler words. When the ENTIRE utterance is only these tokens (in
# any combination) it's almost certainly noise, not intent. Do NOT put
# confirmations (yes/ok/sure) here — donors use them constantly in chat.
_WHISPER_FILLER_WORDS: set[str] = {
    "um", "uh", "hmm", "mmm", "ah", "oh", "eh", "er",
    # Polite filler run — Whisper's classic silent-audio hallucination.
    "thank", "thanks", "you", "very", "much", "please", "bye",
}


# Short but legitimate voice intents. Whisper + our old <3-char rule used
# to reject "hi" / "yes" / "ok", which made hands-free confirmations fail.
_VOICE_OK_SHORT: set[str] = {
    "hi", "hey", "hello", "yo",
    "yes", "yeah", "yep", "yup", "sure", "ok", "okay",
    "no", "nope", "nah",
    "help", "food", "share", "claim", "find", "post", "map",
    "hola", "si", "sí", "claro", "vale", "ayuda", "comida",
}


def _is_whisper_noise(text: str) -> bool:
    """True when a Whisper transcript is almost certainly a hallucination.

    Strategy:
      1. Reject empty / whitespace-only inputs.
      2. Allow known short intents (yes / hi / help / …).
      3. Reject tiny transcripts (< 2 chars after stripping punctuation).
      4. Reject exact matches against known noise phrases.
      5. Reject utterances made ENTIRELY of filler words (3+ tokens).
      6. Reject transcripts where the same short token repeats.
      7. Reject text where > 50% of characters are non-ASCII.
    """
    if not text:
        return True
    stripped = re.sub(r"[^\w\s]", " ", text.strip().lower())
    stripped = re.sub(r"\s+", " ", stripped).strip()
    if not stripped:
        return True
    if stripped in _VOICE_OK_SHORT:
        return False
    if len(stripped) < 2:
        return True
    if stripped in _WHISPER_NOISE_PHRASES:
        return True
    tokens = stripped.split()
    # Require several filler-only tokens — "um" alone is noise, but
    # "yes please" / "ok thanks" must reach the chat turn.
    if len(tokens) >= 3 and all(t in _WHISPER_FILLER_WORDS for t in tokens):
        return True
    if len(tokens) == 1 and tokens[0] in _WHISPER_FILLER_WORDS:
        return True
    # 6. Repeated-token noise: "thank thank thank" / "yeah yeah yeah".
    if len(tokens) >= 3 and len(set(tokens)) == 1:
        return True
    # 7. High non-ASCII ratio (silence hallucinated as CJK/Cyrillic).
    letters = [ch for ch in text if not ch.isspace()]
    if letters:
        non_ascii = sum(1 for ch in letters if ord(ch) > 127)
        if non_ascii / len(letters) > 0.5:
            return True
    return False


_ALLOWED_AUDIO_TYPES = {
    "audio/webm", "audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp4",
    "audio/ogg", "audio/x-m4a", "audio/mp3", "audio/aac", "audio/flac",
    # Chrome sometimes labels Opus-in-WebM microphone captures as video/webm
    "video/webm",
}


def _audio_filename_for_whisper(upload_name: str | None, content_type: str | None) -> str:
    """Pick a Whisper-friendly filename whose extension matches the bytes."""
    base_type = (content_type or "").split(";")[0].strip().lower()
    ext_by_type = {
        "audio/webm": ".webm",
        "video/webm": ".webm",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/mpeg": ".mp3",
        "audio/mp3": ".mp3",
        "audio/mp4": ".mp4",
        "audio/m4a": ".m4a",
        "audio/x-m4a": ".m4a",
        "audio/ogg": ".ogg",
        "audio/aac": ".aac",
        "audio/flac": ".flac",
    }
    preferred = ext_by_type.get(base_type)
    name = (upload_name or "").strip() or "audio.webm"
    lower = name.lower()
    if preferred and not lower.endswith(preferred):
        stem = name.rsplit(".", 1)[0] if "." in name else name
        return f"{stem}{preferred}"
    if "." not in name:
        return f"{name}{preferred or '.webm'}"
    return name


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
    accessibility_profile: Optional[str] = Form(default=None),
    guide_state: Optional[str] = Form(default=None),
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

    base_type = (audio.content_type or "").split(";")[0].strip().lower()
    if base_type and base_type not in _ALLOWED_AUDIO_TYPES:
        raise HTTPException(400, f"Unsupported audio type: {audio.content_type}")

    audio_bytes = await audio.read()
    if len(audio_bytes) > 25 * 1024 * 1024:
        raise HTTPException(400, "Audio file too large (max 25MB)")
    if len(audio_bytes) == 0:
        raise HTTPException(400, "Empty audio file")

    a11y_payload = None
    guide_payload = None
    try:
        if accessibility_profile:
            import json as _json
            parsed = _json.loads(accessibility_profile)
            if isinstance(parsed, dict):
                a11y_payload = parsed
    except Exception:
        a11y_payload = None
    try:
        if guide_state:
            import json as _json
            parsed = _json.loads(guide_state)
            if isinstance(parsed, dict):
                guide_payload = parsed
    except Exception:
        guide_payload = None

    lang = resolve_lang(request)
    whisper_name = _audio_filename_for_whisper(audio.filename, audio.content_type)
    try:
        transcript = await conversation_engine.transcribe_audio(
            audio_bytes=audio_bytes,
            filename=whisper_name,
            content_type=base_type or None,
        )
        if _is_whisper_noise(transcript):
            raise AIInvalidInput(lang)

        result = await conversation_engine.chat(
            user_id=uid,
            message=transcript,
            include_audio=include_audio,
            tone=tone,
            accessibility_profile=a11y_payload,
            guide_state=guide_payload,
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

    base_type = (audio.content_type or "").split(";")[0].strip().lower()
    if base_type and base_type not in _ALLOWED_AUDIO_TYPES:
        raise HTTPException(400, f"Unsupported audio type: {audio.content_type}")

    audio_bytes = await audio.read()
    if len(audio_bytes) > 25 * 1024 * 1024:
        raise HTTPException(400, "Audio file too large (max 25MB)")
    if len(audio_bytes) == 0:
        raise HTTPException(400, "Empty audio file")

    lang = resolve_lang(request)
    whisper_name = _audio_filename_for_whisper(audio.filename, audio.content_type)
    try:
        transcript = await conversation_engine.transcribe_audio(
            audio_bytes=audio_bytes,
            filename=whisper_name,
            content_type=base_type or None,
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
        suggestions = await conversation_engine._build_suggestion_chips(
            cancelled_text,
            lang,
            user_message="Cancel",
            user_id=str(uid),
            actions=[],
        )
        return {
            "text": cancelled_text,
            "audio_url": None,
            "user_id": body.user_id,
            "lang": lang,
            "conversation_id": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actions": [{"tool": pending.get("tool"), "ok": False, "summary": "Cancelled by user"}],
            "suggestions": suggestions,
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

