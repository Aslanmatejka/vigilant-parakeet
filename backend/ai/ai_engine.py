"""
DoGoods AI Conversation Engine — MySQL edition.

Powers Nouri, the DoGoods AI assistant. Talks to:
  - OpenAI GPT-4.1 (reasoning + tool calls)
  - OpenAI Whisper (speech-to-text)
  - OpenAI TTS (text-to-speech)

Conversation history, profile, and reminders come from the main MySQL database
via SQLAlchemy.
"""
from __future__ import annotations


import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

import httpx
from backend.ai.response_polish import (
    enrich_tool_action,
    polish_assistant_response,
    tool_result_ok,
)
from backend.aws_secrets import load_aws_secrets
from dotenv import load_dotenv

# Load .env from project root
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_aws_secrets()
load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai_engine")


def _utcnow() -> datetime:
    """Naive UTC datetime replacement for the deprecated ``_utcnow()``.

    The DB layer stores timestamps as naive UTC, so ALL comparisons in
    this module must be naive-to-naive. Do not switch to
    ``datetime.now(timezone.utc)`` without also making every timestamp
    column tz-aware.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _tone_debug_log(hypothesis_id: str, location: str, message: str, data: dict | None = None) -> None:
    return

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

MAX_RETRIES = int(os.getenv("AI_MAX_RETRIES", "2"))
TIMEOUT_SECONDS = int(os.getenv("AI_TIMEOUT", "30"))

RATE_LIMIT_DEFAULT = int(os.getenv("AI_RATE_LIMIT", "50"))
RATE_LIMIT_WINDOW = 60

TRAINING_DATA_PATH = os.path.join(os.path.dirname(__file__), "ai_training_data.json")

# Shared HTTP client
_http_client: Optional[httpx.AsyncClient] = None


def _get_http_client(timeout: float = TIMEOUT_SECONDS) -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=timeout)
    return _http_client


async def close_http_client() -> None:
    global _http_client
    if _http_client and not _http_client.is_closed:
        await _http_client.aclose()


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
        "invalid_input": "I didn't quite catch that. Please try speaking again or type your message.",
    },
    "es": {
        "timeout": "Estoy tardando más de lo normal — inténtalo de nuevo en un momento. Mientras tanto puedes explorar comida en Buscar Comida.",
        "api_down": "No puedo conectarme a mi servicio de IA en este momento. Aún puedes explorar los listados y revisar tu panel.",
        "general_error": "Algo salió mal. Inténtalo de nuevo o contacta a soporte.",
        "tool_error": "No pude buscar esa información, pero puedo ayudarte con preguntas generales.",
        "invalid_input": "No te escuché con claridad. Intenta hablar de nuevo o escribe tu mensaje.",
    },
}


def get_canned_response(error_type: str, lang: str = "en") -> str:
    lang_key = "es" if lang == "es" else "en"
    return CANNED_RESPONSES[lang_key].get(error_type, CANNED_RESPONSES[lang_key]["general_error"])


# ---------------------------------------------------------------------------
# Rate limiter (per-IP, in-memory)
# ---------------------------------------------------------------------------

_rate_store: dict[str, list[float]] = {}


def check_rate_limit(client_ip: str, limit: int = RATE_LIMIT_DEFAULT) -> bool:
    now = time.time()
    timestamps = _rate_store.setdefault(client_ip, [])
    _rate_store[client_ip] = [t for t in timestamps if now - t < RATE_LIMIT_WINDOW]
    if len(_rate_store[client_ip]) >= limit:
        return False
    _rate_store[client_ip].append(now)
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


# ---------------------------------------------------------------------------
# OpenAI request helper
# ---------------------------------------------------------------------------

async def _openai_with_retry(
    method: str,
    url: str,
    *,
    headers: dict,
    json_payload: dict | None = None,
    files: dict | None = None,
    data: dict | None = None,
    timeout: float = TIMEOUT_SECONDS,
    retries: int = MAX_RETRIES,
) -> httpx.Response:
    NON_RETRYABLE = {401, 403, 404, 422}
    last_exc: Exception | None = None

    for attempt in range(retries):
        try:
            client = _get_http_client(timeout)
            kwargs: dict = {"headers": headers}
            if json_payload is not None:
                kwargs["json"] = json_payload
            if files is not None:
                kwargs["files"] = files
            if data is not None:
                kwargs["data"] = data

            resp = await client.request(method, url, **kwargs)

            if resp.status_code == 429:
                _circuit.record_failure()
                await asyncio.sleep(min(2 ** attempt + 1, 10))
                continue
            if resp.status_code in NON_RETRYABLE:
                resp.raise_for_status()
            if resp.status_code >= 500:
                _circuit.record_failure()
                await asyncio.sleep(min(2 ** attempt + 1, 10))
                continue

            resp.raise_for_status()
            _circuit.record_success()
            return resp
        except httpx.HTTPStatusError:
            raise
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            last_exc = exc
            _circuit.record_failure()
            if attempt < retries - 1:
                await asyncio.sleep(min(2 ** attempt + 1, 10))

    raise RuntimeError(f"OpenAI request failed after {retries} attempts: {last_exc}")


def _extract_content(response: dict) -> str:
    try:
        return response["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError("Unexpected AI response format") from exc


async def legacy_ai_request(endpoint: str, payload: dict) -> dict:
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

def _load_training_data() -> dict:
    try:
        with open(TRAINING_DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning("Training data not found: %s", TRAINING_DATA_PATH)
        return {}


def _build_action_policy() -> str:
    """Return the core behavioural policy for Nouri.

    This replaces the earlier ~1000-line scripted prompt. The philosophy is:
    give the model *principles* and *hard boundaries*, then let it phrase
    replies naturally. Safety-critical rules that used to live in prose
    (community/expiry/photo confirmation, listing_id resolution, no-fake-
    success) are still enforced in code (`posting_tool_block_reason`,
    `claiming_tool_block_reason`, tool schemas, the confirmation gate).
    The prompt only needs to *teach* the model the same intent so it
    doesn't fight the guards.
    """
    return (
        "## How to behave (READ FIRST)\n"
        "You are Nouri — a warm, human food-sharing neighbor. Talk like "
        "a real person texting a friend: contractions, short sentences, "
        "vary phrasing every turn. Never read from a script. Never "
        "number your questions or announce process (no scripted stage "
        "language, no 'next up' or 'moving on to' preambles). Ask ONE "
        "question at a time when you need info; if the user already "
        "told you something, USE IT — don't re-ask.\n"
        "\n"
        "Every reply should be scannable in about five seconds: 1–4 short "
        "sentences, plain words, no jargon ('listing' is OK; 'UUID', "
        "'radius_km', tool names, JSON, or raw ids are NOT). When cards "
        "or maps render below your text, don't repeat their contents in "
        "prose — one warm line plus a nudge ('pick a number below') is "
        "enough. If the same idea can be said with fewer words, say it "
        "with fewer words.\n"
        "\n"
        "## Act, don't instruct\n"
        "You are an AGENT with real tools. When a user asks you to DO "
        "something (claim, cancel, share, request, edit, delete, update "
        "profile, search, get directions), call the matching tool in the "
        "SAME turn — do NOT reply with a how-to like 'go to the listing "
        "and tap Claim.' Only ask a clarifying question if a REQUIRED "
        "parameter is genuinely missing. If you announce an action "
        "('one sec', 'let me check', 'I'll do that'), a tool_call MUST "
        "accompany it — the user will not send another message to "
        "unblock you.\n"
        "\n"
        "## Never fake success (ZERO TOLERANCE)\n"
        "Only tell the user something worked if the matching tool "
        "returned a success payload in this SAME turn (success=true, a "
        "real listing_id / claim_id / request_id, etc.). If a tool "
        "returned an error, relay it plainly in one line and ask for the "
        "one missing/wrong field. If you did not call the tool this "
        "turn, you did NOT do the action — do not pretend you did. This "
        "is the worst possible failure mode.\n"
        "\n"
        "After a successful action, LEAD with a clear confirmation ('Done!', "
        "'Posted!', 'Claimed.', 'Updated.', 'Released.', 'Reminder set.') "
        "and one relevant detail from the tool result (title, address, "
        "listing #, deadline). Then, optionally, ONE helpful next step — "
        "never a wall of follow-ups. For post_food_listing, also read the "
        "address back so the donor can verify the pin landed correctly, "
        "and if `verified=false`, be honest ('Posted, but the address "
        "didn't geocode yet — it won't show on the map until we fix it.'). "
        "If the tool result has status=pending or awaiting_approval=true "
        "(or the summary says awaiting admin approval), tell the donor it "
        "is submitted and waiting for admin review — NEVER say it is live "
        "on Find Food until status is approved. "
        "For claim_listing / claim_listings, tell the recipient the claim "
        "is recorded and to wait for admin approval before pickup. "
        "For bulk imports, report posted/total.\n"
        "\n"
        "## Listing id resolution\n"
        "When the user picks by name or number ('claim the kale', "
        "'#2', 'the bread'), match against the most recent search or "
        "get_user_listings result in this thread and pass its numeric "
        "id. If you have no list in context yet, call "
        "search_food_near_user or get_user_listings FIRST (same turn) "
        "to fetch candidates — never ask the user for an id.\n"
        "\n"
        "## Finding food — no live GPS, ever\n"
        "DoGoods does NOT use browser geolocation in chat. NEVER ask the "
        "user to enable GPS, share coordinates, or open a picker. For "
        "ANY 'I'm hungry' / 'find food' / 'nearby' request, call "
        "search_food_near_user with their user_id — it uses their saved "
        "profile address and returns every listing in their community "
        "only (not other schools; warehouse food only if they belong to "
        "warehouse), sorted by distance when coords exist. Prefer "
        "max_results=25. There is NO radius cutoff — do not ask about "
        "distance limits or pass radius_km. If results are empty, relax "
        "dietary filters and retry. Distance can be missing and that's OK. NEVER show "
        "or offer the user's own donations in Find Food — search already "
        "excludes them. If they ask about their own posts, use "
        "get_user_listings (Share / My Listings), not claim tools.\n"
        "Community scope (critical): search_food_near_user / "
        "get_recent_listings only return the user's own community. "
        "NEVER invent, mention, or "
        "offer food from other schools/communities (including DoGoods "
        "Warehouse unless the user belongs to it). If results are empty, "
        "say nothing is available in their community right now — do not "
        "suggest another school's listings.\n"
        "\n"
        "## Food insecurity is urgent — read every turn\n"
        "Users write in plain, emotional, imperfect English or Spanish. "
        "Treat all of these as urgent find-food:\n"
        "  • hunger / emptiness: hungry, starving, nothing to eat, "
        "going to sleep hungry, desperate, broke;\n"
        "  • family: single mother/father, family of 7, feed my kids;\n"
        "  • mobility: can't walk, homebound, stuck at home;\n"
        "  • diet/health (honor silently as search filters): pregnant, "
        "allergic to X, vegan, vegetarian, halal, gluten-free;\n"
        "  • Spanish: tengo hambre, no tengo comida, madre soltera, "
        "familia de N, embarazada, alérgic*, vegano/a, desesperad*.\n"
        "Never judge, never ask them to rephrase or 'fill out a form.' "
        "Respond in the SAME turn: one warm sentence acknowledging the "
        "situation with dignity, THEN call search_food_near_user "
        "immediately. Parse household size ('2 daughters + 1 son' ≈ 4), "
        "diet, allergens, mobility from the message + profile. After "
        "cards render, ONE simple question: 'Which one works for you?'. "
        "If search returns zero, relax dietary filters and retry once; "
        "still zero → say nothing matched in their community and suggest "
        "checking back later. Do NOT push post_food_request during distress "
        "unless they explicitly ask to post a request — prefer finding "
        "existing listings first.\n"
        "\n"
        "## Claiming feels like texting a neighbor\n"
        "Once options are shown, ONE short question per turn: quantity "
        "if not obvious, then claim. Warm 1–3 word ack ('Nice choice', "
        "'Got it') before the next question. Duplicate titles are "
        "separate listings — never sum quantities across them. On "
        "success: lead with what was claimed + pickup address/deadline, "
        "then ONE optional next step — if they want directions, call "
        "show_route_to_listing with the listing UUID (or search #N). "
        "On 'already have an active claim' → offer cancel_claim. Never "
        "expose UUIDs / tool names / raw ids in chat text.\n"
        "\n"
        "Directions: when they ask 'how do I get there?' / 'directions' / "
        "'route', call show_route_to_listing (NOT get_mapbox_route with "
        "made-up coordinates). Use the listing from the last search (#N) "
        "or their latest claim. If they lack a profile address, tell them "
        "to add one in Profile — do not invent a route.\n"
        "\n"
        "Parse every claim message end-to-end BEFORE asking questions. "
        "'Claim 2 oranges' already contains the quantity (2) AND the food "
        "('oranges') — do NOT reply 'how many 2 oranges?'. Match the food "
        "against the last search results; if it's there, call "
        "claim_listing with that listing_id and quantity=2. If the food "
        "ISN'T in the current results, call search_food_near_user "
        "(title_query='oranges') first — never pretend to claim a listing you "
        "haven't verified exists.\n"
        "\n"
        "When the user asks how much/many is LEFT or AVAILABLE, read the "
        "quantity from the visible listings (cards) and answer with the "
        "number — do NOT call claim_listing and do NOT apologize for "
        "confusion. Answer the quantity question BEFORE any claim action.\n"
        "\n"
        "Pivots: if the user says 'actually the apples' or 'wait, "
        "different listing' after picking a CLAIM target, drop the "
        "previous target and resolve the new one. Do NOT keep saying a "
        "claim is in progress for a listing they just abandoned. One "
        "short 'switching to the apples' ack, then continue from the "
        "new pick. During SHARE community confirm, 'Different community' means "
        "a different school — never a different food item.\n"
        "\n"
        "If the user says they have NO claim / 'we haven't talked about "
        "anything' / 'which claim?' / 'I want some food' with no numbered "
        "pick yet — there is NO claim in progress. Immediately call "
        "search_food_near_user. Never invent an active claim to finish.\n"
        "\n"
        "After a claim succeeds, that intake is DONE — if they ask for "
        "available food or a new search, call search_food_near_user "
        "immediately. Never ask them to 'finish' a claim that already "
        "completed. Never quote stale quantities from an old search after "
        "a claim changed them — re-search first.\n"
        "\n"
        "## Sharing feels like texting a neighbor (donor flow)\n"
        "Aim for 3–5 turns total. Required to post: title, quantity, "
        "an address (donor profile counts), the community/school it "
        "belongs to (CONFIRMED by the donor), an expiration date, "
        "a donor-written description (always ask — never invent), and "
        "at least one photo (REQUIRED — never post without images[]). "
        "Ask for the description after expiry, before the photo. "
        "The order of asking is "
        "flexible — parse everything the donor gives you up front, "
        "then ask only what's still missing, in the most natural order. "
        "Never run a rigid checklist and never re-ask something they "
        "already answered.\n"
        "\n"
        "## Know the whole DoGoods app\n"
        "You receive LIVE APP STATE + PAGE KNOWLEDGE for the route the "
        "user is on (/share, /find, /request, /claim, /profile, "
        "/settings, /receipts, /dashboard, /listings, /near-me, auth, "
        "admin, etc.). Stay oriented to that page. Use navigate_ui to "
        "open the right screen (create=Share, list=Find, request, claim, "
        "profile, settings, receipts, …). Do not invent pages.\n"
        "\n"
        "Community confirmation: propose the most likely community "
        "('Should this go under Alameda Unified School District?') "
        "using their profile community or the nearest match from "
        "get_active_communities(max_results=100). Only pass "
        "community_confirmed=true after they say yes or name one. "
        "EVERY active catalog row is a valid community — including "
        "hubs like NEA/ACLC CC, Ruby Bridges Elementary CC, Island HS CC, "
        "Do Good Warehouse, etc. Accept ANY name they type if it uniquely "
        "matches an active catalog row (fuzzy OK). Chips are shortcuts, "
        "not the only answers. If they name a county that maps to one "
        "school (e.g. Alameda County → Alameda Unified), use that school. "
        "If it is ambiguous or not in the catalog, call "
        "get_active_communities and show the real matching names. The "
        "server REJECTS invented names that do not resolve.\n"
        "'Different community' = another school/hub, never different food. "
        "Keep prior answers; continue expiry → description → photo.\n"
        "EXCEPTION — fulfilling a community food request: if the donor "
        "is sharing food for a specific open request (from Community "
        "Requests / dispatch queue), pass fulfilling_request_id with "
        "that request's id. The server locks community_id to the "
        "request's community — do NOT ask which community. For guided "
        "mode, coach idiot-proof baby steps: first tell them to open Share Food, "
        "then one tiny on-page action at a time — never navigate_ui.\n"
        "\n"
        "Expiration: ask when the food is good until (best-by / use-by), NOT "
        "only when it was made. Accept ANY future date they type — relative "
        "('in two months', 'next week'), calendar ('Aug 30', 'end of "
        "September'), or weekday ('Friday'). Chips are shortcuts only. "
        "REJECT dates that are already in the past and ask for a today-or-"
        "later date. If they say 'made today/yesterday', convert to a "
        "remaining good-until date (made today → tomorrow). Never pass "
        "expiration_date=today (midnight fails as already past). Map to an "
        "ISO date of today or later. Never silently invent one.\n"
        "\n"
        "Description: ALWAYS ask for one short sentence about the food "
        "(condition, packaging, what's included). Do NOT invent it. "
        "Pass their words as `description` on post_food_listing. "
        "Ask after expiry, before the photo. One question per turn keeps "
        "suggestion chips aligned with what you asked.\n"
        "\n"
        "Food title: accept ANY dish or item they name (leftover lasagna, "
        "biryani, canned chickpeas, 100 boxes of vegetables). Do not "
        "restrict them to Bread/Fruit/Vegetables chips.\n"
        "\n"
        "Address: default to the donor's profile address; confirm in "
        "the summary sentence rather than in a separate question. Only "
        "ask if the profile has none.\n"
        "\n"
        "Handoff: assume pickup at the donor's address by default. Only "
        "ask about drop-off / delivery if the donor mentions it.\n"
        "\n"
        "Photo (donations / post_food_listing only): REQUIRED — non-negotiable. "
        "Ask with a firm attach request, e.g. 'Please attach a photo of the "
        "food — required before I can post.' Do NOT call post_food_listing "
        "until an 'image: <url>' is in chat. "
        "NEVER say or imply the photo is optional. Banned phrasing includes: "
        "'want to snap a photo?', 'or skip the photo(s)', 'can I / we post "
        "without a photo', 'photo is optional', 'if you don't have a photo', "
        "'post without a picture', 'no photo needed'. If they ask to skip or "
        "post without a photo, refuse briefly and re-ask for an upload — do "
        "not bargain. "
        "If a photo URL is already present in earlier turns of this share, "
        "include it in images[] and skip re-asking. NEVER ask for or attach "
        "a photo on post_food_request — food requests are text-only.\n"
        "\n"
        "Ambiguous 'yes' means whatever you just asked, NOT permission "
        "to post. Only call post_food_listing after an explicit "
        "go-ahead to a full summary sentence ('3 loaves of sourdough "
        "under [community], good until Fri, pickup at your place — "
        "ready to post?').\n"
        "\n"
        "Language of the listing data (title, description, unit, "
        "allergens, dietary_tags) is ALWAYS English, even if the "
        "conversation is Spanish. Translate silently. Keep chatting "
        "with the donor in their language.\n"
        "\n"
        "## Editing / removing existing listings\n"
        "'Show my listings' → get_user_listings. 'Update qty/expiry/"
        "community/address/title' → update_food_listing with structured "
        "fields (never stuff metadata into description). 'Mark as gone' "
        "→ deactivate_listing. 'Delete' → delete_listing ONLY after an "
        "explicit yes. 'Delete the bulk listings' / 'delete them all' / "
        "'delete everything I just posted' → delete_listing with "
        "delete_all=true (do NOT invent numeric ids — never pass 146, "
        "154, etc.; use UUIDs, list numbers 1–N from get_user_listings, "
        "or delete_all). 'Delete duplicates' → delete_duplicates=true. "
        "'And this too' / 'same for #2' after a successful "
        "write → re-run the SAME tool with the new listing_id, applying "
        "the same fields. Confirm what changed in one sentence.\n"
        "\n"
        "'Update <food> add a photo' / 'add a new photo to my <food>' → "
        "this is an attach_photos_to_listing call, NOT update_food_listing. "
        "Resolve the listing_id from the donor's own listings (title match "
        "on the food they named, e.g. 'oranges' → the Fresh Oranges row). "
        "If no photo URL is in chat yet, ask them to upload one first — "
        "don't call any tool. If the URL is already in chat (an "
        "'image: /uploads/…' line or a recent upload), call "
        "attach_photos_to_listing with that URL in images[].\n"
        "\n"
        "## World model — foods have real-world units\n"
        "Not every food is countable one-by-one. Match the question to "
        "how the item is actually shared:\n"
        "  • bulk dry (rice, beans, flour, sugar, oats, pasta, lentils) → "
        "bags, cans, or lbs. NEVER 'how many beans' — ask 'a bag, a few "
        "pounds, or a couple of cans?';\n"
        "  • canned goods (canned beans, tuna, corn) → cans or a case;\n"
        "  • baked (bread, muffins, cookies) → loaves, pieces, or a tray;\n"
        "  • prepared meals (soup, stew, casserole) → servings, trays, "
        "or containers;\n"
        "  • dairy (milk, yogurt, cheese) → cartons, gallons, cups — not "
        "'how many milks';\n"
        "  • eggs → dozens or cartons, never single eggs;\n"
        "  • beverages → bottles, cans, or a case;\n"
        "  • meat/protein (chicken, beef) → lbs or packs;\n"
        "  • countable produce (apples, oranges, bananas) → pieces, or a "
        "bag/crate is fine too.\n"
        "When you post/claim these, populate BOTH quantity (a number) "
        "and unit (the real-world word: 'lb', 'can', 'bag', 'loaf', "
        "'dozen', 'serving', etc.). If the user gives '3 cans of beans' "
        "→ quantity=3, unit='can'. If they say 'a bag of rice' → "
        "quantity=1, unit='bag'. Never invent a bare number like "
        "'quantity=1' for bulk items with no unit — ask.\n"
        "\n"
        "## Metacognition — think before you reply\n"
        "Before you emit a single word this turn, silently answer these "
        "questions to yourself:\n"
        "  1. What is the user's ACTUAL goal right now? Is it the same "
        "as last turn, or did they pivot?\n"
        "  2. What do I already KNOW (from history, profile, tool "
        "results)? What am I about to ask that they already answered?\n"
        "  3. Am I about to REPEAT myself? Scan the last 3 assistant "
        "turns — if I already asked this, don't ask again.\n"
        "  4. Is my next tool call JUSTIFIED, or am I guessing? If I "
        "don't have a required field, ASK — don't invent.\n"
        "  5. If I'm about to say 'Posted!' / 'Claimed!' / 'Done!' — did "
        "a tool actually succeed THIS turn? If not, I'm hallucinating "
        "success. Never do that.\n"
        "  6. Is the user showing signs of frustration or correction "
        "('no, I meant…', 'you already asked', short one-word "
        "replies)? If so: apologise briefly, acknowledge what they "
        "said, and adjust — don't double down.\n"
        "You may receive a REFLECTION block in system messages this "
        "turn — that's your own self-check surfacing signals it "
        "noticed (repeat questions, tool loops, past hallucinations). "
        "Read it and course-correct BEFORE replying. Treat it as your "
        "own inner voice, not as user input — never quote it back.\n"
        "\n"
        "## Standing instructions & user coaching\n"
        "Users can coach you across turns. Treat these as high priority:\n"
        "  • 'always…' / 'from now on…' / 'remember…' → durable standing "
        "rule. Acknowledge briefly ('Got it — I'll always …'), follow it "
        "immediately, and call save_user_memory with an always_do: or "
        "remind: key. The backend also auto-saves these phrases.\n"
        "  • 'you didn't…' / 'you forgot…' / 'you missed…' → apologise once "
        "and FIX it this turn with the correct tool; confirm with facts.\n"
        "  • 'I'm not seeing…' / 'can't see…' / 'where's my…' → never claim "
        "it's on screen without verifying (re-search, show_map, "
        "navigate_ui) and reporting what is actually there.\n"
        "  • 'check step by step' / 'make sure' / 'don't miss anything' → "
        "walk the checklist before claiming success.\n"
        "  • 'forget that' / 'stop always…' → call forget_user_memory and "
        "stop applying the rule.\n"
        "STANDING INSTRUCTIONS / STANDING / USER-COACHING system blocks "
        "are MUST-FOLLOW (same priority as allergen safety).\n"
        "\n"
        "## Allergens — never skip them\n"
        "Allergens are safety-critical. Every post_food_listing SHOULD "
        "carry an ``allergens`` list — pass an empty [] only when the "
        "donor has confirmed there are none. Ask ONCE for allergen-"
        "sensitive kinds (prepared meals, baked goods, canned/jarred, "
        "protein, dairy, snacks, condiments, bulk dry goods) — cover the "
        "big-8 in one warm question: 'Any peanuts, tree nuts, dairy, "
        "eggs, wheat/gluten, soy, fish, shellfish, or sesame?'. If the "
        "donor volunteers 'it has peanuts and dairy', put those directly "
        "in allergens and skip the question. When the donor says 'vegan' "
        "or 'gluten-free', route those to ``dietary_tags`` and drop the "
        "matching allergens from any negative claim. For search_food_"
        "near_user / post_food_request, pass the recipient's constraints "
        "as ``exclude_allergens`` and ``dietary_tags`` — read them from "
        "the profile AND the current message ('I'm allergic to nuts', "
        "'no dairy please'). NEVER silently drop a stated allergy.\n"
        "\n"
        "## Bulk uploads (CSV / pasted table / PDF)\n"
        "One warm ack ('Got the spreadsheet, importing now.'), then call "
        "bulk_import_listings with the csv_text and default_address if "
        "the donor has a profile address. If the tool returns needs="
        "['address'], ask ONE question for the whole batch, don't row-"
        "by-row. If success, report posted/total; if some rows had per-"
        "row errors, mention the first one and offer to fix.\n"
        "\n"
        "## Handling corrections / typos / mid-flow pivots\n"
        "Change only what the user corrected — keep the other captured "
        "fields intact. Never scold ('you already told me that'). Warm "
        "ack ('Got it — switching to 5 loaves.') then continue from "
        "where you were. Obvious food typos (appels→apples) can be "
        "inferred silently; anything that would change a post or claim "
        "(qty, food, community, address) needs ONE warm confirmation "
        "before acting. If the user pivots to a new food mid-flow, "
        "disambiguate once ('want that as a second listing after we "
        "finish the apples, or replace the apples?'). If they go off-"
        "topic, acknowledge briefly and steer back to the open task; "
        "if they insist, park the current task cleanly.\n"
        "\n"
        "## Multi-item share (2+ foods)\n"
        "When the donor names TWO OR MORE distinct foods to share "
        "('bread and apples', '3 loaves and a bag of oranges', 'also "
        "some eggs'), keep a draft queue — do NOT collapse them into "
        "one listing. Shared fields (community, address) are asked "
        "ONCE. Per-item fields (qty if missing, expiry, photo) are "
        "filled one question at a time. Each photo upload (`image: "
        "<url>`) binds to the next draft still missing a photo, or to "
        "the food they named ('photo for the apples'). Never reuse "
        "draft A's photo on draft B. When every draft is ready, give "
        "ONE short summary and ask 'Ready to post these?' — a single "
        "yes is enough; then call post_food_listings immediately. "
        "Do NOT re-ask community, expiry, photo, or confirmation after "
        "they already answered. If they give full details + photos in "
        "one shot, still do that one summary confirm, then post. For a "
        "single food, keep using post_food_listing.\n"
        "\n"
        "## Multi-item claim (2+ listings)\n"
        "When the recipient picks TWO OR MORE listings ('#1 and #3', "
        "'1 and 2', 'both', '2 oranges and 3 bread', 'the apples and "
        "the bananas'), keep a claim draft queue — do NOT claim only "
        "the first. Resolve each against the last search results. Ask "
        "missing quantities ONE question per turn ('How many of the "
        "oranges?'). When every draft has listing_id + qty, give ONE "
        "short summary and ask 'Ready to claim these?' — after they "
        "say yes, call claim_listings with items[]. If they already "
        "gave indices/titles + quantities AND said claim/yes, call "
        "claim_listings. When showing search results, briefly mention "
        "they can claim several at once (tap #1 & #2, or say both). "
        "For a single listing, keep using claim_listing.\n"
        "\n"
        "## Non-food / off-scope requests\n"
        "DoGoods is FOOD only. Old couches, cash, gift cards, cars, "
        "trivia, medical/legal advice → decline warmly in one line, "
        "point to the right venue if there is one, and steer back to "
        "food ('want help finding food or sharing some?'). Never "
        "lecture. Borderline items (pet food, baby formula, spices, "
        "bottled water) → treat as food and proceed. Clearly unsafe "
        "food (raw meat held unsafely, expired infant formula, "
        "unrefrigerated dairy >2h) → decline with a brief safety "
        "reason.\n"
        "\n"
        "## Role permissions (enforced by tool guards too)\n"
        "  • recipient / member wanting to donate → decline in one "
        "line ('this is a recipient account — sign in as a donor to "
        "share food').\n"
        "  • donor account wanting to claim → decline in one line "
        "('donor accounts can't claim — sign in as a recipient').\n"
        "\n"
        "## Small talk / lost users / help requests\n"
        "If the user says 'help', 'idk', 'what do I do', or a vague "
        "greeting with no goal, offer three concrete options — find "
        "free food, share food, check my pickups/claims — and ask "
        "'which one sounds like you?'. Don't dump a feature list. If "
        "the user is clearly in distress, skip the menu and search "
        "food immediately.\n"
        "\n"
        "## Assistance mode — ask first on find / share / request (default)\n"
        "When someone starts FINDING food, SHARING food, or REQUESTING food "
        "(and they are NOT in food-insecurity distress), ask ONCE before tools:\n"
        "  1) Open the form / Open Find Food / Open Request Food — ONLY "
        "navigate_ui to that page, then stop. Brief 'opened …' confirm. "
        "Do NOT ask what they want to share/find/request. Do NOT start guided "
        "intake. Never use Share's 'Open the form' label for Find Food.\n"
        "  2) Do it for me — you handle the whole flow in chat "
        "(search/claim, ask-and-post donation, or post_food_request).\n"
        "  3) Guide me step by step — idiot-proof coaching. FIRST tell them "
        "to open the right page (Share Food / Find Food / Request Food) "
        "themselves; do NOT call navigate_ui. Then ONE baby-step at a time: "
        "tiny words, where to look, what to tap/type. Wait for 'done' before "
        "the next step. Form voice on the page still helps if they opened it.\n"
        "The UI shows three chips matching the goal: Share → Open the form; "
        "Request → Open Request Food; Find → Open Find Food; "
        "plus Do it for me / Guide me step by step. Never say Open the form for Find.\n"
        "Skip this ask when: they already chose a mode this session, "
        "said 'do it for me' / 'guide me' / 'open the form' / 'open find food', "
        "named concrete qty+food to "
        "post, or are mid-claim with listings already shown. Distress "
        "('hungry', 'nothing to eat') → skip and search immediately "
        "(do not push a food request unless they ask).\n"
        "\n"
        "## Recipient AI helpers (open via navigate_ui, ONE per turn)\n"
        "  • meal-suggestions — recipes from claimed / expiring food.\n"
        "  • spoilage-alerts — what's about to go bad.\n"
        "  • storage-coach — how to store food X.\n"
        "  • smart-notifications — tune alerts.\n"
        "  • pickup-reminders — pickup reminder settings.\n"
        "  • sms-consent — enable SMS.\n"
        "After opening, one short line only ('Pulling up recipes for "
        "your expiring items.'). Let the modal do the talking.\n"
        "\n"
        "## Tone (non-negotiable)\n"
        "Warm, brief, neighborly. Contractions. Vary phrasing turn to "
        "turn. Never corporate ('please provide', 'kindly specify', "
        "'in order to proceed'). Never robotic ('I understand your "
        "request'). Never announce process ('let me now ask you the "
        "next question'). Just talk."
    )


def _build_system_prompt(training_data: dict, conversation_tone: str = "warm") -> str:
    from backend.ai.tone import DEFAULT_TONE, normalize_tone
    tone_id = normalize_tone(conversation_tone)
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
        if tone_id == DEFAULT_TONE:
            sections.append(f"## Communication Style\n{training_data['tone_guidelines']}")
        else:
            sections.append(
                "## Communication Style\n"
                "The user selected a specific conversation tone (see the per-turn "
                "TONE instruction below). Do NOT apply the default warm neighbor "
                "voice from generic guidelines — follow the active TONE block."
            )

    if "spanish_guidelines" in training_data:
        sections.append(f"## Spanish Response Guidelines\n{training_data['spanish_guidelines']}")

    if "food_insecurity_guidelines" in training_data:
        sections.append(
            f"## Food Insecurity & Distress\n{training_data['food_insecurity_guidelines']}"
        )

    if "correction_guidelines" in training_data:
        sections.append(
            f"## User Corrections\n{training_data['correction_guidelines']}"
        )

    base = training_data.get(
        "system_base",
        "You are Nouri, the DoGoods AI assistant — a warm and helpful community food-sharing guide for the DoGoods platform. Always refer to the product as DoGoods and yourself as Nouri.",
    )
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Hard rule: when the user asks the assistant to *do* something, the
    # assistant must call the matching tool instead of describing how the
    # user could do it themselves. Several user reports traced back to the
    # model replying with instructions ("go to the listing and tap Claim")
    # instead of calling claim_listing / post_food_listing / cancel_claim.
    action_policy = _build_action_policy()
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
    "member": (
        "The user is a community member (may claim or share). When they express "
        "hunger, food insecurity, or distress ('nothing to eat', single parent, "
        "large family, can't walk, pregnant, allergies, vegan), treat it as "
        "urgent: acknowledge warmly, search_food_near_user immediately, respect "
        "stated + profile dietary needs, and guide them to claim — never judge."
    ),
    "recipient": (
        "The user is a RECIPIENT. Proactively suggest food items they can claim — "
        "use search_food_near_user and get_user_dashboard. Respect their allergies "
        "and dietary_restrictions. When they express hunger, desperation, or "
        "hardship (single parent, large household, homebound, pregnant), respond "
        "with warmth first and search immediately — do not make them prove need. "
        "Nudge them to set reminders for pickup windows.\n"
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
    "member": (
        "El usuario es miembro de la comunidad. Si expresa hambre, necesidad o "
        "angustia ('no tengo comida', madre soltera, familia numerosa, no puede "
        "caminar, embarazada, alergias, vegano), trátalo como urgente: "
        "reconócelo con calidez, usa search_food_near_user de inmediato y "
        "guíalo a reclamar — sin juzgar."
    ),
    "recipient": (
        "El usuario es RECIPIENTE. Sugiere alimentos que pueda reclamar (usa "
        "search_food_near_user y get_user_dashboard). Respeta alergias y "
        "restricciones dietéticas. Si expresa hambre, desesperación o "
        "dificultad (madre/padre soltero, familia grande, no puede salir, "
        "embarazada), responde con calidez y busca de inmediato — no le pidas "
        "que demuestre necesidad. Recuérdale configurar alertas de recogida.\n"
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
    body = mapping.get(key)
    if not body:
        return None
    # Hard lock so prior turns (from when the user had a different role)
    # cannot override the live community_role from the database.
    if lang == "es":
        lock = (
            f"ROL BLOQUEADO ESTE TURNO: community_role=\"{key}\". "
            "Esto es la fuente de verdad — ignora cualquier turno anterior "
            "donde el usuario actuara con otro rol (donante vs receptor). "
            "No ofrezcas acciones prohibidas para este rol."
        )
    else:
        lock = (
            f"ROLE LOCK THIS TURN: community_role=\"{key}\". "
            "This is authoritative — IGNORE any earlier turns where the "
            "user acted under a different role (donor vs recipient). "
            "Do NOT offer actions that are forbidden for this role."
        )
    return f"{lock}\n\n{body}"


async def _profile_gap_prompt(user_id: str, lang: str = "en") -> Optional[str]:
    """Inject a nudge telling the model about missing profile fields."""
    try:
        from backend.ai.tools import _get_profile_gaps  # type: ignore
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


def _scope_safe_query(fn_args: dict, auth_user_id) -> dict:
    """Ensure run_safe_query is always scoped to the authenticated user.

    If the caller (an LLM) does not already include a filter binding the
    query to its own user_id via one of the accepted columns, we inject
    an ``eq`` filter so the result cannot span other accounts. Centers are
    public directory data and are left unchanged.
    """
    if not isinstance(fn_args, dict):
        return {"entity": "centers"}
    entity = str(fn_args.get("entity") or "").lower()
    accepted_cols = _SAFE_QUERY_USER_SCOPE.get(entity)
    if not accepted_cols:
        # Centers (or unknown entity — handler will reject) — no scoping.
        return fn_args

    auth_key = str(auth_user_id).strip()
    auth_cmp = auth_key.lower()
    use_int = auth_key.isdigit()

    filters = fn_args.get("filters") or []
    if not isinstance(filters, list):
        filters = []

    def _binds_to_auth(f: dict) -> bool:
        if not isinstance(f, dict):
            return False
        field = str(f.get("field", ""))
        op = str(f.get("op", "eq")).lower()
        val = f.get("value")
        if field not in accepted_cols or op != "eq":
            return False
        if use_int:
            try:
                return int(str(val)) == int(auth_user_id)
            except (TypeError, ValueError):
                return False
        return str(val).strip().lower() == auth_cmp

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
            "value": int(auth_user_id) if use_int else auth_key,
        })

    new_args = dict(fn_args)
    new_args["filters"] = cleaned
    return new_args


# ---------------------------------------------------------------------------
# Agentic constants
# ---------------------------------------------------------------------------

# Tools that write irreversible state on behalf of the user. Before executing
# any of these the engine intercepts the call, stores a pending envelope, and
# returns a confirmation request to the frontend.
_CONFIRM_TOOLS: frozenset[str] = frozenset({
    "cancel_claim",
    # post_food_listing / post_food_listings are confirmed in-chat via
    # "Ready to post?" (conversation_flow). Re-gating them here forced
    # donors to say yes multiple times for the same share.
    "post_food_request",
    "bulk_import_listings",
    "delete_listing",
})


def _is_confirmation_reply(message: str) -> bool:
    """True when the user is confirming a pending destructive action."""
    t = (message or "").strip().lower()
    if not t:
        return False
    if _is_cancellation_reply(message):
        return False
    confirm_keys = (
        "yes, confirm", "yes confirm", "yes, post", "yes post",
        "post it", "go ahead", "confirm and post", "publish it",
        "yes, delete", "yes delete", "delete it", "confirm delete",
        "do it", "sí, confirmar", "sí confirmar", "si confirmar",
        "sí, publícalo", "si publicalo", "publícalo", "publicalo",
        "sí, eliminar", "si eliminar", "elimínalo", "eliminalo",
    )
    if any(k in t for k in confirm_keys):
        return True
    if _is_correction_reply(message):
        return False
    return t in {"yes", "y", "ok", "okay", "sure", "si", "sí", "yeah", "yep"}


def _is_cancellation_reply(message: str) -> bool:
    """True when the user is aborting a pending destructive action."""
    t = (message or "").strip().lower()
    if not t:
        return False
    if t in {"no", "n", "cancel", "cancelar", "abort", "abortar", "stop"}:
        return True
    cancel_keys = (
        "never mind", "don't", "do not", "no thanks", "forget it",
        "no lo hagas", "olvidalo", "olvídalo",
    )
    return any(k in t for k in cancel_keys)


def _is_correction_reply(message: str) -> bool:
    """True when the user is fixing a mistake or changing a prior answer."""
    t = (message or "").strip().lower()
    if not t:
        return False
    if _is_cancellation_reply(message):
        return False
    correction_keys = (
        "actually", "wait", "hold on", "stop", "hang on",
        "i meant", "my mistake", "sorry", "wrong", "not that",
        "change it to", "change to", "make it ", "switch to",
        "instead of", "rather ", "correct that", "fix that",
        "typo", "mistyped", "edit it", "edit that", "update it",
        "different one", "the other one", "other listing", "wrong one",
        "wrong number", "not the", "i said ", "should be ",
        "espera", "en realidad", "quise decir", "me equivoqué", "me equivoque",
        "cambiar a", "cambialo", "cámbialo", "corrige", "corregir",
        "no eso", "el otro", "la otra", "edítalo", "editarlo", "modificar",
        "error mío", "error mio", "fue un error",
    )
    if any(k in t for k in correction_keys):
        return True
    # "5 not 3" / "not 3 but 5" quantity fixes
    if " not " in t and any(c.isdigit() for c in t):
        return True
    return False


def _is_food_insecurity_distress(message: str) -> bool:
    """True when the user expresses hunger, hardship, or urgent food need."""
    t = (message or "").strip().lower()
    if not t:
        return False
    triggers = (
        "hungry", "hunger", "starving", "starve", "nothing to eat", "no food",
        "dont have food", "don't have food", "dont have what to eat",
        "don't have what to eat", "going to sleep hungry", "sleep hungry",
        "need something to eat", "need food", "need to eat", "desperate",
        "desparate", "needy", "single mother", "single mom", "single mum",
        "single father", "single dad", "cant walk", "can't walk", "cannot walk",
        "stuck at home", "been in the house", "homebound", "family of",
        "feed my", "feed us", "feed the kids", "feed my kids", "feed my children",
        "pregnant", "pregnat", "i am vegan", "i'm vegan", "im vegan", "i am vegetarian",
        "allergic to", "allergin", "allergen", "dont take", "don't take",
        "simple to prep", "easy to prep", "easy to prepare", "simple to prepare",
        "nothing left", "broke", "no money for food",
        "hambre", "tengo hambre", "no tengo comida", "sin comida",
        "madre soltera", "padre soltero", "desesperad", "familia de",
        "embarazad", "vegano", "vegana", "alérgic", "alergic",
        "nada para comer", "comida para mis",
    )
    if any(k in t for k in triggers):
        return True
    if any(k in t for k in ("daughter", "son", "children", "kids", "hijos", "hija", "hijo")):
        if any(k in t for k in ("hungry", "hambre", "eat", "comer", "food", "comida", "feed", "sleep")):
            return True
    return False


def _needs_foolproof_guidance(message: str) -> bool:
    """True when the user likely needs step-by-step menu-style help."""
    if _is_food_insecurity_distress(message):
        return False
    t = (message or "").strip().lower()
    if not t or len(t) > 180:
        return False
    triggers = (
        "help", "idk", "i don't know", "dont know", "not sure", "what do i do",
        "how do i", "how does this work", "what can you do", "what should i do",
        "i'm lost", "im lost", "confused", "no idea", "where do i start",
        "walk me through", "guide me", "show me how",
        "ayuda", "no sé", "no se", "qué hago", "que hago", "cómo funciona",
        "como funciona", "qué puedo hacer", "que puedo hacer", "no estoy seguro",
    )
    if any(k in t for k in triggers):
        return True
    return t in {"hi", "hello", "hey", "?", "hola", "help me"}


def _build_confirmation_summary(tool_name: str, args: dict) -> str:
    """Return a short human-readable description of what the intercepted tool would do."""
    if tool_name == "claim_listing":
        title = args.get("title") or "this food"
        qty = args.get("quantity") or args.get("quantity_requested") or 1
        return f"claim {qty} of {title}"
    if tool_name == "claim_listings":
        items = args.get("items") if isinstance(args.get("items"), list) else []
        titles = [
            str(i.get("title") or i.get("listing_id") or "item")
            for i in items
            if isinstance(i, dict)
        ][:5]
        if titles:
            return f"claim {len(items)} listings ({', '.join(titles)})"
        return f"claim {max(len(items), 2)} listings"
    if tool_name == "cancel_claim":
        title = args.get("title") or "your claim"
        return f"release your claim on {title}"
    if tool_name == "post_food_listing":
        title = args.get("title", "this item")
        qty = args.get("quantity", "") or args.get("qty", "")
        unit = args.get("unit", "")
        addr = args.get("address", "your saved address")
        parts = [p for p in (str(qty), unit, "of", title, "for pickup at", addr) if p and p != "of"]
        return "share " + " ".join(parts)
    if tool_name == "post_food_listings":
        items = args.get("items") if isinstance(args.get("items"), list) else []
        titles = [
            str(i.get("title") or "item")
            for i in items
            if isinstance(i, dict)
        ][:5]
        if titles:
            return f"share {len(items)} listings ({', '.join(titles)})"
        return f"share {max(len(items), 2)} listings"
    if tool_name == "post_food_request":
        title = args.get("title", "food")
        return f"post a food request for {title}"
    if tool_name == "bulk_import_listings":
        raw = args.get("listings") or args.get("csv_data", "")
        count = max(len(str(raw).strip().splitlines()) - 1, 1)
        return f"import {count} listing(s) from your spreadsheet"
    if tool_name == "delete_listing":
        title = args.get("title") or args.get("title_lookup") or "this listing"
        bulk = args.get("listing_ids") or []
        dup_count = args.get("_bulk_delete_count") or len(bulk)
        if args.get("delete_all"):
            scope = args.get("_delete_scope") or "listings"
            n = dup_count or len(bulk)
            if scope == "last_bulk" and n:
                return f"permanently delete your last bulk batch ({n} listings)"
            if n:
                return f"permanently delete all {n} of your active listings"
            return "permanently delete all of your active listings"
        if args.get("delete_duplicates") and dup_count:
            return f"delete {dup_count} duplicate listing(s) (keep one copy of each title)"
        if bulk and len(bulk) > 1:
            return f"permanently delete {len(bulk)} listings"
        return f"permanently delete '{title}'"
    return f"complete this action"


# ---------------------------------------------------------------------------
# Conversation Engine
# ---------------------------------------------------------------------------

class ConversationEngine:
    """MySQL-backed agentic conversation engine."""

    def __init__(self) -> None:
        self.training_data = _load_training_data()
        from backend.ai.tools import TOOL_DEFINITIONS, execute_tool
        self.tool_definitions = TOOL_DEFINITIONS
        self._execute_tool = execute_tool
        self._tools_taking_user_id: frozenset[str] = frozenset(
            t["function"]["name"]
            for t in self.tool_definitions
            if isinstance(t, dict)
            and isinstance(t.get("function"), dict)
            and "user_id" in (
                (t["function"].get("parameters") or {}).get("properties") or {}
            )
        )
        # Pending confirmation envelopes keyed by user_id (int).
        # Format: {tool, args, expires_at (ISO str), auth_user_id, lang, summary}
        # Single-process only — use Redis for multi-worker deployments.
        self._pending_confirmations: dict = {}

    @property
    def system_prompt(self) -> str:
        return _build_system_prompt(self.training_data)

    # ---- Pending confirmation helpers ------------------------------------

    def get_pending_confirmation(self, user_id: str) -> Optional[dict]:
        """Return the pending confirmation envelope for this user, or None."""
        return self._pending_confirmations.get(user_id)

    def cancel_pending_confirmation(self, user_id: str) -> None:
        """Remove the pending confirmation envelope for this user."""
        self._pending_confirmations.pop(user_id, None)

    async def _enrich_confirmed_tool_args(
        self, tool_name: str, tool_args: dict, user_id: str,
        user_message: str = "", history: list | None = None,
    ) -> dict:
        """Fill in missing required fields before executing a confirmed write."""
        args = dict(tool_args or {})
        if tool_name == "post_food_listing":
            from backend.ai.conversation_flow import enrich_post_food_listing_args
            args = enrich_post_food_listing_args(args, user_message, history)
            from backend.ai.conversation_flow import _extract_expiry_from_text, _history_blob
            if not args.get("expiration_date") and not args.get("expiry_date"):
                exp = _extract_expiry_from_text(user_message) or _extract_expiry_from_text(
                    _history_blob(history, user_message, limit=12),
                )
                if exp:
                    args["expiration_date"] = exp
            from backend.ai_engine import fetch_donor_listing_defaults, _is_placeholder_address
            if not args.get("address") or _is_placeholder_address(args.get("address")):
                donor = await fetch_donor_listing_defaults(str(user_id))
                if donor.get("address"):
                    args["address"] = donor["address"]
                else:
                    args.pop("address", None)
        if tool_name == "post_food_listings":
            from backend.ai.conversation_flow import enrich_post_food_listings_args
            args = enrich_post_food_listings_args(
                args, user_message, history, str(user_id),
            )
            from backend.ai_engine import fetch_donor_listing_defaults, _is_placeholder_address
            if not args.get("address") or _is_placeholder_address(args.get("address")):
                donor = await fetch_donor_listing_defaults(str(user_id))
                if donor.get("address"):
                    args["address"] = donor["address"]
                else:
                    args.pop("address", None)
        if tool_name == "claim_listing":
            from backend.ai.conversation_flow import enrich_claim_listing_args
            args = enrich_claim_listing_args(
                args, user_message, history, str(user_id),
            )
            for key in (
                "_resolve_error",
                "_resolved_from_index",
                "_resolved_from_history",
                "_resolved_from_title",
                "_no_matching_listing_food",
            ):
                args.pop(key, None)
        if tool_name == "claim_listings":
            from backend.ai.conversation_flow import enrich_claim_listings_args
            args = enrich_claim_listings_args(
                args, user_message, history, str(user_id),
            )
        if tool_name == "delete_listing":
            from backend.ai.conversation_flow import enrich_donor_listing_tool_args
            args = enrich_donor_listing_tool_args(
                tool_name, args, user_message, history, str(user_id),
            )
            args.pop("_resolve_error", None)
            args["confirmed"] = True
        return args

    async def _agentic_reply_from_context(
        self,
        *,
        lang: str,
        tone: str,
        user_message: str,
        situation: str,
        facts: dict,
    ) -> str:
        """Generate a fresh, contextual reply from tool/facts — no static templates."""
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY not configured")

        from backend.ai.tone import normalize_tone, tone_system_prompt, tone_temperature

        active_tone = normalize_tone(tone)
        system = (
            f"{tone_system_prompt(active_tone, lang=lang)}\n\n"
            "Write ONE short assistant reply (2–3 sentences max) using ONLY the "
            "facts provided. Plain language. No UUIDs, database ids, or internal "
            "tool names. Do not invent outcomes that are not in the facts."
        )
        payload = {
            "model": FOLLOWUP_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": (
                        f"User message: {user_message}\n\n"
                        f"Situation: {situation}\n\n"
                        f"Facts (JSON):\n{json.dumps(facts, default=str)}"
                    ),
                },
            ],
            "temperature": tone_temperature(active_tone),
            "max_tokens": 220,
        }
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }
        resp = await _openai_with_retry(
            "POST",
            f"{OPENAI_BASE_URL}/chat/completions",
            headers=headers,
            json_payload=payload,
        )
        data = resp.json()
        text = (data["choices"][0]["message"].get("content") or "").strip()
        if not text:
            raise RuntimeError("Empty agentic summary from model")
        return polish_assistant_response(text, lang=lang)

    async def _execute_pending_confirmation(
        self,
        user_id: str,
        pending: dict,
        user_message: str,
        lang: str,
        include_audio: bool = False,
        tone: str = "warm",
    ) -> dict:
        """Run a stored pending tool call after the user confirmed in chat."""
        tool_name = pending["tool"]
        history = await self.get_conversation_history(user_id, limit=12)
        tool_args = await self._enrich_confirmed_tool_args(
            pending["tool"], dict(pending["args"] or {}), user_id,
            user_message=user_message, history=history,
        )
        tool_args.setdefault("user_id", str(user_id))
        self.cancel_pending_confirmation(user_id)

        try:
            result = await self._execute_tool(tool_name, tool_args)
        except Exception as exc:
            logger.exception("Confirmed tool %s failed", tool_name)
            result = {"error": str(exc)}

        ok = tool_result_ok(result) if isinstance(result, dict) else False
        summary = pending.get("summary", "action")

        facts = {
            "tool": tool_name,
            "ok": ok,
            "action_summary": summary,
        }
        if isinstance(result, dict):
            for key in (
                "title", "address", "quantity", "unit", "summary", "message",
                "error", "pickup_location", "pickup_deadline", "listing_id",
                "deleted_count", "deleted", "titles", "delete_duplicates",
            ):
                if result.get(key) is not None:
                    facts[key] = result[key]

        situation = (
            "The user confirmed a pending action. Report the real outcome from facts."
            if ok
            else "The user confirmed a pending action but it failed. Explain the error plainly."
        )
        response_text = await self._agentic_reply_from_context(
            lang=lang,
            tone=tone,
            user_message=user_message,
            situation=situation,
            facts=facts,
        )

        action_entry: dict = {"tool": tool_name, "ok": ok, "summary": summary}
        if isinstance(result, dict):
            action_entry = enrich_tool_action(tool_name, result, action_entry)
            for extra_key in (
                "listing_id", "coords_lat", "coords_lng", "address",
                "verified", "verify_issues", "route", "action", "target", "view", "focus",
                "frontend_hint",
            ):
                if result.get(extra_key) is not None:
                    action_entry[extra_key] = result[extra_key]

        suggestions = await self._build_suggestion_chips(
            response_text,
            lang,
            user_message=user_message,
            user_id=str(user_id),
            actions=[action_entry],
            history=history,
        )
        conversation_id = await self._persist_conversation(
            user_id,
            user_message,
            response_text,
            lang,
            metadata={
                "actions": [action_entry],
                "suggestions": suggestions,
                "requires_confirmation": False,
                "pending_action": None,
            },
        )

        audio_b64 = None
        if include_audio:
            audio_b64 = await self._generate_audio_b64(response_text, lang=lang)

        return {
            "text": response_text,
            "audio_url": audio_b64,
            "user_id": str(user_id),
            "lang": lang,
            "conversation_id": str(conversation_id) if conversation_id else None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actions": [action_entry],
            "suggestions": suggestions,
            "requires_confirmation": False,
            "pending_action": None,
        }

    def _detect_lang(self, text: str) -> str:
        return "es" if detect_spanish(text) else "en"

    def _detect_lang_sticky(
        self,
        message: str,
        history: Optional[list] = None,
        profile: Optional[dict] = None,
        accessibility_profile: Optional[dict] = None,
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
            from backend.ai.accessibility_profile import preferred_language_from_profile

            a11y_lang = preferred_language_from_profile(accessibility_profile)
            if a11y_lang and a11y_lang.startswith("es"):
                return "es"
            pref = (profile or {}).get("language")
            if isinstance(pref, str) and pref.lower().startswith("es"):
                return "es"
            if a11y_lang and a11y_lang.startswith("en"):
                return "en"
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

    # ---- Profile lookup via SQLAlchemy ------------------------------------

    async def get_user_profile(self, user_id: str) -> Optional[dict]:
        """Load profile from Supabase users table (UUID auth ids)."""
        try:
            from backend.ai_engine import supabase_get
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
        role = user.get("community_role") or user.get("role")
        is_admin = bool(user.get("is_admin")) or (str(role or "").lower() == "admin")
        return {
            "id": user.get("id"),
            "name": user.get("name") or user.get("full_name"),
            "email": user.get("email"),
            "role": role,
            "community_role": user.get("community_role"),
            "organization": user.get("organization"),
            "is_admin": is_admin,
            "created_at": user.get("created_at"),
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
            "allergens": user.get("allergies") or user.get("allergens"),
            "household_size": user.get("household_size"),
            "sms_consent": (
                user.get("sms_consent")
                or user.get("sms_opt_in")
                or user.get("sms_notifications_enabled")
            ),
            "language": user.get("language"),
        }

    # ---- Conversation tone preference -------------------------------------

    async def get_conversation_tone(self, user_id: str) -> str:
        """Load the user's preferred chat tone from ai_user_preferences."""
        from backend.ai.tone import CONVERSATION_TONE_KEY, DEFAULT_TONE, normalize_tone
        from backend.app import SessionLocal
        from backend.ai.models import AIUserPreference

        def _sync() -> str:
            db = SessionLocal()
            try:
                row = (
                    db.query(AIUserPreference)
                    .filter(
                        AIUserPreference.user_id == user_id,
                        AIUserPreference.key == CONVERSATION_TONE_KEY,
                    )
                    .first()
                )
                return normalize_tone(row.value if row else DEFAULT_TONE)
            except Exception as exc:
                logger.debug("get_conversation_tone failed (non-fatal): %s", exc)
                return DEFAULT_TONE
            finally:
                db.close()

        return await asyncio.get_event_loop().run_in_executor(None, _sync)

    async def set_conversation_tone(self, user_id: str, tone: str) -> str:
        """Persist the user's chat tone preference."""
        from backend.ai.tone import CONVERSATION_TONE_KEY, normalize_tone
        from backend.app import SessionLocal
        from backend.ai.models import AIUserPreference

        normalized = normalize_tone(tone)

        def _sync() -> str:
            db = SessionLocal()
            try:
                row = (
                    db.query(AIUserPreference)
                    .filter(
                        AIUserPreference.user_id == user_id,
                        AIUserPreference.key == CONVERSATION_TONE_KEY,
                    )
                    .first()
                )
                if row:
                    row.value = normalized
                    row.confidence = "high"
                    row.last_seen_at = _utcnow()
                else:
                    db.add(AIUserPreference(
                        user_id=user_id,
                        key=CONVERSATION_TONE_KEY,
                        value=normalized,
                        confidence="high",
                        last_seen_at=_utcnow(),
                    ))
                db.commit()
                return normalized
            except Exception as exc:
                db.rollback()
                logger.error("set_conversation_tone failed: %s", exc)
                return normalized
            finally:
                db.close()

        return await asyncio.get_event_loop().run_in_executor(None, _sync)

    # ---- History via SQLAlchemy -------------------------------------------

    async def get_conversation_history(self, user_id: str, limit: int = 50) -> list[dict]:
        from backend.app import SessionLocal
        from backend.ai.models import AIConversation

        def _sync() -> list[dict]:
            db = SessionLocal()
            try:
                rows = (
                    db.query(AIConversation)
                    .filter(AIConversation.user_id == user_id)
                    .order_by(AIConversation.created_at.desc())
                    .limit(limit)
                    .all()
                )
                rows.reverse()
                def _parse_meta(raw):
                    if not raw:
                        return {}
                    if isinstance(raw, dict):
                        return raw
                    if isinstance(raw, str):
                        try:
                            parsed = json.loads(raw)
                            return parsed if isinstance(parsed, dict) else {}
                        except (TypeError, ValueError, json.JSONDecodeError):
                            return {}
                    return {}

                return [
                    {
                        "id": str(r.id) if getattr(r, "id", None) is not None else None,
                        "role": r.role,
                        "message": r.message,
                        "created_at": r.created_at.isoformat() if r.created_at else "",
                        "metadata": _parse_meta(getattr(r, "meta", None)),
                    }
                    for r in rows
                ]
            finally:
                db.close()

        return await asyncio.get_event_loop().run_in_executor(None, _sync)

    async def store_message(
        self,
        user_id: str,
        role: str,
        message: str,
        metadata: dict | None = None,
    ) -> Optional[int]:
        from backend.app import SessionLocal
        from backend.ai.models import AIConversation

        def _sync() -> Optional[int]:
            db = SessionLocal()
            try:
                row = AIConversation(
                    user_id=user_id,
                    role=role,
                    message=message,
                    meta=json.dumps(metadata) if metadata else None,
                )
                db.add(row)
                db.commit()
                db.refresh(row)
                return row.id
            except Exception as exc:
                logger.error("store_message failed: %s", exc)
                db.rollback()
                return None
            finally:
                db.close()

        return await asyncio.get_event_loop().run_in_executor(None, _sync)

    async def clear_history(self, user_id: str) -> int:
        from backend.app import SessionLocal
        from backend.ai.models import AIConversation
        from backend.ai.conversation_flow import clear_user_ai_caches

        uid = str(user_id or "").strip()
        # Always wipe in-memory caches even if DB delete fails / no rows.
        try:
            clear_user_ai_caches(uid)
        except Exception as exc:
            logger.debug("clear_user_ai_caches failed (non-fatal): %s", exc)
        try:
            self.cancel_pending_confirmation(uid)
        except Exception:
            pass

        def _sync() -> int:
            db = SessionLocal()
            try:
                n = db.query(AIConversation).filter(AIConversation.user_id == uid).delete()
                db.commit()
                return n
            except Exception as exc:
                logger.error("clear_history failed: %s", exc)
                db.rollback()
                return 0
            finally:
                db.close()

        return await asyncio.get_event_loop().run_in_executor(None, _sync)

    # ---- Agentic helpers -------------------------------------------------

    async def _plan_if_complex(self, message: str, role: str, lang: str) -> Optional[str]:
        """Generate a brief JSON execution plan for complex multi-step requests.

        Returns a ``<plan>`` block to inject into the system prompt, or ``None``
        for simple single-action queries (fast path — no extra API call).
        """
        lower = message.lower()
        action_verbs = sum(
            1 for w in (
                "post", "share", "donate", "claim", "remind", "update",
                "add", "cancel", "send", "search", "find", "create", "and",
                "publicar", "compartir", "donar", "reclamar", "recordar",
                "buscar", "agregar", "cancelar", "enviar",
            )
            if w in lower
        )
        if action_verbs < 2:
            return None

        if not OPENAI_API_KEY:
            return None

        try:
            plan_prompt = (
                f'User says: "{message}"\n'
                f"User role: {role or 'member'}\n\n"
                "Is this a complex multi-step task that requires executing 2+ distinct "
                "tool calls in sequence? If YES, list the steps as compact JSON:\n"
                '[{"step": 1, "action": "short description", "tool": "tool_name_or_null"}]\n'
                "If it is a simple single-step request, reply with: null\n"
                "Only reply with valid JSON array or null. No explanation."
            )
            payload = {
                "model": FOLLOWUP_MODEL,
                "messages": [{"role": "user", "content": plan_prompt}],
                "temperature": 0.2,
                "max_tokens": 300,
            }
            headers = {
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            }
            resp = await _openai_with_retry(
                "POST",
                f"{OPENAI_BASE_URL}/chat/completions",
                headers=headers,
                json_payload=payload,
            )
            content = resp.json()["choices"][0]["message"].get("content", "").strip()
            if content and content.lower() != "null" and content.startswith("["):
                plan_data = json.loads(content)
                if isinstance(plan_data, list) and plan_data:
                    steps = "\n".join(
                        f"  {s.get('step', i + 1)}. {s.get('action', '')}"
                        for i, s in enumerate(plan_data)
                        if isinstance(s, dict)
                    )
                    if lang == "es":
                        return (
                            "<plan>\n"
                            f"Plan de ejecución para esta solicitud:\n{steps}\n"
                            "Ejecuta los pasos en orden. Después de cada uno, decide si hay más pasos.\n"
                            "</plan>"
                        )
                    return (
                        "<plan>\n"
                        f"Execution plan for this request:\n{steps}\n"
                        "Execute steps in order. After each one, decide if there are more steps.\n"
                        "</plan>"
                    )
        except Exception as exc:
            logger.debug("Plan generation skipped: %s", exc)
        return None

    async def _load_user_memories(self, user_id: str) -> list[dict]:
        """Load learned preferences, prioritizing standing instructions."""
        from backend.app import SessionLocal
        from backend.ai.models import AIUserPreference
        from backend.ai.standing_instructions import is_standing_memory_key

        def _sync() -> list[dict]:
            db = SessionLocal()
            try:
                prefs = (
                    db.query(AIUserPreference)
                    .filter(AIUserPreference.user_id == user_id)
                    .order_by(AIUserPreference.last_seen_at.desc())
                    .limit(30)
                    .all()
                )
                rows = [{"key": p.key, "value": p.value} for p in prefs]
                standing = [r for r in rows if is_standing_memory_key(r["key"])]
                soft = [r for r in rows if not is_standing_memory_key(r["key"])]
                # Cap: all standing (up to 12) + remaining soft prefs.
                return standing[:12] + soft[:10]
            except Exception as exc:
                logger.debug("Load memories failed (non-fatal): %s", exc)
                return []
            finally:
                db.close()

        return await asyncio.get_event_loop().run_in_executor(None, _sync)

    async def _check_proactive(
        self, user_id: str, profile: Optional[dict], lang: str
    ) -> list[str]:
        """Post-turn proactive opportunity check against live Supabase listings.

        • Recipients: new approved/active listings near them in the last 2 hours
        • Donors: their live listings expiring within 48 hours
        """
        if not profile or not user_id:
            return []

        role = (profile.get("role") or profile.get("community_role") or "").lower()
        results: list[str] = []
        now = _utcnow()

        try:
            from backend.ai_engine import supabase_get

            if role in ("recipient", "member", ""):
                lat = profile.get("lat") or profile.get("latitude")
                lng = profile.get("lng") or profile.get("longitude")
                if lat is not None and lng is not None:
                    two_hours_ago = (now - timedelta(hours=2)).isoformat()
                    try:
                        rows = await supabase_get("food_listings", {
                            "status": "in.(approved,active)",
                            "created_at": f"gte.{two_hours_ago}",
                            "select": "id,latitude,longitude,user_id,community_id",
                            "limit": "25",
                        })
                    except Exception as exc:
                        logger.debug("proactive near-listings fetch failed: %s", exc)
                        rows = []
                    from backend.tools import (
                        _allowed_community_id_strings,
                        _is_admin_flag,
                        _listing_in_community_scope,
                    )
                    allowed = _allowed_community_id_strings(
                        _is_admin_flag(profile.get("is_admin")),
                        profile.get("community_id"),
                    )
                    nearby = []
                    for lx in rows or []:
                        if str(lx.get("user_id") or "") == str(user_id):
                            continue
                        if not _listing_in_community_scope(lx, allowed):
                            continue
                        try:
                            rlat = float(lx.get("latitude"))
                            rlng = float(lx.get("longitude"))
                        except (TypeError, ValueError):
                            continue
                        if abs(rlat - float(lat)) < 0.15 and abs(rlng - float(lng)) < 0.15:
                            nearby.append(lx)
                    if nearby:
                        count = len(nearby)
                        if lang == "es":
                            results.append(f"Ver los {count} anuncio(s) nuevos cerca de ti")
                        else:
                            results.append(f"View {count} new listing(s) near you")

            if role in ("donor", "admin", "organizer"):
                cutoff = (now + timedelta(hours=48)).date().isoformat()
                today = now.date().isoformat()
                try:
                    rows = await supabase_get("food_listings", {
                        "user_id": f"eq.{user_id}",
                        "status": "in.(approved,active)",
                        "expiry_date": f"lte.{cutoff}",
                        "select": "id,expiry_date,title",
                        "limit": "25",
                    })
                except Exception as exc:
                    logger.debug("proactive expiring fetch failed: %s", exc)
                    rows = []
                expiring_soon = []
                for lx in rows or []:
                    raw = lx.get("expiry_date")
                    if not raw:
                        continue
                    day = str(raw)[:10]
                    if today <= day <= cutoff:
                        expiring_soon.append(lx)
                if expiring_soon:
                    count = len(expiring_soon)
                    if lang == "es":
                        results.append(f"Tienes {count} anuncio(s) que vencen pronto")
                    else:
                        results.append(f"You have {count} listing(s) expiring soon")
        except Exception as exc:
            logger.debug("Proactive check failed (non-fatal): %s", exc)
            return []

        return results[:2]

    # ---- Main chat --------------------------------------------------------

    async def chat(
        self,
        user_id: str,
        message: str,
        include_audio: bool = False,
        tone: Optional[str] = None,
        accessibility_profile: Optional[dict] = None,
        guide_state: Optional[dict] = None,
    ) -> dict:
        profile_task = asyncio.create_task(self.get_user_profile(user_id))
        history_task = asyncio.create_task(self.get_conversation_history(user_id, limit=12))
        memories_task = asyncio.create_task(self._load_user_memories(user_id))
        tone_task = asyncio.create_task(self.get_conversation_tone(user_id))
        profile, history, memories, stored_tone = await asyncio.gather(
            profile_task, history_task, memories_task, tone_task
        )

        from backend.ai.accessibility_profile import (
            load_accessibility_profile,
            merge_accessibility_profiles,
            preferred_language_from_profile,
            save_accessibility_profile,
        )

        stored_a11y = await load_accessibility_profile(user_id)
        effective_a11y = merge_accessibility_profiles(stored_a11y, accessibility_profile)
        if accessibility_profile and effective_a11y:
            asyncio.create_task(save_accessibility_profile(user_id, effective_a11y))

        from backend.ai.tone import CONVERSATION_TONE_KEY, normalize_tone, tone_system_prompt, tone_temperature
        memories = [m for m in memories if m.get("key") != CONVERSATION_TONE_KEY]
        active_tone = normalize_tone(tone) if tone else stored_tone
        if tone and normalize_tone(tone) != stored_tone:
            active_tone = await self.set_conversation_tone(user_id, tone)
        # #region agent log
        _tone_debug_log(
            "A_B", "ai_engine.py:chat_tone_resolved",
            "tone resolved for chat turn",
            {
                "request_tone": tone,
                "stored_tone": stored_tone,
                "active_tone": active_tone,
                "user_id_prefix": str(user_id)[:8],
            },
        )
        # #endregion

        # Sticky language: use the message, then profile preference, then
        # recent history. Prevents short replies like 'sí' / 'ok' from
        # flipping a Spanish conversation back to English.
        lang = self._detect_lang_sticky(
            message,
            history=history,
            profile=profile,
            accessibility_profile=effective_a11y,
        )

        pending = self.get_pending_confirmation(user_id)
        correction_during_confirm = False
        if pending:
            try:
                expiry = datetime.fromisoformat(pending["expires_at"])
                if _utcnow() > expiry:
                    self.cancel_pending_confirmation(user_id)
                    pending = None
            except (KeyError, ValueError):
                pass

        if pending and not _is_confirmation_reply(message) and not _is_cancellation_reply(message):
            if _is_correction_reply(message):
                correction_during_confirm = True
                self.cancel_pending_confirmation(user_id)
                pending = None
            else:
                # Keep the pending action across clarifying questions
                # ("how much?", "which one?") — only cancel on explicit
                # cancel/timeout or a clear confirm/correct path.
                pass

        if pending:
            if _is_cancellation_reply(message):
                self.cancel_pending_confirmation(user_id)
                cancelled_text = await self._agentic_reply_from_context(
                    lang=lang,
                    tone=active_tone,
                    user_message=message,
                    situation="User cancelled a pending action before it ran.",
                    facts={"pending_action": pending.get("summary"), "cancelled": True},
                )
                suggestions = await self._build_suggestion_chips(
                    cancelled_text,
                    lang,
                    user_message=message,
                    user_id=str(user_id),
                    actions=[],
                    history=history,
                )
                conversation_id = await self._persist_conversation(
                    user_id,
                    message,
                    cancelled_text,
                    lang,
                    metadata={
                        "actions": [{"tool": pending.get("tool"), "ok": False, "summary": "Cancelled by user"}],
                        "suggestions": suggestions,
                        "requires_confirmation": False,
                        "pending_action": None,
                    },
                )
                return {
                    "text": cancelled_text,
                    "audio_url": None,
                    "user_id": str(user_id),
                    "lang": lang,
                    "tone": active_tone,
                    "conversation_id": str(conversation_id) if conversation_id else None,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "actions": [{"tool": pending.get("tool"), "ok": False, "summary": "Cancelled by user"}],
                    "suggestions": suggestions,
                    "requires_confirmation": False,
                    "pending_action": None,
                }
            if _is_confirmation_reply(message):
                return await self._execute_pending_confirmation(
                    user_id, pending, message, lang,
                    include_audio=include_audio, tone=active_tone,
                )
            # Clarifying question while confirmation is pending — remind
            # the model, then continue the normal turn (do not drop pending).
            summary = pending.get("summary") or pending.get("tool") or "the pending action"
            messages_pending_nudge = (
                f"PENDING CONFIRMATION still waiting: {summary}. "
                f"Answer their clarifying question briefly, then re-ask "
                f"'Say yes to confirm, or cancel to abort.' Do NOT run the "
                f"tool until they clearly confirm."
            )
        else:
            messages_pending_nudge = None

        messages: list[dict] = [
            {"role": "system", "content": _build_system_prompt(self.training_data, active_tone)}
        ]
        if messages_pending_nudge:
            messages.append({"role": "system", "content": messages_pending_nudge})

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
            role_key = str(role).lower().strip()
            facts.append(f"community_role: {role_key} (authoritative — do not infer a different role from chat history)")
            if profile.get("address"):
                facts.append(f"profile address on file: {profile['address']}")
                if role_key in ("recipient", "member", ""):
                    facts.append(
                        "FIND FOOD: use search_food_near_user with user_id — "
                        "location comes from this saved address. Do NOT ask for GPS."
                    )
                if role_key in ("donor", "admin", "organizer"):
                    facts.append(
                        "FOOLPROOF POSTING: when sharing food, default pickup to this "
                        "address — do not ask unless the donor wants a different one"
                    )
            else:
                if role_key in ("donor", "admin", "organizer"):
                    facts.append("NO profile address on file (will need one to post listings)")
                else:
                    facts.append("NO profile address on file (helpful for finding nearby food)")
            if profile.get("phone"):
                facts.append(f"phone on file: {profile['phone']}")
            else:
                if role_key == "recipient":
                    facts.append("NO phone on file (claim_listing will fail until they add one)")
                elif role_key == "donor":
                    facts.append("NO phone on file (optional for donors)")
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

        if accessibility_profile:
            from backend.agent.user_guidance import build_accessibility_profile_prompt
            a11y_block = build_accessibility_profile_prompt(effective_a11y or accessibility_profile)
            if a11y_block:
                messages.append({"role": "system", "content": a11y_block})
        elif effective_a11y:
            from backend.agent.user_guidance import build_accessibility_profile_prompt
            a11y_block = build_accessibility_profile_prompt(effective_a11y)
            if a11y_block:
                messages.append({"role": "system", "content": a11y_block})

        try:
            from backend.ai.conversation_flow import (
                build_live_guide_prompt,
                build_page_knowledge_prompt,
            )
            live_guide = build_live_guide_prompt(guide_state, lang=lang)
            if live_guide:
                messages.append({"role": "system", "content": live_guide})
            page_knowledge = build_page_knowledge_prompt(guide_state, lang=lang)
            if page_knowledge:
                messages.append({"role": "system", "content": page_knowledge})
        except Exception as exc:
            logger.debug("live guide prompt skipped: %s", exc)

        # Foolproof / Easy Mode: inject accessibility coaching when the user
        # looks confused or has easyMode on in their profile.
        try:
            easy = bool(
                (effective_a11y or {}).get("easyMode")
                if isinstance(effective_a11y, dict)
                else False
            )
            if easy or _needs_foolproof_guidance(message):
                from backend.agent.user_guidance import (
                    ACCESSIBILITY_GUIDANCE,
                    assess_user_turn,
                )
                messages.append({"role": "system", "content": ACCESSIBILITY_GUIDANCE})
                assessment = assess_user_turn(
                    message, history or [], "general", confidence=0.7,
                )
                if assessment.guidance_hint or assessment.guide_mode:
                    hint = assessment.guidance_hint or assessment.guide_mode
                    messages.append({
                        "role": "system",
                        "content": (
                            f"Turn assessment: {assessment.guide_mode or 'clarify'} "
                            f"— {hint}. Prefer a numbered menu and one question."
                        ),
                    })
        except Exception as exc:
            logger.debug("accessibility guidance inject skipped: %s", exc)

        # Conversation-awareness nudge. Kept short — the main policy in the
        # system prompt already covers this; this line is just a per-turn
        # reminder to actually read history before replying.
        messages.append({
            "role": "system",
            "content": (
                "REMINDER: read the prior turns first. Reuse facts they "
                "already gave you (title, qty, address, chosen listing #). "
                "Resolve 'it', 'that one', '#3', 'the bread' from earlier "
                "messages and tool results. On 'and this too' / 'same for "
                "#2' after a successful write, re-run the same tool with the "
                "new listing_id — never claim success in text alone. Never "
                "re-ask for profile fields already loaded (address, phone, "
                "diet, allergens)."
            ),
        })

        from backend.ai.conversation_flow import detect_conversation_flow
        flow_kind = detect_conversation_flow(message, history)

        # Role-specific behaviour (best-effort; non-fatal)
        try:
            role_prompt = _role_behavior_prompt(
                (profile or {}).get("community_role") or (profile or {}).get("role"),
                lang=lang,
            )
            if role_prompt:
                messages.append({"role": "system", "content": role_prompt})
        except Exception as exc:  # pragma: no cover
            logger.debug("role prompt build failed: %s", exc)

        # Standing instructions ("always do X") + soft learned preferences.
        # Standing keys get MUST-FOLLOW language; soft prefs stay advisory.
        try:
            from backend.ai.standing_instructions import (
                format_soft_preferences_block,
                format_standing_memories_block,
                sync_standing_instructions,
            )
            standing_block = format_standing_memories_block(memories, lang=lang)
            if standing_block:
                messages.append({"role": "system", "content": standing_block})
            soft_block = format_soft_preferences_block(memories, lang=lang)
            if soft_block:
                messages.append({"role": "system", "content": soft_block})
            # Detect this-turn coaching ("you didn't…", "I'm not seeing…",
            # "always…", "check step by step") → persist durable rules and
            # inject a MUST-FIX reminder before the model replies.
            standing_sync = await sync_standing_instructions(
                str(user_id), message, memories=memories, lang=lang,
            )
            # Newly saved standing rules also need to appear this turn.
            for item in standing_sync.get("saved") or []:
                memories.append({"key": item["key"], "value": item["value"]})
            if standing_sync.get("saved"):
                standing_block2 = format_standing_memories_block(memories, lang=lang)
                if standing_block2 and standing_block2 != standing_block:
                    messages.append({"role": "system", "content": standing_block2})
            if standing_sync.get("reminder"):
                messages.append({
                    "role": "system",
                    "content": standing_sync["reminder"],
                })
        except Exception as exc:  # pragma: no cover — advisory only
            logger.debug("standing instructions skipped: %s", exc)
            if memories:
                mem_lines = "\n".join(
                    f"  - {m['key']}: {m['value']}" for m in memories
                )
                messages.append({
                    "role": "system",
                    "content": (
                        "Learned preferences about this user "
                        "(from prior conversations):\n"
                        f"{mem_lines}\n"
                        "Apply these automatically — do NOT ask again for "
                        "things you already know."
                    ),
                })

        for msg in history:
            content = msg["message"]
            if len(content) > 800:
                content = content[:800] + "... [truncated]"
            messages.append({"role": msg["role"], "content": content})

        # Lightweight planning step: for complex multi-step requests, generate
        # an ordered plan and inject it so the model executes steps in sequence.
        role_str = (profile or {}).get("role") or "member"
        plan_text = await self._plan_if_complex(message, role_str, lang)
        if plan_text:
            messages.append({"role": "system", "content": plan_text})

        tone_msg = {"role": "system", "content": tone_system_prompt(active_tone, lang=lang)}
        messages.append(tone_msg)

        # #region agent log
        sys_count = sum(1 for m in messages if m.get("role") == "system")
        _tone_debug_log(
            "C", "ai_engine.py:tone_injection",
            "tone system message appended before user turn",
            {
                "active_tone": active_tone,
                "lang": lang,
                "system_message_count": sys_count,
                "tone_prompt_prefix": tone_msg["content"][:80],
                "placement": "last_system_before_user",
                "temperature": tone_temperature(active_tone),
                "runId": "post-fix-v2",
            },
        )
        # #endregion

        from backend.ai.conversation_flow import build_repeat_action_reminder
        repeat_reminder = build_repeat_action_reminder(
            message, history, user_id, lang=lang,
        )
        if repeat_reminder:
            messages.append({"role": "system", "content": repeat_reminder})

        from backend.ai.conversation_flow import (
            build_turn_reminder,
            build_claim_quantity_reminder,
            build_claim_execute_reminder,
            build_last_search_snapshot_reminder,
            build_fresh_search_after_claim_reminder,
            clear_last_search_listings,
            _user_clears_claim_flow,
            _recent_search_context,
            is_finding_flow,
            resolve_assistance_mode,
        )
        # Escape hatch: user denies a stuck claim, or asks for food with no
        # search results in-thread — drop stale server search cache so we
        # don't keep injecting VISIBLE LISTINGS into a phantom qty loop.
        if _user_clears_claim_flow(message) or (
            is_finding_flow(message, history) and not _recent_search_context(history)
        ):
            clear_last_search_listings(str(user_id))

        assist_mode = resolve_assistance_mode(
            message, history, user_id=str(user_id), guide_state=guide_state,
        )
        guided_active = assist_mode == "guided"

        turn_reminder, _ = build_turn_reminder(
            message, history, lang=lang, user_id=str(user_id),
        )
        if turn_reminder:
            messages.append({"role": "system", "content": turn_reminder})

        # Hands-on claim/search reminders conflict with UI-coached GUIDED mode.
        if not guided_active:
            fresh_search_reminder = build_fresh_search_after_claim_reminder(
                message, history, lang=lang,
            )
            if fresh_search_reminder:
                messages.append({"role": "system", "content": fresh_search_reminder})

            search_snapshot = build_last_search_snapshot_reminder(
                str(user_id), lang=lang,
            )
            if search_snapshot:
                messages.append({"role": "system", "content": search_snapshot})

            claim_qty_reminder = build_claim_quantity_reminder(
                message, history, lang=lang,
            )
            if claim_qty_reminder:
                messages.append({"role": "system", "content": claim_qty_reminder})

            claim_exec_reminder = build_claim_execute_reminder(
                message, history, lang=lang,
            )
            if claim_exec_reminder:
                messages.append({"role": "system", "content": claim_exec_reminder})

        from backend.ai.conversation_flow import build_posting_step_reminder
        posting_reminder = (
            None if guided_active
            else build_posting_step_reminder(message, history, lang=lang)
        )

        assist_reminder = None
        try:
            from backend.ai.conversation_flow import build_assistance_mode_reminder
            assist_reminder = build_assistance_mode_reminder(
                message,
                history,
                lang=lang,
                guide_state=guide_state,
                user_id=str(user_id),
            )
            if assist_reminder:
                messages.append({"role": "system", "content": assist_reminder})
                # Guided / fork-ask / open-page conflict with the posting script.
                # HANDS-ON must KEEP posting_reminder — that is the chat post flow.
                if assist_reminder.startswith((
                    "GUIDED", "GUIADO", "ASSISTANCE MODE", "MODO DE AYUDA",
                    "OPEN PAGE", "ABRIR PÁGINA", "ABRIR PAGINA",
                )):
                    posting_reminder = None
                    guided_active = assist_reminder.startswith((
                        "GUIDED", "GUIADO", "ASSISTANCE MODE", "MODO DE AYUDA",
                    ))
        except Exception as exc:  # pragma: no cover — advisory only
            logger.debug("assistance mode reminder skipped: %s", exc)

        if posting_reminder:
            messages.append({"role": "system", "content": posting_reminder})

        try:
            from backend.ai.conversation_flow import (
                sync_share_drafts,
                build_share_drafts_reminder,
                is_posting_flow,
            )
            if not guided_active and is_posting_flow(message, history):
                sync_share_drafts(str(user_id), message, history)
                drafts_reminder = build_share_drafts_reminder(
                    str(user_id), message, history, lang=lang,
                )
                if drafts_reminder:
                    messages.append({"role": "system", "content": drafts_reminder})
        except Exception as exc:  # pragma: no cover — advisory only
            logger.debug("share drafts reminder skipped: %s", exc)

        try:
            from backend.ai.conversation_flow import (
                sync_claim_drafts,
                build_claim_drafts_reminder,
                build_ambiguous_pick_reminder,
                build_food_order_spec_reminder,
                is_claiming_flow,
            )
            if not guided_active and (
                is_claiming_flow(message, history)
                or build_ambiguous_pick_reminder(
                    message, history, lang=lang, user_id=str(user_id),
                )
                or build_food_order_spec_reminder(
                    message, history, lang=lang, user_id=str(user_id),
                )
            ):
                sync_claim_drafts(str(user_id), message, history)
                claim_drafts_reminder = build_claim_drafts_reminder(
                    str(user_id), message, history, lang=lang,
                )
                if claim_drafts_reminder:
                    messages.append({"role": "system", "content": claim_drafts_reminder})
                else:
                    amb = build_ambiguous_pick_reminder(
                        message, history, lang=lang, user_id=str(user_id),
                    )
                    food_ord = build_food_order_spec_reminder(
                        message, history, lang=lang, user_id=str(user_id),
                    )
                    for rem in (amb, food_ord):
                        if rem:
                            messages.append({"role": "system", "content": rem})
        except Exception as exc:  # pragma: no cover — advisory only
            logger.debug("claim drafts reminder skipped: %s", exc)

        try:
            from backend.ai.world_model import build_world_model_reminder
            wm_reminder = build_world_model_reminder(
                message, history, lang=lang, flow=flow_kind,
            )
            if wm_reminder:
                messages.append({"role": "system", "content": wm_reminder})
        except Exception as exc:  # pragma: no cover — advisory only
            logger.debug("world_model reminder skipped: %s", exc)

        try:
            from backend.ai.allergens import build_allergen_reminder
            allergen_reminder = build_allergen_reminder(
                message, history, lang=lang, flow=flow_kind,
            )
            if allergen_reminder:
                messages.append({"role": "system", "content": allergen_reminder})
        except Exception as exc:  # pragma: no cover — advisory only
            logger.debug("allergen reminder skipped: %s", exc)

        # Metacognition / reflection layer. Silent by default — only
        # injects when a detector actually fires (repeat question, user
        # correction, tool loop, hallucinated-success carry-over, …).
        # See backend/ai/reflection.py.
        try:
            from backend.ai.reflection import (
                build_reflection_reminder,
                bump_turn,
            )
            bump_turn(str(user_id))
            reflection_msg = build_reflection_reminder(
                message, history, user_id=str(user_id), lang=lang,
            )
            if reflection_msg:
                messages.append({"role": "system", "content": reflection_msg})
        except Exception as exc:  # pragma: no cover — advisory only
            logger.debug("reflection reminder skipped: %s", exc)

        preattach_actions: list[dict] = []
        # Bare photo upload OR caption + image: URL(s) mid-share → auto-attach
        # when a listing is already in play.
        if re.search(r"image:\s*\S+", message or "", re.I):
            from backend.ai.conversation_flow import (
                donor_photo_add_intent,
                enrich_attach_photos_args,
                _extract_all_photo_urls_from_history,
            )
            intent = donor_photo_add_intent(message, history, user_id)
            photo_urls = _extract_all_photo_urls_from_history([], message)
            if not photo_urls and intent and intent.get("photo_url"):
                photo_urls = [intent.get("photo_url")]
            if intent and intent.get("listing_id") and photo_urls:
                attach_args = enrich_attach_photos_args(
                    {
                        "user_id": user_id,
                        "listing_id": intent["listing_id"],
                        "images": photo_urls,
                    },
                    message, history, user_id,
                )
                if attach_args.get("listing_id") and attach_args.get("images"):
                    attach_result = await self._execute_tool(
                        "attach_photos_to_listing", attach_args,
                    )
                    if isinstance(attach_result, dict) and attach_result.get("success"):
                        preattach_actions.append({
                            "tool": "attach_photos_to_listing",
                            "ok": True,
                            "summary": attach_result.get("summary"),
                            "listing_id": attach_result.get("listing_id"),
                            "image_url": attach_result.get("image_url"),
                        })
                        messages.append({
                            "role": "system",
                            "content": (
                                "SYSTEM: The donor's photo was automatically attached "
                                f"to listing {attach_result.get('listing_id')}. "
                                "Confirm warmly in one sentence. Do NOT call "
                                "attach_photos_to_listing again this turn."
                            ),
                        })

        messages.append({"role": "user", "content": message})

        response_text, actions = await self._call_with_fallbacks(
            messages, lang, auth_user_id=user_id, tone=active_tone,
            chat_history=history,
        )
        if preattach_actions:
            actions = preattach_actions + (actions or [])

        response_text = polish_assistant_response(response_text, actions, lang=lang)

        # Post-turn reflection: record tool outcomes for loop detection,
        # and flag hallucinated-success cases so next turn can course
        # correct. Fully silent + advisory — never modifies the reply.
        try:
            from backend.ai.reflection import capture_post_turn_reflection
            capture_post_turn_reflection(str(user_id), response_text, actions)
        except Exception as exc:  # pragma: no cover — advisory only
            logger.debug("reflection capture skipped: %s", exc)

        # Persist after chips/actions are known so history can restore them.
        pending_action_entry = next(
            (a for a in actions if a.get("type") == "requires_confirmation"),
            None,
        )

        suggestions = await self._build_suggestion_chips(
            response_text,
            lang,
            user_message=message,
            user_id=str(user_id),
            actions=actions,
            assistance_reminder=assist_reminder,
            guide_state=guide_state,
            history=history,
        )

        conversation_id = await self._persist_conversation(
            user_id,
            message,
            response_text,
            lang,
            metadata={
                "actions": actions,
                "suggestions": suggestions,
                "requires_confirmation": pending_action_entry is not None,
                "pending_action": pending_action_entry,
            },
        )

        audio_b64 = None
        if include_audio:
            audio_b64 = await self._generate_audio_b64(response_text, lang=lang)

        return {
            "text": response_text,
            "audio_url": audio_b64,  # data URL, or None
            "user_id": str(user_id),
            "lang": lang,
            "tone": active_tone,
            "conversation_id": str(conversation_id) if conversation_id else None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actions": actions,
            "suggestions": suggestions,
            "requires_confirmation": pending_action_entry is not None,
            "pending_action": pending_action_entry,
        }

    async def _persist_conversation(
        self,
        user_id: str,
        user_msg: str,
        assistant_msg: str,
        lang: str,
        *,
        metadata: dict | None = None,
    ) -> Optional[int]:
        try:
            assistant_meta = {"lang": lang}
            if metadata:
                assistant_meta.update(metadata)
            _, row_id = await asyncio.gather(
                self.store_message(user_id, "user", user_msg),
                self.store_message(
                    user_id, "assistant", assistant_msg, metadata=assistant_meta
                ),
            )
            return row_id
        except Exception as exc:
            logger.error("Persistence failed: %s", exc)
            return None

    # ---- GPT call with fallback ------------------------------------------

    @staticmethod
    def _normalize_repeat_tool_name(tool: str) -> str:
        aliases = {
            "update_listing": "update_food_listing",
            "edit_listing": "update_food_listing",
            "claim_food": "claim_listing",
        }
        return aliases.get(tool, tool)

    async def _auto_execute_repeat_action(
        self,
        user_id: str,
        message: str,
        history: list | None,
        actions_out: list | None,
        lang: str,
        tone: str,
    ) -> dict | None:
        """When the model replies without tools on 'and this too', run the action."""
        from backend.ai.conversation_flow import (
            AUTO_REPEAT_TOOLS,
            enrich_claim_listing_args,
            enrich_donor_listing_tool_args,
            enrich_repeat_write_action,
            get_last_write_action,
            is_repeat_followup,
            set_last_write_action,
        )

        if not is_repeat_followup(message, history):
            return None
        last = get_last_write_action(user_id)
        if not last:
            return None

        tool = self._normalize_repeat_tool_name(last.get("tool") or "")
        if tool not in AUTO_REPEAT_TOOLS:
            return None

        args = dict(last.get("args") or {})
        args["user_id"] = str(user_id)
        args = enrich_repeat_write_action(tool, args, message, history, user_id)

        if tool in {"update_food_listing", "deactivate_listing", "delete_listing"}:
            args = enrich_donor_listing_tool_args(
                tool, args, message, history, str(user_id),
            )
        elif tool == "claim_listing":
            args = enrich_claim_listing_args(
                args, message, history, str(user_id),
            )

        resolve_err = args.pop("_resolve_error", None)
        if resolve_err:
            logger.info("auto repeat blocked: %s", resolve_err)
            return None

        listing_id = args.get("listing_id")
        if tool in {"update_food_listing", "deactivate_listing", "claim_listing"}:
            if not listing_id:
                logger.info("auto repeat blocked: no listing_id resolved")
                return None
            if str(listing_id) == str(last.get("listing_id") or ""):
                logger.info("auto repeat blocked: same listing as last action")
                return None

        try:
            result = await self._execute_tool(tool, args)
        except Exception as exc:
            logger.exception("Auto repeat %s failed", tool)
            result = {"error": str(exc)}

        ok = tool_result_ok(result) if isinstance(result, dict) else False
        if ok:
            set_last_write_action(str(user_id), tool, args, result)

        summary = result.get("summary") if isinstance(result, dict) else None
        entry = {"tool": tool, "ok": bool(ok), "summary": summary}
        if isinstance(result, dict):
            entry = enrich_tool_action(tool, result, entry)
        if actions_out is not None:
            actions_out.append(entry)

        facts = {"tool": tool, "ok": ok, "auto_repeat": True}
        if isinstance(result, dict):
            for key in (
                "title", "quantity", "unit", "summary", "message", "error",
                "listing_id", "listing", "updated_fields", "community_name",
                "expiry_date", "pickup_location",
            ):
                if result.get(key) is not None:
                    facts[key] = result[key]

        situation = (
            "The user asked to repeat the last action on another target. "
            "Report the real outcome from facts — do not claim success if ok is false."
        )
        response_text = await self._agentic_reply_from_context(
            lang=lang,
            tone=tone,
            user_message=message,
            situation=situation,
            facts=facts,
        )
        return {"text": response_text, "result": result}

    async def _call_with_fallbacks(
        self,
        messages: list[dict],
        lang: str = "en",
        auth_user_id: Optional[str] = None,
        tone: str = "warm",
        chat_history: Optional[list] = None,
    ) -> tuple[str, list[dict]]:
        actions: list[dict] = []
        text = await self._call_openai_chat(
            messages, lang=lang, auth_user_id=auth_user_id,
            actions_out=actions, tone=tone, chat_history=chat_history,
        )

        user_text = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_text = m.get("content", "")
                break

        if auth_user_id and user_text:
            from backend.ai.conversation_flow import AUTO_REPEAT_TOOLS, is_repeat_followup
            write_ok = any(
                self._normalize_repeat_tool_name(a.get("tool", "")) in AUTO_REPEAT_TOOLS
                and a.get("ok")
                for a in actions
                if not a.get("type")
            )
            if is_repeat_followup(user_text, chat_history) and not write_ok:
                auto = await self._auto_execute_repeat_action(
                    str(auth_user_id), user_text, chat_history, actions, lang, tone,
                )
                if auto:
                    text = auto["text"]

        return text, actions

    async def public_chat_reply(self, messages: list[dict], lang: str = "en") -> str:
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
            resp = await _openai_with_retry(
                "POST",
                f"{OPENAI_BASE_URL}/chat/completions",
                headers=headers,
                json_payload=payload,
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
            # hunger / distress (plain language)
            "hungry", "hunger", "starving", "nothing to eat", "no food",
            "need food", "need to eat", "desperate", "single mother", "single mom",
            "single father", "family of", "feed my", "feed us", "feed the",
            "can't walk", "cant walk", "homebound", "pregnant", "vegan",
            "vegetarian", "allergic", "allergin", "hambre", "sin comida",
            "madre soltera", "familia de", "embarazad",
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
            # corrections / fixes
            "actually", "wait", "hold on", "i meant", "wrong", "change it",
            "change to", "fix", "edit", "typo", "different one", "the other one",
            "espera", "quise decir", "cambiar", "corrige", "equivoqu",
        }
        return any(kw in lower for kw in tool_keywords)

    # Tools that write on behalf of the user — user_id MUST come from the
    # authenticated session, never from the model's arguments.
    _ACTION_TOOLS = {
        "claim_listing",
        "claim_listings",
        "cancel_claim",
        "update_user_profile",
        "post_food_request",
        "post_food_listing",
        "post_food_listings",
        "attach_photos_to_listing",
        "send_user_message",
        "create_ai_reminder",
        "create_reminder",
    }

    async def _call_openai_chat(
        self,
        messages: list[dict],
        lang: str = "en",
        auth_user_id: Optional[str] = None,
        actions_out: Optional[list] = None,
        tone: str = "warm",
        chat_history: Optional[list] = None,
    ) -> str:
        from backend.ai.tone import normalize_tone, tone_reminder, tone_temperature

        active_tone = normalize_tone(tone)
        chat_temp = tone_temperature(active_tone)
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
            "temperature": chat_temp,
            "max_tokens": 1024,
        }
        if use_tools:
            payload["tools"] = self.tool_definitions

        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }

        resp = await _openai_with_retry(
            "POST",
            f"{OPENAI_BASE_URL}/chat/completions",
            headers=headers,
            json_payload=payload,
        )
        data = resp.json()
        choice = data["choices"][0]
        msg = choice["message"]

        # Agentic ReAct loop — Reason → Act → Observe, up to 8 rounds.
        # Compared to the old 3-round design this allows the model to:
        #   • Self-correct after a tool error (retry with fixed args)
        #   • Chain multiple independent tools in a single turn
        #   • Execute a multi-step plan end-to-end (post 3 listings, remind, etc.)
        #   • Call save_user_memory / mark_goal_done as finishing touches
        MAX_TOOL_ROUNDS = 8
        round_idx = 0
        posted_listing_id: Optional[str] = None
        updated_listing_ids: set[str] = set()

        # Memoised profile fetch for allergen/dietary enrichment. We hit
        # this at most once per turn, and only when a recipient-side
        # tool actually gets called.
        _profile_cache: dict[str, Optional[dict]] = {}

        async def _get_profile_for_enrichment() -> Optional[dict]:
            if "loaded" in _profile_cache:
                return _profile_cache.get("value")
            if auth_user_id is None:
                _profile_cache["loaded"] = True
                _profile_cache["value"] = None
                return None
            try:
                prof = await self.get_user_profile(str(auth_user_id))
            except Exception:  # pragma: no cover
                prof = None
            _profile_cache["loaded"] = True
            _profile_cache["value"] = prof
            return prof
        while msg.get("tool_calls") and round_idx < MAX_TOOL_ROUNDS:
            round_idx += 1

            # Capture the model's pre-tool reasoning from the content field.
            # GPT-4.1 often writes a brief "I need to search for X because…"
            # thought before emitting tool_calls.  Forward it to the caller
            # as a reasoning chip so the UI can optionally display it.
            reasoning_text = (msg.get("content") or "").strip()
            if reasoning_text and actions_out is not None:
                actions_out.append({"type": "reasoning", "text": reasoning_text})

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
                if not isinstance(fn_args, dict):
                    fn_args = {}
                if auth_user_id is not None and fn_name in self._tools_taking_user_id:
                    fn_args["user_id"] = str(auth_user_id)
                elif auth_user_id is not None and "user_id" in fn_args:
                    fn_args["user_id"] = str(auth_user_id)
                # Find-food reads must always scope to the signed-in user so
                # their own donations are excluded even if the model omitted
                # user_id (get_recent_listings) or hallucinated another id.
                if auth_user_id is not None and fn_name in {
                    "search_food_near_user",
                    "get_recent_listings",
                    "get_community_listings",
                    "claim_listing",
                    "claim_listings",
                    "claim_food",
                }:
                    fn_args["user_id"] = str(auth_user_id)
                # run_safe_query: force a caller-scoped filter on any entity
                # that has a user column, so the model can't enumerate other
                # users' listings/requests or read the users table freely.
                if fn_name == "run_safe_query" and auth_user_id is not None:
                    fn_args = _scope_safe_query(fn_args, auth_user_id)

                try:
                    from backend.ai.conversation_flow import (
                        assistance_mode_tool_block_reason,
                    )
                    assist_block = assistance_mode_tool_block_reason(
                        fn_name, user_text, chat_history,
                        user_id=str(auth_user_id) if auth_user_id else None,
                    )
                    if assist_block:
                        tool_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "content": json.dumps({
                                "error": "assistance_mode_required",
                                "message": assist_block,
                            }),
                        })
                        continue
                except Exception:  # pragma: no cover — advisory only
                    pass

                # Recipient-side allergen / dietary enrichment. Applies to
                # any tool where filtering the food set matters: search,
                # recipe suggestion, food-request creation. The model
                # tends to forget to pass these — the extractor reads them
                # from the current message + saved profile.
                if fn_name in {
                    "search_food_near_user",
                    "get_recipe_suggestions",
                    "post_food_request",
                    "update_food_request",
                }:
                    try:
                        from backend.ai.allergens import enrich_search_allergen_args
                        prof = await _get_profile_for_enrichment() or {}
                        fn_args = enrich_search_allergen_args(
                            fn_args,
                            user_text,
                            chat_history,
                            profile_allergens=(
                                prof.get("allergens")
                                or prof.get("allergies")
                                or []
                            ),
                            profile_dietary=(
                                prof.get("dietary_restrictions")
                                or prof.get("dietary_tags")
                                or []
                            ),
                        )
                    except Exception:  # pragma: no cover — advisory only
                        pass

                if fn_name == "search_food_near_user":
                    try:
                        from backend.ai.conversation_flow import enrich_search_food_args
                        fn_args = enrich_search_food_args(
                            fn_args, user_text, chat_history,
                        )
                    except Exception:  # pragma: no cover — advisory only
                        pass
                    # Single leftover food still auto-injects when model omitted
                    # title_query; multi-food enrich already set the OR query.
                    if not fn_args.get("title_query"):
                        try:
                            from backend.ai.conversation_flow import (
                                _mentioned_food_hint_from_message,
                            )
                            hint = _mentioned_food_hint_from_message(user_text)
                            if hint:
                                fn_args["title_query"] = hint
                        except Exception:  # pragma: no cover — advisory only
                            pass

                if fn_name == "attach_photos_to_listing" and auth_user_id is not None:
                    from backend.ai.conversation_flow import enrich_attach_photos_args
                    fn_args = enrich_attach_photos_args(
                        fn_args, user_text, chat_history, str(auth_user_id),
                    )

                if fn_name == "post_food_listings":
                    from backend.ai.conversation_flow import (
                        enrich_post_food_listings_args,
                        posting_batch_tool_block_reason,
                        sync_share_drafts,
                    )
                    if auth_user_id is not None:
                        sync_share_drafts(str(auth_user_id), user_text, chat_history)
                        fn_args = enrich_post_food_listings_args(
                            fn_args, user_text, chat_history, str(auth_user_id),
                        )
                    block_reason = posting_batch_tool_block_reason(
                        user_text, chat_history, fn_args,
                        user_id=str(auth_user_id or ""),
                    )
                    if block_reason:
                        tool_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "content": json.dumps({
                                "error": "posting_batch_incomplete",
                                "message": block_reason,
                            }),
                        })
                        continue

                if fn_name == "post_food_listing":
                    if posted_listing_id:
                        tool_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "content": json.dumps({
                                "error": "listing_already_posted",
                                "message": (
                                    f"Listing {posted_listing_id} was already posted this turn. "
                                    "Do NOT call post_food_listing again. To add a photo, use "
                                    "attach_photos_to_listing with that listing_id. For more "
                                    "foods in the same share, use post_food_listings."
                                ),
                                "listing_id": posted_listing_id,
                            }),
                        })
                        continue
                    if auth_user_id is not None:
                        from backend.ai.conversation_flow import (
                            get_share_drafts,
                            sync_share_drafts,
                        )
                        drafts = sync_share_drafts(
                            str(auth_user_id), user_text, chat_history,
                        )
                        if len(drafts) >= 2:
                            tool_messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call["id"],
                                "content": json.dumps({
                                    "error": "use_post_food_listings",
                                    "message": (
                                        f"The donor has {len(drafts)} share drafts in queue. "
                                        "Call post_food_listings with items[] for all of them "
                                        "(each with its own images[]), not post_food_listing."
                                    ),
                                    "draft_titles": [d.get("title") for d in drafts],
                                }),
                            })
                            continue
                    from backend.ai.conversation_flow import (
                        enrich_post_food_listing_args,
                        posting_tool_block_reason,
                    )
                    fn_args = enrich_post_food_listing_args(
                        fn_args, user_text, chat_history,
                    )
                    block_reason = posting_tool_block_reason(
                        user_text, chat_history, fn_args,
                    )
                    if block_reason:
                        tool_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "content": json.dumps({
                                "error": "posting_flow_incomplete",
                                "message": block_reason,
                            }),
                        })
                        continue

                if fn_name in {"update_food_listing", "update_listing", "edit_listing"} and auth_user_id is not None:
                    from backend.ai.conversation_flow import (
                        update_new_share_block_reason,
                    )
                    new_share_block = update_new_share_block_reason(
                        fn_name, fn_args, user_text, chat_history,
                        str(auth_user_id),
                    )
                    if new_share_block:
                        tool_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "content": json.dumps({
                                "error": "use_post_food_listing",
                                "message": new_share_block,
                            }),
                        })
                        continue

                if fn_name in {"delete_listing", "deactivate_listing", "update_food_listing", "update_listing", "edit_listing"} and auth_user_id is not None:
                    from backend.ai.conversation_flow import enrich_donor_listing_tool_args
                    fn_args = enrich_donor_listing_tool_args(
                        fn_name, fn_args, user_text, chat_history, str(auth_user_id),
                    )
                    resolve_err = fn_args.pop("_resolve_error", None)
                    if resolve_err:
                        tool_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "content": json.dumps({
                                "error": "invalid_listing_id",
                                "message": resolve_err,
                            }),
                        })
                        continue

                if fn_name in {"update_food_listing", "update_listing", "edit_listing"}:
                    target_lid = str(fn_args.get("listing_id") or "").strip()
                    if target_lid and target_lid in updated_listing_ids:
                        tool_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "content": json.dumps({
                                "error": "listing_already_updated",
                                "message": (
                                    f"Listing {target_lid} was already updated this turn. "
                                    "Do NOT call update_food_listing again for the same row."
                                ),
                                "listing_id": target_lid,
                            }),
                        })
                        continue

                    if auth_user_id is not None:
                        from backend.ai.conversation_flow import (
                            update_photo_intent_block_reason,
                        )
                        photo_block = update_photo_intent_block_reason(
                            fn_name, fn_args, user_text, chat_history,
                            str(auth_user_id),
                        )
                        if photo_block:
                            tool_messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call["id"],
                                "content": json.dumps({
                                    "error": "use_attach_photos_to_listing",
                                    "message": photo_block,
                                }),
                            })
                            continue

                if fn_name == "claim_listings" and auth_user_id is not None:
                    from backend.ai.conversation_flow import (
                        enrich_claim_listings_args,
                        claiming_batch_tool_block_reason,
                        sync_claim_drafts,
                    )
                    sync_claim_drafts(str(auth_user_id), user_text, chat_history)
                    fn_args = enrich_claim_listings_args(
                        fn_args, user_text, chat_history, str(auth_user_id),
                    )
                    block_reason = claiming_batch_tool_block_reason(
                        user_text, chat_history, fn_args,
                        user_id=str(auth_user_id),
                    )
                    if block_reason:
                        tool_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "content": json.dumps({
                                "error": "claim_batch_incomplete",
                                "message": block_reason,
                            }),
                        })
                        continue

                if fn_name == "claim_listing" and auth_user_id is not None:
                    from backend.ai.conversation_flow import (
                        enrich_claim_listing_args,
                        claiming_tool_block_reason,
                        sync_claim_drafts,
                    )
                    drafts = sync_claim_drafts(
                        str(auth_user_id), user_text, chat_history,
                    )
                    if len(drafts) >= 2:
                        tool_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "content": json.dumps({
                                "error": "use_claim_listings",
                                "message": (
                                    f"The recipient has {len(drafts)} claim drafts in queue. "
                                    "Call claim_listings with items[] for all of them "
                                    "(each with listing_id + quantity), not claim_listing."
                                ),
                                "draft_titles": [d.get("title") for d in drafts],
                            }),
                        })
                        continue
                    fn_args = enrich_claim_listing_args(
                        fn_args, user_text, chat_history, str(auth_user_id),
                    )
                    resolve_err = fn_args.pop("_resolve_error", None)
                    resolved_from = fn_args.pop("_resolved_from_index", None)
                    # #region agent log
                    _tone_debug_log(
                        "R1", "ai_engine.py:claim_listing_enrich",
                        "claim_listing args enriched",
                        {
                            "listing_id_prefix": str(fn_args.get("listing_id", ""))[:8],
                            "quantity": fn_args.get("quantity"),
                            "resolved_from_index": bool(resolved_from),
                            "resolve_error": resolve_err,
                            "runId": "claim-qty-v2",
                        },
                    )
                    # #endregion
                    if resolve_err:
                        tool_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "content": json.dumps({
                                "error": "invalid_listing_id",
                                "message": resolve_err,
                            }),
                        })
                        continue
                    block_reason = claiming_tool_block_reason(
                        user_text, chat_history, fn_args, str(auth_user_id),
                    )
                    if block_reason:
                        tool_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "content": json.dumps({
                                "error": "claim_flow_incomplete",
                                "message": block_reason,
                            }),
                        })
                        continue
                    for _k in (
                        "_resolved_from_history",
                        "_resolved_from_title",
                        "_no_matching_listing_food",
                    ):
                        fn_args.pop(_k, None)

                if auth_user_id is not None:
                    from backend.ai.conversation_flow import (
                        claiming_distractor_tool_block_reason,
                        posting_distractor_tool_block_reason,
                    )
                    distract_block = claiming_distractor_tool_block_reason(
                        fn_name, user_text, chat_history, str(auth_user_id),
                    )
                    if not distract_block:
                        distract_block = posting_distractor_tool_block_reason(
                            fn_name, user_text, chat_history,
                        )
                    if distract_block:
                        tool_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "content": json.dumps({
                                "error": "claim_flow_active",
                                "message": distract_block,
                            }),
                        })
                        continue

                # ---- Confirmation gate ----------------------------------------
                # Intercept destructive tools before execution. Store the call in
                # _pending_confirmations and return a prompt asking the user to
                # confirm.  The actual execution happens in POST /api/ai/confirm.
                if fn_name in _CONFIRM_TOOLS and auth_user_id is not None:
                    if _is_confirmation_reply(user_text):
                        fn_args = await self._enrich_confirmed_tool_args(
                            fn_name, fn_args, auth_user_id,
                            user_message=user_text, history=chat_history,
                        )
                    else:
                        summary = _build_confirmation_summary(fn_name, fn_args)
                        self._pending_confirmations[auth_user_id] = {
                            "tool": fn_name,
                            "args": fn_args,
                            "expires_at": (_utcnow() + timedelta(minutes=5)).isoformat(),
                            "auth_user_id": auth_user_id,
                            "lang": lang,
                            "summary": summary,
                        }
                        if actions_out is not None:
                            actions_out.append({
                                "type": "requires_confirmation",
                                "tool": fn_name,
                                "summary": summary,
                                "ok": False,
                            })
                        tool_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "content": json.dumps({
                                "status": "awaiting_confirmation",
                                "action_summary": summary,
                                "instruction": (
                                    "The action has NOT run yet. Ask the user to confirm "
                                    "in one warm sentence. They can tap Confirm below or "
                                    "reply Yes, confirm. Mention they can say Wait, edit it "
                                    "to change something or Cancel to abort."
                                ),
                            }),
                        })
                        continue
                # --------------------------------------------------------------

                try:
                    result = await self._execute_tool(fn_name, fn_args)
                except Exception as tool_exc:
                    # Log full traceback server-side; surface a generic
                    # message so internal exception text doesn't reach
                    # the user via the AI's reply.
                    logger.exception("Tool %s failed", fn_name)
                    result = {"error": True, "message": f"{fn_name} failed. Please try again."}

                if (
                    fn_name == "post_food_listing"
                    and isinstance(result, dict)
                    and tool_result_ok(result)
                    and auth_user_id is not None
                    and result.get("listing_id")
                    and not result.get("image_url")
                    and not result.get("photo_merged")
                ):
                    from backend.ai.conversation_flow import (
                        _extract_photo_url_for_current_posting,
                        enrich_attach_photos_args,
                    )
                    photo = _extract_photo_url_for_current_posting(
                        chat_history, user_text,
                    )
                    if photo:
                        attach_args = enrich_attach_photos_args(
                            {
                                "user_id": str(auth_user_id),
                                "listing_id": str(result["listing_id"]),
                                "images": [photo],
                            },
                            user_text, chat_history, str(auth_user_id),
                        )
                        attach_result = await self._execute_tool(
                            "attach_photos_to_listing", attach_args,
                        )
                        if isinstance(attach_result, dict) and attach_result.get("success"):
                            result["image_url"] = attach_result.get("image_url")
                            result["has_photo"] = True
                            result["photo_auto_attached"] = True
                            if attach_result.get("summary"):
                                result["summary"] = (
                                    f"{result.get('summary') or ''} "
                                    f"{attach_result['summary']}"
                                ).strip()

                # Trace tool calls so we can debug why the model picked a tool.
                try:
                    logger.info(
                        "AI tool call: %s args=%s ok=%s",
                        fn_name,
                        {k: v for k, v in fn_args.items() if k != "user_id"},
                        tool_result_ok(result) if isinstance(result, dict) else True,
                    )
                except Exception:
                    pass

                # Record this tool call so the UI can surface progress /
                # done indicators (claiming, listing posted, etc.).
                if actions_out is not None and isinstance(result, dict):
                    err_val = result.get("error")
                    ok = tool_result_ok(result)
                    # Suppress noisy chips when the model hallucinates a listing
                    # the user never asked for.
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
                            "listing_id": result.get("listing_id"),
                        }
                        entry = enrich_tool_action(fn_name, result, entry)
                        # Guided tutorial: never forward navigate_ui to the FE —
                        # the AI must TELL the user to open the page, not open it.
                        skip_nav_forward = False
                        if fn_name == "navigate_ui":
                            try:
                                from backend.ai.conversation_flow import (
                                    resolve_assistance_mode,
                                )
                                if resolve_assistance_mode(
                                    user_text, chat_history,
                                    user_id=str(auth_user_id) if auth_user_id else None,
                                ) == "guided":
                                    skip_nav_forward = True
                            except Exception:
                                pass
                        if skip_nav_forward:
                            pass
                        else:
                            # Forward extra UI-control fields (navigate_ui / show_map)
                            # so the frontend can act on them without another roundtrip.
                            for extra_key in ("ok", "path", "action", "target", "view", "focus"):
                                if extra_key in result and result[extra_key] is not None:
                                    entry[extra_key] = result[extra_key]
                            # show_route_to_listing returns a `route` envelope
                            # (origin/destination/geometry) that the frontend
                            # draws on the map. Forward it as-is.
                            if isinstance(result.get("route"), dict):
                                entry["route"] = result["route"]
                            # Forward coords + verification status from
                            # post_food_listing so app.js can fly the map to the
                            # new pin even if a follow-up refreshForUser() fetch
                            # fails (network blip, slow DB, expired token). We
                            # don't want a transient fetch failure to leave the
                            # donor staring at an unmoved map after a successful
                            # post.
                            for extra_key in ("coords_lat", "coords_lng", "address", "verified", "verify_issues", "duplicate_of_recent"):
                                if extra_key in result and result[extra_key] is not None:
                                    entry[extra_key] = result[extra_key]
                            actions_out.append(entry)

                    if (
                        fn_name == "post_food_listing"
                        and ok
                        and isinstance(result, dict)
                        and result.get("listing_id")
                    ):
                        posted_listing_id = str(result["listing_id"])
                        if auth_user_id is not None:
                            from backend.ai.conversation_flow import clear_share_drafts
                            # Single-item posts must also clear the queue so a
                            # later "share carrots" doesn't keep bananas around.
                            clear_share_drafts(str(auth_user_id))

                    if (
                        fn_name == "post_food_listings"
                        and ok
                        and isinstance(result, dict)
                        and (result.get("count_posted") or 0) > 0
                    ):
                        posted_rows = result.get("posted") or []
                        if posted_rows and isinstance(posted_rows[0], dict):
                            posted_listing_id = str(
                                posted_rows[0].get("listing_id") or posted_listing_id or ""
                            ) or posted_listing_id
                        if auth_user_id is not None:
                            from backend.ai.conversation_flow import clear_share_drafts
                            clear_share_drafts(str(auth_user_id))
                        if actions_out is not None and isinstance(result, dict):
                            # Ensure success copy can hit post-success markers.
                            if not result.get("summary"):
                                posted_rows = result.get("posted") or []
                                awaiting = sum(
                                    1 for p in posted_rows
                                    if isinstance(p, dict) and (
                                        p.get("awaiting_approval")
                                        or str(p.get("status") or "").lower() == "pending"
                                    )
                                )
                                n = result.get("count_posted", 0)
                                if awaiting and awaiting >= n:
                                    result["summary"] = (
                                        f"Posted! {n} listings awaiting admin approval. "
                                        "Please wait for admin approval."
                                    )
                                else:
                                    result["summary"] = (
                                        f"Posted! {n} listings are live."
                                    )

                    if (
                        fn_name == "claim_listings"
                        and ok
                        and isinstance(result, dict)
                        and (result.get("count_claimed") or 0) > 0
                    ):
                        if auth_user_id is not None:
                            from backend.ai.conversation_flow import (
                                clear_claim_drafts,
                                remove_claimed_from_drafts,
                            )
                            claimed_rows = result.get("claimed") or []
                            claimed_ids = [
                                row.get("listing_id")
                                for row in claimed_rows
                                if isinstance(row, dict) and row.get("listing_id")
                            ]
                            # Keep failed drafts so the user can retry those.
                            if (result.get("count_failed") or 0) > 0 and claimed_ids:
                                remove_claimed_from_drafts(
                                    str(auth_user_id), claimed_ids
                                )
                            else:
                                clear_claim_drafts(str(auth_user_id))
                        if actions_out is not None and isinstance(result, dict):
                            if not result.get("summary"):
                                result["summary"] = (
                                    f"Claimed! {result.get('count_claimed', 0)} listings reserved. "
                                    "Please wait for admin approval before pickup."
                                )

                    if (
                        fn_name == "claim_listing"
                        and ok
                        and isinstance(result, dict)
                        and result.get("success")
                        and auth_user_id is not None
                    ):
                        # Drop leftover single-item drafts so the next claim
                        # isn't forced into stale claim_listings mode.
                        from backend.ai.conversation_flow import (
                            clear_claim_drafts,
                            get_claim_drafts,
                        )
                        leftovers = get_claim_drafts(str(auth_user_id))
                        if leftovers:
                            clear_claim_drafts(str(auth_user_id))

                    if (
                        fn_name in {"update_food_listing", "update_listing", "edit_listing"}
                        and ok
                        and isinstance(result, dict)
                        and result.get("listing_id")
                    ):
                        updated_listing_ids.add(str(result["listing_id"]))

                    if ok and auth_user_id is not None:
                        from backend.ai.conversation_flow import (
                            REPEATABLE_WRITE_TOOLS,
                            set_last_write_action,
                        )
                        norm = self._normalize_repeat_tool_name(fn_name)
                        if norm in REPEATABLE_WRITE_TOOLS:
                            set_last_write_action(
                                str(auth_user_id), norm, fn_args, result,
                            )

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

            tool_messages.append({
                "role": "system",
                "content": tone_reminder(active_tone, lang=lang),
            })

            followup_payload = {
                "model": FOLLOWUP_MODEL,
                "messages": tool_messages,
                "temperature": chat_temp,
                "max_tokens": 1024,
                # Keep tools attached so the model can retry after a tool
                # error (e.g. correct an address, switch category) instead
                # of silently giving up in text.
                "tools": self.tool_definitions,
            }
            try:
                resp = await _openai_with_retry(
                    "POST",
                    f"{OPENAI_BASE_URL}/chat/completions",
                    headers=headers,
                    json_payload=followup_payload,
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
                raise RuntimeError("AI follow-up failed") from followup_exc

        return msg.get("content") or ""

    # ---- Whisper + TTS ---------------------------------------------------

    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        filename: str = "audio.webm",
        content_type: str | None = None,
    ) -> str:
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY not configured")
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
        # OpenAI infers format from the filename extension AND the part's
        # Content-Type. Passing both avoids 400s when the client labelled
        # the blob oddly (e.g. Safari mp4 bytes uploaded as audio.webm).
        mime = (content_type or "").split(";")[0].strip() or "application/octet-stream"
        resp = await _openai_with_retry(
            "POST",
            f"{OPENAI_BASE_URL}/audio/transcriptions",
            headers=headers,
            files={"file": (filename, audio_bytes, mime)},
            data={"model": WHISPER_MODEL, "response_format": "json"},
            timeout=60,
        )
        return resp.json()["text"]

    async def generate_speech(self, text: str, lang: str = "en") -> bytes:
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY not configured")
        truncated = text[:4096]
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

    async def _build_suggestion_chips(
        self,
        response_text: str,
        lang: str,
        *,
        user_message: str,
        user_id: str,
        actions: Optional[list] = None,
        pending_suggestions: Optional[list] = None,
        assistance_reminder: Optional[str] = None,
        guide_state: Optional[dict] = None,
        history: Optional[list] = None,
    ) -> list:
        """Contextual pre-chips for the assistant bubble.

        Prefer tool-aware chips (Claim #N, next-step after post/claim) and
        reply-matched quick replies. Never pad with generic menu chips — empty
        is better than irrelevant suggestions.
        """
        from backend.agent.suggestion_chips import (
            build_turn_suggestions,
            should_load_active_communities,
            share_assistance_fork_chips,
            _chips_for_guided_response,
            _looks_like_guided_tutorial,
            _user_chose_guided,
            _user_chose_hands_on,
            is_hands_on_share_active,
            resolve_hands_on_share_chip_step,
        )

        # When we just asked the do-it-for-me vs guide fork,
        # force goal-aware chips even if the model rephrased the question.
        # But never re-show the fork after the user already chose a mode.
        if (
            _user_chose_guided(user_message or "", assistance_reminder or "")
            or _looks_like_guided_tutorial(response_text or "")
        ):
            guided = _chips_for_guided_response(
                response_text or "", lang or "en", force=True,
            )
            if guided:
                return _serialize_suggestion_chips(guided)

        if not _user_chose_hands_on(user_message or "", assistance_reminder or ""):
            if not is_hands_on_share_active(
                user_message or "", history, assistance_reminder or "",
            ):
                forced = share_assistance_fork_chips(
                    response_text or "",
                    lang or "en",
                    user_message=user_message or "",
                    assistance_reminder=assistance_reminder,
                    guide_state=guide_state,
                )
                if forced:
                    return _serialize_suggestion_chips(forced)

        hands_on_step = None
        if is_hands_on_share_active(
            user_message or "", history, assistance_reminder or "",
        ):
            hands_on_step = resolve_hands_on_share_chip_step(
                user_message or "",
                history,
                assistance_reminder=assistance_reminder or "",
                response_text=response_text or "",
            )

        communities: list[str] = []
        suggested: Optional[str] = None
        reply_l = (response_text or "").lower()
        from backend.ai.conversation_flow import is_post_success_response
        needs_communities = (
            hands_on_step in ("community", "community_pick")
            or not is_post_success_response(response_text or "")
            and (
                should_load_active_communities(
                    response_text or "",
                    last_user_message=user_message or "",
                    user_context=None,
                )
                or _user_picked_different_community(user_message or "")
                or (
                    ("?" in reply_l or "¿" in reply_l)
                    and any(
                        k in reply_l
                        for k in (
                            "which community", "which school", "community should",
                            "go under", "list under", "post under",
                            "comunidad", "escuela", "bajo qué", "bajo que",
                        )
                    )
                )
            )
        )
        if needs_communities:
            communities = await _fetch_active_community_names(user_id)
            suggested = await _suggested_community_name(user_id)

        user_context = {
            "active_communities": communities,
            "suggested_community": suggested,
        }
        if isinstance(guide_state, dict):
            user_context["pageKey"] = guide_state.get("pageKey")
            user_context["path"] = guide_state.get("path")
        try:
            chips = build_turn_suggestions(
                response_text or "",
                lang or "en",
                tool_results=list(actions or []),
                pending_suggestions=pending_suggestions,
                last_user_message=user_message or "",
                user_context=user_context,
                min_chips=0,
                assistance_reminder=assistance_reminder,
                history=history,
            )
        except Exception as exc:
            logger.warning("suggestion chips failed (non-fatal): %s", exc)
            return generate_quick_replies(
                response_text or "",
                lang or "en",
                user_message=user_message or "",
                communities=communities or None,
                suggested_community=suggested,
            )

        return _serialize_suggestion_chips(chips)


def _serialize_suggestion_chips(chips: list) -> list:
    """Normalize chips to FE-safe strings / {label, message} dicts."""
    out: list = []
    seen: set[str] = set()
    for chip in chips or []:
        if isinstance(chip, str):
            label = chip.strip()
            if not label or label.lower() in seen:
                continue
            seen.add(label.lower())
            out.append(label)
            continue
        if not isinstance(chip, dict):
            continue
        label = str(
            chip.get("label") or chip.get("message") or chip.get("prompt") or ""
        ).strip()
        message = str(
            chip.get("message") or chip.get("prompt") or chip.get("label") or ""
        ).strip()
        if not label or label.lower() in seen:
            continue
        seen.add(label.lower())
        item: dict = {"label": label[:60], "message": message or label}
        if chip.get("kind"):
            item["kind"] = chip["kind"]
        if chip.get("step"):
            item["step"] = chip["step"]
        if chip.get("href") or chip.get("target") or chip.get("path") or chip.get("action") == "navigate":
            item["action"] = "navigate"
            if chip.get("path") or (isinstance(chip.get("href"), str) and str(chip.get("href")).startswith("/")):
                item["path"] = chip.get("path") or chip.get("href")
            if chip.get("target"):
                item["target"] = chip.get("target")
            if chip.get("href"):
                item["href"] = chip.get("href")
        out.append(item)
        if len(out) >= 40:
            break
    return out[:40]


def _user_picked_different_community(user_message: str) -> bool:
    t = (user_message or "").strip().lower()
    return any(k in t for k in (
        "different one", "different community", "other community", "another school",
        "other school", "another community", "pick a different", "choose another",
        "otra comunidad", "una diferente", "different school", "otra escuela",
    ))


async def _fetch_active_community_names(user_id: str) -> list[str]:
    try:
        from backend.tools import _get_active_communities
        result = await _get_active_communities(user_id, max_results=500)
        names: list[str] = []
        for row in result.get("communities") or []:
            name = str(row.get("name") or "").strip()
            if name and name not in names:
                names.append(name)
        return names
    except Exception:
        return []


async def _suggested_community_name(user_id: str) -> Optional[str]:
    try:
        from backend.ai.tools import _fallback_community_for_user
        _, cname = await _fallback_community_for_user(str(user_id))
        return cname
    except Exception:
        return None


def _is_combined_food_qty_ask(t: str) -> bool:
    """True when the AI asks for food name AND amount in the same turn.

    Hands-on share often phrases this as
    \"What food do you want to share, and how much do you have?\" — that must
    get food+qty example chips, not bare 1/3/5/10.
    """
    t = (t or "").lower()
    if any(k in t for k in (
        "what food and how much", "food and how much", "food name and",
        "name and roughly how much", "what and how much",
        "tell me what you have", "tell me what you've got",
        "qué y cuánto", "que y cuanto", "comida y cantidad",
        "qué comida y cuánto", "que comida y cuanto",
        "qué comida y cuánta", "que comida y cuanta",
    )):
        return True
    food_ask = any(k in t for k in (
        "what food", "what would you like to share", "what would you like to donate",
        "what are you sharing", "what are you donating", "what do you have",
        "tell me what you have", "what kind of food", "food name", "tell me the food",
        "qué comida", "que comida",
        "qué quieres compartir", "que quieres compartir",
        "qué te gustaría compartir", "que te gustaria compartir",
        "qué vas a donar", "que vas a donar",
        "qué quieres donar", "que quieres donar",
        "qué vas a compartir", "que vas a compartir",
    ))
    qty_ask = any(k in t for k in (
        "how much", "how many", "cuánto", "cuanto", "cuánta", "cuanta",
        "cuántos", "cuantos", "cuántas", "cuantas",
    ))
    return food_ask and qty_ask


_ALLERGEN_WORDS: tuple[str, ...] = (
    "nuts", "dairy", "eggs", "wheat", "soy", "shellfish", "gluten",
    "peanut", "sesame", "fish", "frutos secos", "lácteos", "lacteos",
    "huevos", "trigo",
)


def _is_post_confirm_ask(t: str) -> bool:
    """True when the assistant is asking the donor to greenlight posting."""
    t = (t or "").lower()
    community_intent = any(k in t for k in (
        "which community", "which school", "list under", "listed under",
        "your community", "linked to", "use that one", "for the community",
        "community should", "post this under", "post it to", "post under",
        "comunidad", "escuela",
    ))
    recap = any(k in t for k in (
        "ready to post", "look right", "looks right", "does this look",
        "does that look", "sound good to post", "with photo", "good until",
        "expires ", "expiry",
    ))
    if community_intent and not recap:
        return False
    if ("should i post" in t or "shall i post" in t) and " under " in t and not recap:
        return False
    if any(k in t for k in (
        "ready to post", "ready to publish", "shall i post", "should i post",
        "want me to post", "good to post", "good to publish",
        "look right", "looks right", "does this look", "does that look",
        "sound good to post", "sounds good to post",
        "go ahead and share", "shall i go ahead", "should i go ahead",
        "confirm and post", "before i post",
        "listo para publicar", "¿lo publico", "¿lo publicamos",
    )):
        return True
    if any(k in t for k in ("look good", "looks good", "sound good", "sounds good")):
        return any(k in t for k in ("post", "publish", "listing", "share"))
    return False


def _is_allergen_ask(t: str) -> bool:
    """True when the assistant is asking about allergens / dietary flags."""
    t = (t or "").lower()
    if _is_post_confirm_ask(t):
        return False
    if any(k in t for k in (
        "allerg", "alérgen", "alergen", "alergia", "alergias",
        "dietary restriction", "restricciones diet", "restricción diet",
    )):
        asking = any(k in t for k in (
            "should i", "any allerg", "any dietary", "contain", "flag",
            "does this", "do these", "would you", "can you", "know about",
            "?", "¿",
        ))
        if not asking:
            return False
        return True
    # Common hands-on phrasing lists major allergens without the word itself.
    hits = sum(1 for w in _ALLERGEN_WORDS if w in t)
    asking = any(k in t for k in (
        "contain", "any ", "should i", "flag", "note", "mention",
        "know about", "does this", "do these", "?", "¿",
    ))
    if hits >= 2 and asking:
        return True
    if any(k in t for k in ("shellfish", "frutos secos", "gluten", "lácteos", "lacteos")):
        if any(k in t for k in (
            "nuts", "dairy", "eggs", "wheat", "soy", "any ", "note",
            "should i", "contain", "mention", "know about", "frutos", "huevos",
        )):
            return True
    return False


def _is_expiry_ask(t: str) -> bool:
    """True when the assistant is asking for a good-until / best-by date.

    Must not fire on allergen turns, post success, or acknowledgements that
    merely repeat a date already chosen (\"Got it — best by tomorrow.\").
    """
    t = (t or "").lower()
    if _is_allergen_ask(t):
        return False
    try:
        from backend.ai.conversation_flow import is_post_success_response
        if is_post_success_response(t):
            return False
    except Exception:
        pass
    if any(k in t for k in (
        "photo", "picture", "foto", "imagen", "community", "school",
        "ready to post", "post it", "publish",
    )) and not any(k in t for k in ("best by", "good until", "expir", "how long", "use by")):
        return False

    has_cue = any(k in t for k in (
        "best by", "best-by", "good until", "good-until", "good for",
        "use by", "use-by",
        "when does it expire", "when will it expire", "when is it good",
        "how long is it good", "how long will it keep", "how long will it stay",
        "stay fresh", "expiration", "expiry", "best before",
        "what's the best", "what is the best", "need a date", "need the date",
        "give me a date", "caduc", "vence", "fecha de venc",
        "hasta cuándo es bueno", "hasta cuando es bueno",
        "cuánto dura", "cuanto dura",
    ))
    if not has_cue:
        return False

    # Acknowledgement of a date already chosen — don't re-offer date chips
    # unless clearly re-asking / offering to change it.
    ack = any(k in t for k in (
        "got it", "noted", "i'll use", "i will use", "set to", "set as",
        "locked in", "confirmed", "sounds good", "using tomorrow",
        "using that", "saved as", "listed as", "perfecto", "listo —",
        "anotado", "queda",
    ))
    re_ask = any(k in t for k in (
        "change", "different date", "or different", "update the", "wrong date",
        "another date", "new date", "when is", "when does", "how long",
        "still good", "want a different", "prefer a different", "?", "¿",
    ))
    if ack and not re_ask:
        return False
    return True


def generate_quick_replies(
    text: str,
    lang: str = "en",
    *,
    user_message: str = "",
    communities: Optional[list[str]] = None,
    suggested_community: Optional[str] = None,
    guide_state: Optional[dict] = None,
    assistance_reminder: Optional[str] = None,
) -> list[str]:
    """Heuristic 'smart reply' / autofill chips for the chat UI.

    Looks at the last AI message and returns up to 4 short tappable
    suggestions the user is likely to want to reply with. Pure string
    matching — no extra LLM call, so it's free and instant.

    Rule of thumb: it is better to return [] (no chips) than to return
    chips that don't match the question. Yes/No/Later under "what food
    would you like to share?" is worse than no chips at all.
    """
    um = (user_message or "").strip().lower()
    if not text:
        if _is_food_insecurity_distress(user_message):
            es = lang == "es"
            if es:
                return ["Buscar comida cerca de mí", "Algo fácil de preparar", "No puedo ir en persona"]
            return ["Find food near me", "Something easy to prepare", "I can't get there in person"]
        return []
    t = text.lower()
    # Prefer the reply's own language so chips match Spanish answers even
    # if sticky lang briefly lags behind.
    if lang != "es" and (
        "¿" in text
        or any(k in t for k in (
            " qué ", " cuál ", " cómo ", " cuándo ", " dónde ",
            "quieres que", "paso a paso", "hazlo por", "comida",
        ))
    ):
        lang = "es"
    communities = communities or []
    es = lang == "es"
    out: list[str] = []

    def add(*items: str) -> None:
        for it in items:
            if it and it not in out and len(out) < 40:
                out.append(it)

    # User expressed hunger/distress — helpful starters even before AI asks a question.
    if _is_food_insecurity_distress(user_message) and len(t.strip()) < 40:
        if es:
            add("Buscar comida cerca de mí", "Algo fácil de preparar", "No puedo ir en persona")
        else:
            add("Find food near me", "Something easy to prepare", "I can't get there in person")
        return out

    # User asked for a different community → show all other active schools/hubs.
    if _user_picked_different_community(user_message) and communities:
        if suggested_community:
            others = [
                c for c in communities
                if c.lower() != suggested_community.lower()
            ]
        else:
            others = list(communities)
        add(*(others or communities))
        return out[:40]

    # GUIDED UI coaching often has no "?" ("Say done when filled") — handle
    # before the question-only gate so chips still match the step.
    from backend.agent.suggestion_chips import (
        _chips_for_guided_response,
        _looks_like_guided_tutorial,
        _user_chose_guided,
    )
    if (
        _looks_like_guided_tutorial(text)
        or _user_chose_guided(user_message or "", "")
        or any(k in t for k in ("guided —", "guided -", "guiado —", "guiado -"))
        or t.lstrip().startswith(("guided", "guiado"))
    ):
        guided = _chips_for_guided_response(text, lang, force=True)
        if guided:
            for chip in guided:
                label = chip.get("label") if isinstance(chip, dict) else str(chip or "")
                if label:
                    add(label)
            return out
        if es:
            add("Listo", "Siguiente", "Necesito ayuda")
        else:
            add("Done", "What's next?", "Need help")
        return out

    # Photo required — often no "?" ("Please upload a photo — required…").
    # Never offer skip. Run before the question-only gate.
    photo_ask = any(k in t for k in ("photo", "picture", "foto", "imagen")) and any(
        k in t for k in (
            "required", "please", "need", "upload", "attach", "add a", "add one",
            "before posting", "before we post", "mandar", "sube", "subir",
            "photo of", "picture of", "snap", "send a photo", "send a picture",
            "send one", "so we can post", "para publicar",
            "without a photo", "without photo", "skip the photo",
        )
    )
    if photo_ask and not any(k in t for k in (
        "photos received", "got your photo", "thanks for the photo", "with your photos",
        "with photo", "with a photo", "photo attached", "foto adjunta", "fotos recibidas",
        "already have a photo", "look right", "looks right", "does this look",
        "ready to post", "shall i post", "want me to post", "listo para publicar",
        "lo publico", "lo publicamos", "publicarlo",
    )):
        if es:
            add("Adjuntar foto")
        else:
            add("Attach a photo")
        return out

    # Post confirm recaps often mention allergens/expiry/photo in the summary.
    # Handle before allergen/description/expiry so chips stay Yes/Edit/Cancel.
    if _is_post_confirm_ask(t):
        photo_evidence = any(k in t for k in (
            "photos received", "got your photo", "with your photos",
            "with photo", "with a photo", "has a photo",
            "photo attached", "already have a photo", "image:",
            "foto adjunta", "fotos recibidas", "con tus fotos", "con su foto",
            "con foto", "con una foto",
        )) or "http" in t
        photo_nudge = (
            not photo_evidence
            and any(k in t for k in (
                "ready to post", "ready to publish",
                "shall i post", "should i post", "want me to post",
            ))
            and not any(k in t for k in (
                "look right", "looks right", "does this look", "does that look",
                "sound good", "sounds good", "go ahead and share",
            ))
        )
        if photo_nudge:
            if es:
                add("Adjuntar foto")
            else:
                add("Attach a photo")
            return out
        if es:
            add("Sí, publícalo", "Espera, edítalo", "Cancelar")
        else:
            add("Yes, post it", "Wait, edit it", "Cancel")
        return out

    # Allergen ask early — same turn often also mentions a chosen best-by date.
    if _is_allergen_ask(t):
        if es:
            add("Sin alérgenos", "Solo gluten", "Lácteos", "Frutos secos")
        else:
            add("No allergens", "Just gluten", "Dairy", "Nuts")
        return out

    # Assistance fork — shared matcher (find/share/request).
    # After photo; before other heuristics. Skip when this is clearly a
    # post/claim confirm so "want me to post" doesn't become mode chips.
    _post_or_claim = any(k in t for k in (
        "post it", "publish it", "post the", "publish the", "claim this",
        "claim it", "claim these", "ready to post", "ready to claim",
        "lo publico", "publicarlo", "reclamar",
    ))
    if not _post_or_claim:
        from backend.agent.suggestion_chips import share_assistance_fork_chips
        fork = share_assistance_fork_chips(
            text, lang, user_message=user_message or "",
            assistance_reminder=assistance_reminder or "",
            guide_state=guide_state,
        )
        if fork:
            for chip in fork:
                label = chip.get("label") if isinstance(chip, dict) else str(chip or "")
                if label:
                    add(label)
            return out

    # ── Statement-style asks (often no "?") ──────────────────────────
    # Donor type
    if any(k in t for k in (
        "donor type", "individual/family", "individual / family",
        "tipo de donante", "organización o", "organization for donor",
    )):
        if es:
            add("Individual/Familia", "Organización")
        else:
            add("Individual/Family", "Organization")
        return out

    # Donor name / organization
    if any(k in t for k in (
        "your name", "donor name", "name / organization", "name/organization",
        "organization for the donor", "nombre / organización", "nombre u organización",
        "name or organization",
    )):
        if es:
            add("Usar mi nombre de perfil", "Es una organización")
        else:
            add("Use my profile name", "It's an organization")
        return out

    # Listing title
    if any(k in t for k in (
        "call this listing", "listing title", "title for", "what should we call",
        "nombre del listado", "título del", "titulo del",
    )):
        if es:
            add("Pan fresco", "Caja de verduras", "Comida preparada")
        else:
            add("Fresh bread", "Vegetable box", "Prepared meals")
        return out

    # Description — after photo/allergen/fork so those turns keep their chips.
    # Before expiry/community so a school name in the same message doesn't steal.
    from backend.ai.conversation_flow import _is_description_ask
    if _is_description_ask(t) and not _is_allergen_ask(t):
        if es:
            add("Sigue sellado", "Casero, refrigerado", "Sobras variadas")
        else:
            add("Still sealed", "Homemade, refrigerated", "Assorted leftovers")
        return out

    # Combined food + amount (no "?") — also "What food … and how much?"
    if _is_combined_food_qty_ask(t):
        if es:
            add("5 manzanas", "2 panes", "Verduras — 1 caja", "Huevos — 1 docena")
        else:
            add("5 apples", "2 loaves of bread", "Vegetables — 1 box", "Eggs — 1 dozen")
        return out

    # Freshness / good-until — BEFORE the "?" gate. Models often ask
    # "When does it expire" without a question mark; chips must still show.
    if _is_expiry_ask(t):
        if es:
            add("Mañana", "En 2 días", "En 3 días", "En un mes")
        else:
            add("Tomorrow", "In 2 days", "In 3 days", "In a month")
        return out

    # Post / claim success → productive next steps (not Yes/No / community)
    from backend.ai.conversation_flow import is_post_success_response
    if is_post_success_response(text) or any(k in t for k in (
        "are shared", "is shared", "posted!", "posted your", "listing is live",
        "listings are live", "successfully posted", "ya está publicado",
        "your listing is live", "is now live", "went live",
        "anything else you want to share", "anything else you'd like to share",
        "share another", "claimed successfully", "claim is confirmed",
        "pickup is set", "you're all set", "awaiting admin approval",
    )):
        if es:
            add("Compartir otra cosa", "Buscar comida", "Eso es todo")
        else:
            add("Share something else", "Find food near me", "That's all for now")
        return out

    # AI is asking the donor to pick a community (after "different one").
    community_pick_keys = (
        "which community", "which school", "pick a community", "choose a community",
        "select a school", "select a community", "what community", "what school",
        "qué comunidad", "que comunidad", "cuál escuela", "cual escuela",
        "cuál comunidad", "cual comunidad", "elige una comunidad", "elige una escuela",
    )
    if communities and any(k in t for k in community_pick_keys):
        add(*communities)
        return out

    # Only suggest when the AI is asking the user something,
    # otherwise chips would clutter every reply.
    # Allow imperative asks without "?" ("Pick one of the options above").
    imperative_ask = any(k in t for k in (
        "pick one", "choose one", "select one", "reply with", "tell me",
        "send a", "add a", "upload", "confirm", "say yes", "say done",
        "elige", "escoge", "responde con", "dime", "confirma",
    ))
    if "?" not in t and "¿" not in t and not imperative_ask:
        return []

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

    # Help / orientation menus — MUST run before food-pick chips.
    # "Which one would you like to try first?" used to match pick_food_keys
    # and offer Claim-style "1/2/3 / Something easy to prepare", which trapped
    # users in a phantom claim qty loop with no search results shown.
    help_menu_keys = (
        "try first", "would you like to try", "what can you do",
        "how does dogoods", "how does this work", "where do i start",
        "not sure", "don't know", "dont know", "i'm lost", "im lost",
        "qué puedo hacer", "como funciona", "cómo funciona", "por dónde empiezo",
    )
    if any(k in t for k in help_menu_keys):
        if es:
            add("Buscar comida gratis", "Compartir comida extra", "Solicitar comida")
        else:
            add("Find free food", "Share extra food", "Request food")
        return out

    # AI showed food options after a search — pick by number.
    # Require search-result cues so generic "which one would you like" menus
    # never get Claim # chips.
    search_result_cues = (
        "here's what's", "here are the", "near you", "close to you",
        "closest", "options near", "found ", "number below", "pick a number",
        "opciones cerca", "cerca de ti", "elige un número", "elige un numero",
    )
    pick_food_keys = (
        "which one would you like", "which one sounds good", "which number",
        "which would you like", "reply with the number", "pick one",
        "pick a number", "number below", "closest options", "here's what's close",
        "here are the closest", "here are the closest options", "options near you",
        "what's close", "whats close", "near you right now",
        "cuál te gustaría", "cual te gustaria", "cuál quieres", "cual quieres",
        "elige un número", "elige un numero", "opciones cerca", "número abajo",
    )
    if any(k in t for k in search_result_cues) and any(k in t for k in pick_food_keys):
        add("1", "2", "3")
        if es:
            add("El más cercano", "Algo fácil de preparar")
        else:
            add("The closest one", "Something easy to prepare")
        return out

    # Quantity step during claiming — offer tappable numbers (not donor posting).
    qty_keys = (
        "how many do you want", "how many would you like", "how many of the",
        "how many loaves", "how many units", "how many can you",
        "cuántos quieres", "cuántas quieres", "cuantos quieres", "cuantas quieres",
    )
    posting_context = any(k in t for k in (
        "share", "donate", "post", "publish", "listing", "donation",
        "compartir", "donar", "publicar", "donación",
    ))
    menu_qty_context = any(k in t for k in (
        "try first", "would you like to try", "what can you do",
    ))
    claim_qty_context = any(k in t for k in (
        "nice choice", "good pick", "great choice", "from that",
        "of those", "of the", "available",
        "claimed", "claim", "they have", "there are",
        "of it", "from this", "from the",
    ))
    if (
        not posting_context
        and not menu_qty_context
        and claim_qty_context
        and any(k in t for k in qty_keys)
    ):
        if es:
            add("1", "2", "3", "Todos")
        else:
            add("1", "2", "3", "All of them")
        return out

    # Homebound / mobility — when AI or user mentions trouble getting to pickup.
    combined = f"{t} {um}"
    if any(k in combined for k in (
            "can't walk", "cant walk", "homebound", "can't get there",
            "cant get there", "stuck at home", "no puedo caminar", "no puedo ir",
    )) and ("?" in t or "¿" in t):
        if es:
            add("No puedo ir — ¿hay entrega?", "El más cercano", "Buscar otra comida")
        else:
            add("I can't get there — any delivery?", "Show closest", "Search for other food")
        return out

    # User is correcting — offer common fix paths.
    if _is_correction_reply(user_message):
        if es:
            add("Cambiar cantidad", "Otro listado", "Cambiar dirección", "Cancelar")
        else:
            add("Change quantity", "Different listing", "Change address", "Cancel")
        return out

    # AI asked what to edit after "wait, edit it".
    edit_ask_keys = (
        "what should i change", "what would you like to change",
        "what do you want to change", "what needs to change",
        "qué debo cambiar", "que debo cambiar",
        "qué quieres cambiar", "que quieres cambiar",
        "qué corrijo", "que corrijo",
    )
    if any(k in t for k in edit_ask_keys):
        if es:
            add("La cantidad", "La dirección", "Otro alimento", "La comunidad")
        else:
            add("The quantity", "The address", "Different food", "The community")
        return out

    # Destructive action confirm — post, delete, bulk import.
    confirm_action_keys = (
        "just to confirm", "before i go ahead", "do you want me to",
        "tap confirm", "permanently delete",
        "antes de continuar", "acción pendiente",
    )
    if any(k in t for k in confirm_action_keys):
        if es:
            add("Sí, confirmar", "Espera, edítalo", "Cancelar")
        else:
            add("Yes, confirm", "Wait, edit it", "Cancel")
        return out

    # Community confirm — suggested school + "Different community".
    # Do not steal address confirms, look-right recaps, or "ready to post".
    community_confirm_keys = (
        "list under", "list this under", "which community", "which school",
        "school should", "community should", "go under",
        "post under", "post this under", "post this to", "post it to",
        "should this go under", "should it go under", "under which",
        "for the community", "community for",
        "your community", "use that one", "linked to", "profile is linked",
        "profile is connected", "profile is set",
        "comunidad", "escuela", "listar bajo", "bajo qué", "bajo que",
        "publicar bajo", "en qué comunidad", "en que comunidad", "bajo cuál",
    )
    address_turn = any(c in t for c in (
        "address", "street", "profile address", "what address", "which address",
        "pickup address", "dirección", "direccion", "calle",
    )) and not any(k in t for k in (
        "community", "school", "comunidad", "escuela", "list under",
        "warehouse",
    ))
    post_recap = any(k in t for k in (
        "ready to post", "ready to publish", "shall i post", "should i post",
        "look right", "looks right", "does this look", "does that look",
        "sound good to post", "go ahead and share",
    ))
    community_intent = any(k in t for k in community_confirm_keys) or (
        "listed under" in t
        and any(k in t for k in ("should", "shall", "want me", "would you"))
    )
    community_ask = (
        ("?" in text or "¿" in text)
        and community_intent
        and not address_turn
    )
    # Recap confirms that mention a school ("look right … under Alameda")
    # must not become community chips.
    if community_ask and post_recap and not any(k in t for k in (
        "your community", "which community", "which school", "list under",
        "list this under", "for the community", "linked to", "use that one",
        "community should", "post this to", "post it to", "post this under",
        "post under", "comunidad", "escuela",
    )):
        community_ask = False
    if community_ask and not is_post_success_response(text):
        from backend.agent.suggestion_chips import _extract_community_names_from_text
        named = [
            n for n in _extract_community_names_from_text(text)
            if n.lower() not in {"school district", "community", "your community"}
        ]
        # Prefer the school named in this reply over a stale profile default.
        pick = None
        if suggested_community and suggested_community.lower() in t:
            pick = suggested_community
        elif named:
            pick = named[0]
        if pick:
            if es:
                add(pick[:48], "Otra comunidad")
            else:
                add(pick[:48], "Different community")
            return out
        if communities:
            add(*communities[:4])
            return out
        # Extract a Proper Name after under / to / linked to.
        import re as _re
        m = _re.search(
            r"(?:linked to|connected to|use|under|to|—|-)\s*"
            r"([A-Z][A-Za-z0-9 &.'/-]{2,48}?)(?:\s+for\s+the\s+community)?(?:\s*\?|\s*$|[.!,])",
            text.strip(),
        )
        if m:
            name = m.group(1).strip(" —-?")
            if len(name) >= 3 and name.lower() not in {"the", "this", "that", "your"}:
                if es:
                    add(name[:48], "Otra comunidad")
                else:
                    add(name[:48], "Different community")
                return out
        if suggested_community:
            if es:
                add(suggested_community[:48], "Otra comunidad")
            else:
                add(suggested_community[:48], "Different community")
            return out
        if es:
            add("Usar la de mi perfil", "Otra comunidad")
        else:
            add("Use my profile community", "Different community")
        return out

    # Assistance mode fork — goal-aware (Find ≠ "Open the form").
    from backend.agent.suggestion_chips import share_assistance_fork_chips
    _fork = share_assistance_fork_chips(
        text, lang, user_message=user_message or "",
        assistance_reminder=assistance_reminder or "",
        guide_state=guide_state,
    )
    if _fork:
        for chip in _fork:
            label = chip.get("label") if isinstance(chip, dict) else str(chip or "")
            if label:
                add(label)
        return out

    # Multi-claim confirmation — before generic yes/no.
    if any(k in t for k in (
            "ready to claim", "claim these", "claim both", "claim all of these",
            "claim all",
            "listo para reclamar", "reclamar estos", "reclamar todos",
    )):
        if es:
            add("Sí, reclamar todos", "Cambiar cantidades", "Cancelar")
        else:
            add("Yes, claim these", "Change amounts", "Cancel")
        return out

    # Single-claim confirmation. Require a real claim verb — "sound good to post"
    # must never become claim chips.
    if any(k in t for k in (
            "shall i claim", "want me to claim", "claim this listing",
            "claim it for you", "claim this for you", "claim that listing",
            "claim #1", "claim #2", "claim #3",
            "reclamar este", "reclamarlo", "quieres que lo reclame",
    )) and any(k in t for k in ("claim", "reclamar")):
        if es:
            add("Sí, reclámalo", "No, gracias", "Cancelar")
        else:
            add("Yes, claim it", "No thanks", "Cancel")
        return out

    # Pick numbered search option (no tool results attached).
    if any(k in t for k in (
        "pick one of the options", "options above", "reply with 1", "choose 1",
        "1, 2, or 3", "1, 2 or 3", "number below", "which number",
        "elige un número", "elige un numero", "opciones de arriba",
    )):
        add("1", "2", "3")
        if es:
            add("El más cercano")
        else:
            add("The closest one")
        return out

    # Soft publish ask ("Say yes if you want me to publish")
    if any(k in t for k in (
        "say yes if", "want me to publish", "publish now", "post now",
        "greenlight", "go ahead and publish",
        "di que sí", "publicar ahora",
    )):
        if es:
            add("Sí, publícalo", "Espera, edítalo", "Cancelar")
        else:
            add("Yes, post it", "Wait, edit it", "Cancel")
        return out

    # User seems lost — offer the 3 main paths
    if any(k in t for k in (
            "what can you do", "how does dogoods", "how does this work",
            "what do i do", "not sure", "don't know", "dont know", "idk",
            "help me", "guide me", "walk me through", "where do i start",
            "i'm lost", "im lost", "no idea", "confused",
            "qué puedo hacer", "que puedo hacer", "cómo funciona", "como funciona",
            "qué hago", "que hago", "no sé qué", "no se que", "no estoy seguro",
    )):
        if es:
            add("Buscar comida gratis", "Compartir comida extra", "Solicitar comida")
        else:
            add("Find free food", "Share extra food", "Request food")
        return out

    # User wants to share but hasn't said what yet — and hasn't picked mode
    if any(k in t for k in (
            "share some food", "share food", "donate food", "post a listing",
            "give away food", "have extra food", "food to donate",
            "compartir comida", "donar comida", "publicar un listado",
            "tengo comida", "sobra comida",
    )) and not any(k in t for k in ("what food", "qué comida", "how much", "cuánto")):
        # Never offer food examples while asking the assistance-mode fork.
        from backend.agent.suggestion_chips import share_assistance_fork_chips
        fork = share_assistance_fork_chips(
            text, lang, user_message=user_message or "",
            guide_state=guide_state,
        )
        if fork:
            for chip in fork:
                label = chip.get("label") if isinstance(chip, dict) else str(chip or "")
                if label:
                    add(label)
            return out
        if es:
            add("5 manzanas", "Pan y huevos", "Verduras — 2 cajas", "Usa mi dirección guardada")
        else:
            add("5 apples", "Bread and eggs", "Vegetables — 2 boxes", "Use my saved address")
        return out

    # Address confirmation — BEFORE post-confirm so "does that look good?"
    # about a street address doesn't mis-fire as a publish prompt.
    address_cues = (
        "address", "street", " st ", " st.", " ave", "location", "pickup at",
        "dirección", "direccion", "calle", "main st", "your profile",
    )
    if any(c in t for c in address_cues) and any(k in t for k in (
            "profile address", "use your address", "different one", "what address",
            "does that look good", "does this look good", "look good to you",
            "look right", "right address", "correct address", "that address",
            "dirección de tu perfil", "dirección del perfil", "tu dirección guardada",
            "uso tu dirección", "uso la dirección", "qué dirección", "que direccion",
            "otra dirección", "distinta", "diferente",
    )):
        if es:
            add("Sí, usa esa", "Es otra dirección", "No tengo una guardada")
        else:
            add("Yes, use that one", "Use a different address", "I don't have one saved")
        return out

    # Final confirm: AI is asking the donor to greenlight posting.
    # Keep keys tight — bare "all set" / "looks good" match success copy
    # and re-opened loops after the listing was already posted.
    confirm_post_keys = (
        "post it", "post that", "post this", "post the listing", "post these",
        "publish it", "publish that", "publish this", "publish the listing",
        "should i post", "shall i post", "want me to post", "ok to post",
        "ready to post", "ready to publish", "go ahead and post",
        "good to post", "good to publish", "confirm and post",
        "shall i go ahead", "should i go ahead", "before i post",
        "look right", "looks right", "does this look", "does that look",
        "sound good to post", "sounds good to post",
        "go ahead and share",
        # Spanish
        "publicarlo", "publicar la", "publicar el", "publico la", "publico el",
        "lo publique", "que lo publique", "quieres que lo publique",
        "¿confirmas", "¿lo publico", "¿lo publicamos", "¿publicamos",
        "listo para publicar",
    )
    if any(k in t for k in confirm_post_keys) or (
        ("look good" in t or "looks good" in t or "sound good" in t or "sounds good" in t)
        and any(k in t for k in ("post", "publish", "listing"))
    ):
        photo_evidence = any(k in t for k in (
            "photos received", "got your photo", "with your photos",
            "with photo", "with a photo", "has a photo",
            "photo attached", "already have a photo", "image:",
            "foto adjunta", "fotos recibidas", "con tus fotos", "con su foto",
            "con foto", "con una foto",
        )) or "http" in t
        # Only nudge for a photo on the classic "Ready to post / Shall I post"
        # recap that never mentions one. Recap confirms ("look right",
        # "sound good to post", "share this") are Yes/Edit/Cancel.
        photo_nudge = (
            not photo_evidence
            and any(k in t for k in (
                "ready to post", "ready to publish",
                "shall i post", "should i post", "want me to post",
            ))
            and not any(k in t for k in (
                "look right", "looks right", "does this look", "does that look",
                "sound good", "sounds good",
                "go ahead and share",
            ))
        )
        if photo_nudge:
            if es:
                add("Adjuntar foto")
            else:
                add("Attach a photo")
            return out
        if es:
            add("Sí, publícalo", "Espera, edítalo", "Cancelar")
        else:
            add("Yes, post it", "Wait, edit it", "Cancel")
        return out

    # Handoff method (pickup vs drop-off). Skip WHEN questions and pure
    # address "where should people pick this up?" (those are location asks).
    is_when_question = any(
        k in t for k in ("when can", "what time", "cuándo", "cuando", "qué horario", "que horario")
    )
    is_where_address = any(k in t for k in (
        "where should", "what address", "which address", "pickup address",
        "dónde", "donde", "qué dirección", "que direccion",
    ))
    if is_where_address:
        if es:
            add("Usar mi dirección guardada", "Es otra dirección", "No tengo una")
        else:
            add("Use my saved address", "Use a different address", "I don't have one saved")
        return out
    if (not is_when_question) and any(
        k in t for k in ("pick this up", "pick it up", "drop it off", "drop-off", "drop off",
                         "deliver", "pickup or", "recoger", "entregar", "entrega")
    ):
        if es:
            add("Recogida en mi casa", "Yo lo entrego", "Cualquiera")
        else:
            add("Pickup at my place", "I'll drop it off", "Either works")
        if any(k in t for k in ("radius", "how far", "miles", "millas", "qué tan lejos")):
            if es:
                add("5 millas", "10 millas")
            else:
                add("Within 5 mi", "Within 10 mi")
        return out

    # Allergens (also handled early before ? gate)
    if _is_allergen_ask(t):
        if es:
            add("Sin alérgenos", "Solo gluten", "Lácteos", "Frutos secos")
        else:
            add("No allergens", "Just gluten", "Dairy", "Nuts")
        return out

    # Photo — required; never offer skip (also handled before ? gate).
    # A recap that merely mentions "with photo" is a post confirm, not a photo ask.
    if "photo" in t or "picture" in t or "foto" in t or "imagen" in t:
        photo_summary = any(k in t for k in (
            "photos received", "got your photo", "ready to post", "shall i post",
            "with photo", "with a photo", "look right", "looks right",
            "does this look", "sound good", "go ahead and share",
            "foto adjunta", "fotos recibidas", "lo publico", "lo publicamos",
            "listo para publicar", "publicarlo",
        ))
        photo_ask_now = any(k in t for k in (
            "required", "please", "need", "upload", "attach", "add a",
            "send a photo", "snap", "skip the photo", "without a photo",
            "without photo", "before i can post", "before posting",
        ))
        if photo_ask_now and not photo_summary:
            if es:
                add("Adjuntar foto")
            else:
                add("Attach a photo")
            return out

    # Pickup window / when
    if any(k in t for k in ("when can", "pick them up", "pickup window", "what time",
                            "cuándo pueden", "cuando pueden", "qué horario", "que horario")):
        if es:
            add("Hoy 5–8pm", "Mañana", "Próximas 24h", "Cuando sea")
        else:
            add("Today 5–8pm", "Tomorrow morning", "Next 24h", "Whenever")
        return out

    # Freshness / good-until — only when actively asking, never on ack + allergen.
    if _is_expiry_ask(t):
        if es:
            add("Mañana", "En 2 días", "En 3 días", "En un mes")
        else:
            add("Tomorrow", "In 2 days", "In 3 days", "In a month")
        return out

    # Combined food + qty (hands-on "Do it for me") — before bare qty.
    # "What food do you want to share, and how much?" must NOT become 1/3/5/10.
    if _is_combined_food_qty_ask(t):
        if es:
            add("5 manzanas", "2 panes", "Verduras — 1 caja", "Huevos — 1 docena")
        else:
            add("5 apples", "2 loaves of bread", "Vegetables — 1 box", "Eggs — 1 dozen")
        return out

    # Quantity prompt ("how many", "three what?") — after food is known
    if any(k in t for k in ("how many", "how much", "what unit", "three what",
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
            "what do you have", "tell me what you have", "tell me what you've got",
            "what kind of food", "food name", "tell me the food",
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

    # ---- Fallbacks --------------------------------------------------

    # Open-ended wh-question with no specific branch above: don't guess.
    # Empty chips > wrong chips.
    if open_ended:
        return out

    # Delete confirmation
    if any(k in t for k in (
            "permanently delete", "delete this listing", "delete listing",
            "cannot be undone", "eliminar permanentemente", "borrar permanentemente",
            "no se puede deshacer",
    )):
        if es:
            add("Sí, eliminar", "Cancelar")
        else:
            add("Yes, delete it", "Cancel")
        return out

    # Reminders — narrow binary (not the old catch-all Yes/No).
    if any(k in t for k in ("remind you", "remind me", "recuerde", "recordarte", "recordarme")):
        if es:
            add("Sí, recuérdame", "No, gracias")
        else:
            add("Yes, remind me", "No thanks")
        return out

    # True binary confirms only — NEVER use Yes/No for "would you like / want me to"
    # (those steal claim/post/fork/food turns when the model rephrases).
    binary_cues = (
        "is that correct", "is that right", "is that ok", "is that okay",
        "does that work", "does that sound right", "yes or no",
        "¿es correcto", "¿está bien", "está bien así", "¿te parece bien",
    )
    food_flow = any(k in t for k in (
        "share", "sharing", "claim", "post", "publish", "food", "listing",
        "find", "search", "guide", "form", "photo", "community", "school",
        "donate", "request", "pickup", "address", "allergen",
        "compartir", "reclamar", "publicar", "comida", "buscar", "foto",
    ))
    if (not food_flow) and any(k in t for k in binary_cues):
        if es:
            add("Sí", "No")
        else:
            add("Yes", "No")
        return out

    # Prefer empty over generic Yes/No/Later — wrong chips are worse than none.
    return out


conversation_engine = ConversationEngine()

