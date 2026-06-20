"""
DoGoods AI Backend — FastAPI Application
==========================================
Provides all AI-related HTTP endpoints:

  POST /api/ai/chat            – Text conversation (returns text + optional audio URL)
  GET  /api/ai/history/{uid}   – Retrieve conversation history
  POST /api/ai/voice           – Transcribe audio (Whisper) then process as chat
  POST /api/ai/tts             – Text-to-speech
  POST /api/ai/feedback        – Submit feedback on AI message
  GET  /health                 – Health check

Background jobs (every 15 min): AI reminders, missed pickup alerts, expired listing cleanup.

Run:
    uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload
"""

import asyncio
import os
import re
import uuid
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from base64 import b64encode
from typing import Any, List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.ai_engine import (
    conversation_engine,
    check_rate_limit,
    check_user_rate_limit,
    _circuit,
    _upstream_metrics,
    supabase_get,
    supabase_post,
    fetch_donor_listing_defaults,
    apply_donor_defaults_to_listing,
    SUPABASE_URL,
    SUPABASE_SERVICE_KEY,
    OPENAI_API_KEY,
    AIError,
    AIErrorCode,
    classify_exception,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3001,http://127.0.0.1:3001,https://dogoods.netlify.app,https://dogoods.store,https://www.dogoods.store"
    ).split(",")
]

# Twilio configuration
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "")
REMINDER_CHECK_INTERVAL = int(os.getenv("REMINDER_CHECK_INTERVAL", "900"))  # 15 min

# Process-level lock so two overlapping scheduler ticks can't both iterate the
# pending-reminders queue at once (the cross-process race is handled by the
# atomic per-reminder claim in _claim_reminder).
_reminder_job_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# Twilio SMS helper
# ---------------------------------------------------------------------------

async def send_sms_via_twilio(to_phone: str, message: str) -> dict:
    """Send an SMS using the Twilio REST API and log it to sms_logs."""
    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER]):
        logger.warning("Twilio not configured — skipping SMS to %s", to_phone)
        return {"sent": False, "error": "Twilio not configured"}

    url = (
        f"https://api.twilio.com/2010-04-01/Accounts/"
        f"{TWILIO_ACCOUNT_SID}/Messages.json"
    )
    auth_str = b64encode(
        f"{TWILIO_ACCOUNT_SID}:{TWILIO_AUTH_TOKEN}".encode()
    ).decode()

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                url,
                data={
                    "To": to_phone,
                    "From": TWILIO_PHONE_NUMBER,
                    "Body": message[:1600],  # Twilio SMS limit
                },
                headers={"Authorization": f"Basic {auth_str}"},
            )
            # Twilio normally returns JSON, but on infra errors it may return HTML.
            # Guard against JSONDecodeError so we always return a structured result.
            try:
                resp_data = resp.json()
            except Exception:
                resp_data = {}

        twilio_sid = resp_data.get("sid", "")
        error_msg = resp_data.get("error_message")
        sent_ok = resp.status_code in (200, 201) and not error_msg

        # Log to sms_logs table
        try:
            await supabase_post("sms_logs", {
                "phone_number": to_phone,
                "message": message[:1600],
                "type": "reminder",
                "status": "sent" if sent_ok else "failed",
                "twilio_sid": twilio_sid,
                "error_message": error_msg,
            })
        except Exception as log_exc:
            logger.error("Failed to log SMS: %s", log_exc)

        if sent_ok:
            logger.info("SMS sent to %s (sid=%s)", to_phone, twilio_sid)
            return {"sent": True, "twilio_sid": twilio_sid}
        else:
            logger.error("Twilio error: %s", error_msg or resp.text[:200])
            return {"sent": False, "error": error_msg or "Twilio request failed"}

    except Exception as exc:
        logger.error("SMS send failed: %s", exc)
        return {"sent": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Background job: process pending reminders every 15 minutes
# ---------------------------------------------------------------------------

async def process_pending_reminders() -> int:
    """Find due reminders, look up user phone, send SMS, mark as sent.

    Returns the number of reminders processed.

    Race-safety: each reminder is atomically *claimed* before any SMS is
    sent, using the `sent` flag as a compare-and-swap lock. The claim is a
    conditional PATCH (id == rid AND sent == false → sent = true). Only the
    worker whose PATCH actually returns a row owns the reminder; everyone
    else skips it. Combined with the process-level lock this guarantees a
    reminder is sent at most once even if the scheduler overlaps runs or
    multiple replicas are deployed.
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return 0

    # Prevent two overlapping invocations in THIS process from racing each
    # other (the cross-replica race is handled by the atomic claim below).
    if _reminder_job_lock.locked():
        logger.info("Reminder job already running — skipping overlapping run")
        return 0

    async with _reminder_job_lock:
        return await _process_pending_reminders_locked()


async def _claim_reminder(rid: str) -> bool:
    """Atomically claim a reminder. Returns True only if THIS call won it.

    Conditional update: only flips `sent` false → true. PostgREST returns the
    updated rows; an empty list means another worker already claimed it.
    """
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.patch(
                f"{SUPABASE_URL}/rest/v1/ai_reminders",
                params={"id": f"eq.{rid}", "sent": "eq.false"},
                json={
                    "sent": True,
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                },
                headers=headers,
            )
        if resp.status_code not in (200, 204):
            logger.warning(
                "Reminder claim for %s returned HTTP %s", rid, resp.status_code
            )
            return False
        try:
            rows = resp.json()
        except Exception:
            rows = None
        # With return=representation, a successful claim returns the row(s).
        # Empty list → already claimed by someone else.
        if isinstance(rows, list):
            return len(rows) > 0
        # Some PostgREST configs return 204/no body; treat 200 as success.
        return resp.status_code == 200
    except Exception as exc:
        logger.error("Failed to claim reminder %s: %s", rid, exc)
        return False


async def _process_pending_reminders_locked() -> int:
    now_iso = datetime.now(timezone.utc).isoformat()
    processed = 0

    try:
        # Fetch due, unsent reminders
        reminders = await supabase_get("ai_reminders", {
            "sent": "eq.false",
            "trigger_time": f"lte.{now_iso}",
            "select": "id,user_id,message,reminder_type,trigger_time",
            "order": "trigger_time.asc",
            "limit": "50",
        })
    except Exception as exc:
        logger.error("Reminder fetch failed: %s", exc)
        return 0

    for reminder in reminders:
        rid = reminder.get("id")
        uid = reminder.get("user_id")
        msg = reminder.get("message", "")
        rtype = reminder.get("reminder_type", "general")

        if not rid:
            continue

        # Atomically claim BEFORE sending. If we don't win the claim, another
        # worker is handling this reminder — skip to avoid a double SMS.
        if not await _claim_reminder(rid):
            logger.info("Reminder %s already claimed elsewhere — skipping", rid)
            continue

        # Look up user phone
        phone = None
        try:
            user_rows = await supabase_get("users", {
                "id": f"eq.{uid}",
                "select": "phone,name,sms_opt_in,sms_notifications_enabled",
            })
            if user_rows:
                user = user_rows[0]
                # Only send if user has opted in to SMS
                if user.get("sms_opt_in") or user.get("sms_notifications_enabled"):
                    phone = user.get("phone")
        except Exception as exc:
            logger.error("User phone lookup for reminder %s failed: %s", rid, exc)

        # Send SMS if phone available. The reminder is already marked sent
        # (claimed), so it will not be re-processed regardless of SMS outcome.
        if phone:
            prefix = {
                "pickup": "🍎 Pickup Reminder",
                "listing_expiry": "⏰ Listing Expiry",
                "distribution_event": "📍 Event Reminder",
                "general": "📋 Reminder",
            }.get(rtype, "📋 Reminder")
            sms_body = f"[DoGoods] {prefix}: {msg}"
            try:
                await send_sms_via_twilio(phone, sms_body)
            except Exception as exc:
                logger.error("SMS send for reminder %s failed: %s", rid, exc)
        else:
            logger.info(
                "No phone/SMS opt-in for user %s, reminder %s claimed without SMS",
                uid, rid,
            )

        processed += 1

    if processed:
        logger.info("Processed %d reminder(s)", processed)
    return processed


# ---------------------------------------------------------------------------
# Background job: notify users who forgot to pick up claimed food
# ---------------------------------------------------------------------------

PICKUP_GRACE_HOURS = int(os.getenv("PICKUP_GRACE_HOURS", "6"))

async def check_missed_pickups() -> int:
    """Find approved claims with pickup_date in the past and notify users.

    Only notifies once per claim by checking the notifications table
    for an existing 'missed_pickup' notification with the claim ID.
    Returns the number of notifications sent.
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return 0

    from datetime import timedelta

    # Use a strict less-than on today's date so same-day pickups are NEVER
    # flagged as missed before the day ends. `pickup_date` is a date-only
    # column, so hour-level grace (PICKUP_GRACE_HOURS) cannot be expressed
    # in a date comparison — the only safe boundary is midnight (start of
    # today). Pickups from strictly before today are overdue; today's
    # pickups are still in progress regardless of the current time.
    today_iso = datetime.now(timezone.utc).date().isoformat()

    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

    # Find approved claims where pickup_date has passed
    try:
        overdue_claims = await supabase_get("food_claims", {
            "status": "eq.approved",
            "pickup_date": f"lt.{today_iso}",
            "select": "id,claimer_id,food_id,pickup_date",
            "limit": "50",
        })
    except Exception as exc:
        logger.error("Missed pickup check — claims fetch failed: %s", exc)
        return 0

    if not overdue_claims:
        return 0

    notified = 0
    for claim in overdue_claims:
        claim_id = claim.get("id")
        claimer_id = claim.get("claimer_id")
        food_id = claim.get("food_id")
        pickup_date = claim.get("pickup_date", "")

        if not claimer_id or not claim_id:
            continue

        # Check if we already notified for this claim
        try:
            existing = await supabase_get("notifications", {
                "user_id": f"eq.{claimer_id}",
                "type": "eq.alert",
                "data->>claim_id": f"eq.{claim_id}",
                "select": "id",
                "limit": "1",
            })
            if existing:
                continue  # Already notified
        except Exception:
            pass  # If check fails, send anyway to be safe

        # Look up food title
        food_title = "your claimed food"
        try:
            food_rows = await supabase_get("food_listings", {
                "id": f"eq.{food_id}",
                "select": "title",
            })
            if food_rows:
                food_title = food_rows[0].get("title", food_title)
        except Exception:
            pass

        # Send in-app notification
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{SUPABASE_URL}/rest/v1/notifications",
                    json={
                        "user_id": claimer_id,
                        "title": "Pickup Reminder",
                        "message": (
                            f"It looks like you haven't picked up \"{food_title}\" yet "
                            f"(scheduled for {pickup_date}). Please pick it up soon "
                            f"or cancel the claim so others can benefit!"
                        ),
                        "type": "alert",
                        "read": False,
                        "data": {"claim_id": claim_id, "food_id": food_id},
                    },
                    headers=headers,
                )
                resp.raise_for_status()
                notified += 1
                logger.info(
                    "Missed pickup notification sent: claim=%s user=%s food=%s",
                    claim_id, claimer_id, food_title,
                )
        except Exception as exc:
            logger.error(
                "Failed to notify missed pickup claim=%s: %s", claim_id, exc
            )

    if notified:
        logger.info("Sent %d missed-pickup notification(s)", notified)
    return notified


# ---------------------------------------------------------------------------
# Background job: mark expired listings and delete old expired ones
# ---------------------------------------------------------------------------

async def delete_expired_listings() -> dict[str, int]:
    """Mark listings with past expiry_date as expired, then hard-delete very old ones.

    Returns dict with counts: {'marked': N, 'deleted': M}
    
    Two-phase cleanup:
    1. Mark as 'expired' if expiry_date < today AND status is active/approved
    2. Hard delete if status='expired' AND expiry_date was > 7 days ago
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return {"marked": 0, "deleted": 0}

    from datetime import date, timedelta

    today_iso = date.today().isoformat()
    delete_cutoff = (date.today() - timedelta(days=7)).isoformat()
    
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }

    marked = 0
    deleted = 0

    try:
        # Phase 1: Mark as expired (active/approved listings with past expiry_date)
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Find candidates to mark as expired
            mark_url = (
                f"{SUPABASE_URL}/rest/v1/food_listings?"
                f"expiry_date=lt.{today_iso}&"
                f"status=in.(active,approved)&"
                f"select=id,title,expiry_date"
            )
            resp = await client.get(mark_url, headers=headers)
            resp.raise_for_status()
            to_mark = resp.json()

            if to_mark:
                # Batch update to 'expired' status
                mark_ids = [item["id"] for item in to_mark]
                update_url = f"{SUPABASE_URL}/rest/v1/food_listings?id=in.({','.join(mark_ids)})"
                update_resp = await client.patch(
                    update_url,
                    json={"status": "expired"},
                    headers=headers
                )
                update_resp.raise_for_status()
                marked = len(to_mark)
                logger.info(
                    "Marked %d listing(s) as expired (expiry_date < %s)",
                    marked, today_iso
                )

            # Phase 2: Hard delete old expired listings (expiry_date > 7 days ago)
            delete_url = (
                f"{SUPABASE_URL}/rest/v1/food_listings?"
                f"status=eq.expired&"
                f"expiry_date=lt.{delete_cutoff}&"
                f"select=id,title"
            )
            delete_resp = await client.get(delete_url, headers=headers)
            delete_resp.raise_for_status()
            to_delete = delete_resp.json()

            if to_delete:
                delete_ids = [item["id"] for item in to_delete]
                hard_delete_url = f"{SUPABASE_URL}/rest/v1/food_listings?id=in.({','.join(delete_ids)})"
                final_resp = await client.delete(hard_delete_url, headers=headers)
                final_resp.raise_for_status()
                deleted = len(to_delete)
                logger.info(
                    "Hard-deleted %d listing(s) (expiry_date > 7 days ago)",
                    deleted
                )

    except Exception as exc:
        logger.error("Expired listing cleanup failed: %s", exc)

    return {"marked": marked, "deleted": deleted}


async def _reminder_loop() -> None:
    """Background loop: reminders + missed pickup checks with backoff on errors."""
    logger.info(
        "Background job started (interval=%ds)", REMINDER_CHECK_INTERVAL
    )
    consecutive_failures = 0
    while True:
        try:
            await process_pending_reminders()
            consecutive_failures = 0  # Reset on success
        except Exception as exc:
            consecutive_failures += 1
            logger.error("Reminder loop error (fail #%d): %s", consecutive_failures, exc)
        try:
            await check_missed_pickups()
        except Exception as exc:
            logger.error("Missed pickup check error: %s", exc)
        try:
            await delete_expired_listings()
        except Exception as exc:
            logger.error("Expired listing cleanup error: %s", exc)

        # Exponential backoff on repeated failures (up to 1 hour)
        if consecutive_failures > 0:
            backoff = min(REMINDER_CHECK_INTERVAL * (2 ** consecutive_failures), 3600)
            logger.warning("Backing off reminder loop for %ds", backoff)
            await asyncio.sleep(backoff)
        else:
            await asyncio.sleep(REMINDER_CHECK_INTERVAL)


# ---------------------------------------------------------------------------
# FastAPI lifespan (starts/stops background tasks)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: launch background reminder job
    task = asyncio.create_task(_reminder_loop())
    logger.info("Background reminder job scheduled")
    yield
    # Shutdown: cancel background task and close shared HTTP client
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        logger.info("Background reminder job stopped")
    # Close shared httpx client to release connections gracefully
    from backend.ai_engine import _http_client
    if _http_client and not _http_client.is_closed:
        await _http_client.aclose()
        logger.info("Shared HTTP client closed")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="DoGoods AI Backend",
    version="2.0.0",
    description="AI conversation engine + food matching + community tools",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Expose so the browser can read it from JS — without this the
    # X-Request-ID we attach below is invisible to fetch() callers.
    expose_headers=["X-Request-ID", "Retry-After"],
)


# ---------------------------------------------------------------------------
# Request ID middleware
#
# Every request gets a UUID that's:
#   • attached to `request.state.request_id` for downstream handlers/log lines
#   • echoed back in the X-Request-ID response header
#   • included in any AIError JSON body
#
# Lets us correlate a user-reported "AI failed" with backend logs without
# guesswork. Honors an inbound X-Request-ID so traces survive a frontend
# correlation header if/when we add one.
# ---------------------------------------------------------------------------

@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    request.state.request_id = rid
    try:
        response = await call_next(request)
    except Exception:
        # Re-raise — the AIError handler below will see request.state.request_id
        raise
    response.headers["X-Request-ID"] = rid
    return response


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "") if hasattr(request, "state") else ""


# ---------------------------------------------------------------------------
# AIError exception handler — always emits a consistent JSON body.
# The frontend uses `error_code` to decide whether to show a Retry button,
# rate-limit countdown, etc.
# ---------------------------------------------------------------------------

@app.exception_handler(AIError)
async def ai_error_handler(request: Request, exc: AIError) -> JSONResponse:
    rid = _request_id(request)
    if exc.cause:
        logger.warning(
            "[%s] AIError %s (%s) | cause=%s",
            rid, exc.code.value, exc.http_status, exc.cause,
        )
    else:
        logger.warning(
            "[%s] AIError %s (%s) | %s",
            rid, exc.code.value, exc.http_status, exc.message,
        )
    body = exc.to_dict()
    body["request_id"] = rid
    # Keep `detail` for clients that look for FastAPI's conventional field.
    body["detail"] = exc.message
    headers = {"X-Request-ID": rid}
    if exc.retry_after_seconds is not None:
        headers["Retry-After"] = str(exc.retry_after_seconds)
    return JSONResponse(status_code=exc.http_status, content=body, headers=headers)


# Also wrap plain HTTPExceptions raised by validation/rate-limit so the
# frontend gets the same shape (request_id, error_code) for every failure.
@app.exception_handler(HTTPException)
async def http_exception_to_ai_error(request: Request, exc: HTTPException) -> JSONResponse:
    rid = _request_id(request)
    # Pick the closest AIErrorCode for the status — keeps the contract uniform.
    if exc.status_code == 429:
        code = AIErrorCode.RATE_LIMIT
        retryable = True
        retry_after = 30
    elif exc.status_code in (401, 403):
        code = AIErrorCode.AUTH
        retryable = False
        retry_after = None
    elif 400 <= exc.status_code < 500:
        code = AIErrorCode.INVALID_INPUT
        retryable = False
        retry_after = None
    elif exc.status_code == 504:
        code = AIErrorCode.TIMEOUT
        retryable = True
        retry_after = 5
    elif exc.status_code >= 500:
        code = AIErrorCode.MODEL_UNAVAILABLE
        retryable = True
        retry_after = 8
    else:
        # 2xx/3xx HTTPException? unusual, but fall back to default handler.
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "request_id": rid},
            headers={"X-Request-ID": rid},
        )
    body = {
        "error_code": code.value,
        "message": str(exc.detail) if exc.detail else code.value,
        "retryable": retryable,
        "detail": exc.detail,
        "request_id": rid,
    }
    if retry_after is not None:
        body["retry_after_seconds"] = retry_after
    headers = {"X-Request-ID": rid}
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return JSONResponse(status_code=exc.status_code, content=body, headers=headers)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_client_ip(request: Request) -> str:
    # Behind a reverse proxy (Railway/Netlify/Nginx) request.client.host is the
    # proxy IP, which would collapse all users into a single rate-limit bucket.
    # Honour X-Forwarded-For (first hop = original client) when present.
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip", "")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


def _enforce_rate_limit(request: Request) -> None:
    if not check_rate_limit(_get_client_ip(request)):
        raise HTTPException(429, "Rate limit exceeded. Try again later.")


_NIL_UUID = "00000000-0000-0000-0000-000000000000"


def _enforce_user_rate_limit(user_id: str) -> None:
    if user_id and user_id != _NIL_UUID and not check_user_rate_limit(user_id):
        raise HTTPException(429, "You're sending requests too quickly. Slow down a bit.")


async def _require_auth_for_user(request: Request, user_id: str) -> str | None:
    """Auth gate for user-scoped AI routes.

    — Anonymous chat (nil-UUID) is allowed without an Authorization header,
      so the landing-page assistant keeps working.
    — Any real user_id MUST present a matching JWT. We refuse to write
      under (or read from) someone else's identity.
    """
    auth_uid = await _authenticate_request(request)
    if user_id and user_id != _NIL_UUID:
        if not auth_uid:
            raise HTTPException(401, "Authentication required")
        if auth_uid != user_id:
            raise HTTPException(403, "user_id does not match authenticated user")
    return auth_uid


import re as _re

_UUID_RE = _re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", _re.I
)


def _validate_uuid(value: str, field: str = "user_id") -> str:
    """Validate that a string is a proper UUID v4 format."""
    if not _UUID_RE.match(value):
        raise HTTPException(400, f"Invalid {field}: must be a valid UUID")
    return value


async def _authenticate_request(request: Request) -> str | None:
    """Validate the Supabase JWT from the Authorization header.

    Returns the authenticated user_id, or None if no auth header is present.
    In development (no SUPABASE_URL), auth is skipped for convenience.
    """
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return None  # No token — caller may be unauthenticated

    token = auth_header[7:]
    if not SUPABASE_URL:
        return None  # Can't validate without Supabase

    try:
        from backend.ai_engine import _get_http_client
        client = _get_http_client(5)
        resp = await client.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {token}",
            },
            timeout=5,
        )
        if resp.status_code == 200:
            user_data = resp.json()
            return user_data.get("id")
        return None
    except Exception as exc:
        logger.warning("Auth validation failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Pydantic models — AI conversation endpoints
# ---------------------------------------------------------------------------

class AIChatRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=5000)
    include_audio: bool = False
    # True when the message is an internal context push (e.g. after a
    # successful photo/CSV bulk upload) and should NOT appear in the user's
    # chat history. The assistant's reply is still persisted normally.
    silent: bool = False


class AIChatResponse(BaseModel):
    text: str
    audio_url: str | None = None
    user_id: str
    lang: str = "en"
    conversation_id: str | None = None
    transcript: str | None = None
    tool_results: list[dict] = []
    suggestions: list[str | dict[str, Any]] = []
    timestamp: str


class ConversationMessage(BaseModel):
    role: str
    message: str
    created_at: str


# ===================================================================
#  AI CONVERSATION ROUTES
# ===================================================================

@app.post("/api/ai/chat", response_model=AIChatResponse)
async def ai_chat(body: AIChatRequest, request: Request) -> dict:
    """
    Handle a text conversation turn.

    Flow: user message + user_id -> profile lookup -> GPT-4.1 query
          -> text response (+ optional TTS audio URL).

    Errors are returned as structured AIError JSON (see ai_engine.AIError)
    so the frontend can decide whether to render Retry, rate-limit hint, etc.
    """
    rid = _request_id(request)
    _enforce_rate_limit(request)
    _validate_uuid(body.user_id)
    _enforce_user_rate_limit(body.user_id)

    # Verify the caller owns this user_id. Anonymous (nil-UUID) sessions
    # remain allowed without auth so the landing-page chat keeps working.
    await _require_auth_for_user(request, body.user_id)

    try:
        return await conversation_engine.chat(
            user_id=body.user_id,
            message=body.message,
            include_audio=body.include_audio,
            silent=body.silent,
        )
    except AIError:
        # Already structured — let the AIError handler render it.
        raise
    except Exception as exc:
        # Convert anything else to a typed AIError so the response shape
        # stays consistent. Log with the request ID so we can correlate.
        logger.error("[%s] AI chat failed: %s", rid, exc, exc_info=True)
        raise classify_exception(exc) from exc


@app.get("/api/ai/history/{user_id}")
async def ai_history(user_id: str, request: Request, limit: int = 50) -> dict:
    """
    Retrieve conversation history for a user.

    Query params:
      - limit: max messages to return (default 50)
    """
    _enforce_rate_limit(request)
    _validate_uuid(user_id)
    _enforce_user_rate_limit(user_id)

    # Verify the caller owns this user_id
    await _require_auth_for_user(request, user_id)

    if limit < 1 or limit > 200:
        raise HTTPException(400, "limit must be between 1 and 200")

    try:
        history = await conversation_engine.get_conversation_history(
            user_id=user_id,
            limit=limit,
        )
        return {
            "user_id": user_id,
            "messages": history,
            "count": len(history),
        }
    except Exception as exc:
        logger.error("History fetch error: %s", exc)
        raise HTTPException(500, "Failed to retrieve conversation history") from exc


@app.delete("/api/ai/history/{user_id}")
async def ai_clear_history(user_id: str, request: Request) -> dict:
    """Delete all conversation history for a user."""
    _enforce_rate_limit(request)
    _validate_uuid(user_id)
    _enforce_user_rate_limit(user_id)

    await _require_auth_for_user(request, user_id)

    try:
        # Use proper query params instead of encoding filters in the table path
        headers = {
            "apikey": SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "Content-Type": "application/json",
        }
        from backend.ai_engine import _get_http_client, SUPABASE_TIMEOUT
        client = _get_http_client(SUPABASE_TIMEOUT)
        resp = await client.delete(
            f"{SUPABASE_URL}/rest/v1/ai_conversations",
            params={"user_id": f"eq.{user_id}"},
            headers=headers,
        )
        resp.raise_for_status()
        return {"user_id": user_id, "cleared": True}
    except Exception as exc:
        logger.error("Clear history error: %s", exc)
        raise HTTPException(500, "Failed to clear conversation history") from exc


class AIFeedbackRequest(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    rating: str = Field(min_length=1, max_length=20)
    comment: str | None = None


@app.post("/api/ai/feedback")
async def ai_feedback(body: AIFeedbackRequest, request: Request) -> dict:
    """Submit feedback on an AI message."""
    _enforce_rate_limit(request)
    _validate_uuid(body.user_id)
    _validate_uuid(body.conversation_id, "conversation_id")
    _enforce_user_rate_limit(body.user_id)

    await _require_auth_for_user(request, body.user_id)

    if body.rating not in ("helpful", "not_helpful", "up", "down"):
        raise HTTPException(400, "rating must be helpful or not_helpful")

    # Normalise legacy up/down to helpful/not_helpful for storage
    rating = body.rating
    if rating == "up":
        rating = "helpful"
    elif rating == "down":
        rating = "not_helpful"

    try:
        payload = {
            "conversation_id": body.conversation_id,
            "user_id": body.user_id,
            "rating": rating,
        }
        if body.comment:
            payload["comment"] = body.comment

        await supabase_post("ai_feedback", payload)
        return {"success": True}
    except Exception as exc:
        logger.error("Feedback save error: %s", exc)
        raise classify_exception(exc) from exc


@app.post("/api/ai/voice", response_model=AIChatResponse)
async def ai_voice(
    request: Request,
    audio: UploadFile = File(..., description="Audio file (webm, wav, mp3, m4a)"),
    user_id: str = Form(..., min_length=1, max_length=128),
    include_audio: bool = Form(default=True),
    silent: bool = Form(default=False),
    language: str | None = Form(default=None, max_length=5),
) -> dict:
    """
    Transcribe uploaded audio via OpenAI Whisper, then process as a chat message.

    Accepts multipart form with:
      - audio: audio file
      - user_id: user UUID
      - include_audio: whether to return TTS audio in response (default true)
      - language: optional ISO-639-1 hint ("en" or "es") passed to Whisper to
        improve accuracy on short/accented clips
    """
    _enforce_rate_limit(request)
    _validate_uuid(user_id)
    _enforce_user_rate_limit(user_id)

    await _require_auth_for_user(request, user_id)

    # Validate file type (strip codec params like ";codecs=opus")
    allowed_types = {
        "audio/webm", "audio/wav", "audio/mpeg", "audio/mp4",
        "audio/ogg", "audio/x-m4a", "audio/mp3",
    }
    base_type = (audio.content_type or "").split(";")[0].strip().lower()
    if base_type and base_type not in allowed_types:
        raise HTTPException(
            400,
            f"Unsupported audio type: {audio.content_type}. "
            f"Accepted: webm, wav, mp3, m4a, ogg",
        )

    # Read audio bytes (limit to 25MB — Whisper API max)
    audio_bytes = await audio.read()
    if len(audio_bytes) > 25 * 1024 * 1024:
        raise HTTPException(400, "Audio file too large (max 25MB)")
    if len(audio_bytes) == 0:
        raise HTTPException(400, "Empty audio file")

    try:
        # 1. Transcribe with Whisper
        transcript = await conversation_engine.transcribe_audio(
            audio_bytes=audio_bytes,
            filename=audio.filename or "audio.webm",
            language=language if language in ("en", "es") else None,
        )
        logger.info("Transcribed audio for user %s: %s", user_id, transcript[:100])

        # 1b. Filter Whisper hallucinations before sending to GPT
        if _is_whisper_noise(transcript):
            logger.info("Filtered Whisper noise for user %s: %s", user_id, transcript[:80])
            raise HTTPException(
                400,
                "Could not understand the audio. Please try again "
                "or switch to text input.",
            )

        # 2. Process transcribed text as a chat message
        result = await conversation_engine.chat(
            user_id=user_id,
            message=transcript,
            include_audio=include_audio,
            silent=silent,
        )
        # Include the transcript in the response
        result["transcript"] = transcript
        return result

    except (AIError, HTTPException):
        raise  # already structured / typed
    except Exception as exc:
        rid = _request_id(request)
        logger.error("[%s] Voice processing failed for user %s: %s", rid, user_id, exc, exc_info=True)
        # Convert anything else to a typed AIError so the frontend can
        # decide whether to retry, fall back to text, etc.
        raise classify_exception(exc) from exc


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4096)
    lang: str = Field(default="en", max_length=5)


@app.post("/api/ai/tts")
async def ai_tts(body: TTSRequest, request: Request):
    """Generate speech audio from text. Returns audio/mpeg blob."""
    _enforce_rate_limit(request)

    try:
        audio_bytes = await conversation_engine.generate_speech(
            body.text, lang=body.lang
        )
        from fastapi.responses import Response

        return Response(content=audio_bytes, media_type="audio/mpeg")
    except RuntimeError as exc:
        logger.error("TTS RuntimeError: %s", exc)
        raise classify_exception(exc) from exc
    except httpx.HTTPStatusError as exc:
        logger.error("TTS upstream error %s", exc.response.status_code)
        raise classify_exception(exc) from exc
    except Exception as exc:
        logger.error("TTS error: %s", exc)
        raise classify_exception(exc) from exc


# ---------------------------------------------------------------------------
# Whisper hallucination filter (common artifacts on silence / noise)
# ---------------------------------------------------------------------------

# Exact-match noise phrases (after punctuation removal + lowercase)
_WHISPER_NOISE_PHRASES = {
    "thank you", "thanks", "thank you for watching", "thanks for watching",
    "thank you very much", "thank you so much", "thank you bye",
    "thank you byebye", "thank you goodbye", "thanks bye",
    "thanks for listening", "thanks for tuning in",
    "subscribe", "like and subscribe", "please subscribe",
    "music", "foreign", "applause", "laughter", "silence",
    "bye", "byebye", "bye bye", "goodbye", "good bye",
    "you", "the", "i", "a", "um", "uh", "oh", "hmm", "huh",
    "gwynple", "asha", "welcome",
    "okay", "ok", "so", "yeah", "yes", "no", "right",
    "subtitles by", "subtitles", "captions",
    "you know", "see you next time", "see you",
    "thats all", "thats it", "the end",
}

# Words that are individually noise — if ALL words in transcript are noise, filter it
_WHISPER_NOISE_WORDS = {
    "thank", "thanks", "you", "bye", "byebye", "goodbye", "good",
    "the", "a", "i", "um", "uh", "oh", "hmm", "huh", "ok", "okay",
    "so", "yeah", "yes", "no", "right", "well", "and", "but",
    "please", "welcome", "foreign", "music", "applause", "laughter",
    "silence", "subscribe", "like", "see", "next", "time",
    "very", "much", "for", "watching", "listening", "bye",
}


def _is_whisper_noise(text: str) -> bool:
    """Return True if the transcription looks like Whisper hallucination."""
    stripped = text.strip()
    # Pure-number replies (e.g. "1", "2") are valid listing picks in the
    # voice claim flow — never treat them as noise.
    if stripped.isdigit():
        return False
    if len(stripped) < 3:
        return True

    # Remove punctuation for comparison
    cleaned = re.sub(r"[^\w\s]", "", stripped).strip().lower()

    # Exact match against known noise phrases
    if cleaned in _WHISPER_NOISE_PHRASES:
        return True

    # Very short cleaned text
    if len(cleaned) < 3:
        return True

    # All-noise-words check: if every word is a filler/noise word, filter it
    words = cleaned.split()
    if words and all(w in _WHISPER_NOISE_WORDS for w in words):
        return True

    # Repeated phrase detection (e.g. "thank you thank you thank you")
    if words and len(set(words)) <= 2 and len(words) >= 3:
        return True

    # High ratio of non-ASCII chars suggests garbled output
    ascii_chars = sum(1 for c in stripped if c.isascii())
    if len(stripped) > 5 and ascii_chars / len(stripped) < 0.5:
        return True

    return False


@app.post("/api/ai/transcribe")
async def ai_transcribe(
    request: Request,
    audio: UploadFile = File(..., description="Audio file (webm, wav, mp3, m4a)"),
    language: str | None = Form(default=None, max_length=5),
) -> dict:
    """
    Transcription-only endpoint — Whisper STT without chat processing.

    Use this when you only need the transcript text and will send it to
    /api/ai/chat separately. ``language`` is an optional ISO-639-1 hint
    ("en" or "es") that the frontend should send based on the UI language.
    """
    _enforce_rate_limit(request)

    # Validate file type
    allowed_types = {
        "audio/webm", "audio/wav", "audio/mpeg", "audio/mp4",
        "audio/ogg", "audio/x-m4a", "audio/mp3",
    }
    base_type = (audio.content_type or "").split(";")[0].strip().lower()
    if base_type and base_type not in allowed_types:
        raise HTTPException(
            400,
            f"Unsupported audio type: {audio.content_type}. "
            f"Accepted: webm, wav, mp3, m4a, ogg",
        )

    audio_bytes = await audio.read()
    if len(audio_bytes) > 25 * 1024 * 1024:
        raise HTTPException(400, "Audio file too large (max 25MB)")
    if len(audio_bytes) == 0:
        raise HTTPException(400, "Empty audio file")

    try:
        transcript = await conversation_engine.transcribe_audio(
            audio_bytes=audio_bytes,
            filename=audio.filename or "audio.webm",
            language=language if language in ("en", "es") else None,
        )
        logger.info("Transcribed (transcribe-only): %s", transcript[:100])

        # Filter Whisper hallucinations
        if _is_whisper_noise(transcript):
            logger.info("Filtered Whisper noise: %s", transcript[:80])
            return {"transcript": "", "filtered": True}

        return {"transcript": transcript.strip(), "filtered": False}

    except httpx.TimeoutException as exc:
        raise classify_exception(exc) from exc
    except RuntimeError as exc:
        logger.error("Transcribe RuntimeError: %s", exc)
        raise classify_exception(exc) from exc
    except Exception as exc:
        logger.error("Transcription error: %s", exc)
        raise classify_exception(exc) from exc


# ===================================================================
#  ROLE-SPECIFIC DASHBOARD INSIGHTS
# ===================================================================

class AIInsightsRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    role_hint: str | None = Field(default=None, max_length=32)


async def _resolve_user_role(user_id: str, role_hint: str | None) -> tuple[str, dict]:
    """Resolve a user's effective dashboard role.

    Returns (role, user_row). Role is one of:
      admin, donor, dispatcher, recipient, volunteer, organizer, sponsor.
    """
    users = await supabase_get("users", {
        "id": f"eq.{user_id}",
        "select": (
            "id,name,is_admin,community_role,"
            "address,phone,avatar_url,"
            "dietary_restrictions,sms_opt_in"
        ),
        "limit": "1",
    })
    user_row = users[0] if users else {}

    if user_row.get("is_admin"):
        return "admin", user_row

    raw_role = (role_hint or user_row.get("community_role") or "recipient").lower()
    allowed = {"admin", "donor", "dispatcher", "driver", "recipient", "volunteer", "organizer", "sponsor"}
    if raw_role not in allowed:
        raw_role = "recipient"
    if raw_role == "driver":
        raw_role = "dispatcher"
    return raw_role, user_row


async def _gather_recipient_data(user_id: str) -> dict:
    now_iso = datetime.now(timezone.utc).isoformat()
    today_iso = datetime.now(timezone.utc).date().isoformat()
    pending_claims = await supabase_get("food_claims", {
        "claimer_id": f"eq.{user_id}",
        "status": "in.(pending,approved)",
        "select": "id,status,created_at,quantity,food_id",
        "order": "created_at.desc",
        "limit": "10",
    })
    nearby_listings = await supabase_get("food_listings", {
        "status": "in.(approved,active)",
        "or": f"(expiry_date.is.null,expiry_date.gte.{today_iso})",
        "select": "id,title,category,quantity,unit,expiry_date,pickup_by,location,image_url,created_at",
        "order": "created_at.desc",
        "limit": "12",
    })
    notifications = await supabase_get("notifications", {
        "user_id": f"eq.{user_id}",
        "read": "eq.false",
        "select": "id,title,message,created_at",
        "order": "created_at.desc",
        "limit": "5",
    })
    return {
        "pending_claims": pending_claims,
        "nearby_listings": nearby_listings,
        "unread_notifications": notifications,
        "snapshot_at": now_iso,
    }


async def _gather_donor_data(user_id: str) -> dict:
    now = datetime.now(timezone.utc)
    my_listings = await supabase_get("food_listings", {
        "user_id": f"eq.{user_id}",
        "select": "id,title,status,quantity,unit,expiry_date,pickup_by,category,created_at",
        "order": "created_at.desc",
        "limit": "25",
    })
    # Claims received on the donor's listings (requires listing ids)
    listing_ids = [str(item.get("id")) for item in my_listings if item.get("id") is not None]
    claims_received = []
    if listing_ids:
        claims_received = await supabase_get("food_claims", {
            "food_id": f"in.({','.join(listing_ids)})",
            "select": "id,status,quantity,created_at,food_id,claimer_id",
            "order": "created_at.desc",
            "limit": "20",
        })
    return {
        "my_listings": my_listings,
        "claims_received": claims_received,
        "snapshot_at": now.isoformat(),
    }


async def _gather_dispatcher_data(user_id: str) -> dict:
    now_iso = datetime.now(timezone.utc).isoformat()
    approved_claims = await supabase_get("food_claims", {
        "status": "in.(approved,pending)",
        "select": "id,status,quantity,created_at,food_id,claimer_id",
        "order": "created_at.desc",
        "limit": "30",
    })
    today_iso = datetime.now(timezone.utc).date().isoformat()
    upcoming_events = await supabase_get("distribution_events", {
        "select": "id,title,event_date,start_time,location,status,capacity,registered_count",
        # Only surface future/today events so the AI doesn't narrate past events
        # as "upcoming" when building dispatcher insights.
        "event_date": f"gte.{today_iso}",
        "order": "event_date.asc",
        "limit": "10",
    })
    return {
        "open_claims": approved_claims,
        "upcoming_events": upcoming_events,
        "snapshot_at": now_iso,
    }


async def _gather_admin_data(user_id: str) -> dict:
    now_iso = datetime.now(timezone.utc).isoformat()
    pending_listings = await supabase_get("food_listings", {
        "status": "eq.pending",
        "select": "id,title,created_at,user_id,category",
        "order": "created_at.desc",
        "limit": "20",
    })
    pending_broadcasts = await supabase_get("admin_broadcasts", {
        "sent": "eq.false",
        "select": "id,title,channel,created_at",
        "order": "created_at.desc",
        "limit": "10",
    })
    recent_feedback = await supabase_get("user_feedback", {
        "select": "id,feedback_type,subject,message,status,priority,created_at",
        "order": "created_at.desc",
        "limit": "10",
    })
    return {
        "pending_listings": pending_listings,
        "pending_broadcasts": pending_broadcasts,
        "recent_feedback": recent_feedback,
        "snapshot_at": now_iso,
    }


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, (list, tuple, dict)) and len(value) == 0:
        return True
    return False


def _build_profile_gap_insights(role: str, user_row: dict) -> list[dict]:
    """Deterministic insights that nudge the user to fill profile gaps.

    Returned in priority order. These run alongside AI-generated insights
    so we always surface critical missing fields regardless of model output.
    """
    gaps: list[dict] = []

    has_name = not _is_empty(user_row.get("name"))
    has_address = not _is_empty(user_row.get("address"))
    has_phone = not _is_empty(user_row.get("phone"))
    has_dietary = not _is_empty(user_row.get("dietary_restrictions"))
    has_avatar = not _is_empty(user_row.get("avatar_url"))
    has_role = not _is_empty(user_row.get("community_role"))
    sms_opt_in = bool(user_row.get("sms_opt_in"))

    # All profile-gap actions deep-link to the editable settings page,
    # not the read-only /profile view.
    profile_href = "/settings"

    if not has_name:
        gaps.append({
            "id": "profile-name",
            "icon": "id-card",
            "title": "Add your name",
            "message": "Donors and dispatchers see your name when you claim or coordinate pickups.",
            "priority": "high",
            "action": {"label": "Update profile", "href": profile_href},
            "source": "profile_gap",
        })

    if role in ("recipient", "volunteer") and not has_dietary:
        gaps.append({
            "id": "profile-dietary",
            "icon": "utensils",
            "title": "Set your dietary needs",
            "message": "Tell us about allergies or dietary restrictions so we can match you with safe food.",
            "priority": "high",
            "action": {"label": "Add dietary needs", "href": profile_href},
            "source": "profile_gap",
        })

    if not has_address and role in ("recipient", "donor", "dispatcher", "volunteer"):
        gaps.append({
            "id": "profile-address",
            "icon": "map-marker-alt",
            "title": "Add your address",
            "message": (
                "We use your address to find food and pickups near you"
                if role != "donor"
                else "Your address helps recipients see where to pick up your donations."
            ),
            "priority": "high",
            "action": {"label": "Add address", "href": profile_href},
            "source": "profile_gap",
        })

    if not has_phone:
        gaps.append({
            "id": "profile-phone",
            "icon": "phone",
            "title": "Add a phone number",
            "message": "Required for SMS pickup reminders and coordinating last-minute changes.",
            "priority": "medium",
            "action": {"label": "Add phone", "href": profile_href},
            "source": "profile_gap",
        })
    elif not sms_opt_in:
        gaps.append({
            "id": "profile-sms-optin",
            "icon": "sms",
            "title": "Turn on SMS reminders",
            "message": "Get pickup reminders and expiration alerts by text. You can opt out anytime.",
            "priority": "low",
            "action": {"label": "Enable SMS", "href": profile_href},
            "source": "profile_gap",
        })

    if not has_role and role == "recipient":
        gaps.append({
            "id": "profile-role",
            "icon": "user-tag",
            "title": "Tell us how you help",
            "message": "Choose donor, recipient, volunteer, or dispatcher so your dashboard fits your goals.",
            "priority": "medium",
            "action": {"label": "Choose role", "href": profile_href},
            "source": "profile_gap",
        })

    if not has_avatar:
        gaps.append({
            "id": "profile-avatar",
            "icon": "image",
            "title": "Add a profile photo",
            "message": "A friendly photo helps neighbors recognize you at pickups.",
            "priority": "low",
            "action": {"label": "Upload photo", "href": profile_href},
            "source": "profile_gap",
        })

    return gaps


def _profile_completion_pct(user_row: dict) -> int:
    fields = [
        user_row.get("name"),
        user_row.get("address"),
        user_row.get("phone"),
        user_row.get("dietary_restrictions"),
        user_row.get("avatar_url"),
        user_row.get("community_role"),
    ]
    filled = sum(0 if _is_empty(v) else 1 for v in fields)
    return int(round(100 * filled / len(fields)))


def httpx_timedelta_hours(_hours: int):  # pragma: no cover - reserved
    from datetime import timedelta
    return timedelta(hours=_hours)


_ROLE_SYSTEM_PROMPTS = {
    "recipient": (
        "You help a FOOD RECIPIENT on DoGoods spot the best food to claim now. "
        "Use the listings provided. Prefer items expiring soon, fresh produce, "
        "and matches to their pending claims. Keep tone warm and practical."
    ),
    "donor": (
        "You help a FOOD DONOR on DoGoods keep their listings effective. "
        "Flag items expiring within 48 hours, listings stuck in 'pending', "
        "and unclaimed inventory. Suggest concrete actions like extending pickup, "
        "marking distributed, or adjusting category. Tone: supportive coach."
    ),
    "dispatcher": (
        "You help a DISPATCHER coordinate pickups. Surface unassigned approved "
        "claims, distribution events with low registration, and suggest a "
        "logical pickup order grouped by location. Tone: concise operator."
    ),
    "volunteer": (
        "You help a VOLUNTEER find ways to contribute today: nearby pickups to "
        "deliver and upcoming events that need help. Tone: motivating."
    ),
    "organizer": (
        "You help a community ORGANIZER coordinate distributions and member "
        "engagement. Highlight underperforming events and growth opportunities."
    ),
    "sponsor": (
        "You help a SPONSOR see their community impact. Highlight quantities "
        "distributed and notable stories. Tone: appreciative."
    ),
    "admin": (
        "You are a supportive ADMIN coach on DoGoods. Mix encouragement with "
        "operational nudges: queue of pending listings, unsent broadcasts, "
        "recent feedback themes. Celebrate wins. Tone: warm, brief, energizing."
    ),
}

_ROLE_GATHERERS = {
    "recipient": _gather_recipient_data,
    "donor": _gather_donor_data,
    "dispatcher": _gather_dispatcher_data,
    "volunteer": _gather_dispatcher_data,
    "organizer": _gather_admin_data,
    "sponsor": _gather_admin_data,
    "admin": _gather_admin_data,
}


_INSIGHTS_JSON_INSTRUCTIONS = (
    "Respond with STRICT JSON only, matching this schema:\n"
    "{\n"
    '  "headline": "short greeting headline, <= 80 chars",\n'
    '  "insights": [\n'
    "    {\n"
    '      "id": "kebab-case slug",\n'
    '      "icon": "fontawesome class without fa- prefix (e.g. clock, bell, route)",\n'
    '      "title": "short title <= 60 chars",\n'
    '      "message": "1-2 sentence explanation",\n'
    '      "priority": "high|medium|low",\n'
    '      "action": { "label": "<= 24 chars", "href": "/path" } or null\n'
    "    }\n"
    "  ]\n"
    "}\n"
    "Produce 2-5 insights. Order by priority. Use real data only — never invent records.\n"
    "Use ONLY these exact href paths (no others): /find, /share, /dashboard, /donations, "
    "/admin, /admin/users, /admin/broadcasts, /admin/distribution, /admin/feedback, "
    "/admin/reports, /admin/messages, /admin/communities, /admin/verifications, "
    "/near-me, /profile, /listings, /receipts, /notifications, /settings."
)


async def _call_openai_json(system_prompt: str, user_payload: str) -> dict:
    """Call OpenAI chat completions in JSON-mode and return parsed dict.

    Appends _INSIGHTS_JSON_INSTRUCTIONS to enforce the {headline, insights}
    output schema required by the dashboard insights endpoint.
    Retries once on 429 / 5xx before failing.
    """
    if not OPENAI_API_KEY:
        return {"headline": "AI insights offline", "insights": []}

    import asyncio
    import json as _json
    from backend.ai_engine import _get_http_client, OPENAI_BASE_URL, FOLLOWUP_MODEL
    client = _get_http_client(30)
    payload = {
        "model": FOLLOWUP_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt + "\n\n" + _INSIGHTS_JSON_INSTRUCTIONS},
            {"role": "user", "content": user_payload},
        ],
        "temperature": 0.5,
        "max_tokens": 700,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    for attempt in range(3):
        try:
            resp = await client.post(
                f"{OPENAI_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            )
            if resp.status_code in (429,) or resp.status_code >= 500:
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                resp.raise_for_status()
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            try:
                parsed = _json.loads(content)
            except Exception:
                return {"headline": "Insights unavailable", "insights": []}
            if not isinstance(parsed, dict):
                return {"headline": "Insights unavailable", "insights": []}
            insights = parsed.get("insights") or []
            if not isinstance(insights, list):
                insights = []
            return {
                "headline": str(parsed.get("headline") or "")[:200],
                "insights": insights[:5],
            }
        except Exception as exc:
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)
            else:
                logger.error("_call_openai_json failed after retries: %s", exc)
    return {"headline": "Insights unavailable", "insights": []}


async def _call_openai_raw_json(messages: list, max_tokens: int = 400) -> dict:
    """Call OpenAI chat completions in JSON-mode with caller-supplied messages.

    Unlike _call_openai_json, this does NOT append any fixed schema instructions —
    the caller is responsible for the full prompt (system + user). Returns the raw
    parsed JSON dict, or {} on error.
    """
    if not OPENAI_API_KEY:
        return {}

    import asyncio
    import json as _json
    from backend.ai_engine import _get_http_client, OPENAI_BASE_URL, FOLLOWUP_MODEL
    client = _get_http_client(30)
    payload = {
        "model": FOLLOWUP_MODEL,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    for attempt in range(3):
        try:
            resp = await client.post(
                f"{OPENAI_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            )
            if resp.status_code in (429,) or resp.status_code >= 500:
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                resp.raise_for_status()
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            try:
                return _json.loads(content)
            except Exception:
                return {}
        except Exception as exc:
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)
            else:
                logger.warning("_call_openai_raw_json failed: %s", exc)
    return {}


def _summarize_data_for_prompt(role: str, user_row: dict, data: dict) -> str:
    """Compact human-readable summary of role-specific data for the prompt."""
    name = user_row.get("name") or "there"
    lines = [f"User: {name} (role={role})"]
    # users.address is the correct plain-text column (no city/state columns exist).
    address = (user_row.get("address") or "").strip()
    if address:
        lines.append(f"Location: {address}")

    if role == "recipient":
        listings = data.get("nearby_listings", [])
        lines.append(f"Pending claims: {len(data.get('pending_claims', []))}")
        lines.append(f"Unread notifications: {len(data.get('unread_notifications', []))}")
        lines.append(f"Open listings nearby: {len(listings)}")
        for item in listings[:8]:
            lines.append(
                f"- listing#{item.get('id')} '{item.get('title')}' "
                f"category={item.get('category')} qty={item.get('quantity')}{item.get('unit') or ''} "
                f"expires={item.get('expiry_date') or item.get('pickup_by') or 'n/a'}"
            )
    elif role == "donor":
        listings = data.get("my_listings", [])
        lines.append(f"Your listings: {len(listings)}")
        lines.append(f"Claims received: {len(data.get('claims_received', []))}")
        for item in listings[:10]:
            lines.append(
                f"- listing#{item.get('id')} '{item.get('title')}' status={item.get('status')} "
                f"expires={item.get('expiry_date') or item.get('pickup_by') or 'n/a'} "
                f"qty={item.get('quantity')}{item.get('unit') or ''}"
            )
    elif role in ("dispatcher", "volunteer"):
        claims = data.get("open_claims", [])
        events = data.get("upcoming_events", [])
        lines.append(f"Open claims: {len(claims)}")
        lines.append(f"Upcoming events: {len(events)}")
        for item in claims[:10]:
            lines.append(
                f"- claim#{item.get('id')} status={item.get('status')} "
                f"listing#{item.get('food_id')} qty={item.get('quantity')}"
            )
        for ev in events[:5]:
            lines.append(
                f"- event#{ev.get('id')} '{ev.get('title')}' date={ev.get('event_date')} start={ev.get('start_time')} "
                f"capacity={ev.get('capacity')} registered={ev.get('registered_count')}"
            )
    else:  # admin / organizer / sponsor
        lines.append(f"Pending listings: {len(data.get('pending_listings', []))}")
        lines.append(f"Pending broadcasts: {len(data.get('pending_broadcasts', []))}")
        lines.append(f"Recent feedback items: {len(data.get('recent_feedback', []))}")
        for item in data.get("pending_listings", [])[:6]:
            lines.append(f"- pending listing#{item.get('id')} '{item.get('title')}' cat={item.get('category')}")
        for fb in data.get("recent_feedback", [])[:5]:
            rating = fb.get("rating")
            comment = (fb.get("comment") or "")[:120]
            lines.append(f"- feedback rating={rating} '{comment}'")

    return "\n".join(lines)


@app.post("/api/ai/insights")
async def ai_insights(body: AIInsightsRequest, request: Request) -> dict:
    """Generate role-specific dashboard insights for a user."""
    _enforce_rate_limit(request)
    _validate_uuid(body.user_id)

    await _require_auth_for_user(request, body.user_id)

    try:
        role, user_row = await _resolve_user_role(body.user_id, body.role_hint)
        gather = _ROLE_GATHERERS.get(role, _gather_recipient_data)
        data = await gather(body.user_id)

        is_admin_role = role == "admin"
        gap_insights = [] if is_admin_role else _build_profile_gap_insights(role, user_row)
        completion_pct = None if is_admin_role else _profile_completion_pct(user_row)

        system_prompt = _ROLE_SYSTEM_PROMPTS.get(role, _ROLE_SYSTEM_PROMPTS["recipient"])
        summary = _summarize_data_for_prompt(role, user_row, data)
        if is_admin_role:
            summary += (
                "\nDo NOT generate any insights about profile completion, profile fields, "
                "or personal account setup — this user is a platform admin."
            )
        elif gap_insights:
            gap_titles = ", ".join(g["title"] for g in gap_insights)
            summary += (
                f"\nProfile completion: {completion_pct}%.\n"
                f"Profile gaps already surfaced separately (do NOT duplicate): {gap_titles}."
            )
        else:
            summary += f"\nProfile completion: {completion_pct}% (no gaps)."

        result = await _call_openai_json(system_prompt, summary)
        ai_insights_list = result.get("insights") or []

        # Normalize any legacy / hallucinated href paths to real frontend routes.
        _HREF_ALIASES = {
            "/find-food": "/find",
            "/findfood": "/find",
            "/share-food": "/share",
            "/sharefood": "/share",
            "/user-dashboard": "/dashboard",
            "/userdashboard": "/dashboard",
            "/donation-schedules": "/donations",
            "/donationschedules": "/donations",
            "/admin/user-feedback": "/admin/feedback",
            "/admin/userfeedback": "/admin/feedback",
            "/admin/user-management": "/admin/users",
            "/user-feedback": "/admin/feedback",
            "/feedback": "/admin/feedback",
            "/admin/dashboard": "/admin",
            "/my-listings": "/listings",
            "/my-receipts": "/receipts",
            # /profile is read-only; any "complete/update profile" action must
            # go to the editable settings form instead.
            "/profile": "/settings",
            "/profile/edit": "/settings",
            "/edit-profile": "/settings",
            "/account": "/settings",
        }
        _ALLOWED_HREFS = {
            "/find", "/share", "/dashboard", "/donations", "/admin", "/admin/users",
            "/admin/broadcasts", "/admin/distribution", "/admin/feedback", "/admin/reports",
            "/admin/messages", "/admin/communities", "/admin/verifications",
            "/admin/settings", "/admin/impact", "/admin/attendees", "/admin/approval-codes",
            "/admin/share-food", "/admin/impact-content",
            "/near-me", "/profile", "/listings", "/receipts", "/notifications", "/settings",
            "/recipes", "/sponsors", "/community", "/blog", "/contact", "/donate",
        }
        for ins in ai_insights_list:
            if not isinstance(ins, dict):
                continue
            action = ins.get("action")
            if not isinstance(action, dict):
                continue
            href = (action.get("href") or "").strip()
            if not href:
                ins["action"] = None
                continue
            # Strip query/hash for matching, keep absolute external URLs as-is.
            if href.startswith(("http://", "https://")):
                continue
            base = href.split("?")[0].split("#")[0].rstrip("/") or "/"
            base_lc = base.lower()
            if base_lc in _HREF_ALIASES:
                action["href"] = _HREF_ALIASES[base_lc] + href[len(base):]
            elif base_lc not in _ALLOWED_HREFS:
                # Unknown route — drop the action button rather than 404.
                ins["action"] = None

        # Drop AI insights that duplicate profile-gap ids/titles.
        gap_keys = {g["id"] for g in gap_insights}
        gap_titles_lc = {g["title"].lower() for g in gap_insights}
        filtered_ai = [
            ins for ins in ai_insights_list
            if isinstance(ins, dict)
            and ins.get("id") not in gap_keys
            and str(ins.get("title", "")).lower() not in gap_titles_lc
        ]

        # Belt-and-suspenders: strip any profile-themed insight for admins.
        if is_admin_role:
            def _is_profile_themed(ins: dict) -> bool:
                blob = " ".join(str(ins.get(k, "")) for k in ("id", "title", "message", "source")).lower()
                return any(term in blob for term in ("profile", "complete your", "update your account"))
            filtered_ai = [ins for ins in filtered_ai if not _is_profile_themed(ins)]

        merged = gap_insights + filtered_ai
        return {
            "role": role,
            "headline": result.get("headline") or "Here's what's happening today",
            "insights": merged[:6],
            "profile_completion": completion_pct,
            "profile_gaps": [g["id"] for g in gap_insights],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        rid = _request_id(request)
        logger.exception("[%s] AI insights error: %s", rid, exc)
        raise classify_exception(exc) from exc


# ===================================================================
#  VOICE + LOCATION FOOD SEARCH
# ===================================================================

class VoiceSearchRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    transcript: str = Field(min_length=1, max_length=500)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    max_distance_km: float = Field(default=25.0, gt=0, le=500)
    limit: int = Field(default=10, ge=1, le=50)


_VOICE_SEARCH_FILTER_PROMPT = (
    "You extract structured search filters from a spoken food-search request.\n"
    "Return ONLY valid JSON matching this schema:\n"
    "{\n"
    '  "keywords": [string],         // 0-5 lowercased nouns to match against title/description\n'
    '  "category": string | null,    // one of: produce, bakery, dairy, prepared, pantry, frozen, beverages, other, or null\n'
    '  "dietary_tags": [string],     // e.g. ["vegetarian","vegan","halal","kosher","gluten-free"]\n'
    '  "avoid_allergens": [string],  // e.g. ["peanuts","dairy","gluten"]\n'
    '  "prefer_urgent": boolean,     // true if user wants soon-expiring food\n'
    '  "max_distance_km": number | null  // override max distance if user specified one\n'
    "}\n"
    "Never invent specifics not in the request. Use empty arrays / null when unsure."
)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two GPS points in kilometers."""
    import math
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _hours_until(deadline_iso: str | None) -> float | None:
    if not deadline_iso:
        return None
    try:
        dt = datetime.fromisoformat(str(deadline_iso).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = dt - datetime.now(timezone.utc)
        return max(0.0, delta.total_seconds() / 3600.0)
    except (ValueError, TypeError):
        return None


def _urgency_score(hours: float | None) -> tuple[int, str]:
    """Map hours-until-deadline to a 0..100 score and label."""
    if hours is None:
        return 25, "normal"
    if hours <= 0:
        return 100, "expired"
    if hours < 6:
        return 95, "critical"
    if hours < 24:
        return 80, "high"
    if hours < 72:
        return 55, "medium"
    return 25, "normal"


def _matches_filters(listing: dict, filters: dict) -> bool:
    """Apply parsed voice filters in a forgiving way (any-match)."""
    cat = (filters.get("category") or "").lower().strip()
    if cat and (listing.get("category") or "").lower() != cat:
        return False

    avoid = [str(a).lower() for a in (filters.get("avoid_allergens") or [])]
    if avoid:
        allergens = [str(a).lower() for a in (listing.get("allergens") or [])]
        if any(a in allergens for a in avoid):
            return False

    dietary = [str(d).lower() for d in (filters.get("dietary_tags") or [])]
    if dietary:
        tags = [str(t).lower() for t in (listing.get("dietary_tags") or [])]
        if not any(d in tags for d in dietary):
            return False

    keywords = [str(k).lower() for k in (filters.get("keywords") or []) if str(k).strip()]
    if keywords:
        haystack = " ".join([
            str(listing.get("title") or ""),
            str(listing.get("description") or ""),
            str(listing.get("category") or ""),
        ]).lower()
        if not any(k in haystack for k in keywords):
            return False
    return True


async def _parse_voice_query(transcript: str) -> dict:
    """Use the LLM to extract structured filters; fall back to plain-keyword search."""
    fallback = {
        "keywords": [w for w in transcript.lower().split() if len(w) > 3][:5],
        "category": None,
        "dietary_tags": [],
        "avoid_allergens": [],
        "prefer_urgent": "soon" in transcript.lower() or "urgent" in transcript.lower(),
        "max_distance_km": None,
    }
    if not OPENAI_API_KEY:
        return fallback
    try:
        # Use _call_openai_raw_json so only _VOICE_SEARCH_FILTER_PROMPT is in play —
        # _call_openai_json appends _INSIGHTS_JSON_INSTRUCTIONS which would override
        # the filter schema and make the LLM return {headline, insights} instead.
        parsed = await _call_openai_raw_json(
            [
                {"role": "system", "content": _VOICE_SEARCH_FILTER_PROMPT},
                {"role": "user", "content": transcript.strip()},
            ],
            max_tokens=200,
        )
        merged = {**fallback, **{k: v for k, v in parsed.items() if k in fallback}}
        return merged
    except Exception as exc:  # noqa: BLE001
        logger.warning("voice-search filter parse failed: %s", exc)
        return fallback


@app.post("/api/ai/voice-search")
async def ai_voice_search(body: VoiceSearchRequest, request: Request) -> dict:
    """GPS + voice-driven food search ranked by urgency and distance."""
    _enforce_rate_limit(request)
    _validate_uuid(body.user_id)

    await _require_auth_for_user(request, body.user_id)

    try:
        filters = await _parse_voice_query(body.transcript)
        max_distance = float(filters.get("max_distance_km") or body.max_distance_km)
        prefer_urgent = bool(filters.get("prefer_urgent"))

        today_iso = datetime.now(timezone.utc).date().isoformat()
        listings = await supabase_get("food_listings", {
            "select": (
                "id,title,description,image_url,category,quantity,unit,status,"
                "latitude,longitude,location,full_address,"
                "expiry_date,pickup_by,created_at,"
                "dietary_tags,allergens,urgency_level,donor_name"
            ),
            "status": "in.(approved,active)",
            "or": f"(expiry_date.gte.{today_iso},expiry_date.is.null)",
            "limit": "200",
        })

        results = []
        for item in listings:
            if not _matches_filters(item, filters):
                continue

            deadline = item.get("pickup_by") or item.get("expiry_date")
            hours = _hours_until(deadline)
            u_score, u_label = _urgency_score(hours)

            lat = item.get("latitude")
            lon = item.get("longitude")
            distance_km: float | None = None
            if (
                body.latitude is not None
                and body.longitude is not None
                and isinstance(lat, (int, float))
                and isinstance(lon, (int, float))
            ):
                distance_km = round(_haversine_km(body.latitude, body.longitude, float(lat), float(lon)), 2)
                if distance_km > max_distance:
                    continue

            # Distance score: 100 when on top of you, 0 at max_distance.
            if distance_km is None:
                d_score = 35  # neutral when location unknown
            else:
                d_score = max(0, int(round(100 * (1 - min(distance_km, max_distance) / max_distance))))

            urgency_weight = 0.7 if prefer_urgent else 0.55
            combined = round(urgency_weight * u_score + (1 - urgency_weight) * d_score, 1)

            results.append({
                "id": item.get("id"),
                "title": item.get("title"),
                "description": (item.get("description") or "")[:240],
                "image_url": item.get("image_url"),
                "category": item.get("category"),
                "quantity": item.get("quantity"),
                "unit": item.get("unit"),
                "location": item.get("location"),
                "full_address": item.get("full_address"),
                "latitude": item.get("latitude"),
                "longitude": item.get("longitude"),
                "donor_name": item.get("donor_name"),
                "dietary_tags": item.get("dietary_tags") or [],
                "allergens": item.get("allergens") or [],
                "deadline": deadline,
                "hours_until_deadline": round(hours, 1) if hours is not None else None,
                "urgency_label": u_label,
                "urgency_score": u_score,
                "distance_km": distance_km,
                "distance_score": d_score,
                "combined_score": combined,
            })

        results.sort(key=lambda r: r["combined_score"], reverse=True)
        top = results[: body.limit]

        if not top:
            headline = "No nearby listings matched that request."
        else:
            best = top[0]
            bits = [f"{len(top)} match{'es' if len(top) != 1 else ''}"]
            if best.get("distance_km") is not None:
                bits.append(f"closest {best['distance_km']} km")
            if best.get("hours_until_deadline") is not None:
                bits.append(f"most urgent in {best['hours_until_deadline']}h")
            headline = " · ".join(bits)

        return {
            "headline": headline,
            "transcript": body.transcript,
            "filters": filters,
            "max_distance_km": max_distance,
            "user_location": (
                {"latitude": body.latitude, "longitude": body.longitude}
                if body.latitude is not None and body.longitude is not None
                else None
            ),
            "results": top,
            "total_matched": len(results),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        rid = _request_id(request)
        logger.error("[%s] Voice search error: %s", rid, exc, exc_info=True)
        raise classify_exception(exc) from exc


# ===================================================================
#  ROUTE (Mapbox Directions proxy for client-side rendering)
# ===================================================================

class RouteRequest(BaseModel):
    origin_lat: float
    origin_lng: float
    dest_lat: float
    dest_lng: float
    profile: str = Field(default="driving", pattern="^(driving|walking|cycling)$")


@app.post("/api/ai/route")
async def ai_route(body: RouteRequest, request: Request) -> dict:
    """Return a Mapbox Directions route (geometry + summary) for client rendering."""
    _enforce_rate_limit(request)
    from backend.tools import _get_mapbox_route
    try:
        result = await _get_mapbox_route(
            origin_lng=body.origin_lng,
            origin_lat=body.origin_lat,
            dest_lng=body.dest_lng,
            dest_lat=body.dest_lat,
            profile=body.profile,
        )
        return result
    except Exception as exc:
        rid = _request_id(request)
        logger.error("[%s] Route lookup failed: %s", rid, exc, exc_info=True)
        raise classify_exception(exc) from exc


# ===================================================================
#  AI RECIPE GENERATOR  (household-aware, low-resource)
# ===================================================================

class RecipeRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    ingredients: list[str] | None = Field(default=None, max_length=40)
    use_claimed: bool = True
    low_resource: bool = True
    household_size: int | None = Field(default=None, ge=1, le=20)
    max_recipes: int = Field(default=3, ge=1, le=5)
    dietary_overrides: list[str] | None = Field(default=None, max_length=10)
    notes: str | None = Field(default=None, max_length=300)


_RECIPE_SYSTEM_PROMPT = (
    "You are a frugal home cook helping a household turn rescued/claimed food into meals.\n"
    "You MUST respond with ONLY valid JSON matching this exact schema:\n"
    "{\n"
    '  "headline": "short single-sentence summary of the menu",\n'
    '  "recipes": [\n'
    "    {\n"
    '      "title": "short dish name",\n'
    '      "summary": "1-2 sentence pitch",\n'
    '      "servings": integer,\n'
    '      "time_minutes": integer,\n'
    '      "difficulty": "easy|medium|hard",\n'
    '      "cost_tier": "low|medium|high",\n'
    '      "ingredients": [ { "name": "...", "quantity": "e.g. 1 cup", "optional": true|false } ],\n'
    '      "steps": [ "step 1", "step 2", ... ],\n'
    '      "equipment": [ "pan", "oven", ... ],\n'
    '      "dietary_tags": [ "vegetarian", "halal", ... ],\n'
    '      "uses_ingredients": [ "subset of user-provided ingredients actually used" ],\n'
    '      "tips": "1 short pro-tip about substitutions or storage"\n'
    "    }\n"
    "  ]\n"
    "}\n"
    "Hard rules:\n"
    "- Center each recipe on the provided ingredients; only add common pantry staples "
    "(salt, pepper, oil, water, flour, sugar, common spices, onion, garlic) when needed.\n"
    "- Respect dietary restrictions strictly.\n"
    "- If low_resource is true: limit equipment to stovetop/microwave/one pot/oven only; "
    "keep steps <= 8; keep total time <= 45 minutes; keep cost_tier = low.\n"
    "- Scale servings to household_size when provided.\n"
    "- Never invent ingredients the user does not have unless they are common staples.\n"
    "- Output between 1 and max_recipes recipes; do not exceed it.\n"
    "- Keep all strings concise; the entire response must fit in ~900 tokens."
)


async def _call_openai_freeform_json(
    system_prompt: str,
    user_payload: str,
    max_tokens: int = 1100,
    temperature: float = 0.6,
) -> dict:
    """Free-form JSON-mode chat call (not pinned to the insights schema).

    Retries on 429 / 5xx with exponential backoff so transient rate-limit
    spikes don't surface as hard errors on the recipes endpoint.
    """
    if not OPENAI_API_KEY:
        raise HTTPException(503, "AI service not configured")

    import asyncio
    import json as _json
    from backend.ai_engine import _get_http_client, OPENAI_BASE_URL, FOLLOWUP_MODEL
    client = _get_http_client(45)
    payload = {
        "model": FOLLOWUP_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_payload},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    for attempt in range(3):
        try:
            resp = await client.post(
                f"{OPENAI_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            )
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                resp.raise_for_status()
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            try:
                parsed = _json.loads(content)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Free-form JSON parse failed: %s", exc)
                return {}
            return parsed if isinstance(parsed, dict) else {}
        except Exception as exc:
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)
            else:
                logger.error("_call_openai_freeform_json failed after retries: %s", exc)
                raise
    return {}


async def _gather_claimed_ingredients(user_id: str, limit: int = 12) -> list[dict]:
    """Pull the user's active claims joined with food_listings as ingredient hints."""
    try:
        rows = await supabase_get("food_claims", {
            "select": (
                "id,quantity,status,"
                "food_listings(id,title,category,quantity,unit,expiry_date,pickup_by,dietary_tags,allergens)"
            ),
            "claimer_id": f"eq.{user_id}",
            "status": "in.(pending,approved,scheduled)",
            "limit": str(limit),
        })
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load claimed ingredients: %s", exc)
        return []

    out: list[dict] = []
    for row in rows or []:
        fl = (row or {}).get("food_listings") or {}
        title = fl.get("title")
        if not title:
            continue
        out.append({
            "name": title,
            "category": fl.get("category"),
            "quantity": row.get("quantity") or fl.get("quantity"),
            "unit": fl.get("unit"),
            "dietary_tags": fl.get("dietary_tags") or [],
            "allergens": fl.get("allergens") or [],
            "deadline": fl.get("pickup_by") or fl.get("expiry_date"),
        })
    return out


def _coerce_int(value, default=None):
    """Best-effort integer coercion from numbers, '4', '4 people', '30-45 min'."""
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
    import re as _re
    m = _re.search(r"-?\d+", str(value))
    if m:
        try:
            return int(m.group(0))
        except (ValueError, TypeError):
            return default
    return default


def _normalize_recipe(raw: dict) -> dict | None:
    """Coerce model output into a stable shape; drop obviously bad rows."""
    if not isinstance(raw, dict):
        return None
    try:
        title = str(raw.get("title") or raw.get("name") or "").strip()
        if not title:
            return None
        ingredients_raw = raw.get("ingredients") or raw.get("items") or []
        ingredients: list[dict] = []
        for ing in ingredients_raw[:25]:
            if isinstance(ing, dict):
                name = str(ing.get("name") or ing.get("item") or "").strip()
                if not name:
                    continue
                ingredients.append({
                    "name": name[:80],
                    "quantity": str(ing.get("quantity") or ing.get("amount") or "").strip()[:40],
                    "optional": bool(ing.get("optional")),
                })
            elif isinstance(ing, str) and ing.strip():
                ingredients.append({"name": ing.strip()[:80], "quantity": "", "optional": False})
        # Steps can come back under several keys depending on model mood.
        steps_raw = (
            raw.get("steps")
            or raw.get("instructions")
            or raw.get("directions")
            or raw.get("method")
            or []
        )
        if isinstance(steps_raw, str):
            # Sometimes returned as a single newline-delimited string.
            steps_raw = [s for s in steps_raw.splitlines() if s.strip()]
        steps = [str(s).strip()[:400] for s in steps_raw[:15] if str(s).strip()]
        if not ingredients or not steps:
            return None
        return {
            "title": title[:80],
            "summary": str(raw.get("summary") or raw.get("description") or "").strip()[:240],
            "servings": _coerce_int(raw.get("servings") or raw.get("serves")),
            "time_minutes": _coerce_int(raw.get("time_minutes") or raw.get("time") or raw.get("total_time")),
            "difficulty": str(raw.get("difficulty") or "easy").lower()[:10],
            "cost_tier": str(raw.get("cost_tier") or "low").lower()[:10],
            "ingredients": ingredients,
            "steps": steps,
            "equipment": [str(e).strip()[:40] for e in (raw.get("equipment") or [])[:8] if str(e).strip()],
            "dietary_tags": [str(t).strip().lower()[:30] for t in (raw.get("dietary_tags") or [])[:8] if str(t).strip()],
            "uses_ingredients": [str(u).strip()[:60] for u in (raw.get("uses_ingredients") or [])[:15] if str(u).strip()],
            "tips": str(raw.get("tips") or raw.get("tip") or "").strip()[:240],
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Recipe normalization failed for one row: %s", exc)
        return None


@app.post("/api/ai/recipes")
async def ai_recipes(body: RecipeRequest, request: Request) -> dict:
    """Generate household-aware, low-resource recipes from claimed/available items."""
    _enforce_rate_limit(request)
    _validate_uuid(body.user_id)

    await _require_auth_for_user(request, body.user_id)

    # Profile context (dietary restrictions + allergies, community_role for household hint).
    user_rows = await supabase_get("users", {
        # Fetch both dietary_restrictions AND allergies — both are safety-critical
        # for recipe generation. Missing allergies here would let the AI suggest
        # nut-containing recipes to someone with a nut allergy.
        "select": "id,name,community_role,dietary_restrictions,allergies",
        "id": f"eq.{body.user_id}",
        "limit": "1",
    })
    user_row = (user_rows or [{}])[0] if user_rows else {}

    dietary: list[str] = []
    raw_diet = user_row.get("dietary_restrictions")
    if isinstance(raw_diet, list):
        dietary.extend([str(d).strip() for d in raw_diet if str(d).strip()])
    elif isinstance(raw_diet, str) and raw_diet.strip():
        dietary.extend([p.strip() for p in raw_diet.split(",") if p.strip()])
    # Always include allergies so the recipe AI never suggests food containing
    # an ingredient the user is allergic to (e.g. nut allergy → no nut recipes).
    raw_allergies = user_row.get("allergies")
    if isinstance(raw_allergies, list):
        dietary.extend([str(a).strip() for a in raw_allergies if str(a).strip()])
    elif isinstance(raw_allergies, str) and raw_allergies.strip():
        dietary.extend([p.strip() for p in raw_allergies.split(",") if p.strip()])
    if body.dietary_overrides:
        dietary.extend([str(d).strip() for d in body.dietary_overrides if str(d).strip()])
    dietary = list(dict.fromkeys([d.lower() for d in dietary]))[:12]

    # Ingredient list: explicit > claimed pickups.
    explicit = [str(i).strip() for i in (body.ingredients or []) if str(i).strip()]
    claimed: list[dict] = []
    if body.use_claimed and not explicit:
        claimed = await _gather_claimed_ingredients(body.user_id)

    ingredient_names = explicit or [c["name"] for c in claimed]
    if not ingredient_names:
        return {
            "headline": "Add some ingredients or claim food to get recipe suggestions.",
            "recipes": [],
            "source": "empty",
            "household_size": body.household_size,
            "dietary_restrictions": dietary,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    household = body.household_size or 2
    role = user_row.get("community_role") or "household"

    payload_lines = [
        f"household_size: {household}",
        f"household_role: {role}",
        f"low_resource: {body.low_resource}",
        f"max_recipes: {body.max_recipes}",
        f"dietary_restrictions: {dietary or 'none'}",
        f"ingredients_available: {ingredient_names[:25]}",
    ]
    if claimed:
        deadlines = [c.get("deadline") for c in claimed if c.get("deadline")]
        if deadlines:
            payload_lines.append(f"upcoming_pickup_deadlines: {deadlines[:5]}")
    if body.notes:
        payload_lines.append(f"notes_from_user: {body.notes[:280]}")

    payload_lines.append(
        "Return up to max_recipes recipes that use as many ingredients as possible, "
        "scaled to household_size, honoring dietary_restrictions, and matching the "
        "low_resource constraints when low_resource is true."
    )

    try:
        parsed = await _call_openai_freeform_json(
            _RECIPE_SYSTEM_PROMPT,
            "\n".join(payload_lines),
            max_tokens=1200,
            temperature=0.55,
        )
    except HTTPException:
        raise
    except Exception as exc:
        rid = _request_id(request)
        logger.error("[%s] Recipe generation error: %s", rid, exc, exc_info=True)
        raise classify_exception(exc) from exc

    recipes_out: list[dict] = []
    for r in (parsed.get("recipes") or [])[: body.max_recipes]:
        try:
            norm = _normalize_recipe(r)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping malformed recipe: %s", exc)
            continue
        if norm:
            recipes_out.append(norm)

    headline = str(parsed.get("headline") or "").strip()[:200]
    if not headline:
        if recipes_out:
            headline = f"{len(recipes_out)} recipe idea{'s' if len(recipes_out) != 1 else ''} for {household} serving{'s' if household != 1 else ''}."
        else:
            headline = "Couldn't build a recipe from those ingredients — try adjusting them."

    return {
        "headline": headline,
        "recipes": recipes_out,
        "source": "explicit" if explicit else ("claimed" if claimed else "empty"),
        "ingredients_used": ingredient_names[:25],
        "household_size": household,
        "low_resource": body.low_resource,
        "dietary_restrictions": dietary,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ===================================================================
#  NATURAL-LANGUAGE QUERY SYSTEM  (LLM function-calling → safe tools)
# ===================================================================
#
# Maps free-form questions to a whitelist of read-only, parameterized
# data-access "tools" executed against Supabase PostgREST. No raw SQL
# is ever produced or executed by the LLM — that surface is removed.
# Each tool is scoped to the authenticated user (admin gets a few extras).

class QueryRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    question: str = Field(min_length=1, max_length=500)
    max_steps: int = Field(default=3, ge=1, le=5)


_QUERY_SYSTEM_PROMPT = (
    "You are DoGoods' data assistant. Answer the user's question by calling "
    "the smallest set of provided tools, then give a concise (<=120 word) "
    "natural-language answer grounded in the tool results.\n"
    "Rules:\n"
    "- Never invent rows, counts, names, or IDs that did not come from a tool.\n"
    "- Always call a tool before making factual claims about the user's data.\n"
    "- If a tool returns no data, say so plainly.\n"
    "- Prefer at most 2 tool calls; chain only when strictly necessary.\n"
    "- When listing items, use short markdown bullets with the key fields.\n"
    "- Never reveal another user's private data."
)


def _query_tool_specs(is_admin: bool) -> list[dict]:
    """Return the OpenAI tools list available to this user."""
    tools: list[dict] = [
        {
            "type": "function",
            "function": {
                "name": "search_food_listings",
                "description": (
                    "Search public food listings by free-text keywords and/or category. "
                    "Returns at most max_results approved/active listings."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "keywords": {"type": "string", "description": "Optional space-separated terms to match title/description."},
                        "category": {"type": "string", "description": "Optional category filter (produce, bakery, dairy, prepared, pantry, frozen, beverages, other)."},
                        "dietary_tag": {"type": "string", "description": "Optional dietary tag (e.g. vegan, halal)."},
                        "max_results": {"type": "integer", "minimum": 1, "maximum": 25, "default": 10},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_my_claims",
                "description": "List the current user's food claims with their food listing details.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "description": "pending|approved|scheduled|completed|cancelled|all", "default": "all"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_my_listings",
                "description": "List the current user's own food listings.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "description": "approved|pending|expired|all", "default": "all"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_my_impact_summary",
                "description": "Aggregate counts for the current user: listings, claims, totals by status.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_my_profile",
                "description": "Return the current user's sanitized profile (name, role, dietary, address city/state).",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_recent_recipes",
                "description": "Read up to 5 active curated recipes from the recipes library.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "minimum": 1, "maximum": 5, "default": 5},
                    },
                },
            },
        },
    ]

    if is_admin:
        tools.extend([
            {
                "type": "function",
                "function": {
                    "name": "admin_count_users",
                    "description": "Admin: count users, optionally filtered by community_role.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "community_role": {"type": "string", "description": "donor|recipient|volunteer|sponsor|admin"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "admin_pending_claims",
                    "description": "Admin: list pending food claims awaiting approval.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "admin_failed_broadcasts",
                    "description": "Admin: list recent failed broadcast deliveries.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20},
                        },
                    },
                },
            },
        ])
    return tools


def _slim_listing(row: dict) -> dict:
    from backend.tools import _extract_location_text
    return {
        "id": row.get("id"),
        "title": row.get("title"),
        "category": row.get("category"),
        "quantity": row.get("quantity"),
        "unit": row.get("unit"),
        "status": row.get("status"),
        # food_listings.location is JSONB (dict from frontend writes); always
        # extract the human-readable address string via the helper.
        "location": row.get("full_address") or _extract_location_text(row.get("location")),
        "pickup_by": row.get("pickup_by"),
        "expiry_date": row.get("expiry_date"),
        "dietary_tags": row.get("dietary_tags") or [],
    }


async def _tool_search_food_listings(args: dict, _ctx: dict) -> dict:
    keywords = (args.get("keywords") or "").strip()
    category = (args.get("category") or "").strip().lower()
    dietary_tag = (args.get("dietary_tag") or "").strip().lower()
    max_results = max(1, min(25, int(args.get("max_results") or 10)))
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    params = {
        "select": "id,title,description,category,quantity,unit,status,location,full_address,pickup_by,expiry_date,dietary_tags",
        "status": "in.(approved,active)",
        # Exclude listings whose expiry_date has passed; include unlabeled items
        # (NULL expiry_date) which are non-perishable or pantry staples.
        "or": f"(expiry_date.is.null,expiry_date.gte.{today_str})",
        "limit": str(max_results),
    }
    if category:
        params["category"] = f"eq.{category}"
    if keywords:
        safe = keywords.replace(",", " ").replace("*", "").strip()
        if safe:
            # Can't add a second or= key (Python dict single-value constraint).
            # Wrap keyword filter in and(or(...)) so the expiry or= is preserved.
            params["and"] = f"(or(title.ilike.*{safe}*,description.ilike.*{safe}*))"
    if dietary_tag:
        params["dietary_tags"] = f"cs.{{{dietary_tag}}}"

    rows = await supabase_get("food_listings", params)
    return {"count": len(rows or []), "results": [_slim_listing(r) for r in (rows or [])]}


async def _tool_get_my_claims(args: dict, ctx: dict) -> dict:
    status = (args.get("status") or "all").strip().lower()
    limit = max(1, min(50, int(args.get("limit") or 20)))

    params = {
        "select": "id,status,quantity,created_at,pickup_by,food_listings(id,title,category,quantity,unit,pickup_by,expiry_date,location)",
        "claimer_id": f"eq.{ctx['user_id']}",
        "order": "created_at.desc",
        "limit": str(limit),
    }
    if status and status != "all":
        params["status"] = f"eq.{status}"
    rows = await supabase_get("food_claims", params)
    return {
        "count": len(rows or []),
        "claims": [
            {
                "id": r.get("id"),
                "status": r.get("status"),
                "quantity": r.get("quantity"),
                "created_at": r.get("created_at"),
                "pickup_by": r.get("pickup_by"),
                "listing": _slim_listing((r or {}).get("food_listings") or {}),
            }
            for r in (rows or [])
        ],
    }


async def _tool_get_my_listings(args: dict, ctx: dict) -> dict:
    status = (args.get("status") or "all").strip().lower()
    limit = max(1, min(50, int(args.get("limit") or 20)))

    params = {
        "select": "id,title,category,quantity,unit,status,location,full_address,pickup_by,expiry_date,dietary_tags,created_at",
        "user_id": f"eq.{ctx['user_id']}",
        "order": "created_at.desc",
        "limit": str(limit),
    }
    if status and status != "all":
        params["status"] = f"eq.{status}"
    rows = await supabase_get("food_listings", params)
    return {"count": len(rows or []), "listings": [_slim_listing(r) for r in (rows or [])]}


async def _tool_get_my_impact_summary(_args: dict, ctx: dict) -> dict:
    user_id = ctx["user_id"]
    try:
        listings = await supabase_get("food_listings", {
            "select": "id,status",
            "user_id": f"eq.{user_id}",
            "limit": "1000",
        })
    except Exception:
        listings = []
    try:
        claims = await supabase_get("food_claims", {
            "select": "id,status",
            "claimer_id": f"eq.{user_id}",
            "limit": "1000",
        })
    except Exception:
        claims = []

    def _by_status(rows: list[dict]) -> dict:
        out: dict[str, int] = {}
        for r in rows or []:
            key = (r or {}).get("status") or "unknown"
            out[key] = out.get(key, 0) + 1
        return out

    return {
        "listings_total": len(listings or []),
        "listings_by_status": _by_status(listings),
        "claims_total": len(claims or []),
        "claims_by_status": _by_status(claims),
    }


async def _tool_get_my_profile(_args: dict, ctx: dict) -> dict:
    rows = await supabase_get("users", {
        # Use `address` (plain text) instead of `location` (legacy JSON column).
        # `location` was null or a JSON blob for most users so queries like
        # "what address do you have for me?" would return nothing.
        "select": "id,name,community_role,address,dietary_restrictions,allergies,is_admin",
        "id": f"eq.{ctx['user_id']}",
        "limit": "1",
    })
    row = (rows or [{}])[0] if rows else {}
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "community_role": row.get("community_role"),
        "address": row.get("address"),
        "dietary_restrictions": row.get("dietary_restrictions") or [],
        "allergies": row.get("allergies") or [],
        "is_admin": bool(row.get("is_admin")),
    }


async def _tool_get_recent_recipes(args: dict, _ctx: dict) -> dict:
    limit = max(1, min(5, int(args.get("limit") or 5)))
    rows = await supabase_get("impact_recipes", {
        "select": "id,title,description,prep_time_minutes,cook_time_minutes,servings,difficulty,youtube_url",
        "is_active": "eq.true",
        "order": "created_at.desc",
        "limit": str(limit),
    })
    return {"count": len(rows or []), "recipes": rows or []}


async def _tool_admin_count_users(args: dict, _ctx: dict) -> dict:
    role = (args.get("community_role") or "").strip().lower()
    params: dict[str, str] = {"select": "id", "limit": "5000"}
    if role:
        params["community_role"] = f"eq.{role}"
    rows = await supabase_get("users", params)
    return {"count": len(rows or []), "community_role": role or "all"}


async def _tool_admin_pending_claims(args: dict, _ctx: dict) -> dict:
    limit = max(1, min(50, int(args.get("limit") or 20)))
    rows = await supabase_get("food_claims", {
        "select": "id,status,quantity,created_at,claimer_id,food_listings(id,title,category)",
        "status": "eq.pending",
        "order": "created_at.desc",
        "limit": str(limit),
    })
    return {"count": len(rows or []), "claims": rows or []}


async def _tool_admin_failed_broadcasts(args: dict, _ctx: dict) -> dict:
    limit = max(1, min(50, int(args.get("limit") or 20)))
    try:
        rows = await supabase_get("broadcast_deliveries", {
            "select": "id,broadcast_id,channel,target,sent_at,delivered,error",
            "delivered": "eq.false",
            "order": "sent_at.desc",
            "limit": str(limit),
        })
    except Exception as exc:  # noqa: BLE001
        logger.warning("admin_failed_broadcasts unavailable: %s", exc)
        rows = []
    return {"count": len(rows or []), "deliveries": rows or []}


_QUERY_TOOL_REGISTRY = {
    "search_food_listings": _tool_search_food_listings,
    "get_my_claims": _tool_get_my_claims,
    "get_my_listings": _tool_get_my_listings,
    "get_my_impact_summary": _tool_get_my_impact_summary,
    "get_my_profile": _tool_get_my_profile,
    "get_recent_recipes": _tool_get_recent_recipes,
    "admin_count_users": _tool_admin_count_users,
    "admin_pending_claims": _tool_admin_pending_claims,
    "admin_failed_broadcasts": _tool_admin_failed_broadcasts,
}

_ADMIN_TOOL_NAMES = {"admin_count_users", "admin_pending_claims", "admin_failed_broadcasts"}


async def _run_query_agent(question: str, user_id: str, is_admin: bool, max_steps: int) -> dict:
    """Drive the OpenAI function-calling loop over the safe tool registry."""
    if not OPENAI_API_KEY:
        raise HTTPException(503, "AI service not configured")

    from backend.ai_engine import _get_http_client, OPENAI_BASE_URL, FOLLOWUP_MODEL
    client = _get_http_client(45)

    tools = _query_tool_specs(is_admin)
    messages: list[dict] = [
        {"role": "system", "content": _QUERY_SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    trace: list[dict] = []

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    import asyncio as _asyncio
    import json as _json
    ctx = {"user_id": user_id, "is_admin": is_admin}

    for step in range(max_steps):
        payload = {
            "model": FOLLOWUP_MODEL,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 0.2,
            "max_tokens": 600,
        }
        for attempt in range(3):
            resp = await client.post(
                f"{OPENAI_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            )
            if (resp.status_code == 429 or resp.status_code >= 500) and attempt < 2:
                await _asyncio.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            break
        choice = resp.json()["choices"][0]
        msg = choice.get("message", {}) or {}
        tool_calls = msg.get("tool_calls") or []

        if not tool_calls:
            answer = (msg.get("content") or "").strip()
            return {"answer": answer, "tool_trace": trace, "steps": step}

        messages.append({
            "role": "assistant",
            "content": msg.get("content"),
            "tool_calls": tool_calls,
        })

        for call in tool_calls:
            fn = (call.get("function") or {})
            name = fn.get("name") or ""
            try:
                args = _json.loads(fn.get("arguments") or "{}")
            except Exception:
                args = {}

            handler = _QUERY_TOOL_REGISTRY.get(name)
            if not handler:
                tool_result: dict = {"error": f"Unknown tool: {name}"}
            elif name in _ADMIN_TOOL_NAMES and not is_admin:
                tool_result = {"error": "Forbidden: admin tool"}
            else:
                try:
                    tool_result = await handler(args, ctx)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("query tool '%s' failed: %s", name, exc)
                    tool_result = {"error": "Tool execution failed"}

            trace.append({"tool": name, "arguments": args, "result_preview": _preview(tool_result)})
            messages.append({
                "role": "tool",
                "tool_call_id": call.get("id"),
                "name": name,
                "content": _json.dumps(tool_result)[:4000],
            })

    # Hit max_steps without a final answer — ask for a summary using collected tool data.
    fallback_payload = {
        "model": FOLLOWUP_MODEL,
        "messages": messages + [{
            "role": "user",
            "content": "Summarize the findings above in <= 120 words. Do not call more tools.",
        }],
        "temperature": 0.2,
        "max_tokens": 400,
    }
    for attempt in range(3):
        resp = await client.post(
            f"{OPENAI_BASE_URL}/chat/completions",
            headers=headers,
            json=fallback_payload,
        )
        if (resp.status_code == 429 or resp.status_code >= 500) and attempt < 2:
            await _asyncio.sleep(2 ** attempt)
            continue
        resp.raise_for_status()
        break
    answer = (resp.json()["choices"][0]["message"].get("content") or "").strip()
    return {"answer": answer, "tool_trace": trace, "steps": max_steps}


def _preview(value, max_chars: int = 280) -> str:
    import json as _json
    try:
        s = _json.dumps(value, default=str)
    except Exception:
        s = str(value)
    return s[:max_chars] + ("…" if len(s) > max_chars else "")


# ===================================================================
#  BULK LISTINGS + VISION LISTING  (photo / CSV uploads from chat UI)
# ===================================================================

_VALID_FOOD_CATEGORIES = {
    "produce", "bakery", "dairy", "pantry", "meat", "prepared", "other",
}
_DEFAULT_FOOD_CATEGORY = "other"
_MAX_BULK_LISTINGS = 100


class BulkListingItem(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    quantity: float = Field(gt=0, le=100000)
    unit: str = Field(min_length=1, max_length=40)
    category: str = Field(min_length=1, max_length=40)
    description: Optional[str] = Field(default=None, max_length=2000)
    expiry_date: Optional[str] = Field(default=None, max_length=40)
    location: Optional[str] = Field(default=None, max_length=200)
    community_id: Optional[str] = Field(default=None, max_length=64)
    dietary_tags: Optional[List[str]] = None
    allergens: Optional[List[str]] = None
    image_url: Optional[str] = Field(default=None, max_length=2000)


class BulkListingsRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    listings: List[BulkListingItem] = Field(min_length=1, max_length=_MAX_BULK_LISTINGS)


def _normalize_listing_row(
    item: BulkListingItem,
    user_id: str,
    donor: dict | None = None,
) -> dict:
    """Map a validated BulkListingItem into a Supabase food_listings row."""
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
        # Match the manual Share Food flow after admin approval so recipients
        # see AI photo listings in Find Food and dashboard insights.
        "status": "approved",
    }
    if item.description:
        row["description"] = item.description.strip()[:2000]
    if item.expiry_date:
        # Normalize to YYYY-MM-DD before writing. The AI (enrich-listings or
        # vision-listing) may supply a full ISO datetime ('2026-06-15T00:00:00')
        # which PostgreSQL's date column would reject. Matches the normalization
        # applied in _create_food_listing and _post_food_request (bugs AV, AX).
        from backend.tools import _normalize_expiry_date as _ned
        _exp = _ned(item.expiry_date.strip())
        if _exp:
            row["expiry_date"] = _exp
    if item.location:
        loc_s = item.location.strip()[:200]
        row["location"] = loc_s
        # full_address powers address line on search cards + map pin popover.
        # Keep it in sync with location so bulk/photo listings render the same
        # as manually-posted ones (mirrors _create_food_listing logic).
        row["full_address"] = loc_s
    if item.dietary_tags:
        row["dietary_tags"] = [str(t).strip()[:40] for t in item.dietary_tags if str(t).strip()][:20]
    if item.allergens:
        row["allergens"] = [str(t).strip()[:40] for t in item.allergens if str(t).strip()][:20]
    if item.image_url:
        _url = item.image_url.strip()
        # Only store http/https URLs — reject javascript:, data:, file:, etc.
        if _url.startswith(("http://", "https://")):
            row["image_url"] = _url[:2000]
    if item.community_id:
        # Trust the explicit override (e.g. from the photo preview UI) over
        # the donor's saved community_id default.
        cid = str(item.community_id).strip()
        if cid:
            row["community_id"] = cid[:64]
    return apply_donor_defaults_to_listing(row, donor)


# ---- AI gap-fill for parsed CSV / vision drafts ------------------------------
_ENRICH_LISTINGS_PROMPT = (
    "You help donors clean up bulk food-listing rows before they are published. "
    "For each row, FILL ONLY MISSING OR EMPTY OPTIONAL FIELDS. NEVER overwrite a "
    "field the user already provided.\n"
    "Allowed optional fields you may add: description (<=200 chars, neutral tone), "
    "dietary_tags (lowercase strings like 'vegetarian','vegan','gluten-free','halal','kosher'), "
    "allergens (lowercase strings like 'nuts','dairy','gluten','eggs','soy','shellfish'), "
    "expiry_date (ISO 'YYYY-MM-DD' guessed conservatively from category if absent).\n"
    "You MAY also correct an obviously-wrong category to one of "
    "['produce','bakery','dairy','pantry','meat','prepared','other'] — but ONLY if "
    "the existing value is missing or 'other'. Never invent allergens you cannot "
    "infer from the title/description.\n"
    "Output STRICT JSON: {\"rows\":[{...same fields..., \"_filled\":[\"field1\",...]}], "
    "\"summary\":\"short human sentence in the requested language\"}.\n"
    "Echo every input row, in order. Keep the user's title, quantity, and unit "
    "EXACTLY as given. Do NOT add image_url."
)


class EnrichListingsRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    rows: List[BulkListingItem] = Field(min_length=1, max_length=_MAX_BULK_LISTINGS)
    language: Optional[str] = Field(default="en", max_length=8)


def _row_for_enrich_prompt(item: BulkListingItem) -> dict:
    """Compact dict the model sees — drops empty fields so it knows what to fill."""
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


@app.post("/api/ai/enrich-listings")
async def ai_enrich_listings(body: EnrichListingsRequest, request: Request) -> dict:
    """
    Have the model fill in missing optional fields (description, dietary_tags,
    allergens, expiry_date, weak category) on parsed listing rows so the user
    sees a complete preview before confirming the bulk insert.

    Never overwrites user-provided values. If the AI service is unavailable,
    returns the original rows unchanged with a fallback summary.

    Returns: { rows: [...], summary: str, filled: [{index, fields:[...]}] }
    """
    _enforce_rate_limit(request)
    _validate_uuid(body.user_id)
    await _require_auth_for_user(request, body.user_id)
    originals = [item.model_dump() for item in body.rows]
    fallback = {
        "rows": originals,
        "summary": "AI gap-fill unavailable — rows returned unchanged.",
        "filled": [],
    }
    if not OPENAI_API_KEY:
        return fallback

    import json as _json
    compact = [_row_for_enrich_prompt(item) for item in body.rows]
    language = (body.language or "en").lower()[:2]
    user_msg = (
        f"Language for summary: {language}.\n"
        f"Rows to review (JSON array):\n{_json.dumps(compact, ensure_ascii=False)}"
    )

    from backend.ai_engine import _get_http_client, OPENAI_BASE_URL, FOLLOWUP_MODEL
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
    import asyncio as _asyncio
    try:
        data = None
        for attempt in range(3):
            resp = await client.post(
                f"{OPENAI_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            )
            if (resp.status_code == 429 or resp.status_code >= 500) and attempt < 2:
                await _asyncio.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            data = resp.json()
            break
        if data is None:
            return fallback
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

    # Merge AI suggestions onto the originals, NEVER overwriting user values.
    merged: List[dict] = []
    filled_log: List[dict] = []
    for idx, original in enumerate(originals):
        ai_row = ai_rows[idx] if idx < len(ai_rows) and isinstance(ai_rows[idx], dict) else {}
        out = dict(original)
        added_fields: List[str] = []

        # description / expiry_date / location — only if missing
        for f in ("description", "expiry_date", "location"):
            if not out.get(f) and ai_row.get(f):
                val = str(ai_row[f]).strip()
                if val:
                    if f == "expiry_date":
                        # Normalize AI-supplied date to YYYY-MM-DD so the row
                        # survives PostgreSQL's date column type check.
                        from backend.tools import _normalize_expiry_date as _ned2
                        norm_date = _ned2(val)
                        if norm_date:
                            out[f] = norm_date
                            added_fields.append(f)
                    else:
                        cap = 2000 if f == "description" else 200
                        out[f] = val[:cap]
                        added_fields.append(f)

        # dietary_tags / allergens — only if absent or empty
        for f in ("dietary_tags", "allergens"):
            existing = out.get(f) or []
            if (not existing or len(existing) == 0):
                ai_val = ai_row.get(f) or []
                if isinstance(ai_val, list) and ai_val:
                    clean = [str(t).strip().lower()[:40] for t in ai_val if str(t).strip()][:10]
                    if clean:
                        out[f] = clean
                        added_fields.append(f)

        # category — only escalate from 'other' / missing
        cur_cat = (out.get("category") or "").strip().lower()
        ai_cat = (ai_row.get("category") or "").strip().lower()
        if ai_cat in _VALID_FOOD_CATEGORIES and cur_cat in ("", "other") and ai_cat != cur_cat:
            out["category"] = ai_cat
            added_fields.append("category")

        merged.append(out)
        if added_fields:
            filled_log.append({"index": idx, "fields": added_fields})

    if not summary:
        n_rows = len(filled_log)
        if language == "es":
            summary = (
                f"Rellené {n_rows} fila(s) con datos faltantes." if n_rows
                else "No encontré huecos que rellenar."
            )
        else:
            summary = (
                f"Filled gaps on {n_rows} row(s)." if n_rows
                else "No gaps to fill — your rows look complete."
            )

    return {"rows": merged, "summary": summary, "filled": filled_log}


@app.post("/api/ai/bulk-listings")
async def ai_bulk_listings(body: BulkListingsRequest, request: Request) -> dict:
    """
    Create one or more food_listings rows from a vetted JSON payload
    (used by the chat UI's photo + CSV upload flow).

    Returns: { created: int, failed: int, ids: [uuid], errors: [{index, error}] }
    """
    _enforce_rate_limit(request)
    _validate_uuid(body.user_id)
    await _require_auth_for_user(request, body.user_id)
    donor = await fetch_donor_listing_defaults(body.user_id)
    # Geocode each row's own pickup address so it gets an accurate map pin
    # instead of always inheriting the donor's home coords. Falls back to the
    # donor defaults (applied in _normalize_listing_row) when a row has no
    # address or geocoding fails. Cache so a batch sharing an address hits
    # Mapbox once.
    from backend.tools import _forward_geocode
    geocode_cache: dict[str, tuple | None] = {}
    created_ids: List[str] = []
    errors: List[dict] = []
    for idx, item in enumerate(body.listings):
        try:
            addr = str(item.location or "").strip()
            pre_coords = None
            if addr:
                if addr not in geocode_cache:
                    geocode_cache[addr] = await _forward_geocode(addr)
                pre_coords = geocode_cache[addr]
            row = _normalize_listing_row(item, body.user_id, donor=donor)
            # Geocode BEFORE donor defaults so a failed geocode doesn't leave
            # the donor's home pin on a row with its own pickup address.
            if pre_coords:
                row["latitude"], row["longitude"] = pre_coords
            elif addr:
                # Row had its own address but geocoding failed — strip any
                # donor coords inherited by apply_donor_defaults_to_listing.
                row.pop("latitude", None)
                row.pop("longitude", None)
            result = await supabase_post("food_listings", row)
            if isinstance(result, list) and result:
                rid = result[0].get("id")
                if rid:
                    created_ids.append(str(rid))
                    continue
            errors.append({"index": idx, "error": "no row returned"})
        except Exception as exc:  # noqa: BLE001
            errors.append({"index": idx, "error": str(exc)[:200]})
    return {
        "created": len(created_ids),
        "failed": len(errors),
        "ids": created_ids,
        "errors": errors,
    }


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


@app.post("/api/ai/vision-listing")
async def ai_vision_listing(
    request: Request,
    user_id: str = Form(..., min_length=1, max_length=128),
    image: UploadFile = File(..., description="Photo of the food item (jpg/png/webp)"),
) -> dict:
    """
    Send a photo to GPT-4-class vision and return a draft food_listings row
    for the chat UI to preview + confirm before insert.

    Returns: { draft: {...listing fields...}, confidence: float, raw: string }
    """
    _enforce_rate_limit(request)
    _validate_uuid(user_id)
    await _require_auth_for_user(request, user_id)
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

    import base64 as _b64
    b64 = _b64.b64encode(raw).decode("ascii")
    data_url = f"data:{content_type};base64,{b64}"

    from backend.ai_engine import _get_http_client, OPENAI_BASE_URL, FOLLOWUP_MODEL
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
    import asyncio as _asyncio
    try:
        for attempt in range(3):
            resp = await client.post(
                f"{OPENAI_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            )
            if (resp.status_code == 429 or resp.status_code >= 500) and attempt < 2:
                await _asyncio.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            break
    except Exception as exc:  # noqa: BLE001
        logger.exception("vision-listing OpenAI call failed")
        raise HTTPException(status_code=502, detail=f"Vision call failed: {exc}") from exc

    data = resp.json()
    content_str = (data.get("choices") or [{}])[0].get("message", {}).get("content") or "{}"
    import json as _json
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

    # Pre-fill address / community / expiry so the photo flow lands a
    # complete listing instead of one missing pickup + freshness fields.
    # The Vision call itself only inspects the photo; these defaults come
    # from the donor's profile + a category-based expiry heuristic so the
    # user just confirms instead of typing them all in.
    try:
        donor = await fetch_donor_listing_defaults(user_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("vision-listing: donor lookup failed for %s: %s", user_id, exc)
        donor = {}
    if donor:
        donor_addr = str(donor.get("address") or "").strip()
        if donor_addr:
            draft["location"] = donor_addr[:200]
        if donor.get("community_id"):
            draft["community_id"] = str(donor["community_id"])

    # Suggest a sensible expiry the user can override before confirming.
    try:
        from backend.tools import _suggested_expiry_for_category
        draft["expiry_date"] = _suggested_expiry_for_category(category)
    except Exception as exc:  # noqa: BLE001
        logger.debug("vision-listing: expiry suggestion failed: %s", exc)

    return {
        "draft": draft,
        "confidence": confidence_val,
        "raw": content_str[:2000],
    }


@app.post("/api/ai/query")
async def ai_query(body: QueryRequest, request: Request) -> dict:
    """Natural-language Q&A grounded in safe Supabase tool calls."""
    _enforce_rate_limit(request)
    _validate_uuid(body.user_id)

    await _require_auth_for_user(request, body.user_id)

    # Resolve admin flag from DB (never trust client claims).
    user_rows = await supabase_get("users", {
        "select": "id,is_admin",
        "id": f"eq.{body.user_id}",
        "limit": "1",
    })
    is_admin = bool(((user_rows or [{}])[0] or {}).get("is_admin"))

    try:
        result = await _run_query_agent(
            question=body.question.strip(),
            user_id=body.user_id,
            is_admin=is_admin,
            max_steps=body.max_steps,
        )
    except HTTPException:
        raise
    except Exception as exc:
        rid = _request_id(request)
        logger.error("[%s] AI query failed: %s", rid, exc, exc_info=True)
        raise classify_exception(exc) from exc

    return {
        "question": body.question,
        "answer": result.get("answer") or "I couldn't find an answer for that.",
        "tool_trace": result.get("tool_trace") or [],
        "steps": result.get("steps") or 0,
        "is_admin": is_admin,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/health")
async def health() -> dict:
    ai_ok = bool(OPENAI_API_KEY)
    db_ok = bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)
    all_ok = ai_ok and db_ok
    metrics = _upstream_metrics.snapshot()
    return {
        "status": "ok" if all_ok else "degraded",
        "ai_configured": ai_ok,
        "database_configured": db_ok,
        "circuit_state": _circuit.state.value,
        "upstream": metrics,
        "error_rate_pct": metrics["error_rate_pct"],
        "error_rate_ok": metrics["within_threshold"],
    }


# Mirror under the /api/ai prefix so the Vite dev proxy can reach it.
@app.get("/api/ai/health")
async def health_ai() -> dict:
    return await health()


@app.post("/api/ai/reset-circuit")
async def reset_circuit(request: Request) -> dict:
    """Admin-only endpoint: clear the OpenAI circuit breaker so normal traffic
    resumes immediately instead of waiting for the cooldown timeout.

    Requires the ADMIN_RESET_TOKEN env var to be set; callers must supply it
    as a Bearer token so the endpoint cannot be abused publicly.
    """
    reset_token = os.getenv("ADMIN_RESET_TOKEN", "")
    if reset_token:
        auth_header = request.headers.get("Authorization", "")
        provided = auth_header.removeprefix("Bearer ").strip()
        if provided != reset_token:
            raise HTTPException(status_code=403, detail="Forbidden")

    prev_state = _circuit.state.value
    _circuit.record_success()  # forces state → CLOSED and resets failure_count
    logger.info("Circuit breaker manually reset via /api/ai/reset-circuit (was %s)", prev_state)
    return {
        "ok": True,
        "previous_state": prev_state,
        "current_state": _circuit.state.value,
    }

# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )

