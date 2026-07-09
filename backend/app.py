from fastapi import FastAPI, HTTPException, Depends, status, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey, Enum
from sqlalchemy.orm import Session, relationship
from sqlalchemy import text, func, case
from pydantic import BaseModel
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Optional, List, Dict, Any
from backend.aws_secrets import load_aws_secrets
from dotenv import load_dotenv
import hmac
import jwt
import json
import os
import secrets
import string
import subprocess
from urllib.parse import quote
from passlib.context import CryptContext
from backend.email_service import (
    send_reset_email,
    send_verification_email as send_verification_email_message,
)
from backend.schemas import (
    FoodResourceResponse,
    DistributionCenterCreate,
    DistributionCenterResponse,
    DistributionCenterWithInventory,
    CenterInventoryResponse,
    UserRegisterRequest,
    UserLoginRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
)
from backend.models import (
    Base, FoodResource, User, UserRole, FoodCategory, PerishabilityLevel,
    DistributionCenter, CenterInventory, Message, DonationSchedule, 
    DonationReminder, RecurrenceFrequency, ReminderStatus, Feedback,
    FeedbackType, FeedbackStatus, SafetyReport, ReportType, ReportStatus,
    PickupReminder, PickupReminderStatus, FavoriteLocation
)
# Register AI models on the shared Base so create_all() picks them up
from backend.ai import models as ai_models  # noqa: F401
from threading import Timer, Lock
from twilio.rest import Client
from backend.db import engine, SessionLocal, get_db

pwd_context = CryptContext(schemes=["argon2", "bcrypt"], deprecated="auto")

# Helper function to generate unique referral codes
def generate_referral_code():
    """Generate a unique 8-character referral code"""
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(8))

app = FastAPI(title="DoGoods Agentic API", version="1.0.0")
load_aws_secrets()
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# Serve static files at root paths for legacy HTML compatibility
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
# Static files will be mounted at the end of the file, after all routes
security = HTTPBearer()
# Optional bearer for endpoints where auth is not required but can tailor results
optional_security = HTTPBearer(auto_error=False)

# Twilio SMS configuration
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")  # Default Twilio number




# CORS middleware — read allowlist from CORS_ORIGINS env (comma-separated).
# The wildcard `*` used to be hard-coded here even though the env was
# already documented and populated, so every browser could hit the API
# from any origin. Now we default to a locked-down set of local origins
# and require ops to opt in to real production hostnames.
_cors_env = os.getenv("CORS_ORIGINS", "").strip()
if _cors_env == "*":
    # Explicit opt-in wildcard, still incompatible with credentials.
    _cors_origins: list[str] = ["*"]
    _cors_credentials = False
else:
    _cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()] or [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]
    _cors_credentials = True

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def secure_http_exception_handler(request: Request, exc: HTTPException):
    """Avoid leaking internal server details through HTTP 500 responses.

    :class:`~backend.ai.errors.AIError` subclasses ship a structured
    ``detail`` dict (``error_code`` / ``message`` / ``retryable`` / ``lang``);
    keep that payload intact — it is safe user-facing content, not a raw
    exception message. Generic 5xx exceptions still get their detail
    scrubbed to prevent leaking stack traces or DB messages.
    """
    from backend.ai.errors import AIError  # local import: avoid cycles at boot
    if isinstance(exc, AIError) and isinstance(exc.detail, dict):
        body: dict = dict(exc.detail)
        return JSONResponse(status_code=exc.status_code, content=body)
    if exc.status_code >= 500:
        return JSONResponse(status_code=exc.status_code, content={"detail": "Internal server error"})
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.middleware("http")
async def add_cache_control_headers(request: Request, call_next):
    """Avoid stale frontend assets requiring hard refreshes in development and production."""
    path = request.url.path
    relative_path = path.lstrip("/")
    # /uploads serves user-generated content (chat photos, listing images).
    # The directory is gitignored on purpose, but it MUST still be reachable
    # over HTTP — otherwise listing photos and AI chat attachments 404.
    is_uploads_asset = relative_path.startswith("uploads/") or relative_path == "uploads"
    if relative_path and not is_uploads_asset and (
        any(part.startswith(".") for part in relative_path.split("/") if part)
        or _is_gitignored_path(relative_path)
    ):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})

    response = await call_next(request)

    # Keep API responses unchanged; only control cache behavior for frontend routes/assets.
    path = path.lower()
    if not path.startswith("/api"):
        if path in {"/", ""} or path.endswith(".html"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        elif path.endswith((".js", ".css", ".map")):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

    return response

# NOTE: Use Base imported from models; do not re-declare another Base here
# JWT settings
JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET or len(JWT_SECRET) < 16:
    # Fail closed: refuse to start with a weak/missing JWT secret rather
    # than fall back to a known literal that anyone reading the source
    # could use to forge tokens.
    raise RuntimeError(
        "JWT_SECRET environment variable is required and must be at least "
        "16 characters long."
    )
JWT_ALGORITHM = "HS256"
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL")
if not PUBLIC_BASE_URL:
    raise RuntimeError("PUBLIC_BASE_URL environment variable is required")


def get_public_base_url() -> str:
    """Return the user-facing base URL configured in environment."""
    return PUBLIC_BASE_URL.rstrip("/")


@lru_cache(maxsize=4096)
def _is_gitignored_path(relative_path: str) -> bool:
    try:
        completed = subprocess.run(
            ["git", "-C", PROJECT_ROOT, "check-ignore", "-q", "--", relative_path],
            capture_output=True,
            check=False,
        )
        return completed.returncode == 0
    except OSError:
        return False


# Global request input constraints for API routes.
MAX_API_BODY_BYTES = 64 * 1024
# Per-path overrides for multipart upload endpoints whose handlers enforce
# their own size caps. Keep these slightly above the handler cap so we don't
# pre-empt the handler's friendlier error message.
UPLOAD_PATH_LIMITS = {
    "/api/ai/voice": 26 * 1024 * 1024,        # handler caps at 25MB
    "/api/ai/upload_image": 9 * 1024 * 1024,  # handler caps at 8MB
}


def _max_body_bytes_for(path: str) -> int:
    return UPLOAD_PATH_LIMITS.get(path.rstrip("/"), MAX_API_BODY_BYTES)


MAX_QUERY_STRING_BYTES = 2048
MAX_QUERY_PARAM_NAME_CHARS = 64
MAX_QUERY_PARAM_VALUE_CHARS = 512
MAX_JSON_STRING_CHARS = 5000
MAX_JSON_KEY_CHARS = 128
MAX_JSON_OBJECT_KEYS = 200
MAX_JSON_ARRAY_ITEMS = 500
MAX_JSON_NESTING_DEPTH = 20


def _contains_disallowed_control_chars(value: str) -> bool:
    for ch in value:
        code = ord(ch)
        if (code < 32 and ch not in {"\n", "\r", "\t"}) or code == 127:
            return True
    return False


def _sanitize_text(value: str, *, max_chars: int, label: str) -> str:
    if len(value) > max_chars:
        raise HTTPException(status_code=413, detail=f"{label} is too large")
    if _contains_disallowed_control_chars(value):
        raise HTTPException(status_code=400, detail=f"{label} contains invalid characters")
    return value.strip()


def _sanitize_json_payload(value: Any, depth: int = 0) -> Any:
    if depth > MAX_JSON_NESTING_DEPTH:
        raise HTTPException(status_code=400, detail="JSON payload is too deeply nested")

    if isinstance(value, dict):
        if len(value) > MAX_JSON_OBJECT_KEYS:
            raise HTTPException(status_code=413, detail="JSON object has too many fields")
        sanitized: Dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise HTTPException(status_code=400, detail="JSON object keys must be strings")
            clean_key = _sanitize_text(key, max_chars=MAX_JSON_KEY_CHARS, label="JSON field name")
            sanitized[clean_key] = _sanitize_json_payload(item, depth + 1)
        return sanitized

    if isinstance(value, list):
        if len(value) > MAX_JSON_ARRAY_ITEMS:
            raise HTTPException(status_code=413, detail="JSON array is too large")
        return [_sanitize_json_payload(item, depth + 1) for item in value]

    if isinstance(value, str):
        return _sanitize_text(value, max_chars=MAX_JSON_STRING_CHARS, label="JSON field value")

    # JSON scalar values allowed as-is.
    if isinstance(value, (int, float, bool)) or value is None:
        return value

    raise HTTPException(status_code=400, detail="Unsupported JSON value")


def _validate_query_params(request: Request) -> None:
    if len(request.url.query) > MAX_QUERY_STRING_BYTES:
        raise HTTPException(status_code=413, detail="Query string is too large")

    for key, value in request.query_params.multi_items():
        _sanitize_text(key, max_chars=MAX_QUERY_PARAM_NAME_CHARS, label="Query parameter name")
        _sanitize_text(value, max_chars=MAX_QUERY_PARAM_VALUE_CHARS, label="Query parameter value")


async def _set_request_body(request: Request, body: bytes) -> None:
    async def receive() -> dict:
        return {"type": "http.request", "body": body, "more_body": False}

    request._receive = receive


@app.middleware("http")
async def sanitize_api_input(request: Request, call_next):
    """Validate and sanitize user-provided API input before endpoint handlers run."""
    path = request.url.path.lower()

    # Starlette's BaseHTTPMiddleware does not translate HTTPException raised
    # inside the middleware into the normal FastAPI exception handlers — it
    # surfaces as a 500. Catch them here and return a proper JSONResponse.
    try:
        if path.startswith("/api"):
            _validate_query_params(request)

            max_body_bytes = _max_body_bytes_for(path)

            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    if int(content_length) > max_body_bytes:
                        raise HTTPException(status_code=413, detail="Request body is too large")
                except ValueError:
                    raise HTTPException(status_code=400, detail="Invalid Content-Length header")

            if request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
                body = await request.body()
                if len(body) > max_body_bytes:
                    raise HTTPException(status_code=413, detail="Request body is too large")

                if body:
                    content_type = request.headers.get("content-type", "").lower()

                    if "application/json" in content_type:
                        try:
                            parsed = json.loads(body.decode("utf-8"))
                        except UnicodeDecodeError:
                            raise HTTPException(status_code=400, detail="Request body must be valid UTF-8")
                        except json.JSONDecodeError:
                            raise HTTPException(status_code=400, detail="Malformed JSON request body")

                        sanitized_payload = _sanitize_json_payload(parsed)
                        sanitized_body = json.dumps(sanitized_payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
                        await _set_request_body(request, sanitized_body)
                    elif "application/x-www-form-urlencoded" in content_type:
                        try:
                            body.decode("utf-8")
                        except UnicodeDecodeError:
                            raise HTTPException(status_code=400, detail="Request body must be valid UTF-8")
                        # We consumed the body via request.body(); put it back so
                        # downstream form parsers can read it.
                        await _set_request_body(request, body)
                    else:
                        # multipart/form-data, application/octet-stream, etc.
                        # We've already consumed the body; re-inject it so the
                        # endpoint's UploadFile / Form parsers can read it.
                        await _set_request_body(request, body)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    return await call_next(request)


# Login rate limiting: max 5 attempts per 10-minute window.
LOGIN_RATE_LIMIT_MAX_ATTEMPTS = 5
LOGIN_RATE_LIMIT_WINDOW = timedelta(minutes=10)
login_attempts_by_key: Dict[str, List[datetime]] = {}
login_attempts_lock = Lock()

# Signup rate limiting: max 3 attempts per 30-minute window.
SIGNUP_RATE_LIMIT_MAX_ATTEMPTS = 3
SIGNUP_RATE_LIMIT_WINDOW = timedelta(minutes=30)
signup_attempts_by_ip: Dict[str, List[datetime]] = {}
signup_attempts_lock = Lock()

# Password reset flow rate limiting.
FORGOT_PASSWORD_RATE_LIMIT_MAX_ATTEMPTS = 5
RESET_PASSWORD_RATE_LIMIT_MAX_ATTEMPTS = 5
PASSWORD_RESET_RATE_LIMIT_WINDOW = timedelta(minutes=30)
forgot_password_attempts_by_key: Dict[str, List[datetime]] = {}
reset_password_attempts_by_key: Dict[str, List[datetime]] = {}
password_reset_attempts_lock = Lock()


def _client_ip(request: Request) -> str:
    """Best-effort client IP extraction with proxy header fallback."""
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _login_rate_limit_key(request: Request, email: Optional[str]) -> str:
    normalized_email = (email or "").strip().lower()
    ip = _client_ip(request)
    if normalized_email:
        return f"email:{normalized_email}|ip:{ip}"
    return f"ip:{ip}"


def enforce_login_rate_limit(request: Request, email: Optional[str]) -> None:
    """Allow up to LOGIN_RATE_LIMIT_MAX_ATTEMPTS login attempts in LOGIN_RATE_LIMIT_WINDOW."""
    now = datetime.utcnow()
    cutoff = now - LOGIN_RATE_LIMIT_WINDOW
    key = _login_rate_limit_key(request, email)

    with login_attempts_lock:
        attempts = [ts for ts in login_attempts_by_key.get(key, []) if ts > cutoff]

        if len(attempts) >= LOGIN_RATE_LIMIT_MAX_ATTEMPTS:
            retry_after_seconds = int((attempts[0] + LOGIN_RATE_LIMIT_WINDOW - now).total_seconds())
            if retry_after_seconds < 1:
                retry_after_seconds = 1
            raise HTTPException(
                status_code=429,
                detail=(
                    "Too many login attempts. "
                    f"Please try again in about {retry_after_seconds // 60 + (1 if retry_after_seconds % 60 else 0)} minute(s)."
                )
            )

        attempts.append(now)
        login_attempts_by_key[key] = attempts


def enforce_signup_rate_limit(request: Request) -> None:
    """Allow up to SIGNUP_RATE_LIMIT_MAX_ATTEMPTS signup attempts in SIGNUP_RATE_LIMIT_WINDOW."""
    now = datetime.utcnow()
    cutoff = now - SIGNUP_RATE_LIMIT_WINDOW
    ip = _client_ip(request)

    with signup_attempts_lock:
        attempts = [ts for ts in signup_attempts_by_ip.get(ip, []) if ts > cutoff]

        if len(attempts) >= SIGNUP_RATE_LIMIT_MAX_ATTEMPTS:
            retry_after_seconds = int((attempts[0] + SIGNUP_RATE_LIMIT_WINDOW - now).total_seconds())
            if retry_after_seconds < 1:
                retry_after_seconds = 1
            raise HTTPException(
                status_code=429,
                detail=(
                    "Too many signup attempts. "
                    f"Please try again in about {retry_after_seconds // 60 + (1 if retry_after_seconds % 60 else 0)} minute(s)."
                )
            )

        attempts.append(now)
        signup_attempts_by_ip[ip] = attempts


def _ip_email_key(request: Request, email: Optional[str]) -> str:
    ip = _client_ip(request)
    email_part = (email or "").strip().lower()
    return f"ip:{ip}|email:{email_part or '-'}"


def _enforce_attempt_rate_limit(
    attempts_store: Dict[str, List[datetime]],
    max_attempts: int,
    request: Request,
    email: Optional[str],
    action_label: str,
) -> None:
    now = datetime.utcnow()
    cutoff = now - PASSWORD_RESET_RATE_LIMIT_WINDOW
    key = _ip_email_key(request, email)

    with password_reset_attempts_lock:
        attempts = [ts for ts in attempts_store.get(key, []) if ts > cutoff]
        if len(attempts) >= max_attempts:
            retry_after_seconds = int((attempts[0] + PASSWORD_RESET_RATE_LIMIT_WINDOW - now).total_seconds())
            if retry_after_seconds < 1:
                retry_after_seconds = 1
            retry_minutes = retry_after_seconds // 60 + (1 if retry_after_seconds % 60 else 0)
            raise HTTPException(
                status_code=429,
                detail=f"Too many {action_label} attempts. Please try again in about {retry_minutes} minute(s).",
            )

        attempts.append(now)
        attempts_store[key] = attempts


def enforce_forgot_password_rate_limit(request: Request, email: Optional[str]) -> None:
    _enforce_attempt_rate_limit(
        forgot_password_attempts_by_key,
        FORGOT_PASSWORD_RATE_LIMIT_MAX_ATTEMPTS,
        request,
        email,
        "password reset request",
    )


def enforce_reset_password_rate_limit(request: Request, email: Optional[str]) -> None:
    _enforce_attempt_rate_limit(
        reset_password_attempts_by_key,
        RESET_PASSWORD_RATE_LIMIT_MAX_ATTEMPTS,
        request,
        email,
        "password reset",
    )

# -----------------------------
# Serialization helpers
# -----------------------------

def serialize_user(user: Optional[User]) -> Optional[dict]:
    """Return a safe, minimal representation of a User for client responses."""
    if not user:
        return None
    try:
        return {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role.value if getattr(user, "role", None) else None,
            "phone": getattr(user, "phone", None),
            "address": getattr(user, "address", None),
            "coords_lat": getattr(user, "coords_lat", None),
            "coords_lng": getattr(user, "coords_lng", None),
            "created_at": user.created_at.isoformat() if getattr(user, "created_at", None) else None,
            # Trust signals
            "trust_score": getattr(user, "trust_score", 50),
            "verified_by_aglf": getattr(user, "verified_by_aglf", False),
            "school_partner": getattr(user, "school_partner", False),
            "partner_badge": getattr(user, "partner_badge", None),
            "partner_since": user.partner_since.isoformat() if getattr(user, "partner_since", None) else None,
            "last_active": user.last_active.isoformat() if getattr(user, "last_active", None) else None,
        }
    except Exception:
        # Best-effort fallback to avoid breaking responses
        return {"id": getattr(user, "id", None), "name": getattr(user, "name", None)}


def serialize_listing(item: FoodResource, include_donor: bool = True, include_donor_contact: bool = False) -> dict:
    """Return a safe, client-friendly listing dict. Converts enums/datetimes and includes donor if available."""
    # Only include full donor details if listing is claimed, otherwise just include basic info
    donor_payload = None
    if include_donor and getattr(item, "donor", None):
        if include_donor_contact or item.status == 'claimed':
            donor_payload = serialize_user(item.donor)
        else:
            # For non-claimed listings, only include donor ID, not contact info
            donor_payload = {"id": item.donor.id} if item.donor else None
    
    # Enum helpers
    def ev(v):
        try:
            # If it's already an enum, get its value
            if hasattr(v, 'value'):
                return v.value
            # If it's a string, return as-is (might be enum value already stored as string)
            if isinstance(v, str):
                return v
            return v if v is not None else None
        except Exception:
            # Already a string or unexpected type
            return v

    # Parse images JSON column to a Python list (best effort)
    images_list = []
    raw_images = getattr(item, "images", None)
    if raw_images:
        if isinstance(raw_images, list):
            images_list = [str(x) for x in raw_images if isinstance(x, (str, bytes))]
        else:
            try:
                parsed_imgs = json.loads(raw_images)
                if isinstance(parsed_imgs, list):
                    images_list = [str(x) for x in parsed_imgs if isinstance(x, str)]
            except Exception:
                images_list = []

    return {
        "id": item.id,
        "donor_id": getattr(item, "donor_id", None),
        "recipient_id": getattr(item, "recipient_id", None),
        "title": getattr(item, "title", None),
        "description": getattr(item, "description", None),
        "category": ev(getattr(item, "category", None)),
        "qty": getattr(item, "qty", None),
        "unit": getattr(item, "unit", None),
        "perishability": ev(getattr(item, "perishability", None)),
        "expiration_date": item.expiration_date.isoformat() if getattr(item, "expiration_date", None) else None,
        "date_label_type": getattr(item, "date_label_type", None),
        "address": getattr(item, "address", None),
        "coords_lat": getattr(item, "coords_lat", None),
        "coords_lng": getattr(item, "coords_lng", None),
        "pickup_window_start": item.pickup_window_start.isoformat() if getattr(item, "pickup_window_start", None) else None,
        "pickup_window_end": item.pickup_window_end.isoformat() if getattr(item, "pickup_window_end", None) else None,
        "status": getattr(item, "status", None),
        "claimed_at": item.claimed_at.isoformat() if getattr(item, "claimed_at", None) else None,
        "urgency_score": getattr(item, "urgency_score", 0) or 0,
        "created_at": item.created_at.isoformat() if getattr(item, "created_at", None) else None,
        "updated_at": item.updated_at.isoformat() if getattr(item, "updated_at", None) else None,
        "verification_status": ev(getattr(item, "verification_status", None)),
        "is_refrigerated": getattr(item, "is_refrigerated", False) or False,
        "is_frozen": getattr(item, "is_frozen", False) or False,
        "safety_checklist_passed": getattr(item, "safety_checklist_passed", False) or False,
        "packaging_condition": getattr(item, "packaging_condition", "unknown"),
        "allergens": getattr(item, "allergens", None),
        "contamination_warning": getattr(item, "contamination_warning", None),
        "dietary_tags": getattr(item, "dietary_tags", None),
        "ingredients_list": getattr(item, "ingredients_list", None),
        "images": images_list,
        "donor": donor_payload,
    }

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

def verify_admin(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    """Verify user is authenticated and has admin role"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub")) if payload and payload.get("sub") is not None else None
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user = db.query(User).filter(User.id == user_id).first()
        if not user or user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Admin access required")
        
        return user
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Authorization error")


import os
HTML_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

def get_html_content(filename):
    filepath = os.path.join(HTML_DIR, filename)
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()

@app.get("/", response_class=HTMLResponse)
async def serve_landing():
    return get_html_content("landing.html")

@app.get("/index.html", response_class=HTMLResponse)
async def serve_index():
    return get_html_content("index.html")

@app.get("/privacy.html", response_class=HTMLResponse)
async def serve_privacy():
    return get_html_content("privacy.html")

@app.get("/dispatch.html", response_class=HTMLResponse)
async def serve_dispatch():
    return get_html_content("dispatch.html")

@app.get("/cookies.html", response_class=HTMLResponse)
async def serve_cookies():
    return get_html_content("cookies.html")

@app.get("/terms.html", response_class=HTMLResponse)
async def serve_terms():
    return get_html_content("terms.html")

@app.get("/impactStory.html", response_class=HTMLResponse)
async def serve_impact_story():
    return get_html_content("impactStory.html")

@app.get("/admin-referrals.html", response_class=HTMLResponse)
async def serve_admin_referrals():
    return get_html_content("admin-referrals.html")

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now()}

# -----------------------------
# User profile helper endpoints
# -----------------------------

@app.get("/api/user/me")
async def get_me(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub")) if payload and payload.get("sub") is not None else None
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role.value if user.role else None,
            "phone": user.phone,
            "address": user.address,
            "coords_lat": user.coords_lat,
            "coords_lng": user.coords_lng,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "dietary_restrictions": user.dietary_restrictions,
            "allergies": user.allergies,
            "household_size": user.household_size,
            "preferred_categories": user.preferred_categories,
            "special_needs": user.special_needs
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/user/profile")
@app.get("/user/profile")
async def get_user_profile(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    """Backward-compatible profile read endpoint used by frontend and some deployments.

    Includes both /api/user/profile and /user/profile to tolerate proxies that strip /api.
    """
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub")) if payload and payload.get("sub") is not None else None
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role.value if user.role else None,
            "phone": user.phone,
            "address": user.address,
            "coords_lat": user.coords_lat,
            "coords_lng": user.coords_lng,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "dietary_restrictions": user.dietary_restrictions,
            "allergies": user.allergies,
            "household_size": user.household_size,
            "preferred_categories": user.preferred_categories,
            "special_needs": user.special_needs,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/user/phone")
async def update_phone(request: Request, credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub")) if payload and payload.get("sub") is not None else None
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        body = await request.json()
        phone = (body or {}).get("phone") if isinstance(body, dict) else None
        if not phone or not isinstance(phone, str) or len(phone.strip()) < 7:
            raise HTTPException(status_code=422, detail="Please provide a valid phone number")
        phone = phone.strip()
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user.phone = phone
        db.add(user)
        db.commit()
        return {"success": True, "phone": phone}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/user/profile")
async def update_profile(request: Request, credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub")) if payload and payload.get("sub") is not None else None
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        body = await request.json()
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        if 'name' in body:
            user.name = body['name']
        if 'email' in body:
            user.email = body['email']
        if 'phone' in body:
            user.phone = body['phone']
        if 'address' in body:
            user.address = body['address']
        
        # Dietary needs and preferences
        if 'dietary_restrictions' in body:
            user.dietary_restrictions = body['dietary_restrictions']
        if 'allergies' in body:
            user.allergies = body['allergies']
        if 'household_size' in body:
            user.household_size = body['household_size']
        if 'preferred_categories' in body:
            user.preferred_categories = body['preferred_categories']
        if 'special_needs' in body:
            user.special_needs = body['special_needs']
        
        # Allow role switching between donor, recipient, driver (but not admin/dispatcher)
        if 'role' in body:
            new_role = body['role']
            allowed_roles = ['donor', 'recipient', 'driver', 'volunteer']
            if new_role in allowed_roles:
                user.role = UserRole(new_role)
        
        db.commit()
        db.refresh(user)
        
        return {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "phone": user.phone,
            "address": user.address,
            "role": user.role.value if user.role else None,
            "dietary_restrictions": user.dietary_restrictions,
            "allergies": user.allergies,
            "household_size": user.household_size,
            "preferred_categories": user.preferred_categories,
            "special_needs": user.special_needs
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/user/change-password")
async def change_password(request: Request, credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub")) if payload and payload.get("sub") is not None else None
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        body = await request.json()
        current_password = body.get('current_password')
        new_password = body.get('new_password')
        
        if not current_password or not new_password:
            raise HTTPException(status_code=400, detail="Current and new passwords required")
        
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Verify current password
        if not pwd_context.verify(current_password, user.password_hash):
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        
        # Update password
        user.password_hash = pwd_context.hash(new_password)
        db.commit()
        
        return {"success": True, "message": "Password changed successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/admin/make-admin")
async def make_user_admin(request: Request, db: Session = Depends(get_db)):
    """Make a user an admin by email - temporary endpoint for setup"""
    try:
        body = await request.json()
        email = body.get('email')
        secret = body.get('secret')

        # Fail-closed: if ADMIN_SECRET is not configured, the endpoint is
        # disabled. Previously this fell back to a hardcoded literal which,
        # in any environment that hadn't set the env var, allowed anyone
        # who read the source to escalate to admin.
        admin_secret = os.getenv('ADMIN_SECRET')
        if not admin_secret or len(admin_secret) < 16:
            raise HTTPException(
                status_code=503,
                detail="Admin bootstrap endpoint disabled (ADMIN_SECRET not configured).",
            )
        if not secret or not hmac.compare_digest(str(secret), admin_secret):
            raise HTTPException(status_code=403, detail="Invalid secret")
        
        if not email:
            raise HTTPException(status_code=400, detail="Email required")
        
        user = db.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        user.role = UserRole.ADMIN
        db.commit()
        
        return {
            "success": True,
            "message": f"User {user.name} ({user.email}) is now an admin"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Mount AI router (DoGoods AI assistant — Nouri)
from backend.ai.routes import router as ai_router, start_background_jobs as ai_start_jobs, stop_background_jobs as ai_stop_jobs
app.include_router(ai_router)

# Create tables
@app.on_event("startup")
async def startup_event():
    # Ensure tables exist
    Base.metadata.create_all(bind=engine)
    # Recover any listings stuck in 'pending_confirmation' from a previous
    # process. The confirmation code lives only in the in-memory
    # pending_confirmations dict, which is wiped on restart, so those
    # listings would otherwise be unclaimable AND unreleasable until the
    # donor manually deletes them. Reset them so other recipients can claim.
    try:
        recovery_db = SessionLocal()
        try:
            recovered = (
                recovery_db.query(FoodResource)
                .filter(FoodResource.status == "pending_confirmation")
                .update(
                    {
                        FoodResource.status: "available",
                        FoodResource.recipient_id: None,
                        FoodResource.claimed_at: None,
                    },
                    synchronize_session=False,
                )
            )
            recovery_db.commit()
            if recovered:
                print(f"\u23f0 Released {recovered} stale 'pending_confirmation' listings on startup")
        finally:
            recovery_db.close()
    except Exception as _recover_exc:
        print(f"Stale-claim recovery skipped: {_recover_exc}")
    # Start AI background reminder loop
    try:
        await ai_start_jobs()
    except Exception as _ai_exc:
        print(f"AI background jobs failed to start: {_ai_exc}")
    # MySQL column additions (best-effort, ignore if already exists)
    try:
        with engine.connect() as conn:
            # Add missing columns if they don't exist
            try:
                conn.execute(text("ALTER TABLE food_resources ADD COLUMN recipient_id INT NULL"))
            except Exception:
                pass  # Column already exists
            try:
                conn.execute(text("ALTER TABLE food_resources ADD COLUMN claimed_at DATETIME NULL"))
            except Exception:
                pass  # Column already exists
            
            # Create favorite_locations table if it doesn't exist
            try:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS favorite_locations (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        user_id INT NOT NULL,
                        name VARCHAR(255) NOT NULL,
                        address VARCHAR(500),
                        coords_lat FLOAT,
                        coords_lng FLOAT,
                        location_type VARCHAR(50) DEFAULT 'general',
                        donor_id INT NULL,
                        center_id INT NULL,
                        notes TEXT,
                        tags TEXT,
                        visit_count INT DEFAULT 0,
                        last_visited DATETIME NULL,
                        notify_new_listings BOOLEAN DEFAULT FALSE,
                        notification_radius_km FLOAT DEFAULT 5.0,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        is_active BOOLEAN DEFAULT TRUE,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                        FOREIGN KEY (donor_id) REFERENCES users(id) ON DELETE SET NULL,
                        FOREIGN KEY (center_id) REFERENCES distribution_centers(id) ON DELETE SET NULL,
                        INDEX idx_user_id (user_id),
                        INDEX idx_donor_id (donor_id),
                        INDEX idx_center_id (center_id),
                        INDEX idx_location_type (location_type),
                        INDEX idx_is_active (is_active)
                    )
                """))
                print("✅ favorite_locations table created/verified")
            except Exception as e:
                print(f"Note: favorite_locations table migration: {e}")
                pass  # Table likely already exists
            
            conn.commit()
    except Exception as e:
        try:
            print(f"Startup migration warning: {e}")
        except Exception:
            pass

@app.get("/api/dbtest")
async def db_test(admin_user: "User" = Depends(verify_admin)):
    """Health probe for the database connection (admin-only).

    Previously this endpoint was public and returned the raw exception
    string, which leaked schema names, driver internals, and sometimes
    connection URIs. It is now gated behind ``verify_admin`` and returns
    only a boolean plus a redacted error code so ops tooling can still
    detect outages without exposing surface area to unauthenticated
    scrapers.

    :param admin_user: injected by ``verify_admin``; unused directly but
        FastAPI evaluates the dependency first, which rejects
        non-admin callers before we touch the DB.
    """
    del admin_user  # dependency side-effect only
    db = None
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        return {"success": True, "message": "Database connection successful"}
    except Exception as exc:
        print(f"dbtest failed: {exc!r}")
        return {"success": False, "error": "connection_failed"}
    finally:
        if db is not None:
            db.close()


@app.get("/api/listings/get")
def get_listings(
    limit: int = 100,
    db: Session = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_security)
):
    """
    Returns ALL food resources for authenticated users to filter on frontend.
    - Recipients see: all available + their claimed listings
    - Donors see: all their listings (available, claimed, expired)
    - Unauthenticated: only available listings
    """
    payload = None
    if credentials is not None:
        try:
            payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        except jwt.ExpiredSignatureError:
            print("JWT token expired")
            raise HTTPException(status_code=401, detail="Invalid token")
        except jwt.InvalidTokenError as e:
            print(f"JWT token invalid: {e}")
            raise HTTPException(status_code=401, detail="Invalid token")
        except Exception as e:
            print(f"JWT decode error: {e}")
            raise HTTPException(status_code=401, detail="Invalid token")
    try:
        user_id = None
        user_role = None
        
        # Use decoded JWT payload if provided
        if payload is not None:
            user_id = str(payload.get("sub")) if payload else None
            user_role = str(payload.get("role") or "").lower() if payload else None

        # Return ALL listings - let frontend filter
        # This allows proper filtering for donors to see expired/claimed items
        listings = (
            db.query(FoodResource)
            .order_by(FoodResource.created_at.desc())
            .limit(limit)
        ).all()

        def _to_timestamp(value):
            if not value:
                return None
            try:
                ts = datetime.fromisoformat(str(value).replace('Z', '+00:00')).timestamp()
                return ts
            except Exception:
                return None

        def _effective_status(serialized_listing):
            raw_status = str(serialized_listing.get('status') or '').lower()
            if raw_status and raw_status != 'available':
                return raw_status

            deadlines = [
                _to_timestamp(serialized_listing.get('pickup_window_end')),
                _to_timestamp(serialized_listing.get('expiration_date')),
            ]
            deadlines = [d for d in deadlines if d is not None]

            if deadlines and min(deadlines) <= datetime.now().timestamp():
                return 'expired'

            return raw_status or 'available'

        # Serialize listings and apply role-aware visibility rules.
        result = []
        for listing in listings:
            try:
                serialized = serialize_listing(listing, include_donor=True, include_donor_contact=False)

                effective_status = _effective_status(serialized)
                serialized['status'] = effective_status

                if user_role == 'recipient':
                    recipient_id = serialized.get('recipient_id')
                    is_claimed = effective_status in ('claimed', 'pending_confirmation')
                    is_mine = user_id is not None and recipient_id is not None and str(recipient_id) == str(user_id)

                    # Recipients may only see available listings and listings claimed by themselves.
                    if not (effective_status == 'available' or (is_claimed and is_mine)):
                        continue

                result.append(serialized)
            except Exception as e:
                print(f"Error serializing listing {listing.id}: {e}")
                continue

        return result
    except Exception as e:
        # Inline logging for easier diagnostics in environments without log collection
        try:
            print(f"/api/listings/get error: {e}")
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Failed to fetch listings")

@app.delete("/api/listings/get/{listing_id}")
async def delete_listing(listing_id: int, db: Session = Depends(get_db), credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Delete a listing. Donor who created it or admin can delete."""
    try:
        item = db.query(FoodResource).filter(FoodResource.id == listing_id).first()
        if not item:
            raise HTTPException(status_code=404, detail="Listing not found")

        # Authorization: donor who created it or admin can delete
        try:
            payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            user_id = str(payload.get("sub")) if payload else None
            if not user_id:
                raise HTTPException(status_code=401, detail="Your session is missing or expired. Please sign in to continue.")
            
            # Check if user is the owner or an admin
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                raise HTTPException(status_code=401, detail="User not found")
            
            is_owner = str(item.donor_id) == user_id
            role_value = user.role.value if hasattr(user.role, "value") else str(user.role or "")
            is_admin = role_value.lower() == UserRole.ADMIN.value
            
            if not (is_owner or is_admin):
                raise HTTPException(status_code=403, detail="Not authorized to delete this listing")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=401, detail="Your session is missing or expired. Please sign in to continue.")

        # Clear dependent rows that reference this listing to avoid MySQL
        # FK integrity errors. Use raw SQL so this is independent of which
        # ORM models happen to be imported. Nullable FKs are nulled out;
        # non-nullable FKs (pickup_reminders.listing_id) require deleting.
        from sqlalchemy import text as _sql_text
        try:
            db.execute(_sql_text("UPDATE consumption_logs SET food_resource_id = NULL WHERE food_resource_id = :lid"), {"lid": listing_id})
        except Exception as dep_err:
            print(f"delete_listing: failed to null consumption_logs for {listing_id}: {dep_err}")
        try:
            db.execute(_sql_text("UPDATE safety_reports SET listing_id = NULL WHERE listing_id = :lid"), {"lid": listing_id})
        except Exception as dep_err:
            print(f"delete_listing: failed to null safety_reports for {listing_id}: {dep_err}")
        try:
            db.execute(_sql_text("UPDATE ai_broadcasts SET food_resource_id = NULL WHERE food_resource_id = :lid"), {"lid": listing_id})
        except Exception as dep_err:
            print(f"delete_listing: failed to null ai_broadcasts for {listing_id}: {dep_err}")
        try:
            db.execute(_sql_text("DELETE FROM pickup_reminders WHERE listing_id = :lid"), {"lid": listing_id})
        except Exception as dep_err:
            print(f"delete_listing: failed to delete pickup_reminders for {listing_id}: {dep_err}")

        db.delete(item)
        db.commit()

        return {"success": True, "message": "Listing deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"DELETE /api/listings/get/{listing_id} error: {e}")
        traceback.print_exc()
        try:
            db.rollback()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/listings/recommended")
async def get_recommended_listings(
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get personalized food recommendations based on user's dietary needs and preferences.
    Filters out allergens and prioritizes preferred categories.
    """
    try:
        # Decode JWT to get user
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub")) if payload and payload.get("sub") is not None else None
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Parse dietary preferences
        import json
        
        dietary_restrictions = []
        allergies = []
        preferred_categories = []
        
        try:
            if user.dietary_restrictions:
                dietary_restrictions = json.loads(user.dietary_restrictions) if isinstance(user.dietary_restrictions, str) else user.dietary_restrictions
        except:
            pass
            
        try:
            if user.allergies:
                allergies = json.loads(user.allergies) if isinstance(user.allergies, str) else user.allergies
        except:
            pass
            
        try:
            if user.preferred_categories:
                preferred_categories = json.loads(user.preferred_categories) if isinstance(user.preferred_categories, str) else user.preferred_categories
        except:
            pass
        
        # Get all available listings
        listings = db.query(FoodResource).filter(FoodResource.status == "available").all()
        
        # Score each listing based on dietary compatibility
        scored_listings = []
        for listing in listings:
            score = 0
            skip = False
            
            # Load mock data to check dietary_info and allergens
            # In real app, this would be stored in database
            # For now, we'll use basic category matching
            
            # Preferred category bonus (high priority)
            if listing.category and listing.category.value in preferred_categories:
                score += 50
            
            # Dietary restrictions matching
            # Check listing description/title for keywords
            listing_text = (listing.title or '').lower() + ' ' + (listing.description or '').lower()
            
            for restriction in dietary_restrictions:
                restriction_lower = restriction.lower()
                if restriction_lower == 'vegetarian':
                    # Avoid meat keywords
                    if any(word in listing_text for word in ['meat', 'chicken', 'beef', 'pork', 'fish', 'salmon']):
                        score -= 30
                    if any(word in listing_text for word in ['vegetarian', 'vegan', 'veggie', 'produce', 'fruit']):
                        score += 20
                elif restriction_lower == 'vegan':
                    if any(word in listing_text for word in ['vegan', 'plant-based']):
                        score += 30
                    if any(word in listing_text for word in ['dairy', 'cheese', 'milk', 'egg', 'meat', 'chicken', 'fish']):
                        score -= 40
                elif restriction_lower == 'gluten-free':
                    if 'gluten' in listing_text or 'bread' in listing_text or 'pasta' in listing_text:
                        score -= 20
                    if 'gluten-free' in listing_text:
                        score += 25
                elif restriction_lower == 'halal':
                    if 'halal' in listing_text:
                        score += 30
                    if 'pork' in listing_text:
                        skip = True
                elif restriction_lower == 'kosher':
                    if 'kosher' in listing_text:
                        score += 30
                    if 'pork' in listing_text or 'shellfish' in listing_text:
                        skip = True
            
            # Allergy filtering (critical - skip if allergen present)
            for allergy in allergies:
                allergy_lower = allergy.lower()
                # Check for common allergen keywords
                if allergy_lower in ['peanuts', 'tree nuts', 'nuts']:
                    if any(word in listing_text for word in ['peanut', 'almond', 'walnut', 'cashew', 'nut']):
                        skip = True
                        break
                elif allergy_lower in ['dairy', 'milk']:
                    if any(word in listing_text for word in ['dairy', 'milk', 'cheese', 'yogurt', 'cream']):
                        skip = True
                        break
                elif allergy_lower in ['eggs', 'egg']:
                    if 'egg' in listing_text:
                        skip = True
                        break
                elif allergy_lower == 'soy':
                    if 'soy' in listing_text or 'tofu' in listing_text:
                        skip = True
                        break
                elif allergy_lower in ['wheat/gluten', 'wheat', 'gluten']:
                    if any(word in listing_text for word in ['wheat', 'gluten', 'bread', 'pasta']):
                        skip = True
                        break
                elif allergy_lower in ['fish', 'shellfish', 'seafood']:
                    if any(word in listing_text for word in ['fish', 'salmon', 'tuna', 'shellfish', 'shrimp', 'crab', 'lobster']):
                        skip = True
                        break
            
            if not skip:
                # Household size matching (bonus for appropriate quantities)
                household_size = user.household_size or 1
                if listing.qty:
                    # Ideal portion: 1-3 servings per person
                    ideal_qty = household_size * 2
                    qty_diff = abs(listing.qty - ideal_qty)
                    if qty_diff < 5:
                        score += 10
                
                # Proximity bonus (if user has location)
                if user.coords_lat and user.coords_lng and listing.coords_lat and listing.coords_lng:
                    # Simple distance calculation (rough approximation)
                    import math
                    lat_diff = user.coords_lat - listing.coords_lat
                    lng_diff = user.coords_lng - listing.coords_lng
                    distance = math.sqrt(lat_diff**2 + lng_diff**2) * 69  # Rough miles
                    
                    if distance < 2:
                        score += 30
                    elif distance < 5:
                        score += 20
                    elif distance < 10:
                        score += 10
                
                # Freshness/urgency bonus
                if listing.perishability and listing.perishability.value == 'high':
                    score += 5  # Slight bonus for fresh food
                
                scored_listings.append({
                    'listing': listing,
                    'score': score
                })
        
        # Sort by score (highest first)
        scored_listings.sort(key=lambda x: x['score'], reverse=True)
        
        # Return top recommendations
        top_listings = [item['listing'] for item in scored_listings[:20]]
        
        # Ensure donor relationship is loaded
        for listing in top_listings:
            _ = listing.donor
        
        return {
            'listings': top_listings,
            'user_preferences': {
                'dietary_restrictions': dietary_restrictions,
                'allergies': allergies,
                'preferred_categories': preferred_categories,
                'household_size': user.household_size
            },
            'total_matches': len(scored_listings)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in recommended listings: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/listings/get/{listing_id}")
async def update_listing(listing_id: int, request: Request, db: Session = Depends(get_db), credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Update a listing's editable fields. Attempts server-side geocoding if address is provided and coords missing."""
    try:
        item = db.query(FoodResource).filter(FoodResource.id == listing_id).first()
        if not item:
            raise HTTPException(status_code=404, detail="Listing not found")

        # Authorization: only the donor who created the listing can edit
        try:
            payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            user_id = str(payload.get("sub")) if payload else None
            if not user_id or str(item.donor_id) != user_id:
                raise HTTPException(status_code=403, detail="Not authorized to edit this listing")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=401, detail="Your session is missing or expired. Please sign in to continue.")

        body = {}
        try:
            body = await request.json()
        except Exception:
            body = {}

        # Track whether address changed
        address_changed = False
        title = body.get('title') if 'title' in body else None
        desc = body.get('desc') if 'desc' in body else None
        category_val = body.get('category') if 'category' in body else None
        qty = body.get('qty') if 'qty' in body else None
        unit = body.get('unit') if 'unit' in body else None
        perishability_val = body.get('perishability') if 'perishability' in body else None
        pickup_start_provided = 'pickup_start' in body
        pickup_end_provided = 'pickup_end' in body
        expiration_date_provided = 'expiration_date' in body
        recipient_id_provided = 'recipient_id' in body
        pickup_start = body.get('pickup_start') if pickup_start_provided else None
        pickup_end = body.get('pickup_end') if pickup_end_provided else None
        expiration_date = body.get('expiration_date') if expiration_date_provided else None
        status = body.get('status') if 'status' in body else None
        recipient_id = body.get('recipient_id') if recipient_id_provided else None
        address = body.get('address') if 'address' in body else None

        if title is not None:
            item.title = title
        if desc is not None:
            item.description = desc
        if category_val is not None:
            try:
                item.category = category_val
            except Exception:
                pass
        if qty is not None:
            try:
                item.qty = float(qty)
            except Exception:
                pass
        if unit is not None:
            item.unit = unit
        if perishability_val is not None:
            try:
                item.perishability = perishability_val
            except Exception:
                pass
        if pickup_start_provided:
            item.pickup_window_start = pickup_start
        if pickup_end_provided:
            item.pickup_window_end = pickup_end
        if expiration_date_provided:
            item.expiration_date = expiration_date
        if status is not None:
            item.status = status
        if recipient_id_provided:
            item.recipient_id = recipient_id
        if address is not None and address != item.address:
            item.address = address
            address_changed = True

        # Optional images update: accept a list of URL strings or a JSON
        # string. Apply the same validation as create.
        if 'images' in body:
            raw_imgs = body.get('images')
            try:
                if isinstance(raw_imgs, str):
                    raw_imgs = json.loads(raw_imgs)
            except Exception:
                raw_imgs = None
            if isinstance(raw_imgs, list):
                cleaned = []
                for u in raw_imgs:
                    if not isinstance(u, str):
                        continue
                    s = u.strip()
                    if not s or len(s) > 1024:
                        continue
                    if not (s.startswith("/uploads/") or s.startswith("http://") or s.startswith("https://")):
                        continue
                    cleaned.append(s)
                    if len(cleaned) >= 8:
                        break
                item.images = json.dumps(cleaned) if cleaned else None
            elif raw_imgs is None or raw_imgs == [] or raw_imgs == "":
                item.images = None

        # If coords missing or address changed, attempt geocoding
        try:
            if (item.coords_lat is None or item.coords_lng is None or address_changed) and item.address:
                MAPBOX_TOKEN = os.getenv("MAPBOX_TOKEN")
                if MAPBOX_TOKEN:
                    from urllib.parse import quote as urlquote
                    import httpx
                    geocode_url = "https://api.mapbox.com/geocoding/v5/mapbox.places/{}.json".format(urlquote(item.address))
                    params = {"access_token": MAPBOX_TOKEN, "limit": 1, "type": "address"}
                    with httpx.Client(timeout=10.0) as client:
                        resp = client.get(geocode_url, params=params)
                        if resp.status_code == 200:
                            data = resp.json()
                            features = data.get("features") or []
                            if len(features) > 0:
                                center = features[0].get("center")
                                if center and len(center) >= 2:
                                    item.coords_lng = float(center[0])
                                    item.coords_lat = float(center[1])
        except Exception as ge:
            try:
                print(f"Geocoding error for address {item.address}: {ge}")
            except Exception:
                pass

        item.updated_at = datetime.utcnow()
        db.add(item)
        db.commit()
        db.refresh(item)

        return {"success": True, "listing": serialize_listing(item)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/user/create")
async def create_user(payload: UserRegisterRequest, request: Request, db: Session = Depends(get_db)):
    try:    
        enforce_signup_rate_limit(request)

        email = payload.email
        password = payload.password
        referral_code = payload.referral_code
        try:
            role = UserRole(payload.role)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid role")

        # Check for existing user
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # Validate referral code if provided
        referrer_id = None
        if referral_code:
            referrer = db.query(User).filter(User.referral_code == referral_code).first()
            if not referrer:
                raise HTTPException(status_code=400, detail="Invalid referral code")
            referrer_id = referrer.id
        
        # Generate unique referral code for new user
        new_referral_code = generate_referral_code()
        while db.query(User).filter(User.referral_code == new_referral_code).first():
            new_referral_code = generate_referral_code()
        
        # Create new user
        user = User(
            email=email, 
            name=payload.name,
            password_hash=pwd_context.hash(password), 
            role=role,
            referral_code=new_referral_code,
            referred_by_code=referral_code if referrer_id else None,
            created_at=datetime.utcnow()
        )
        
        db.add(user)
        db.commit()
        db.refresh(user)
        
        return {"success": True, "message": "Account created successfully", "referral_code": new_referral_code}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/user/login")
async def login_user(payload: UserLoginRequest, request: Request, db: Session = Depends(get_db)):
    try:
        email = payload.email
        password = payload.password

        enforce_login_rate_limit(request, email)

        print("Login attempt received")
        
        if not email or not password:
            print("Missing email or password")
            raise HTTPException(status_code=400, detail="Email and password are required")
        
        user = db.query(User).filter(User.email == email).first()
        if not user:
            print(f"User not found: {email}")
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        print(f"User found: {user.id}, verifying password...")
        if not pwd_context.verify(password, user.password_hash):
            print("Password verification failed")
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        print("Password verified successfully")
        # Create token with 24 hour expiration
        now = datetime.utcnow()
        payload = {
            "sub": str(user.id),
            "name": user.name,
            "role": user.role.value,
            "iat": now,
            "exp": now + timedelta(hours=24)
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        print(f"✅ Generated token for user {user.id} ({user.email}), expires in 24 hours")
        return {"success": True, "token": token}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Login error: {e}")
        raise HTTPException(status_code=500, detail="Login failed")

# Store for password reset codes
password_reset_codes = {}

@app.post("/api/user/forgot-password")
async def forgot_password(payload: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)):
    """Send password reset code to user's email"""
    try:
        email = payload.email

        enforce_forgot_password_rate_limit(request, email)
        
        if not email:
            raise HTTPException(status_code=400, detail="Email is required")
        
        user = db.query(User).filter(User.email == email).first()
        if not user:
            # Don't reveal if email exists
            return {"success": True, "message": "If the email exists, a reset code has been sent"}
        
        # Generate 6-digit code
        reset_code = generate_reset_code(6)
        
        # Store code with expiration
        password_reset_codes[email] = {
            'code': reset_code,
            'expires_at': datetime.utcnow() + timedelta(minutes=15)
        }
        
        send_reset_email(email, reset_code, user.name or "there")
        
        return {"success": True, "message": "Reset code sent"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Forgot password error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/user/reset-password")
async def reset_password(payload: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)):
    """Reset user password with verification code"""
    try:
        email = payload.email
        code = payload.code
        new_password = payload.new_password

        enforce_reset_password_rate_limit(request, email)
        
        if not email or not code or not new_password:
            raise HTTPException(status_code=400, detail="Missing required fields")
        
        # Check if code exists
        if email not in password_reset_codes:
            raise HTTPException(status_code=400, detail="Invalid or expired reset code")
        
        stored = password_reset_codes[email]
        
        # Verify code
        if stored['code'] != code:
            raise HTTPException(status_code=400, detail="Invalid reset code")
        
        # Check expiration
        if datetime.utcnow() > stored['expires_at']:
            del password_reset_codes[email]
            raise HTTPException(status_code=400, detail="Reset code expired")
        
        # Update password
        user = db.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        user.password_hash = pwd_context.hash(new_password)
        db.commit()
        
        # Clean up code
        del password_reset_codes[email]
        
        return {"success": True, "message": "Password reset successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Reset password error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/user/referrals")
async def get_user_referrals(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    """Get user's referral stats"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub")) if payload and payload.get("sub") is not None else None
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Generate referral code if user doesn't have one
        if not user.referral_code:
            new_code = generate_referral_code()
            while db.query(User).filter(User.referral_code == new_code).first():
                new_code = generate_referral_code()
            user.referral_code = new_code
            db.commit()
            db.refresh(user)
        
        # Count referrals using referred_by_code field
        referral_count = db.query(User).filter(User.referred_by_code == user.referral_code).count()
        
        return {
            "referral_code": user.referral_code,
            "referral_count": referral_count
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/referral/validate")
async def validate_referral_code(request: Request, db: Session = Depends(get_db)):
    """Validate a referral code in real-time"""
    try:
        body = await request.json()
        code = body.get('code', '').strip().upper()
        
        if not code:
            return {"valid": False, "referrer_name": None}
        
        if len(code) < 6:
            return {"valid": False, "referrer_name": None}
        
        user = db.query(User).filter(User.referral_code == code).first()
        if not user:
            return {"valid": False, "referrer_name": None}
        
        return {"valid": True, "referrer_name": user.name}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error validating referral code: {e}")
        return {"valid": False, "referrer_name": None}

@app.get("/api/admin/referrals")
async def get_referral_analytics(admin_user: User = Depends(verify_admin), db: Session = Depends(get_db)):
    """Get referral analytics for admin (Admin only)"""
    try:
        # Get all users with their referral data
        users = db.query(User).all()
        
        referral_stats = []
        for user in users:
            # Count how many people this user referred
            referral_count = 0
            referred_users = []
            if user.referral_code:
                referral_count = db.query(User).filter(User.referred_by_code == user.referral_code).count()
            
            # Get the actual referred users for recent referrals display
            if user.referral_code:
                referred_users = db.query(User).filter(User.referred_by_code == user.referral_code).all()
            
            referral_stats.append({
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "referral_code": user.referral_code,
                "referral_count": referral_count,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "referred_users": [{
                    "id": ru.id,
                    "name": ru.name,
                    "email": ru.email,
                    "created_at": ru.created_at.isoformat() if ru.created_at else None
                } for ru in referred_users]
            })
        
        return referral_stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/stats")
async def get_admin_stats(admin_user: User = Depends(verify_admin), db: Session = Depends(get_db)):
    """Get admin dashboard aggregate stats from the primary database."""
    try:
        total_users = db.query(User).count()
        total_listings = db.query(FoodResource).count()
        total_schedules = db.query(DonationSchedule).count()
        active_tasks = db.query(DonationReminder).filter(
            DonationReminder.status.in_([ReminderStatus.PENDING, ReminderStatus.SENT])
        ).count()

        return {
            "users": total_users,
            "listings": total_listings,
            "schedules": total_schedules,
            "tasks": active_tasks,
            "connected": True,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/public/stats")
@app.get("/public/stats")
async def get_public_stats(response: Response, db: Session = Depends(get_db)):
    """Lightweight, cache-friendly impact totals for the public landing page."""
    fallback = {
        "pounds_donated_lbs": 85000,
        "families_helped": 2500,
        "claimed_listings": 0,
        "updated_at": None,
    }

    try:
        normalized_unit = func.lower(func.coalesce(FoodResource.unit, ""))
        pounds_expr = case(
            (FoodResource.est_weight_kg.isnot(None), FoodResource.est_weight_kg * 2.20462),
            (normalized_unit.in_(["lb", "lbs", "pound", "pounds"]), FoodResource.qty),
            else_=FoodResource.qty * 0.5,
        )

        totals = db.query(
            func.count(FoodResource.id).label("claimed_listings"),
            func.coalesce(func.sum(pounds_expr), 0.0).label("pounds_donated_lbs"),
            func.count(func.distinct(FoodResource.recipient_id)).label("families_helped"),
            func.max(FoodResource.claimed_at).label("updated_at"),
        ).filter(
            FoodResource.status == "claimed"
        ).first()

        pounds_donated = int(round(float(totals.pounds_donated_lbs or 0)))
        families_helped = int(totals.families_helped or 0)

        response.headers["Cache-Control"] = "public, max-age=1800"
        return {
            "pounds_donated_lbs": max(0, pounds_donated),
            "families_helped": max(0, families_helped),
            "claimed_listings": int(totals.claimed_listings or 0),
            "updated_at": totals.updated_at.isoformat() if totals.updated_at else None,
        }
    except Exception:
        response.headers["Cache-Control"] = "public, max-age=300"
        return fallback

# Store for pending confirmations
pending_confirmations = {}

def generate_reset_code(length: int = 6) -> str:
    """Generate a random numeric code for SMS confirmation"""
    return ''.join(secrets.choice(string.digits) for _ in range(length))

def generate_referral_code() -> str:
    """Generate a unique referral code"""
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(8))

def send_sms(phone: str, message: str) -> bool:
    """Send SMS using Twilio API with fallback to console logging"""
    try:
        # Check if Twilio credentials are configured
        if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
            print(f"⚠️  Twilio not configured. SMS to {phone}: {message}")
            return False
        
        # Initialize Twilio client
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        
        # Format phone number (ensure it starts with +)
        formatted_phone = phone.strip()
        if not formatted_phone.startswith('+'):
            # Assume US number if no country code
            formatted_phone = '+1' + formatted_phone.replace('-', '').replace('(', '').replace(')', '').replace(' ', '').replace('.', '')
        
        # Send SMS
        message_obj = client.messages.create(
            body=message,
            from_=TWILIO_PHONE_NUMBER,
            to=formatted_phone
        )
        
        print(f"✅ SMS sent successfully to {formatted_phone} (SID: {message_obj.sid})")
        return True
        
    except Exception as e:
        print(f"❌ Failed to send SMS to {phone}: {str(e)}")
        # Log to console as fallback
        print(f"📱 SMS to {phone}: {message}")
        return False

def auto_release_claim(listing_id: int):
    """Auto-release a claim if not confirmed within time limit"""
    db = None
    try:
        db = SessionLocal()
        if listing_id in pending_confirmations:
            item = db.query(FoodResource).filter(FoodResource.id == listing_id).first()
            if item and item.status == "pending_confirmation":
                item.status = "available"
                item.recipient_id = None
                item.claimed_at = None
                db.commit()
                print(f"\u23f0 Auto-released listing {listing_id} due to timeout")
            del pending_confirmations[listing_id]
    except Exception as e:
        print(f"Error in auto_release_claim: {e}")
        if db is not None:
            try:
                db.rollback()
            except Exception:
                pass
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass

# ============================================
# DISTRIBUTION CENTER ENDPOINTS
# ============================================

@app.get("/api/centers", response_model=List[DistributionCenterResponse])
async def get_distribution_centers(db: Session = Depends(get_db)):
    """Get all distribution centers"""
    try:
        centers = db.query(DistributionCenter).all()
        return centers
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/centers")
async def create_distribution_center(request: Request, admin_user: User = Depends(verify_admin), db: Session = Depends(get_db)):
    """Create a new distribution center (Admin only)"""
    try:
        body = await request.json()
        center = DistributionCenter(
            owner_id=admin_user.id,
            name=body.get('name'),
            description=body.get('description'),
            address=body.get('address'),
            coords_lat=body.get('coords_lat'),
            coords_lng=body.get('coords_lng'),
            phone=body.get('phone'),
            hours=body.get('hours'),
            created_at=datetime.utcnow()
        )
        db.add(center)
        db.commit()
        db.refresh(center)
        return {"success": True, "center": center}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/centers/{center_id}")
async def update_distribution_center(center_id: int, request: Request, admin_user: User = Depends(verify_admin), db: Session = Depends(get_db)):
    """Update a distribution center (Admin only)"""
    try:
        center = db.query(DistributionCenter).filter(DistributionCenter.id == center_id).first()
        if not center:
            raise HTTPException(status_code=404, detail="Center not found")
        
        body = await request.json()
        
        # Update fields if provided
        if 'name' in body:
            center.name = body['name']
        if 'description' in body:
            center.description = body['description']
        if 'address' in body:
            center.address = body['address']
        if 'coords_lat' in body:
            center.coords_lat = body['coords_lat']
        if 'coords_lng' in body:
            center.coords_lng = body['coords_lng']
        if 'phone' in body:
            center.phone = body['phone']
        if 'hours' in body:
            center.hours = body['hours']
        if 'is_active' in body:
            center.is_active = body['is_active']
        
        db.commit()
        db.refresh(center)
        return {"success": True, "center": center}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"Update center error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/centers/{center_id}")
async def delete_distribution_center(center_id: int, admin_user: User = Depends(verify_admin), db: Session = Depends(get_db)):
    """Delete a distribution center and its inventory (Admin only)"""
    try:
        center = db.query(DistributionCenter).filter(DistributionCenter.id == center_id).first()
        if not center:
            raise HTTPException(status_code=404, detail="Center not found")
        
        # Delete associated inventory first
        db.query(CenterInventory).filter(CenterInventory.center_id == center_id).delete()
        
        # Delete the center
        db.delete(center)
        db.commit()
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"Delete center error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/centers/{center_id}", response_model=DistributionCenterWithInventory)
async def get_distribution_center(center_id: int, db: Session = Depends(get_db)):
    """Get a specific distribution center with inventory"""
    try:
        center = db.query(DistributionCenter).filter(
            DistributionCenter.id == center_id
        ).first()
        
        if not center:
            raise HTTPException(status_code=404, detail="Distribution center not found")
        
        return center
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/centers/{center_id}/inventory", response_model=List[CenterInventoryResponse])
async def get_center_inventory(center_id: int, db: Session = Depends(get_db)):
    """Get inventory for a specific distribution center"""
    try:
        center = db.query(DistributionCenter).filter(
            DistributionCenter.id == center_id
        ).first()
        
        if not center:
            raise HTTPException(status_code=404, detail="Distribution center not found")
        
        inventory = db.query(CenterInventory).filter(
            CenterInventory.center_id == center_id
        ).all()
        
        return inventory
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Support both legacy and canonical claim routes.
@app.patch("/api/listings/get/{listing_id}")
@app.post("/api/listings/claim/{listing_id}")
async def claim_listing(listing_id: int, db: Session = Depends(get_db), credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Claim a listing with SMS confirmation requirement."""
    try:
        # Authorization first — no point hitting the DB without a valid user.
        try:
            payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            user_id = str(payload.get("sub")) if payload else None
            if not user_id:
                raise HTTPException(status_code=401, detail="Invalid token")
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid token")

        uid_int = int(user_id)
        now = datetime.utcnow()

        # Atomic claim: only one concurrent caller can transition
        # 'available' -> 'pending_confirmation'. Prevents the read-then-
        # update race that previously let two users both win the same
        # listing.
        updated = (
            db.query(FoodResource)
            .filter(
                FoodResource.id == listing_id,
                FoodResource.status == "available",
                FoodResource.donor_id != uid_int,
            )
            .update(
                {
                    FoodResource.status: "pending_confirmation",
                    FoodResource.recipient_id: uid_int,
                    FoodResource.claimed_at: now,
                },
                synchronize_session=False,
            )
        )
        if not updated:
            item = db.query(FoodResource).filter(FoodResource.id == listing_id).first()
            db.rollback()
            if not item:
                raise HTTPException(status_code=404, detail="Listing not found")
            if item.donor_id == uid_int:
                raise HTTPException(status_code=400, detail="You cannot claim your own listing")
            raise HTTPException(status_code=400, detail="Listing is not available")

        item = db.query(FoodResource).filter(FoodResource.id == listing_id).first()

        # Get user details (claimant must have a phone for SMS confirmation).
        claimant = db.query(User).filter(User.id == uid_int).first()
        if not claimant or not claimant.phone:
            # Roll back the claim so the listing goes back to 'available'.
            (
                db.query(FoodResource)
                .filter(FoodResource.id == listing_id, FoodResource.recipient_id == uid_int)
                .update(
                    {
                        FoodResource.status: "available",
                        FoodResource.recipient_id: None,
                        FoodResource.claimed_at: None,
                    },
                    synchronize_session=False,
                )
            )
            db.commit()
            raise HTTPException(status_code=400, detail="Phone number required")

        donor = db.query(User).filter(User.id == item.donor_id).first()
        
        # Generate confirmation code
        confirmation_code = generate_reset_code(4)

        # Store confirmation code (the listing was already moved to
        # pending_confirmation by the atomic update above).
        pending_confirmations[listing_id] = {
            'code': confirmation_code,
            'recipient_id': uid_int,
            'expires_at': datetime.utcnow() + timedelta(minutes=5)
        }
        
        # Send SMS to recipient
        recipient_msg = f"You claimed '{item.title}'. Reply with code {confirmation_code} within 5 minutes to confirm. Address: {item.address}"
        send_sms(claimant.phone, recipient_msg)
        
        # Send SMS to donor if they have a phone
        if donor and donor.phone:
            donor_msg = f"Your listing '{item.title}' was claimed by {claimant.name}. Waiting for confirmation."
            send_sms(donor.phone, donor_msg)
        
        # Set auto-release timer
        timer = Timer(300.0, auto_release_claim, args=[listing_id])  # 5 minutes
        timer.start()
        
        return {
            "success": True, 
            "message": "Claim initiated. Check your phone for confirmation code.",
            "listing": serialize_listing(item)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/listings/confirm/{listing_id}")
async def confirm_claim(listing_id: int, request: Request, db: Session = Depends(get_db), credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Confirm a claim with SMS code."""
    try:
        body = await request.json()
        code = body.get('code', '').strip()
        
        if not code:
            raise HTTPException(status_code=400, detail="Confirmation code required")
        
        # Check if confirmation is pending
        if listing_id not in pending_confirmations:
            raise HTTPException(status_code=400, detail="No pending confirmation for this listing")
        
        confirmation = pending_confirmations[listing_id]
        
        # Check if code matches
        if confirmation['code'] != code:
            raise HTTPException(status_code=400, detail="Invalid confirmation code")
        
        # Check if expired
        if datetime.utcnow() > confirmation['expires_at']:
            del pending_confirmations[listing_id]
            raise HTTPException(status_code=400, detail="Confirmation code expired")
        
        # Verify user authorization
        try:
            payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            user_id = int(payload.get("sub")) if payload and payload.get("sub") is not None else None
            if user_id != confirmation['recipient_id']:
                raise HTTPException(status_code=403, detail="Not authorized")
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        # Update listing status to claimed
        item = db.query(FoodResource).filter(FoodResource.id == listing_id).first()
        if not item:
            raise HTTPException(status_code=404, detail="Listing not found")
        
        item.status = "claimed"
        db.commit()
        
        # Clean up confirmation
        del pending_confirmations[listing_id]
        
        # Get user details for notification
        claimant = db.query(User).filter(User.id == user_id).first()
        donor = db.query(User).filter(User.id == item.donor_id).first()
        
        # Send confirmation SMS to both parties
        if claimant and claimant.phone:
            msg = f"Claim confirmed! You can now pick up '{item.title}' at {item.address}. Contact donor: {donor.phone if donor and donor.phone else 'N/A'}"
            send_sms(claimant.phone, msg)
        
        if donor and donor.phone:
            msg = f"Claim confirmed! {claimant.name if claimant else 'Recipient'} will pick up '{item.title}'. Contact: {claimant.phone if claimant and claimant.phone else 'N/A'}"
            send_sms(donor.phone, msg)
        
        return {
            "success": True,
            "message": "Claim confirmed successfully",
            "listing": serialize_listing(item)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/listings/{listing_id}/verify-before")
async def verify_before_pickup(
    listing_id: int,
    request: Request,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Upload before-pickup verification photo"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub")) if payload and payload.get("sub") is not None else None
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        body = await request.json()
        photo_data = body.get('photo')
        notes = body.get('notes', '')
        
        if not photo_data:
            raise HTTPException(status_code=400, detail="Photo data required")
        
        listing = db.query(FoodResource).filter(FoodResource.id == listing_id).first()
        if not listing:
            raise HTTPException(status_code=404, detail="Listing not found")
        
        # Verify user is the recipient
        if listing.recipient_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized")
        
        # Update listing
        listing.before_photo = photo_data
        listing.before_verified_at = datetime.utcnow()
        listing.verification_status = "before_verified"
        if notes:
            listing.pickup_notes = notes
        
        db.commit()
        
        return {
            "success": True,
            "message": "Before-pickup photo uploaded successfully",
            "verification_status": listing.verification_status
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/listings/{listing_id}/verify-after")
async def verify_after_pickup(
    listing_id: int,
    request: Request,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Upload after-pickup verification photo and complete verification"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub")) if payload and payload.get("sub") is not None else None
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        body = await request.json()
        photo_data = body.get('photo')
        notes = body.get('notes', '')
        
        if not photo_data:
            raise HTTPException(status_code=400, detail="Photo data required")
        
        listing = db.query(FoodResource).filter(FoodResource.id == listing_id).first()
        if not listing:
            raise HTTPException(status_code=404, detail="Listing not found")
        
        # Verify user is the recipient
        if listing.recipient_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized")
        
        # Update listing
        listing.after_photo = photo_data
        listing.after_verified_at = datetime.utcnow()
        listing.verification_status = "completed"
        listing.status = "completed"
        if notes:
            listing.pickup_notes = (listing.pickup_notes or '') + "\n" + notes
        
        db.commit()
        
        return {
            "success": True,
            "message": "Pickup completed and verified successfully",
            "verification_status": listing.verification_status
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/listings/{listing_id}/verification")
async def get_verification_status(
    listing_id: int,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get verification status and photos for a listing"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub")) if payload and payload.get("sub") is not None else None
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        listing = db.query(FoodResource).filter(FoodResource.id == listing_id).first()
        if not listing:
            raise HTTPException(status_code=404, detail="Listing not found")
        
        # Only donor or recipient can see verification
        if listing.donor_id != user_id and listing.recipient_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized")
        
        return {
            "verification_status": listing.verification_status,
            "before_photo": listing.before_photo,
            "after_photo": listing.after_photo,
            "before_verified_at": listing.before_verified_at.isoformat() if listing.before_verified_at else None,
            "after_verified_at": listing.after_verified_at.isoformat() if listing.after_verified_at else None,
            "pickup_notes": listing.pickup_notes
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/user/send-verification-email")
async def send_verification_email(
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Send verification email to user"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub")) if payload and payload.get("sub") is not None else None
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Generate verification token (valid for 24 hours)
        verification_token = jwt.encode(
            {
                "sub": str(user.id),
                "email": user.email,
                "purpose": "email_verification",
                "exp": datetime.utcnow() + timedelta(hours=24)
            },
            JWT_SECRET,
            algorithm=JWT_ALGORITHM
        )
        
        base_url = get_public_base_url()
        encoded_token = quote(verification_token, safe="")
        verification_link = f"{base_url}/verify-email?token={encoded_token}"
        send_verification_email_message(user.email, user.name or "there", verification_link)

        return {
            "success": True,
            "message": "Verification email sent successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/verify-email")
async def verify_email_endpoint(token: str, db: Session = Depends(get_db)):
    """Verify email with token from link"""
    try:
        # Decode token
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        
        if payload.get("purpose") != "email_verification":
            raise HTTPException(status_code=400, detail="Invalid verification token")
        
        user_id = int(payload.get("sub"))
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Mark email as verified
        user.email_verified = True
        
        # Update trust score
        current_score = getattr(user, 'trust_score', 50)
        user.trust_score = min(100, current_score + 5)
        
        db.commit()
        
        # Return HTML page with success message
        return HTMLResponse(content="""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Email Verified - DoGoods</title>
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    min-height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                }
                .container {
                    background: white;
                    padding: 3rem;
                    border-radius: 1rem;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                    text-align: center;
                    max-width: 500px;
                }
                .icon {
                    font-size: 4rem;
                    margin-bottom: 1rem;
                }
                h1 {
                    color: #2d3748;
                    margin: 0 0 1rem 0;
                }
                p {
                    color: #4a5568;
                    margin-bottom: 2rem;
                }
                .button {
                    display: inline-block;
                    padding: 0.75rem 2rem;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    text-decoration: none;
                    border-radius: 0.5rem;
                    font-weight: 600;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="icon">✅</div>
                <h1>Email Verified!</h1>
                <p>Your email has been successfully verified. Your trust score has increased by 5 points!</p>
                <a href="/" class="button">Return to DoGoods</a>
            </div>
        </body>
        </html>
        """, status_code=200)
        
    except jwt.ExpiredSignatureError:
        return HTMLResponse(content="""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Link Expired - DoGoods</title>
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    min-height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
                }
                .container {
                    background: white;
                    padding: 3rem;
                    border-radius: 1rem;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                    text-align: center;
                    max-width: 500px;
                }
                .icon {
                    font-size: 4rem;
                    margin-bottom: 1rem;
                }
                h1 {
                    color: #2d3748;
                    margin: 0 0 1rem 0;
                }
                p {
                    color: #4a5568;
                    margin-bottom: 2rem;
                }
                .button {
                    display: inline-block;
                    padding: 0.75rem 2rem;
                    background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
                    color: white;
                    text-decoration: none;
                    border-radius: 0.5rem;
                    font-weight: 600;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="icon">⏰</div>
                <h1>Link Expired</h1>
                <p>This verification link has expired. Please request a new verification email from your account settings.</p>
                <a href="/" class="button">Return to DoGoods</a>
            </div>
        </body>
        </html>
        """, status_code=400)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

# ============================================================================
# SAFETY AND TRUST ENDPOINTS
# ============================================================================

@app.get("/api/user/trust-score")
async def get_trust_score(
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get user's trust score and verification status"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub")) if payload and payload.get("sub") is not None else None
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        return {
            "trust_score": getattr(user, 'trust_score', 50),
            "verification_status": {
                "verified": getattr(user, 'email_verified', False) and getattr(user, 'phone_verified', False),
                "email_verified": getattr(user, 'email_verified', False),
                "phone_verified": getattr(user, 'phone_verified', False),
                "id_verified": getattr(user, 'id_verified', False),
                "address_verified": getattr(user, 'address_verified', False)
            },
            "stats": {
                "completed_exchanges": getattr(user, 'completed_exchanges', 0),
                "positive_feedback": getattr(user, 'positive_feedback', 0),
                "negative_feedback": getattr(user, 'negative_feedback', 0),
                "verified_pickups": getattr(user, 'verified_pickups', 0)
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/safety/report")
async def submit_safety_report(
    request: Request,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Submit a safety report"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub")) if payload and payload.get("sub") is not None else None
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        data = await request.json()
        report_type = data.get('type')
        description = data.get('description')
        listing_id = data.get('listingId')
        evidence = data.get('evidence')
        
        if not report_type or not description:
            raise HTTPException(status_code=400, detail="Missing required fields")
        
        # Note: SafetyReport table exists and should work
        try:
            # Convert string to enum
            report_type_enum = ReportType[report_type.upper().replace(' ', '_')] if report_type.upper().replace(' ', '_') in ReportType.__members__ else ReportType.OTHER
            
            new_report = SafetyReport(
                reporter_id=user_id,
                report_type=report_type_enum,
                description=description,
                listing_id=int(listing_id) if listing_id else None,
                evidence=evidence
            )
            
            db.add(new_report)
            db.commit()
            db.refresh(new_report)
            
            return {
                "success": True,
                "message": "Report submitted successfully",
                "report_id": new_report.id
            }
        except Exception as inner_e:
            db.rollback()
            # If table doesn't exist yet, log the report attempt
            print(f"Safety report error: {str(inner_e)}")
            print(f"Safety report logged: {report_type} by user {user_id}")
            return {
                "success": True,
                "message": "Report received and will be reviewed"
            }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/user/update-trust-score")
async def update_trust_score(
    request: Request,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Update user trust score (internal use or admin)"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub")) if payload and payload.get("sub") is not None else None
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        data = await request.json()
        action = data.get('action')  # 'completed_exchange', 'positive_feedback', 'verified_pickup', etc.
        
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Update based on action
        trust_increase = 0
        if action == 'completed_exchange':
            user.completed_exchanges = getattr(user, 'completed_exchanges', 0) + 1
            trust_increase = 2
        elif action == 'positive_feedback':
            user.positive_feedback = getattr(user, 'positive_feedback', 0) + 1
            trust_increase = 3
        elif action == 'verified_pickup':
            user.verified_pickups = getattr(user, 'verified_pickups', 0) + 1
            trust_increase = 5
        elif action == 'email_verified':
            user.email_verified = True
            trust_increase = 5
        elif action == 'phone_verified':
            user.phone_verified = True
            trust_increase = 5
        
        # Update trust score (cap at 100)
        current_score = getattr(user, 'trust_score', 50)
        user.trust_score = min(100, current_score + trust_increase)
        
        db.commit()
        
        return {
            "success": True,
            "new_trust_score": user.trust_score,
            "increase": trust_increase
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/listings/create")
async def create_listing(donor_id: int, title: str, desc: str, category: FoodCategory, qty: float, unit: str, perishability: PerishabilityLevel, address: str,  pickup_start: str, pickup_end: str, est_w: float = 0, images: Optional[str] = None, db: Session = Depends(get_db), credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_security)):
    """
    Create a FoodResource and attempt server-side geocoding using Mapbox when an address is provided
    and coords are not supplied. Returns the created listing as JSON.

    `images` may be a JSON-encoded array of URL strings (e.g. paths returned by
    /api/ai/upload_image) to attach as listing photos.

    SECURITY: the authoritative donor_id is taken from the JWT (Authorization
    header). The legacy `donor_id` URL parameter is kept for backward
    compatibility but is IGNORED when a valid token is present — otherwise a
    stale `localStorage.current_user` on the client could cause a listing to
    be attributed to the wrong user (and surface that user's profile address
    on the listing card).
    """
    try:
        # Resolve the authenticated donor from the JWT. Fall back to the URL
        # parameter only if no token was supplied (legacy callers); never
        # silently trust a client-supplied id when auth context disagrees.
        authed_donor_id: Optional[int] = None
        if credentials and getattr(credentials, "credentials", None):
            try:
                payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
                sub = payload.get("sub") if isinstance(payload, dict) else None
                if sub is not None:
                    authed_donor_id = int(sub)
            except Exception:
                raise HTTPException(status_code=401, detail="Your session is missing or expired. Please sign in to continue.")

        if authed_donor_id is not None:
            if int(donor_id) != authed_donor_id:
                try:
                    print(f"[create_listing] overriding client donor_id={donor_id} with authenticated id={authed_donor_id}")
                except Exception:
                    pass
            donor_id = authed_donor_id

        # Enforce that donor has a phone number on file
        donor = db.query(User).filter(User.id == int(donor_id)).first()
        if not donor:
            raise HTTPException(status_code=404, detail="Donor not found")
        if not donor.phone or len(str(donor.phone).strip()) < 7:
            raise HTTPException(status_code=400, detail="A valid phone number is required to create a listing")

        # Validate and normalize the optional images parameter. We store a
        # JSON-encoded array of URL strings; reject anything else to avoid
        # storing arbitrary blobs (or huge data URLs) on the listing row.
        images_json = None
        if images:
            try:
                parsed = json.loads(images) if isinstance(images, str) else images
            except Exception:
                raise HTTPException(status_code=400, detail="images must be a JSON array of URL strings")
            if not isinstance(parsed, list):
                raise HTTPException(status_code=400, detail="images must be a JSON array of URL strings")
            cleaned = []
            for u in parsed:
                if not isinstance(u, str):
                    continue
                s = u.strip()
                if not s:
                    continue
                # Only accept relative /uploads/... paths or http(s) URLs.
                if not (s.startswith("/uploads/") or s.startswith("http://") or s.startswith("https://")):
                    continue
                if len(s) > 1024:
                    continue
                cleaned.append(s)
                if len(cleaned) >= 8:
                    break
            images_json = json.dumps(cleaned) if cleaned else None

        item = FoodResource(
            donor_id=donor_id,
            title=title,
            description=desc,
            category=category,
            qty=qty,
            unit=unit,
            perishability=perishability,
            pickup_window_start=pickup_start,
            pickup_window_end=pickup_end,
            address=address,
            images=images_json,
            created_at=datetime.utcnow()
        )

        # If coords are missing and address provided, attempt Mapbox geocoding
        try:
            if (item.coords_lat is None or item.coords_lng is None) and item.address:
                MAPBOX_TOKEN = os.getenv('MAPBOX_TOKEN')
                if MAPBOX_TOKEN:
                    from urllib.parse import quote as urlquote
                    import httpx
                    geocode_url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{urlquote(item.address)}.json"
                    params = {"access_token": MAPBOX_TOKEN, "limit": 1}
                    with httpx.Client(timeout=10.0) as client:
                        resp = client.get(geocode_url, params=params)
                        if resp.status_code == 200:
                            data = resp.json()
                            features = data.get('features') or []
                            if len(features) > 0:
                                center = features[0].get('center')
                                if center and len(center) >= 2:
                                    # Mapbox returns [lng, lat]
                                    item.coords_lng = float(center[0])
                                    item.coords_lat = float(center[1])
                else:
                    # No MAPBOX token configured - skip geocoding
                    pass
        except Exception as ge:
            # Don't fail the request if geocoding fails; log and continue
            try:
                print(f"Geocoding error for address {item.address}: {ge}")
            except Exception:
                pass

        db.add(item)
        db.commit()
        db.refresh(item)
        # Return the created item
        return {"success": True, "listing": serialize_listing(item)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/listings/user-details/{listing_id}")
async def get_user_details(
    listing_id: int,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Return the counterparty contact info for a claimed listing:
    - If requester is the recipient who claimed the listing, return the donor's name/phone.
    - If requester is the donor who created the listing, return the recipient's name/phone.
    """
    try:
        try:
            payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            user_role = str(payload.get("role") or "").lower() if payload else None
            user_id = int(payload.get("sub")) if payload and payload.get("sub") is not None else None
        except Exception:
            raise HTTPException(status_code=401, detail="Your session is missing or expired. Please sign in to continue.")

        if user_role not in ("donor", "recipient"):
            raise HTTPException(status_code=403, detail="Not authorized")

        listing = db.query(FoodResource).filter(FoodResource.id == listing_id).first()
        if not listing:
            raise HTTPException(status_code=404, detail="Listing not found")

        # Recipient can only see donor for listings they claimed
        if user_role == "recipient":
            if listing.recipient_id is None or listing.recipient_id != user_id:
                raise HTTPException(status_code=403, detail="Not authorized for this listing")
            donor = db.query(User).filter(User.id == listing.donor_id).first()
            if not donor:
                # Return empty contact gracefully if donor record is missing
                return {"name": "", "phone": ""}
            return {"name": donor.name or "", "phone": donor.phone or ""}

        # Donor can only see recipient for their own listing
        if listing.donor_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized for this listing")
        # If not yet claimed or recipient missing, return empty contact gracefully
        if listing.recipient_id is None:
            return {"name": "", "phone": ""}
        recipient = db.query(User).filter(User.id == listing.recipient_id).first()
        if not recipient:
            return {"name": "", "phone": ""}
        return {"name": recipient.name or "", "phone": recipient.phone or ""}

    except HTTPException:
        raise
    except Exception as e:
        try:
            print(f"/api/listings/user-details error: {e}")
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Failed to fetch user details")   



# Food Safety Checklist Endpoints
@app.post("/api/food/safety-check")
async def submit_safety_check(
    listing_id: int,
    storage_temperature: Optional[float] = None,
    is_refrigerated: bool = False,
    is_frozen: bool = False,
    packaging_condition: str = 'good',
    safety_score: int = 0,
    safety_notes: Optional[str] = None,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Submit a food safety checklist for a listing.
    Only the donor who created the listing can submit safety checks.
    """
    try:
        # Verify user
        try:
            payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            user_id = int(payload.get("sub")) if payload and payload.get("sub") is not None else None
        except Exception:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # Get the listing
        listing = db.query(FoodResource).filter(FoodResource.id == listing_id).first()
        if not listing:
            raise HTTPException(status_code=404, detail="Listing not found")
        
        # Verify the user is the donor
        if listing.donor_id != user_id:
            raise HTTPException(status_code=403, detail="Only the donor can submit safety checks")
        
        # Validate safety score
        if safety_score < 0 or safety_score > 100:
            raise HTTPException(status_code=400, detail="Safety score must be between 0 and 100")
        
        # Validate packaging condition
        valid_conditions = ['excellent', 'good', 'fair', 'poor']
        if packaging_condition not in valid_conditions:
            raise HTTPException(status_code=400, detail=f"Invalid packaging condition. Must be one of: {', '.join(valid_conditions)}")
        
        # Update listing with safety information
        listing.storage_temperature = storage_temperature
        listing.is_refrigerated = is_refrigerated
        listing.is_frozen = is_frozen
        listing.packaging_condition = packaging_condition
        listing.safety_score = safety_score
        listing.safety_notes = safety_notes
        listing.safety_last_checked = datetime.utcnow()
        
        # Mark as passed if score >= 60 and packaging is not poor
        listing.safety_checklist_passed = (safety_score >= 60 and packaging_condition != 'poor')
        
        db.commit()
        db.refresh(listing)
        
        return {
            "success": True,
            "message": "Safety checklist submitted successfully",
            "listing": serialize_listing(listing),
            "safety_passed": listing.safety_checklist_passed
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/food/{listing_id}/safety-status")
async def get_safety_status(
    listing_id: int,
    db: Session = Depends(get_db)
):
    """
    Get the food safety status for a listing.
    Public endpoint - anyone can view safety information.
    """
    try:
        listing = db.query(FoodResource).filter(FoodResource.id == listing_id).first()
        if not listing:
            raise HTTPException(status_code=404, detail="Listing not found")
        
        return {
            "listing_id": listing.id,
            "safety_checklist_passed": listing.safety_checklist_passed or False,
            "safety_score": listing.safety_score or 0,
            "storage_temperature": listing.storage_temperature,
            "is_refrigerated": listing.is_refrigerated or False,
            "is_frozen": listing.is_frozen or False,
            "packaging_condition": listing.packaging_condition or 'unknown',
            "safety_notes": listing.safety_notes,
            "safety_last_checked": listing.safety_last_checked.isoformat() if listing.safety_last_checked else None
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/food/{listing_id}/safety-update")
async def update_safety_info(
    listing_id: int,
    storage_temperature: Optional[float] = None,
    is_refrigerated: Optional[bool] = None,
    is_frozen: Optional[bool] = None,
    packaging_condition: Optional[str] = None,
    safety_notes: Optional[str] = None,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Update partial safety information for a listing.
    Only the donor can update safety information.
    """
    try:
        # Verify user
        try:
            payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            user_id = int(payload.get("sub")) if payload and payload.get("sub") is not None else None
        except Exception:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # Get the listing
        listing = db.query(FoodResource).filter(FoodResource.id == listing_id).first()
        if not listing:
            raise HTTPException(status_code=404, detail="Listing not found")
        
        # Verify the user is the donor
        if listing.donor_id != user_id:
            raise HTTPException(status_code=403, detail="Only the donor can update safety information")
        
        # Update only provided fields
        if storage_temperature is not None:
            listing.storage_temperature = storage_temperature
        if is_refrigerated is not None:
            listing.is_refrigerated = is_refrigerated
        if is_frozen is not None:
            listing.is_frozen = is_frozen
        if packaging_condition is not None:
            valid_conditions = ['excellent', 'good', 'fair', 'poor']
            if packaging_condition not in valid_conditions:
                raise HTTPException(status_code=400, detail=f"Invalid packaging condition. Must be one of: {', '.join(valid_conditions)}")
            listing.packaging_condition = packaging_condition
        if safety_notes is not None:
            listing.safety_notes = safety_notes
        
        # Update last checked timestamp
        listing.safety_last_checked = datetime.utcnow()
        
        db.commit()
        db.refresh(listing)
        
        return {
            "success": True,
            "message": "Safety information updated successfully",
            "listing": serialize_listing(listing)
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# Pickup Reminder Endpoints
@app.get("/api/pickup-reminders/list")
async def get_pickup_reminders(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Get all pickup reminders for the authenticated user"""
    try:
        from backend.models import PickupReminder
        
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub"))
        
        reminders = db.query(PickupReminder).filter(
            PickupReminder.user_id == user_id
        ).order_by(PickupReminder.scheduled_time).all()
        
        # Enhance with listing details
        reminder_list = []
        for reminder in reminders:
            listing = db.query(FoodResource).filter(FoodResource.id == reminder.listing_id).first()
            reminder_list.append({
                "id": reminder.id,
                "listing_id": reminder.listing_id,
                "listing_title": listing.title if listing else "Unknown",
                "location": listing.address if listing else None,
                "scheduled_time": reminder.scheduled_time.isoformat() if reminder.scheduled_time else None,
                "reminder_sent_at": reminder.reminder_sent_at.isoformat() if reminder.reminder_sent_at else None,
                "status": reminder.status.value if reminder.status else "scheduled",
                "sms_sent": reminder.sms_sent,
                "email_sent": reminder.email_sent,
                "snooze_count": reminder.snooze_count,
                "snoozed_until": reminder.snoozed_until.isoformat() if reminder.snoozed_until else None
            })
        
        return {"success": True, "reminders": reminder_list}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/pickup-reminders/settings")
async def get_reminder_settings(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Get reminder settings for the authenticated user"""
    try:
        from backend.models import ReminderSettings
        
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub"))
        
        settings = db.query(ReminderSettings).filter(
            ReminderSettings.user_id == user_id
        ).first()
        
        if not settings:
            # Create default settings
            settings = ReminderSettings(
                user_id=user_id,
                enabled=True,
                advance_notice_hours=2.0,
                sms_enabled=True,
                email_enabled=False,
                auto_reminder=True
            )
            db.add(settings)
            db.commit()
            db.refresh(settings)
        
        return {
            "success": True,
            "settings": {
                "enabled": settings.enabled,
                "advance_notice_hours": settings.advance_notice_hours,
                "sms_enabled": settings.sms_enabled,
                "email_enabled": settings.email_enabled,
                "auto_reminder": settings.auto_reminder
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/pickup-reminders/settings")
async def update_reminder_settings(
    enabled: bool = True,
    advance_notice_hours: float = 2.0,
    sms_enabled: bool = True,
    email_enabled: bool = False,
    auto_reminder: bool = True,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Update reminder settings for the authenticated user"""
    try:
        from backend.models import ReminderSettings
        
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub"))
        
        settings = db.query(ReminderSettings).filter(
            ReminderSettings.user_id == user_id
        ).first()
        
        if not settings:
            settings = ReminderSettings(user_id=user_id)
            db.add(settings)
        
        settings.enabled = enabled
        settings.advance_notice_hours = advance_notice_hours
        settings.sms_enabled = sms_enabled
        settings.email_enabled = email_enabled
        settings.auto_reminder = auto_reminder
        settings.updated_at = datetime.utcnow()
        
        db.commit()
        
        return {"success": True, "message": "Settings updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/pickup-reminders/schedule")
async def schedule_pickup_reminder(
    listing_id: int,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Schedule a pickup reminder for a listing"""
    try:
        from backend.models import PickupReminder, ReminderSettings, PickupReminderStatus
        
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub"))
        
        # Get the listing
        listing = db.query(FoodResource).filter(FoodResource.id == listing_id).first()
        if not listing:
            raise HTTPException(status_code=404, detail="Listing not found")
        
        # Verify user claimed this listing
        if listing.recipient_id != user_id:
            raise HTTPException(status_code=403, detail="You haven't claimed this listing")
        
        # Check if reminder already exists
        existing = db.query(PickupReminder).filter(
            PickupReminder.listing_id == listing_id,
            PickupReminder.user_id == user_id,
            PickupReminder.status.in_([PickupReminderStatus.SCHEDULED, PickupReminderStatus.SNOOZED])
        ).first()
        
        if existing:
            raise HTTPException(status_code=400, detail="Reminder already scheduled for this listing")
        
        # Get user settings
        settings = db.query(ReminderSettings).filter(
            ReminderSettings.user_id == user_id
        ).first()
        
        if not settings:
            settings = ReminderSettings(user_id=user_id)
            db.add(settings)
            db.commit()
            db.refresh(settings)
        
        # Calculate reminder time (advance_notice_hours before pickup)
        from datetime import timedelta
        pickup_time = listing.pickup_window_start
        reminder_time = pickup_time - timedelta(hours=settings.advance_notice_hours)
        
        # Create reminder
        reminder = PickupReminder(
            user_id=user_id,
            listing_id=listing_id,
            scheduled_time=reminder_time,
            status=PickupReminderStatus.SCHEDULED
        )
        
        db.add(reminder)
        db.commit()
        db.refresh(reminder)
        
        return {
            "success": True,
            "message": "Reminder scheduled successfully",
            "reminder_id": reminder.id,
            "scheduled_time": reminder_time.isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/pickup-reminders/{reminder_id}/cancel")
async def cancel_pickup_reminder(
    reminder_id: int,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Cancel a scheduled pickup reminder"""
    try:
        from backend.models import PickupReminder, PickupReminderStatus
        
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub"))
        
        reminder = db.query(PickupReminder).filter(
            PickupReminder.id == reminder_id,
            PickupReminder.user_id == user_id
        ).first()
        
        if not reminder:
            raise HTTPException(status_code=404, detail="Reminder not found")
        
        reminder.status = PickupReminderStatus.CANCELLED
        reminder.updated_at = datetime.utcnow()
        
        db.commit()
        
        return {"success": True, "message": "Reminder cancelled"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/pickup-reminders/{reminder_id}/snooze")
async def snooze_pickup_reminder(
    reminder_id: int,
    minutes: int = 30,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Snooze a pickup reminder"""
    try:
        from backend.models import PickupReminder, PickupReminderStatus
        from datetime import timedelta
        
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub"))
        
        reminder = db.query(PickupReminder).filter(
            PickupReminder.id == reminder_id,
            PickupReminder.user_id == user_id
        ).first()
        
        if not reminder:
            raise HTTPException(status_code=404, detail="Reminder not found")
        
        # Calculate snooze time
        snooze_until = datetime.utcnow() + timedelta(minutes=minutes)
        
        reminder.status = PickupReminderStatus.SNOOZED
        reminder.snoozed_until = snooze_until
        reminder.snooze_count += 1
        reminder.updated_at = datetime.utcnow()
        
        db.commit()
        
        return {
            "success": True,
            "message": f"Reminder snoozed for {minutes} minutes",
            "snoozed_until": snooze_until.isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# Referral System Endpoints
@app.get("/api/referrals/stats")
async def get_referral_stats(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Get referral statistics for admin"""
    try:
        user = verify_token(credentials.credentials, db)
        
        # Check if user is admin
        if user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Admin access required")
        
        # Get all users with referral codes
        users_with_referrals = db.query(User).filter(User.referred_by_code.isnot(None)).all()
        
        # Build referral tree
        referral_data = []
        for user_item in users_with_referrals:
            referrer = db.query(User).filter(User.referral_code == user_item.referred_by_code).first()
            referral_data.append({
                "id": user_item.id,
                "name": user_item.name,
                "email": user_item.email,
                "role": user_item.role.value,
                "referral_code": user_item.referral_code,
                "referred_by_code": user_item.referred_by_code,
                "referrer_name": referrer.name if referrer else "Unknown",
                "referrer_email": referrer.email if referrer else "Unknown",
                "created_at": user_item.created_at.isoformat() if user_item.created_at else None
            })
        
        # Count total referrals per user
        referral_counts = {}
        all_users = db.query(User).filter(User.referral_code.isnot(None)).all()
        for user_item in all_users:
            count = db.query(User).filter(User.referred_by_code == user_item.referral_code).count()
            if count > 0:
                referral_counts[user_item.referral_code] = {
                    "referrer_id": user_item.id,
                    "referrer_name": user_item.name,
                    "referrer_email": user_item.email,
                    "referrer_role": user_item.role.value,
                    "total_referrals": count
                }
        
        return {
            "success": True,
            "total_referred_users": len(referral_data),
            "referral_details": referral_data,
            "top_referrers": dict(sorted(referral_counts.items(), key=lambda x: x[1]['total_referrals'], reverse=True))
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/referrals/user/{user_id}")
async def get_user_referrals(
    user_id: int,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Get all users referred by a specific user"""
    try:
        user = verify_token(credentials.credentials, db)
        
        # Check if user is admin or the user themselves
        if user.role != UserRole.ADMIN and user.id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Get the user's referral code
        target_user = db.query(User).filter(User.id == user_id).first()
        if not target_user:
            raise HTTPException(status_code=404, detail="User not found")
        
        if not target_user.referral_code:
            # Generate one if missing
            new_code = generate_referral_code()
            while db.query(User).filter(User.referral_code == new_code).first():
                new_code = generate_referral_code()
            target_user.referral_code = new_code
            db.add(target_user)
            db.commit()
        
        # Get all users referred by this code
        referred_users = db.query(User).filter(User.referred_by_code == target_user.referral_code).all()
        
        return {
            "success": True,
            "referral_code": target_user.referral_code,
            "referred_users": [
                {
                    "id": u.id,
                    "name": u.name,
                    "email": u.email,
                    "role": u.role.value,
                    "created_at": u.created_at.isoformat() if u.created_at else None
                }
                for u in referred_users
            ],
            "total_referrals": len(referred_users)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/user/referral-code")
async def get_my_referral_code(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Get current user's referral code"""
    try:
        user = verify_token(credentials.credentials, db)
        
        # Generate referral code if user doesn't have one
        if not user.referral_code:
            new_code = generate_referral_code()
            while db.query(User).filter(User.referral_code == new_code).first():
                new_code = generate_referral_code()
            
            user.referral_code = new_code
            db.add(user)
            db.commit()
            db.refresh(user)
        
        return {
            "success": True,
            "referral_code": user.referral_code,
            "referral_link": f"https://dogoods.store/register?ref={user.referral_code}"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# MESSAGING ENDPOINTS
# ============================================

@app.post("/api/messages/send")
async def send_message(request: Request, credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    """Send a message to admin or reply as admin"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub")) if payload and payload.get("sub") is not None else None
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        body = await request.json()
        content = body.get('content', '').strip()
        conversation_id = body.get('conversation_id')
        
        if not content:
            raise HTTPException(status_code=400, detail="Message content required")
        
        # If no conversation_id provided, create one based on user_id
        if not conversation_id:
            conversation_id = f"user_{user_id}"
        
        is_from_admin = user.role == UserRole.ADMIN
        
        message = Message(
            sender_id=user_id,
            conversation_id=conversation_id,
            content=content,
            is_from_admin=is_from_admin,
            is_read=False,
            created_at=datetime.utcnow()
        )
        
        db.add(message)
        db.commit()
        db.refresh(message)
        
        return {
            "success": True,
            "message": {
                "id": message.id,
                "sender_id": message.sender_id,
                "sender_name": user.name,
                "conversation_id": message.conversation_id,
                "content": message.content,
                "is_from_admin": message.is_from_admin,
                "is_read": message.is_read,
                "created_at": message.created_at.isoformat()
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/messages/conversations")
async def get_conversations(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    """Get all conversations (admin only) or user's conversation"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub")) if payload and payload.get("sub") is not None else None
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        if user.role == UserRole.ADMIN:
            # Admin sees all conversations
            conversations = db.query(Message.conversation_id).distinct().all()
            conversation_list = []
            
            for (conv_id,) in conversations:
                # Get latest message and unread count for each conversation
                latest_msg = db.query(Message).filter(
                    Message.conversation_id == conv_id
                ).order_by(Message.created_at.desc()).first()
                
                unread_count = db.query(Message).filter(
                    Message.conversation_id == conv_id,
                    Message.is_from_admin == False,
                    Message.is_read == False
                ).count()
                
                # Get user info from conversation_id
                user_id_from_conv = conv_id.replace("user_", "")
                conv_user = db.query(User).filter(User.id == int(user_id_from_conv)).first() if user_id_from_conv.isdigit() else None
                
                conversation_list.append({
                    "conversation_id": conv_id,
                    "user_name": conv_user.name if conv_user else "Unknown",
                    "user_id": conv_user.id if conv_user else None,
                    "latest_message": latest_msg.content if latest_msg else "",
                    "latest_message_time": latest_msg.created_at.isoformat() if latest_msg else None,
                    "unread_count": unread_count,
                    "is_from_admin": latest_msg.is_from_admin if latest_msg else False
                })
            
            # Sort by latest message time
            conversation_list.sort(key=lambda x: x['latest_message_time'] or '', reverse=True)
            return conversation_list
        else:
            # Regular user sees only their conversation
            conversation_id = f"user_{user_id}"
            messages = db.query(Message).filter(
                Message.conversation_id == conversation_id
            ).order_by(Message.created_at.desc()).limit(1).all()
            
            if messages:
                latest_msg = messages[0]
                unread_count = db.query(Message).filter(
                    Message.conversation_id == conversation_id,
                    Message.is_from_admin == True,
                    Message.is_read == False
                ).count()
                
                return [{
                    "conversation_id": conversation_id,
                    "user_name": "Admin Support",
                    "latest_message": latest_msg.content,
                    "latest_message_time": latest_msg.created_at.isoformat(),
                    "unread_count": unread_count,
                    "is_from_admin": latest_msg.is_from_admin
                }]
            return []
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/messages/{conversation_id}")
async def get_messages(conversation_id: str, credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    """Get all messages in a conversation"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub")) if payload and payload.get("sub") is not None else None
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Check authorization
        if user.role != UserRole.ADMIN and conversation_id != f"user_{user_id}":
            raise HTTPException(status_code=403, detail="Not authorized")
        
        messages = db.query(Message).filter(
            Message.conversation_id == conversation_id
        ).order_by(Message.created_at.asc()).all()
        
        # Mark messages as read
        if user.role == UserRole.ADMIN:
            # Admin reading user messages
            for msg in messages:
                if not msg.is_from_admin and not msg.is_read:
                    msg.is_read = True
        else:
            # User reading admin messages
            for msg in messages:
                if msg.is_from_admin and not msg.is_read:
                    msg.is_read = True
        
        db.commit()
        
        result = []
        for msg in messages:
            sender = db.query(User).filter(User.id == msg.sender_id).first()
            result.append({
                "id": msg.id,
                "sender_id": msg.sender_id,
                "sender_name": sender.name if sender else "Unknown",
                "content": msg.content,
                "is_from_admin": msg.is_from_admin,
                "is_read": msg.is_read,
                "created_at": msg.created_at.isoformat()
            })
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# DONATION SCHEDULE & REMINDER ENDPOINTS
# ============================================

@app.post("/api/schedules/donations")
async def create_donation_schedule(request: Request, credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    """Create a recurring donation schedule"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub")) if payload and payload.get("sub") is not None else None
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user = db.query(User).filter(User.id == user_id).first()
        if not user or user.role != UserRole.DONOR:
            raise HTTPException(status_code=403, detail="Only donors can create donation schedules")
        
        body = await request.json()
        
        # Calculate next donation date based on frequency
        next_date = calculate_next_donation_date(
            body.get('frequency'),
            body.get('day_of_week'),
            body.get('day_of_month'),
            body.get('time_of_day', '09:00'),
            body.get('custom_interval_days')
        )
        
        schedule = DonationSchedule(
            user_id=user_id,
            title=body.get('title'),
            description=body.get('description'),
            category=FoodCategory[body.get('category').upper()],
            estimated_quantity=float(body.get('estimated_quantity', 0)),
            unit=body.get('unit', 'items'),
            perishability=PerishabilityLevel[body.get('perishability', 'MEDIUM').upper()] if body.get('perishability') else None,
            frequency=RecurrenceFrequency[body.get('frequency').upper()],
            day_of_week=body.get('day_of_week'),
            day_of_month=body.get('day_of_month'),
            time_of_day=body.get('time_of_day', '09:00'),
            custom_interval_days=body.get('custom_interval_days'),
            start_date=datetime.fromisoformat(body.get('start_date')) if body.get('start_date') else datetime.utcnow(),
            end_date=datetime.fromisoformat(body.get('end_date')) if body.get('end_date') else None,
            next_donation_date=next_date,
            send_reminders=body.get('send_reminders', True),
            reminder_hours_before=body.get('reminder_hours_before', 24)
        )
        
        db.add(schedule)
        db.commit()
        db.refresh(schedule)
        
        # Create first reminder if enabled
        if schedule.send_reminders:
            create_reminder_for_schedule(db, schedule)
        
        return {
            "id": schedule.id,
            "title": schedule.title,
            "frequency": schedule.frequency.value,
            "next_donation_date": schedule.next_donation_date.isoformat(),
            "is_active": schedule.is_active
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/schedules/donations")
async def get_donation_schedules(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    """Get all donation schedules for the current user"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub")) if payload and payload.get("sub") is not None else None
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        schedules = db.query(DonationSchedule).filter(DonationSchedule.user_id == user_id).order_by(DonationSchedule.next_donation_date).all()
        
        result = []
        for schedule in schedules:
            result.append({
                "id": schedule.id,
                "title": schedule.title,
                "description": schedule.description,
                "category": schedule.category.value,
                "estimated_quantity": schedule.estimated_quantity,
                "unit": schedule.unit,
                "perishability": schedule.perishability.value if schedule.perishability else None,
                "frequency": schedule.frequency.value,
                "day_of_week": schedule.day_of_week,
                "day_of_month": schedule.day_of_month,
                "time_of_day": schedule.time_of_day,
                "next_donation_date": schedule.next_donation_date.isoformat() if schedule.next_donation_date else None,
                "last_donation_date": schedule.last_donation_date.isoformat() if schedule.last_donation_date else None,
                "is_active": schedule.is_active,
                "send_reminders": schedule.send_reminders,
                "reminder_hours_before": schedule.reminder_hours_before,
                "created_at": schedule.created_at.isoformat()
            })
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/schedules/donations/{schedule_id}")
async def update_donation_schedule(schedule_id: int, request: Request, credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    """Update a donation schedule"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub")) if payload and payload.get("sub") is not None else None
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        schedule = db.query(DonationSchedule).filter(DonationSchedule.id == schedule_id, DonationSchedule.user_id == user_id).first()
        if not schedule:
            raise HTTPException(status_code=404, detail="Schedule not found")
        
        body = await request.json()
        
        # Update fields
        if 'title' in body:
            schedule.title = body['title']
        if 'description' in body:
            schedule.description = body['description']
        if 'category' in body:
            schedule.category = FoodCategory[body['category'].upper()]
        if 'estimated_quantity' in body:
            schedule.estimated_quantity = float(body['estimated_quantity'])
        if 'unit' in body:
            schedule.unit = body['unit']
        if 'is_active' in body:
            schedule.is_active = body['is_active']
        if 'send_reminders' in body:
            schedule.send_reminders = body['send_reminders']
        if 'reminder_hours_before' in body:
            schedule.reminder_hours_before = body['reminder_hours_before']
        
        # Recalculate next donation date if frequency changed
        if any(key in body for key in ['frequency', 'day_of_week', 'day_of_month', 'time_of_day', 'custom_interval_days']):
            if 'frequency' in body:
                schedule.frequency = RecurrenceFrequency[body['frequency'].upper()]
            if 'day_of_week' in body:
                schedule.day_of_week = body['day_of_week']
            if 'day_of_month' in body:
                schedule.day_of_month = body['day_of_month']
            if 'time_of_day' in body:
                schedule.time_of_day = body['time_of_day']
            if 'custom_interval_days' in body:
                schedule.custom_interval_days = body['custom_interval_days']
            
            schedule.next_donation_date = calculate_next_donation_date(
                schedule.frequency.value,
                schedule.day_of_week,
                schedule.day_of_month,
                schedule.time_of_day,
                schedule.custom_interval_days
            )
        
        db.commit()
        db.refresh(schedule)
        
        return {"success": True, "schedule": {"id": schedule.id, "next_donation_date": schedule.next_donation_date.isoformat()}}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/schedules/donations/{schedule_id}")
async def delete_donation_schedule(schedule_id: int, credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    """Delete a donation schedule"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub")) if payload and payload.get("sub") is not None else None
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        schedule = db.query(DonationSchedule).filter(DonationSchedule.id == schedule_id, DonationSchedule.user_id == user_id).first()
        if not schedule:
            raise HTTPException(status_code=404, detail="Schedule not found")
        
        db.delete(schedule)
        db.commit()
        
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/reminders")
async def get_reminders(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    """Get all pending reminders for the current user"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub")) if payload and payload.get("sub") is not None else None
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        reminders = db.query(DonationReminder).filter(
            DonationReminder.user_id == user_id,
            DonationReminder.status.in_([ReminderStatus.PENDING, ReminderStatus.SENT])
        ).order_by(DonationReminder.scheduled_for).all()
        
        result = []
        for reminder in reminders:
            result.append({
                "id": reminder.id,
                "schedule_id": reminder.schedule_id,
                "title": reminder.title,
                "message": reminder.message,
                "scheduled_for": reminder.scheduled_for.isoformat(),
                "donation_date": reminder.donation_date.isoformat(),
                "status": reminder.status.value,
                "sent_at": reminder.sent_at.isoformat() if reminder.sent_at else None
            })
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/reminders/{reminder_id}/dismiss")
async def dismiss_reminder(reminder_id: int, credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    """Dismiss a reminder"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub")) if payload and payload.get("sub") is not None else None
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        reminder = db.query(DonationReminder).filter(DonationReminder.id == reminder_id, DonationReminder.user_id == user_id).first()
        if not reminder:
            raise HTTPException(status_code=404, detail="Reminder not found")
        
        reminder.status = ReminderStatus.DISMISSED
        reminder.dismissed_at = datetime.utcnow()
        db.commit()
        
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/reminders/{reminder_id}/complete")
async def complete_reminder(reminder_id: int, credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    """Mark a reminder as completed and update the schedule"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub")) if payload and payload.get("sub") is not None else None
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        reminder = db.query(DonationReminder).filter(DonationReminder.id == reminder_id, DonationReminder.user_id == user_id).first()
        if not reminder:
            raise HTTPException(status_code=404, detail="Reminder not found")
        
        reminder.status = ReminderStatus.COMPLETED
        reminder.completed_at = datetime.utcnow()
        
        # Update schedule's last donation date and calculate next
        schedule = db.query(DonationSchedule).filter(DonationSchedule.id == reminder.schedule_id).first()
        if schedule:
            schedule.last_donation_date = reminder.donation_date
            schedule.next_donation_date = calculate_next_donation_date(
                schedule.frequency.value,
                schedule.day_of_week,
                schedule.day_of_month,
                schedule.time_of_day,
                schedule.custom_interval_days,
                from_date=reminder.donation_date
            )
            
            # Create next reminder
            if schedule.send_reminders and schedule.is_active:
                create_reminder_for_schedule(db, schedule)
        
        db.commit()
        
        return {"success": True, "next_donation_date": schedule.next_donation_date.isoformat() if schedule else None}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Helper functions for schedule calculations
def calculate_next_donation_date(frequency, day_of_week=None, day_of_month=None, time_of_day='09:00', custom_interval_days=None, from_date=None):
    """Calculate the next donation date based on frequency"""
    base_date = from_date if from_date else datetime.utcnow()
    hour, minute = map(int, time_of_day.split(':'))
    
    if frequency == 'daily' or frequency == RecurrenceFrequency.DAILY.value:
        next_date = base_date + timedelta(days=1)
    elif frequency == 'weekly' or frequency == RecurrenceFrequency.WEEKLY.value:
        # Calculate days until next occurrence
        current_day = base_date.weekday()
        if day_of_week is None:
            day_of_week = current_day
        
        days_ahead = day_of_week - current_day
        # If we're on the same day or past it, schedule for next week
        if days_ahead <= 0:
            days_ahead += 7
        next_date = base_date + timedelta(days=days_ahead)
    elif frequency == 'biweekly' or frequency == RecurrenceFrequency.BIWEEKLY.value:
        # Calculate days until next occurrence (2 weeks)
        current_day = base_date.weekday()
        if day_of_week is None:
            day_of_week = current_day
        
        days_ahead = day_of_week - current_day
        # If we're on the same day or past it, schedule for 2 weeks from now
        if days_ahead <= 0:
            days_ahead += 14
        next_date = base_date + timedelta(days=days_ahead)
    elif frequency == 'monthly' or frequency == RecurrenceFrequency.MONTHLY.value:
        # Handle month boundaries and invalid days
        target_day = day_of_month if day_of_month else 1
        
        # Start with next month
        if base_date.month == 12:
            next_month = 1
            next_year = base_date.year + 1
        else:
            next_month = base_date.month + 1
            next_year = base_date.year
        
        # Handle days that don't exist in target month (e.g., Feb 30)
        max_day_in_month = 31
        if next_month in [4, 6, 9, 11]:
            max_day_in_month = 30
        elif next_month == 2:
            # Check for leap year
            is_leap = (next_year % 4 == 0 and next_year % 100 != 0) or (next_year % 400 == 0)
            max_day_in_month = 29 if is_leap else 28
        
        safe_day = min(target_day, max_day_in_month)
        next_date = base_date.replace(year=next_year, month=next_month, day=safe_day)
        
        # If we somehow ended up in the past, move to next month
        if next_date <= base_date:
            if next_date.month == 12:
                next_date = next_date.replace(year=next_date.year + 1, month=1, day=safe_day)
            else:
                next_month = next_date.month + 1
                # Recalculate safe day for the new month
                if next_month in [4, 6, 9, 11]:
                    max_day_in_month = 30
                elif next_month == 2:
                    is_leap = (next_date.year % 4 == 0 and next_date.year % 100 != 0) or (next_date.year % 400 == 0)
                    max_day_in_month = 29 if is_leap else 28
                else:
                    max_day_in_month = 31
                safe_day = min(target_day, max_day_in_month)
                next_date = next_date.replace(month=next_month, day=safe_day)
    elif frequency == 'custom' or frequency == RecurrenceFrequency.CUSTOM.value:
        interval = custom_interval_days or 7
        next_date = base_date + timedelta(days=interval)
    else:
        # Default to weekly
        next_date = base_date + timedelta(days=7)
    
    return next_date.replace(hour=hour, minute=minute, second=0, microsecond=0)

def create_reminder_for_schedule(db: Session, schedule: DonationSchedule):
    """Create a reminder for an upcoming donation"""
    if not schedule.next_donation_date or not schedule.send_reminders:
        return
    
    scheduled_for = schedule.next_donation_date - timedelta(hours=schedule.reminder_hours_before)
    
    # Don't create reminder if it's in the past
    if scheduled_for < datetime.utcnow():
        return
    
    reminder = DonationReminder(
        schedule_id=schedule.id,
        user_id=schedule.user_id,
        title=f"Donation Reminder: {schedule.title}",
        message=f"You have a scheduled donation of {schedule.estimated_quantity} {schedule.unit} of {schedule.category.value} coming up.",
        scheduled_for=scheduled_for,
        donation_date=schedule.next_donation_date
    )
    
    db.add(reminder)
    db.commit()


# -----------------------------
# Feedback System Endpoints
# -----------------------------

@app.post("/api/feedback/submit")
async def submit_feedback(
    request: Request,
    db: Session = Depends(get_db)
):
    """Submit user feedback, error report, or feature request (auth optional)"""
    try:
        data = await request.json()
        
        # Try to get user if authenticated
        user_id = None
        try:
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]
                payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
                user_id = payload.get("sub")
        except:
            pass  # Anonymous feedback is allowed
        
        # Validate feedback type
        feedback_type = data.get("type", "general")
        if feedback_type not in ["bug", "feature_request", "general", "error_report", "improvement"]:
            feedback_type = "general"
        
        # Create feedback record
        feedback = Feedback(
            user_id=user_id,
            type=FeedbackType[feedback_type.upper()],
            subject=data.get("subject", "User Feedback"),
            message=data.get("message", ""),
            url=data.get("url"),
            user_agent=data.get("userAgent"),
            screenshot=data.get("screenshot"),
            error_stack=data.get("errorStack"),
            email=data.get("email"),
            status=FeedbackStatus.NEW
        )
        
        db.add(feedback)
        db.commit()
        db.refresh(feedback)
        
        return {
            "success": True,
            "message": "Thank you for your feedback!",
            "feedback_id": feedback.id
        }
        
    except Exception as e:
        print(f"Error submitting feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/feedback/list")
async def list_feedback(
    status: Optional[str] = None,
    type: Optional[str] = None,
    limit: int = 50,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """List all feedback (admin only)"""
    try:
        # Verify admin
        token = credentials.credentials
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        
        user = db.query(User).filter(User.id == user_id).first()
        if not user or user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Admin access required")
        
        # Build query
        query = db.query(Feedback)
        
        if status:
            query = query.filter(Feedback.status == FeedbackStatus[status.upper()])
        
        if type:
            query = query.filter(Feedback.type == FeedbackType[type.upper()])
        
        feedback_list = query.order_by(Feedback.created_at.desc()).limit(limit).all()
        
        return {
            "success": True,
            "feedback": [
                {
                    "id": f.id,
                    "user_id": f.user_id,
                    "type": f.type.value,
                    "subject": f.subject,
                    "message": f.message,
                    "url": f.url,
                    "status": f.status.value,
                    "email": f.email,
                    "created_at": f.created_at.isoformat(),
                    "has_screenshot": bool(f.screenshot),
                    "screenshot": f.screenshot if f.screenshot else None,
                    "has_error_stack": bool(f.error_stack),
                    "error_stack": f.error_stack if f.error_stack else None
                }
                for f in feedback_list
            ]
        }
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        print(f"Error listing feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/feedback/{feedback_id}/status")
async def update_feedback_status(
    feedback_id: int,
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Update feedback status (admin only)"""
    try:
        # Verify admin
        token = credentials.credentials
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        
        user = db.query(User).filter(User.id == user_id).first()
        if not user or user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Admin access required")
        
        data = await request.json()
        new_status = data.get("status")
        admin_notes = data.get("admin_notes")
        
        feedback = db.query(Feedback).filter(Feedback.id == feedback_id).first()
        if not feedback:
            raise HTTPException(status_code=404, detail="Feedback not found")
        
        if new_status:
            feedback.status = FeedbackStatus[new_status.upper()]
        
        if admin_notes:
            feedback.admin_notes = admin_notes
        
        feedback.updated_at = datetime.utcnow()
        db.commit()
        
        return {"success": True, "message": "Feedback updated"}
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        print(f"Error updating feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -----------------------------
# Donor Impact Statistics
# -----------------------------

@app.get("/api/donor/impact")
async def get_donor_impact(
    timeframe: str = "all",
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Get donor's personal impact statistics"""
    try:
        token = credentials.credentials
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Calculate date range based on timeframe
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        start_date = None
        
        if timeframe == "week":
            start_date = now - timedelta(days=7)
        elif timeframe == "month":
            start_date = now - timedelta(days=30)
        elif timeframe == "year":
            start_date = now - timedelta(days=365)
        # else: all time (no filter)
        
        # Query donations
        query = db.query(FoodResource).filter(FoodResource.donor_id == user_id)
        if start_date:
            query = query.filter(FoodResource.created_at >= start_date)
        
        all_donations = query.all()
        claimed_donations = query.filter(FoodResource.status == "claimed").all()
        active_donations = query.filter(FoodResource.status == "available").all()
        
        # Calculate statistics
        total_donations = len(all_donations)
        claimed_count = len(claimed_donations)
        active_count = len(active_donations)
        
        # Calculate total pounds
        total_pounds = sum([d.qty if d.unit == 'lbs' else d.est_weight_kg * 2.20462 if d.est_weight_kg else d.qty * 0.5 
                           for d in claimed_donations])
        
        # Estimate meals (assuming 1 lb = 3.5 meals on average)
        meals_provided = int(total_pounds * 3.5)
        
        # Estimate people helped (assuming 1 person = 13 meals on average)
        people_helped = max(1, int(meals_provided / 13)) if meals_provided > 0 else 0
        
        # Environmental impact calculations
        co2_saved = int(total_pounds * 1.7)  # ~1.7 lbs CO2 per lb of food saved
        water_saved = int(total_pounds * 23.8)  # ~23.8 gallons per lb of food
        money_saved = int(total_pounds * 8.10)  # ~$8.10 per lb retail value
        
        # Calculate impact score (0-100)
        impact_score = min(100, int((
            total_donations * 2 +
            meals_provided * 0.05 +
            people_helped * 0.5 +
            (100 if total_donations >= 50 else 0)
        ) * 0.8))
        
        # Calculate streak (simplified - would need actual tracking)
        streak_days = 0
        if total_donations > 0:
            recent_donations = db.query(FoodResource).filter(
                FoodResource.donor_id == user_id,
                FoodResource.created_at >= now - timedelta(days=30)
            ).order_by(FoodResource.created_at.desc()).all()
            
            if recent_donations:
                # Simple streak calculation
                last_donation_date = recent_donations[0].created_at
                days_since_last = (now - last_donation_date).days
                if days_since_last <= 7:
                    streak_days = min(30, len([d for d in recent_donations if (now - d.created_at).days <= 30]))
        
        # Get recent donations for display
        recent_donations = db.query(FoodResource).filter(
            FoodResource.donor_id == user_id,
            FoodResource.status == "claimed"
        ).order_by(FoodResource.claimed_at.desc()).limit(5).all()
        
        recent_donations_list = []
        for donation in recent_donations:
            recipient = db.query(User).filter(User.id == donation.recipient_id).first() if donation.recipient_id else None
            recent_donations_list.append({
                "id": donation.id,
                "title": donation.title,
                "qty": donation.qty,
                "unit": donation.unit,
                "claimed_by": recipient.name if recipient else "Anonymous",
                "claimed_at": donation.claimed_at.isoformat() if donation.claimed_at else donation.created_at.isoformat(),
                "meals_provided": int((donation.qty if donation.unit == 'lbs' else donation.qty * 0.5) * 3.5)
            })
        
        return {
            "success": True,
            "stats": {
                "total_donations": total_donations,
                "total_pounds": int(total_pounds),
                "meals_provided": meals_provided,
                "people_helped": people_helped,
                "co2_saved": co2_saved,
                "water_saved": water_saved,
                "money_saved_recipients": money_saved,
                "active_listings": active_count,
                "claimed_listings": claimed_count,
                "impact_score": impact_score,
                "streak_days": streak_days,
                "badges_earned": min(5, total_donations // 10)
            },
            "recent_donations": recent_donations_list
        }
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        print(f"Error fetching donor impact: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# FAVORITES / BOOKMARKS ENDPOINTS
# =====================================================

@app.get("/api/favorites")
async def get_favorites(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    """Get all favorite locations for the authenticated user"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub"))
        
        favorites = db.query(FavoriteLocation).filter(
            FavoriteLocation.user_id == user_id,
            FavoriteLocation.is_active == True
        ).order_by(FavoriteLocation.visit_count.desc(), FavoriteLocation.created_at.desc()).all()
        
        result = []
        for fav in favorites:
            fav_data = {
                "id": fav.id,
                "name": fav.name,
                "address": fav.address,
                "coords_lat": fav.coords_lat,
                "coords_lng": fav.coords_lng,
                "location_type": fav.location_type,
                "notes": fav.notes,
                "tags": fav.tags,
                "visit_count": fav.visit_count,
                "last_visited": fav.last_visited.isoformat() if fav.last_visited else None,
                "notify_new_listings": fav.notify_new_listings,
                "notification_radius_km": fav.notification_radius_km,
                "created_at": fav.created_at.isoformat(),
                "updated_at": fav.updated_at.isoformat()
            }
            
            # Add donor details if it's a donor favorite
            if fav.location_type == 'donor' and fav.donor_id:
                donor = db.query(User).filter(User.id == fav.donor_id).first()
                if donor:
                    fav_data["donor"] = {
                        "id": donor.id,
                        "name": donor.name,
                        "trust_score": donor.trust_score
                    }
            
            # Add center details if it's a distribution center favorite
            elif fav.location_type == 'distribution_center' and fav.center_id:
                center = db.query(DistributionCenter).filter(DistributionCenter.id == fav.center_id).first()
                if center:
                    fav_data["center"] = {
                        "id": center.id,
                        "name": center.name,
                        "hours": getattr(center, 'hours', None)
                    }
            
            result.append(fav_data)
        
        return result
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        print(f"Error fetching favorites: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/favorites")
async def add_favorite(request: Request, credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    """Add a new favorite location for the authenticated user"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub"))
        body = await request.json()

        # Donors cannot favorite their own listings.
        if body.get('location_type') == 'donor':
            donor_id = body.get('donor_id')
            if donor_id is None and body.get('location_id') is not None:
                try:
                    listing_id = int(body.get('location_id'))
                    item = db.query(FoodResource).filter(FoodResource.id == listing_id).first()
                    donor_id = item.donor_id if item else None
                except Exception:
                    donor_id = None

            if donor_id is not None and str(donor_id) == str(user_id):
                raise HTTPException(status_code=400, detail="You cannot favorite your own listing")
        
        # Validate required fields
        if not body.get('name') or not body.get('address'):
            raise HTTPException(status_code=400, detail="Name and address are required")
        
        # Check for duplicates based on location type and reference ID
        existing = None
        if body.get('donor_id'):
            existing = db.query(FavoriteLocation).filter(
                FavoriteLocation.user_id == user_id,
                FavoriteLocation.donor_id == body.get('donor_id'),
                FavoriteLocation.is_active == True
            ).first()
        elif body.get('center_id'):
            existing = db.query(FavoriteLocation).filter(
                FavoriteLocation.user_id == user_id,
                FavoriteLocation.center_id == body.get('center_id'),
                FavoriteLocation.is_active == True
            ).first()
        else:
            # For general locations, check by coordinates proximity (within 50 meters)
            favorites = db.query(FavoriteLocation).filter(
                FavoriteLocation.user_id == user_id,
                FavoriteLocation.location_type == 'general',
                FavoriteLocation.is_active == True
            ).all()
            
            for fav in favorites:
                # Simple distance check (approximate)
                lat_diff = abs(fav.coords_lat - body.get('coords_lat', 0))
                lng_diff = abs(fav.coords_lng - body.get('coords_lng', 0))
                if lat_diff < 0.0005 and lng_diff < 0.0005:  # ~50 meters
                    existing = fav
                    break
        
        if existing:
            return {"success": False, "message": "This location is already in your favorites", "favorite_id": existing.id}
        
        # Create new favorite
        favorite = FavoriteLocation(
            user_id=user_id,
            name=body.get('name'),
            address=body.get('address'),
            coords_lat=body.get('coords_lat'),
            coords_lng=body.get('coords_lng'),
            location_type=body.get('location_type', 'general'),
            donor_id=body.get('donor_id'),
            center_id=body.get('center_id'),
            notes=body.get('notes', ''),
            tags=body.get('tags'),
            notify_new_listings=body.get('notify_new_listings', False),
            notification_radius_km=body.get('notification_radius_km', 5.0),
            created_at=datetime.utcnow()
        )
        
        db.add(favorite)
        db.commit()
        db.refresh(favorite)
        
        return {
            "success": True,
            "message": "Location added to favorites",
            "favorite_id": favorite.id,
            "favorite": {
                "id": favorite.id,
                "name": favorite.name,
                "address": favorite.address,
                "location_type": favorite.location_type
            }
        }
        
    except HTTPException:
        raise
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        print(f"Error adding favorite: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/favorites/{favorite_id}")
async def update_favorite(favorite_id: int, request: Request, credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    """Update a favorite location (notes, tags, notifications)"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub"))
        body = await request.json()
        
        favorite = db.query(FavoriteLocation).filter(
            FavoriteLocation.id == favorite_id,
            FavoriteLocation.user_id == user_id
        ).first()
        
        if not favorite:
            raise HTTPException(status_code=404, detail="Favorite not found")
        
        # Update allowed fields
        if 'name' in body:
            favorite.name = body['name']
        if 'notes' in body:
            favorite.notes = body['notes']
        if 'tags' in body:
            favorite.tags = body['tags']
        if 'notify_new_listings' in body:
            favorite.notify_new_listings = body['notify_new_listings']
        if 'notification_radius_km' in body:
            favorite.notification_radius_km = body['notification_radius_km']
        
        favorite.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(favorite)
        
        return {
            "success": True,
            "message": "Favorite updated successfully",
            "favorite": {
                "id": favorite.id,
                "name": favorite.name,
                "notes": favorite.notes,
                "tags": favorite.tags,
                "notify_new_listings": favorite.notify_new_listings
            }
        }
        
    except HTTPException:
        raise
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        print(f"Error updating favorite: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/favorites/{favorite_id}/visit")
async def record_visit(favorite_id: int, credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    """Record a visit to a favorite location"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub"))
        
        favorite = db.query(FavoriteLocation).filter(
            FavoriteLocation.id == favorite_id,
            FavoriteLocation.user_id == user_id
        ).first()
        
        if not favorite:
            raise HTTPException(status_code=404, detail="Favorite not found")
        
        favorite.visit_count += 1
        favorite.last_visited = datetime.utcnow()
        favorite.updated_at = datetime.utcnow()
        
        db.commit()
        
        return {
            "success": True,
            "visit_count": favorite.visit_count,
            "last_visited": favorite.last_visited.isoformat()
        }
        
    except HTTPException:
        raise
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        print(f"Error recording visit: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/favorites/{favorite_id}")
async def remove_favorite(favorite_id: int, credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    """Remove a favorite location (soft delete)"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub"))
        
        favorite = db.query(FavoriteLocation).filter(
            FavoriteLocation.id == favorite_id,
            FavoriteLocation.user_id == user_id
        ).first()
        
        if not favorite:
            raise HTTPException(status_code=404, detail="Favorite not found")
        
        # Soft delete
        favorite.is_active = False
        favorite.updated_at = datetime.utcnow()
        db.commit()
        
        return {"success": True, "message": "Favorite removed"}
        
    except HTTPException:
        raise
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        print(f"Error removing favorite: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# ADMIN: TRUST BADGE MANAGEMENT
# =====================================================

@app.put("/api/admin/users/{user_id}/trust-badges")
async def update_user_trust_badges(
    user_id: int,
    request: Request,
    admin_user: User = Depends(verify_admin),
    db: Session = Depends(get_db)
):
    """Admin endpoint to assign/update trust badges for users"""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        body = await request.json()
        
        # Update trust badge fields
        if 'verified_by_aglf' in body:
            user.verified_by_aglf = body['verified_by_aglf']
        if 'school_partner' in body:
            user.school_partner = body['school_partner']
        if 'partner_badge' in body:
            user.partner_badge = body['partner_badge']
        if 'partner_since' in body and body['partner_since']:
            user.partner_since = datetime.fromisoformat(body['partner_since'].replace('Z', '+00:00'))
        
        # Set partner_since if becoming a partner for the first time
        if (user.verified_by_aglf or user.school_partner) and not user.partner_since:
            user.partner_since = datetime.utcnow()
        
        db.commit()
        db.refresh(user)
        
        return serialize_user(user)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error updating trust badges: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/admin/centers/{center_id}/trust-badges")
async def update_center_trust_badges(
    center_id: int,
    request: Request,
    admin_user: User = Depends(verify_admin),
    db: Session = Depends(get_db)
):
    """Admin endpoint to assign/update trust badges for distribution centers"""
    try:
        center = db.query(DistributionCenter).filter(DistributionCenter.id == center_id).first()
        if not center:
            raise HTTPException(status_code=404, detail="Center not found")
        
        body = await request.json()
        
        # Update trust badge fields
        if 'verified_by_aglf' in body:
            center.verified_by_aglf = body['verified_by_aglf']
        if 'school_partner' in body:
            center.school_partner = body['school_partner']
        if 'partner_badge' in body:
            center.partner_badge = body['partner_badge']
        if 'partner_since' in body and body['partner_since']:
            center.partner_since = datetime.fromisoformat(body['partner_since'].replace('Z', '+00:00'))
        
        # Set partner_since if becoming a partner for the first time
        if (center.verified_by_aglf or center.school_partner) and not center.partner_since:
            center.partner_since = datetime.utcnow()
        
        # Update last_updated timestamp
        center.last_updated = datetime.utcnow()
        
        db.commit()
        db.refresh(center)
        
        return {
            "id": center.id,
            "name": center.name,
            "verified_by_aglf": center.verified_by_aglf,
            "school_partner": center.school_partner,
            "partner_badge": center.partner_badge,
            "partner_since": center.partner_since.isoformat() if center.partner_since else None,
            "last_updated": center.last_updated.isoformat() if center.last_updated else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error updating center trust badges: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/users/{user_id}/activity")
async def update_user_activity(
    user_id: int,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Update user's last_active timestamp (called automatically by frontend)"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        requesting_user_id = int(payload.get("sub"))
        
        # Users can only update their own activity
        if requesting_user_id != user_id:
            raise HTTPException(status_code=403, detail="Cannot update other users' activity")
        
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        user.last_active = datetime.utcnow()
        db.commit()
        
        return {"success": True, "last_active": user.last_active.isoformat()}
        
    except HTTPException:
        raise
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        print(f"Error updating user activity: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# SMART NOTIFICATIONS
# ============================================================================

@app.get("/api/notification-preferences")
async def get_notification_preferences(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Get user's notification preferences"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub"))
        
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Parse JSON string if needed
        if user.notification_preferences:
            if isinstance(user.notification_preferences, str):
                prefs = json.loads(user.notification_preferences)
            else:
                prefs = user.notification_preferences
        else:
            prefs = {
                "enabled": False,
                "maxDistance": 2,
                "categories": [],
                "dietaryTags": [],
                "favoriteLocations": [],
                "quietHours": {"start": "22:00", "end": "08:00"},
                "maxPerDay": 3,
                "urgencyOnly": False
            }
        
        return prefs
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        print(f"Error getting notification preferences: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/notification-preferences")
async def update_notification_preferences(
    preferences: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Update user's notification preferences"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub"))
        
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Store as JSON string
        user.notification_preferences = json.dumps(preferences)
        db.commit()
        
        return {"success": True, "preferences": preferences}
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        db.rollback()
        print(f"Error updating notification preferences: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/notification-behavior")
async def get_notification_behavior(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Get learned behavior data for AI notification filtering"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub"))
        
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Parse JSON string if needed
        if user.notification_behavior:
            if isinstance(user.notification_behavior, str):
                behavior = json.loads(user.notification_behavior)
            else:
                behavior = user.notification_behavior
        else:
            behavior = {
                "clickedCategories": {},
                "ignoredCategories": {},
                "clickedTimes": [],
                "preferredDistance": 2,
                "responseRate": 0
            }
        
        return behavior
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        print(f"Error getting notification behavior: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/notification-sent")
async def track_notification_sent(
    notification: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Track that a notification was sent (for learning)"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub"))
        
        # Store notification history
        # In production, you'd want a dedicated notifications table
        # For now, we'll just return success
        
        return {"success": True}
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        print(f"Error tracking notification: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/notification-clicked")
async def track_notification_clicked(
    click_data: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Track that a notification was clicked (for AI learning)"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub"))
        
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Parse behavior data
        if user.notification_behavior:
            if isinstance(user.notification_behavior, str):
                behavior = json.loads(user.notification_behavior)
            else:
                behavior = user.notification_behavior
        else:
            behavior = {
                "clickedCategories": {},
                "ignoredCategories": {},
                "clickedTimes": [],
                "preferredDistance": 2,
                "responseRate": 0
            }
        
        category = click_data.get("category")
        if category:
            behavior["clickedCategories"][category] = behavior["clickedCategories"].get(category, 0) + 1
        
        # Add click time for pattern analysis
        behavior["clickedTimes"].append(click_data.get("clicked_at"))
        
        # Calculate response rate
        total_sent = sum(behavior["clickedCategories"].values()) + sum(behavior["ignoredCategories"].values())
        total_clicked = sum(behavior["clickedCategories"].values())
        if total_sent > 0:
            behavior["responseRate"] = total_clicked / total_sent
        
        # Store as JSON string
        user.notification_behavior = json.dumps(behavior)
        db.commit()
        
        return {"success": True, "behavior": behavior}
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        db.rollback()
        print(f"Error tracking notification click: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/listings/recent")
async def get_recent_listings(
    minutes: int = 30,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Get listings created in the last N minutes (for notification checking)"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub"))
        
        # Calculate time threshold
        time_threshold = datetime.utcnow() - timedelta(minutes=minutes)
        
        # Get recent listings
        listings = db.query(FoodResource).filter(
            FoodResource.created_at >= time_threshold,
            FoodResource.available == True
        ).all()
        
        # Serialize listings
        result = []
        for listing in listings:
            item = serialize_listing(listing)
            
            # Calculate distance (would need user location)
            # For now, use a placeholder
            item["distance"] = 1.5
            
            # Calculate hours until expiry
            if listing.expiration_date:
                hours_left = (listing.expiration_date - datetime.utcnow()).total_seconds() / 3600
                item["hours_until_expiry"] = max(0, hours_left)
            
            result.append(item)
        
        return result
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        print(f"Error getting recent listings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sms-consent")
async def get_sms_consent(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Get user's SMS consent status and preferences"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub"))
        
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Parse notification types
        notification_types = []
        if user.sms_notification_types:
            if isinstance(user.sms_notification_types, str):
                notification_types = json.loads(user.sms_notification_types)
            else:
                notification_types = user.sms_notification_types
        
        return {
            "consent_given": user.sms_consent_given or False,
            "consent_date": user.sms_consent_date.isoformat() if user.sms_consent_date else None,
            "notification_types": notification_types,
            "opt_out_date": user.sms_opt_out_date.isoformat() if user.sms_opt_out_date else None,
            "phone": user.phone,
            "phone_verified": user.phone_verified or False
        }
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        print(f"Error getting SMS consent: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/sms-consent")
async def update_sms_consent(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Update user's SMS consent and notification preferences"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub"))
        
        consent_data = await request.json()
        
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Get client IP for compliance logging
        client_ip = request.client.host
        
        # Update consent status
        consent_given = consent_data.get("consent_given", False)
        notification_types = consent_data.get("notification_types", [])
        
        if consent_given:
            # User is opting IN
            user.sms_consent_given = True
            user.sms_consent_date = datetime.utcnow()
            user.sms_consent_ip = client_ip
            user.sms_opt_out_date = None  # Clear any previous opt-out
            user.sms_notification_types = json.dumps(notification_types)
        else:
            # User is opting OUT
            user.sms_consent_given = False
            user.sms_opt_out_date = datetime.utcnow()
            user.sms_notification_types = json.dumps([])  # Clear notification types
        
        db.commit()
        
        return {
            "success": True,
            "consent_given": user.sms_consent_given,
            "consent_date": user.sms_consent_date.isoformat() if user.sms_consent_date else None,
            "notification_types": notification_types if consent_given else [],
            "message": "SMS preferences updated successfully"
        }
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        db.rollback()
        print(f"Error updating SMS consent: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Stop AI background jobs on shutdown
@app.on_event("shutdown")
async def shutdown_event():
    try:
        await ai_stop_jobs()
    except Exception as _ai_exc:
        print(f"AI shutdown error: {_ai_exc}")

# Mount static files at the end to allow API routes to take precedence
# /uploads serves user-uploaded photos (chat attachments, listing images)
# from a writable directory outside the source tree.
_UPLOADS_DIR = os.path.join(PROJECT_ROOT, "uploads")
os.makedirs(_UPLOADS_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=_UPLOADS_DIR), name="uploads")
app.mount("/", StaticFiles(directory=PROJECT_ROOT, html=True), name="root")



