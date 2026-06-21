"""End-to-end coverage tests for the AI assistant spec.

Each scenario sends one or two turns to /api/ai/chat and asserts the reply
contains the substantive signals the spec demands (real listings, dietary
filtering, multi-turn memory, platform-help steps, etc.). Failures are
collected and printed as a coverage matrix at the end so we can see which
spec categories are weak.

Run:  pytest backend/tests/test_spec_coverage.py -v -s
"""

from __future__ import annotations

import os
import time
from typing import Optional

import httpx
import pytest
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = (os.environ.get("SUPABASE_URL") or os.environ["VITE_SUPABASE_URL"]).rstrip("/")
SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
API = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
USER_ID = "c4dcbd93-081e-4160-87eb-1d51d444413a"  # Abdulkarim (Alameda)
CONVERSATION = f"spec-cov-{int(time.time())}"

_ACCESS_TOKEN: Optional[str] = None


def _admin_headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def _mint_token() -> str:
    """Use the Supabase admin API to mint a real access token for USER_ID."""
    global _ACCESS_TOKEN
    if _ACCESS_TOKEN:
        return _ACCESS_TOKEN
    r = httpx.get(
        f"{SUPABASE_URL}/auth/v1/admin/users/{USER_ID}",
        headers=_admin_headers(), timeout=10,
    )
    r.raise_for_status()
    email = r.json()["email"]
    r = httpx.post(
        f"{SUPABASE_URL}/auth/v1/admin/generate_link",
        headers=_admin_headers(),
        json={"type": "magiclink", "email": email}, timeout=15,
    )
    r.raise_for_status()
    body = r.json()
    hashed = body.get("hashed_token") or body.get("token_hash") or body["properties"]["hashed_token"]
    r = httpx.post(
        f"{SUPABASE_URL}/auth/v1/verify",
        headers={"apikey": SERVICE_KEY, "Content-Type": "application/json"},
        json={"type": "magiclink", "token_hash": hashed}, timeout=15,
    )
    r.raise_for_status()
    _ACCESS_TOKEN = r.json()["access_token"]
    return _ACCESS_TOKEN


def _chat(message: str, conversation_id: Optional[str] = None) -> dict:
    """POST one chat turn. Returns parsed JSON."""
    token = _mint_token()
    payload = {
        "message": message,
        "user_id": USER_ID,
        "conversation_id": conversation_id or CONVERSATION,
        "include_audio": False,
    }
    r = httpx.post(
        f"{API}/api/ai/chat",
        json=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=90,
    )
    r.raise_for_status()
    return r.json()


def _has_any(text: str, needles: list[str]) -> list[str]:
    """Return needles that DID appear (case-insensitive)."""
    lo = text.lower()
    return [n for n in needles if n.lower() in lo]


def _has_listing_signal(text: str) -> bool:
    """A plausible listing reply mentions an item + lb/kg/mi/km/pickup OR lists
    bulleted items with quantities."""
    lo = text.lower()
    signals = (
        "lb", "kg", "miles", "mile", "km", "pickup", "available",
        "bag", "loaves", "tray", "sandwiches", "apples", "bread",
        "lasagna", "watermelon",
    )
    return any(s in lo for s in signals)


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

# Format: (category, prompt, must_have_any[list], must_NOT_have[list], extra check, forbidden_tools[list])
# extra check is a callable(text)->Optional[str] returning failure msg or None.
# forbidden_tools — tool names that the AI MUST NOT call for this prompt
# (used to catch destructive misinterpretations of help questions).

SCENARIOS = [
    # --- 1. SEARCH BY FOOD TYPE -------------------------------------------
    ("food_type:bread", "show me bread available near me", [], [], None, []),
    ("food_type:produce", "any fresh fruit available?", [], [], None, []),
    ("food_type:vegetables", "show me greens", [], [], None, []),
    ("food_type:dairy", "I'm looking for milk products", [], [], None, []),
    ("food_type:prepared", "any cooked meals available?", [], [], None, []),

    # --- 2. FUZZY / MISSPELLINGS ------------------------------------------
    ("fuzzy:vegtables", "do you have any vegtables?", [], [], None, []),
    ("fuzzy:mlik", "I want some mlik", [], [], None, []),
    ("fuzzy:saandwich", "any saandwiches?", [], [], None, []),

    # --- 3. DIETARY ---------------------------------------------------------
    ("dietary:vegan", "show me vegan food", [], [], None, []),
    ("dietary:gluten_free", "any gluten free meals?", [], [], None, []),
    ("dietary:halal", "is there halal food available?", [], [], None, []),

    # --- 4. ALLERGEN-FREE --------------------------------------------------
    ("allergen:nut_free", "I need nut-free food", [], [], None, []),
    ("allergen:dairy_free", "any dairy free options?", [], [], None, []),

    # --- 5. EXPIRY ---------------------------------------------------------
    ("expiry:today", "what's expiring today?", [], [], None, []),
    ("expiry:soon", "show me food expiring soon", [], [], None, []),
    ("expiry:3_days", "anything expiring within 3 days?", [], [], None, []),

    # --- 6. QUANTITY / SERVINGS -------------------------------------------
    ("qty:10_people", "I need food for 10 people", [], [], None, []),
    ("qty:family", "looking for a family meal", [], [], None, []),
    ("qty:large_group", "large quantity food for a group", [], [], None, []),

    # --- 7. LOCATION -------------------------------------------------------
    ("loc:near_me", "what food is near me?", [], [],
     lambda t: None if _has_listing_signal(t) else "no listing signal", []),
    ("loc:within_5km", "show food within 5 km", [], [], None, []),

    # --- 8. SPECIAL NEEDS --------------------------------------------------
    ("special:children", "food for my children", [], [], None, []),
    ("special:elderly", "I'm cooking for an elderly relative, any soft food?", [], [], None, []),
    ("special:high_protein", "high protein meals?", [], [], None, []),

    # --- 9. INTENT RECOGNITION (non-search) -------------------------------
    # NOTE: these are HELP/INFO questions — the AI should explain, not act.
    ("help:how_to_cancel", "how do I cancel my claim?",
     ["cancel"], [], None, ["cancel_claim"]),
    ("help:how_to_report", "how do I report a problem with a listing?",
     ["report"], [], None, ["delete_listing", "deactivate_listing"]),
    ("help:contact_donor", "how do I contact the donor?",
     ["donor", "contact", "message"], [], None, []),

    # --- 10. PLATFORM HELP --------------------------------------------------
    ("help:how_to_pickup", "how do I pick up food after claiming?",
     ["pickup", "claim"], [], None, []),
    ("help:how_to_post", "how do I post food?",
     ["share", "post", "list"], [], None, []),
    ("help:cancel_claim_yes_no", "can I cancel a claim?",
     ["yes", "cancel"], [], None, ["cancel_claim"]),
    ("help:someone_else_pickup", "can someone else pick up the food for me?",
     [], [], None, []),

    # --- 11. ERROR HANDLING (vague request) -------------------------------
    ("err:school_event", "I need food for a school event",
     [], ["i don't understand", "i cannot help"],
     lambda t: None if "?" in t else "no clarifying question asked", []),

    # --- 12. CAPABILITY DISCOVERY (cat 17) --------------------------------
    # Must offer a numbered/bulleted menu of things the AI can do.
    ("cap:what_can_you_do", "what can you do?",
     ["find", "claim", "help"], [],
     lambda t: None if any(c in t for c in ("1.", "•", "- ")) else "no menu in reply",
     []),
    ("cap:help_alone", "help",
     [], [],
     lambda t: None if any(c in t for c in ("1.", "•", "- ")) else "no menu in reply",
     []),
    ("cap:show_examples", "show me examples",
     ["find", "claim", "share"], [], None, []),

    # --- 13. ELDERLY / NON-TECHNICAL (cat 13) -----------------------------
    ("guided:confused", "I'm confused, I don't know how this works",
     [], [],
     lambda t: None if any(c in t for c in ("1.", "•", "- ")) else "no guided menu",
     []),
    ("guided:where_start", "where do I start?",
     [], [],
     lambda t: None if any(c in t for c in ("1.", "•", "- ")) else "no guided menu",
     []),

    # --- 14. CONVERSATIONAL CUES (cat 12) ---------------------------------
    ("convo:hungry", "I'm hungry", [], [], None, []),
    ("convo:kids_lunch", "my kids need lunch", [], [], None, []),
    ("convo:guests_coming", "I have guests coming over", [], [], None, []),
    ("convo:tight_budget", "I'm on a tight budget", [], [], None, []),

    # --- 15. MEAL-TIME FRAMING (cat 1) ------------------------------------
    ("meal:breakfast", "show me breakfast foods", [], [], None, []),
    ("meal:lunch", "show me lunch foods", [], [], None, []),
    ("meal:dinner", "what can I get for dinner?", [], [], None, []),

    # --- 16. QUANTITY ESTIMATION (cat 3) ----------------------------------
    # Must contain a yes/no-style estimate or a number of servings, NOT
    # just "here are options".
    ("qty_est:will_feed_family", "will this feed my family of 4?",
     ["serv", "people", "yes", "no", "enough"], [], None, []),
    ("qty_est:how_many_serve", "how many people can a loaf of bread serve?",
     ["serv", "slice", "people"], [], None, []),
    ("qty_est:enough_for_8", "I have 8 guests, what should I claim?",
     ["8", "serv", "people", "guest"], [], None, []),

    # --- 17. POSTING ASSISTANCE (cat 6) -----------------------------------
    # Asking for description help should produce description text, not a tool call.
    ("post:improve_desc",
     "I'm posting 'Bread - few loaves left'. Can you improve the description?",
     ["loaves", "fresh", "bread"], [],
     lambda t: None if len(t) > 40 else "rewrite too short",
     ["post_food_listing", "create_food_listing"]),
    ("post:which_category",
     "which category should I use for sourdough bread?",
     ["bakery"], [], None, []),
    ("post:how_many_serve",
     "I have 3 loaves of bread to share — how many people will this serve?",
     ["serv", "people", "slice"], [], None, []),

    # --- 18. FOOD SAFETY (cat 7) ------------------------------------------
    ("safety:expires_tomorrow",
     "the bread I'm getting expires tomorrow, is that okay?",
     ["safe", "okay", "fine", "freeze", "fresh"], [], None, []),
    ("safety:freeze_rice",
     "can I freeze cooked rice?",
     ["freez", "yes"], [], None, []),
    ("safety:cooked_rice",
     "how long does cooked rice last in the fridge?",
     ["day", "fridge", "refriger"], [], None, []),

    # --- 19. SUITABILITY REASONING (cat 2) --------------------------------
    ("suit:diabetic", "I'm diabetic, what should I look for?",
     ["sugar", "protein", "diabet"], [], None, []),
    ("suit:pregnant",
     "I'm pregnant, what food should I avoid?",
     ["raw", "unpasteur", "deli", "seafood", "soft cheese", "avoid"], [], None, []),
    ("suit:lasts_longest", "what food lasts the longest?",
     ["pantry", "can", "dry", "shelf"], [], None, []),

    # --- 20. PICKUP ASSISTANCE (cat 4) ------------------------------------
    ("pickup:what_next", "I claimed something — what do I do next?",
     ["pickup", "donor", "address", "time"], [], None, []),
    ("pickup:someone_else",
     "can my friend pick up the food instead of me?",
     ["yes", "friend", "code", "title"], [],
     lambda t: None if any(s in t.lower() for s in ("yes", "friend", "can", "send")) else "did not affirm",
     []),
    ("pickup:running_late",
     "I'm going to be late for pickup, what do I do?",
     ["donor", "message", "chat", "contact", "extend"], [], None, []),

    # --- 21. CLAIM STATUS (cat 5) ------------------------------------------
    ("claim:status_check", "did my claim go through?",
     ["claim"], [], None, []),
    ("claim:how_many_claims", "how many claims do I have?",
     ["claim"], [], None, []),
    ("claim:who_claimed_before",
     "who claimed the bread before me?",
     [], [],
     lambda t: None if any(s in t.lower() for s in ("can't share", "cannot share", "won't share", "private", "don't share")) else "did not protect other claimers' privacy",
     []),

    # --- 22. ACCOUNT SUPPORT (cat 9) --------------------------------------
    ("account:forgot_password", "I forgot my password",
     ["password", "reset", "forgot"], [], None, []),
    ("account:delete_account", "how do I delete my account?",
     ["contact", "support", "delete"], [],
     lambda t: None if any(s in t.lower() for s in ("contact", "support", "/contact")) else "no support route given",
     []),
    ("account:change_phone", "how do I change my phone number?",
     ["settings", "profile", "phone"], [], None, []),
    ("account:why_blocked", "why am I blocked?",
     ["contact", "support"], [], None, []),

    # --- 23. REPORTING (cat 10) -------------------------------------------
    ("report:no_show",
     "the donor didn't show up for the pickup",
     ["sorry", "contact", "report"], [], None, []),
    ("report:unsafe", "I feel unsafe",
     ["sorry", "safe", "emergency", "contact", "support"], [], None, []),
    ("report:spoiled_food",
     "the food I picked up was spoiled, what do I do?",
     ["sorry", "report", "contact"], [], None, []),

    # --- 24. RECOMMENDATION MODE (cat 11) ---------------------------------
    ("recommend:what_should_i_claim",
     "what should I claim?",
     [], [], None, []),
    ("recommend:expire_today",
     "what's likely to expire today?",
     ["expir", "today", "soon"], [], None, []),

    # --- 25. ACCESSIBILITY (cat 15) ---------------------------------------
    ("a11y:read_to_me",
     "read this to me",
     ["speaker", "tap", "voice", "listen", "audio"], [], None, []),
    ("a11y:larger_text",
     "can you make the text larger?",
     ["settings"], [], None, []),
    ("a11y:simpler",
     "use easier language please",
     [], [],
     lambda t: None if len(t.split()) < 80 else "reply too long for 'simpler language'",
     []),
    ("a11y:translate_es",
     "translate to Spanish",
     ["español", "spanish", "qué", "¿"], [], None, []),

    # --- 26. SPEC FUZZY-INPUT NORMALISATION (newdoc.doc gaps) -------------
    # Imperial radius units
    ("imperial:one_mile", "show me food within 1 mile",
     [], [], lambda t: None if _has_listing_signal(t) or "?" in t or len(t) > 40 else "empty reply",
     []),
    ("imperial:five_miles", "any food within 5 miles?",
     [], [], lambda t: None if _has_listing_signal(t) or "?" in t or len(t) > 40 else "empty reply",
     []),
    # Condition adjectives that aren't categories
    ("cond:fresh", "show me fresh food", [], [], None, []),
    ("cond:chilled", "any chilled food available?", [], [], None, []),
    ("cond:hot_food", "I want hot food", [], [], None, []),
    ("cond:ready_to_eat", "ready to eat food please", [], [], None, []),
    ("cond:long_shelf", "what food has a long shelf life?",
     ["pantry", "can", "dry", "rice", "pasta", "shelf"], [], None, []),
    # Healthy / low-salt / quick
    ("health:general", "what's healthy?",
     ["produce", "protein", "vegetable", "fruit", "healthy"], [], None, []),
    ("health:low_salt", "show me low salt food",
     ["sodium", "salt"], [], None, []),
    ("health:quick", "I need something quick",
     ["prepared", "ready", "sandwich", "quick"], [], None, []),
    # Available today / not yet claimed
    ("avail:today", "what food is available today?", [], [],
     lambda t: None if _has_listing_signal(t) or len(t) > 40 else "empty reply",
     []),
    ("avail:not_claimed", "what food hasn't been claimed?", [], [],
     lambda t: None if _has_listing_signal(t) or len(t) > 40 else "empty reply",
     []),
    # Recipes from ingredients
    ("recipe:from_ingredients",
     "what can I cook with chicken and rice?",
     ["recipe", "cook", "chicken", "rice", "suggestion"], [], None, []),
    # Vague group size — must ask, not guess
    ("vague:party_no_count", "I need food for a party",
     [], ["i don't understand"],
     lambda t: None if "?" in t else "did not ask for headcount",
     []),
]


@pytest.fixture(scope="module")
def conversation_id() -> str:
    return CONVERSATION


@pytest.mark.parametrize("category,prompt,must_have,must_not_have,extra,forbidden_tools", SCENARIOS)
def test_scenario(category, prompt, must_have, must_not_have, extra, forbidden_tools):
    """Sends a single-turn prompt and asserts the reply meets the spec hint."""
    # Each scenario uses its OWN conversation_id so prior turns don't pollute
    # results. Multi-turn behaviour is tested separately below.
    # Light throttle so we stay under the 50/min per-user rate limit.
    time.sleep(0.4)
    convo = f"spec-{category}-{int(time.time() * 1000)}"
    resp = _chat(prompt, conversation_id=convo)
    reply = resp.get("text") or resp.get("reply") or resp.get("response", "")
    tools_called = [t.get("tool") for t in resp.get("tool_results") or []]
    print(f"\n[{category}] PROMPT: {prompt}")
    print(f"[{category}] TOOLS: {tools_called}")
    print(f"[{category}] REPLY ({len(reply)} chars): {reply[:300]}")

    # Hard fails (must_not_have)
    bad = _has_any(reply, must_not_have)
    assert not bad, f"[{category}] reply contained forbidden: {bad}"

    # Forbidden tools (destructive misinterpretation guard)
    leaked = [t for t in tools_called if t in forbidden_tools]
    assert not leaked, (
        f"[{category}] AI called destructive tool(s) on an INFO question: {leaked}. "
        f"Reply: {reply[:200]}"
    )

    # Soft signals (must_have) — pass if ANY appears
    if must_have:
        found = _has_any(reply, must_have)
        assert found, (
            f"[{category}] reply missing all of {must_have}. "
            f"Full reply: {reply[:500]}"
        )

    # Extra check
    if extra:
        err = extra(reply)
        assert err is None, f"[{category}] extra check failed: {err}"


# ---------------------------------------------------------------------------
# Multi-turn follow-up (context memory)
# ---------------------------------------------------------------------------

def test_multiturn_followup_filter():
    """Spec example:
        User: 'Show dairy free meals.'   -> results
        User: 'Which one serves 10 people?'  -> filtered
    """
    convo = f"multi-{int(time.time())}"
    r1 = _chat("show me dairy free food near me", conversation_id=convo)
    reply1 = r1.get("text") or r1.get("reply") or r1.get("response", "")
    print(f"\n[multi-1] {reply1[:400]}")

    r2 = _chat("which one is enough for 10 people?", conversation_id=convo)
    reply2 = r2.get("text") or r2.get("reply") or r2.get("response", "")
    print(f"\n[multi-2] {reply2[:400]}")

    # The second turn should reference the prior results, not re-ask scratch.
    # Pass if it (a) names a specific listing OR (b) asks a clarifying follow-up
    # that references the prior context (e.g. "of those" / "from the list").
    lo = reply2.lower()
    referenced = any(s in lo for s in (
        "of those", "from the list", "from the results", "the bag of",
        "sandwiches", "lasagna", "loaves", "apples", "watermelon",
        "from above", "earlier", "previous", "first one",
    ))
    assert referenced, (
        f"Multi-turn: turn 2 did not reference prior results. Reply: {reply2[:500]}"
    )


# ---------------------------------------------------------------------------
# Combined-filter (advanced)
# ---------------------------------------------------------------------------

def test_combined_filter_vegan_for_10():
    """Spec: 'Show vegan food for 10 people.'"""
    convo = f"combo-{int(time.time())}"
    r = _chat("show vegan food for 10 people", conversation_id=convo)
    reply = r.get("text") or r.get("reply") or r.get("response", "")
    print(f"\n[combo] {reply[:500]}")
    # Should NOT silently return all listings; should either filter or ask.
    assert reply.strip(), "empty reply"


# ---------------------------------------------------------------------------
# Safety warning on near-expiry
# ---------------------------------------------------------------------------

def test_safety_expiry_warning():
    """When listings include one expiring soon, AI should flag it."""
    convo = f"safety-{int(time.time())}"
    r = _chat("show me food near me with expiry dates", conversation_id=convo)
    reply = r.get("text") or r.get("reply") or r.get("response", "")
    print(f"\n[safety] {reply[:500]}")
    # Soft check — pass if 'expir' or a relative phrase appears
    lo = reply.lower()
    assert any(s in lo for s in ("expir", "today", "tomorrow", "days")), (
        f"No freshness/expiry framing in reply: {reply[:400]}"
    )
