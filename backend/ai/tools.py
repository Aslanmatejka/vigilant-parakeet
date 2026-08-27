"""
DoGoods AI (Nouri) tools — MySQL edition.

OpenAI function-calling tool definitions and handlers.
All data operations go through SQLAlchemy against the main MySQL database.
"""
from __future__ import annotations


import asyncio
import json
import logging
import math
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from backend.aws_secrets import load_aws_secrets

# Pull secrets (e.g. MAPBOX_TOKEN) from AWS Secrets Manager into the
# process env BEFORE we read module-level config below. In production the
# secret name comes from the AWS_SECRET_NAME env var (set in the systemd
# unit, e.g. "prod/env"); in tests/dev it's a no-op when unset.
load_aws_secrets()

logger = logging.getLogger("ai_tools")


def _utcnow() -> datetime:
    """Return the current UTC time as a naive ``datetime`` (no tzinfo).

    ``_utcnow()`` is deprecated in Python 3.12+, but the DB
    columns we compare against are still stored as naive UTC — mixing
    naive/aware datetimes would raise on every comparison. This helper
    keeps the SAME semantics (naive UTC) while silencing the warning
    globally in one place.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


MAPBOX_TOKEN = os.getenv("MAPBOX_TOKEN") or os.getenv("VITE_MAPBOX_TOKEN", "")
MAPBOX_DIRECTIONS_URL = "https://api.mapbox.com/directions/v5/mapbox"
MAPBOX_GEOCODE_URL = "https://api.mapbox.com/geocoding/v5/mapbox.places/{}.json"


def _geocode_address(address: str) -> Optional[tuple]:
    """Best-effort forward-geocode of an address via Mapbox.

    Returns ``(lat, lng)`` on success, ``None`` if no token, no match, or
    on any error. Used to make sure AI-posted listings show up on the map
    instead of only in the sidebar list. Filters out low-relevance hits
    (country / region centroids) so a vague string like 'Alameda' doesn't
    drop a listing in the middle of the wrong area.
    """
    addr = (address or "").strip()
    if not addr or not MAPBOX_TOKEN:
        return None
    try:
        from urllib.parse import quote as urlquote
        url = MAPBOX_GEOCODE_URL.format(urlquote(addr))
        # Two attempts; transient mapbox errors shouldn't permanently fail
        # a listing post.
        last_exc = None
        for attempt in range(2):
            try:
                with httpx.Client(timeout=10.0) as client:
                    resp = client.get(url, params={"access_token": MAPBOX_TOKEN, "limit": 1})
                if resp.status_code != 200:
                    continue
                features = (resp.json() or {}).get("features") or []
                if not features:
                    return None
                feat = features[0]
                # Reject very low-relevance matches and country/region
                # centroids — those are useless on a delivery map.
                relevance = float(feat.get("relevance") or 0)
                place_types = set(feat.get("place_type") or [])
                if relevance < 0.5:
                    return None
                if place_types and place_types.issubset({"country", "region"}):
                    return None
                center = feat.get("center")
                if not center or len(center) < 2:
                    return None
                # Mapbox returns [lng, lat]
                return float(center[1]), float(center[0])
            except Exception as exc:
                last_exc = exc
                continue
        if last_exc is not None:
            logger.warning("Geocode failed for %r: %s", addr, last_exc)
        return None
    except Exception as exc:
        logger.warning("Geocode failed for %r: %s", addr, exc)
        return None


# ---------------------------------------------------------------------------
# OpenAI function-calling tool schemas
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_food_near_user",
            "description": (
                "Search available food listings for the user. Uses their saved "
                "profile address (NOT live GPS). Always pass user_id. "
                "Returns every listing in the user's school community — never "
                "other schools (warehouse food only if the user belongs to "
                "warehouse). No radius "
                "cutoff; distance is only for sorting when coords exist. "
                "Never returns the caller's own donations — use get_user_listings "
                "for those. Use dietary_tags / exclude_allergens only when the "
                "user stated diet needs. Do NOT ask the user to enable GPS or "
                "share location."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "User UUID"},
                    "food_type": {
                        "type": "string",
                        "description": (
                            "Optional DB category: produce, dairy, bakery, pantry, "
                            "meat, seafood, frozen, snacks, beverages, prepared"
                        ),
                    },
                    "dietary_tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Dietary tags the listing must include (vegan, halal, etc.)",
                    },
                    "exclude_allergens": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Allergens to exclude (nuts, dairy, gluten, etc.)",
                    },
                    "min_quantity": {
                        "type": "number",
                        "description": "Minimum listing quantity for large households",
                    },
                    "title_query": {
                        "type": "string",
                        "description": (
                            "Optional food name filter. For ONE food: 'carrots'. "
                            "For MULTIPLE foods the user asked for (e.g. pawpaw AND "
                            "carrots), pass ALL of them comma-separated: "
                            "'pawpaw, carrots' — the server OR-matches so both "
                            "appear when available. Never pass only the first food."
                        ),
                    },
                    "max_results": {
                        "type": "integer",
                        "default": 25,
                        "description": "Max listings to return (default 25, capped at 25).",
                    },
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_listings",
            "description": (
                "Newest food listings posted recently. Always pass user_id. "
                "Scoped to the user's school community only — "
                "never other schools. Own donations are excluded."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "User UUID"},
                    "hours": {
                        "type": "integer",
                        "description": "How far back to look (default 72).",
                        "default": 72,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max listings to return (default 10).",
                        "default": 10,
                    },
                    "category": {
                        "type": "string",
                        "description": "Optional category filter.",
                    },
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_community_listings",
            "description": (
                "Active donations for a specific community_id. Always pass "
                "user_id. Callers may only query their own community — "
                "other schools (including warehouse for non-members) return empty."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "User UUID"},
                    "community_id": {
                        "type": "string",
                        "description": "Community id (must be the caller's own community).",
                    },
                    "category": {"type": "string"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["user_id", "community_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_profile",
            "description": "Retrieve a user's profile, dietary info, and activity summary.",
            "parameters": {
                "type": "object",
                "properties": {"user_id": {"type": "string"}},
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_pickup_schedule",
            "description": "Get upcoming pickups (claimed food) and distribution center events for a user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "include_community_events": {"type": "boolean", "default": True},
                    "days_ahead": {"type": "integer", "default": 7},
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_ai_reminder",
            "description": "Schedule a reminder (pickup, expiry, event, or general) for a user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "message": {"type": "string"},
                    "trigger_time": {"type": "string", "description": "ISO 8601 datetime"},
                    "reminder_type": {
                        "type": "string",
                        "enum": ["pickup", "listing_expiry", "distribution_event", "general"],
                        "default": "general",
                    },
                    "related_id": {"type": "integer"},
                },
                "required": ["user_id", "message", "trigger_time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_mapbox_route",
            "description": "Get driving/walking/cycling directions between two points.",
            "parameters": {
                "type": "object",
                "properties": {
                    "origin_lng": {"type": "number"},
                    "origin_lat": {"type": "number"},
                    "dest_lng": {"type": "number"},
                    "dest_lat": {"type": "number"},
                    "profile": {"type": "string", "enum": ["driving", "walking", "cycling"], "default": "driving"},
                },
                "required": ["origin_lng", "origin_lat", "dest_lng", "dest_lat"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_distribution_centers",
            "description": "List active distribution centers (community food hubs).",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_results": {"type": "integer", "default": 10},
                    "user_id": {"type": "string", "description": "Optional: sort by proximity"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_dashboard",
            "description": "Rich dashboard: profile, active listings, claimed food, reminders, impact.",
            "parameters": {
                "type": "object",
                "properties": {"user_id": {"type": "string"}},
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_pickup_schedule",
            "description": "Check pending reminders and scheduled pickups, organized by type.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "include_sent": {"type": "boolean", "default": False},
                    "days_ahead": {"type": "integer", "default": 14},
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recipes",
            "description": "Suggest recipes from given ingredients or a user's claimed food. Household-aware: pulls household_size / dietary_restrictions / allergies from the user's profile when user_id is supplied. Set low_resource=true for minimal-equipment recipes (stovetop/one-pot, no oven).",
            "parameters": {
                "type": "object",
                "properties": {
                    "ingredients": {"type": "array", "items": {"type": "string"}},
                    "user_id": {"type": "string"},
                    "dietary_preferences": {"type": "string"},
                    "household_size": {"type": "integer"},
                    "low_resource": {"type": "boolean", "default": False},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_storage_tips",
            "description": "Storage/preservation tips for specific food items or a user's claimed food.",
            "parameters": {
                "type": "object",
                "properties": {
                    "food_items": {"type": "array", "items": {"type": "string"}},
                    "user_id": {"type": "string"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_donor_expiring_listings",
            "description": "DONOR ROLE: the user's own food listings expiring within the next N hours — use to remind a donor to act before food goes to waste.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "hours_ahead": {"type": "integer", "default": 48},
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_driver_route_plan",
            "description": "VOLUNTEER/DRIVER ROLE: ordered optimised list of the user's currently-claimed pickups (nearest-neighbour from user location).",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "max_stops": {"type": "integer", "default": 8},
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_dispatch_queue",
            "description": "DISPATCHER ROLE: open food requests and unclaimed listings that need matching/assignment.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "max_items": {"type": "integer", "default": 20},
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_platform_stats",
            "description": "ADMIN ROLE: platform health metrics (members, listings, exchanges) — use for dashboards and encouragement messages.",
            "parameters": {
                "type": "object",
                "properties": {"user_id": {"type": "string"}},
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_profile_gaps",
            "description": "Return role-relevant profile fields the user has not yet filled (e.g., dietary needs, address, SMS consent). Use to politely prompt the user to complete their profile.",
            "parameters": {
                "type": "object",
                "properties": {"user_id": {"type": "string"}},
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "optimize_pickup_route",
            "description": "Smart multi-stop route optimisation for a volunteer/driver. Uses nearest-neighbour over backend data, upgraded with the Mapbox Optimization API when available. Returns ordered stops plus a frontend_hint payload the RouteOptimizer component can consume.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "origin_lat": {"type": "number"},
                    "origin_lng": {"type": "number"},
                    "listing_ids": {"type": "array", "items": {"type": "integer"}},
                    "profile": {"type": "string", "enum": ["driving", "walking", "cycling"], "default": "driving"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_safe_query",
            "description": "Translate a natural-language question into a bounded, read-only SQL SELECT against a whitelisted table (listings / requests / centers / users). Build filters as [{field, op, value}] where op is one of eq/ne/gt/gte/lt/lte/in/like. No free-form SQL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity": {"type": "string", "enum": ["listings", "requests", "centers", "users"]},
                    "filters": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field": {"type": "string"},
                                "op": {"type": "string", "enum": ["eq", "ne", "gt", "gte", "lt", "lte", "in", "like"]},
                                "value": {},
                            },
                            "required": ["field", "op", "value"],
                        },
                    },
                    "order_by": {"type": "string"},
                    "descending": {"type": "boolean", "default": True},
                    "limit": {"type": "integer", "default": 25},
                },
                "required": ["entity"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "claim_listing",
            "description": (
                "Claim a SPECIFIC available food listing for the current user. "
                "Call this whenever the user picks a listing — by name or by the "
                "numbered position from search results. "
                "IMPORTANT: listing_id must be the UUID from search results "
                "(each result includes id: …). If you only have the display "
                "number (1, 2, 3…), pass that integer — the server resolves it "
                "from the last search_food_near_user result. "
                "Always pass quantity (how many the user wants from THAT listing). "
                "Ask how many before calling unless clearly 1 unit or they said "
                "'all' / 'everything'. Omit quantity only when they clearly want "
                "the full stock (defaults to all available). "
                "NEVER pass the display number as if it were the database id without "
                "a prior search in this conversation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "listing_id": {
                        "description": (
                            "UUID from search results, OR display index 1-N "
                            "from the numbered list (resolved server-side)."
                        ),
                    },
                    "quantity": {
                        "description": (
                            "How many units to claim (integer), or 'all' for full "
                            "stock. Available qty is the hard ceiling. Explicit "
                            "numbers above 50 need user confirmation — do not invent them."
                        ),
                    },
                },
                "required": ["user_id", "listing_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "claim_listings",
            "description": (
                "Claim TWO OR MORE available listings for the current user in one "
                "call. Use when the user picked multiple options (#1 and #3, both, "
                "or '2 oranges and 3 bread'). Each item needs listing_id (UUID or "
                "display index from the last search) and quantity. Prefer this over "
                "calling claim_listing repeatedly. For a single listing, use "
                "claim_listing instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "items": {
                        "type": "array",
                        "description": "One object per claim (min 2).",
                        "items": {
                            "type": "object",
                            "properties": {
                                "listing_id": {
                                    "description": (
                                        "UUID from search results, OR display index 1-N."
                                    ),
                                },
                                "quantity": {
                                    "description": (
                                        "How many units from THIS listing "
                                        "(integer), or 'all' for full stock."
                                    ),
                                },
                                "title": {
                                    "type": "string",
                                    "description": "Optional food title for summaries.",
                                },
                            },
                            "required": ["listing_id", "quantity"],
                        },
                    },
                },
                "required": ["user_id", "items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "confirm_claim",
            "description": (
                "Confirm pickup / mark the user's claim as completed. "
                "Use when the claimant says they picked up the food, or wants "
                "to finish an approved claim. For Supabase UUID users no SMS "
                "code is required — pass listing_id or claim_id when known. "
                "(Legacy SQLite flow may still accept a 4-digit code.)"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "listing_id": {
                        "type": "string",
                        "description": "Listing UUID from search results, or display list number (1, 2, 3…) after search_food_near_user.",
                    },
                    "code": {
                        "type": "string",
                        "description": "Optional 4-digit code (legacy SQLite only; ignore for normal UUID claims).",
                    },
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_claim",
            "description": "ACTION: release a listing the user previously claimed (before pickup), returning it as approved/live. Confirm with the user first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "listing_id": {
                        "type": "string",
                        "description": "Listing UUID or display list number (1, 2, 3…) from search results.",
                    },
                },
                "required": ["user_id", "listing_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_user_profile",
            "description": "ACTION: update the current user's profile fields. Only the fields supplied are changed. Use for dietary needs, allergies, address, phone, SMS consent, preferred categories, or household size.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "phone": {"type": "string"},
                    "address": {"type": "string"},
                    "household_size": {"type": "integer"},
                    "dietary_restrictions": {"type": "array", "items": {"type": "string"}},
                    "allergies": {"type": "array", "items": {"type": "string"}},
                    "preferred_categories": {"type": "array", "items": {"type": "string"}},
                    "sms_consent_given": {"type": "boolean"},
                    "notification_preferences": {"type": "object"},
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "post_food_request",
            "description": (
                "ACTION: create a community food request for the current user "
                "(recipient asks for food not on Find Food). Stores as "
                "food_listings with listing_type=request so donors see it on "
                "Community Requests. Do NOT ask for or attach photos — requests "
                "are text-only. Category: produce/prepared/packaged/bakery/"
                "water/fruit/leftovers or omit. Prefer a short title of what "
                "they need when known."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "title": {"type": "string", "description": "What food they need"},
                    "category": {"type": "string"},
                    "household_size": {"type": "integer", "default": 1},
                    "address": {"type": "string"},
                    "notes": {"type": "string"},
                    "latest_by": {"type": "string", "description": "ISO 8601 date or datetime needed-by"},
                    "special_needs": {"type": "array", "items": {"type": "string"}},
                    "dietary_restrictions": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "post_food_listing",
            "description": (
                "ACTION: create a food listing for the current donor user. "
                "REQUIRED flow before calling: (1) donor confirms community/school "
                "via community_confirmed=true, (2) donor gives expiry/best-by as "
                "expiration_date YYYY-MM-DD. EXCEPTION: when sharing food to fulfill "
                "an open community food request, pass fulfilling_request_id — the "
                "server locks community to that request (skip asking which "
                "community). Category: produce/prepared/packaged/"
                "bakery/water/fruit/leftovers. OMIT pickup_window unless donor "
                "named specific times. success ONLY when response has success:true "
                "AND listing_id. When status=pending / awaiting_approval=true, tell "
                "the donor it is awaiting admin approval — do NOT say it is live "
                "on Find Food yet."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "category": {"type": "string"},
                    "qty": {"type": "number"},
                    "unit": {"type": "string"},
                    "perishability": {"type": "string", "enum": ["low", "medium", "high"], "default": "medium"},
                    "address": {"type": "string", "description": "Full street address. Required if the donor's profile has none."},
                    "pickup_window_start": {"type": "string", "description": "ISO 8601. OMIT unless the donor named a specific start time."},
                    "pickup_window_end": {"type": "string", "description": "ISO 8601. OMIT unless the donor named a specific end time."},
                    "expiration_date": {
                        "type": "string",
                        "description": "Required. Best-by / expiry as YYYY-MM-DD — ask the donor first.",
                    },
                    "expiry_date": {
                        "type": "string",
                        "description": "Alias for expiration_date (prefer expiration_date).",
                    },
                    "community_name": {
                        "type": "string",
                        "description": "Community/school name — only after donor confirms.",
                    },
                    "community_id": {"type": "string"},
                    "community_confirmed": {
                        "type": "boolean",
                        "description": "Must be true after donor explicitly confirms the community.",
                    },
                    "fulfilling_request_id": {
                        "type": "string",
                        "description": (
                            "When sharing to fulfill an open food request, pass that "
                            "request's id. Locks community to the request's community "
                            "and sets community_confirmed automatically."
                        ),
                    },
                    "allergens": {"type": "array", "items": {"type": "string"}},
                    "dietary_tags": {"type": "array", "items": {"type": "string"}},
                    "images": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "REQUIRED photo URL(s) from chat (image: …). "
                            "Posting without a photo is not allowed."
                        ),
                    },
                },
                "required": [
                    "user_id", "title", "qty", "expiration_date",
                    "community_name", "community_confirmed", "images",
                ],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "post_food_listings",
            "description": (
                "ACTION: create TWO OR MORE food listings in one call. Use when the "
                "donor is sharing multiple distinct foods (e.g. bread AND apples). "
                "Each item in items[] gets its OWN photo via images[] (REQUIRED). Shared "
                "community_name + community_confirmed apply to the whole batch. "
                "Prefer this over calling post_food_listing repeatedly. For a "
                "single item, use post_food_listing instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "community_name": {
                        "type": "string",
                        "description": "Community/school for the whole batch — after donor confirms.",
                    },
                    "community_id": {"type": "string"},
                    "community_confirmed": {
                        "type": "boolean",
                        "description": "Must be true after donor explicitly confirms the community.",
                    },
                    "address": {
                        "type": "string",
                        "description": "Shared pickup address for all items (profile address OK).",
                    },
                    "items": {
                        "type": "array",
                        "description": "One object per listing (min 2).",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "qty": {"type": "number"},
                                "unit": {"type": "string"},
                                "category": {"type": "string"},
                                "expiration_date": {
                                    "type": "string",
                                    "description": "YYYY-MM-DD best-by / expiry for this item.",
                                },
                                "description": {"type": "string"},
                                "allergens": {"type": "array", "items": {"type": "string"}},
                                "dietary_tags": {"type": "array", "items": {"type": "string"}},
                                "images": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Photo URL(s) for THIS item only.",
                                },
                            },
                            "required": ["title", "qty", "expiration_date"],
                        },
                    },
                },
                "required": ["user_id", "items", "community_name", "community_confirmed"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "attach_photos_to_listing",
            "description": (
                "ACTION: append one or more photo URLs to an existing food "
                "listing's gallery. Use this when the donor uploads a photo "
                "AFTER the listing is already posted (the chat will contain "
                "a message like 'image: /uploads/ai/<uuid>.jpg' or '📎 "
                "Uploaded photo …'). Pick the listing_id from the most "
                "recently posted listing in the conversation, or ask the "
                "donor which listing if it's ambiguous. De-dups against "
                "existing images so re-sending is safe."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "listing_id": {"type": "integer"},
                    "images": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "URLs to attach (e.g. /uploads/ai/<uuid>.jpg).",
                    },
                },
                "required": ["user_id", "listing_id", "images"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_listings",
            "description": (
                "Fetch the authenticated user's own food listings (as a donor). "
                "Use when the user asks 'show my listings', 'what have I posted', "
                "'my active donations', 'has anyone claimed my food', or before "
                "edit/delete when you need to identify which listing they mean."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["active", "approved", "pending", "expired", "claimed", "all"],
                        "description": (
                            "Filter by status. Default: active+approved+pending "
                            "(includes listings awaiting admin approval)."
                        ),
                    },
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_food_listing",
            "description": (
                "Edit one of the authenticated donor's own listings. Use for "
                "'change pickup time', 'increase quantity', 'update description', "
                "'mark as unavailable' (status=expired), 'rename to ...'. "
                "Identify the row with listing_id (preferred — use list number from "
                "get_user_listings) or title_lookup ONLY when listing_id is unknown. "
                "Use structured fields: expiry_date (YYYY-MM-DD), community_name, "
                "quantity, location — NEVER pack community/expiry/qty into description. "
                "title = the NEW name when renaming; do NOT pass the old name in title. "
                "Only pass fields that should change."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "listing_id": {"type": "string"},
                    "title_lookup": {"type": "string"},
                    "title": {"type": "string"},
                    "quantity": {"type": "number"},
                    "unit": {"type": "string"},
                    "description": {"type": "string"},
                    "category": {"type": "string"},
                    "expiry_date": {"type": "string"},
                    "pickup_by": {"type": "string"},
                    "location": {"type": "string"},
                    "community_id": {"type": "string"},
                    "community_name": {"type": "string"},
                    "dietary_tags": {"type": "array", "items": {"type": "string"}},
                    "allergens": {"type": "array", "items": {"type": "string"}},
                    "image_url": {"type": "string"},
                    "status": {"type": "string"},
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deactivate_listing",
            "description": (
                "Soft-remove one of the donor's own listings by setting status "
                "to expired. Use for 'take it down', 'it's all gone', 'hide my "
                "listing'. Provide listing_id or title."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "listing_id": {"type": "string"},
                    "title": {"type": "string"},
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_listing",
            "description": (
                "Permanently delete one or more of the donor's own listings. Use "
                "delete_all=true when the user wants to remove the last CSV/bulk "
                "batch or ALL their active listings ('delete the bulk listings', "
                "'delete them all'). Use delete_duplicates=true to remove "
                "duplicate titles only (keeps one best copy). Pass listing_ids "
                "(UUIDs or list numbers from get_user_listings) for specific "
                "rows. Irreversible — confirm with the user first."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "listing_id": {"type": "string"},
                    "listing_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "delete_duplicates": {"type": "boolean"},
                    "delete_all": {
                        "type": "boolean",
                        "description": (
                            "Delete the last bulk/CSV batch if known, otherwise "
                            "all of the donor's active listings."
                        ),
                    },
                    "title": {"type": "string"},
                    "confirmed": {
                        "type": "boolean",
                        "description": "Must be true after the user confirms deletion.",
                    },
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bulk_import_listings",
            "description": (
                "ACTION: create MANY food listings from CSV. Prefer the chat "
                "CSV upload UI when the donor attaches a file. Requires "
                "community_confirmed=true plus community_name (batch default). "
                "CSV may include per-row community/school columns that override "
                "the batch default — never stamp every row with the donor's "
                "warehouse community when rows name different schools. "
                "PRE-FLIGHT validates title + address. Header aliases: "
                "'food name'→title, 'quantity'→qty, 'pickup location'→address, "
                "'community'/'school'→per-row community, "
                "'expiration date'/'best by'→expiration_date. Dates in "
                "expiry_date / default_expiry_date accept American MM/DD/YYYY "
                "(e.g. 9/15/2026) as well as ISO YYYY-MM-DD — the server "
                "normalizes to ISO before storage."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "csv_text": {"type": "string", "description": "Raw CSV text. First row must be the header."},
                    "default_address": {"type": "string", "description": "Optional fallback address used for rows that don't include one."},
                    "default_expiry_date": {
                        "type": "string",
                        "description": (
                            "Optional fallback expiry for rows missing one. "
                            "Accepts American MM/DD/YYYY (e.g. 9/15/2026) or "
                            "ISO YYYY-MM-DD."
                        ),
                    },
                    "community_name": {"type": "string", "description": "Batch default community/school. Per-row CSV community overrides this."},
                    "community_id": {"type": "string", "description": "Batch default community id."},
                    "community_confirmed": {"type": "boolean", "description": "Must be true after the donor confirms the community."},
                    "listings": {
                        "type": "array",
                        "description": "Optional pre-parsed listings instead of csv_text.",
                        "items": {"type": "object"},
                    },
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_user_message",
            "description": "ACTION: send an in-app chat message from the current user. To message another user directly, pass their id as recipient_id and the tool builds a shared pair conversation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "content": {"type": "string"},
                    "recipient_id": {"type": "integer", "description": "Optional. The other party's user id. Creates a shared pair thread."},
                    "conversation_id": {"type": "string", "description": "Optional. If set, overrides recipient_id and uses this exact thread id."},
                },
                "required": ["user_id", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "show_map",
            "description": (
                "ACTION: switch the DoGoods UI to the interactive map view so the user "
                "can see available food listings on the map. Call this whenever the user "
                "asks to 'show the map', 'open the map', 'see food on the map', 'view "
                "listings on the map', or anything similar. DO NOT EXPLAIN, JUST CALL — "
                "the UI will navigate immediately."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "focus": {
                        "type": "string",
                        "description": (
                            "Optional. What to focus the map on. One of 'me' (center on the "
                            "user), 'all' (fit all listings), or a free-text place/category."
                        ),
                    },
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "show_route_to_listing",
            "description": (
                "ACTION: draw a driving route on the map from the recipient's saved "
                "address to a specific food listing's pickup location. Call this when "
                "the recipient asks 'how do I get there?', 'show me directions', "
                "'route to listing #N', 'cómo llego', 'dame las direcciones', or "
                "right AFTER a successful claim so they can see the path to pickup. "
                "Pass listing_id as the Supabase listing UUID from search/claim "
                "results, OR the display number (#1, #2) from the latest search. "
                "If they ask for directions to their pickup without a number, omit "
                "listing_id and the server uses their most recent claim. "
                "Requires the recipient to have an address on file AND the listing "
                "to have map coordinates. The UI switches to Find Food map and "
                "draws a blue route line."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "listing_id": {
                        "type": "string",
                        "description": (
                            "Listing UUID, or search display index ('1', '2', '#3'). "
                            "Optional when the user just claimed — uses latest claim."
                        ),
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["driving", "walking", "cycling"],
                        "description": "Mapbox profile. Default 'driving'.",
                    },
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "navigate_ui",
            "description": (
                "ACTION: drive the DoGoods web UI on the user's behalf — open or close "
                "views, panels and modals. Call this whenever the user asks to 'open', "
                "'show', 'go to', 'close', 'hide', 'exit', 'leave', 'back to map', etc. "
                "DO NOT EXPLAIN, JUST CALL — the UI will navigate immediately and the "
                "assistant should keep its reply short. Use 'close' (no target) to return "
                "to the map. Targets are page-level views; 'list' and 'map' also flip the "
                "main map/list toggle."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "action": {
                        "type": "string",
                        "enum": ["open", "close", "toggle"],
                        "description": "What to do. 'close' returns the UI to the map.",
                    },
                    "target": {
                        "type": "string",
                        "enum": [
                            "map",
                            "list",
                            "create",
                            "bulk-create",
                            "request",
                            "request-food",
                            "community-requests",
                            "claim",
                            "profile",
                            "settings",
                            "receipts",
                            "listings",
                            "near-me",
                            "notifications",
                            "login",
                            "signup",
                            "home",
                            "dashboard",
                            "dispatch",
                            "admin",
                            "driver",
                            "schedule",
                            "partners",
                            "food-rescue",
                            "meal-planning",
                            "ai-matching",
                            "routes",
                            "emergency",
                            "nutrition",
                            "consumption",
                            "filters",
                            "favorites",
                            "chat",
                            "voice",
                            "meal-suggestions",
                            "spoilage-alerts",
                            "storage-coach",
                            "smart-notifications",
                            "pickup-reminders",
                            "sms-consent",
                        ],
                        "description": (
                            "Which UI surface to act on. Core product pages: "
                            "list/find (/find), create/share (/share), request, claim, "
                            "profile, settings, receipts, listings, near-me, dashboard, "
                            "community-requests, login, signup, home. "
                            "'map'/'list' toggle the main view; 'chat'/'voice' control Nouri."
                        ),
                    },
                    "query": {
                        "type": "string",
                        "description": (
                            "Optional URL query for page targets (especially create/share). "
                            "Example when fulfilling a request: "
                            "request=Bread&community_id=<uuid>&community=<name>"
                            "&fulfilling_request_id=<uuid>. Allowed keys: request, "
                            "community_id, community, category, quantity, unit, "
                            "description, needed_by, fulfilling_request_id."
                        ),
                    },
                },
                "required": ["user_id", "action"],
            },
        },
    },
    # ---- Agentic memory tools -----------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "save_user_memory",
            "description": (
                "Save a learned preference or durable standing instruction about the user. "
                "Use for: favourite foods, household context, AND "
                "explicit coaching like 'always confirm quantity', 'always open the map', "
                "'remember I use miles'. For standing rules prefer keys starting with "
                "always_do: or remind: (e.g. always_do:confirm_quantity). Do NOT store "
                "transient turn data. The backend also auto-saves obvious 'always…' / "
                "'remember…' phrases — still call this when you infer a durable rule."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "key": {
                        "type": "string",
                        "description": (
                            "Short snake_case label, e.g. 'favourite_foods', "
                            "'always_do:confirm_quantity', 'remind:open_map_after_search'"
                        ),
                    },
                    "value": {"type": "string", "description": "The value to store"},
                    "confidence": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "description": "How confident you are in this preference",
                    },
                },
                "required": ["user_id", "key", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "forget_user_memory",
            "description": (
                "Delete a previously saved preference or standing instruction when the "
                "user says to forget it / stop always doing it. Pass the exact key if "
                "known, or a short search phrase to match always_do:/remind: values."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "key": {
                        "type": "string",
                        "description": "Exact preference key to delete, if known",
                    },
                    "query": {
                        "type": "string",
                        "description": (
                            "Free-text match against key or value when the exact key "
                            "is unknown (e.g. 'confirm quantity')"
                        ),
                    },
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_memory",
            "description": (
                "Retrieve previously learned preferences and facts about this user. "
                "Call at the start of a new conversation or when you need to recall "
                "what you already know about them."
            ),
            "parameters": {
                "type": "object",
                "properties": {"user_id": {"type": "string"}},
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mark_goal_done",
            "description": (
                "Record that a multi-step user goal has been completed "
                "(e.g. 'posted 3 food listings', 'claimed pickup for the week'). "
                "Call this after successfully finishing a complex multi-step task."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "description": {
                        "type": "string",
                        "description": "Human-readable summary of what was accomplished",
                    },
                },
                "required": ["user_id", "description"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

async def execute_tool(name: str, arguments: dict) -> dict:
    handlers = {
        "search_food_near_user": _search_food_near_user,
        "get_recent_listings": _get_recent_listings,
        "get_community_listings": _get_community_listings,
        "get_user_profile": _get_user_profile,
        "get_pickup_schedule": _get_pickup_schedule,
        "create_ai_reminder": _create_reminder,
        "create_reminder": _create_reminder,  # legacy alias
        "get_mapbox_route": _get_mapbox_route,
        "query_distribution_centers": _query_distribution_centers,
        "get_user_dashboard": _get_user_dashboard,
        "check_pickup_schedule": _check_pickup_schedule,
        "get_recipes": _get_recipes,
        "get_storage_tips": _get_storage_tips,
        "get_donor_expiring_listings": _get_donor_expiring_listings,
        "get_driver_route_plan": _get_driver_route_plan,
        "get_dispatch_queue": _get_dispatch_queue,
        "get_platform_stats": _get_platform_stats,
        "get_profile_gaps": _get_profile_gaps,
        "optimize_pickup_route": _optimize_pickup_route,
        "run_safe_query": _run_safe_query,
        "claim_listing": _claim_listing,
        "claim_listings": _claim_listings,
        "cancel_claim": _cancel_claim,
        "confirm_claim": _confirm_claim,
        "update_user_profile": _update_user_profile,
        "post_food_request": _post_food_request,
        "post_food_listing": _post_food_listing,
        "post_food_listings": _post_food_listings,
        "attach_photos_to_listing": _attach_photos_to_listing,
        "get_user_listings": _get_user_listings,
        "update_food_listing": _update_food_listing,
        "update_listing": _update_food_listing,
        "edit_listing": _update_food_listing,
        "deactivate_listing": _deactivate_listing,
        "delete_listing": _delete_listing,
        "bulk_import_listings": _bulk_import_listings,
        "send_user_message": _send_user_message,
        "show_map": _show_map,
        "show_route_to_listing": _show_route_to_listing,
        "navigate_ui": _navigate_ui,
        # Agentic memory tools
        "save_user_memory": _save_user_memory,
        "get_user_memory": _get_user_memory,
        "forget_user_memory": _forget_user_memory,
        "mark_goal_done": _mark_goal_done,
    }
    handler = handlers.get(name)
    if handler is None:
        return {"error": f"Unknown tool: {name}"}
    # Defense-in-depth: silently drop kwargs the handler doesn't accept.
    # OpenAI tool calls occasionally include legacy/extra fields (e.g.
    # 'confirmed' from a prior schema version) that would otherwise raise
    # TypeError and surface as an ugly "Tool execution failed" message.
    import inspect as _inspect
    try:
        sig = _inspect.signature(handler)
        accepts_kwargs = any(
            p.kind == _inspect.Parameter.VAR_KEYWORD
            for p in sig.parameters.values()
        )
        if not accepts_kwargs and isinstance(arguments, dict):
            allowed = set(sig.parameters.keys())
            arguments = {k: v for k, v in arguments.items() if k in allowed}
    except (TypeError, ValueError):
        pass
    try:
        result = await handler(**arguments)
        if name == "search_food_near_user" and isinstance(result, dict):
            try:
                from backend.ai.conversation_flow import set_last_search_listings
                listings = result.get("listings") or []
                uid = str(arguments.get("user_id") or "")
                if uid and listings:
                    set_last_search_listings(uid, listings)
            except Exception:
                pass
        if name == "claim_listing" and isinstance(result, dict) and result.get("success"):
            try:
                from backend.ai.conversation_flow import (
                    update_last_search_listing_after_claim,
                )
                uid = str(arguments.get("user_id") or "")
                lid = result.get("listing_id")
                if uid and lid:
                    remaining = result.get("remaining_on_listing")
                    update_last_search_listing_after_claim(
                        uid,
                        str(lid),
                        remaining,
                        fully_claimed=bool(result.get("already_claimed"))
                        or (
                            remaining is not None
                            and float(remaining) <= 0
                        ),
                    )
            except Exception:
                pass
        return result
    except Exception as exc:
        # Log full traceback server-side, but return a generic message to
        # the model so internal errors (SQL exceptions, schema details,
        # file paths) don't leak into chat replies.
        logger.exception("Tool %s failed", name)
        return {"error": f"{name} failed. Please try again or rephrase."}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _to_int(value) -> Optional[int]:
    try:
        return int(str(value))
    except (ValueError, TypeError):
        return None


_UUID_RE = re.compile(r"^[0-9a-f-]{36}$", re.I)


def _is_supabase_user_id(user_id: str) -> bool:
    """True when auth id is a Supabase UUID (not a legacy integer PK)."""
    uid = str(user_id or "").strip()
    return bool(uid) and not uid.isdigit()


def _resolve_supabase_listing_id(listing_id, user_id: str) -> Optional[str]:
    """Map search display index (1, 2, 3…) to a Supabase listing UUID."""
    if listing_id is None:
        return None
    lid = str(listing_id).strip().lstrip("#").strip()
    if not lid:
        return None
    if _UUID_RE.match(lid):
        return lid
    from backend.ai.conversation_flow import resolve_listing_id_from_search
    resolved, _err = resolve_listing_id_from_search(lid, str(user_id or ""))
    return resolved


# Keyword -> FoodCategory guessing so the AI doesn't have to ask the donor
# what 'category' a loaf of bread is. Falls back to 'prepared'.
_CATEGORY_KEYWORDS = {
    "produce":   ["lettuce", "kale", "spinach", "carrot", "tomato", "onion", "potato",
                  "pepper", "cucumber", "broccoli", "cabbage", "celery", "garlic",
                  "vegetable", "veggie", "greens", "salad"],
    "fruit":     ["apple", "banana", "orange", "berry", "berries", "grape", "pear",
                  "peach", "plum", "melon", "watermelon", "mango", "pineapple",
                  "fruit", "lemon", "lime"],
    "bakery":    ["bread", "loaf", "loaves", "bagel", "croissant", "muffin", "pastry",
                  "donut", "doughnut", "cake", "pie", "scone", "roll", "sourdough",
                  "baguette", "tortilla"],
    "prepared":  ["meal", "soup", "stew", "casserole", "pasta", "pizza", "rice",
                  "curry", "sandwich", "burrito", "taco", "lasagna", "salad bowl",
                  "leftover", "leftovers"],
    "packaged":  ["can", "canned", "box", "boxed", "jar", "package", "snack",
                  "cereal", "chips", "cookies", "crackers", "pasta dry", "rice dry",
                  "beans", "lentils", "peanut butter", "sealed"],
    "water":     ["water", "bottled water", "gallon"],
    "leftovers": ["leftover", "leftovers"],
}


def _guess_category_from_title(title: str) -> str:
    t = (title or "").lower()
    for cat, kws in _CATEGORY_KEYWORDS.items():
        for kw in kws:
            if kw in t:
                return cat
    return "prepared"


# ---------------------------------------------------------------------------
# Spanish → English glossary for listing fields.
#
# Listings are stored in English so the recipient-side UI / search /
# filters work consistently. The AI prompt already instructs the model
# to translate before calling post_food_listing, but this is a backend
# safety net for the case where the model lapses (especially on bulk /
# CSV imports). Word-boundary, case-preserving substitution.
# ---------------------------------------------------------------------------

_LISTING_ES_EN: dict[str, str] = {
    # produce
    "manzanas": "apples", "manzana": "apple",
    "naranjas": "oranges", "naranja": "orange",
    "plátanos": "bananas", "plátano": "banana", "platanos": "bananas", "platano": "banana",
    "uvas": "grapes", "uva": "grape",
    "fresas": "strawberries", "fresa": "strawberry",
    "limones": "lemons", "limón": "lemon", "limon": "lemon",
    "lechuga": "lettuce",
    "tomates": "tomatoes", "tomate": "tomato",
    "cebollas": "onions", "cebolla": "onion",
    "zanahorias": "carrots", "zanahoria": "carrot",
    "papas": "potatoes", "papa": "potato", "patatas": "potatoes",
    "verduras": "vegetables", "verdura": "vegetable",
    "frutas": "fruit", "fruta": "fruit",
    "produce fresco": "fresh produce", "produce": "produce",
    # bakery
    "pan": "bread", "panes": "loaves of bread",
    "panecillos": "rolls", "bollos": "rolls",
    "tortillas": "tortillas",
    "galletas": "cookies",
    "pastel": "cake", "pasteles": "cakes",
    # prepared / leftovers
    "comida preparada": "prepared meal",
    "sobras": "leftovers",
    "arroz": "rice",
    "frijoles": "beans", "habichuelas": "beans",
    "sopa": "soup",
    "guisado": "stew", "guiso": "stew",
    "pollo": "chicken",
    "carne": "beef", "res": "beef",
    "puerco": "pork", "cerdo": "pork",
    "pescado": "fish",
    "ensalada": "salad",
    # packaged / dairy
    "leche": "milk",
    "queso": "cheese",
    "yogur": "yogurt", "yogurt": "yogurt",
    "huevos": "eggs", "huevo": "egg",
    "agua": "water",
    "jugo": "juice", "zumo": "juice",
    # allergens / dietary tags
    "gluten": "gluten",
    "lácteos": "dairy", "lacteos": "dairy",
    "frutos secos": "nuts", "nueces": "nuts",
    "soya": "soy", "soja": "soy",
    "mariscos": "shellfish",
    "sin gluten": "gluten-free",
    "sin lácteos": "dairy-free", "sin lacteos": "dairy-free",
    "vegetariano": "vegetarian",
    "vegano": "vegan",
    # handoff phrasing donors often write in description
    "recogida solamente": "Pickup only.",
    "recogida solo": "Pickup only.",
    "solo recogida": "Pickup only.",
    "entrega disponible": "Donor delivery available.",
    "entrega del donante": "Donor delivery available.",
    # units
    "libras": "lbs", "libra": "lb",
    "kilos": "kg", "kilo": "kg",
    "cajas": "boxes", "caja": "box",
    "bolsas": "bags", "bolsa": "bag",
    "piezas": "pieces", "pieza": "piece",
    "barras": "loaves", "barra": "loaf",
}


def _translate_listing_text(value: Optional[str]) -> Optional[str]:
    """Translate a Spanish listing field to English using a small glossary.

    Conservative: substitutes only known terms with word-boundary matching
    (case-insensitive, preserves leading-capital). If nothing matches, the
    text is returned unchanged. Never raises; never blocks posting.
    """
    if not value or not isinstance(value, str):
        return value
    out = value
    for es, en in _LISTING_ES_EN.items():
        # word-boundary, case-insensitive
        pattern = r"\b" + re.escape(es) + r"\b"

        def _replace(match: "re.Match[str]") -> str:
            src = match.group(0)
            if src.isupper():
                return en.upper()
            if src[:1].isupper():
                return en[:1].upper() + en[1:]
            return en

        out = re.sub(pattern, _replace, out, flags=re.IGNORECASE)
    return out


async def _run(sync_fn):
    """Run a blocking SQLAlchemy function in a thread."""
    return await asyncio.get_event_loop().run_in_executor(None, sync_fn)


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

async def _search_food_near_user(
    user_id: str,
    food_type: Optional[str] = None,
    max_results: int = 25,
    **kwargs,
) -> dict:
    """Search food for the user via Supabase (supports UUID user ids)."""
    from backend.tools import _search_food_near_user as _impl
    # Drop legacy radius_km if the model still sends it — search has no radius cutoff.
    kwargs.pop("radius_km", None)
    return await _impl(
        user_id=user_id,
        food_type=food_type,
        max_results=max_results,
        **kwargs,
    )


async def _get_recent_listings(
    user_id: str,
    hours: int = 72,
    limit: int = 10,
    category: Optional[str] = None,
    **kwargs,
) -> dict:
    from backend.tools import _get_recent_listings as _impl
    return await _impl(
        user_id=user_id,
        hours=hours,
        limit=limit,
        category=category,
        **kwargs,
    )


async def _get_community_listings(
    community_id: str,
    user_id: Optional[str] = None,
    limit: int = 10,
    category: Optional[str] = None,
    **kwargs,
) -> dict:
    from backend.tools import _get_community_listings as _impl
    return await _impl(
        community_id=str(community_id),
        user_id=user_id,
        limit=limit,
        category=category,
        **kwargs,
    )


async def _get_user_profile(user_id: str) -> dict:
    """Retrieve user profile via Supabase (auth IDs are UUIDs, not MySQL ints)."""
    from backend.tools import _get_user_profile as _impl
    return await _impl(user_id=user_id)


async def _get_pickup_schedule(
    user_id: str,
    include_community_events: bool = True,
    days_ahead: int = 7,
) -> dict:
    if _is_supabase_user_id(user_id):
        from backend.tools import _get_pickup_schedule as _impl
        return await _impl(
            user_id=str(user_id).strip(),
            include_community_events=include_community_events,
            days_ahead=days_ahead,
        )

    from backend.app import SessionLocal
    from backend.models import FoodResource, DistributionCenter

    uid = _to_int(user_id)
    if uid is None:
        return {"error": "Invalid user_id"}

    def _sync() -> dict:
        db = SessionLocal()
        try:
            claimed = (
                db.query(FoodResource)
                .filter(FoodResource.recipient_id == uid)
                .filter(FoodResource.status.in_(["claimed", "pending", "approved"]))
                .order_by(FoodResource.pickup_window_start.asc())
                .limit(20)
                .all()
            )
            pickups = [
                {
                    "claim_id": l.id,
                    "food_title": l.title,
                    "status": l.status,
                    "pickup_date": l.pickup_window_start.isoformat() if l.pickup_window_start else None,
                    "pickup_by": l.pickup_window_end.isoformat() if l.pickup_window_end else None,
                    "address": l.address,
                }
                for l in claimed
            ]

            events = []
            if include_community_events:
                centers = (
                    db.query(DistributionCenter)
                    .filter(DistributionCenter.is_active == True)  # noqa: E712
                    .limit(10)
                    .all()
                )
                for c in centers:
                    events.append({
                        "center_id": c.id,
                        "name": c.name,
                        "description": (c.description or "")[:200],
                        "address": c.address,
                        "phone": c.phone,
                        "hours": c.hours,
                    })

            return {"pickups": pickups, "events": events, "days_ahead": days_ahead}
        finally:
            db.close()

    return await _run(_sync)


async def _create_reminder(
    user_id: str,
    message: str,
    trigger_time: str,
    reminder_type: str = "general",
    related_id: Optional[int] = None,
) -> dict:
    if _is_supabase_user_id(user_id):
        from backend.tools import _create_reminder as _impl
        return await _impl(
            user_id=str(user_id).strip(),
            message=message,
            trigger_time=trigger_time,
            reminder_type=reminder_type,
            related_id=str(related_id) if related_id is not None else None,
        )

    from backend.app import SessionLocal
    from backend.ai.models import AIReminder

    uid = _to_int(user_id)
    if uid is None:
        return {"created": False, "error": "Invalid user_id"}

    try:
        trigger_dt = datetime.fromisoformat(trigger_time.replace("Z", "+00:00"))
        if trigger_dt < datetime.now(timezone.utc):
            return {"created": False, "error": "Trigger time must be in the future."}
    except (ValueError, TypeError):
        return {"created": False, "error": "Invalid trigger_time format (use ISO 8601)."}

    def _sync() -> dict:
        db = SessionLocal()
        try:
            # Store as naive UTC for MySQL DATETIME
            row = AIReminder(
                user_id=str(uid),
                message=message,
                trigger_time=trigger_dt.astimezone(timezone.utc).replace(tzinfo=None),
                reminder_type=reminder_type,
                related_id=related_id,
                sent=False,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return {
                "created": True,
                "success": True,
                "reminder_id": row.id,
                "trigger_time": trigger_time,
                "message": f"Reminder set for {trigger_time}.",
                "summary": f"Done — reminder set for {trigger_time}. I'll ping you when it's time.",
            }
        except Exception as exc:
            db.rollback()
            return {"created": False, "error": str(exc)}
        finally:
            db.close()

    return await _run(_sync)


async def _get_mapbox_route(
    origin_lng: float,
    origin_lat: float,
    dest_lng: float,
    dest_lat: float,
    profile: str = "driving",
) -> dict:
    if not MAPBOX_TOKEN:
        return {
            "error": "Mapbox token not configured",
            "fallback": f"Straight-line distance: ~{_haversine(origin_lat, origin_lng, dest_lat, dest_lng):.1f} km.",
        }

    if profile not in ("driving", "walking", "cycling"):
        profile = "driving"

    coords = f"{origin_lng},{origin_lat};{dest_lng},{dest_lat}"
    url = f"{MAPBOX_DIRECTIONS_URL}/{profile}/{coords}"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params={
                "access_token": MAPBOX_TOKEN,
                "geometries": "geojson",
                "overview": "simplified",
                "steps": "true",
                "language": "en",
            })
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        return {"error": f"Mapbox API error: HTTP {exc.response.status_code}"}
    except Exception as exc:
        return {"error": f"Mapbox request failed: {exc}"}

    routes = data.get("routes", [])
    if not routes:
        return {"error": "No route found"}

    route = routes[0]
    duration_sec = route.get("duration", 0)
    distance_m = route.get("distance", 0)
    steps = []
    for leg in route.get("legs", []):
        for step in leg.get("steps", []):
            instr = step.get("maneuver", {}).get("instruction", "")
            if instr:
                steps.append({
                    "instruction": instr,
                    "distance_m": round(step.get("distance", 0)),
                    "duration_sec": round(step.get("duration", 0)),
                })

    dist_km = distance_m / 1000
    if duration_sec < 60:
        time_str = f"{int(duration_sec)} seconds"
    elif duration_sec < 3600:
        time_str = f"{int(duration_sec // 60)} minutes"
    else:
        h = int(duration_sec // 3600)
        m = int((duration_sec % 3600) // 60)
        time_str = f"{h}h {m}min"

    return {
        "profile": profile,
        "distance_km": round(dist_km, 2),
        "duration_minutes": round(duration_sec / 60, 1),
        "duration_text": time_str,
        "steps": steps[:20],
        "summary": f"Route by {profile}: {dist_km:.1f} km, about {time_str}.",
    }


async def _query_distribution_centers(
    max_results: int = 10,
    user_id: Optional[str] = None,
) -> dict:
    from backend.app import SessionLocal
    from backend.models import DistributionCenter, User

    def _sync() -> dict:
        db = SessionLocal()
        try:
            user_lat = user_lng = None
            if user_id:
                uid = _to_int(user_id)
                if uid is not None:
                    u = db.query(User).filter(User.id == uid).first()
                    if u:
                        user_lat, user_lng = u.coords_lat, u.coords_lng

            centers = (
                db.query(DistributionCenter)
                .filter(DistributionCenter.is_active == True)  # noqa: E712
                .limit(50)
                .all()
            )
            results = []
            for c in centers:
                entry = {
                    "center_id": c.id,
                    "name": c.name,
                    "description": (c.description or "")[:300],
                    "address": c.address,
                    "phone": c.phone,
                    "hours": c.hours,
                    "verified_by_aglf": c.verified_by_aglf,
                    "school_partner": c.school_partner,
                }
                if (
                    user_lat is not None and user_lng is not None
                    and c.coords_lat is not None and c.coords_lng is not None
                ):
                    dist = _haversine(user_lat, user_lng, c.coords_lat, c.coords_lng)
                    entry["distance_km"] = round(dist, 1)
                results.append(entry)

            if user_lat is not None:
                results.sort(key=lambda r: r.get("distance_km", 9999))
            else:
                results.sort(key=lambda r: r["name"] or "")

            results = results[:max_results]
            if results:
                parts = [
                    f"{i}. **{r['name']}** — {r.get('address', 'N/A')}"
                    + (f" ({r['distance_km']} km away)" if 'distance_km' in r else "")
                    for i, r in enumerate(results, 1)
                ]
                summary = f"Found {len(results)} distribution center(s):\n" + "\n".join(parts)
            else:
                summary = "No active distribution centers found."

            return {"centers": results, "total": len(results), "summary": summary}
        finally:
            db.close()

    return await _run(_sync)


async def _get_user_dashboard(user_id: str) -> dict:
    """Rich dashboard via Supabase (auth IDs are UUIDs, not legacy ints)."""
    from backend.tools import _get_user_dashboard as _impl
    return await _impl(user_id=str(user_id).strip())


async def _check_pickup_schedule(
    user_id: str,
    include_sent: bool = False,
    days_ahead: int = 14,
) -> dict:
    """Supabase-backed schedule (UUID auth users). Legacy int ids stay on MySQL."""
    if _is_supabase_user_id(user_id):
        from backend.tools import _check_pickup_schedule as _impl
        return await _impl(
            user_id=str(user_id).strip(),
            include_sent=include_sent,
            days_ahead=days_ahead,
        )

    from backend.app import SessionLocal
    from backend.models import FoodResource
    from backend.ai.models import AIReminder

    uid = _to_int(user_id)
    if uid is None:
        return {"error": "Invalid user_id"}

    def _sync() -> dict:
        db = SessionLocal()
        try:
            now = _utcnow()
            future = now + timedelta(days=days_ahead)

            reminders_q = (
                db.query(AIReminder)
                .filter(AIReminder.user_id == uid)
                .filter(AIReminder.trigger_time <= future)
            )
            if not include_sent:
                reminders_q = reminders_q.filter(AIReminder.sent == False)  # noqa: E712
            reminders = reminders_q.order_by(AIReminder.trigger_time.asc()).limit(50).all()

            reminders_by_type: dict[str, list] = {
                "pickup": [], "listing_expiry": [], "distribution_event": [], "general": [],
            }
            for r in reminders:
                t = r.reminder_type if r.reminder_type in reminders_by_type else "general"
                reminders_by_type[t].append({
                    "id": r.id, "message": r.message,
                    "trigger_time": r.trigger_time.isoformat(),
                    "sent": r.sent,
                })

            claimed = (
                db.query(FoodResource)
                .filter(FoodResource.recipient_id == uid)
                .filter(FoodResource.status.in_(["claimed", "pending", "approved"]))
                .order_by(FoodResource.pickup_window_start.asc())
                .limit(20)
                .all()
            )
            pickups = [
                {
                    "claim_id": l.id,
                    "food_title": l.title,
                    "status": l.status,
                    "pickup_date": l.pickup_window_start.isoformat() if l.pickup_window_start else None,
                    "pickup_by": l.pickup_window_end.isoformat() if l.pickup_window_end else None,
                    "address": l.address,
                    "expiry_date": l.expiration_date.isoformat() if l.expiration_date else None,
                }
                for l in claimed
            ]

            total_reminders = sum(len(v) for v in reminders_by_type.values())
            parts = []
            if pickups:
                parts.append(f"{len(pickups)} pending pickup(s)")
            for kind in ("pickup", "distribution_event", "listing_expiry", "general"):
                if reminders_by_type[kind]:
                    parts.append(f"{len(reminders_by_type[kind])} {kind.replace('_', ' ')} reminder(s)")

            summary = "Your schedule: " + ", ".join(parts) + "." if parts else "You have no pending pickups or reminders."

            return {
                "pickups": pickups,
                "reminders": reminders_by_type,
                "total_reminders": total_reminders,
                "total_pickups": len(pickups),
                "summary": summary,
            }
        finally:
            db.close()

    return await _run(_sync)


async def _get_recipes(
    ingredients: Optional[list[str]] = None,
    user_id: Optional[str] = None,
    dietary_preferences: Optional[str] = None,
    household_size: Optional[int] = None,
    low_resource: bool = False,
    **kwargs,
) -> dict:
    """Recipe suggestions via Supabase + OpenAI (supports UUID user ids)."""
    from backend.ai.recipes import generate_recipes

    overrides = None
    if dietary_preferences:
        overrides = [p.strip() for p in str(dietary_preferences).split(",") if p.strip()]
    if kwargs.get("dietary_overrides"):
        extra = kwargs["dietary_overrides"]
        overrides = (overrides or []) + list(extra)

    result = await generate_recipes(
        user_id=user_id,
        ingredients=ingredients,
        use_claimed=kwargs.get("use_claimed", not bool(ingredients)),
        low_resource=low_resource,
        household_size=household_size,
        max_recipes=int(kwargs.get("max_recipes") or 3),
        dietary_overrides=overrides,
        notes=kwargs.get("notes"),
    )
    if result.get("error"):
        return {"error": result["error"]}
    return {
        "recipes": result.get("recipes") or [],
        "headline": result.get("headline", ""),
        "ingredients_used": result.get("ingredients_used") or [],
        "dietary_preferences": dietary_preferences,
        "household_size": result.get("household_size"),
        "low_resource": result.get("low_resource"),
        "allergens_avoided": result.get("allergens_avoided") or [],
        "summary": result.get("headline") or f"Found {len(result.get('recipes') or [])} recipe(s).",
    }


async def _get_storage_tips(
    food_items: Optional[list[str]] = None,
    user_id: Optional[str] = None,
) -> dict:
    from backend.ai.ai_engine import legacy_ai_request, _extract_content, CHAT_MODEL
    from backend.app import SessionLocal
    from backend.models import FoodResource

    if not food_items and user_id:
        uid = _to_int(user_id)
        if uid is not None:
            def _fetch():
                db = SessionLocal()
                try:
                    rows = (
                        db.query(FoodResource)
                        .filter(FoodResource.recipient_id == uid)
                        .filter(FoodResource.status.in_(["claimed", "approved", "pending"]))
                        .limit(10)
                        .all()
                    )
                    return [r.title for r in rows if r.title]
                finally:
                    db.close()
            food_items = await _run(_fetch)

    if not food_items:
        return {"error": "No food items provided and no claimed food found for user."}

    prompt = (
        f"Provide storage tips for: {', '.join(food_items)}. "
        "For each item include optimal temperature, container, shelf life "
        "(fridge/freezer/pantry), spoilage signs, and tips to extend freshness. "
        "Return JSON."
    )
    payload = {
        "model": CHAT_MODEL,
        "messages": [
            {"role": "system", "content": "You are a food preservation expert."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.5,
        "max_tokens": 1500,
    }
    try:
        data = await legacy_ai_request("/chat/completions", payload)
        return {"tips": _extract_content(data), "food_items": food_items}
    except Exception as exc:
        return {"error": f"Failed to generate storage tips: {exc}"}


# ---------------------------------------------------------------------------
# Role-specific tools
# ---------------------------------------------------------------------------

async def _get_donor_expiring_listings(
    user_id: str,
    hours_ahead: int = 48,
    days: Optional[int] = None,
    **_ignored,
) -> dict:
    """Donor: own listings whose expiry is close (Supabase for UUID users)."""
    if _is_supabase_user_id(user_id):
        from backend.tools import _get_donor_expiring_listings as _impl
        # Canonical tool uses days; map hours_ahead when days omitted.
        if days is None:
            try:
                days = max(1, int(math.ceil(float(hours_ahead or 48) / 24.0)))
            except (TypeError, ValueError):
                days = 2
        return await _impl(user_id=str(user_id).strip(), days=days)

    from backend.app import SessionLocal
    from backend.models import FoodResource

    uid = _to_int(user_id)
    if uid is None:
        return {"error": "Invalid user_id"}

    def _sync() -> dict:
        db = SessionLocal()
        try:
            now = _utcnow()
            horizon = now + timedelta(hours=hours_ahead)
            rows = (
                db.query(FoodResource)
                .filter(FoodResource.donor_id == uid)
                .filter(FoodResource.status == "available")
                .all()
            )
            items = []
            for r in rows:
                deadline = r.pickup_window_end or r.expiration_date
                if not deadline or deadline > horizon or deadline < now:
                    continue
                hrs = max(0, int((deadline - now).total_seconds() // 3600))
                items.append({
                    "id": r.id,
                    "title": r.title,
                    "qty": r.qty,
                    "unit": r.unit,
                    "deadline": deadline.isoformat(),
                    "hours_until_deadline": hrs,
                    "address": r.address,
                })
            items.sort(key=lambda x: x["hours_until_deadline"])
            if items:
                parts = [f"- {i['title']} ({i['qty']} {i['unit'] or ''}): {i['hours_until_deadline']}h left"
                         for i in items]
                summary = f"You have {len(items)} listing(s) expiring within {hours_ahead}h:\n" + "\n".join(parts)
            else:
                summary = f"No listings expiring in the next {hours_ahead} hours. Great job keeping things fresh!"
            return {"count": len(items), "items": items, "summary": summary}
        finally:
            db.close()

    return await _run(_sync)


async def _get_driver_route_plan(user_id: str, max_stops: int = 8) -> dict:
    """Volunteer/Driver: route plan across claimed pickups for today."""
    from backend.app import SessionLocal
    from backend.models import User, FoodResource

    uid = _to_int(user_id)
    if uid is None:
        return {"error": "Invalid user_id"}

    def _sync() -> dict:
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == uid).first()
            if not user:
                return {"error": "User not found"}
            rows = (
                db.query(FoodResource)
                .filter(FoodResource.recipient_id == uid)
                .filter(FoodResource.status.in_(["claimed", "approved", "pending", "en_route"]))
                .all()
            )
            stops = []
            for r in rows:
                if r.coords_lat is None or r.coords_lng is None:
                    continue
                dist = None
                if user.coords_lat is not None and user.coords_lng is not None:
                    dist = _haversine(user.coords_lat, user.coords_lng,
                                      float(r.coords_lat), float(r.coords_lng))
                stops.append({
                    "listing_id": r.id,
                    "title": r.title,
                    "address": r.address,
                    "lat": r.coords_lat,
                    "lng": r.coords_lng,
                    "pickup_by": r.pickup_window_end.isoformat() if r.pickup_window_end else None,
                    "distance_km_from_start": round(dist, 2) if dist is not None else None,
                })
            # Simple nearest-neighbour ordering from user's current location
            if user.coords_lat is not None and user.coords_lng is not None and stops:
                ordered: list[dict] = []
                remaining = list(stops)
                cur_lat, cur_lng = user.coords_lat, user.coords_lng
                while remaining and len(ordered) < max_stops:
                    remaining.sort(key=lambda s: _haversine(
                        cur_lat, cur_lng, float(s["lat"]), float(s["lng"])))
                    nxt = remaining.pop(0)
                    ordered.append(nxt)
                    cur_lat, cur_lng = float(nxt["lat"]), float(nxt["lng"])
                stops = ordered
            else:
                stops = stops[:max_stops]

            if stops:
                parts = [f"{i+1}. {s['title']} — {s['address']}" for i, s in enumerate(stops)]
                summary = f"Optimized route with {len(stops)} stop(s):\n" + "\n".join(parts)
            else:
                summary = "No active pickups assigned to you right now."
            return {"count": len(stops), "stops": stops, "summary": summary}
        finally:
            db.close()

    return await _run(_sync)



async def _get_dispatch_queue(user_id: str, max_items: int = 20) -> dict:
    """Dispatcher: open food requests + unclaimed donation listings (Supabase)."""
    from backend.ai_engine import supabase_get

    if not (user_id or "").strip():
        return {"error": "Invalid user_id"}

    limit = max(1, min(int(max_items or 20), 50))
    try:
        open_requests = await supabase_get("food_listings", {
            "listing_type": "eq.request",
            "status": "in.(approved,active,pending)",
            "select": (
                "id,user_id,title,category,quantity,unit,full_address,location,"
                "community_id,communities(id,name),status,created_at,expiry_date"
            ),
            "order": "created_at.desc",
            "limit": str(limit),
        })
        unclaimed_listings = await supabase_get("food_listings", {
            "listing_type": "eq.donation",
            "status": "in.(approved,active)",
            "select": (
                "id,title,category,quantity,unit,full_address,location,"
                "pickup_by,community_id,created_at"
            ),
            "order": "created_at.desc",
            "limit": str(limit),
        })
    except Exception as exc:
        return {"error": f"dispatch queue failed: {exc}"}

    reqs = []
    for r in (open_requests or []):
        community = r.get("communities")
        if isinstance(community, list):
            community = community[0] if community else None
        cname = (community or {}).get("name") if isinstance(community, dict) else None
        reqs.append({
            "id": r.get("id"),
            "recipient_id": r.get("user_id"),
            "title": r.get("title"),
            "category": r.get("category"),
            "quantity": r.get("quantity"),
            "unit": r.get("unit"),
            "address": r.get("full_address") or r.get("location"),
            "status": r.get("status"),
            "created_at": r.get("created_at"),
            "needed_by": r.get("expiry_date"),
            "community_id": r.get("community_id"),
            "community_name": cname,
        })

    lst = [{
        "id": l.get("id"),
        "title": l.get("title"),
        "category": l.get("category"),
        "address": l.get("full_address") or l.get("location"),
        "qty": l.get("quantity"),
        "unit": l.get("unit"),
        "pickup_by": l.get("pickup_by"),
    } for l in (unclaimed_listings or [])]

    summary = (
        f"Dispatch queue: {len(reqs)} open request(s) and "
        f"{len(lst)} unclaimed listing(s) need attention."
    )
    return {
        "open_requests": reqs,
        "unclaimed_listings": lst,
        "summary": summary,
    }


async def _get_platform_stats(user_id: str) -> dict:
    """Admin: high-level metrics + encouragement-ready stats (Supabase)."""
    from backend.ai_engine import supabase_get

    if not (user_id or "").strip():
        return {"error": "Invalid user_id"}

    try:
        admin_rows = await supabase_get("users", {
            "id": f"eq.{user_id}",
            "select": "id,is_admin",
            "limit": "1",
        })
        admin = (admin_rows or [{}])[0]
        if not admin.get("is_admin"):
            return {"error": "Admin role required"}

        open_requests = await supabase_get("food_listings", {
            "listing_type": "eq.request",
            "status": "in.(approved,active,pending)",
            "select": "id,created_at",
            "order": "created_at.desc",
            "limit": "500",
        })
        active_listings = await supabase_get("food_listings", {
            "listing_type": "eq.donation",
            "status": "in.(approved,active)",
            "select": "id,created_at",
            "order": "created_at.desc",
            "limit": "500",
        })
        users = await supabase_get("users", {
            "select": "id,created_at",
            "order": "created_at.desc",
            "limit": "1000",
        })
    except Exception as exc:
        return {"error": f"platform stats failed: {exc}"}

    now = _utcnow()
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)

    def _parse_dt(value):
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except Exception:
            return None

    user_rows = users or []
    listing_rows = active_listings or []
    request_rows = open_requests or []

    total_users = len(user_rows)
    new_users_7d = sum(
        1 for u in user_rows
        if (_parse_dt(u.get("created_at")) or now) >= last_7d
    )
    listings_24h = sum(
        1 for l in listing_rows
        if (_parse_dt(l.get("created_at")) or now) >= last_24h
    )
    open_request_count = len(request_rows)
    active_count = len(listing_rows)

    summary = (
        f"Platform health: {total_users} members, +{new_users_7d} this week. "
        f"{active_count} live donations (+{listings_24h} in 24h). "
        f"{open_request_count} open food request(s)."
    )
    return {
        "total_users": total_users,
        "new_users_7d": new_users_7d,
        "active_listings": active_count,
        "listings_24h": listings_24h,
        "open_requests": open_request_count,
        "summary": summary,
    }


async def _get_profile_gaps(user_id: str) -> dict:
    """Return profile fields the user has not filled (Supabase-backed)."""
    from backend.tools import _get_profile_gaps as _impl
    return await _impl(user_id=user_id)



# ---------------------------------------------------------------------------
# GPS voice-location search (urgency + distance ranked)
# ---------------------------------------------------------------------------

async def _search_food_by_location(
    lat: float,
    lng: float,
    food_type: Optional[str] = None,
    max_results: int = 10,
    urgency_weight: float = 0.4,
    **_ignored,
) -> dict:
    """Live-GPS search. Ranks results by a blend of distance and urgency.

    No radius cutoff — all available rows with coordinates are ranked.
    Legacy ``radius_km`` in ``_ignored`` is discarded.
    """
    from backend.app import SessionLocal
    from backend.models import FoodResource, FoodCategory

    try:
        lat = float(lat)
        lng = float(lng)
    except (TypeError, ValueError):
        return {"error": "lat/lng must be numeric"}

    w = max(0.0, min(1.0, float(urgency_weight)))

    def _sync() -> dict:
        db = SessionLocal()
        try:
            q = db.query(FoodResource).filter(FoodResource.status == "available")
            if food_type:
                try:
                    cat = FoodCategory(food_type.lower())
                    q = q.filter(FoodResource.category == cat)
                except ValueError:
                    pass
            rows = q.order_by(FoodResource.created_at.desc()).limit(500).all()

            candidates = []
            now = _utcnow()
            for r in rows:
                if r.coords_lat is None or r.coords_lng is None:
                    continue
                dist = _haversine(lat, lng, float(r.coords_lat), float(r.coords_lng))
                # urgency: combine stored urgency_score with a time-to-expire bonus
                stored = float(r.urgency_score or 0)  # 0..100
                deadline = r.pickup_window_end or r.expiration_date
                time_urg = 0.0
                if deadline:
                    hrs = max(0.0, (deadline - now).total_seconds() / 3600)
                    # 0h -> 100, 48h+ -> 0
                    time_urg = max(0.0, 100.0 - (hrs / 48.0 * 100.0))
                urgency = max(stored, time_urg)
                candidates.append((r, dist, urgency))

            if not candidates:
                return {
                    "results": [], "total": 0,
                    "summary": "No available food found right now.",
                }

            max_d = max(c[1] for c in candidates) or 1.0
            max_u = max(c[2] for c in candidates) or 1.0
            scored = []
            for r, d, u in candidates:
                score = (1 - w) * (d / max_d) + w * (1 - (u / max_u))
                deadline = r.pickup_window_end or r.expiration_date
                scored.append({
                    "id": r.id,
                    "title": r.title,
                    "category": r.category.value if r.category else None,
                    "quantity": r.qty,
                    "unit": r.unit,
                    "address": r.address,
                    "distance_km": round(d, 2),
                    "urgency_score": round(u, 1),
                    "deadline": deadline.isoformat() if deadline else None,
                    "latitude": r.coords_lat,
                    "longitude": r.coords_lng,
                    "_score": round(score, 4),
                })
            scored.sort(key=lambda x: x["_score"])
            scored = scored[:max_results]

            parts = [
                f"{i+1}. {x['title']} — {x['distance_km']} km, urgency {x['urgency_score']}/100"
                for i, x in enumerate(scored)
            ]
            return {
                "results": scored,
                "total": len(scored),
                "urgency_weight": w,
                "origin": {"lat": lat, "lng": lng},
                "summary": "Top matches by urgency + distance:\n" + "\n".join(parts),
            }
        finally:
            db.close()

    return await _run(_sync)


# ---------------------------------------------------------------------------
# Smart pickup route optimiser (nearest-neighbour + optional Mapbox Optimization)
# ---------------------------------------------------------------------------

async def _optimize_pickup_route(
    user_id: Optional[str] = None,
    origin_lat: Optional[float] = None,
    origin_lng: Optional[float] = None,
    listing_ids: Optional[list[int]] = None,
    profile: str = "driving",
) -> dict:
    """Optimise a multi-stop pickup route for a volunteer/driver.

    Resolves stops from:
      (a) explicit listing_ids, else
      (b) the user's currently-claimed FoodResources.
    Origin defaults to the user's saved coords. Returns stop order plus a
    ``frontend_hint`` the browser can feed into window.RouteOptimizer /
    DirectionsAPI for live Mapbox turn-by-turn.
    """
    from backend.app import SessionLocal
    from backend.models import User, FoodResource

    def _sync() -> dict:
        db = SessionLocal()
        try:
            uid = _to_int(user_id) if user_id else None
            user = db.query(User).filter(User.id == uid).first() if uid else None
            o_lat = origin_lat if origin_lat is not None else (user.coords_lat if user else None)
            o_lng = origin_lng if origin_lng is not None else (user.coords_lng if user else None)
            if o_lat is None or o_lng is None:
                return {"error": "origin coords required (origin_lat/origin_lng or user profile)"}

            q = db.query(FoodResource)
            if listing_ids:
                q = q.filter(FoodResource.id.in_(listing_ids))
            elif uid is not None:
                q = q.filter(FoodResource.recipient_id == uid).filter(
                    FoodResource.status.in_(["claimed", "approved", "pending", "en_route"]))
            else:
                return {"error": "provide listing_ids or user_id"}

            rows = q.all()
            stops: list[dict] = []
            for r in rows:
                if r.coords_lat is None or r.coords_lng is None:
                    continue
                stops.append({
                    "listing_id": r.id,
                    "title": r.title,
                    "address": r.address,
                    "lat": float(r.coords_lat),
                    "lng": float(r.coords_lng),
                    "pickup_by": r.pickup_window_end.isoformat() if r.pickup_window_end else None,
                })
            return {"origin": (float(o_lat), float(o_lng)), "stops": stops, "profile": profile}
        finally:
            db.close()

    prep = await _run(_sync)
    if "error" in prep:
        return prep
    origin_tuple = prep["origin"]
    stops = prep["stops"]
    profile = prep["profile"] if prep.get("profile") in ("driving", "walking", "cycling") else "driving"

    if not stops:
        return {"count": 0, "stops": [], "summary": "No eligible pickups to route."}

    # Nearest-neighbour order from origin
    ordered: list[dict] = []
    remaining = list(stops)
    cur_lat, cur_lng = origin_tuple
    total_km = 0.0
    while remaining:
        remaining.sort(key=lambda s: _haversine(cur_lat, cur_lng, s["lat"], s["lng"]))
        nxt = remaining.pop(0)
        leg = _haversine(cur_lat, cur_lng, nxt["lat"], nxt["lng"])
        nxt["leg_km"] = round(leg, 2)
        total_km += leg
        ordered.append(nxt)
        cur_lat, cur_lng = nxt["lat"], nxt["lng"]

    # Optional: hit Mapbox Optimization for a better order (up to 12 waypoints).
    mapbox_order: Optional[list[int]] = None
    if MAPBOX_TOKEN and len(ordered) <= 11:
        try:
            coords = f"{origin_tuple[1]},{origin_tuple[0]};" + ";".join(
                f"{s['lng']},{s['lat']}" for s in ordered
            )
            url = f"https://api.mapbox.com/optimized-trips/v1/mapbox/{profile}/{coords}"
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(url, params={
                    "access_token": MAPBOX_TOKEN,
                    "source": "first",
                    "roundtrip": "false",
                    "overview": "simplified",
                })
                if resp.status_code == 200:
                    data = resp.json()
                    trips = data.get("trips") or []
                    waypoints = data.get("waypoints") or []
                    if trips and waypoints:
                        # waypoints[0] is the origin; 1..N map back to the input stops.
                        mapbox_order = [wp.get("waypoint_index") for wp in waypoints[1:]]
                        # Re-order using Mapbox's optimised sequence
                        pairs = sorted(
                            enumerate(ordered),
                            key=lambda iv: mapbox_order.index(iv[0]) if iv[0] in mapbox_order else iv[0],
                        )
                        ordered = [p[1] for p in pairs]
                        # Recompute cumulative leg distances
                        cur_lat, cur_lng = origin_tuple
                        total_km = 0.0
                        for s in ordered:
                            leg = _haversine(cur_lat, cur_lng, s["lat"], s["lng"])
                            s["leg_km"] = round(leg, 2)
                            total_km += leg
                            cur_lat, cur_lng = s["lat"], s["lng"]
        except Exception as exc:  # pragma: no cover
            logger.warning("Mapbox Optimization failed, using nearest-neighbour: %s", exc)

    summary_lines = [
        f"{i+1}. {s['title'] or 'stop'} — {s['leg_km']} km leg, pickup by {s.get('pickup_by') or 'no deadline'}"
        for i, s in enumerate(ordered)
    ]
    summary = (f"Optimized route: {len(ordered)} stop(s), ~{round(total_km, 1)} km total "
               f"(profile={profile}).\n" + "\n".join(summary_lines))

    return {
        "count": len(ordered),
        "origin": {"lat": origin_tuple[0], "lng": origin_tuple[1]},
        "profile": profile,
        "total_km": round(total_km, 2),
        "stops": ordered,
        "mapbox_optimized": mapbox_order is not None,
        "frontend_hint": {
            "component": "RouteOptimizer",
            "waypoints": [[s["lng"], s["lat"]] for s in ordered],
            "origin": [origin_tuple[1], origin_tuple[0]],
        },
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Safe natural-language -> read-only SQL query tool
# ---------------------------------------------------------------------------

# Whitelist: entity -> (SQLAlchemy model attr path, allowed filter fields, allowed sort fields)
_QUERY_WHITELIST: dict[str, dict] = {
    "listings": {
        "model_import": ("backend.models", "FoodResource"),
        "fields": {
            "id": "id", "donor_id": "donor_id", "recipient_id": "recipient_id",
            "category": "category", "status": "status", "qty": "qty",
            "urgency_score": "urgency_score", "expiration_date": "expiration_date",
            "pickup_window_end": "pickup_window_end", "created_at": "created_at",
            "title": "title", "address": "address",
        },
        "select": ["id", "donor_id", "recipient_id", "title", "category",
                   "status", "qty", "unit", "address", "urgency_score",
                   "pickup_window_end", "expiration_date", "created_at"],
    },
    "requests": {
        # Handled via Supabase food_listings (listing_type=request); no SQLAlchemy model.
        "model_import": None,
        "supabase_table": "food_listings",
        "supabase_filters": {"listing_type": "eq.request"},
        "fields": {
            "id": "id", "user_id": "user_id", "category": "category",
            "status": "status", "quantity": "quantity", "title": "title",
            "created_at": "created_at",
        },
        "select": ["id", "user_id", "title", "category", "status", "quantity",
                   "unit", "full_address", "created_at"],
    },
    "centers": {
        "model_import": ("backend.models", "DistributionCenter"),
        "fields": {
            "id": "id", "owner_id": "owner_id", "is_active": "is_active",
            "name": "name", "address": "address", "verified_by_aglf": "verified_by_aglf",
        },
        "select": ["id", "name", "address", "phone", "is_active",
                   "verified_by_aglf", "school_partner"],
    },
    "users": {
        # NOTE: only non-PII fields are exposed in the projection
        "model_import": ("backend.models", "User"),
        "fields": {
            "id": "id", "role": "role", "trust_score": "trust_score",
            "school_partner": "school_partner", "verified_by_aglf": "verified_by_aglf",
            "created_at": "created_at",
        },
        "select": ["id", "name", "role", "trust_score", "verified_by_aglf",
                   "school_partner", "created_at"],
    },
}

_ALLOWED_OPS = {"eq", "ne", "gt", "gte", "lt", "lte", "in", "like"}
_MAX_QUERY_ROWS = 100


async def _run_safe_query(
    entity: str,
    filters: Optional[list[dict]] = None,
    order_by: Optional[str] = None,
    descending: bool = True,
    limit: int = 25,
) -> dict:
    """Execute a read-only, whitelisted query.

    This is the entry point used by the conversation engine to translate a
    natural-language request into a bounded SQL SELECT. The model supplies
    ``entity`` (one of the whitelisted tables), a list of ``filters``
    (each ``{field, op, value}``), plus optional ``order_by`` / ``descending``
    / ``limit``. No free-form SQL is accepted, so SQL injection is impossible
    by construction.
    """
    spec = _QUERY_WHITELIST.get((entity or "").lower())
    if not spec:
        return {"error": f"entity must be one of: {sorted(_QUERY_WHITELIST)}"}

    try:
        limit = max(1, min(int(limit or 25), _MAX_QUERY_ROWS))
    except (TypeError, ValueError):
        limit = 25

    # Supabase-backed entities (no SQLAlchemy model)
    if not spec.get("model_import") and spec.get("supabase_table"):
        from backend.ai_engine import supabase_get

        params = {
            "select": ",".join(spec.get("select") or ["id"]),
            "order": f"{order_by or 'created_at'}.{'desc' if descending else 'asc'}",
            "limit": str(limit),
        }
        for key, value in (spec.get("supabase_filters") or {}).items():
            params[key] = value
        for f in (filters or []):
            fname = str(f.get("field", "")).strip()
            op = str(f.get("op", "eq")).lower()
            value = f.get("value")
            if fname not in (spec.get("fields") or {}):
                return {"error": f"field '{fname}' not allowed for {entity}"}
            if op not in _ALLOWED_OPS:
                return {"error": f"op '{op}' not allowed"}
            col = spec["fields"][fname]
            if op == "eq":
                params[col] = f"eq.{value}"
            elif op == "ne":
                params[col] = f"neq.{value}"
            elif op == "in":
                vals = value if isinstance(value, (list, tuple)) else [value]
                params[col] = f"in.({','.join(str(v) for v in vals)})"
            elif op == "like":
                params[col] = f"ilike.*{value}*"
            elif op in {"gt", "gte", "lt", "lte"}:
                params[col] = f"{op}.{value}"
        try:
            rows = await supabase_get(spec["supabase_table"], params)
        except Exception as exc:
            return {"error": f"query failed: {exc}"}
        return {
            "entity": entity,
            "count": len(rows or []),
            "rows": rows or [],
            "summary": f"Found {len(rows or [])} {entity}.",
        }

    mod_name, cls_name = spec["model_import"]
    try:
        model = getattr(__import__(mod_name, fromlist=[cls_name]), cls_name)
    except Exception as exc:
        return {"error": f"model import failed: {exc}"}

    fields = spec["fields"]
    select_cols = spec["select"]

    def _sync() -> dict:
        from backend.app import SessionLocal
        db = SessionLocal()
        try:
            q = db.query(model)
            applied: list[dict] = []
            for f in (filters or []):
                fname = str(f.get("field", "")).strip()
                op = str(f.get("op", "eq")).lower()
                value = f.get("value")
                if fname not in fields:
                    return {"error": f"field '{fname}' not allowed for {entity}"}
                if op not in _ALLOWED_OPS:
                    return {"error": f"op '{op}' not allowed"}
                col = getattr(model, fields[fname])
                try:
                    if op == "eq":
                        q = q.filter(col == value)
                    elif op == "ne":
                        q = q.filter(col != value)
                    elif op == "gt":
                        q = q.filter(col > value)
                    elif op == "gte":
                        q = q.filter(col >= value)
                    elif op == "lt":
                        q = q.filter(col < value)
                    elif op == "lte":
                        q = q.filter(col <= value)
                    elif op == "in":
                        if not isinstance(value, (list, tuple)):
                            return {"error": "op 'in' requires a list value"}
                        q = q.filter(col.in_(list(value)[:50]))
                    elif op == "like":
                        if not isinstance(value, str):
                            return {"error": "op 'like' requires a string value"}
                        q = q.filter(col.like(f"%{value}%"))
                    applied.append({"field": fname, "op": op, "value": value})
                except Exception as exc:
                    return {"error": f"filter failed on {fname}: {exc}"}

            if order_by:
                if order_by not in fields:
                    return {"error": f"order_by '{order_by}' not allowed"}
                col = getattr(model, fields[order_by])
                q = q.order_by(col.desc() if descending else col.asc())

            rows = q.limit(limit).all()
            out = []
            for r in rows:
                item = {}
                for c in select_cols:
                    val = getattr(r, c, None)
                    if hasattr(val, "value"):  # Enum
                        val = val.value
                    if isinstance(val, datetime):
                        val = val.isoformat()
                    item[c] = val
                out.append(item)
            return {
                "entity": entity,
                "count": len(out),
                "results": out,
                "filters_applied": applied,
                "order_by": order_by,
                "descending": bool(descending),
                "limit": limit,
            }
        finally:
            db.close()

    return await _run(_sync)


# ---------------------------------------------------------------------------
# Action tools (write operations the AI can perform on the user's behalf)
# ---------------------------------------------------------------------------

class _ParseError(ValueError):
    """Raised when a user-supplied ISO datetime fails to parse."""


def _parse_iso(value) -> Optional[datetime]:
    """Parse an ISO-8601 string to naive UTC datetime.

    Returns None only when value is falsy. Raises _ParseError on bad input
    so callers can surface a clear error instead of silently dropping it.
    """
    if not value:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value
    try:
        s = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
    except (TypeError, ValueError) as exc:
        raise _ParseError(f"Invalid ISO datetime: {value!r}") from exc
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _validate_listing_timestamps(
    pickup_window_start: Optional[str],
    pickup_window_end: Optional[str],
    expiration_date: Optional[str],
) -> Optional[dict]:
    """Return ``{"error": "..."}`` for bad timestamps, or ``None`` if OK.

    Reject inputs BEFORE we touch the database so the AI gets a clear
    error message it can relay to the donor (past dates, reversed
    windows, unparseable ISO strings). This runs on both the Supabase
    and legacy SQL post paths so behaviour is consistent regardless of
    which backend actually stores the listing.
    """
    # Coerce date-only today/past → tomorrow before comparing to UTC now.
    # Models often pass expiration=today for "Made today", which is midnight
    # and fails as "already past" later the same UTC day.
    try:
        from backend.ai.conversation_flow import normalize_expiration_date_for_post
        expiration_date = normalize_expiration_date_for_post(expiration_date)
    except Exception:
        pass

    try:
        win_start = _parse_iso(pickup_window_start)
        win_end = _parse_iso(pickup_window_end)
        exp_dt = _parse_iso(expiration_date)
    except _ParseError as exc:
        return {"error": str(exc)}

    now = _utcnow()
    if win_end is not None and win_end <= now:
        return {
            "error": (
                "pickup_window_end is in the past — the listing would be "
                f"expired on creation. Today is {now.strftime('%Y-%m-%d %H:%M UTC')}; "
                "please pick a future pickup window (e.g. the next 24-48 hours)."
            )
        }
    if win_start is not None and win_end is not None and win_start > win_end:
        return {"error": "pickup_window_start must be before pickup_window_end"}
    if exp_dt is not None and exp_dt <= now:
        # Date-only expiries arrive as midnight — compare calendar days so
        # "good until today" is still valid for the rest of the day.
        exp_day = exp_dt.date() if hasattr(exp_dt, "date") else None
        today = now.date()
        if exp_day is None or exp_day < today:
            return {
                "error": (
                    "expiration_date is in the past — listing would be expired. "
                    f"Today is {now.strftime('%Y-%m-%d %H:%M UTC')}. "
                    "Ask for a good-until date of today or later "
                    "(any wording is fine — tomorrow, in 2 months, Aug 30)."
                )
            }
    return None


async def _claim_listing(
    user_id: str,
    listing_id,
    quantity: Optional[object] = None,
    **_ignored,
) -> dict:
    """Claim a listing — Supabase (UUID) or legacy SQLite (int)."""
    uid = str(user_id or "").strip()
    lid = listing_id

    if _is_supabase_user_id(uid):
        resolved = _resolve_supabase_listing_id(lid, uid)
        if resolved:
            lid = resolved
        elif lid is not None and not _UUID_RE.match(str(lid)):
            return {
                "error": (
                    "Listing not found. Search for food first, then use the "
                    "list number (1, 2, 3…) from those results."
                ),
            }

    if _UUID_RE.match(str(lid or "")):
        from backend.tools import _claim_food_listing
        result = await _claim_food_listing(
            user_id=uid,
            listing_id=str(lid),
            quantity=quantity,
        )
        if result.get("success"):
            out = {
                "success": True,
                "listing_id": result.get("listing_id"),
                "claim_id": result.get("claim_id"),
                "quantity": result.get("quantity"),
                "summary": result.get("summary"),
                "title": result.get("title"),
                "pickup_location": result.get("pickup_location"),
                "pickup_deadline": result.get("pickup_deadline"),
            }
            if result.get("already_claimed"):
                out["already_claimed"] = True
                out["message"] = result.get("message")
            return out
        err = result.get("error", "Could not complete the claim.")
        hint = "Tell the user exactly what went wrong — do not re-run search unless they ask."
        if "already have an active claim" in str(err).lower():
            hint = "Offer cancel_claim first if they want to switch listings."
        elif "your own listing" in str(err).lower():
            hint = "They cannot claim their own donation — pick a different listing."
        return {"error": err, "next_step": hint}

    if uid and not uid.isdigit():
        return {
            "error": (
                "Listing not found. Pass the UUID id from search results, "
                "or the display list number (1, 2, 3…) after search_food_near_user."
            ),
        }

    from backend.app import SessionLocal, pending_confirmations, send_sms, generate_reset_code, auto_release_claim
    from backend.models import User, FoodResource
    from threading import Timer

    uid = _to_int(user_id)
    if uid is None:
        return {"error": "Invalid user_id"}

    def _sync() -> dict:
        db = SessionLocal()
        try:
            lid = int(listing_id)
            # Role guard: donors/dispatchers/etc. cannot claim food. Claiming is
            # a recipient action. Refuse early with a clear message so the AI
            # can tell the user to sign in as a recipient instead of attempting
            # the claim and getting a generic failure later.
            caller = db.query(User).filter(User.id == uid).first()
            if caller and caller.role:
                role_value = caller.role.value if hasattr(caller.role, "value") else str(caller.role)
                if role_value == "donor":
                    return {
                        "error": (
                            "This account is a donor account and cannot claim "
                            "food. Please sign in as a recipient to claim "
                            "listings."
                        ),
                        "reason": "wrong_role",
                        "current_role": "donor",
                        "required_role": "recipient",
                    }

            # Atomic claim: only one concurrent caller can transition
            # 'available' -> 'pending_confirmation'. Prevents the read-then-
            # update race that could let two users both "win" a listing.
            now = _utcnow()
            updated = (
                db.query(FoodResource)
                .filter(
                    FoodResource.id == lid,
                    FoodResource.status == "available",
                    FoodResource.donor_id != uid,
                )
                .update(
                    {
                        FoodResource.status: "pending_confirmation",
                        FoodResource.recipient_id: uid,
                        FoodResource.claimed_at: now,
                    },
                    synchronize_session=False,
                )
            )
            if not updated:
                # Figure out why the update matched nothing.
                item = db.query(FoodResource).filter(FoodResource.id == lid).first()
                db.rollback()
                if not item:
                    return {"error": "Listing not found"}
                if item.donor_id == uid:
                    return {"error": "You cannot claim your own listing."}
                return {"error": f"Listing is not available (status={item.status})"}

            # Pre-flight: claimant must have phone. If not, undo the claim.
            claimant = db.query(User).filter(User.id == uid).first()
            if not claimant or not claimant.phone:
                (
                    db.query(FoodResource)
                    .filter(FoodResource.id == lid, FoodResource.recipient_id == uid)
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
                return {"error": "Phone number required on your profile to claim food. Update profile first."}

            db.commit()
            item = db.query(FoodResource).filter(FoodResource.id == lid).first()
            code = generate_reset_code(4)
            pending_confirmations[item.id] = {
                "code": code,
                "recipient_id": uid,
                "expires_at": now + timedelta(minutes=5),
            }

            sms_ok = False
            try:
                sms_ok = bool(send_sms(
                    claimant.phone,
                    f"You claimed '{item.title}'. Reply with code {code} within 5 minutes to confirm. "
                    f"Address: {item.address}",
                ))
                donor = db.query(User).filter(User.id == item.donor_id).first()
                if donor and donor.phone:
                    send_sms(donor.phone,
                             f"Your listing '{item.title}' was claimed by {claimant.name}. Awaiting confirmation.")
            except Exception as exc:  # pragma: no cover
                logger.warning("claim SMS delivery failed: %s", exc)

            try:
                t = Timer(300.0, auto_release_claim, args=[item.id])
                t.daemon = True  # do not block interpreter shutdown
                t.start()
            except Exception:
                pass

            # When SMS delivery is unavailable (e.g. Twilio not configured),
            # surface the code in the tool result so the assistant can show
            # it to the user inline. Safe because the chat session is
            # already authenticated to this user via JWT.
            if sms_ok:
                summary = (
                    f"Claim initiated for '{item.title}'. A 4-digit code was "
                    f"texted to your phone. Reply here with 'confirm <code>' "
                    f"within 5 minutes or it auto-releases."
                )
                return {
                    "success": True,
                    "listing_id": item.id,
                    "status": item.status,
                    "needs_confirmation": True,
                    "summary": summary,
                }
            # SMS fallback: include the code in the result so the AI can
            # relay it to the user in chat.
            logger.warning("SMS unavailable; relaying claim code in chat for listing %s", item.id)
            return {
                "success": True,
                "listing_id": item.id,
                "status": item.status,
                "needs_confirmation": True,
                "sms_delivered": False,
                "confirm_code": code,
                "summary": (
                    f"Claim initiated for '{item.title}' (listing #{item.id}). "
                    f"SMS delivery is currently unavailable, so your confirmation "
                    f"code is {code}. Reply with 'confirm {code}' within 5 minutes "
                    f"or the claim auto-releases. Pickup address: {item.address}."
                ),
            }
        except Exception as exc:
            logger.exception("claim_listing failed")
            db.rollback()
            return {"error": "Could not complete the claim. Please try again."}
        finally:
            db.close()

    return await _run(_sync)


async def _claim_listings(
    user_id: str,
    items: list,
    **_ignored,
) -> dict:
    """Claim two or more listings, each with its own quantity."""
    if not (user_id or "").strip():
        return {"error": "Invalid user_id", "success": False}
    if not isinstance(items, list) or len(items) < 2:
        return {
            "error": "items must contain at least 2 claims",
            "success": False,
            "next_step": "Use claim_listing for a single listing.",
        }

    claimed: list[dict] = []
    failed: list[dict] = []
    for idx, raw in enumerate(items, start=1):
        if not isinstance(raw, dict):
            failed.append({"index": idx, "error": "invalid item"})
            continue
        lid = raw.get("listing_id")
        if lid is None or str(lid).strip() == "":
            failed.append({
                "index": idx,
                "title": raw.get("title"),
                "error": "missing listing_id",
            })
            continue
        qty = raw.get("quantity")
        if qty is None:
            qty = raw.get("qty")
        qty_arg: object = qty
        if isinstance(qty, str) and qty.strip().lower() in {
            "all", "everything", "todo", "todos", "toda", "todas",
            "all of them", "all of it",
        }:
            qty_arg = qty.strip().lower()
        else:
            try:
                qty_int = int(float(qty)) if qty is not None else None
            except (TypeError, ValueError):
                qty_int = None
            if qty_int is None or qty_int <= 0:
                failed.append({
                    "index": idx,
                    "listing_id": lid,
                    "title": raw.get("title"),
                    "error": "missing or invalid quantity",
                })
                continue
            qty_arg = qty_int

        result = await _claim_listing(
            user_id=str(user_id),
            listing_id=lid,
            quantity=qty_arg,
        )
        if isinstance(result, dict) and result.get("success"):
            claimed.append({
                "listing_id": result.get("listing_id") or lid,
                "title": result.get("title") or raw.get("title"),
                "quantity": result.get("quantity") or (
                    qty_arg if isinstance(qty_arg, int) else None
                ),
                "claim_id": result.get("claim_id"),
                "awaiting_approval": bool(result.get("awaiting_approval")),
                "already_claimed": bool(result.get("already_claimed")),
            })
            try:
                from backend.ai.conversation_flow import (
                    update_last_search_listing_after_claim,
                )
                remaining = result.get("remaining_on_listing")
                update_last_search_listing_after_claim(
                    str(user_id),
                    str(result.get("listing_id") or lid),
                    remaining,
                    fully_claimed=bool(result.get("already_claimed"))
                    or (
                        remaining is not None
                        and float(remaining) <= 0
                    ),
                )
            except Exception:
                pass
        else:
            err = (result or {}).get("error") or (result or {}).get("message") or "failed"
            failed.append({
                "index": idx,
                "listing_id": lid,
                "title": raw.get("title"),
                "error": err,
            })

    ok = len(claimed) > 0
    summary_bits = [f"Claimed {len(claimed)}/{len(items)} listings"]
    if claimed:
        names = ", ".join(
            f"{c.get('quantity')}× {c.get('title') or c.get('listing_id')}"
            for c in claimed
        )
        summary_bits.append(f"— {names}.")
        if any(c.get("awaiting_approval") for c in claimed):
            summary_bits.append("Please wait for admin approval before pickup.")
        else:
            summary_bits.append("Ready for pickup from Receipts & Activity.")
    if failed:
        summary_bits.append(
            f"{len(failed)} failed: "
            + "; ".join(
                f"{f.get('title') or f.get('listing_id') or f.get('index')}: {f.get('error')}"
                for f in failed
            )
        )
    return {
        "success": ok,
        "partial": ok and len(failed) > 0,
        "claimed": claimed,
        "failed": failed,
        "count_claimed": len(claimed),
        "count_failed": len(failed),
        "summary": " ".join(summary_bits),
    }


async def _confirm_claim(user_id: str, listing_id: int = None, code: str = "") -> dict:
    """Finalize a pending claim (SMS code for legacy SQLite, pickup confirm for Supabase)."""
    if _is_supabase_user_id(user_id):
        from backend.tools import _confirm_claim as _impl
        uid = str(user_id).strip()
        resolved_lid = _resolve_supabase_listing_id(listing_id, uid) if listing_id is not None else None
        result = await _impl(
            user_id=uid,
            listing_id=resolved_lid,
            claim_id=None,
        )
        if result.get("success"):
            return {
                "success": True,
                "listing_id": result.get("listing_id"),
                "claim_id": result.get("claim_id"),
                "summary": result.get("summary"),
            }
        return {"error": result.get("error", "Could not confirm the claim.")}

    from backend.app import SessionLocal, pending_confirmations, send_sms
    from backend.models import FoodResource, User

    uid = _to_int(user_id)
    if uid is None:
        return {"error": "Invalid user_id"}
    code_clean = str(code or "").strip()
    if not code_clean:
        return {"error": "Confirmation code required"}

    # Resolve listing_id from the in-memory pending map when not provided.
    lid = _to_int(listing_id) if listing_id is not None else None
    if lid is None:
        candidates = [
            (k, v) for k, v in pending_confirmations.items()
            if v.get("recipient_id") == uid and v.get("code") == code_clean
        ]
        if not candidates:
            return {
                "error": (
                    "No pending claim matches that code for your account. "
                    "It may have expired (5 min) or already been confirmed."
                )
            }
        # Pick the most recent (largest id wins as a proxy for newest).
        lid = max(c[0] for c in candidates)

    # Snapshot the resolved listing id for the inner sync closure.
    resolved_lid = lid

    def _sync() -> dict:
        db = SessionLocal()
        try:
            lid = int(resolved_lid)
            confirmation = pending_confirmations.get(lid)
            if not confirmation:
                # Maybe already confirmed or auto-released.
                item = db.query(FoodResource).filter(FoodResource.id == lid).first()
                if item and item.status == "claimed" and item.recipient_id == uid:
                    return {
                        "success": True,
                        "already_confirmed": True,
                        "listing_id": lid,
                        "summary": f"'{item.title}' is already confirmed as claimed.",
                    }
                return {"error": "No pending confirmation for this listing (it may have expired or been released)."}

            if confirmation.get("recipient_id") != uid:
                return {"error": "This confirmation belongs to a different user."}
            if confirmation.get("code") != code_clean:
                return {"error": "Invalid confirmation code"}
            expires_at = confirmation.get("expires_at")
            if expires_at is None or _utcnow() > expires_at:
                pending_confirmations.pop(lid, None)
                return {"error": "Confirmation code expired. Please claim again."}

            item = db.query(FoodResource).filter(FoodResource.id == lid).first()
            if not item:
                return {"error": "Listing not found"}

            # Atomic flip: only succeed if the listing is still
            # pending_confirmation for THIS recipient. Prevents the race
            # where auto_release_claim's Timer flips status back to
            # 'available' between our pending_confirmations lookup above
            # and the commit below — which previously could have produced
            # a 'claimed' listing with a null recipient.
            updated = (
                db.query(FoodResource)
                .filter(
                    FoodResource.id == lid,
                    FoodResource.status == "pending_confirmation",
                    FoodResource.recipient_id == uid,
                )
                .update({FoodResource.status: "claimed"}, synchronize_session=False)
            )
            if not updated:
                pending_confirmations.pop(lid, None)
                db.rollback()
                return {"error": "Claim is no longer pending — it may have been auto-released. Please claim again."}
            db.commit()
            db.refresh(item)
            pending_confirmations.pop(lid, None)

            # ----------------------------------------------------------
            # Post-write verification: re-query the row and confirm the
            # status flip actually persisted with this user as recipient.
            # If a parallel auto-release Timer fired between our atomic
            # update and the commit, or a different process raced us,
            # we'd otherwise tell the user "claim confirmed" while the
            # row sits at status='available'. The atomic UPDATE above
            # already guards against this, but verifying gives us a
            # clear `verified` flag the AI/UI can use to warn instead
            # of celebrating a phantom confirmation.
            # ----------------------------------------------------------
            db.expire_all()
            check = db.query(FoodResource).filter(FoodResource.id == lid).first()
            verify_issues: list[str] = []
            if check is None:
                verify_issues.append("listing row not found on re-query")
            else:
                status_val = (
                    check.status.value
                    if hasattr(check.status, "value")
                    else str(check.status or "")
                )
                if status_val != "claimed":
                    verify_issues.append(f"status={status_val!r} (expected 'claimed')")
                if check.recipient_id != uid:
                    verify_issues.append(
                        f"recipient_id={check.recipient_id!r} (expected {uid})"
                    )
            verified = not verify_issues

            # Only blast confirmation SMS when the post-write check
            # actually agrees the row is now claimed by this user.
            # Otherwise we'd tell both parties "Claim confirmed!" via
            # SMS while telling the chat user "verify failed" — a
            # contradiction that's worse than no SMS at all.
            if verified:
                try:
                    donor = db.query(User).filter(User.id == item.donor_id).first()
                    claimant = db.query(User).filter(User.id == uid).first()
                    if claimant and claimant.phone:
                        send_sms(
                            claimant.phone,
                            f"Claim confirmed! Pick up '{item.title}' at {item.address}. "
                            f"Donor contact: {donor.phone if donor and donor.phone else 'N/A'}",
                        )
                    if donor and donor.phone:
                        send_sms(
                            donor.phone,
                            f"Claim confirmed! {claimant.name if claimant else 'Recipient'} "
                            f"will pick up '{item.title}'.",
                        )
                except Exception as exc:  # pragma: no cover
                    logger.warning("confirm SMS delivery failed: %s", exc)

            if verified:
                summary = f"Claim confirmed for '{item.title}'. You're cleared to pick it up."
            else:
                summary = (
                    f"Claim status flipped for '{item.title}', but a post-write check "
                    f"found issues: " + "; ".join(verify_issues) + ". Please reload and verify."
                )
            return {
                "success": True,
                "listing_id": item.id,
                "status": item.status,
                "verified": verified,
                "verify_issues": verify_issues,
                "summary": summary,
            }
        except Exception as exc:
            logger.exception("confirm_claim failed")
            db.rollback()
            return {"error": "Could not confirm the claim. Please try again."}
        finally:
            db.close()

    return await _run(_sync)


async def _cancel_claim(user_id: str, listing_id: int) -> dict:
    if _is_supabase_user_id(user_id):
        from backend.tools import _cancel_claim as _impl
        uid = str(user_id).strip()
        resolved_lid = _resolve_supabase_listing_id(listing_id, uid)
        result = await _impl(
            user_id=uid,
            listing_id=resolved_lid,
            claim_id=None,
        )
        if result.get("success"):
            return {
                "success": True,
                "listing_id": result.get("listing_id"),
                "claim_id": result.get("claim_id"),
                "summary": result.get("summary"),
            }
        return {"error": result.get("error", "Could not cancel the claim.")}

    from backend.app import SessionLocal, pending_confirmations
    from backend.models import FoodResource

    uid = _to_int(user_id)
    if uid is None:
        return {"error": "Invalid user_id"}

    def _sync() -> dict:
        db = SessionLocal()
        try:
            lid = int(listing_id)
            item = db.query(FoodResource).filter(FoodResource.id == lid).first()
            if not item:
                return {"error": "Listing not found"}
            if item.recipient_id != uid:
                return {"error": "Not your claim"}
            if item.status not in ("claimed", "pending_confirmation", "pending", "approved"):
                return {"error": f"Cannot cancel at status={item.status}"}
            item.status = "available"
            item.recipient_id = None
            item.claimed_at = None
            db.commit()
            # Drop any pending SMS-confirmation code so an old code can't
            # re-confirm the listing after release.
            pending_confirmations.pop(lid, None)

            # ----------------------------------------------------------
            # Post-write verification: re-query and confirm the row is
            # actually back to status='available' with no recipient. If
            # something else races us (a parallel claim from another
            # session), we want to surface it instead of silently
            # claiming "released!".
            # ----------------------------------------------------------
            db.expire_all()
            check = db.query(FoodResource).filter(FoodResource.id == lid).first()
            verify_issues: list[str] = []
            if check is None:
                verify_issues.append("listing row not found on re-query")
            else:
                status_val = (
                    check.status.value
                    if hasattr(check.status, "value")
                    else str(check.status or "")
                )
                if status_val != "available":
                    verify_issues.append(f"status={status_val!r} (expected 'available')")
                if check.recipient_id is not None:
                    verify_issues.append(
                        f"recipient_id={check.recipient_id!r} (expected None)"
                    )
            verified = not verify_issues
            summary = (
                f"Released '{item.title}' back to the community."
                if verified else
                f"Released '{item.title}', but post-check found issues: "
                + "; ".join(verify_issues)
            )
            return {
                "success": True,
                "listing_id": item.id,
                "verified": verified,
                "verify_issues": verify_issues,
                "summary": summary,
            }
        except Exception as exc:
            logger.exception("cancel_claim failed")
            db.rollback()
            return {"error": "Could not cancel the claim. Please try again."}
        finally:
            db.close()

    return await _run(_sync)


async def _update_user_profile(
    user_id: str,
    phone: Optional[str] = None,
    address: Optional[str] = None,
    household_size: Optional[int] = None,
    dietary_restrictions: Optional[list] = None,
    allergies: Optional[list] = None,
    preferred_categories: Optional[list] = None,
    sms_consent_given: Optional[bool] = None,
    notification_preferences: Optional[dict] = None,
) -> dict:
    if _is_supabase_user_id(user_id):
        from backend.tools import _update_user_profile as _impl
        fields: dict = {}
        if phone is not None:
            fields["phone"] = phone
        if address is not None:
            fields["address"] = address
        if dietary_restrictions:
            fields["dietary_restrictions"] = list(dietary_restrictions)
        if allergies:
            fields["allergies"] = list(allergies)
        if sms_consent_given is not None:
            fields["sms_opt_in"] = bool(sms_consent_given)
        if isinstance(notification_preferences, dict):
            if "pickup_reminder" in notification_preferences:
                fields["pickup_reminder_enabled"] = bool(
                    notification_preferences["pickup_reminder"]
                )
            if "sms_notifications" in notification_preferences:
                fields["sms_notifications_enabled"] = bool(
                    notification_preferences["sms_notifications"]
                )
        result = await _impl(user_id=str(user_id).strip(), **fields)
        if result.get("success"):
            updated = result.get("updated_fields") or []
            return {
                "success": True,
                "updated": updated,
                "summary": (
                    f"Done — updated your {', '.join(updated)}. All saved."
                    if updated else "Profile updated."
                ),
            }
        return {"error": result.get("error", "update failed")}

    from backend.app import SessionLocal
    from backend.models import User

    uid = _to_int(user_id)
    if uid is None:
        return {"error": "Invalid user_id"}

    def _sync() -> dict:
        db = SessionLocal()
        try:
            u = db.query(User).filter(User.id == uid).first()
            if not u:
                return {"error": "User not found"}
            changed: list[str] = []
            if phone is not None:
                u.phone = phone.strip() or None; changed.append("phone")
            if address is not None:
                u.address = address.strip() or None; changed.append("address")
            if household_size is not None:
                try:
                    u.household_size = max(1, int(household_size))
                    changed.append("household_size")
                except (TypeError, ValueError):
                    return {"error": f"Invalid household_size: {household_size!r}"}
            # For list fields, an empty list is treated as "no change" rather
            # than a silent wipe. Callers must pass an explicit single-item
            # sentinel like ["none"] (handled client-side) to clear.
            if dietary_restrictions:
                u.dietary_restrictions = json.dumps(list(dietary_restrictions)); changed.append("dietary_restrictions")
            if allergies:
                u.allergies = json.dumps(list(allergies)); changed.append("allergies")
            if preferred_categories:
                u.preferred_categories = json.dumps(list(preferred_categories)); changed.append("preferred_categories")
            if sms_consent_given is not None:
                u.sms_consent_given = bool(sms_consent_given)
                if sms_consent_given:
                    u.sms_consent_date = _utcnow()
                    u.sms_opt_out_date = None
                else:
                    u.sms_opt_out_date = _utcnow()
                changed.append("sms_consent_given")
            if notification_preferences is not None:
                existing = {}
                try:
                    existing = json.loads(u.notification_preferences) if u.notification_preferences else {}
                except (ValueError, TypeError):
                    existing = {}
                if isinstance(notification_preferences, dict):
                    existing.update(notification_preferences)
                    u.notification_preferences = json.dumps(existing); changed.append("notification_preferences")
            if not changed:
                return {"success": False, "summary": "No fields provided.", "updated": []}
            db.commit()
            return {
                "success": True,
                "updated": changed,
                "summary": f"Done — updated your {', '.join(changed)}. All saved.",
            }
        except Exception as exc:
            db.rollback()
            return {"error": f"update failed: {exc}"}
        finally:
            db.close()

    return await _run(_sync)


async def _post_food_request(
    user_id: str,
    title: Optional[str] = None,
    category: Optional[str] = None,
    household_size: int = 1,
    address: Optional[str] = None,
    notes: Optional[str] = None,
    latest_by: Optional[str] = None,
    special_needs: Optional[list] = None,
    dietary_restrictions: Optional[list] = None,
) -> dict:
    """Create a community food request in Supabase (listing_type=request)."""
    from backend.tools import _create_food_request
    from backend.ai_engine import _is_placeholder_address

    if not (user_id or "").strip():
        return {"error": "Invalid user_id"}

    if notes:
        notes = _translate_listing_text(notes)
    if isinstance(special_needs, list):
        special_needs = [_translate_listing_text(s) or s for s in special_needs]
    if isinstance(dietary_restrictions, list):
        dietary_restrictions = [_translate_listing_text(d) or d for d in dietary_restrictions]

    dietary = []
    for item in list(dietary_restrictions or []) + list(special_needs or []):
        s = str(item or "").strip()
        if s and s not in dietary:
            dietary.append(s)

    desc_parts = []
    if notes:
        desc_parts.append(str(notes).strip())
    if dietary:
        desc_parts.append("Dietary needs: " + ", ".join(dietary))
    description = "\n\n".join(desc_parts) or None

    needed = None
    if latest_by:
        needed = str(latest_by).strip()[:10] if "T" in str(latest_by) else str(latest_by).strip()[:10]

    loc = None if _is_placeholder_address(address) else address

    try:
        qty = max(1, int(household_size or 1))
    except (TypeError, ValueError):
        qty = 1

    result = await _create_food_request(
        user_id=str(user_id),
        title=title,
        category=category,
        quantity=qty,
        unit="items",
        description=description,
        needed_by=needed,
        location=loc,
        dietary_tags=dietary or None,
    )

    if result.get("success"):
        return {
            "success": True,
            "request_id": result.get("request_id") or result.get("listing_id"),
            "listing_id": result.get("listing_id"),
            "listing_type": "request",
            "status": result.get("status"),
            "awaiting_approval": bool(result.get("awaiting_approval")),
            "verified": not bool(result.get("awaiting_approval")),
            "verify_issues": (
                ["awaiting admin approval"] if result.get("awaiting_approval") else []
            ),
            "summary": result.get("summary") or "Food request posted.",
            "duplicate_of_recent": bool(result.get("duplicate_of_recent")),
        }

    return {
        "error": result.get("message") or result.get("error") or "Could not post food request.",
        "next_step": (
            "Ask which school/community they belong to, or open /request to submit the form."
            if result.get("error") == "community_required"
            else None
        ),
    }


_AI_TO_SUPABASE_CATEGORY = {
    "produce": "produce",
    "prepared": "prepared",
    "packaged": "pantry",
    "bakery": "bakery",
    "water": "beverages",
    "fruit": "produce",
    "leftovers": "prepared",
}


async def _fallback_community_for_user(user_id: str) -> tuple[Optional[str], Optional[str]]:
    """Best-effort community when the donor profile has none set."""
    from backend.ai_engine import supabase_get, fetch_donor_listing_defaults
    from backend.tools import _resolve_community

    donor = await fetch_donor_listing_defaults(str(user_id))
    if donor.get("community_id"):
        cid, cname = await _resolve_community(None, str(donor["community_id"]))
        if cid:
            return cid, cname

    for name in ("Alameda Unified", "Alameda", "Oakland"):
        cid, cname = await _resolve_community(name, None)
        if cid:
            return cid, cname

    try:
        rows = await supabase_get("communities", {
            "is_active": "eq.true",
            "select": "id,name",
            "limit": "1",
        })
        if rows:
            return str(rows[0]["id"]), rows[0].get("name")
    except Exception:
        pass
    return None, None


async def _check_recipient_role_block(user_id: str) -> Optional[dict]:
    """Return an error payload if the account is a recipient (cannot post).

    Recipients can only claim, not donate. This guard fires BEFORE community
    / expiry / timestamp checks so a recipient never sees confusing
    'confirm the community' errors — they should be told immediately to
    switch to a donor account.

    Uses SessionLocal (legacy int ids) when available, then falls back to
    the Supabase `users` table. Both paths return the same shape so
    `execute_tool` and legacy tests treat them identically.
    """
    if not user_id:
        return None
    try:
        from backend.app import SessionLocal
        from backend.models import User, UserRole
    except Exception:
        SessionLocal = None
        UserRole = None
        User = None

    if SessionLocal is not None and UserRole is not None and User is not None:
        try:
            uid_int = int(str(user_id))
        except (TypeError, ValueError):
            uid_int = None
        if uid_int is not None:
            db = None
            try:
                db = SessionLocal()
                user = db.query(User).filter(User.id == uid_int).first()
                if user is not None and getattr(user, "role", None) == UserRole.RECIPIENT:
                    return {
                        "error": (
                            "This account is a recipient account and cannot "
                            "donate or post food listings. Please sign in as "
                            "a donor to share food."
                        ),
                        "reason": "wrong_role",
                        "current_role": "recipient",
                        "required_role": "donor",
                    }
            except Exception:
                pass
            finally:
                try:
                    if db is not None:
                        db.close()
                except Exception:
                    pass

    try:
        from backend.ai_engine import supabase_get
        rows = await supabase_get("users", {
            "id": f"eq.{user_id}",
            "select": "id,community_role",
            "limit": "1",
        })
        if rows:
            role = str(rows[0].get("community_role") or "").strip().lower()
            if role == "recipient":
                return {
                    "error": (
                        "This account is a recipient account and cannot "
                        "donate or post food listings. Please sign in as "
                        "a donor to share food."
                    ),
                    "reason": "wrong_role",
                    "current_role": "recipient",
                    "required_role": "donor",
                }
    except Exception:
        pass
    return None


async def _post_food_listing_via_supabase(
    user_id: str,
    title: str,
    category: Optional[str] = None,
    qty: float = 1,
    description: Optional[str] = None,
    unit: Optional[str] = None,
    address: Optional[str] = None,
    expiration_date: Optional[str] = None,
    allergens: Optional[list] = None,
    dietary_tags: Optional[list] = None,
    images: Optional[list] = None,
    community_name: Optional[str] = None,
    community_id: Optional[str] = None,
    community_confirmed: bool = False,
    fulfilling_request_id: Optional[str] = None,
    **_ignored,
) -> dict:
    """Post a donation listing to Supabase (UUID user ids)."""
    from backend.tools import _create_food_listing
    from backend.ai_engine import fetch_donor_listing_defaults, _is_placeholder_address

    if _is_placeholder_address(address):
        address = None

    if not (user_id or "").strip():
        return {"error": "Invalid user_id"}

    role_block = await _check_recipient_role_block(str(user_id))
    if role_block is not None:
        return role_block

    confirmed = bool(community_confirmed)

    # Sharing to fulfill an open request → lock to that request's community.
    if fulfilling_request_id:
        from backend.tools import _community_from_food_request
        req_cid, req_cname, req_title = await _community_from_food_request(
            str(fulfilling_request_id)
        )
        if not req_cid:
            return {
                "error": "request_not_found",
                "message": (
                    "Could not find that food request. Open Community Requests "
                    "or pass a valid fulfilling_request_id."
                ),
            }
        community_id = req_cid
        community_name = req_cname or community_name
        confirmed = True
        if not description and req_title:
            description = f"Shared in response to a community request for: {req_title}"

    if community_id and not community_name:
        from backend.tools import _resolve_community
        cid, cname = await _resolve_community(None, community_id)
        if cid:
            community_id, community_name = cid, cname
        else:
            # Name was stuffed into community_id and still failed — clear the
            # bogus id so the confirmed-without-name guard can ask again.
            community_id = None
    elif community_name and not community_id:
        from backend.tools import _resolve_community
        cid, cname = await _resolve_community(community_name, None)
        if cid:
            community_id, community_name = cid, cname
    elif community_name and community_id:
        from backend.tools import _resolve_community
        cid, cname = await _resolve_community(community_name, community_id)
        if cid:
            community_id, community_name = cid, cname
        else:
            community_id = None

    if not confirmed:
        suggested_id, suggested_name = await _fallback_community_for_user(str(user_id))
        return {
            "error": "community_not_confirmed",
            "suggested_community_name": suggested_name,
            "suggested_community_id": suggested_id,
            "next_step": (
                "Ask the donor which community/school this goes under, get explicit "
                "confirmation, then retry with community_name and community_confirmed=true."
            ),
        }

    if confirmed and not community_id and not community_name:
        # Do not silently assign Alameda Unified / first active community.
        # Confirmed without a name usually means the model lied about
        # community_confirmed — force an explicit pick.
        suggested_id, suggested_name = await _fallback_community_for_user(str(user_id))
        return {
            "error": "community_name_required",
            "suggested_community_name": suggested_name,
            "suggested_community_id": suggested_id,
            "next_step": (
                "Ask which community/school this donation goes under, then retry "
                "with that community_name and community_confirmed=true."
            ),
        }

    image_url = None
    if isinstance(images, list):
        from backend.ai.conversation_flow import normalize_public_image_url
        for url in images:
            if not url:
                continue
            norm = normalize_public_image_url(str(url).strip())
            if norm:
                image_url = norm
                break
            if str(url).strip().startswith(("http://", "https://", "/")):
                image_url = str(url).strip()
                break

    supabase_cat = _AI_TO_SUPABASE_CATEGORY.get(
        str(category or "").lower(),
        str(category or "other").lower(),
    )

    result = await _create_food_listing(
        user_id=str(user_id),
        title=title,
        quantity=qty,
        unit=unit or "items",
        category=supabase_cat,
        description=description,
        expiry_date=expiration_date,
        expiration_date=expiration_date,
        location=address,
        dietary_tags=dietary_tags,
        allergens=allergens,
        community_name=community_name,
        community_id=community_id,
        community_confirmed=confirmed,
        image_url=image_url,
        fulfilling_request_id=fulfilling_request_id,
    )

    if result.get("success"):
        out = {
            "success": True,
            "listing_id": result.get("listing_id"),
            "address": result.get("address"),
            "coords_lat": result.get("latitude"),
            "coords_lng": result.get("longitude"),
            "verified": bool(result.get("on_map", True)),
            "verify_issues": [],
            "summary": result.get("summary"),
        }
        if result.get("duplicate_of_recent"):
            out["duplicate_of_recent"] = True
        if result.get("photo_merged"):
            out["photo_merged"] = True
        if result.get("image_url"):
            out["image_url"] = result["image_url"]
            out["has_photo"] = True
        return out

    err = result.get("message") or result.get("error") or "Could not post the listing."
    out: dict = {"error": err}
    err_code = result.get("error")
    if err_code == "community_not_confirmed":
        sug = result.get("suggested_community_name")
        if sug:
            out["suggested_community_name"] = sug
        out["next_step"] = (
            "Ask the donor to confirm that community, then call post_food_listing "
            "with community_name and community_confirmed=true."
        )
    elif err_code == "expiry_date_required":
        out["next_step"] = (
            "Ask when the food expires or its best-by date, then pass "
            "expiration_date as YYYY-MM-DD."
        )
        if result.get("suggested_expiry_date"):
            out["suggested_expiry_date"] = result["suggested_expiry_date"]
    elif err_code == "community_required":
        out["next_step"] = (
            "Ask them to pick an active catalog community by exact name "
            "(call get_active_communities with max_results=100), confirm it, "
            "then retry the post with community_name + community_confirmed=true."
        )
        if isinstance(result.get("active_communities"), list):
            out["active_communities"] = result["active_communities"]
        if result.get("suggested_community_name"):
            out["suggested_community_name"] = result["suggested_community_name"]
    return out


async def _post_food_listings(
    user_id: str,
    items: list,
    community_name: Optional[str] = None,
    community_id: Optional[str] = None,
    community_confirmed: bool = False,
    address: Optional[str] = None,
    **_ignored,
) -> dict:
    """Create two or more listings, each with its own REQUIRED photo."""
    if not (user_id or "").strip():
        return {"error": "Invalid user_id", "success": False}
    if not isinstance(items, list) or len(items) < 2:
        return {
            "error": "items must contain at least 2 listings",
            "success": False,
            "next_step": "Use post_food_listing for a single item.",
        }
    if not community_confirmed:
        return {
            "error": "community_not_confirmed",
            "success": False,
            "next_step": (
                "Confirm community/school, then retry with community_name and "
                "community_confirmed=true."
            ),
        }

    posted: list[dict] = []
    failed: list[dict] = []
    for idx, raw in enumerate(items, start=1):
        if not isinstance(raw, dict):
            failed.append({"index": idx, "error": "invalid item"})
            continue
        title = str(raw.get("title") or "").strip()
        if not title:
            failed.append({"index": idx, "error": "missing title"})
            continue
        try:
            qty = float(raw.get("qty") if raw.get("qty") is not None else raw.get("quantity") or 1)
        except (TypeError, ValueError):
            qty = 1.0
        exp = raw.get("expiration_date") or raw.get("expiry_date")
        images = raw.get("images") if isinstance(raw.get("images"), list) else []
        result = await _post_food_listing(
            user_id=str(user_id),
            title=title,
            category=raw.get("category"),
            qty=qty,
            description=raw.get("description"),
            unit=raw.get("unit") or "items",
            address=address or raw.get("address"),
            expiration_date=exp,
            allergens=raw.get("allergens"),
            dietary_tags=raw.get("dietary_tags"),
            images=images,
            community_name=raw.get("community_name") or community_name,
            community_id=(
                str(raw["community_id"])
                if raw.get("community_id") is not None
                else community_id
            ),
            community_confirmed=True,
        )
        if isinstance(result, dict) and result.get("success") and result.get("listing_id"):
            posted.append({
                "listing_id": result.get("listing_id"),
                "title": title,
                "image_url": result.get("image_url"),
                "has_photo": bool(result.get("image_url") or result.get("has_photo")),
                "duplicate_of_recent": bool(result.get("duplicate_of_recent")),
                "status": result.get("status"),
                "awaiting_approval": bool(result.get("awaiting_approval")),
            })
        else:
            err = (result or {}).get("error") or (result or {}).get("message") or "failed"
            failed.append({"index": idx, "title": title, "error": err})

    ok = len(posted) > 0 and len(failed) == 0
    summary_bits = [f"Posted {len(posted)}/{len(items)} listings"]
    if posted:
        names = ", ".join(
            f"{p.get('title')}{' (photo)' if p.get('has_photo') else ''}"
            for p in posted
        )
        awaiting = sum(1 for p in posted if p.get("awaiting_approval") or str(p.get("status") or "").lower() == "pending")
        if awaiting == len(posted):
            summary_bits.append(
                f"— {names} awaiting admin approval. "
                "Please wait for admin approval."
            )
        elif awaiting > 0:
            summary_bits.append(
                f"— {names}. {awaiting} awaiting admin approval; "
                f"the rest are live. Please wait for admin approval "
                f"on the pending listing{'s' if awaiting != 1 else ''}."
            )
        else:
            summary_bits.append(f"— {names} are live.")
    if failed:
        summary_bits.append(
            f"{len(failed)} failed: "
            + "; ".join(f"{f.get('title') or f.get('index')}: {f.get('error')}" for f in failed)
        )
    if posted:
        try:
            from backend.ai.conversation_flow import set_last_bulk_posted_ids
            set_last_bulk_posted_ids(
                str(user_id),
                [p["listing_id"] for p in posted if p.get("listing_id")],
            )
        except Exception:  # noqa: BLE001
            pass
    return {
        "success": ok,
        "posted": posted,
        "failed": failed,
        "count_posted": len(posted),
        "count_failed": len(failed),
        "summary": " ".join(summary_bits),
    }


async def _post_food_listing(
    user_id: str,
    title: str,
    category: Optional[str] = None,
    qty: float = 1,
    description: Optional[str] = None,
    unit: Optional[str] = None,
    perishability: str = "medium",
    address: Optional[str] = None,
    pickup_window_start: Optional[str] = None,
    pickup_window_end: Optional[str] = None,
    expiration_date: Optional[str] = None,
    allergens: Optional[list] = None,
    dietary_tags: Optional[list] = None,
    images: Optional[list] = None,
    community_name: Optional[str] = None,
    community_id: Optional[str] = None,
    community_confirmed: bool = False,
) -> dict:
    # Coerce date-only today/past → tomorrow so the insert uses a safe day
    # (validation alone is not enough — callers must store the coerced value).
    try:
        from backend.ai.conversation_flow import normalize_expiration_date_for_post
        expiration_date = (
            normalize_expiration_date_for_post(expiration_date) or expiration_date
        )
    except Exception:
        pass

    # Reject bad timestamps BEFORE any DB / auth work so donors get an
    # immediate, actionable error and we don't burn quota on a Supabase
    # insert that would leave a "born-expired" listing.
    ts_error = _validate_listing_timestamps(
        pickup_window_start, pickup_window_end, expiration_date,
    )
    if ts_error is not None:
        return ts_error

    # Role guard before photo so recipients get a clear wrong-role error.
    role_block = await _check_recipient_role_block(str(user_id))
    if role_block is not None:
        return role_block

    try:
        qty_val = float(qty)
    except (TypeError, ValueError):
        return {"error": f"Invalid qty: {qty!r}"}
    if qty_val <= 0:
        return {"error": "qty must be greater than 0"}

    cleaned_images = [
        str(u).strip() for u in (images or []) if u and str(u).strip()
    ]
    if not cleaned_images:
        return {
            "error": "photo_required",
            "ok": False,
            "message": (
                "A photo is required before posting. Ask the donor to upload "
                "an image in chat, then retry post_food_listing with images[]. "
                "Do not offer to post without a photo."
            ),
        }

    return await _post_food_listing_via_supabase(
        user_id=user_id,
        title=title,
        category=category,
        qty=qty,
        description=description,
        unit=unit,
        address=address,
        expiration_date=expiration_date,
        allergens=allergens,
        dietary_tags=dietary_tags,
        images=images,
        community_name=community_name,
        community_id=community_id,
        community_confirmed=community_confirmed,
    )


async def _post_food_listing_legacy_sqlalchemy(
    user_id: str,
    title: str,
    category: Optional[str] = None,
    qty: float = 1,
    description: Optional[str] = None,
    unit: Optional[str] = None,
    perishability: str = "medium",
    address: Optional[str] = None,
    pickup_window_start: Optional[str] = None,
    pickup_window_end: Optional[str] = None,
    expiration_date: Optional[str] = None,
    allergens: Optional[list] = None,
    dietary_tags: Optional[list] = None,
    images: Optional[list] = None,
) -> dict:
    from backend.app import SessionLocal
    from backend.models import User, UserRole, FoodResource, FoodCategory, PerishabilityLevel

    uid = _to_int(user_id)
    if uid is None:
        return {"error": "Invalid user_id"}

    if not (title or "").strip():
        return {"error": "title is required"}

    # Listings are stored in English so search/filters work for all
    # recipients regardless of donor language. Translate any Spanish
    # the AI may have left in title/description/unit/allergens/tags.
    title = _translate_listing_text(title) or title
    if description:
        description = _translate_listing_text(description)
    if unit:
        unit = _translate_listing_text(unit)
    if isinstance(allergens, list):
        allergens = [_translate_listing_text(a) or a for a in allergens]
    if isinstance(dietary_tags, list):
        dietary_tags = [_translate_listing_text(t) or t for t in dietary_tags]

    # Smart category default: guess from title keywords so the AI doesn't
    # have to interrogate the donor about it. The donor can still override.
    if not category:
        category = _guess_category_from_title(title)

    try:
        cat_enum = FoodCategory(str(category).lower())
    except ValueError:
        return {"error": f"Unknown category '{category}'. Allowed: produce, prepared, packaged, bakery, water, fruit, leftovers"}

    try:
        peri_enum = PerishabilityLevel(str(perishability).lower())
    except ValueError:
        return {"error": f"Invalid perishability '{perishability}'. Allowed: low, medium, high"}

    try:
        from backend.ai.conversation_flow import normalize_expiration_date_for_post
        expiration_date = (
            normalize_expiration_date_for_post(expiration_date) or expiration_date
        )
    except Exception:
        pass

    try:
        exp_dt = _parse_iso(expiration_date)
        win_start = _parse_iso(pickup_window_start)
        win_end = _parse_iso(pickup_window_end)
    except _ParseError as exc:
        return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Sanity-check timestamps. The model frequently picks dates that are
    # already in the past (its training data lags real time), which makes
    # the listing show up as "expired" in the UI and hides it on the map.
    # We:
    #   1) reject any pickup window or expiration that is already past
    #   2) supply sensible defaults when the model omits them
    # ------------------------------------------------------------------
    now = _utcnow()
    if win_end is None and win_start is None:
        # Default pickup window: now -> +48h (good for most donations).
        win_start = now
        win_end = now + timedelta(hours=48)
    elif win_end is None and win_start is not None:
        win_end = win_start + timedelta(hours=24)
    elif win_end is not None and win_start is None:
        win_start = min(now, win_end - timedelta(hours=1))

    if win_end <= now:
        return {
            "error": (
                "pickup_window_end is in the past — the listing would be "
                f"expired on creation. Today is {now.strftime('%Y-%m-%d %H:%M UTC')}; "
                "please pick a future pickup window (e.g. the next 24-48 hours)."
            )
        }
    if win_start and win_start > win_end:
        return {"error": "pickup_window_start must be before pickup_window_end"}

    if exp_dt is None:
        # Default expiration: 7 days for non-perishable, 3 days for high
        # perishability, otherwise 5 days. Always strictly after the pickup
        # window so the UI never marks the new listing 'expired'.
        peri_days = {"low": 7, "medium": 5, "high": 3}.get(
            str(perishability).lower(), 5
        )
        exp_dt = max(win_end, now + timedelta(days=peri_days))
    elif exp_dt <= now:
        # Date-only expiries are midnight — allow the calendar day of "today".
        exp_day = exp_dt.date() if hasattr(exp_dt, "date") else None
        today = now.date()
        if exp_day is None or exp_day < today:
            return {
                "error": (
                    "expiration_date is in the past — listing would be expired. "
                    f"Today is {now.strftime('%Y-%m-%d %H:%M UTC')}. "
                    "Use a good-until date of today or later "
                    "(any future date wording is fine)."
                )
            }

    try:
        qty_val = float(qty)
    except (TypeError, ValueError):
        return {"error": f"Invalid qty: {qty!r}"}
    if qty_val <= 0:
        return {"error": "qty must be greater than 0"}

    def _sync() -> dict:
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == uid).first()
            if not user:
                return {"error": "User not found"}

            # Role gate: only DONOR / VOLUNTEER / ADMIN accounts may post
            # food listings via the AI. Recipients are explicitly blocked
            # so the AI tells them to sign in as a donor (mirror of the
            # donor-cannot-claim guard). Drivers and dispatchers are also
            # excluded to avoid role-blurring on the dispatch dashboard.
            #
            # IMPORTANT: this gate runs BEFORE the dedup short-circuit
            # below — otherwise a banned role could probe for an
            # existing duplicate and get a "success" reply for a
            # listing they're not allowed to post against.
            if user.role == UserRole.RECIPIENT:
                return {
                    "error": (
                        "This account is a recipient account and cannot "
                        "donate or post food listings. Please sign in as "
                        "a donor to share food."
                    ),
                    "reason": "wrong_role",
                    "current_role": "recipient",
                    "required_role": "donor",
                }
            blocked_roles = {UserRole.DRIVER, UserRole.DISPATCHER}
            if user.role in blocked_roles:
                return {"error": "Drivers and dispatchers can't post donor listings from chat."}

            # ----------------------------------------------------------
            # Idempotency / duplicate-post guard.
            # The most common cause of duplicate listings is the model
            # re-issuing the same tool call after a transient network
            # blip — or a recipient hitting "share again" on a voice
            # turn that timed out. If a listing with the same donor +
            # title + address was created in the last 10 seconds, treat
            # this call as a retry and return the EXISTING listing_id
            # instead of creating a second row. We also surface
            # `duplicate_of_recent: true` so the AI can phrase its reply
            # honestly ("That listing is already up — id #N") rather
            # than claiming a fresh post.
            # ----------------------------------------------------------
            try:
                normalized_title = (title or "").strip()[:255].lower()
                normalized_addr = ((address or user.address or "").strip() or None)
                if normalized_title:
                    from sqlalchemy import func as _sa_func
                    recent_cutoff = _utcnow() - timedelta(seconds=10)
                    dup_q = (
                        db.query(FoodResource)
                        .filter(FoodResource.donor_id == uid)
                        .filter(FoodResource.created_at >= recent_cutoff)
                        .filter(_sa_func.lower(FoodResource.title) == normalized_title)
                    )
                    if normalized_addr:
                        dup_q = dup_q.filter(FoodResource.address == normalized_addr)
                    dup = dup_q.order_by(FoodResource.id.desc()).first()
                    if dup is not None:
                        logger.info(
                            "post_food_listing: dedup hit for donor=%s title=%r addr=%r -> existing id=%s",
                            uid, normalized_title, normalized_addr, dup.id,
                        )
                        return {
                            "success": True,
                            "listing_id": dup.id,
                            "address": dup.address,
                            "coords_lat": dup.coords_lat,
                            "coords_lng": dup.coords_lng,
                            "duplicate_of_recent": True,
                            "verified": True,
                            "verify_issues": [],
                            "summary": (
                                f"That listing is already up — id #{dup.id}, '{dup.title}'. "
                                "Skipping the duplicate so you don't end up with two pins for the same food."
                            ),
                        }
            except Exception:
                # Dedup is best-effort; never block the post on a
                # query-shape problem.
                logger.exception("post_food_listing: dedup check failed (continuing)")

            # A listing must be findable. If neither the call nor the user
            # profile has an address AND the user has no coords, the listing
            # would never appear on the map. Ask the AI to collect this.
            resolved_address = (address or user.address or "").strip() or None
            if not resolved_address and (user.coords_lat is None or user.coords_lng is None):
                return {
                    "error": (
                        "Cannot post listing: no pickup address. Ask the user "
                        "for the pickup address (street + city) and call again."
                    )
                }

            # Geocode the resolved address so the listing shows up on the
            # map. Strategy:
            #   1. Try to geocode the freshly-supplied address.
            #   2. If that fails AND the user has good profile coords,
            #      use those rather than rejecting the post outright.
            #   3. Only reject when we have NEITHER a geocode hit NOR
            #      profile coords — in that case the listing genuinely
            #      can't appear on the map.
            geocoded = _geocode_address(resolved_address) if resolved_address else None
            if geocoded is not None:
                lat, lng = geocoded
            elif user.coords_lat is not None and user.coords_lng is not None:
                lat, lng = user.coords_lat, user.coords_lng
                logger.info(
                    "post_food_listing: geocode miss for %r, using profile coords",
                    resolved_address,
                )
            else:
                return {
                    "error": (
                        "Cannot post listing: address could not be located on the map. "
                        "Please provide a more specific street + city + state "
                        "(e.g. '123 Main St, Alameda, CA')."
                    )
                }

            item = FoodResource(
                donor_id=uid,
                title=title.strip()[:255],
                description=(description or None),
                category=cat_enum,
                qty=qty_val,
                unit=(unit or "units"),
                perishability=peri_enum,
                expiration_date=exp_dt,
                pickup_window_start=win_start,
                pickup_window_end=win_end,
                address=resolved_address,
                coords_lat=lat,
                coords_lng=lng,
                status="available",
                allergens=json.dumps(list(allergens)) if allergens else None,
                dietary_tags=json.dumps(list(dietary_tags)) if dietary_tags else None,
                images=json.dumps([str(u) for u in images if u]) if images else None,
            )
            db.add(item)
            db.commit()
            db.refresh(item)

            # ----------------------------------------------------------
            # Verification pass: re-query the listing as a fresh row and
            # confirm it would actually show up on the map. We check the
            # same conditions the frontend uses to decide whether to
            # render a marker:
            #   - row exists with the new id
            #   - status == 'available'
            #   - coords_lat / coords_lng are non-null
            #   - pickup_window_end is in the future (not auto-expired)
            # If any of those fail, we still return success (the row is
            # in the DB) but flag verified=false with a reason so the
            # AI can tell the donor 'posted but won't be visible because
            # X' instead of pretending everything is fine.
            # ----------------------------------------------------------
            db.expire_all()
            check = (
                db.query(FoodResource)
                .filter(FoodResource.id == item.id)
                .first()
            )
            verified = False
            verify_issues: list[str] = []
            visible_count = None
            if check is None:
                verify_issues.append("listing row not found on re-query")
            else:
                status_val = (
                    check.status.value
                    if hasattr(check.status, "value")
                    else str(check.status or "")
                )
                if status_val != "available":
                    verify_issues.append(f"status={status_val!r} (expected 'available')")
                if check.coords_lat is None or check.coords_lng is None:
                    verify_issues.append("missing map coordinates")
                if check.pickup_window_end and check.pickup_window_end <= _utcnow():
                    verify_issues.append("pickup window already ended")
                # Also confirm it would be returned by the public listings
                # query the map uses. We replicate the simplest version of
                # that filter (status=available, coords present) and count
                # the donor's currently-visible listings so the AI can
                # report 'now N of your listings are live' if helpful.
                from sqlalchemy import and_
                visible_count = (
                    db.query(FoodResource)
                    .filter(
                        and_(
                            FoodResource.donor_id == uid,
                            FoodResource.status == "available",
                            FoodResource.coords_lat.isnot(None),
                            FoodResource.coords_lng.isnot(None),
                        )
                    )
                    .count()
                )
                verified = not verify_issues

            # Include the resolved address + coords in the summary so the
            # user (and the chip in the chat) gets visible confirmation
            # of WHERE the pin was dropped on the map. Donors frequently
            # complained that the address step felt skipped because the
            # tool used profile coords silently — this surfaces it.
            addr_part = f" at {resolved_address}" if resolved_address else ""
            coord_part = f" (pin {lat:.4f}, {lng:.4f})"
            if verified:
                summary = (
                    f"Posted listing #{item.id} — '{item.title}' "
                    f"({cat_enum.value}){addr_part}{coord_part}. "
                    f"Verified live on the map"
                    + (f" ({visible_count} of your listings now visible)." if visible_count else ".")
                )
            else:
                summary = (
                    f"Posted listing #{item.id} — '{item.title}' "
                    f"({cat_enum.value}){addr_part}{coord_part}. "
                    f"WARNING: post-check found issues — "
                    + "; ".join(verify_issues)
                    + ". The row is in the database but may NOT show on the map."
                )
            return {
                "success": True,
                "listing_id": item.id,
                "address": resolved_address,
                "coords_lat": lat,
                "coords_lng": lng,
                "verified": verified,
                "verify_issues": verify_issues,
                "visible_listings_for_donor": visible_count,
                "summary": summary,
            }
        except Exception as exc:
            logger.exception("post_food_listing failed")
            db.rollback()
            return {"error": "Could not post the listing. Please try again."}
        finally:
            db.close()

    return await _run(_sync)


async def _attach_photos_to_listing(
    user_id: str,
    listing_id,
    images: list,
) -> dict:
    """Append one or more image URLs to an existing listing's photo gallery."""
    if _is_supabase_user_id(user_id):
        from backend.tools import _attach_photos_to_listing as _impl
        uid = str(user_id).strip()
        resolved_lid = _resolve_supabase_listing_id(listing_id, uid)
        if not resolved_lid:
            return {"error": "Invalid listing_id"}
        cleaned = [str(u).strip() for u in (images or []) if u and str(u).strip()]
        if not cleaned:
            return {"error": "No image URLs provided."}
        last_result = None
        for url in cleaned:
            last_result = await _impl(
                user_id=uid,
                listing_id=resolved_lid,
                image_url=url,
            )
            if not last_result.get("success"):
                return {"error": last_result.get("error", "Could not attach photos.")}
        if last_result and last_result.get("success"):
            return {
                "success": True,
                "listing_id": resolved_lid,
                "summary": last_result.get("summary"),
            }
        return {"error": "No valid image URLs (must start with http:// or https://)."}

    from backend.app import SessionLocal
    from backend.models import User, UserRole, FoodResource

    uid = _to_int(user_id)
    if uid is None:
        return {"error": "Invalid user_id"}
    lid = _to_int(listing_id)
    if lid is None:
        return {"error": "Invalid listing_id"}
    cleaned = [str(u).strip() for u in (images or []) if u and str(u).strip()]
    if not cleaned:
        return {"error": "No image URLs provided."}

    def _sync() -> dict:
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == uid).first()
            if not user:
                return {"error": "User not found"}
            listing = db.query(FoodResource).filter(FoodResource.id == lid).first()
            if not listing:
                return {"error": f"Listing #{lid} not found."}
            if listing.donor_id != uid and user.role != UserRole.ADMIN:
                return {"error": "You can only add photos to your own listings."}

            existing: list = []
            if listing.images:
                try:
                    parsed = json.loads(listing.images)
                    if isinstance(parsed, list):
                        existing = [str(u) for u in parsed if u]
                except (ValueError, TypeError):
                    existing = []

            seen = set(existing)
            for url in cleaned:
                if url not in seen:
                    existing.append(url)
                    seen.add(url)

            listing.images = json.dumps(existing)
            db.commit()
            return {
                "success": True,
                "listing_id": lid,
                "image_count": len(existing),
                "summary": f"Done — added {len(cleaned)} photo(s) to listing #{lid} (now {len(existing)} total).",
            }
        except Exception:
            logger.exception("attach_photos_to_listing failed")
            db.rollback()
            return {"error": "Could not attach photos. Please try again."}
        finally:
            db.close()

    return await _run(_sync)


# Listing management — delegate to backend.tools (Supabase-backed).
async def _get_user_listings(**kwargs) -> dict:
    from backend.tools import _get_user_listings as _impl
    return await _impl(**kwargs)


async def _update_food_listing(**kwargs) -> dict:
    from backend.tools import _update_food_listing as _impl
    return await _impl(**kwargs)


async def _deactivate_listing(**kwargs) -> dict:
    from backend.tools import _deactivate_listing as _impl
    return await _impl(**kwargs)


async def _delete_listing(**kwargs) -> dict:
    from backend.tools import _delete_listing as _impl
    return await _impl(**kwargs)


async def _bulk_import_listings(
    user_id: str,
    csv_text: Optional[str] = None,
    listings: Optional[list] = None,
    default_address: Optional[str] = None,
    default_expiry_date: Optional[str] = None,
    community_name: Optional[str] = None,
    community_id: Optional[str] = None,
    community_confirmed: bool = False,
    **kwargs,
) -> dict:
    """Supabase bulk import - honors per-row community/school CSV columns."""
    from backend.tools import _bulk_import_listings as _impl
    return await _impl(
        user_id=user_id,
        csv_text=csv_text,
        listings=listings,
        default_address=default_address,
        default_expiry_date=default_expiry_date,
        community_name=community_name,
        community_id=community_id,
        community_confirmed=community_confirmed,
        **kwargs,
    )


async def _send_user_message(
    user_id: str,
    content: str,
    conversation_id: Optional[str] = None,
    recipient_id: Optional[int] = None,
) -> dict:
    """Send an in-app message.

    Routing precedence:
    1. If conversation_id is provided, use it verbatim.
    2. Else if recipient_id is provided, use the canonical pair thread
       ``pair_<lo>_<hi>`` so both participants land in the same conversation.
    3. Else fall back to the user's own thread ``user_<uid>``.
    """
    from backend.app import SessionLocal
    from backend.models import Message, User, UserRole

    uid = _to_int(user_id)
    if uid is None:
        return {"error": "Invalid user_id"}
    text = (content or "").strip()
    if not text:
        return {"error": "content required"}

    rid = _to_int(recipient_id) if recipient_id is not None else None

    def _sync() -> dict:
        db = SessionLocal()
        try:
            u = db.query(User).filter(User.id == uid).first()
            if not u:
                return {"error": "User not found"}
            if conversation_id:
                conv = conversation_id
            elif rid is not None:
                if rid == uid:
                    return {"error": "recipient_id cannot be the current user"}
                other = db.query(User).filter(User.id == rid).first()
                if not other:
                    return {"error": "recipient not found"}
                lo, hi = sorted((uid, rid))
                conv = f"pair_{lo}_{hi}"
            else:
                conv = f"user_{uid}"
            msg = Message(
                sender_id=uid,
                conversation_id=conv,
                content=text[:2000],
                is_from_admin=(u.role == UserRole.ADMIN),
                is_read=False,
            )
            db.add(msg)
            db.commit()
            db.refresh(msg)
            return {
                "success": True,
                "message_id": msg.id,
                "conversation_id": conv,
                "summary": "Sent! Your message is delivered — they'll see it in their inbox.",
            }
        except Exception as exc:
            db.rollback()
            return {"error": f"send failed: {exc}"}
        finally:
            db.close()

    return await _run(_sync)


async def _show_map(user_id: str, focus: Optional[str] = None) -> dict:
    """UI-control tool: tells the frontend to switch to the map view.

    Server-side this is a no-op — it just returns a success payload that
    the chat UI broadcasts as a `dogoods:show_map` event so app.js can
    flip the active view to the map. We never fail this call.
    """
    focus_norm = (focus or "").strip().lower() or None
    if focus_norm == "me":
        summary = "Showing the map centered on you."
    elif focus_norm == "all":
        summary = "Showing the map with all available listings."
    elif focus_norm:
        summary = f"Showing the map focused on {focus}."
    else:
        summary = "Showing the map."
    return {
        "success": True,
        "summary": summary,
        "view": "map",
        "focus": focus_norm,
    }


def _coords_from_row(row: Optional[dict], *, address_keys: tuple = ()) -> tuple:
    """Return (lat, lng, address) from a Supabase users/food_listings row."""
    if not isinstance(row, dict):
        return (None, None, None)
    lat = lng = None
    for lat_key, lng_key in (("latitude", "longitude"), ("lat", "lng"), ("coords_lat", "coords_lng")):
        try:
            if row.get(lat_key) is not None and row.get(lng_key) is not None:
                lat = float(row[lat_key])
                lng = float(row[lng_key])
                break
        except (TypeError, ValueError):
            lat = lng = None
    loc = row.get("location")
    if isinstance(loc, str):
        try:
            import json as _json
            loc = _json.loads(loc)
        except Exception:
            loc = None
    if (lat is None or lng is None) and isinstance(loc, dict):
        try:
            if loc.get("latitude") is not None and loc.get("longitude") is not None:
                lat = float(loc["latitude"])
                lng = float(loc["longitude"])
            elif loc.get("lat") is not None and loc.get("lng") is not None:
                lat = float(loc["lat"])
                lng = float(loc["lng"])
        except (TypeError, ValueError):
            pass
    addr = None
    for key in address_keys or ("full_address", "address"):
        val = row.get(key)
        if isinstance(val, str) and val.strip():
            addr = val.strip()
            break
    if not addr and isinstance(loc, dict):
        addr = str(loc.get("address") or loc.get("full_address") or "").strip() or None
    return (lat, lng, addr)


async def _resolve_supabase_route_endpoints(
    user_id: str,
    listing_id,
) -> dict:
    """Resolve origin/destination for a Supabase UUID auth user."""
    from backend.ai_engine import supabase_get

    lid = _resolve_supabase_listing_id(listing_id, user_id) if listing_id is not None else None
    if not lid and listing_id is not None:
        raw = str(listing_id).strip().lstrip("#")
        if _UUID_RE.match(raw):
            lid = raw

    # No listing id → use most recent claim's food listing.
    if not lid:
        try:
            claims = await supabase_get("food_claims", {
                "claimer_id": f"eq.{user_id}",
                "status": "in.(pending,approved)",
                "select": "food_id,created_at",
                "order": "created_at.desc",
                "limit": "1",
            })
            if claims:
                lid = str(claims[0].get("food_id") or "").strip() or None
        except Exception as exc:
            logger.warning("show_route: claim lookup failed: %s", exc)

    if not lid:
        return {
            "error": (
                "I need a listing to route to. Search for food, pick a number "
                "(or claim one), then ask for directions — e.g. 'directions to #1'."
            ),
            "reason": "listing_not_resolved",
        }

    try:
        users = await supabase_get("users", {
            "id": f"eq.{user_id}",
            "select": "id,address,latitude,longitude,location",
            "limit": "1",
        })
    except Exception as exc:
        return {"error": f"Could not load your profile: {exc}", "reason": "profile_lookup"}
    if not users:
        return {"error": "User not found", "reason": "missing_user"}
    user_row = users[0]

    try:
        listings = await supabase_get("food_listings", {
            "id": f"eq.{lid}",
            "select": "id,title,full_address,location,latitude,longitude",
            "limit": "1",
        })
    except Exception as exc:
        return {"error": f"Could not load listing: {exc}", "reason": "listing_lookup"}
    if not listings:
        return {
            "error": (
                f"Listing not found. Search again and ask for directions to a "
                f"numbered option (e.g. 'show me directions to #1')."
            ),
            "reason": "listing_not_found",
        }
    listing = listings[0]

    o_lat, o_lng, o_addr = _coords_from_row(
        user_row, address_keys=("address", "full_address"),
    )
    if (o_lat is None or o_lng is None) and o_addr:
        geo = _geocode_address(o_addr)
        if geo is not None:
            o_lat, o_lng = geo
    if o_lat is None or o_lng is None:
        return {
            "error": (
                "I can't draw a route without your address. Please add a "
                "home address in Profile, then ask again."
            ),
            "reason": "missing_origin",
        }

    d_lat, d_lng, d_addr = _coords_from_row(
        listing, address_keys=("full_address", "address"),
    )
    if (d_lat is None or d_lng is None) and d_addr:
        geo = _geocode_address(d_addr)
        if geo is not None:
            d_lat, d_lng = geo
    if d_lat is None or d_lng is None:
        return {
            "error": (
                f"'{listing.get('title') or 'That listing'}' doesn't have a map "
                "location, so I can't draw directions to it."
            ),
            "reason": "missing_destination",
        }

    return {
        "_origin": (float(o_lat), float(o_lng), o_addr),
        "_destination": (
            float(d_lat),
            float(d_lng),
            d_addr,
            str(listing.get("id") or lid),
            listing.get("title"),
        ),
    }


async def _show_route_to_listing(
    user_id: str,
    listing_id=None,
    mode: Optional[str] = None,
    **_ignored,
) -> dict:
    """Build a driving route from the user's saved address to a listing.

    Returns an envelope the frontend turns into a blue line on the map.
    Supabase UUID users use food_listings; legacy int users use FoodResource.
    """
    profile = (mode or "driving").strip().lower()
    if profile not in {"driving", "walking", "cycling"}:
        profile = "driving"

    if _is_supabase_user_id(user_id):
        pre = await _resolve_supabase_route_endpoints(str(user_id).strip(), listing_id)
    else:
        from backend.app import SessionLocal
        from backend.models import User, FoodResource

        uid = _to_int(user_id)
        if uid is None:
            return {"error": "Invalid user_id"}
        try:
            lid = int(str(listing_id).strip().lstrip("#"))
        except (TypeError, ValueError):
            return {"error": "Invalid listing_id"}

        def _sync() -> dict:
            db = SessionLocal()
            try:
                user = db.query(User).filter(User.id == uid).first()
                if not user:
                    return {"error": "User not found"}
                listing = db.query(FoodResource).filter(FoodResource.id == lid).first()
                if not listing:
                    return {"error": f"Listing #{lid} not found"}

                o_lat = user.coords_lat
                o_lng = user.coords_lng
                o_addr = (user.address or "").strip() or None
                if (o_lat is None or o_lng is None) and o_addr:
                    geo = _geocode_address(o_addr)
                    if geo is not None:
                        o_lat, o_lng = geo
                if o_lat is None or o_lng is None:
                    return {
                        "error": (
                            "I can't draw a route without your address. Please "
                            "add a pickup/home address to your profile first."
                        ),
                        "reason": "missing_origin",
                    }

                d_lat = listing.coords_lat
                d_lng = listing.coords_lng
                d_addr = (listing.address or "").strip() or None
                if (d_lat is None or d_lng is None) and d_addr:
                    geo = _geocode_address(d_addr)
                    if geo is not None:
                        d_lat, d_lng = geo
                if d_lat is None or d_lng is None:
                    return {
                        "error": (
                            f"Listing #{lid} doesn't have a map location, so I "
                            "can't draw directions to it."
                        ),
                        "reason": "missing_destination",
                    }

                return {
                    "_origin": (float(o_lat), float(o_lng), o_addr),
                    "_destination": (
                        float(d_lat), float(d_lng), d_addr,
                        listing.id, getattr(listing, "title", None),
                    ),
                }
            finally:
                db.close()

        pre = await asyncio.to_thread(_sync)

    if "error" in pre:
        return pre

    o_lat, o_lng, o_addr = pre["_origin"]
    d_lat, d_lng, d_addr, l_id, l_title = pre["_destination"]

    # Call Mapbox Directions. Best-effort: if anything goes wrong we fall
    # back to a straight-line geometry so the UI can still show the path.
    geometry: dict = {
        "type": "LineString",
        "coordinates": [[o_lng, o_lat], [d_lng, d_lat]],
    }
    distance_m: Optional[float] = None
    duration_s: Optional[float] = None
    steps: list = []
    fallback = True

    if MAPBOX_TOKEN:
        url = (
            f"{MAPBOX_DIRECTIONS_URL}/{profile}/"
            f"{o_lng},{o_lat};{d_lng},{d_lat}"
        )
        params = {
            "access_token": MAPBOX_TOKEN,
            "geometries": "geojson",
            "overview": "full",
            # Request per-maneuver instructions so we can surface a
            # short turn-by-turn list ("Head north on Main St for
            # 0.4 mi, then turn right onto Elm Ave"). Without
            # steps=true the route only includes total distance/time.
            "steps": "true",
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json() or {}
                routes = data.get("routes") or []
                if routes:
                    r0 = routes[0]
                    geom = r0.get("geometry")
                    if isinstance(geom, dict) and isinstance(geom.get("coordinates"), list):
                        geometry = geom
                        fallback = False
                        # Only trust Mapbox's distance/duration when we
                        # actually accepted its geometry. Otherwise we'd
                        # report road-network mileage while drawing a
                        # straight line, which confuses the user.
                        distance_m = (
                            float(r0.get("distance")) if r0.get("distance") is not None else None
                        )
                        duration_s = (
                            float(r0.get("duration")) if r0.get("duration") is not None else None
                        )
                        # Flatten step instructions out of legs[*].steps.
                        # We keep distance per step so the frontend (and
                        # the assistant's text reply) can say "Head
                        # north on Main St for 0.4 mi".
                        for leg in (r0.get("legs") or []):
                            for step in (leg.get("steps") or []):
                                man = step.get("maneuver") or {}
                                instr = (man.get("instruction") or "").strip()
                                if not instr:
                                    continue
                                step_dist = step.get("distance")
                                steps.append({
                                    "instruction": instr,
                                    "distance_m": (
                                        float(step_dist) if step_dist is not None else None
                                    ),
                                })
            else:
                logger.warning(
                    "Mapbox Directions returned %s for listing %s",
                    resp.status_code, l_id,
                )
        except Exception as exc:
            logger.warning("Mapbox Directions failed for listing %s: %s", l_id, exc)

    def _fmt_step(step: dict) -> str:
        """One human line, e.g. 'Turn right onto Elm Ave (0.4 mi)'."""
        instr = step.get("instruction") or ""
        dm = step.get("distance_m")
        if dm is None or dm <= 0:
            return instr
        miles = dm / 1609.344
        # Sub-tenth-mile turns read better in feet.
        if miles < 0.1:
            feet = int(round(dm * 3.28084 / 10.0)) * 10
            return f"{instr} ({feet} ft)"
        return f"{instr} ({miles:.1f} mi)"

    # Build a human summary in the same language the AI will reply in.
    def _fmt_summary() -> str:
        head = f"Route to '{l_title or f'listing #{l_id}'}'"
        metrics: list = []
        if distance_m is not None:
            miles = distance_m / 1609.344
            metrics.append(f"{miles:.1f} mi")
        if duration_s is not None:
            mins = int(round(duration_s / 60.0))
            metrics.append(f"~{mins} min")
        parts = [head]
        if metrics:
            parts.append(", ".join(metrics))
        if fallback:
            parts.append("(approximate)")
        first_line = " — ".join(parts)
        # Append the first few turn instructions so the assistant has
        # actual directions to read back, not just total mileage. Cap
        # at 6 turns to keep the chat reply readable; the frontend can
        # render the full list from route.steps if it wants.
        if steps:
            shown = [_fmt_step(s) for s in steps[:6] if s.get("instruction")]
            shown = [s for s in shown if s]
            if shown:
                turn_block = "\n".join(f"{i + 1}. {line}" for i, line in enumerate(shown))
                more = f"\n…and {len(steps) - len(shown)} more turn(s)" if len(steps) > len(shown) else ""
                return f"{first_line}\n\n{turn_block}{more}"
        return first_line

    return {
        "success": True,
        "ok": True,
        "view": "map",
        # Frontend UIControlContext understands open_map → navigates to /find.
        "action": "open_map",
        "summary": _fmt_summary(),
        "route": {
            "origin": {"lat": o_lat, "lng": o_lng, "address": o_addr},
            "destination": {
                "lat": d_lat,
                "lng": d_lng,
                "address": d_addr,
                "listing_id": l_id,
                "title": l_title,
            },
            "mode": profile,
            "distance_m": distance_m,
            "duration_s": duration_s,
            "distance_km": (round(distance_m / 1000.0, 2) if distance_m is not None else None),
            "duration_text": (
                f"{int(round(duration_s / 60.0))} min" if duration_s is not None else None
            ),
            "geometry": geometry,
            "steps": steps,
            "fallback": fallback,
        },
    }


# Display labels for navigate_ui targets, used to build a friendly summary.
_NAV_TARGET_LABELS = {
    "map": "the map",
    "list": "Find Food",
    "create": "Share Food",
    "bulk-create": "Share Food (bulk)",
    "request": "Request Food",
    "request-food": "Request Food",
    "community-requests": "Community Requests",
    "claim": "Claim Food",
    "profile": "your profile",
    "settings": "Settings",
    "receipts": "Receipts / pickups",
    "listings": "My Listings",
    "near-me": "Near Me",
    "notifications": "Notifications",
    "login": "Login",
    "signup": "Sign up",
    "home": "Home",
    "dashboard": "your dashboard",
    "dispatch": "the dispatch console",
    "admin": "the admin panel",
    "driver": "the driver interface",
    "schedule": "donation schedules",
    "partners": "Sponsors",
    "food-rescue": "the food-rescue network",
    "meal-planning": "Recipes",
    "ai-matching": "AI matching",
    "routes": "volunteer routes",
    "emergency": "Contact",
    "nutrition": "nutrition tracker",
    "consumption": "the consumption tracker",
    "filters": "the filters panel",
    "favorites": "your favorites",
    "chat": "the chat assistant",
    "voice": "the voice assistant",
    "meal-suggestions": "AI meal suggestions",
    "spoilage-alerts": "spoilage risk alerts",
    "storage-coach": "the AI storage coach",
    "smart-notifications": "smart notifications",
    "pickup-reminders": "pickup reminders",
    "sms-consent": "SMS text notifications",
}

_NAV_VALID_ACTIONS = {"open", "close", "toggle"}

# Mirrors NAV_TARGET_ROUTES / MODAL_TARGET_ROUTES in UIControlContext.jsx
_NAV_TARGET_PATHS = {
    "list": "/find",
    "create": "/share",
    "bulk-create": "/share",
    "request": "/request",
    "request-food": "/request",
    "community-requests": "/community-requests",
    "claim": "/claim",
    "profile": "/profile",
    "settings": "/settings",
    "receipts": "/receipts",
    "listings": "/listings",
    "near-me": "/near-me",
    "notifications": "/notifications",
    "login": "/login",
    "signup": "/signup",
    "home": "/",
    "dashboard": "/dashboard",
    "dispatch": "/admin/distribution",
    "admin": "/admin",
    "driver": "/admin",
    "schedule": "/donations",
    "partners": "/sponsors",
    "food-rescue": "/find",
    "meal-planning": "/recipes",
    "ai-matching": "/find",
    "routes": "/find",
    "emergency": "/contact",
    "nutrition": "/recipes",
    "consumption": "/dashboard",
    "filters": "/find",
    "favorites": "/find",
}

_NAV_MODAL_TARGETS = {
    "meal-suggestions", "spoilage-alerts", "storage-coach",
    "smart-notifications", "pickup-reminders", "sms-consent",
}


def _build_navigate_ui_payload(
    act: str,
    tgt: Optional[str],
    summary: str,
    query: Optional[str] = None,
) -> dict:
    """Shape a frontend-ready UI directive (ok + navigate/open_map/open_modal)."""
    payload: dict = {
        "ok": True,
        "success": True,
        "summary": summary,
        "target": tgt,
    }

    if act == "close":
        if tgt == "chat":
            payload["action"] = "close_assistant"
        elif tgt in _NAV_MODAL_TARGETS:
            payload["action"] = "close_modal"
        else:
            payload["action"] = "navigate"
            payload["path"] = "/find"
        return payload

    if act == "open" and tgt == "map":
        payload["action"] = "open_map"
        return payload
    if act == "open" and tgt == "chat":
        payload["action"] = "open_assistant"
        return payload
    if act == "open" and tgt == "voice":
        payload["action"] = "expand_assistant"
        return payload

    canon_tgt = (tgt or "").replace("_", "-")
    if act == "open" and tgt in _NAV_MODAL_TARGETS:
        payload["action"] = "open_modal"
        payload["target"] = canon_tgt
        return payload
    if act == "toggle" and tgt in _NAV_MODAL_TARGETS:
        payload["action"] = "toggle_modal"
        payload["target"] = canon_tgt
        return payload

    path = _NAV_TARGET_PATHS.get(tgt or "")
    if path:
        safe_q = _sanitize_navigate_query(query)
        if safe_q:
            path = f"{path}?{safe_q}"
        payload["action"] = "navigate"
        payload["path"] = path
        return payload

    # Fallback — should not happen after validation.
    payload["action"] = act
    return payload


_NAV_QUERY_ALLOWED_KEYS = frozenset({
    "request",
    "community_id",
    "community",
    "category",
    "quantity",
    "unit",
    "description",
    "needed_by",
    "fulfilling_request_id",
})


def _sanitize_navigate_query(query: Optional[str]) -> Optional[str]:
    """Allow only known share/request prefill keys in navigate_ui query strings."""
    if not query or not isinstance(query, str):
        return None
    from urllib.parse import parse_qsl, urlencode

    raw = query.strip().lstrip("?")
    if not raw:
        return None
    pairs = []
    for key, value in parse_qsl(raw, keep_blank_values=False):
        if key not in _NAV_QUERY_ALLOWED_KEYS:
            continue
        val = str(value or "").strip()
        if not val:
            continue
        pairs.append((key, val[:500]))
    if not pairs:
        return None
    return urlencode(pairs)


async def _navigate_ui(
    user_id: str,
    action: str,
    target: Optional[str] = None,
    query: Optional[str] = None,
) -> dict:
    """UI-control tool: instructs the frontend to open/close a UI surface.

    Server-side this is a no-op — the frontend listens for the
    `dogoods:navigate_ui` event broadcast from the chatbot and handles
    the actual navigation. We only validate inputs and shape a friendly
    summary string for the action chip.
    """
    act = (action or "").strip().lower()
    if act not in _NAV_VALID_ACTIONS:
        return {"error": f"Invalid action '{action}'. Use open, close, or toggle."}

    tgt = (target or "").strip().lower() or None
    # 'close' may omit a target — defaults to returning to the map.
    if tgt is not None and tgt not in _NAV_TARGET_LABELS:
        return {"error": f"Unknown target '{target}'."}
    if act in {"open", "toggle"} and tgt is None:
        return {"error": f"target is required for action '{act}'."}

    if act == "close":
        label = _NAV_TARGET_LABELS.get(tgt, "the map") if tgt else "the current view"
        summary = f"Closed {label}."
    elif act == "toggle":
        summary = f"Toggled {_NAV_TARGET_LABELS[tgt]}."
    else:  # open
        summary = f"Opened {_NAV_TARGET_LABELS[tgt]}."

    _nav_result = _build_navigate_ui_payload(act, tgt, summary, query=query)
    return _nav_result


# ---------------------------------------------------------------------------
# Agentic memory tool handlers
# ---------------------------------------------------------------------------

async def _save_user_memory(
    user_id: str,
    key: str,
    value: str,
    confidence: str = "medium",
) -> dict:
    """Upsert a learned preference into ai_user_preferences."""
    uid = str(user_id or "").strip()
    if not uid:
        return {"error": "Invalid user_id"}
    key = (key or "").strip()[:128]
    value = (value or "").strip()
    if not key or not value:
        return {"error": "key and value are required"}
    confidence = confidence if confidence in ("low", "medium", "high") else "medium"

    from backend.app import SessionLocal
    from backend.ai.models import AIUserPreference

    def _sync() -> dict:
        db = SessionLocal()
        try:
            existing = (
                db.query(AIUserPreference)
                .filter(
                    AIUserPreference.user_id == uid,
                    AIUserPreference.key == key,
                )
                .first()
            )
            if existing:
                existing.value = value
                existing.confidence = confidence
                existing.last_seen_at = _utcnow()
            else:
                db.add(AIUserPreference(
                    user_id=str(uid),
                    key=key,
                    value=value,
                    confidence=confidence,
                    last_seen_at=_utcnow(),
                ))
            db.commit()
            return {"saved": True, "key": key, "value": value}
        except Exception as exc:
            db.rollback()
            logger.error("save_user_memory failed: %s", exc)
            return {"error": "Failed to save preference"}
        finally:
            db.close()

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


async def _get_user_memory(user_id: str) -> dict:
    """Return the top-20 learned preferences for this user."""
    uid = str(user_id or "").strip()
    if not uid:
        return {"memories": [], "error": "Invalid user_id"}

    from backend.app import SessionLocal
    from backend.ai.models import AIUserPreference

    def _sync() -> dict:
        db = SessionLocal()
        try:
            prefs = (
                db.query(AIUserPreference)
                .filter(AIUserPreference.user_id == uid)
                .order_by(AIUserPreference.last_seen_at.desc())
                .limit(20)
                .all()
            )
            return {
                "memories": [
                    {"key": p.key, "value": p.value, "confidence": p.confidence}
                    for p in prefs
                ]
            }
        except Exception as exc:
            logger.error("get_user_memory failed: %s", exc)
            return {"memories": [], "error": "Failed to load memories"}
        finally:
            db.close()

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


async def _forget_user_memory(
    user_id: str,
    key: Optional[str] = None,
    query: Optional[str] = None,
) -> dict:
    """Delete a saved preference / standing instruction by key or fuzzy match."""
    uid = str(user_id or "").strip()
    if not uid:
        return {"error": "Invalid user_id"}
    key_s = (key or "").strip()[:128]
    query_s = (query or "").strip().lower()
    if not key_s and not query_s:
        return {"error": "Provide key or query"}

    from backend.app import SessionLocal
    from backend.ai.models import AIUserPreference

    def _sync() -> dict:
        db = SessionLocal()
        try:
            deleted: list[str] = []
            if key_s:
                rows = (
                    db.query(AIUserPreference)
                    .filter(
                        AIUserPreference.user_id == uid,
                        AIUserPreference.key == key_s,
                    )
                    .all()
                )
            else:
                rows = (
                    db.query(AIUserPreference)
                    .filter(AIUserPreference.user_id == uid)
                    .order_by(AIUserPreference.last_seen_at.desc())
                    .limit(50)
                    .all()
                )
                rows = [
                    r for r in rows
                    if query_s in (r.key or "").lower()
                    or query_s in (r.value or "").lower()
                ][:5]
            for row in rows:
                deleted.append(row.key)
                db.delete(row)
            if deleted:
                db.commit()
                return {"forgotten": True, "keys": deleted}
            return {"forgotten": False, "keys": [], "message": "No matching memory found"}
        except Exception as exc:
            db.rollback()
            logger.error("forget_user_memory failed: %s", exc)
            return {"error": "Failed to forget preference"}
        finally:
            db.close()

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


async def _mark_goal_done(user_id: str, description: str) -> dict:
    """Record that a multi-step goal was completed."""
    uid = str(user_id or "").strip()
    if not uid:
        return {"error": "Invalid user_id"}
    description = (description or "").strip()[:500]
    if not description:
        return {"error": "description is required"}

    from backend.app import SessionLocal
    from backend.ai.models import AIGoal

    def _sync() -> dict:
        db = SessionLocal()
        try:
            goal = AIGoal(
                user_id=str(uid),
                description=description,
                status="done",
                completed_at=_utcnow(),
            )
            db.add(goal)
            db.commit()
            db.refresh(goal)
            return {"recorded": True, "goal_id": goal.id, "description": description}
        except Exception as exc:
            db.rollback()
            logger.error("mark_goal_done failed: %s", exc)
            return {"error": "Failed to record goal"}
        finally:
            db.close()

    return await asyncio.get_event_loop().run_in_executor(None, _sync)

