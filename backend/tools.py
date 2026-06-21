"""
DoGoods AI Tool Signatures & Implementations
----------------------------------------------
OpenAI function-calling tool definitions for the DoGoods AI assistant.
Implements: search_food_near_user, get_user_profile, get_pickup_schedule,
            create_reminder, get_mapbox_route, query_distribution_centers,
            get_user_dashboard, check_pickup_schedule.
"""

import json
import logging
import math
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

logger = logging.getLogger("ai_tools")

MAPBOX_TOKEN = os.getenv("MAPBOX_TOKEN") or os.getenv("VITE_MAPBOX_TOKEN", "")
MAPBOX_DIRECTIONS_URL = "https://api.mapbox.com/directions/v5/mapbox"

# Max age (hours) applied ONLY when a listing has no expiry_date and no pickup_by.
# These are intentionally generous — the listing's active/approved status is the
# primary signal of availability. Only cooked/prepared/perishable-meat listings
# get a strict cutoff to avoid surfacing genuinely dangerous old food.
# Everything else uses 30 days (720h) — if it's still active in the DB and the
# donor hasn't removed it, we trust it's still available.
_PERISHABLE_CATEGORY_MAX_AGE_HOURS = {
    "prepared": 48,
    "prepared food": 48,
    "prepared foods": 48,
    "meat": 48,
    "seafood": 48,
    # All other categories: 30-day fallback
    "dairy": 720,
    "bakery": 720,
    "produce": 720,
    "vegetables": 720,
    "fruits": 720,
    "beverages": 720,
    "other": 720,
    "pantry": 720,
    "canned": 720,
    "grains": 720,
}


def _parse_dt(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


def _extract_location_text(location_field) -> str:
    """Safely extract a plain-text address from a food_listings.location value.

    food_listings.location is a JSONB column that can hold either:
      - A plain string: "123 Main St, Oakland, CA"
      - A JSON string: '{"address": "123 Main St", "latitude": 37.8, ...}'
      - A dict (returned by PostgREST for JSONB): {"address": "...", ...}
    Returns a plain text string or "" when nothing useful is found.
    """
    if not location_field:
        return ""
    if isinstance(location_field, dict):
        return str(location_field.get("address") or location_field.get("full_address") or "").strip()
    if isinstance(location_field, str):
        trimmed = location_field.strip()
        if trimmed.startswith("{"):
            try:
                parsed = json.loads(trimmed)
                if isinstance(parsed, dict):
                    return str(parsed.get("address") or parsed.get("full_address") or "").strip()
            except (ValueError, TypeError):
                pass
        return trimmed
    return ""


def _normalize_expiry_date(*candidates: Optional[str]) -> Optional[str]:
    """Return YYYY-MM-DD from the first valid expiry candidate."""
    for raw in candidates:
        if raw is None:
            continue
        s = str(raw).strip()
        if not s:
            continue
        if len(s) >= 10 and s[4:5] == "-" and s[7:8] == "-":
            try:
                return datetime.fromisoformat(s[:10]).date().isoformat()
            except ValueError:
                pass
        dt = _parse_dt(s)
        if dt:
            return dt.date().isoformat()
    return None


# Realistic shelf-life estimates used when SUGGESTING an expiry date on a new
# listing (separate from the search freshness filter above).
_SUGGESTED_EXPIRY_DAYS: dict = {
    "prepared": 2,
    "prepared food": 2,
    "prepared foods": 2,
    "meat": 2,
    "seafood": 2,
    "dairy": 5,
    "bakery": 5,
    "produce": 7,
    "vegetables": 7,
    "fruits": 7,
    "beverages": 14,
    "other": 7,
    "pantry": 30,
    "canned": 30,
    "grains": 30,
}


def _suggested_expiry_for_category(category: str) -> str:
    cat = str(category or "other").strip().lower()
    days = _SUGGESTED_EXPIRY_DAYS.get(cat, 7)
    return (datetime.now(timezone.utc).date() + timedelta(days=days)).isoformat()


def _listing_is_fresh_enough(listing: dict, now: Optional[datetime] = None) -> bool:
    """Return True when a listing is still safe enough for the AI to surface.

    Rules:
    - hide listings whose pickup_by has already passed
    - hide listings whose expiry_date is already in the past
    - if a listing has neither expiry_date nor pickup_by, apply a category-based
      max age so the AI does not point users at old food that may have gone bad
    """
    now = now or datetime.now(timezone.utc)

    pickup_by_dt = _parse_dt(listing.get("pickup_by"))
    if pickup_by_dt and pickup_by_dt < now:
        return False

    expiry_value = listing.get("expiry_date")
    if expiry_value:
        expiry_dt = _parse_dt(expiry_value)
        if expiry_dt:
            if expiry_dt < now:
                return False
        else:
            try:
                expiry_date = datetime.fromisoformat(str(expiry_value)).date()
                if expiry_date < now.date():
                    return False
            except Exception:
                pass

    if expiry_value or pickup_by_dt:
        return True

    created_dt = _parse_dt(listing.get("created_at"))
    if not created_dt:
        # No created_at — if listing is active/approved, trust the status.
        return True

    category = str(listing.get("category") or "other").strip().lower()
    # Default fallback: 30 days (720h) for uncategorised items
    max_age_hours = _PERISHABLE_CATEGORY_MAX_AGE_HOURS.get(category, 720)
    age_hours = (now - created_dt).total_seconds() / 3600
    return age_hours <= max_age_hours

# ---------------------------------------------------------------------------
# OpenAI function-calling tool definitions
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_food_near_user",
            "description": (
                "Search for available food listings near a user's location. "
                "Returns food items that are currently available for pickup "
                "within the specified radius."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "The UUID of the user to search near",
                    },
                    "radius_km": {
                        "type": "number",
                        "description": "Search radius in kilometers (default 10)",
                        "default": 10,
                    },
                    "food_type": {
                        "type": "string",
                        "description": (
                            "Optional food category filter using DB enum values: "
                            "produce (vegetables, fruits, greens, etc.), "
                            "dairy (milk, cheese, eggs, yogurt, butter), "
                            "bakery (bread, pastries, muffins, bagels), "
                            "pantry (canned goods, grains, rice, beans, pasta, dry goods), "
                            "meat (beef, pork, chicken, poultry), "
                            "seafood (fish, shellfish), "
                            "frozen (frozen meals, ice cream), "
                            "snacks (chips, crackers, cookies), "
                            "beverages (juice, soda, water, tea), "
                            "prepared (cooked meals, sandwiches, leftovers). "
                            "Pass the DB enum value exactly. If unsure, omit this "
                            "and use dietary_tags / exclude_allergens instead."
                        ),
                    },
                    "dietary_tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Optional dietary tags the listing must include (ALL required). "
                            "Examples: vegan, vegetarian, gluten-free, halal, kosher, "
                            "dairy-free, nut-free, organic, low-sodium, high-protein. "
                            "Case-insensitive; hyphens optional ('gluten free' == 'gluten-free')."
                        ),
                    },
                    "exclude_allergens": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Optional allergens to exclude. Listings whose `allergens` "
                            "field contains ANY of these are filtered out. "
                            "Examples: nuts, peanuts, tree nuts, dairy, milk, eggs, "
                            "gluten, wheat, soy, shellfish, fish, sesame."
                        ),
                    },
                    "expiry_within_days": {
                        "type": "integer",
                        "description": (
                            "Optional. Only return listings whose expiry_date is within "
                            "this many days from today. Use 0 for 'expiring today', "
                            "1 for 'today or tomorrow', 3 for 'within 3 days', 7 for "
                            "'this week'. Listings without an expiry date are still "
                            "included (they are non-perishable / unlabeled)."
                        ),
                    },
                    "min_quantity": {
                        "type": "number",
                        "description": (
                            "Optional. Only return listings whose quantity is at least "
                            "this number. Useful for 'food for 10 people' style requests "
                            "where you want listings large enough to feed a group."
                        ),
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default 10)",
                        "default": 10,
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
                "Check the newest food listings that were posted recently. "
                "Use this when the user asks what's new, asks to check new listings, "
                "or wants the latest available listings."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "hours": {
                        "type": "integer",
                        "description": "How far back to look for newly posted listings (default 72 hours).",
                        "default": 72,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of new listings to return (default 10).",
                        "default": 10,
                    },
                    "category": {
                        "type": "string",
                        "description": "Optional category filter for new listings.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_profile",
            "description": (
                "Retrieve a user's profile information including name, location, "
                "preferences, dietary restrictions, and activity history summary."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "The UUID of the user",
                    },
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_user_profile",
            "description": (
                "Update fields on the authenticated user's profile. Only pass the "
                "fields the user explicitly asked to change. Use this when the user "
                "says things like 'update my address', 'change my phone', 'set my "
                "dietary restrictions', 'opt me into SMS', etc. The user_id is taken "
                "from the authenticated session — never from the model."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "The UUID of the authenticated user (auto-filled by the server).",
                    },
                    "name": {"type": "string", "description": "Display name."},
                    "address": {
                        "type": "string",
                        "description": "Street address used as the default pickup/recipient address.",
                    },
                    "phone": {
                        "type": "string",
                        "description": "Phone number in E.164 or local format.",
                    },
                    "organization": {"type": "string"},
                    "community_role": {
                        "type": "string",
                        "enum": ["donor", "recipient", "volunteer", "driver", "organizer", "sponsor"],
                        "description": (
                            "How the user participates in the community: "
                            "donor (shares food), recipient (receives food), volunteer (helps organize), "
                            "driver (delivers), organizer (runs distributions), sponsor (supports community)."
                        ),
                    },
                    "dietary_restrictions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "e.g. ['vegetarian','gluten-free']",
                    },
                    "allergies": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "dietary_preferences": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "sms_opt_in": {"type": "boolean"},
                    "sms_notifications_enabled": {"type": "boolean"},
                    "pickup_reminder_enabled": {"type": "boolean"},
                    "default_reminder_hours": {"type": "integer"},
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_pickup_schedule",
            "description": (
                "Get upcoming food pickup or distribution event schedules. "
                "Can filter by user's claimed items or by community events."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "The UUID of the user",
                    },
                    "include_community_events": {
                        "type": "boolean",
                        "description": "Whether to include community distribution events (default true)",
                        "default": True,
                    },
                    "days_ahead": {
                        "type": "integer",
                        "description": "Number of days to look ahead (default 7)",
                        "default": 7,
                    },
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_reminder",
            "description": (
                "Create a reminder for the user. Can be used for pickup reminders, "
                "listing expiry alerts, distribution events, or general reminders."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "The UUID of the user",
                    },
                    "message": {
                        "type": "string",
                        "description": "The reminder message text",
                    },
                    "trigger_time": {
                        "type": "string",
                        "description": "ISO 8601 datetime for when to send the reminder",
                    },
                    "reminder_type": {
                        "type": "string",
                        "enum": ["pickup", "listing_expiry", "distribution_event", "general"],
                        "description": "Type of reminder (default 'general')",
                        "default": "general",
                    },
                    "related_id": {
                        "type": "string",
                        "description": "Optional UUID of related entity (food listing, event, etc.)",
                    },
                },
                "required": ["user_id", "message", "trigger_time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_mapbox_route",
            "description": (
                "Get walking or driving directions between two points. "
                "Returns step-by-step directions, distance, and estimated travel time. "
                "Useful when a user wants to know how to get to a food pickup location."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "origin_lng": {
                        "type": "number",
                        "description": "Origin longitude",
                    },
                    "origin_lat": {
                        "type": "number",
                        "description": "Origin latitude",
                    },
                    "dest_lng": {
                        "type": "number",
                        "description": "Destination longitude",
                    },
                    "dest_lat": {
                        "type": "number",
                        "description": "Destination latitude",
                    },
                    "profile": {
                        "type": "string",
                        "enum": ["driving", "walking", "cycling"],
                        "description": "Travel mode (default 'driving')",
                        "default": "driving",
                    },
                },
                "required": ["origin_lng", "origin_lat", "dest_lng", "dest_lat"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_distribution_centers",
            "description": (
                "Query upcoming community food distribution events and centers. "
                "Returns event details including location, hours, capacity, "
                "and registration status. Can filter by date range and status."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days_ahead": {
                        "type": "integer",
                        "description": "Number of days ahead to search (default 14)",
                        "default": 14,
                    },
                    "status": {
                        "type": "string",
                        "enum": ["scheduled", "in_progress", "completed", "cancelled"],
                        "description": "Filter by event status (default 'scheduled')",
                        "default": "scheduled",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum results to return (default 10)",
                        "default": 10,
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_dashboard",
            "description": (
                "Get a comprehensive user dashboard including profile data, "
                "dietary restrictions, favorite food categories, active listings, "
                "pending claims, upcoming reminders, and impact stats. "
                "Use this to personalize conversations."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "The UUID of the user",
                    },
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_pickup_schedule",
            "description": (
                "Check a user's upcoming reminders and scheduled pickups "
                "from the ai_reminders table. Returns pending reminders "
                "organized by type (pickup, listing_expiry, distribution_event, general)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "The UUID of the user",
                    },
                    "include_sent": {
                        "type": "boolean",
                        "description": "Include already-sent reminders (default false)",
                        "default": False,
                    },
                    "days_ahead": {
                        "type": "integer",
                        "description": "Number of days to look ahead (default 14)",
                        "default": 14,
                    },
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recipes",
            "description": (
                "Get recipe suggestions based on specific ingredients or based on "
                "a user's claimed/available food items from the platform. "
                "When user_id is provided, looks up their active food claims to "
                "suggest recipes they can actually make. Returns 3 creative recipes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ingredients": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of ingredient names to base recipes on",
                    },
                    "user_id": {
                        "type": "string",
                        "description": (
                            "Optional user UUID — if provided, fetches their claimed "
                            "food items and uses those as ingredients"
                        ),
                    },
                    "dietary_preferences": {
                        "type": "string",
                        "description": (
                            "Optional dietary restrictions or preferences "
                            "(e.g. vegetarian, vegan, gluten-free, halal, kosher)"
                        ),
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_storage_tips",
            "description": (
                "Get food storage and preservation tips for specific food items "
                "or for food a user has claimed/listed on the platform. "
                "Returns optimal storage conditions, shelf life, signs of spoilage, "
                "and tips to extend freshness."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "food_items": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of food item names to get storage tips for",
                    },
                    "user_id": {
                        "type": "string",
                        "description": (
                            "Optional user UUID — if provided, fetches their active "
                            "food claims/listings and gives storage tips for those items"
                        ),
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_active_communities",
            "description": (
                "Find active local food sharing communities and groups near a user. "
                "Returns community names, locations, contact info, hours, descriptions, "
                "and impact stats (food given, families helped). Can optionally filter "
                "by proximity to a user's location."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": (
                            "Optional user UUID — if provided, sorts communities "
                            "by distance from the user's location"
                        ),
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of communities to return (default 10)",
                        "default": 10,
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_notifications",
            "description": (
                "Retrieve a user's notifications and alerts. Returns recent "
                "notifications including food claim updates, trade requests, "
                "system alerts, and community announcements. Can filter by "
                "read/unread status and notification type."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "The user's UUID to fetch notifications for",
                    },
                    "unread_only": {
                        "type": "boolean",
                        "description": "If true, return only unread notifications (default false)",
                        "default": False,
                    },
                    "notification_type": {
                        "type": "string",
                        "description": (
                            "Optional filter by type: 'system', 'food_claimed', "
                            "'trade_request', 'claim_approved', 'claim_declined', "
                            "'submission_declined', or 'alert'"
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max notifications to return (default 20)",
                        "default": 20,
                    },
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_notification",
            "description": (
                "Send a notification or alert to a user. Use this to notify users "
                "about important events like expiring food, upcoming distribution "
                "events, claim status changes, community updates, or custom alerts. "
                "The notification appears in the user's notification center."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "The recipient user's UUID",
                    },
                    "title": {
                        "type": "string",
                        "description": "Short notification title (e.g. 'Food Expiring Soon')",
                    },
                    "message": {
                        "type": "string",
                        "description": "The full notification message body",
                    },
                    "notification_type": {
                        "type": "string",
                        "description": (
                            "Notification type: 'system', 'food_claimed', "
                            "'trade_request', 'claim_approved', 'claim_declined', "
                            "'submission_declined', or 'alert'"
                        ),
                        "default": "system",
                    },
                    "data": {
                        "type": "object",
                        "description": (
                            "Optional extra data as JSON (e.g. {\"listing_id\": \"...\", "
                            "\"action_url\": \"/find-food\"})"
                        ),
                    },
                },
                "required": ["user_id", "title", "message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mark_notifications_read",
            "description": (
                "Mark one or all of a user's notifications as read. "
                "Can mark a single notification by ID or all unread "
                "notifications for a user at once."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "The user's UUID",
                    },
                    "notification_id": {
                        "type": "string",
                        "description": (
                            "Optional specific notification UUID to mark as read. "
                            "If omitted, marks ALL unread notifications as read."
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
            "name": "ui_action",
            "description": (
                "Drive the DoGoods web UI on the user's behalf. Use this when "
                "the user asks you to navigate, open something, close something, "
                "or otherwise interact with the app. The frontend will execute "
                "the action when it receives the response. Always confirm in "
                "your reply what you did (e.g. 'I opened the Find Food page')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": (
                            "The UI action to perform. Supported values: "
                            "'navigate' (go to a route), "
                            "'open_assistant' (open the AI chat panel), "
                            "'close_assistant' (close the AI chat panel), "
                            "'expand_assistant' (make the chat panel full-screen), "
                            "'open_listing' (open a food listing's detail/claim view), "
                            "'open_map' (navigate to the Find Food map view), "
                            "'clear_map' (remove AI markers/route from the map), "
                            "'open_modal' / 'close_modal' / 'toggle_modal' "
                            "(open a recipient AI helper surface named by 'target'), "
                            "'scroll_to_top', 'scroll_to_bottom', "
                            "'focus' (focus an input by data-ai-id attribute), "
                            "'set_language' (change UI language)."
                        ),
                        "enum": [
                            "navigate", "open_assistant", "close_assistant",
                            "expand_assistant", "open_listing", "open_map",
                            "clear_map", "open_modal", "close_modal",
                            "toggle_modal", "scroll_to_top", "scroll_to_bottom",
                            "focus", "set_language",
                        ],
                    },
                    "path": {
                        "type": "string",
                        "description": (
                            "For 'navigate': route path. Common routes: "
                            "'/' (home), '/find' (browse food), '/share' (share food), "
                            "'/dashboard', '/profile', '/donate', "
                            "'/notifications', '/recipes', '/donations' (distribution schedules), "
                            "'/near-me', '/how-it-works', '/contact', '/blog', "
                            "'/login', '/signup', '/listings' (my listings), '/settings'."
                        ),
                    },
                    "target": {
                        "type": "string",
                        "description": (
                            "For 'open_modal' / 'toggle_modal' / 'close_modal': the "
                            "recipient AI helper surface to open. One of: "
                            "'meal-suggestions' (recipes from claimed food), "
                            "'spoilage-alerts' (what's about to expire), "
                            "'storage-coach' (how to store a food), "
                            "'smart-notifications' (tune alert preferences), "
                            "'pickup-reminders' (pickup reminder settings), "
                            "'sms-consent' (enable text notifications)."
                        ),
                        "enum": [
                            "meal-suggestions", "spoilage-alerts", "storage-coach",
                            "smart-notifications", "pickup-reminders", "sms-consent",
                        ],
                    },
                    "listing_id": {
                        "type": "string",
                        "description": "For 'open_listing': UUID of the food listing to open.",
                    },
                    "target_id": {
                        "type": "string",
                        "description": (
                            "For 'focus': data-ai-id of the element to focus "
                            "(e.g. 'search-input', 'share-title-input')."
                        ),
                    },
                    "lang": {
                        "type": "string",
                        "enum": ["en", "es"],
                        "description": "For 'set_language': UI language code.",
                    },
                    "reason": {
                        "type": "string",
                        "description": (
                            "Short human-readable reason shown to the user "
                            "(e.g. 'Opening Find Food so you can browse listings near you')."
                        ),
                    },
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_food_listing",
            "description": (
                "Create a new food donation listing for the authenticated user. "
                "Use this when the user wants to share / post / donate / list food. "
                "Confirm key fields (title, quantity, unit, category) with the user "
                "before calling. Only call once the user clearly says yes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "UUID of the donor (the authenticated user).",
                    },
                    "title": {
                        "type": "string",
                        "description": "Short product name (e.g. '5 loaves of sourdough bread').",
                    },
                    "quantity": {
                        "type": "number",
                        "description": "Numeric quantity (must be > 0).",
                    },
                    "unit": {
                        "type": "string",
                        "description": "Unit for the quantity (e.g. 'items','loaves','kg','lbs','servings','boxes').",
                    },
                    "category": {
                        "type": "string",
                        "enum": ["produce", "bakery", "dairy", "pantry", "meat", "prepared", "other"],
                        "description": "Food category.",
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional details about condition, ingredients, packaging.",
                    },
                    "expiry_date": {
                        "type": "string",
                        "description": "Required best-by / expiration date as YYYY-MM-DD. Ask the donor before posting.",
                    },
                    "expiration_date": {
                        "type": "string",
                        "description": "Alias for expiry_date (prefer expiry_date).",
                    },
                    "location": {
                        "type": "string",
                        "description": "Pickup location / full street address. STRONGLY recommended — without an address the listing has no map pin.",
                    },
                    "community_name": {
                        "type": "string",
                        "description": "Name of the community / school this listing is shared with (e.g. 'Alameda Unified'). REQUIRED — ask the donor and get explicit confirmation before posting.",
                    },
                    "community_id": {
                        "type": "string",
                        "description": "Optional community UUID if already known from get_active_communities.",
                    },
                    "community_confirmed": {
                        "type": "boolean",
                        "description": "Must be true. Set only after the donor explicitly confirms which community/school the listing is for (yes to profile default or picks a name).",
                    },
                    "latitude": {
                        "type": "number",
                        "description": "Optional explicit latitude for the pickup spot. The server will auto-geocode the location string if omitted.",
                    },
                    "longitude": {
                        "type": "number",
                        "description": "Optional explicit longitude for the pickup spot.",
                    },
                    "dietary_tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional tags like 'vegetarian','vegan','gluten-free','halal'.",
                    },
                    "allergens": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional allergens present (e.g. 'nuts','dairy','gluten').",
                    },
                    "image_url": {
                        "type": "string",
                        "description": "Optional public URL of a photo for this listing (https://... Supabase storage URL). Include when the donor uploads a photo before posting.",
                    },
                },
                "required": ["user_id", "title", "quantity", "unit", "category", "expiry_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "claim_listing",
            "description": (
                "Claim a food listing on behalf of the authenticated user. Use this "
                "when the user clearly wants to reserve / take / pick up / claim a "
                "specific listing. You MUST already have the listing_id from a prior "
                "search_food_near_user or get_recent_listings call — never invent one. "
                "Confirm once before calling (e.g. 'Want me to claim X for you?')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "UUID of the recipient (the authenticated user).",
                    },
                    "listing_id": {
                        "type": "string",
                        "description": "UUID of the food listing to claim (from search results).",
                    },
                    "quantity": {
                        "type": "integer",
                        "description": "How many units to claim (default 1, must be <= listing's available quantity).",
                    },
                    "pickup_date": {
                        "type": "string",
                        "description": "Optional ISO date (YYYY-MM-DD) the user plans to pick up.",
                    },
                    "people": {
                        "type": "integer",
                        "description": "Optional number of people this claim will feed.",
                    },
                },
                "required": ["user_id", "listing_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_claim",
            "description": (
                "Cancel/release a claim the authenticated user has made on a food "
                "listing. Use when the user says things like 'cancel my claim', "
                "'release it', 'I can't pick it up', 'never mind'. Provide either "
                "claim_id (preferred) OR listing_id; if only listing_id is given "
                "the tool will look up the user's active claim on that listing."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "UUID of the authenticated user."},
                    "claim_id": {"type": "string", "description": "UUID of the food_claims row to cancel."},
                    "listing_id": {"type": "string", "description": "UUID of the food listing — used to find the user's claim if claim_id unknown."},
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "confirm_claim",
            "description": (
                "Mark the authenticated user's claim as completed (pickup confirmed). "
                "Use when the user says 'I got it', 'picked it up', 'confirm pickup', "
                "or shares a confirmation code. Provide either claim_id (preferred) "
                "OR listing_id."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "UUID of the authenticated user."},
                    "claim_id": {"type": "string", "description": "UUID of the food_claims row to confirm."},
                    "listing_id": {"type": "string", "description": "UUID of the food listing — used to find the user's claim if claim_id unknown."},
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
                "Alias of create_food_listing. Create a new food donation "
                "listing for the authenticated user. Use whichever name the "
                "system prompt refers to."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "title": {"type": "string"},
                    "quantity": {"type": "number"},
                    "unit": {"type": "string"},
                    "category": {
                        "type": "string",
                        "enum": ["produce", "bakery", "dairy", "pantry", "meat", "prepared", "other"],
                    },
                    "description": {"type": "string"},
                    "expiry_date": {"type": "string", "description": "Required. Best-by / expiration date as YYYY-MM-DD."},
                    "expiration_date": {"type": "string", "description": "Alias for expiry_date (prefer expiry_date)."},
                    "location": {"type": "string", "description": "Pickup street address — required for the listing to appear on the map."},
                    "community_name": {"type": "string", "description": "Community/school the donation is shared with — required after donor confirms."},
                    "community_id": {"type": "string", "description": "Optional community UUID if already known."},
                    "community_confirmed": {"type": "boolean", "description": "Must be true after the donor confirms the community."},
                    "latitude": {"type": "number"},
                    "longitude": {"type": "number"},
                    "dietary_tags": {"type": "array", "items": {"type": "string"}},
                    "allergens": {"type": "array", "items": {"type": "string"}},
                    "image_url": {"type": "string", "description": "Optional public photo URL (https://...). Include when the donor provides a photo."},
                },
                "required": ["user_id", "title", "quantity", "unit", "category", "expiry_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bulk_import_listings",
            "description": (
                "Create multiple food donation listings in one shot for the "
                "authenticated user. Accept either a CSV string (csv_text) "
                "with columns title,quantity,unit,category[,description,"
                "expiry_date,location] OR a pre-parsed listings array. Use "
                "after the user confirms a bulk preview."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "csv_text": {"type": "string", "description": "Raw CSV. First row must be a header."},
                    "listings": {
                        "type": "array",
                        "description": "Pre-parsed listings (alternative to csv_text).",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "quantity": {"type": "number"},
                                "unit": {"type": "string"},
                                "category": {"type": "string"},
                                "description": {"type": "string"},
                                "expiry_date": {"type": "string"},
                                "location": {"type": "string"},
                            },
                            "required": ["title", "quantity", "unit", "category"],
                        },
                    },
                    "default_address": {
                        "type": "string",
                        "description": (
                            "Batch-wide pickup address applied to any row that "
                            "has no address column of its own. Pass the donor's "
                            "profile address, or an address they give you on a "
                            "retry. If omitted, the server falls back to the "
                            "donor's saved profile address."
                        ),
                    },
                    "default_expiry_date": {
                        "type": "string",
                        "description": (
                            "Batch-wide best-by date (YYYY-MM-DD) applied to rows "
                            "missing expiry_date. Ask the donor before importing."
                        ),
                    },
                    "community_name": {
                        "type": "string",
                        "description": "Community/school for the whole batch — required after donor confirms.",
                    },
                    "community_id": {"type": "string", "description": "Optional community UUID if known."},
                    "community_confirmed": {
                        "type": "boolean",
                        "description": "Must be true after the donor confirms the community for this batch.",
                    },
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_donor_expiring_listings",
            "description": (
                "List the authenticated donor's own active listings whose "
                "expiry_date or pickup_by falls within the next N days "
                "(default 2). Use when warning the donor about expiring food."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "days": {"type": "integer", "description": "Look-ahead window in days (default 2, max 14)."},
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "attach_photos_to_listing",
            "description": (
                "Attach a photo (image URL) to one of the authenticated user's "
                "food listings. Use after the user uploads/shares an image and "
                "you have a public URL for it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "listing_id": {"type": "string"},
                    "image_url": {"type": "string", "description": "Public URL of the uploaded image."},
                },
                "required": ["user_id", "listing_id", "image_url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "navigate_ui",
            "description": "Alias of ui_action. Drive the DoGoods web UI on the user's behalf.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string"},
                    "path": {"type": "string"},
                    "listing_id": {"type": "string"},
                    "target_id": {"type": "string"},
                    "lang": {"type": "string", "enum": ["en", "es"]},
                    "reason": {"type": "string"},
                    "target": {"type": "string", "description": "Alias for path when action='open'."},
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "meal_suggestions",
            "description": "Alias of get_recipes. Suggest meals for given ingredients.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ingredients": {"type": "array", "items": {"type": "string"}},
                    "dietary_preferences": {"type": "string"},
                },
                "required": ["ingredients"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deactivate_listing",
            "description": (
                "Soft-remove one of the authenticated user's own food listings by "
                "setting its status to 'expired'. The row stays in the database. "
                "Use when the donor says 'mark as unavailable', 'it's all gone now', "
                "'hide my listing', or 'take it down'. "
                "Provide listing_id (preferred) OR the listing title to look it up."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "UUID of the authenticated user (the donor)."},
                    "listing_id": {"type": "string", "description": "UUID of the food_listings row to deactivate."},
                    "title": {"type": "string", "description": "Listing title to look up if listing_id is not known."},
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
                "Permanently delete one of the authenticated user's own food listings "
                "from the database. Use ONLY when the user explicitly says 'delete', "
                "'permanently delete', 'remove from database', or 'erase my listing'. "
                "This is irreversible — confirm with the user before calling. "
                "Provide listing_id (preferred) OR the listing title to look it up."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "UUID of the authenticated user (the donor)."},
                    "listing_id": {"type": "string", "description": "UUID of the food_listings row to delete."},
                    "title": {"type": "string", "description": "Listing title to look up if listing_id is not known."},
                    "confirmed": {"type": "boolean", "description": "Must be true — set only after the user has explicitly confirmed the deletion."},
                },
                "required": ["user_id", "confirmed"],
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
                "'my active donations', 'my food shares', 'has anyone claimed my food', "
                "'how many claims do my listings have'. Each listing comes back with "
                "a `claims_count` (active claims on it), `has_photo`, and an overall "
                "`views_tracking` field. View tracking is NOT live yet — when the "
                "user asks 'how many views', honestly answer that we don't track "
                "views and pivot to claims/photo/description coaching."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "UUID of the authenticated user."},
                    "status": {
                        "type": "string",
                        "enum": ["active", "approved", "expired", "claimed", "all"],
                        "description": "Filter by status. Default: active+approved.",
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
                "natural-language edits the donor speaks in chat: 'change pickup "
                "time to 7pm' (put free-text pickup info in description), "
                "'increase servings to 10', 'update the description', "
                "'mark it as unavailable' / 'all gone' (sets status=expired), "
                "'rename to ...', 'change category to bakery', 'add allergen: eggs'. "
                "Identify the listing by listing_id when known, or pass title_lookup "
                "(matches the most recent active listing whose title ILIKEs the "
                "value). If neither is supplied, the most recently posted active "
                "listing is targeted. Only fields you actually pass are written — "
                "everything else is left alone. For photos, prefer attach_photos_to_"
                "listing; image_url here REPLACES the cover photo."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "UUID of the authenticated donor."},
                    "listing_id": {"type": "string", "description": "UUID of the listing. Preferred."},
                    "title_lookup": {"type": "string", "description": "Substring of the listing title — used when listing_id is unknown."},
                    "title": {"type": "string", "description": "New title."},
                    "quantity": {"type": "number", "description": "New quantity (must be > 0)."},
                    "unit": {"type": "string", "description": "New unit (loaves, lbs, trays, etc.)."},
                    "description": {"type": "string", "description": "New description text."},
                    "category": {"type": "string", "description": "produce / bakery / dairy / pantry / meat / seafood / frozen / snacks / beverages / prepared / other."},
                    "expiry_date": {"type": "string", "description": "YYYY-MM-DD."},
                    "pickup_by": {"type": "string", "description": "ISO-8601 timestamp (YYYY-MM-DDTHH:MM[:SS][±HH:MM]). For free-text like 'tonight 7pm', put it in description instead."},
                    "location": {"type": "string", "description": "New pickup address."},
                    "dietary_tags": {"type": "array", "items": {"type": "string"}},
                    "allergens": {"type": "array", "items": {"type": "string"}},
                    "image_url": {"type": "string", "description": "Public URL replacing the cover photo."},
                    "status": {
                        "type": "string",
                        "description": (
                            "Lifecycle. Accepts 'available' / 'live' / 'active' → approved, "
                            "'unavailable' / 'hidden' / 'taken down' / 'gone' / 'all gone' → expired, "
                            "or the literal DB enum values approved / expired / completed / claimed / cancelled."
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
            "name": "bulk_post_food_listings",
            "description": "Alias of bulk_import_listings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "csv_text": {"type": "string"},
                    "listings": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "quantity": {"type": "number"},
                                "unit": {"type": "string"},
                                "category": {"type": "string"},
                                "description": {"type": "string"},
                                "expiry_date": {"type": "string"},
                                "location": {"type": "string"},
                            },
                            "required": ["title", "quantity", "unit", "category"],
                        },
                    },
                    "default_address": {"type": "string"},
                    "community_name": {"type": "string"},
                    "community_id": {"type": "string"},
                    "community_confirmed": {"type": "boolean"},
                },
                "required": ["user_id"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool execution dispatcher
# ---------------------------------------------------------------------------

async def execute_tool(name: str, arguments: dict) -> dict:
    """Route a tool call to its handler and return the result."""
    handlers = {
        "search_food_near_user": _search_food_near_user,
        "get_recent_listings": _get_recent_listings,
        "get_user_profile": _get_user_profile,
        "update_user_profile": _update_user_profile,
        "get_pickup_schedule": _get_pickup_schedule,
        "create_reminder": _create_reminder,
        "get_mapbox_route": _get_mapbox_route,
        "query_distribution_centers": _query_distribution_centers,
        "get_user_dashboard": _get_user_dashboard,
        "check_pickup_schedule": _check_pickup_schedule,
        "get_recipes": _get_recipes,
        "get_storage_tips": _get_storage_tips,
        "get_active_communities": _get_active_communities,
        "get_user_notifications": _get_user_notifications,
        "send_notification": _send_notification,
        "mark_notifications_read": _mark_notifications_read,
        "ui_action": _ui_action,
        "create_food_listing": _create_food_listing,
        "claim_listing": _claim_food_listing,
        "cancel_claim": _cancel_claim,
        "confirm_claim": _confirm_claim,
        "post_food_listing": _create_food_listing,
        "bulk_import_listings": _bulk_import_listings,
        "get_donor_expiring_listings": _get_donor_expiring_listings,
        "attach_photos_to_listing": _attach_photos_to_listing,
        "navigate_ui": _navigate_ui,
        "meal_suggestions": _get_recipes,
        "bulk_post_food_listings": _bulk_import_listings,
        "deactivate_listing": _deactivate_listing,
        "delete_listing": _delete_listing,
        "get_user_listings": _get_user_listings,
        "update_food_listing": _update_food_listing,
        "update_listing": _update_food_listing,
        "edit_listing": _update_food_listing,
    }

    handler = handlers.get(name)
    if handler is None:
        logger.warning("Unknown tool requested: %s", name)
        return {"error": f"Unknown tool: {name}"}

    try:
        return await handler(**arguments)
    except Exception as exc:
        logger.error("Tool %s failed: %s", name, exc)
        return {"error": f"Tool execution failed: {str(exc)}"}


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

async def _get_recent_listings(
    hours: int = 72,
    limit: int = 10,
    category: Optional[str] = None,
) -> dict:
    """Return newly posted, still-available food listings."""
    from backend.ai_engine import supabase_get

    logger.info(
        "get_recent_listings: hours=%s limit=%s category=%s",
        hours, limit, category,
    )

    safe_hours = max(1, min(int(hours), 24 * 14))
    safe_limit = max(1, min(int(limit), 25))
    cutoff_iso = (datetime.now(timezone.utc) - timedelta(hours=safe_hours)).isoformat()
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    params: dict = {
        "select": (
            "id,title,description,category,quantity,unit,"
            "latitude,longitude,full_address,location,donor_name,"
            "community_id,communities(id,name),"
            "expiry_date,pickup_by,status,dietary_tags,allergens,created_at"
        ),
        "status": "in.(approved,active)",
        # Recipients see donations only; food REQUESTS are a separate feed.
        "listing_type": "eq.donation",
        # Include listings with no expiry_date (non-perishable/unlabeled) plus
        # those whose expiry_date has not yet passed. Without the IS NULL branch,
        # unlabeled items never appear in recent-listings results.
        "or": f"(expiry_date.is.null,expiry_date.gte.{today_str})",
        "created_at": f"gte.{cutoff_iso}",
        "order": "created_at.desc",
        "limit": str(safe_limit),
    }
    if category:
        params["category"] = f"eq.{category}"

    try:
        rows = await supabase_get("food_listings", params)
    except Exception as exc:
        logger.error("Failed to fetch recent listings: %s", exc)
        return {"error": f"Could not fetch recent listings: {str(exc)}"}

    now = datetime.now(timezone.utc)
    listings = []
    for row in rows:
        if not _listing_is_fresh_enough(row, now=now):
            continue
        created_at = row.get("created_at")
        hours_ago = None
        if created_at:
            try:
                created_dt = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
                hours_ago = max(0, int((now - created_dt).total_seconds() // 3600))
            except Exception:
                hours_ago = None
        listings.append({
            "id": row.get("id"),
            "title": row.get("title"),
            "category": row.get("category"),
            "quantity": row.get("quantity"),
            "unit": row.get("unit"),
            "latitude": row.get("latitude"),
            "longitude": row.get("longitude"),
            "address": row.get("full_address") or _extract_location_text(row.get("location")),
            "pickup_by": row.get("pickup_by"),
            "expiry_date": row.get("expiry_date"),
            # donor_name excluded — see search_food_near_user for rationale.
            "created_at": created_at,
            "hours_ago": hours_ago,
            "community_name": (
                (row.get("communities") or {}).get("name")
                or row.get("community_name")
                or None
            ),
        })

    if not listings:
        window_label = f"in the last {safe_hours} hour{'s' if safe_hours != 1 else ''}"
        if category:
            return {
                "listings": [],
                "total": 0,
                "hours": safe_hours,
                "summary": f"No new {category} listings were posted {window_label}.",
            }
        return {
            "listings": [],
            "total": 0,
            "hours": safe_hours,
            "summary": f"No new listings were posted {window_label}.",
        }

    summary = f"Found {len(listings)} new listing{'s' if len(listings) != 1 else ''} from the last {safe_hours} hour{'s' if safe_hours != 1 else ''}."
    if category:
        summary = f"Found {len(listings)} new {category} listing{'s' if len(listings) != 1 else ''} from the last {safe_hours} hour{'s' if safe_hours != 1 else ''}."

    return {
        "listings": listings,
        "total": len(listings),
        "hours": safe_hours,
        "summary": summary,
    }

# Allowed UI navigation routes (mirrors the React Router config). Keeping this
# server-side prevents the model from sending the user to bogus paths.
_UI_ALLOWED_PATHS = {
    "/", "/find", "/share", "/dashboard", "/profile",
    "/donate", "/notifications", "/recipes", "/donations",
    "/near-me", "/how-it-works", "/contact", "/blog", "/news", "/faqs",
    "/login", "/signup", "/sponsors", "/featured",
    "/testimonials", "/impact-story", "/terms", "/privacy",
    "/cookies", "/listings", "/receipts", "/settings", "/success",
}

_UI_ALLOWED_ACTIONS = {
    "navigate", "open_assistant", "close_assistant", "expand_assistant",
    "open_listing", "open_map", "clear_map", "scroll_to_top",
    "scroll_to_bottom", "focus", "set_language",
    # Modal surfaces (recipient AI helpers). The frontend maps each target
    # to the right route/overlay via MODAL_TARGET_ROUTES in UIControlContext.
    "open_modal", "close_modal", "toggle_modal",
}

# Modal targets the frontend knows how to open (mirrors MODAL_TARGET_ROUTES
# in utils/UIControlContext.jsx). Keeping this server-side stops the model
# from naming a modal that doesn't exist.
_UI_ALLOWED_MODAL_TARGETS = {
    "meal-suggestions", "spoilage-alerts", "storage-coach",
    "smart-notifications", "pickup-reminders", "sms-consent",
}


async def _ui_action(
    action: str,
    path: Optional[str] = None,
    target: Optional[str] = None,
    listing_id: Optional[str] = None,
    target_id: Optional[str] = None,
    lang: Optional[str] = None,
    reason: Optional[str] = None,
    **_ignored,
) -> dict:
    """Validate a UI directive and echo it back for the frontend to execute.

    The actual navigation/UI manipulation runs in the browser. The backend's
    only job is to confirm the action is well-formed so GPT gets a reliable
    signal it can talk about in its reply.
    """
    if action not in _UI_ALLOWED_ACTIONS:
        return {"ok": False, "error": f"Unsupported UI action: {action}"}

    payload = {"ok": True, "action": action}

    if action == "navigate":
        if not path or not isinstance(path, str):
            return {"ok": False, "error": "navigate requires a 'path'"}
        # Strip trailing slash (except root) and normalize
        norm = path if path == "/" else path.rstrip("/")
        if norm not in _UI_ALLOWED_PATHS:
            return {
                "ok": False,
                "error": f"Path '{path}' is not a known route.",
                "allowed_paths": sorted(_UI_ALLOWED_PATHS),
            }
        payload["path"] = norm

    elif action in ("open_modal", "toggle_modal"):
        norm_target = str(target or "").strip().replace("_", "-")
        if not norm_target:
            return {"ok": False, "error": f"{action} requires a 'target'"}
        if norm_target not in _UI_ALLOWED_MODAL_TARGETS:
            return {
                "ok": False,
                "error": f"Modal target '{target}' is not a known surface.",
                "allowed_targets": sorted(_UI_ALLOWED_MODAL_TARGETS),
            }
        payload["target"] = norm_target

    elif action == "close_modal":
        if target:
            payload["target"] = str(target).strip().replace("_", "-")

    elif action == "open_listing":
        if not listing_id:
            return {"ok": False, "error": "open_listing requires 'listing_id'"}
        payload["listing_id"] = listing_id

    elif action == "focus":
        if not target_id:
            return {"ok": False, "error": "focus requires 'target_id'"}
        payload["target_id"] = target_id

    elif action == "set_language":
        if lang not in ("en", "es"):
            return {"ok": False, "error": "lang must be 'en' or 'es'"}
        payload["lang"] = lang

    if reason:
        payload["reason"] = reason

    logger.info("ui_action: %s %s", action, {k: v for k, v in payload.items() if k != "action"})
    return payload


# ---------------------------------------------------------------------------
# Haversine distance helper
# ---------------------------------------------------------------------------
def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in km between two lat/lng points."""
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


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

# Map common synonyms / GPT guesses → actual DB enum values for category.
# DB enum (food_category): produce, dairy, bakery, pantry, meat, seafood,
# frozen, snacks, beverages, prepared, other.
_FOOD_TYPE_SYNONYMS: dict[str, Optional[str]] = {
    # Produce
    "vegetable": "produce", "vegetables": "produce", "veggie": "produce",
    "veggies": "produce", "greens": "produce", "leafy greens": "produce",
    "salad": "produce", "fruit": "produce", "fruits": "produce",
    "produce": "produce", "vegetal": "produce",
    # Bakery
    "bread": "bakery", "breads": "bakery", "bakery": "bakery",
    "baked": "bakery", "baked goods": "bakery", "pastry": "bakery",
    "pastries": "bakery", "bagel": "bakery", "bagels": "bakery",
    "croissant": "bakery", "muffin": "bakery", "muffins": "bakery",
    "cake": "bakery", "cakes": "bakery", "donut": "bakery", "donuts": "bakery",
    # Dairy
    "dairy": "dairy", "milk": "dairy", "cheese": "dairy", "yogurt": "dairy",
    "yoghurt": "dairy", "butter": "dairy", "cream": "dairy", "eggs": "dairy",
    "egg": "dairy", "milk product": "dairy", "milk products": "dairy",
    "dairy product": "dairy", "dairy products": "dairy",
    # Meat
    "meat": "meat", "meats": "meat", "beef": "meat", "pork": "meat",
    "chicken": "meat", "poultry": "meat", "turkey": "meat", "lamb": "meat",
    "ground meat": "meat", "ground beef": "meat",
    # Seafood
    "seafood": "seafood", "fish": "seafood", "shellfish": "seafood",
    "shrimp": "seafood", "salmon": "seafood", "tuna": "seafood",
    "crab": "seafood",
    # Frozen
    "frozen": "frozen", "frozen meal": "frozen", "frozen meals": "frozen",
    "frozen food": "frozen", "frozen foods": "frozen", "ice cream": "frozen",
    # Snacks
    "snack": "snacks", "snacks": "snacks", "chips": "snacks",
    "crackers": "snacks", "cookies": "snacks", "candy": "snacks",
    "granola bar": "snacks", "granola bars": "snacks",
    # Beverages
    "beverage": "beverages", "beverages": "beverages", "drink": "beverages",
    "drinks": "beverages", "juice": "beverages", "soda": "beverages",
    "water": "beverages", "tea": "beverages", "coffee": "beverages",
    # Prepared
    "prepared": "prepared", "prepared meal": "prepared",
    "prepared meals": "prepared", "prepared food": "prepared",
    "prepared foods": "prepared", "cooked": "prepared",
    "cooked meal": "prepared", "cooked meals": "prepared", "meal": "prepared",
    "meals": "prepared", "hot meal": "prepared", "hot meals": "prepared",
    "hot food": "prepared", "hot foods": "prepared",
    "ready meal": "prepared", "ready meals": "prepared", "takeout": "prepared",
    "ready to eat": "prepared", "ready-to-eat": "prepared",
    "ready to eat food": "prepared", "ready-to-eat food": "prepared",
    "sandwich": "prepared", "sandwiches": "prepared", "leftover": "prepared",
    "leftovers": "prepared",
    # Pantry / dry / canned / grains / staples
    "grain": "pantry", "grains": "pantry", "rice": "pantry", "bean": "pantry",
    "beans": "pantry", "lentil": "pantry", "lentils": "pantry",
    "pasta": "pantry", "noodle": "pantry", "noodles": "pantry",
    "cereal": "pantry", "cereals": "pantry", "oat": "pantry", "oats": "pantry",
    "oatmeal": "pantry", "flour": "pantry", "sugar": "pantry",
    "salt": "pantry", "canned": "pantry", "can": "pantry", "cans": "pantry",
    "canned good": "pantry", "canned goods": "pantry", "pantry": "pantry",
    "dry": "pantry", "dry goods": "pantry", "nonperishable": "pantry",
    "non-perishable": "pantry", "shelf stable": "pantry",
    "shelf-stable": "pantry", "staple": "pantry", "staples": "pantry",
    "long shelf life": "pantry", "long-lasting": "pantry",
    "longest lasting": "pantry", "lasts long": "pantry",
    # Conditions / adjectives — not categories. Let the model decide whether
    # to filter; pass-through (None) so search returns everything available
    # and the AI describes what's there in natural language.
    "fresh": None, "fresh food": None, "fresh foods": None,
    "chilled": None, "cold": None, "cold food": None,
    "raw": None, "raw ingredients": None, "raw food": None,
    "ingredients": None, "ingredient": None,
    "healthy": None, "healthy food": None, "healthy meal": None,
    "healthy meals": None, "quick": None, "quick meal": None,
    "quick meals": None, "easy": None,
    # Ambiguous / unmapped: let model decide (no category filter).
    "protein": None, "proteins": None, "other": None,
}


async def _search_food_near_user(
    user_id: str,
    radius_km: float = 10,
    food_type: Optional[str] = None,
    max_results: int = 20,
    dietary_tags: Optional[list] = None,
    exclude_allergens: Optional[list] = None,
    expiry_within_days: Optional[int] = None,
    min_quantity: Optional[float] = None,
    **_ignored,
) -> dict:
    """Search available food listings near the user's location.

    1. Fetch the user's location from the users table
    2. Query food_listings with status in [approved, active], not expired
    3. Filter by Haversine distance and optional food_type
    4. Apply post-fetch filters for dietary_tags, exclude_allergens,
       expiry_within_days, and min_quantity
    5. Format natural-language-friendly results
    """
    from backend.ai_engine import supabase_get

    # Normalize GPT-supplied food_type synonyms to actual DB enum values.
    if food_type:
        normalized = _FOOD_TYPE_SYNONYMS.get(food_type.strip().lower())
        food_type = normalized  # May become None for "other" / unmapped values

    # Normalize dietary/allergen filter terms for case-insensitive comparison.
    def _norm_tag(s: str) -> str:
        return (s or "").strip().lower().replace("_", "-").replace(" ", "-")

    want_diet = {_norm_tag(t) for t in (dietary_tags or []) if t}
    bad_allergens = {_norm_tag(t) for t in (exclude_allergens or []) if t}

    logger.info(
        "search_food_near_user: user=%s radius=%skm type=%s diet=%s "
        "exclude_allergens=%s expiry_within=%s min_qty=%s",
        user_id, radius_km, food_type, want_diet, bad_allergens,
        expiry_within_days, min_quantity,
    )

    # --- 1. Get user location ---
    # Prefer the geocoded latitude/longitude columns populated when the
    # user saves their profile address. Fall back to the legacy `location`
    # JSON column for older rows that pre-date geocoding.
    user_lat, user_lng = None, None
    try:
        user_rows = await supabase_get("users", {
            "id": f"eq.{user_id}",
            "select": "id,name,organization,location,latitude,longitude,address,created_at",
        })
        if user_rows:
            profile = user_rows[0]
            # 1a) New canonical columns (numeric — PostgREST may return strings)
            raw_lat = profile.get("latitude")
            raw_lng = profile.get("longitude")
            if raw_lat is not None and raw_lng is not None:
                try:
                    user_lat = float(raw_lat)
                    user_lng = float(raw_lng)
                except (TypeError, ValueError):
                    user_lat, user_lng = None, None
            # 1b) Legacy JSON column fallback
            if user_lat is None or user_lng is None:
                loc = profile.get("location")
                if isinstance(loc, dict):
                    user_lat = loc.get("latitude")
                    user_lng = loc.get("longitude")
                elif isinstance(loc, str):
                    try:
                        parsed = json.loads(loc)
                        user_lat = parsed.get("latitude")
                        user_lng = parsed.get("longitude")
                    except (ValueError, TypeError):
                        pass
    except Exception as exc:
        logger.error("User lookup failed: %s", exc)

    # --- 2. Query food_listings with bounding box pre-filter ---
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    params: dict = {
        "select": (
            "id,title,description,category,quantity,unit,"
            "latitude,longitude,full_address,location,donor_name,user_id,"
            "community_id,communities(id,name),"
            "expiry_date,pickup_by,status,"
            "dietary_tags,allergens,created_at"
        ),
        "status": "in.(approved,active)",
        # Search returns donations only; requests live in their own feed.
        "listing_type": "eq.donation",
        # Include listings with no expiry_date (non-perishable/unlabeled) plus
        # those whose expiry_date has not yet passed. Without the IS NULL branch,
        # unlabeled items never appear in search results.
        "or": f"(expiry_date.is.null,expiry_date.gte.{today_str})",
        "order": "created_at.desc",
        "limit": "100",
    }
    if food_type:
        params["category"] = f"eq.{food_type}"

    # Tighter expiry window when caller asks for "expiring soon" style queries.
    # Listings without an expiry_date stay included (non-perishable / unlabeled).
    if expiry_within_days is not None and expiry_within_days >= 0:
        cutoff = (
            datetime.now(timezone.utc) + timedelta(days=int(expiry_within_days))
        ).strftime("%Y-%m-%d")
        params["or"] = (
            f"(expiry_date.is.null,"
            f"and(expiry_date.gte.{today_str},expiry_date.lte.{cutoff}))"
        )

    # Server-side minimum quantity filter.
    if min_quantity is not None and min_quantity > 0:
        params["quantity"] = f"gte.{min_quantity}"

    # Bounding box pre-filter: narrow DB results to ~radius before fetching
    if user_lat is not None and user_lng is not None:
        # Rough degree offset for the given radius (1 deg lat ≈ 111 km)
        lat_offset = radius_km / 111.0
        lng_offset = radius_km / (111.0 * max(math.cos(math.radians(user_lat)), 0.01))
        # PostgREST doesn't support duplicate query-param keys, so bounding-box
        # filtering across two columns uses a single `and` compound filter.
        params["and"] = (
            f"(latitude.gte.{user_lat - lat_offset},"
            f"latitude.lte.{user_lat + lat_offset},"
            f"longitude.gte.{user_lng - lng_offset},"
            f"longitude.lte.{user_lng + lng_offset})"
        )

    try:
        listings = await supabase_get("food_listings", params)
    except Exception as exc:
        logger.error("Food listings fetch failed: %s", exc)
        return {"listings": [], "total": 0, "error": f"Database query failed: {exc}"}

    # --- 3. Filter by distance ---
    now = datetime.now(timezone.utc)
    results = []
    for listing in listings:
        if not _listing_is_fresh_enough(listing, now=now):
            continue
        # Exclude the current user's own listings from search results.
        # The claim tool enforces this at DB level, but filtering here prevents
        # GPT from seeing and mis-handling listings with a matching donor_name.
        if str(listing.get("user_id") or "") == str(user_id):
            continue
        lat = listing.get("latitude")
        lng = listing.get("longitude")

        if lat is not None and lng is not None and user_lat is not None and user_lng is not None:
            try:
                dist = _haversine(user_lat, user_lng, float(lat), float(lng))
            except (ValueError, TypeError):
                dist = None
        else:
            dist = None

        # Include listing if within radius, or if no location data available
        if dist is not None and dist > radius_km:
            continue

        # Dietary / allergen filters (post-fetch so we can normalise tags).
        # Listing tag columns may be a list, comma-separated string, or null.
        def _as_tag_set(val) -> set:
            if val is None:
                return set()
            if isinstance(val, str):
                items = [t for t in val.replace(";", ",").split(",") if t.strip()]
            elif isinstance(val, (list, tuple)):
                items = list(val)
            else:
                return set()
            return {_norm_tag(str(t)) for t in items if str(t).strip()}

        listing_diet = _as_tag_set(listing.get("dietary_tags"))
        listing_allergens = _as_tag_set(listing.get("allergens"))

        # Require ALL requested dietary tags to be present on the listing.
        if want_diet and not want_diet.issubset(listing_diet):
            continue
        # Drop listings that contain ANY excluded allergen.
        if bad_allergens and (bad_allergens & listing_allergens):
            continue

        result = {
            "id": listing.get("id"),
            "title": listing.get("title"),
            "description": listing.get("description", "")[:200],
            "category": listing.get("category"),
            "quantity": listing.get("quantity"),
            "unit": listing.get("unit"),
            "address": listing.get("full_address") or _extract_location_text(listing.get("location")),
            # donor_name intentionally excluded: GPT must NOT use display names
            # to infer ownership — two accounts can share the same name. Use
            # listing_owner_id vs the current user_id context for that check.
            "listing_owner_id": listing.get("user_id"),
            "expiry_date": listing.get("expiry_date"),
            "pickup_by": listing.get("pickup_by"),
            "dietary_tags": listing.get("dietary_tags", []),
            "allergens": listing.get("allergens", []),
            "distance_km": round(dist, 1) if dist is not None else None,
            "latitude": lat,
            "longitude": lng,
            "community_name": (
                (listing.get("communities") or {}).get("name")
                or listing.get("community_name")
                or None
            ),
        }
        results.append(result)

    # Sort by distance (nearest first), nulls last
    results.sort(key=lambda r: r["distance_km"] if r["distance_km"] is not None else 9999)
    results = results[:max_results]

    # --- 4. Format natural response summary ---
    if results:
        summary_parts = []
        for i, r in enumerate(results, 1):
            dist_str = f"{r['distance_km']} km away" if r["distance_km"] is not None else "distance unknown"
            summary_parts.append(
                f"{i}. **{r['title']}** ({r['category'] or 'uncategorized'}) — "
                f"{r['quantity']} {r['unit'] or 'items'}, {dist_str}. "
                f"Pickup: {r['address'] or 'contact donor'}."
            )
        summary = (
            f"Found {len(results)} food item(s) near you:\n" 
            + "\n".join(summary_parts)
            + "\n\n(Quantities shown are current now but may change as others claim food.)"
        )
    else:
        active_filters = []
        if food_type:
            active_filters.append(f"category={food_type}")
        if want_diet:
            active_filters.append(f"dietary={','.join(sorted(want_diet))}")
        if bad_allergens:
            active_filters.append(f"no {','.join(sorted(bad_allergens))}")
        if expiry_within_days is not None:
            active_filters.append(f"expiring within {expiry_within_days}d")
        if min_quantity:
            active_filters.append(f"qty>={min_quantity}")
        hint = f" (filters: {'; '.join(active_filters)})" if active_filters else ""
        summary = (
            f"No available food listings found within {radius_km} km{hint}. "
            "Try widening your radius, relaxing dietary/allergen filters, "
            "or check back later!"
        )

    return {
        # `listings` is the canonical key. The duplicate `results` field
        # was previously returned for backwards-compat but doubled the
        # tokens spent on every search and never carried different data —
        # downstream consumers all prefer `listings` (see ai_engine
        # _build_memory_snapshot and _persist_conversation compaction).
        "listings": results,
        "total": len(results),
        "radius_km": radius_km,
        "user_location_available": user_lat is not None,
        "filters_applied": {
            "food_type": food_type,
            "dietary_tags": sorted(want_diet) if want_diet else [],
            "exclude_allergens": sorted(bad_allergens) if bad_allergens else [],
            "expiry_within_days": expiry_within_days,
            "min_quantity": min_quantity,
        },
        "summary": summary,
    }


async def _get_user_profile(user_id: str) -> dict:
    """Retrieve user profile with activity summary."""
    from backend.ai_engine import supabase_get

    logger.info("get_user_profile: user=%s", user_id)
    try:
        rows = await supabase_get("users", {
            "id": f"eq.{user_id}",
            "select": (
                "id,name,email,phone,"
                "is_admin,avatar_url,account_type,organization,community_role,"
                "created_at,address,latitude,longitude,address_geocoded_at,"
                "dietary_restrictions,allergies"
            ),
        })
        if not rows:
            return {"user_id": user_id, "profile": None, "message": "User not found."}

        profile = rows[0]

        # Count listings and claims
        listings_count, claims_count = 0, 0
        try:
            listing_rows = await supabase_get("food_listings", {
                "user_id": f"eq.{user_id}",
                "select": "id",
            })
            listings_count = len(listing_rows)
        except Exception:
            pass
        try:
            claim_rows = await supabase_get("food_claims", {
                "claimer_id": f"eq.{user_id}",
                "select": "id",
            })
            claims_count = len(claim_rows)
        except Exception:
            pass

        # Normalise the geocoded coords (PostgREST returns numeric as strings).
        try:
            lat_val = float(profile["latitude"]) if profile.get("latitude") is not None else None
            lng_val = float(profile["longitude"]) if profile.get("longitude") is not None else None
        except (TypeError, ValueError):
            lat_val, lng_val = None, None

        return {
            "user_id": user_id,
            "profile": {
                "name": profile.get("name") or profile.get("email"),
                "email": profile.get("email"),
                # community_role holds the user-facing role (donor/recipient/volunteer).
                # users.role is the Supabase auth role (e.g. 'authenticated') and is
                # NOT selected here to avoid confusing the AI with meaningless values.
                "community_role": profile.get("community_role"),
                "account_type": profile.get("account_type"),
                "organization": profile.get("organization"),
                "is_admin": profile.get("is_admin", False),
                "member_since": profile.get("created_at"),
                # Use only `address` (plain text) — users.location is a JSON
                # {latitude,longitude} dict used for coordinates, not display.
                "address": profile.get("address") or "",
                "latitude": lat_val,
                "longitude": lng_val,
                "address_geocoded_at": profile.get("address_geocoded_at"),
                "dietary_restrictions": profile.get("dietary_restrictions"),
                "allergies": profile.get("allergies"),
            },
            "activity": {
                "listings_shared": listings_count,
                "food_claimed": claims_count,
            },
        }
    except Exception as exc:
        logger.error("Profile fetch failed: %s", exc)
        return {"user_id": user_id, "profile": None, "error": str(exc)}


# Whitelisted columns the AI may write to via update_user_profile. Anything
# not in this set is silently dropped to avoid privilege escalation
# (is_admin, role, etc.) or accidental writes to schema-mismatched fields.
_UPDATABLE_PROFILE_FIELDS = {
    "name",
    "address",
    "phone",
    "organization",
    "community_role",
    "dietary_restrictions",
    "allergies",
    "dietary_preferences",
    "sms_opt_in",
    "sms_notifications_enabled",
    "pickup_reminder_enabled",
    "default_reminder_hours",
}


async def _update_user_profile(user_id: str, **fields) -> dict:
    """Update whitelisted profile fields for the authenticated user."""
    from backend.ai_engine import supabase_patch

    logger.info("update_user_profile: user=%s fields=%s", user_id, list(fields.keys()))
    if not user_id:
        return {"success": False, "error": "missing user_id"}

    updates: dict = {}
    rejected: list[str] = []
    for key, value in fields.items():
        if key not in _UPDATABLE_PROFILE_FIELDS:
            rejected.append(key)
            continue
        # Normalize empty strings to NULL so the UI clears cleanly.
        if isinstance(value, str):
            value = value.strip() or None
        updates[key] = value

    # If user is opting in to SMS, stamp the consent date.
    if updates.get("sms_opt_in") is True:
        from datetime import datetime, timezone
        updates.setdefault("sms_opt_in_date", datetime.now(timezone.utc).isoformat())

    # If address is changing, geocode the new value so search_food_near_user
    # and community distance sorting work immediately — without this the
    # old (or null) latitude/longitude stays in the DB until the user
    # manually re-saves their profile through the React UI.
    new_address = updates.get("address")
    if new_address and isinstance(new_address, str) and new_address.strip():
        try:
            coords = await _forward_geocode(new_address.strip())
            if coords:
                from datetime import datetime, timezone as _tz
                updates["latitude"] = coords[0]
                updates["longitude"] = coords[1]
                updates["address_geocoded_at"] = datetime.now(_tz.utc).isoformat()
        except Exception as geo_exc:
            logger.warning("update_user_profile: address geocode failed (non-fatal): %s", geo_exc)

    if not updates:
        return {
            "success": False,
            "error": "no_updatable_fields",
            "rejected_fields": rejected,
            "allowed_fields": sorted(_UPDATABLE_PROFILE_FIELDS),
        }

    try:
        rows = await supabase_patch(
            "users",
            {"id": f"eq.{user_id}"},
            updates,
        )
        return {
            "success": True,
            "updated_fields": list(updates.keys()),
            "rejected_fields": rejected,
            "profile": (rows[0] if isinstance(rows, list) and rows else None),
        }
    except Exception as exc:
        logger.error("update_user_profile failed: %s", exc)
        return {"success": False, "error": str(exc), "rejected_fields": rejected}


async def _get_pickup_schedule(
    user_id: str,
    include_community_events: bool = True,
    days_ahead: int = 7,
) -> dict:
    """Get upcoming pickup and distribution schedules."""
    from backend.ai_engine import supabase_get

    logger.info(
        "get_pickup_schedule: user=%s events=%s days=%d",
        user_id, include_community_events, days_ahead,
    )

    now = datetime.now(timezone.utc)
    future = now + timedelta(days=days_ahead)

    # --- Pending pickups (user's claimed food) ---
    pickups = []
    try:
        claims = await supabase_get("food_claims", {
            "claimer_id": f"eq.{user_id}",
            "status": "in.(pending,approved)",
            "select": "id,food_id,status,pickup_date,pickup_time,pickup_place,created_at",
            "order": "pickup_date.asc",
        })
        for claim in claims:
            # Fetch linked food listing summary
            food_title = "Food item"
            try:
                food_rows = await supabase_get("food_listings", {
                    "id": f"eq.{claim['food_id']}",
                    "select": "title,full_address,location",
                })
                if food_rows:
                    food_title = food_rows[0].get("title", food_title)
                    claim["address"] = (
                        food_rows[0].get("full_address")
                        or _extract_location_text(food_rows[0].get("location"))
                    )
            except Exception:
                pass

            pickups.append({
                "claim_id": claim.get("id"),
                "food_title": food_title,
                "status": claim.get("status"),
                "pickup_date": claim.get("pickup_date"),
                "pickup_time": claim.get("pickup_time"),
                "address": claim.get("address") or claim.get("pickup_place", ""),
            })
    except Exception as exc:
        logger.error("Claims fetch failed: %s", exc)

    # --- Community distribution events ---
    events = []
    if include_community_events:
        try:
            today_str = now.strftime("%Y-%m-%d")
            future_str = future.strftime("%Y-%m-%d")
            event_rows = await supabase_get("distribution_events", {
                "event_date": f"gte.{today_str}",
                # Apply the upper-bound so days_ahead is actually respected.
                # Previously future_str was computed but never used, causing
                # all upcoming events to be returned regardless of the window.
                "and": f"(event_date.lte.{future_str})",
                "status": "eq.scheduled",
                "select": (
                    "id,title,description,location,event_date,"
                    "start_time,end_time,capacity,registered_count"
                ),
                "order": "event_date.asc",
                "limit": "10",
            })
            for ev in event_rows:
                spots_left = (ev.get("capacity") or 0) - (ev.get("registered_count") or 0)
                events.append({
                    "event_id": ev.get("id"),
                    "title": ev.get("title"),
                    "description": (ev.get("description") or "")[:200],
                    "location": ev.get("location"),
                    "date": ev.get("event_date"),
                    "start_time": ev.get("start_time"),
                    "end_time": ev.get("end_time"),
                    "spots_available": max(spots_left, 0),
                })
        except Exception as exc:
            logger.error("Events fetch failed: %s", exc)

    return {
        "pickups": pickups,
        "events": events,
        "days_ahead": days_ahead,
    }


async def _create_reminder(
    user_id: str,
    message: str,
    trigger_time: str,
    reminder_type: str = "general",
    related_id: Optional[str] = None,
) -> dict:
    """Create a reminder in the ai_reminders table."""
    from backend.ai_engine import supabase_post

    logger.info(
        "create_reminder: user=%s type=%s time=%s",
        user_id, reminder_type, trigger_time,
    )

    # Validate trigger_time is in the future
    try:
        trigger_dt = datetime.fromisoformat(trigger_time.replace("Z", "+00:00"))
        # If the model sends a naive ISO string (no tz offset, no Z) assume UTC
        # so the future-check below doesn't raise a TypeError that the except
        # block misidentifies as "Invalid trigger_time format".
        if trigger_dt.tzinfo is None:
            trigger_dt = trigger_dt.replace(tzinfo=timezone.utc)
        if trigger_dt < datetime.now(timezone.utc):
            return {
                "created": False,
                "error": "Trigger time must be in the future.",
            }
    except (ValueError, TypeError):
        return {
            "created": False,
            "error": "Invalid trigger_time format. Use ISO 8601.",
        }

    data = {
        "user_id": user_id,
        "message": message,
        "trigger_time": trigger_time,
        "reminder_type": reminder_type,
        "sent": False,
    }
    if related_id:
        data["related_id"] = related_id

    try:
        rows = await supabase_post("ai_reminders", data)
        summary = f"Reminder set for {trigger_time}."
        return {
            "success": True,
            "created": True,
            "reminder_id": rows[0].get("id") if rows else None,
            "trigger_time": trigger_time,
            "message": summary,
            "summary": summary,
        }
    except Exception as exc:
        logger.error("Reminder creation failed: %s", exc)
        return {"success": False, "created": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# NEW: get_mapbox_route — proxy Mapbox Directions API
# ---------------------------------------------------------------------------

async def _get_mapbox_route(
    origin_lng: float,
    origin_lat: float,
    dest_lng: float,
    dest_lat: float,
    profile: str = "driving",
) -> dict:
    """Proxy Mapbox Directions API and return a human-friendly summary.

    Returns step-by-step directions, total distance, and estimated travel time.
    """
    logger.info(
        "get_mapbox_route: (%s,%s)->(%s,%s) profile=%s",
        origin_lat, origin_lng, dest_lat, dest_lng, profile,
    )

    if not MAPBOX_TOKEN:
        return {
            "error": "Mapbox token not configured.",
            "fallback": (
                f"Straight-line distance: ~{_haversine(origin_lat, origin_lng, dest_lat, dest_lng):.1f} km. "
                "Configure VITE_MAPBOX_TOKEN for turn-by-turn directions."
            ),
        }

    # Validate profile
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
        logger.error("Mapbox API error: %s", exc.response.text[:300])
        return {"error": f"Mapbox API error: HTTP {exc.response.status_code}"}
    except Exception as exc:
        logger.error("Mapbox request failed: %s", exc)
        return {"error": f"Mapbox request failed: {exc}"}

    routes = data.get("routes", [])
    if not routes:
        return {"error": "No route found between these locations."}

    route = routes[0]
    duration_sec = route.get("duration", 0)
    distance_m = route.get("distance", 0)
    # Geometry as GeoJSON LineString for client-side rendering on a map
    geometry = route.get("geometry")

    # Build step-by-step directions
    steps = []
    legs = route.get("legs", [])
    for leg in legs:
        for step in leg.get("steps", []):
            maneuver = step.get("maneuver", {})
            instruction = maneuver.get("instruction", "")
            step_dist = step.get("distance", 0)
            step_dur = step.get("duration", 0)
            if instruction:
                steps.append({
                    "instruction": instruction,
                    "distance_m": round(step_dist),
                    "duration_sec": round(step_dur),
                })

    # Human-friendly summary
    dist_km = distance_m / 1000
    if duration_sec < 60:
        time_str = f"{int(duration_sec)} seconds"
    elif duration_sec < 3600:
        time_str = f"{int(duration_sec // 60)} minutes"
    else:
        hours = int(duration_sec // 3600)
        mins = int((duration_sec % 3600) // 60)
        time_str = f"{hours}h {mins}min"

    summary = (
        f"Route by {profile}: {dist_km:.1f} km, approximately {time_str}. "
        f"{len(steps)} navigation step(s)."
    )

    return {
        "profile": profile,
        "distance_km": round(dist_km, 2),
        "duration_minutes": round(duration_sec / 60, 1),
        "duration_text": time_str,
        "steps": steps[:20],  # cap to avoid huge payloads
        "summary": summary,
        # Endpoints + geometry so the client can draw the route on a map
        "origin": {"lat": origin_lat, "lng": origin_lng},
        "destination": {"lat": dest_lat, "lng": dest_lng},
        "geometry": geometry,
    }


# ---------------------------------------------------------------------------
# NEW: query_distribution_centers — community events + locations
# ---------------------------------------------------------------------------

async def _query_distribution_centers(
    days_ahead: int = 14,
    status: str = "scheduled",
    max_results: int = 10,
) -> dict:
    """Query upcoming distribution events from the distribution_events table.

    Returns event details: title, location, hours, capacity/availability.
    """
    from backend.ai_engine import supabase_get

    logger.info(
        "query_distribution_centers: days=%d status=%s max=%d",
        days_ahead, status, max_results,
    )

    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")
    future_str = (now + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    try:
        rows = await supabase_get("distribution_events", {
            "event_date": f"gte.{today_str}",
            # Apply upper-bound so days_ahead is actually respected.
            # Without this, future_str was computed but never used and
            # events months away would leak into results whenever there
            # were fewer than max_results events in the requested window.
            "and": f"(event_date.lte.{future_str})",
            "status": f"eq.{status}",
            "select": (
                "id,title,description,location,event_date,"
                "start_time,end_time,capacity,registered_count,status"
            ),
            "order": "event_date.asc",
            "limit": str(max_results),
        })
    except Exception as exc:
        logger.error("Distribution events query failed: %s", exc)
        return {"centers": [], "total": 0, "error": str(exc)}

    centers = []
    for ev in rows:
        capacity = ev.get("capacity") or 0
        registered = ev.get("registered_count") or 0
        spots_left = max(capacity - registered, 0)

        hours_str = ""
        if ev.get("start_time") and ev.get("end_time"):
            hours_str = f"{ev['start_time']} - {ev['end_time']}"
        elif ev.get("start_time"):
            hours_str = f"Starts at {ev['start_time']}"

        centers.append({
            "event_id": ev.get("id"),
            "title": ev.get("title"),
            "description": (ev.get("description") or "")[:300],
            "location": ev.get("location"),
            "date": ev.get("event_date"),
            "hours": hours_str,
            "capacity": capacity,
            "registered": registered,
            "spots_available": spots_left,
            "status": ev.get("status"),
        })

    # Natural summary
    if centers:
        parts = []
        for i, c in enumerate(centers, 1):
            spots_info = (
                f"{c['spots_available']} spots left"
                if c["capacity"] > 0
                else "open capacity"
            )
            parts.append(
                f"{i}. **{c['title']}** — {c['date']}, {c['hours']}. "
                f"Location: {c['location'] or 'TBA'}. {spots_info}."
            )
        summary = (
            f"Found {len(centers)} upcoming distribution event(s):\n"
            + "\n".join(parts)
        )
    else:
        summary = (
            f"No {status} distribution events found in the next {days_ahead} days. "
            "Check back soon or contact your community organizer!"
        )

    return {
        "centers": centers,
        "total": len(centers),
        "days_searched": days_ahead,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# get_user_dashboard — comprehensive dashboard for personalization
# ---------------------------------------------------------------------------

async def _get_user_dashboard(user_id: str) -> dict:
    """Return a rich user dashboard: profile, active listings,
    pending claims, upcoming reminders, and impact stats.
    All independent queries run in parallel for speed."""
    from backend.ai_engine import supabase_get
    import asyncio

    logger.info("get_user_dashboard: user=%s", user_id)
    now_iso = datetime.now(timezone.utc).isoformat()

    # Fire ALL independent queries in parallel
    async def _safe(coro):
        try:
            return await coro
        except Exception as e:
            logger.error("Dashboard query failed: %s", e)
            return []

    profile_q = _safe(supabase_get("users", {
        "id": f"eq.{user_id}",
        # Note: users.role is the Supabase auth role ("authenticated") — never
        # expose it to the AI. Only community_role is the meaningful user role.
        "select": "id,name,email,phone,address,is_admin,community_role,organization,created_at",
    }))
    listings_q = _safe(supabase_get("food_listings", {
        "user_id": f"eq.{user_id}",
        "status": "in.(approved,active,pending)",
        "select": "id,title,category,quantity,status,expiry_date,pickup_by,created_at",
        "order": "created_at.desc",
        "limit": "5",
    }))
    claims_q = _safe(supabase_get("food_claims", {
        "claimer_id": f"eq.{user_id}",
        "status": "in.(pending,approved)",
        "select": "id,food_id,status,pickup_date",
        "order": "created_at.desc",
        "limit": "5",
    }))
    reminders_q = _safe(supabase_get("ai_reminders", {
        "user_id": f"eq.{user_id}",
        "sent": "eq.false",
        "trigger_time": f"gte.{now_iso}",
        "select": "id,message,trigger_time,reminder_type",
        "order": "trigger_time.asc",
        "limit": "5",
    }))
    shared_q = _safe(supabase_get("food_listings", {
        "user_id": f"eq.{user_id}",
        "status": "in.(completed,claimed)",
        "select": "id",
    }))
    received_q = _safe(supabase_get("food_claims", {
        "claimer_id": f"eq.{user_id}",
        "status": "eq.approved",
        "select": "id",
    }))

    (profile_rows, listings, claims, reminders,
     completed_listings, completed_claims) = await asyncio.gather(
        profile_q, listings_q, claims_q, reminders_q, shared_q, received_q
    )

    # Build dashboard from parallel results
    dashboard: dict = {"user_id": user_id}

    # Profile
    if profile_rows:
        p = profile_rows[0]
        dashboard["profile"] = {
            "name": p.get("name") or p.get("email", ""),
            "email": p.get("email"),
            "phone": p.get("phone"),
            # community_role is the user-facing role (donor/recipient/volunteer).
            # users.role is the Supabase auth role ("authenticated") — it is NOT
            # selected and should never be passed to the AI.
            "role": p.get("community_role") or "member",
            "organization": p.get("organization"),
            "is_admin": p.get("is_admin", False),
            "member_since": p.get("created_at"),
            # address is the plain-text column; location is a legacy JSON column
            # — never pass it raw (it's a dict, not a string).
            "address": p.get("address") or None,
        }

    # Active listings
    dashboard["active_listings"] = [
        {"title": l.get("title"), "category": l.get("category"),
         "quantity": l.get("quantity"), "status": l.get("status")}
        for l in listings
        if _listing_is_fresh_enough(l)
    ]

    # Pending claims — batch fetch food titles
    if claims:
        food_ids = [c["food_id"] for c in claims if c.get("food_id")]
        food_map = {}
        if food_ids:
            ids_csv = ",".join(food_ids)
            food_rows = await _safe(supabase_get("food_listings", {
                "id": f"in.({ids_csv})",
                "select": "id,title",
            }))
            food_map = {r["id"]: r.get("title", "Food item") for r in food_rows}
        dashboard["pending_claims"] = [
            {"food_title": food_map.get(c.get("food_id"), "Food item"),
             "status": c.get("status"), "pickup_date": c.get("pickup_date")}
            for c in claims
        ]
    else:
        dashboard["pending_claims"] = []

    # Reminders
    dashboard["upcoming_reminders"] = [
        {"message": r.get("message"), "trigger_time": r.get("trigger_time"),
         "type": r.get("reminder_type")}
        for r in reminders
    ]

    # Impact
    dashboard["impact_summary"] = {
        "food_shared_count": len(completed_listings),
        "food_received_count": len(completed_claims),
        "total_contributions": len(completed_listings) + len(completed_claims),
    }

    return dashboard


# ---------------------------------------------------------------------------
# check_pickup_schedule — reads ai_reminders + food_claims
# ---------------------------------------------------------------------------

async def _check_pickup_schedule(
    user_id: str,
    include_sent: bool = False,
    days_ahead: int = 14,
) -> dict:
    """Check user's reminders table and pending pickups, organized by type."""
    from backend.ai_engine import supabase_get

    logger.info(
        "check_pickup_schedule: user=%s include_sent=%s days=%d",
        user_id, include_sent, days_ahead,
    )

    now = datetime.now(timezone.utc)
    future = now + timedelta(days=days_ahead)
    now_iso = now.isoformat()
    future_iso = future.isoformat()

    # --- Reminders from ai_reminders table ---
    reminder_params: dict = {
        "user_id": f"eq.{user_id}",
        # Lower bound (gte now) keeps past-due unsent reminders out of the
        # "upcoming" set. Without it, any reminder whose trigger_time already
        # passed but was never sent (e.g. background worker lag) would be
        # returned and the AI would describe it as an "upcoming" reminder.
        "and": f"(trigger_time.gte.{now_iso},trigger_time.lte.{future_iso})",
        "select": "id,message,trigger_time,reminder_type,sent,sent_at,related_id,created_at",
        "order": "trigger_time.asc",
        "limit": "50",
    }
    if not include_sent:
        reminder_params["sent"] = "eq.false"

    reminders_by_type: dict[str, list] = {
        "pickup": [],
        "listing_expiry": [],
        "distribution_event": [],
        "general": [],
    }

    try:
        reminders = await supabase_get("ai_reminders", reminder_params)
        for r in reminders:
            rtype = r.get("reminder_type", "general")
            if rtype not in reminders_by_type:
                rtype = "general"
            reminders_by_type[rtype].append({
                "id": r.get("id"),
                "message": r.get("message"),
                "trigger_time": r.get("trigger_time"),
                "sent": r.get("sent", False),
                "sent_at": r.get("sent_at"),
                "related_id": r.get("related_id"),
            })
    except Exception as exc:
        logger.error("Reminders fetch failed: %s", exc)

    # --- Pending pickups from food_claims ---
    pickups = []
    try:
        claims = await supabase_get("food_claims", {
            "claimer_id": f"eq.{user_id}",
            "status": "in.(pending,approved)",
            "select": "id,food_id,status,pickup_date,pickup_time,pickup_place,created_at",
            "order": "pickup_date.asc",
            "limit": "20",
        })
        for claim in claims:
            food_info = {"title": "Food item", "address": ""}
            try:
                food_rows = await supabase_get("food_listings", {
                    "id": f"eq.{claim['food_id']}",
                    "select": "title,full_address,location,pickup_by,expiry_date",
                })
                if food_rows:
                    f = food_rows[0]
                    food_info = {
                        "title": f.get("title", "Food item"),
                        "address": f.get("full_address") or _extract_location_text(f.get("location")),
                        "pickup_by": f.get("pickup_by"),
                        "expiry_date": f.get("expiry_date"),
                    }
            except Exception:
                pass

            pickups.append({
                "claim_id": claim.get("id"),
                "food_title": food_info.get("title"),
                "status": claim.get("status"),
                "pickup_date": claim.get("pickup_date"),
                "pickup_time": claim.get("pickup_time"),
                "pickup_by": food_info.get("pickup_by"),
                "address": food_info.get("address") or claim.get("pickup_place", ""),
                "expiry_date": food_info.get("expiry_date"),
            })
    except Exception as exc:
        logger.error("Pickup claims fetch failed: %s", exc)

    # --- Summary ---
    total_pending = sum(len(v) for v in reminders_by_type.values())
    summary_parts = []
    if pickups:
        summary_parts.append(f"{len(pickups)} pending food pickup(s)")
    if reminders_by_type["pickup"]:
        summary_parts.append(f"{len(reminders_by_type['pickup'])} pickup reminder(s)")
    if reminders_by_type["distribution_event"]:
        summary_parts.append(
            f"{len(reminders_by_type['distribution_event'])} event reminder(s)"
        )
    if reminders_by_type["listing_expiry"]:
        summary_parts.append(
            f"{len(reminders_by_type['listing_expiry'])} listing expiry alert(s)"
        )
    if reminders_by_type["general"]:
        summary_parts.append(
            f"{len(reminders_by_type['general'])} general reminder(s)"
        )

    if summary_parts:
        summary = "Your upcoming schedule: " + ", ".join(summary_parts) + "."
    else:
        summary = "You have no pending pickups or reminders right now."

    return {
        "pickups": pickups,
        "reminders": reminders_by_type,
        "total_reminders": total_pending,
        "total_pickups": len(pickups),
        "days_ahead": days_ahead,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# get_recipes — suggest recipes from ingredients or user's claimed food
# ---------------------------------------------------------------------------

async def _get_recipes(
    ingredients: list[str] | None = None,
    user_id: str | None = None,
    dietary_preferences: str | None = None,
) -> dict:
    """Generate recipe suggestions based on ingredients or a user's food claims."""
    from backend.ai_engine import supabase_get, legacy_ai_request, _extract_content, DEFAULT_MODEL

    logger.info("get_recipes: ingredients=%s user_id=%s", ingredients, user_id)

    # If user_id provided, look up their claimed food items
    if not ingredients and user_id:
        ingredients = []
        try:
            claims = await supabase_get("food_claims", {
                "claimer_id": f"eq.{user_id}",
                "status": "in.(pending,approved)",
                "select": "food_id",
                "limit": "20",
            })
            food_ids = [c["food_id"] for c in claims if c.get("food_id")]
            for fid in food_ids[:10]:
                try:
                    rows = await supabase_get("food_listings", {
                        "id": f"eq.{fid}",
                        "select": "title,category",
                    })
                    if rows:
                        ingredients.append(rows[0].get("title", ""))
                except Exception:
                    pass
        except Exception as exc:
            logger.error("Failed to fetch user claims for recipes: %s", exc)

    diet_note = ""
    if dietary_preferences:
        diet_note = f" The recipes must be {dietary_preferences}."

    if not ingredients:
        # No specific ingredients — suggest general easy recipes with common items
        prompt = (
            "Suggest 3 easy, budget-friendly recipes using common pantry staples "
            "that someone who is hungry could make quickly.{diet_note} "
            "Focus on simple ingredients like rice, beans, pasta, eggs, bread, "
            "canned vegetables, potatoes, or oatmeal. "
            "For each recipe provide: name, ingredients list with quantities, "
            "step-by-step instructions, prep time, cook time, and servings. "
            "Return valid JSON array."
        ).format(diet_note=diet_note)
        payload = {
            "model": DEFAULT_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a helpful culinary assistant for a food-sharing community. Help people who are hungry find easy meals they can make.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.8,
            "max_tokens": 1500,
        }
        try:
            data = await legacy_ai_request("/chat/completions", payload)
            return {
                "recipes": _extract_content(data),
                "ingredients_used": ["common pantry staples"],
                "dietary_preferences": dietary_preferences,
                "note": "These are general recipes using common ingredients. Tell me what you have on hand for more personalized suggestions!",
            }
        except Exception as exc:
            logger.error("get_recipes general AI call failed: %s", exc)
            return {"error": f"Failed to generate recipes: {str(exc)}"}

    prompt = (
        "Suggest 3 creative recipes using some or all of these ingredients: "
        f"{', '.join(ingredients)}.{diet_note} "
        "For each recipe provide: name, ingredients list with quantities, "
        "step-by-step instructions, prep time, cook time, and servings. "
        "Return valid JSON array."
    )
    payload = {
        "model": DEFAULT_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "You are a helpful culinary assistant for a food-sharing community.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.8,
        "max_tokens": 1500,
    }

    try:
        data = await legacy_ai_request("/chat/completions", payload)
        return {
            "recipes": _extract_content(data),
            "ingredients_used": ingredients,
            "dietary_preferences": dietary_preferences,
        }
    except Exception as exc:
        logger.error("get_recipes AI call failed: %s", exc)
        return {"error": f"Failed to generate recipes: {str(exc)}"}


# ---------------------------------------------------------------------------
# get_storage_tips — food storage & preservation advice
# ---------------------------------------------------------------------------

async def _get_storage_tips(
    food_items: list[str] | None = None,
    user_id: str | None = None,
) -> dict:
    """Generate storage tips for specific food items or a user's claimed food."""
    from backend.ai_engine import supabase_get, legacy_ai_request, _extract_content, DEFAULT_MODEL

    logger.info("get_storage_tips: food_items=%s user_id=%s", food_items, user_id)

    # If user_id provided, look up their claimed/listed food
    if not food_items and user_id:
        food_items = []
        try:
            claims = await supabase_get("food_claims", {
                "claimer_id": f"eq.{user_id}",
                "status": "in.(pending,approved)",
                "select": "food_id",
                "limit": "20",
            })
            food_ids = [c["food_id"] for c in claims if c.get("food_id")]
            for fid in food_ids[:10]:
                try:
                    rows = await supabase_get("food_listings", {
                        "id": f"eq.{fid}",
                        "select": "title",
                    })
                    if rows:
                        food_items.append(rows[0].get("title", ""))
                except Exception:
                    pass
        except Exception as exc:
            logger.error("Failed to fetch user claims for storage tips: %s", exc)

    if not food_items:
        return {"error": "No food items provided and no claimed food found for user."}

    prompt = (
        f"Provide storage tips for these food items: {', '.join(food_items)}. "
        "For each item include: optimal temperature, container type, "
        "shelf life (fridge/freezer/pantry), signs of spoilage, "
        "and tips to extend freshness. Return valid JSON."
    )
    payload = {
        "model": DEFAULT_MODEL,
        "messages": [
            {"role": "system", "content": "You are a food preservation expert."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.5,
        "max_tokens": 1500,
    }

    try:
        data = await legacy_ai_request("/chat/completions", payload)
        return {
            "tips": _extract_content(data),
            "food_items": food_items,
        }
    except Exception as exc:
        logger.error("get_storage_tips AI call failed: %s", exc)
        return {"error": f"Failed to generate storage tips: {str(exc)}"}


# ---------------------------------------------------------------------------
# get_active_communities — local food sharing groups
# ---------------------------------------------------------------------------

async def _get_active_communities(
    user_id: str | None = None,
    max_results: int = 10,
) -> dict:
    """Fetch active food sharing communities, optionally sorted by proximity."""
    from backend.ai_engine import supabase_get

    logger.info("get_active_communities: user_id=%s max=%d", user_id, max_results)

    # Fetch all active communities
    try:
        communities = await supabase_get("communities", {
            "is_active": "eq.true",
            "select": (
                "id,name,location,contact,hours,phone,description,"
                "latitude,longitude,food_given_lb,families_helped,"
                "school_staff_helped,image"
            ),
            "limit": "50",
        })
    except Exception as exc:
        logger.error("Failed to fetch communities: %s", exc)
        return {"error": f"Could not fetch communities: {str(exc)}"}

    if not communities:
        return {"communities": [], "total": 0, "summary": "No active communities found."}

    # If user_id provided, get their location and sort by distance.
    # Prefer the geocoded latitude/longitude columns (set when user saves
    # their address). Fall back to the legacy location JSON column for
    # older rows that pre-date geocoding.
    user_lat = user_lng = None
    if user_id:
        try:
            rows = await supabase_get("users", {
                "id": f"eq.{user_id}",
                "select": "latitude,longitude,location",
            })
            if rows:
                profile = rows[0]
                # 1. New canonical columns (numeric — PostgREST may return strings)
                raw_lat = profile.get("latitude")
                raw_lng = profile.get("longitude")
                if raw_lat is not None and raw_lng is not None:
                    try:
                        user_lat = float(raw_lat)
                        user_lng = float(raw_lng)
                    except (TypeError, ValueError):
                        pass
                # 2. Legacy JSON column fallback (older profiles)
                if user_lat is None or user_lng is None:
                    loc = profile.get("location")
                    if isinstance(loc, str):
                        import json as _json
                        try:
                            loc = _json.loads(loc)
                        except (ValueError, TypeError):
                            loc = None
                    if isinstance(loc, dict):
                        lat_val = loc.get("latitude") or loc.get("lat")
                        lng_val = loc.get("longitude") or loc.get("lng") or loc.get("lon")
                        if lat_val and lng_val:
                            try:
                                user_lat = float(lat_val)
                                user_lng = float(lng_val)
                            except (TypeError, ValueError):
                                pass
        except Exception as exc:
            logger.warning("Could not get user location: %s", exc)

    results = []
    for c in communities:
        entry = {
            "name": c.get("name", ""),
            "address": c.get("location", ""),
            "contact": c.get("contact", ""),
            "phone": c.get("phone", ""),
            "hours": c.get("hours", ""),
            "description": c.get("description", ""),
            "impact": {
                "food_given_lb": c.get("food_given_lb", 0),
                "families_helped": c.get("families_helped", 0),
                "school_staff_helped": c.get("school_staff_helped", 0),
            },
        }

        c_lat = c.get("latitude")
        c_lng = c.get("longitude")
        if user_lat and user_lng and c_lat and c_lng:
            dist = _haversine(user_lat, user_lng, float(c_lat), float(c_lng))
            entry["distance_km"] = round(dist, 1)
            entry["distance_miles"] = round(dist * 0.621371, 1)

        results.append(entry)

    # Sort by distance if available, otherwise by name
    if user_lat:
        results.sort(key=lambda x: x.get("distance_km", 9999))
    else:
        results.sort(key=lambda x: x["name"])

    results = results[:max_results]

    # Build summary
    total_food = sum(r["impact"]["food_given_lb"] for r in results)
    total_families = sum(r["impact"]["families_helped"] for r in results)
    summary = (
        f"Found {len(results)} active food sharing communit{'y' if len(results) == 1 else 'ies'} "
        f"that have collectively distributed {total_food:,} lbs of food "
        f"and helped {total_families:,} families."
    )

    return {
        "communities": results,
        "total": len(results),
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# get_user_notifications
# ---------------------------------------------------------------------------

async def _get_user_notifications(
    user_id: str,
    unread_only: bool = False,
    notification_type: str | None = None,
    limit: int = 20,
) -> dict:
    """Fetch a user's notifications with optional filters."""
    from backend.ai_engine import supabase_get

    logger.info(
        "get_user_notifications: user=%s unread_only=%s type=%s",
        user_id, unread_only, notification_type,
    )

    params: dict = {
        "user_id": f"eq.{user_id}",
        "select": "id,title,message,type,read,data,created_at",
        "order": "created_at.desc",
        "limit": str(min(limit, 50)),
    }
    if unread_only:
        params["read"] = "eq.false"
    if notification_type:
        params["type"] = f"eq.{notification_type}"

    try:
        rows = await supabase_get("notifications", params)
    except Exception as exc:
        logger.error("Failed to fetch notifications: %s", exc)
        return {"error": f"Could not fetch notifications: {str(exc)}"}

    if not rows:
        return {
            "notifications": [],
            "total": 0,
            "unread_count": 0,
            "summary": "You have no notifications.",
        }

    unread = sum(1 for r in rows if not r.get("read"))

    summary_parts = [f"You have {len(rows)} notification{'s' if len(rows) != 1 else ''}"]
    if unread:
        summary_parts.append(f"{unread} unread")
    summary = ", ".join(summary_parts) + "."

    return {
        "notifications": rows,
        "total": len(rows),
        "unread_count": unread,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# send_notification
# ---------------------------------------------------------------------------

async def _send_notification(
    user_id: str,
    title: str,
    message: str,
    notification_type: str = "system",
    data: dict | None = None,
) -> dict:
    """Create a notification for a user."""
    import httpx
    from backend.ai_engine import SUPABASE_URL, SUPABASE_SERVICE_KEY

    logger.info("send_notification: user=%s title=%s type=%s", user_id, title, notification_type)

    allowed_types = {
        "system", "food_claimed", "trade_request",
        "claim_approved", "claim_declined", "submission_declined", "alert",
    }
    if notification_type not in allowed_types:
        notification_type = "system"

    payload = {
        "user_id": user_id,
        "title": title,
        "message": message,
        "type": notification_type,
        "read": False,
        "data": data or {},
    }

    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation,resolution=ignore-duplicates",
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{SUPABASE_URL}/rest/v1/notifications",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            result = resp.json()
    except Exception as exc:
        logger.error("Failed to send notification: %s", exc)
        return {"error": f"Could not send notification: {str(exc)}"}

    row = result[0] if isinstance(result, list) and result else result
    return {
        "success": True,
        "notification_id": row.get("id") if isinstance(row, dict) else None,
        "summary": f"Notification '{title}' sent successfully.",
    }


# ---------------------------------------------------------------------------
# mark_notifications_read
# ---------------------------------------------------------------------------

async def _mark_notifications_read(
    user_id: str,
    notification_id: str | None = None,
) -> dict:
    """Mark notification(s) as read via Supabase REST PATCH."""
    import httpx
    from backend.ai_engine import SUPABASE_URL, SUPABASE_SERVICE_KEY

    logger.info(
        "mark_notifications_read: user=%s notif_id=%s",
        user_id, notification_id,
    )

    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

    base = f"{SUPABASE_URL}/rest/v1/notifications"
    params = {"user_id": f"eq.{user_id}", "read": "eq.false"}
    if notification_id:
        params["id"] = f"eq.{notification_id}"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.patch(
                base, headers=headers, params=params, json={"read": True}
            )
            resp.raise_for_status()
            updated = resp.json()
    except Exception as exc:
        logger.error("Failed to mark notifications read: %s", exc)
        return {"error": f"Could not update notifications: {str(exc)}"}

    count = len(updated) if isinstance(updated, list) else 0
    if notification_id:
        summary = "Notification marked as read." if count else "Notification not found or already read."
    else:
        summary = f"Marked {count} notification{'s' if count != 1 else ''} as read."

    return {"success": True, "updated_count": count, "summary": summary}


# ---------------------------------------------------------------------------
# create_food_listing — conversational donation post
# ---------------------------------------------------------------------------

_LISTING_CATEGORIES = {
    "produce", "bakery", "dairy", "pantry", "meat",
    "seafood", "frozen", "snacks", "beverages", "prepared", "other",
}


MAPBOX_GEOCODE_URL = "https://api.mapbox.com/geocoding/v5/mapbox.places"


async def _forward_geocode(address: str) -> Optional[tuple[float, float]]:
    """Return (lat, lng) for an address string via Mapbox, or None on failure."""
    if not address or not MAPBOX_TOKEN:
        return None
    from urllib.parse import quote
    try:
        url = f"{MAPBOX_GEOCODE_URL}/{quote(address.strip(), safe='')}.json"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params={"access_token": MAPBOX_TOKEN, "limit": "1"})
        if resp.status_code != 200:
            logger.warning("Mapbox geocode HTTP %s for %r", resp.status_code, address[:80])
            return None
        features = resp.json().get("features") or []
        if not features:
            return None
        center = features[0].get("center") or []
        if len(center) < 2:
            return None
        # Mapbox returns [lng, lat]
        return float(center[1]), float(center[0])
    except Exception as exc:
        logger.warning("Mapbox geocode failed for %r: %s", address[:80], exc)
        return None


async def _resolve_community(community_name: Optional[str], community_id: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Resolve a community name or id to (id, name). Returns (None, None) on miss."""
    from backend.ai_engine import supabase_get

    if community_id:
        try:
            rows = await supabase_get("communities", {
                "id": f"eq.{community_id}",
                "is_active": "eq.true",
                "select": "id,name",
                "limit": "1",
            })
            if rows:
                return str(rows[0]["id"]), rows[0].get("name")
        except Exception as exc:
            logger.warning("community lookup by id failed: %s", exc)

    name = (community_name or "").strip()
    if not name:
        return None, None
    try:
        # Try exact match first (case-insensitive via ilike).
        # Only match active communities so inactive ones can't be silently
        # assigned to new listings (frontend RLS would hide them anyway).
        rows = await supabase_get("communities", {
            "name": f"ilike.{name}",
            "is_active": "eq.true",
            "select": "id,name",
            "limit": "1",
        })
        if not rows:
            # Fall back to fuzzy contains match using % as the ILIKE wildcard.
            # httpx URL-encodes % → %25; PostgREST URL-decodes it back to %
            # before passing to PostgreSQL, so ILIKE '%name%' works correctly.
            rows = await supabase_get("communities", {
                "name": f"ilike.%{name}%",
                "is_active": "eq.true",
                "select": "id,name",
                "limit": "1",
            })
        if rows:
            return str(rows[0]["id"]), rows[0].get("name")
    except Exception as exc:
        logger.warning("community lookup by name failed: %s", exc)
    return None, None


async def _create_food_listing(
    user_id: str,
    title: str,
    quantity: float,
    unit: str,
    category: str,
    description: Optional[str] = None,
    expiry_date: Optional[str] = None,
    expiration_date: Optional[str] = None,
    best_before: Optional[str] = None,
    location: Optional[str] = None,
    dietary_tags: Optional[list] = None,
    allergens: Optional[list] = None,
    community_name: Optional[str] = None,
    community_id: Optional[str] = None,
    community_confirmed: bool = False,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    image_url: Optional[str] = None,
    **_ignored,
) -> dict:
    """Insert a single food donation listing for the authenticated user."""
    from backend.ai_engine import (
        supabase_post,
        fetch_donor_listing_defaults,
        apply_donor_defaults_to_listing,
    )

    logger.info("create_food_listing: user=%s title=%s qty=%s", user_id, title, quantity)
    if not user_id:
        return {"success": False, "error": "missing user_id"}

    title_s = (title or "").strip()
    if not title_s:
        return {"success": False, "error": "title is required"}
    unit_s = (unit or "items").strip()[:40] or "items"

    try:
        qty = float(quantity)
        if qty <= 0:
            return {"success": False, "error": "quantity must be greater than 0"}
    except (TypeError, ValueError):
        return {"success": False, "error": "quantity must be a number"}

    cat = str(category or "").strip().lower()
    if cat not in _LISTING_CATEGORIES:
        cat = "other"

    donor = await fetch_donor_listing_defaults(str(user_id))

    if not community_confirmed:
        suggested_id, suggested_name = (None, None)
        if donor.get("community_id"):
            suggested_id, suggested_name = await _resolve_community(None, str(donor["community_id"]))
        return {
            "success": False,
            "error": "community_not_confirmed",
            "message": (
                "Ask the donor which community/school this donation is for and get "
                "explicit confirmation before posting. Mention their profile community "
                "if they have one, then call post_food_listing with community_name "
                "(or community_id) and community_confirmed=true."
            ),
            "suggested_community_name": suggested_name,
            "suggested_community_id": suggested_id,
        }

    resolved_community_id, resolved_community_name = await _resolve_community(
        community_name, community_id
    )
    if not resolved_community_id:
        suggested_id, suggested_name = (None, None)
        if donor.get("community_id"):
            suggested_id, suggested_name = await _resolve_community(None, str(donor["community_id"]))
        return {
            "success": False,
            "error": "community_required",
            "message": (
                "Could not resolve the community. Ask the donor to pick one "
                "(call get_active_communities if needed), confirm their choice, "
                "then pass community_name with community_confirmed=true."
            ),
            "suggested_community_name": suggested_name,
            "suggested_community_id": suggested_id,
        }

    row: dict = {
        "user_id": str(user_id),
        "title": title_s[:200],
        "quantity": qty,
        "unit": unit_s,
        "category": cat,
        "listing_type": "donation",
        "status": "approved",
    }
    if description:
        row["description"] = str(description).strip()[:2000]

    resolved_expiry = _normalize_expiry_date(expiry_date, expiration_date, best_before)
    if not resolved_expiry:
        return {
            "success": False,
            "error": "expiry_date_required",
            "message": (
                "Ask the donor when the food expires or was made (best-by date). "
                "Map their answer to expiry_date as YYYY-MM-DD before calling "
                "post_food_listing. Examples: made today → today's date; "
                "good for 24h → tomorrow; bakery → 2 days out."
            ),
            "suggested_expiry_date": _suggested_expiry_for_category(cat),
        }
    row["expiry_date"] = resolved_expiry

    if location:
        loc_s = str(location).strip()[:200]
        row["location"] = loc_s
        # full_address powers the address line on search cards + the map pin
        # popover. Keep it in sync with location so AI-posted listings render
        # the same as form-posted ones.
        row["full_address"] = loc_s
    if isinstance(dietary_tags, list):
        row["dietary_tags"] = [str(t).strip()[:40] for t in dietary_tags if str(t).strip()][:20]
    if isinstance(allergens, list):
        row["allergens"] = [str(t).strip()[:40] for t in allergens if str(t).strip()][:20]
    if image_url and isinstance(image_url, str) and image_url.strip().startswith(("http://", "https://")):
        row["image_url"] = image_url.strip()[:2000]

    # Explicit coords from the model win over donor profile defaults.
    try:
        if latitude is not None and longitude is not None:
            row["latitude"] = float(latitude)
            row["longitude"] = float(longitude)
    except (TypeError, ValueError):
        pass

    # If the donor named an explicit pickup address (which may differ from
    # their saved profile address), geocode THAT address now — BEFORE donor
    # profile coordinate defaults are applied below. Otherwise a pickup at
    # "the library on 5th" would inherit the donor's home coordinates and
    # drop the map pin in the wrong place.
    if (row.get("latitude") is None or row.get("longitude") is None) and row.get("location"):
        coords = await _forward_geocode(row.get("full_address") or row.get("location"))
        if coords:
            row["latitude"], row["longitude"] = coords

    row["community_id"] = resolved_community_id

    row = apply_donor_defaults_to_listing(row, donor)
    # Never inherit community silently from profile — only the confirmed choice.
    row["community_id"] = resolved_community_id

    # Final fallback: still no coordinates (donor gave no explicit pickup
    # address, so we're relying on the donor's saved address filled in by
    # apply_donor_defaults_to_listing). Geocode that as a last resort.
    if row.get("latitude") is None or row.get("longitude") is None:
        addr_for_geocode = row.get("full_address") or row.get("location")
        if addr_for_geocode:
            coords = await _forward_geocode(addr_for_geocode)
            if coords:
                row["latitude"], row["longitude"] = coords

    try:
        result = await supabase_post("food_listings", row)
    except Exception as exc:
        logger.error("create_food_listing insert failed: %s", exc)
        return {"success": False, "error": f"Insert failed: {exc}"}

    listing_id = None
    if isinstance(result, list) and result:
        listing_id = result[0].get("id")
    if not listing_id:
        return {"success": False, "error": "No row returned from database"}

    on_map = row.get("latitude") is not None and row.get("longitude") is not None
    summary_bits = [
        f"Posted '{row['title']}' ({row['quantity']} {row['unit']}, {row['category']})"
    ]
    if row.get("full_address") or row.get("location"):
        summary_bits.append(f"at {row.get('full_address') or row.get('location')}")
    if resolved_community_name:
        summary_bits.append(f"in {resolved_community_name}")
    summary_bits.append("— live on the map." if on_map else "— note: no map coordinates yet, recipients can still see it in the feed.")

    return {
        "success": True,
        "listing_id": str(listing_id),
        "title": row["title"],
        "quantity": row["quantity"],
        "unit": row["unit"],
        "category": row["category"],
        "address": row.get("full_address") or row.get("location"),
        "latitude": row.get("latitude"),
        "longitude": row.get("longitude"),
        "community_id": row.get("community_id"),
        "community_name": resolved_community_name,
        "expiry_date": row.get("expiry_date"),
        "on_map": on_map,
        "summary": " ".join(summary_bits),
    }


# ---------------------------------------------------------------------------
# claim_food_listing — conversational claim flow
# ---------------------------------------------------------------------------


# Words the model might pass as `quantity` instead of a number when the user
# says "claim everything" / "all of it" / "todo". Tracked case-insensitively;
# any match means "claim every available unit on the listing".
_CLAIM_ALL_KEYWORDS = frozenset({
    "all", "everything", "every", "max", "maximum", "whole", "entire",
    "todo", "todos", "toda", "todas", "completo", "completa", "entero",
})


def _normalize_claim_quantity(
    raw_quantity: object, available_qty: int
) -> tuple[int, bool]:
    """Coerce a free-form ``quantity`` argument into a positive int.

    Returns ``(requested_qty, clamped)`` where ``clamped`` is True when the
    requested amount exceeded ``available_qty`` and was reduced to fit. The
    bare-handler ``int(quantity)`` lost real user intent in two cases:

    * "all" / "everything" / "todo" silently became 1 (caught by the
      ValueError branch). The user wanted to claim every available unit
      and instead got one — a "wrong number claimed" bug.
    * Strings like "5 loaves" or "two" silently became 1 for the same
      reason. We now extract a leading integer when present, and accept
      common all-quantity words.
    """
    if available_qty < 1:
        return (1, False)
    if raw_quantity is None:
        # Mutual-aid default: take the whole listing. Donors post surplus they
        # want gone, and claimers (a hungry family, a shelter) typically want
        # all of it. Defaulting to 1 produced the "claimed 1 egg of 6" bug
        # when the AI omitted quantity for vague affirmations like "yes please".
        return (available_qty, False)
    # Native ints / floats — keep the int part.
    if isinstance(raw_quantity, bool):  # bool is subclass of int — reject first
        return (1, False)
    if isinstance(raw_quantity, (int, float)):
        try:
            n = int(raw_quantity)
        except (TypeError, ValueError, OverflowError):
            return (1, False)
        if n < 1:
            return (1, False)
        if n > available_qty:
            return (available_qty, True)
        return (n, False)
    # String forms — handle "all" / "5" / "5 loaves" / "two".
    s = str(raw_quantity).strip().lower()
    if not s:
        return (1, False)
    if s in _CLAIM_ALL_KEYWORDS:
        return (available_qty, False)
    # Pull the first integer out of "5", "5 loaves", "qty: 3", etc.
    m = re.search(r"-?\d+", s)
    if m:
        try:
            n = int(m.group(0))
        except (TypeError, ValueError):
            n = 1
        if n < 1:
            return (1, False)
        if n > available_qty:
            return (available_qty, True)
        return (n, False)
    return (1, False)


async def _claim_food_listing(
    user_id: str,
    listing_id: str,
    quantity: Optional[int] = None,
    pickup_date: Optional[str] = None,
    people: Optional[int] = None,
    **_ignored,
) -> dict:
    """Create a food_claims row for the authenticated user and decrement the listing."""
    from backend.ai_engine import supabase_get, supabase_post, supabase_patch, supabase_delete

    logger.info(
        "claim_food_listing: user=%s listing=%s qty=%s",
        user_id, listing_id, quantity,
    )
    if not user_id:
        return {"success": False, "error": "missing user_id"}
    if not listing_id or not isinstance(listing_id, str):
        return {"success": False, "error": "missing listing_id"}

    # --- 1. Fetch the listing to verify it exists and is claimable ---
    try:
        listings = await supabase_get("food_listings", {
            "id": f"eq.{listing_id}",
            "select": "id,title,quantity,unit,status,user_id,listing_type,expiry_date,pickup_by,full_address,location",
            "limit": "1",
        })
    except Exception as exc:
        logger.error("claim_food_listing: listing fetch failed: %s", exc)
        return {"success": False, "error": f"Could not look up listing: {exc}"}

    if not listings:
        return {"success": False, "error": "Listing not found. Search for available food first."}
    listing = listings[0]

    # Only donations are claimable — requests are the opposite direction.
    if str(listing.get("listing_type") or "donation").lower() == "request":
        return {
            "success": False,
            "error": "That's a food request, not a donation — it can't be claimed.",
        }

    if str(listing.get("user_id") or "") == str(user_id):
        return {"success": False, "error": "You cannot claim your own listing."}

    status = str(listing.get("status") or "").lower()
    if status in {"claimed", "completed", "expired", "cancelled", "declined"}:
        return {
            "success": False,
            "error": (
                f"Sorry, this listing was just {status} by someone else. "
                f"Search again to see what's currently available."
            ),
        }
    if status not in {"", "active", "approved", "available"}:
        return {
            "success": False,
            "error": f"Listing is not available to claim yet (status: {status}).",
        }

    # Guard: reject claims on listings whose expiry_date or pickup_by has
    # already passed. The DB-level query filters prevent expired listings
    # from appearing in search, but a user can supply a listing_id directly
    # (e.g. from a bookmarked link or a stale AI context message) and bypass
    # that filter. Without this check they would claim food that may no
    # longer be safe to eat.
    _now = datetime.now(timezone.utc)
    _expiry_raw = listing.get("expiry_date")
    if _expiry_raw:
        _expiry_dt = _parse_dt(str(_expiry_raw))
        if _expiry_dt and _expiry_dt < _now:
            return {
                "success": False,
                "error": "This listing has expired and is no longer available for claiming.",
            }
        # ISO-date-only fallback (no time component)
        if not _expiry_dt:
            try:
                from datetime import date as _date
                _expiry_date = _date.fromisoformat(str(_expiry_raw)[:10])
                if _expiry_date < _now.date():
                    return {
                        "success": False,
                        "error": "This listing has expired and is no longer available for claiming.",
                    }
            except (ValueError, TypeError):
                pass
    _pickup_raw = listing.get("pickup_by")
    if _pickup_raw:
        _pickup_dt = _parse_dt(str(_pickup_raw))
        if _pickup_dt and _pickup_dt < _now:
            return {
                "success": False,
                "error": "The pickup deadline for this listing has passed.",
            }

    try:
        available_qty = float(listing.get("quantity") or 0)
    except (TypeError, ValueError):
        available_qty = 0
    if available_qty <= 0:
        return {
            "success": False, 
            "error": (
                "Sorry, this listing has no quantity left — someone claimed it all. "
                "Search again to see what else is available."
            ),
        }

    # --- 2. Normalize claim quantity (food_claims.quantity is INTEGER NOT NULL) ---
    # Tolerate "all" / "everything" / "5 loaves" instead of silently defaulting
    # to 1 when the model passes a non-numeric value. See _normalize_claim_quantity.
    requested_qty, quantity_clamped = _normalize_claim_quantity(
        quantity, int(available_qty) if available_qty >= 1 else 1
    )

    # --- 2b. Prevent duplicate claims on the same listing ---
    try:
        existing_claim = await supabase_get("food_claims", {
            "food_id": f"eq.{listing_id}",
            "claimer_id": f"eq.{user_id}",
            "status": "in.(pending,approved)",
            "select": "id",
            "limit": "1",
        })
        if existing_claim:
            return {
                "success": False,
                "error": "You already have an active claim on this listing. Use cancel_claim to release it first if you want to re-claim.",
            }
    except Exception as exc:
        logger.warning("claim_food_listing: duplicate claim check failed (non-fatal): %s", exc)

    # --- 3. Fetch the claimant profile for requester_* fields ---
    try:
        users = await supabase_get("users", {
            "id": f"eq.{user_id}",
            "select": "id,name,email,phone",
            "limit": "1",
        })
    except Exception as exc:
        logger.error("claim_food_listing: user fetch failed: %s", exc)
        users = []

    user_row = users[0] if users else {}
    requester_name = (
        str(user_row.get("name") or "").strip()
        or str(user_row.get("email") or "").strip()
        or "Anonymous"
    )[:200]

    # --- 3c. Find or create a receipt for this user (so the claim appears in Receipts & Activity) ---
    # pickup_by is intentionally NOT set here. The DB BEFORE INSERT trigger
    # (set_receipt_pickup_deadline → calculate_pickup_deadline) computes the
    # correct Friday 11:59 PM Pacific deadline automatically.
    # The old _next_friday_5pm_utc() helper was wrong: it used Friday 5 PM
    # (pre-migration deadline) and hardcoded PST -8h (incorrect during PDT,
    # Apr–Oct, when the offset should be -7h).
    receipt_id = None
    pickup_deadline_db: Optional[str] = None
    pickup_loc = listing.get("full_address") or _extract_location_text(listing.get("location")) or None
    try:
        existing_receipts = await supabase_get("receipts", {
            "user_id": f"eq.{user_id}",
            "status": "eq.pending",
            "select": "id,pickup_by",
            "order": "created_at.desc",
            "limit": "1",
        })
        if existing_receipts:
            receipt_id = existing_receipts[0].get("id")
            pickup_deadline_db = existing_receipts[0].get("pickup_by")
        else:
            receipt_row: dict = {
                "user_id": str(user_id),
                "status": "pending",
                # pickup_by omitted — DB trigger sets Friday 11:59 PM Pacific
            }
            if pickup_loc:
                receipt_row["pickup_location"] = str(pickup_loc)[:255]
                receipt_row["pickup_address"] = str(pickup_loc)[:500]
            receipt_result = await supabase_post("receipts", receipt_row)
            if isinstance(receipt_result, list) and receipt_result:
                receipt_id = receipt_result[0].get("id")
                pickup_deadline_db = receipt_result[0].get("pickup_by")
    except Exception as exc:
        logger.warning("claim_food_listing: receipt create/lookup failed (non-fatal): %s", exc)

    claim_row: dict = {
        "food_id": listing_id,
        "claimer_id": str(user_id),
        "requester_name": requester_name,
        "status": "approved",
        "quantity": requested_qty,
        "pickup_date": str(pickup_date).strip()[:40] if pickup_date else None,
    }
    if receipt_id:
        claim_row["receipt_id"] = str(receipt_id)
    if user_row.get("email"):
        claim_row["requester_email"] = str(user_row["email"])[:200]
    if user_row.get("phone"):
        claim_row["requester_phone"] = str(user_row["phone"])[:40]
    if not pickup_date:
        claim_row.pop("pickup_date", None)
    # `people` is an optional impact-tracking column that may not exist on all
    # Supabase deployments. Skip it to avoid 400 errors on the insert.
    # (The AI response text already conveys how many people will be fed.)

    # --- 4. Insert the claim ---
    try:
        result = await supabase_post("food_claims", claim_row)
    except Exception as exc:
        logger.error("claim_food_listing: insert failed: %s", exc)
        return {"success": False, "error": f"Could not create claim: {exc}"}

    claim_id = None
    if isinstance(result, list) and result:
        claim_id = result[0].get("id")
    if not claim_id:
        return {"success": False, "error": "Claim insert returned no row."}

    # --- 5. Atomically decrement the listing quantity (CAS prevents overselling) ---
    # The CAS filter `quantity=eq.{available_qty}` ensures the PATCH only
    # succeeds if no other request has already modified the row since we
    # read it in step 1. If two users simultaneously reach this point, only
    # one PATCH will match; the other gets an empty result → claim rollback.
    remaining = available_qty - requested_qty
    patch_body = {"status": "claimed"} if remaining <= 0 else {"quantity": remaining}
    try:
        patched_rows = await supabase_patch(
            "food_listings",
            {"id": f"eq.{listing_id}", "quantity": f"eq.{available_qty}"},
            patch_body,
        )
        if not isinstance(patched_rows, list) or len(patched_rows) == 0:
            # CAS failed: another request modified the listing quantity
            # between our read (step 1) and this write (step 5). Roll back
            # the claim row we just inserted to keep the DB consistent.
            try:
                await supabase_delete("food_claims", {"id": f"eq.{claim_id}"})
            except Exception as del_exc:
                logger.error(
                    "claim_food_listing: rollback delete failed for claim %s: %s",
                    claim_id, del_exc,
                )
            return {
                "success": False,
                "error": (
                    "The listing was updated by another request while your claim was being processed. "
                    "Please search again and claim from fresh results."
                ),
            }
    except Exception as exc:
        logger.warning("claim_food_listing: listing patch failed (non-fatal): %s", exc)

    title = str(listing.get("title") or "the listing")
    unit = str(listing.get("unit") or "")

    summary_parts = [f"Claimed {requested_qty} {unit}".rstrip(), f"of '{title}'"]
    summary = " ".join(p for p in summary_parts if p).strip() + "."
    if pickup_loc:
        summary += f" Pickup at {pickup_loc}."
    # When we had to clamp the request down to what was actually available,
    # tell the model explicitly. Without this hint GPT often echoes the
    # number the user asked for ("I claimed 5 loaves") instead of the
    # number we really created the claim with ("I claimed 3 loaves, that's
    # all that was left").
    if quantity_clamped:
        summary += f" Only {requested_qty} {unit or 'units'} were available."

    return {
        "success": True,
        "claim_id": str(claim_id),
        "receipt_id": str(receipt_id) if receipt_id else None,
        "listing_id": str(listing_id),
        "title": title,
        "quantity": requested_qty,
        "quantity_clamped": quantity_clamped,
        "unit": unit,
        "remaining_on_listing": max(remaining, 0),
        "pickup_location": pickup_loc,
        "pickup_deadline": pickup_deadline_db,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Shared helper: find the user's most relevant active claim
# ---------------------------------------------------------------------------


async def _find_user_claim(
    user_id: str,
    claim_id: Optional[str],
    listing_id: Optional[str],
) -> Optional[dict]:
    """Resolve a food_claims row for the user. Priority: claim_id > listing_id."""
    from backend.ai_engine import supabase_get

    select = "id,food_id,claimer_id,status,quantity,requester_name"
    if claim_id:
        rows = await supabase_get("food_claims", {
            "id": f"eq.{claim_id}",
            "claimer_id": f"eq.{user_id}",
            "select": select,
            "limit": "1",
        })
        return rows[0] if rows else None
    if listing_id:
        rows = await supabase_get("food_claims", {
            "food_id": f"eq.{listing_id}",
            "claimer_id": f"eq.{user_id}",
            "status": "in.(approved,pending)",
            "select": select,
            "order": "created_at.desc",
            "limit": "1",
        })
        return rows[0] if rows else None
    # Fall back to user's most recent active claim
    rows = await supabase_get("food_claims", {
        "claimer_id": f"eq.{user_id}",
        "status": "in.(approved,pending)",
        "select": select,
        "order": "created_at.desc",
        "limit": "1",
    })
    return rows[0] if rows else None


# ---------------------------------------------------------------------------
# cancel_claim — release a claim and restore the listing
# ---------------------------------------------------------------------------


async def _cancel_claim(
    user_id: str,
    claim_id: Optional[str] = None,
    listing_id: Optional[str] = None,
    **_ignored,
) -> dict:
    from backend.ai_engine import supabase_get, supabase_patch, supabase_delete

    logger.info("cancel_claim: user=%s claim=%s listing=%s", user_id, claim_id, listing_id)
    if not user_id:
        return {"success": False, "error": "missing user_id"}

    try:
        claim = await _find_user_claim(user_id, claim_id, listing_id)
    except Exception as exc:
        logger.error("cancel_claim: lookup failed: %s", exc)
        return {"success": False, "error": f"Could not look up your claim: {exc}"}

    if not claim:
        return {"success": False, "error": "No active claim found to cancel."}

    status = str(claim.get("status") or "").lower()
    if status in {"completed", "expired", "declined"}:
        # The claim_id from conversation history is stale. Try to find a live
        # active claim — first on the same food item, then any of this user's
        # active claims — rather than surfacing a confusing error to the user.
        stale_food_id = claim.get("food_id")
        try:
            fresh = await _find_user_claim(user_id, None, stale_food_id)
            if fresh and str(fresh.get("status") or "").lower() not in {"completed", "expired", "declined"}:
                claim = fresh
            else:
                fresh = await _find_user_claim(user_id, None, None)
                if fresh:
                    claim = fresh
                else:
                    return {"success": False, "error": f"Claim is already {status}, nothing to cancel."}
        except Exception as exc:
            logger.warning("cancel_claim: fallback lookup failed: %s", exc)
            return {"success": False, "error": f"Claim is already {status}, nothing to cancel."}

    cid = claim["id"]
    food_id = claim.get("food_id")
    claim_qty = int(claim.get("quantity") or 1)

    # Release the claim by removing it (claim_status enum has no 'cancelled' value)
    try:
        await supabase_delete(
            "food_claims",
            {"id": f"eq.{cid}", "claimer_id": f"eq.{user_id}"},
        )
    except Exception as exc:
        logger.error("cancel_claim: delete failed: %s", exc)
        return {"success": False, "error": f"Could not cancel claim: {exc}"}

    # Restore the listing (only if it exists and was marked claimed/active)
    title = "the listing"
    if food_id:
        try:
            listings = await supabase_get("food_listings", {
                "id": f"eq.{food_id}",
                "select": "id,title,quantity,status",
                "limit": "1",
            })
            if listings:
                listing = listings[0]
                title = str(listing.get("title") or title)
                try:
                    current_qty = float(listing.get("quantity") or 0)
                except (TypeError, ValueError):
                    current_qty = 0
                restored_qty = current_qty + claim_qty
                listing_status = str(listing.get("status") or "").lower()
                patch = {"quantity": restored_qty}
                if listing_status in {"claimed", "completed"}:
                    patch["status"] = "active"
                await supabase_patch("food_listings", {"id": f"eq.{food_id}"}, patch)
        except Exception as exc:
            logger.warning("cancel_claim: listing restore failed (non-fatal): %s", exc)

    return {
        "success": True,
        "claim_id": str(cid),
        "listing_id": str(food_id) if food_id else None,
        "title": title,
        "summary": f"Released your claim on '{title}'. It's back up for the community.",
    }


# ---------------------------------------------------------------------------
# confirm_claim — mark a claim as completed (pickup confirmed)
# ---------------------------------------------------------------------------


async def _confirm_claim(
    user_id: str,
    claim_id: Optional[str] = None,
    listing_id: Optional[str] = None,
    **_ignored,
) -> dict:
    from backend.ai_engine import supabase_get, supabase_patch

    logger.info("confirm_claim: user=%s claim=%s listing=%s", user_id, claim_id, listing_id)
    if not user_id:
        return {"success": False, "error": "missing user_id"}

    try:
        claim = await _find_user_claim(user_id, claim_id, listing_id)
    except Exception as exc:
        logger.error("confirm_claim: lookup failed: %s", exc)
        return {"success": False, "error": f"Could not look up your claim: {exc}"}

    if not claim:
        return {"success": False, "error": "No active claim found to confirm."}

    status = str(claim.get("status") or "").lower()
    if status == "completed":
        return {"success": False, "error": "Claim is already confirmed as picked up."}
    if status == "expired":
        return {"success": False, "error": "Cannot confirm an expired claim."}

    cid = claim["id"]
    food_id = claim.get("food_id")

    try:
        await supabase_patch(
            "food_claims",
            {"id": f"eq.{cid}", "claimer_id": f"eq.{user_id}"},
            {"status": "completed"},
        )
    except Exception as exc:
        logger.error("confirm_claim: patch failed: %s", exc)
        return {"success": False, "error": f"Could not confirm claim: {exc}"}

    # Look up title for the summary
    title = "your claim"
    if food_id:
        try:
            listings = await supabase_get("food_listings", {
                "id": f"eq.{food_id}",
                "select": "title",
                "limit": "1",
            })
            if listings:
                title = str(listings[0].get("title") or title)
        except Exception:
            pass

    return {
        "success": True,
        "claim_id": str(cid),
        "listing_id": str(food_id) if food_id else None,
        "title": title,
        "summary": f"Pickup confirmed for '{title}'. You're all set — thanks for keeping food out of the landfill!",
    }


# ---------------------------------------------------------------------------
# delete_listing — permanently delete a donor's own listing from the DB
# ---------------------------------------------------------------------------


async def _delete_listing(
    user_id: str,
    listing_id: Optional[str] = None,
    title: Optional[str] = None,
    confirmed: bool = False,
    **_ignored,
) -> dict:
    from backend.ai_engine import supabase_get, supabase_delete

    logger.info("delete_listing: user=%s listing=%s title=%s confirmed=%s", user_id, listing_id, title, confirmed)
    if not user_id:
        return {"success": False, "error": "missing user_id"}
    if not confirmed:
        return {
            "success": False,
            "needs_confirmation": True,
            "message": "Deletion is permanent and cannot be undone. Please confirm you want to permanently delete this listing.",
        }

    # Resolve listing_id from title if not provided. Use substring match
    # (ilike %lookup%) and refuse to silently pick when more than one row
    # matches — delete is permanent, ambiguity must be resolved by the donor.
    if not listing_id and title:
        lookup = title.strip()
        rows = await supabase_get("food_listings", {
            "user_id": f"eq.{user_id}",
            "title": f"ilike.%{lookup}%",
            "select": "id,title,status",
            "order": "created_at.desc",
            "limit": "5",
        })
        if not rows:
            return {
                "success": False,
                "error": f"No listing matching '{lookup}'.",
                "lookup": lookup,
                "message": (
                    f"Couldn't find a listing whose title contains '{lookup}'. "
                    "Ask the donor which listing they mean — call "
                    "get_user_listings to show them their listings, then "
                    "retry with the specific listing_id."
                ),
            }
        if len(rows) > 1:
            return {
                "success": False,
                "error": "multiple_matches",
                "lookup": lookup,
                "matches": [
                    {"listing_id": str(r["id"]), "title": r.get("title"), "status": r.get("status")}
                    for r in rows
                ],
                "message": (
                    f"Multiple listings match '{lookup}'. Read the titles "
                    "back to the donor, let them pick one, then retry "
                    "delete_listing with the specific listing_id."
                ),
            }
        listing_id = rows[0]["id"]
        title = rows[0].get("title") or title

    if not listing_id:
        return {"success": False, "error": "Could not find a listing to delete. Please provide the listing title or ID."}

    # Verify ownership before deleting
    check = await supabase_get("food_listings", {
        "id": f"eq.{listing_id}",
        "user_id": f"eq.{user_id}",
        "select": "id,title",
        "limit": "1",
    })
    if not check:
        return {"success": False, "error": "Listing not found or you don't own it."}
    title = check[0].get("title") or title or "the listing"

    try:
        count = await supabase_delete("food_listings", {
            "id": f"eq.{listing_id}",
            "user_id": f"eq.{user_id}",
        })
    except Exception as exc:
        logger.error("delete_listing: delete failed: %s", exc)
        return {"success": False, "error": f"Could not delete listing: {exc}"}

    if count == 0:
        return {"success": False, "error": "Listing not found or already deleted."}

    return {
        "success": True,
        "ok": True,
        "listing_id": str(listing_id),
        "title": title,
        "summary": f"'{title}' has been permanently deleted from the database.",
    }


# ---------------------------------------------------------------------------
# deactivate_listing — donor removes their own listing
# ---------------------------------------------------------------------------


async def _deactivate_listing(
    user_id: str,
    listing_id: Optional[str] = None,
    title: Optional[str] = None,
    **_ignored,
) -> dict:
    from backend.ai_engine import supabase_get, supabase_patch

    logger.info("deactivate_listing: user=%s listing=%s title=%s", user_id, listing_id, title)
    if not user_id:
        return {"success": False, "error": "missing user_id"}

    # Resolve listing_id from title if not provided. Honor the title the
    # caller gave us: a miss must NOT silently take down the wrong listing.
    if not listing_id and title:
        lookup = title.strip()
        rows = await supabase_get("food_listings", {
            "user_id": f"eq.{user_id}",
            "title": f"ilike.%{lookup}%",
            "status": "in.(active,approved,pending)",
            "select": "id,title,status",
            "order": "created_at.desc",
            "limit": "5",
        })
        if not rows:
            return {
                "success": False,
                "error": f"No active listing matching '{lookup}'.",
                "lookup": lookup,
                "message": (
                    f"Couldn't find an active listing whose title contains "
                    f"'{lookup}'. Ask the donor which listing they mean — "
                    "call get_user_listings to show them their current "
                    "listings, then retry with the specific listing_id."
                ),
            }
        if len(rows) > 1:
            return {
                "success": False,
                "error": "multiple_matches",
                "lookup": lookup,
                "matches": [
                    {"listing_id": str(r["id"]), "title": r.get("title")}
                    for r in rows
                ],
                "message": (
                    f"Multiple listings match '{lookup}'. Read the titles "
                    "back to the donor, let them pick one, then retry "
                    "deactivate_listing with the specific listing_id."
                ),
            }
        listing_id = rows[0]["id"]
        title = rows[0].get("title") or title

    if not listing_id:
        # Fall back: user's most recently posted active listing
        rows = await supabase_get("food_listings", {
            "user_id": f"eq.{user_id}",
            "status": "in.(active,approved,pending)",
            "select": "id,title,status",
            "order": "created_at.desc",
            "limit": "1",
        })
        if not rows:
            return {"success": False, "error": "No active listing found to deactivate."}
        listing_id = rows[0]["id"]
        title = rows[0].get("title") or title

    # Verify ownership
    check = await supabase_get("food_listings", {
        "id": f"eq.{listing_id}",
        "user_id": f"eq.{user_id}",
        "select": "id,title,status",
        "limit": "1",
    })
    if not check:
        return {"success": False, "error": "Listing not found or you don't own it."}
    title = check[0].get("title") or title or "the listing"
    current_status = str(check[0].get("status") or "").lower()
    if current_status in {"expired", "completed", "cancelled", "deleted"}:
        return {"success": False, "error": f"Listing is already {current_status}."}

    try:
        await supabase_patch(
            "food_listings",
            {"id": f"eq.{listing_id}", "user_id": f"eq.{user_id}"},
            {"status": "expired"},
        )
    except Exception as exc:
        logger.error("deactivate_listing: patch failed: %s", exc)
        return {"success": False, "error": f"Could not deactivate listing: {exc}"}

    return {
        "success": True,
        "ok": True,
        "listing_id": str(listing_id),
        "title": title,
        "summary": f"'{title}' has been taken down and is no longer visible to the community.",
    }


# ---------------------------------------------------------------------------
# get_user_listings — fetch the donor's own listings
# ---------------------------------------------------------------------------


async def _get_user_listings(
    user_id: str,
    status: str = "active",
    **_ignored,
) -> dict:
    from backend.ai_engine import supabase_get

    logger.info("get_user_listings: user=%s status=%s", user_id, status)
    if not user_id:
        return {"success": False, "error": "missing user_id"}

    params: dict = {
        "user_id": f"eq.{user_id}",
        "select": "id,title,quantity,unit,category,status,expiry_date,created_at,image_url",
        "order": "created_at.desc",
        "limit": "20",
    }
    if status == "all":
        pass  # no status filter
    elif status in {"active", "approved"}:
        params["status"] = "in.(active,approved,pending)"
    else:
        params["status"] = f"eq.{status}"

    try:
        rows = await supabase_get("food_listings", params)
    except Exception as exc:
        return {"success": False, "error": f"Could not fetch listings: {exc}"}

    # Enrich each listing with a claim count so the donor can answer
    # "has anyone claimed my food?" / "how many claims does X have?"
    # without a second tool round-trip.
    listing_ids = [str(r.get("id")) for r in (rows or []) if r.get("id")]
    claims_by_listing: dict[str, int] = {}
    if listing_ids:
        try:
            claims = await supabase_get("food_claims", {
                "food_id": f"in.({','.join(listing_ids)})",
                "status": "in.(pending,approved,confirmed,completed)",
                "select": "food_id,status",
            })
            for c in claims or []:
                fid = str(c.get("food_id"))
                claims_by_listing[fid] = claims_by_listing.get(fid, 0) + 1
        except Exception as exc:
            logger.warning("get_user_listings: claim-count enrichment failed: %s", exc)

    listings = [
        {
            "id": r.get("id"),
            "title": r.get("title"),
            "quantity": r.get("quantity"),
            "unit": r.get("unit"),
            "category": r.get("category"),
            "status": r.get("status"),
            "expiry_date": r.get("expiry_date"),
            "has_photo": bool(r.get("image_url")),
            "claims_count": claims_by_listing.get(str(r.get("id")), 0),
        }
        for r in (rows or [])
    ]

    total_claims = sum(l["claims_count"] for l in listings)
    return {
        "success": True,
        "ok": True,
        "count": len(listings),
        "total_claims": total_claims,
        "listings": listings,
        "summary": (
            f"You have {len(listings)} {status if status != 'active' else 'active'} "
            f"listing(s) with {total_claims} active claim(s) across them."
        ),
        # Views are NOT tracked yet — surface this so the AI can honestly
        # answer "how many views does my listing have?".
        "views_tracking": "not_available",
    }


# ---------------------------------------------------------------------------
# update_food_listing — donor edits one of their own listings in natural language
# ---------------------------------------------------------------------------


_UPDATABLE_LISTING_FIELDS = {
    "title", "description", "quantity", "unit",
    "expiry_date", "pickup_by",
    "dietary_tags", "allergens", "image_url",
    "category", "location", "full_address",
}

_STATUS_ALIASES = {
    "available": "approved", "live": "approved", "active": "approved",
    "approved": "approved",
    "unavailable": "expired", "hidden": "expired", "taken down": "expired",
    "expired": "expired", "gone": "expired", "all gone": "expired",
    "completed": "completed", "claimed": "claimed", "cancelled": "cancelled",
}


async def _update_food_listing(
    user_id: str,
    listing_id: Optional[str] = None,
    title_lookup: Optional[str] = None,
    title: Optional[str] = None,
    quantity: Optional[float] = None,
    unit: Optional[str] = None,
    description: Optional[str] = None,
    category: Optional[str] = None,
    expiry_date: Optional[str] = None,
    pickup_by: Optional[str] = None,
    location: Optional[str] = None,
    dietary_tags: Optional[list] = None,
    allergens: Optional[list] = None,
    image_url: Optional[str] = None,
    status: Optional[str] = None,
    **_ignored,
) -> dict:
    """Patch one of the authenticated donor's own listings.

    Handles natural-language edits like 'change my pickup time to 7pm',
    'increase servings to 10', 'update description', 'mark as unavailable',
    'add another photo'. Ownership is enforced via the user_id filter (and
    RLS on top). Only fields the caller actually supplies are written.
    """
    from backend.ai_engine import supabase_get, supabase_patch

    logger.info(
        "update_food_listing: user=%s listing=%s title_lookup=%s",
        user_id, listing_id, title_lookup,
    )
    if not user_id:
        return {"success": False, "error": "missing user_id"}

    # 1) Resolve listing_id — direct, by title, or most-recent fallback.
    #    If the caller passed title_lookup we MUST honor it: do NOT silently
    #    fall back to "the most recent active listing" on a miss. That bug
    #    caused the AI to patch the wrong row and then report success.
    if not listing_id and title_lookup:
        lookup = title_lookup.strip()
        rows = await supabase_get("food_listings", {
            "user_id": f"eq.{user_id}",
            "title": f"ilike.%{lookup}%",
            "status": "in.(active,approved,pending)",
            "select": "id,title",
            "order": "created_at.desc",
            "limit": "5",
        })
        if not rows:
            return {
                "success": False,
                "error": f"No active listing matching '{lookup}'.",
                "lookup": lookup,
                "message": (
                    f"Couldn't find an active listing whose title contains "
                    f"'{lookup}'. Ask the donor which listing they mean — "
                    "call get_user_listings to show them their current "
                    "listings, then retry with the specific listing_id."
                ),
            }
        if len(rows) > 1:
            return {
                "success": False,
                "error": "multiple_matches",
                "lookup": lookup,
                "matches": [
                    {"listing_id": str(r["id"]), "title": r.get("title")}
                    for r in rows
                ],
                "message": (
                    f"Multiple listings match '{lookup}'. Read the titles "
                    "back to the donor, let them pick one, then retry "
                    "update_food_listing with the specific listing_id."
                ),
            }
        listing_id = rows[0]["id"]
    if not listing_id:
        rows = await supabase_get("food_listings", {
            "user_id": f"eq.{user_id}",
            "status": "in.(active,approved,pending)",
            "select": "id,title",
            "order": "created_at.desc",
            "limit": "1",
        })
        if not rows:
            return {"success": False, "error": "No active listing found to update."}
        listing_id = rows[0]["id"]

    # 2) Ownership check
    check = await supabase_get("food_listings", {
        "id": f"eq.{listing_id}",
        "user_id": f"eq.{user_id}",
        "select": "id,title,status",
        "limit": "1",
    })
    if not check:
        return {"success": False, "error": "Listing not found or you don't own it."}
    current_title = check[0].get("title") or "the listing"

    # 3) Build the patch
    patch: dict = {}
    if title is not None:
        t = str(title).strip()
        if t:
            patch["title"] = t[:200]
    if description is not None:
        patch["description"] = str(description).strip()[:2000]
    if quantity is not None:
        try:
            q = float(quantity)
            if q > 0:
                patch["quantity"] = q
        except (TypeError, ValueError):
            return {"success": False, "error": "quantity must be a number"}
    if unit is not None:
        u = str(unit).strip()[:40]
        if u:
            patch["unit"] = u
    if category is not None:
        c = str(category).strip().lower()
        if c in _LISTING_CATEGORIES:
            patch["category"] = c
    if expiry_date is not None:
        resolved = _normalize_expiry_date(expiry_date)
        if resolved:
            patch["expiry_date"] = resolved
    if pickup_by is not None:
        # food_listings.pickup_by is TIMESTAMPTZ — only write if it parses as a
        # real datetime so we never ship raw natural-language to the DB.
        from datetime import datetime as _dt
        raw = str(pickup_by).strip()
        try:
            _dt.fromisoformat(raw.replace("Z", "+00:00"))
            patch["pickup_by"] = raw
        except (TypeError, ValueError):
            pass
    if location is not None:
        loc_s = str(location).strip()[:200]
        if loc_s:
            patch["location"] = loc_s
            patch["full_address"] = loc_s
    if isinstance(dietary_tags, list):
        patch["dietary_tags"] = [str(t).strip()[:40] for t in dietary_tags if str(t).strip()][:20]
    if isinstance(allergens, list):
        patch["allergens"] = [str(t).strip()[:40] for t in allergens if str(t).strip()][:20]
    if image_url and isinstance(image_url, str) and image_url.strip().startswith(("http://", "https://")):
        patch["image_url"] = image_url.strip()[:2000]
    if status is not None:
        s = str(status).strip().lower()
        mapped = _STATUS_ALIASES.get(s, s if s in _STATUS_ALIASES.values() else None)
        if mapped:
            patch["status"] = mapped

    if not patch:
        return {
            "success": False,
            "error": "no_fields_to_update",
            "message": (
                "No updatable fields were supplied. Pass at least one of "
                "title, description, quantity, unit, category, expiry_date, "
                "pickup_by, location, dietary_tags, allergens, "
                "image_url, status."
            ),
        }

    try:
        await supabase_patch(
            "food_listings",
            {"id": f"eq.{listing_id}", "user_id": f"eq.{user_id}"},
            patch,
        )
    except Exception as exc:
        logger.error("update_food_listing: patch failed: %s", exc)
        return {"success": False, "error": f"Could not update listing: {exc}"}

    return {
        "success": True,
        "ok": True,
        "listing_id": str(listing_id),
        "title": current_title,
        "updated_fields": sorted(patch.keys()),
        "summary": f"Updated '{current_title}' ({', '.join(sorted(patch.keys()))}).",
    }


# ---------------------------------------------------------------------------
# bulk_import_listings — create many listings in one call
# ---------------------------------------------------------------------------


_CSV_CATEGORY_ALIASES = {
    "fruit": "produce", "fruits": "produce", "vegetable": "produce",
    "vegetables": "produce", "veggies": "produce", "veg": "produce",
    "bread": "bakery", "pastry": "bakery", "baked": "bakery",
    "milk": "dairy", "cheese": "dairy", "yogurt": "dairy",
    "canned": "pantry", "dry": "pantry", "grain": "pantry", "grains": "pantry",
    "rice": "pantry", "pasta": "pantry",
    "fish": "meat", "poultry": "meat", "chicken": "meat", "beef": "meat",
    "cooked": "prepared", "meal": "prepared", "meals": "prepared",
}


def _csv_parse(text: str) -> list[dict]:
    """Tiny RFC-4180-ish CSV parser. Header row required."""
    import csv as _csv
    import io as _io

    if not isinstance(text, str) or not text.strip():
        return []
    reader = _csv.DictReader(_io.StringIO(text))
    rows = []
    for raw in reader:
        rows.append({(k or "").strip().lower(): (v.strip() if isinstance(v, str) else v) for k, v in raw.items() if k})
    return rows


def _normalize_bulk_row(raw: dict, user_id: str) -> Optional[dict]:
    title = str(raw.get("title") or raw.get("name") or raw.get("item") or "").strip()
    if not title:
        return None
    try:
        qty = float(raw.get("quantity") or raw.get("qty") or raw.get("amount") or 0)
    except (TypeError, ValueError):
        qty = 0
    # Per the bulk contract the server defaults a missing/zero qty to 1
    # (the AI is told to double-check). We do NOT drop the row for qty alone
    # — only a missing title makes a row unusable.
    if qty <= 0:
        qty = 1
    unit = str(raw.get("unit") or raw.get("units") or "items").strip() or "items"
    cat_raw = str(raw.get("category") or raw.get("type") or "other").strip().lower()
    category = cat_raw if cat_raw in _LISTING_CATEGORIES else _CSV_CATEGORY_ALIASES.get(cat_raw, "other")
    row: dict = {
        "user_id": str(user_id),
        "title": title[:200],
        "quantity": qty,
        "unit": unit[:40],
        "category": category,
        "listing_type": "donation",
        # Use "approved" (not "active") to match _create_food_listing so all
        # AI-posted listings appear with the same status. Both show in the
        # find-food feed but "approved" is semantically correct for new AI posts.
        "status": "approved",
    }
    if raw.get("description"):
        row["description"] = str(raw["description"])[:1000]
    if raw.get("expiry_date") or raw.get("expiration_date") or raw.get("best_before"):
        row["expiry_date"] = _normalize_expiry_date(
            raw.get("expiry_date"),
            raw.get("expiration_date"),
            raw.get("best_before"),
        )
    # Capture the row's own pickup address from any of the common column names.
    row_addr = (
        raw.get("location") or raw.get("address")
        or raw.get("pickup_address") or raw.get("full_address")
    )
    if row_addr:
        row["location"] = str(row_addr)[:400]
    return row


async def _bulk_import_listings(
    user_id: str,
    csv_text: Optional[str] = None,
    listings: Optional[list] = None,
    default_address: Optional[str] = None,
    default_expiry_date: Optional[str] = None,
    community_name: Optional[str] = None,
    community_id: Optional[str] = None,
    community_confirmed: bool = False,
    **_ignored,
) -> dict:
    from backend.ai_engine import (
        supabase_post,
        fetch_donor_listing_defaults,
        apply_donor_defaults_to_listing,
    )

    logger.info("bulk_import_listings: user=%s csv_len=%s listings=%s default_address=%s",
                user_id,
                len(csv_text) if csv_text else 0,
                len(listings) if listings else 0,
                bool(default_address))
    if not user_id:
        return {"success": False, "error": "missing user_id"}

    donor = await fetch_donor_listing_defaults(str(user_id))

    if not community_confirmed:
        suggested_id, suggested_name = (None, None)
        if donor.get("community_id"):
            suggested_id, suggested_name = await _resolve_community(None, str(donor["community_id"]))
        return {
            "success": False,
            "error": "community_not_confirmed",
            "message": (
                "Confirm which community/school this batch is for before importing. "
                "Then call bulk_import_listings with community_name and "
                "community_confirmed=true."
            ),
            "suggested_community_name": suggested_name,
            "suggested_community_id": suggested_id,
        }

    resolved_community_id, resolved_community_name = await _resolve_community(
        community_name, community_id
    )
    if not resolved_community_id:
        return {
            "success": False,
            "error": "community_required",
            "message": (
                "Could not resolve the community for this batch. Ask the donor to "
                "pick one, confirm it, then retry with community_name and "
                "community_confirmed=true."
            ),
        }

    rows_in: list[dict] = []
    if csv_text:
        rows_in.extend(_csv_parse(csv_text))
    if isinstance(listings, list):
        for item in listings:
            if isinstance(item, dict):
                rows_in.append({(k or "").lower(): v for k, v in item.items()})

    if not rows_in:
        return {"success": False, "error": "No rows to import. Provide csv_text or listings."}
    if len(rows_in) > 100:
        return {"success": False, "error": "Too many rows (max 100 per call)."}

    # Donor profile (address + coordinates) loaded ONCE and reused for every
    # row that doesn't carry its own pickup address. Mirrors the single-listing
    # creator so bulk-imported listings get a location + map pin too.
    # Use only `address` (plain text) — users.location is a JSON {latitude,longitude}
    # dict used for coordinates, not as a human-readable address string.
    donor_addr = str(donor.get("address") or "").strip()
    explicit_default = str(default_address).strip() if default_address else ""
    # Batch-wide fallback address: the address the AI passed wins over the
    # donor's saved profile address.
    fallback_address = explicit_default or donor_addr or None

    # ---- Pre-flight: normalize + classify gaps before inserting anything ----
    # (1-based row numbers so the AI can talk to the donor in human terms.)
    normalized: list[Optional[dict]] = []
    missing_title_rows: list[int] = []
    missing_address_rows: list[int] = []
    missing_expiry_rows: list[int] = []
    batch_expiry = _normalize_expiry_date(default_expiry_date)
    for idx, raw in enumerate(rows_in):
        human_row = idx + 1
        norm = _normalize_bulk_row(raw, user_id)
        normalized.append(norm)
        if not norm:
            missing_title_rows.append(human_row)
            continue
        row_addr = str(norm.get("location") or "").strip()
        if not row_addr and not fallback_address:
            missing_address_rows.append(human_row)
        if not norm.get("expiry_date") and not batch_expiry:
            missing_expiry_rows.append(human_row)

    if missing_title_rows or missing_address_rows or missing_expiry_rows:
        needs: list[str] = []
        if missing_title_rows:
            needs.append("title")
        if missing_address_rows:
            needs.append("address")
        if missing_expiry_rows:
            needs.append("expiry_date")
        return {
            "success": False,
            "posted": 0,
            "needs": needs,
            "missing_title_rows": missing_title_rows,
            "missing_address_rows": missing_address_rows,
            "missing_expiry_rows": missing_expiry_rows,
            "fallback_address": fallback_address,
            "total": len(rows_in),
            "summary": (
                "Pre-flight blocked the import: "
                + (f"{len(missing_title_rows)} row(s) missing a title" if missing_title_rows else "")
                + (" and " if missing_title_rows and missing_address_rows else "")
                + (f"{len(missing_address_rows)} row(s) missing a pickup address" if missing_address_rows else "")
                + (" and " if (missing_title_rows or missing_address_rows) and missing_expiry_rows else "")
                + (f"{len(missing_expiry_rows)} row(s) missing expiry_date" if missing_expiry_rows else "")
                + ". Ask the donor for a batch best-by date (default_expiry_date) or per-row expiry. Nothing was posted."
            ),
        }

    # ---- Insert: apply address, donor defaults, and coordinates per row ----
    created_ids: list[str] = []
    errors: list[dict] = []
    # Cache geocode lookups so a batch sharing one address hits Mapbox once.
    geocode_cache: dict[str, Optional[tuple]] = {}
    for idx, norm in enumerate(normalized):
        if not norm:  # unreachable after pre-flight, but keep mypy/readers happy
            continue
        if not norm.get("expiry_date") and batch_expiry:
            norm["expiry_date"] = batch_expiry
        resolved = (str(norm.get("location") or "").strip() or fallback_address or "")[:400]
        if resolved:
            norm["location"] = resolved
            norm["full_address"] = resolved
        # Geocode the resolved pickup address BEFORE donor defaults so a row
        # with its own address gets its OWN pin, not the donor's home coords.
        if resolved:
            if resolved not in geocode_cache:
                geocode_cache[resolved] = await _forward_geocode(resolved)
            coords = geocode_cache[resolved]
            if coords:
                norm["latitude"], norm["longitude"] = coords
        # Donor defaults fill name/phone + coords ONLY where missing.
        norm = apply_donor_defaults_to_listing(norm, donor)
        norm["community_id"] = resolved_community_id
        try:
            result = await supabase_post("food_listings", norm)
            if isinstance(result, list) and result:
                created_ids.append(str(result[0].get("id")))
            else:
                errors.append({"index": idx + 1, "error": "Insert returned no row"})
        except Exception as exc:
            errors.append({"index": idx + 1, "error": str(exc)})

    posted = len(created_ids)
    return {
        "success": posted > 0,
        "posted": posted,
        "verified": posted,
        "created": posted,
        "total": len(rows_in),
        "failed": len(errors),
        "ids": created_ids,
        "errors": errors,
        "results": errors,
        "summary": f"Imported {posted} of {len(rows_in)} listings."
                   + (f" {len(errors)} failed." if errors else ""),
    }


# ---------------------------------------------------------------------------
# get_donor_expiring_listings — donor's listings nearing expiry
# ---------------------------------------------------------------------------


async def _get_donor_expiring_listings(
    user_id: str,
    days: Optional[int] = 2,
    **_ignored,
) -> dict:
    from backend.ai_engine import supabase_get
    from datetime import datetime, timedelta, timezone

    logger.info("get_donor_expiring_listings: user=%s days=%s", user_id, days)
    if not user_id:
        return {"success": False, "error": "missing user_id"}

    try:
        window = int(days) if days is not None else 2
    except (TypeError, ValueError):
        window = 2
    window = max(1, min(window, 14))

    cutoff = (datetime.now(timezone.utc) + timedelta(days=window)).date().isoformat()
    today = datetime.now(timezone.utc).date().isoformat()

    try:
        rows = await supabase_get("food_listings", {
            "user_id": f"eq.{user_id}",
            "status": "in.(approved,active)",
            # Donor view: their donations expiring soon, never their requests.
            "listing_type": "eq.donation",
            # Lower bound (gte today) so already-expired listings are excluded.
            # Without it, lte.cutoff would also return past-expiry rows which
            # would confuse the AI into narrating stale items as "expiring soon".
            "expiry_date": f"gte.{today}",
            "and": f"(expiry_date.lte.{cutoff})",
            "select": "id,title,quantity,unit,category,expiry_date,pickup_by,full_address",
            "order": "expiry_date.asc",
            "limit": "20",
        })
    except Exception as exc:
        logger.error("get_donor_expiring_listings: fetch failed: %s", exc)
        return {"success": False, "error": f"Could not look up your listings: {exc}"}

    if not rows:
        return {
            "success": True,
            "count": 0,
            "listings": [],
            "summary": f"No listings expiring in the next {window} day(s). You're good!",
        }

    summary_lines = [
        f"- '{r.get('title')}' ({r.get('quantity')} {r.get('unit')}) expires {r.get('expiry_date')}"
        for r in rows
    ]
    return {
        "success": True,
        "count": len(rows),
        "window_days": window,
        "listings": rows,
        "summary": f"{len(rows)} listing(s) expiring within {window} day(s):\n" + "\n".join(summary_lines),
    }


# ---------------------------------------------------------------------------
# attach_photos_to_listing — set image_url on the donor's listing
# ---------------------------------------------------------------------------


async def _attach_photos_to_listing(
    user_id: str,
    listing_id: str,
    image_url: str,
    **_ignored,
) -> dict:
    from backend.ai_engine import supabase_get, supabase_patch

    logger.info("attach_photos_to_listing: user=%s listing=%s", user_id, listing_id)
    if not (user_id and listing_id and image_url):
        return {"success": False, "error": "user_id, listing_id, and image_url are all required"}
    if not (image_url.startswith("http://") or image_url.startswith("https://")):
        return {"success": False, "error": "image_url must start with http:// or https://"}

    try:
        listings = await supabase_get("food_listings", {
            "id": f"eq.{listing_id}",
            "user_id": f"eq.{user_id}",
            "select": "id,title",
            "limit": "1",
        })
    except Exception as exc:
        return {"success": False, "error": f"Could not look up listing: {exc}"}
    if not listings:
        return {"success": False, "error": "Listing not found or not owned by you."}

    try:
        await supabase_patch(
            "food_listings",
            {"id": f"eq.{listing_id}", "user_id": f"eq.{user_id}"},
            {"image_url": image_url},
        )
    except Exception as exc:
        logger.error("attach_photos_to_listing: patch failed: %s", exc)
        return {"success": False, "error": f"Could not attach photo: {exc}"}

    title = str(listings[0].get("title") or "your listing")
    return {
        "success": True,
        "listing_id": str(listing_id),
        "image_url": image_url,
        "title": title,
        "summary": f"Photo attached to '{title}'.",
    }


# ---------------------------------------------------------------------------
# navigate_ui — friendly alias of ui_action that maps common alt arg names
# ---------------------------------------------------------------------------


_NAVIGATE_ACTION_ALIASES = {
    "open": "navigate",
    "go": "navigate",
    "goto": "navigate",
    "go_to": "navigate",
    "show": "navigate",
}

# Recipient-facing AI modal surfaces. The frontend opens these as overlays —
# they are NOT React Router paths, so they must NOT go through the
# `_UI_ALLOWED_PATHS` validator. The model is instructed (in the system
# prompts) to call navigate_ui(action='open', target=<one of these>).
_UI_MODAL_TARGETS = {
    "meal-suggestions",
    "spoilage-alerts",
    "storage-coach",
    "smart-notifications",
    "pickup-reminders",
    "sms-consent",
    # also accept the snake_case form the model sometimes produces
    "meal_suggestions",
    "spoilage_alerts",
    "storage_coach",
    "smart_notifications",
    "pickup_reminders",
    "sms_consent",
}

_MODAL_ACTION_ALIASES = {
    "open": "open_modal",
    "close": "close_modal",
    "toggle": "toggle_modal",
    "show": "open_modal",
    "hide": "close_modal",
}


async def _navigate_ui(
    action: str,
    path: Optional[str] = None,
    target: Optional[str] = None,
    target_id: Optional[str] = None,
    listing_id: Optional[str] = None,
    lang: Optional[str] = None,
    reason: Optional[str] = None,
    **_ignored,
) -> dict:
    action_lc = (action or "").lower()
    target_lc = (target or "").lower().strip().lstrip("/")

    # 1. Modal surfaces (recipient AI helpers) — handled directly.
    if target_lc in _UI_MODAL_TARGETS:
        modal_action = _MODAL_ACTION_ALIASES.get(action_lc, action_lc or "open_modal")
        canonical_target = target_lc.replace("_", "-")
        payload = {
            "ok": True,
            "action": modal_action,
            "target": canonical_target,
        }
        if reason:
            payload["reason"] = reason
        logger.info("navigate_ui (modal): %s -> %s", modal_action, canonical_target)
        return payload

    # 2. Otherwise treat as a route navigation.
    mapped_action = _NAVIGATE_ACTION_ALIASES.get(action_lc, action)
    if mapped_action == "navigate" and not path and target:
        path = target if target.startswith("/") else f"/{target.lstrip('/')}"
    return await _ui_action(
        action=mapped_action,
        path=path,
        listing_id=listing_id,
        target_id=target_id,
        lang=lang,
        reason=reason,
    )


# ---------------------------------------------------------------------------
# _get_profile_gaps — nudge AI to prompt for missing profile fields
# ---------------------------------------------------------------------------

_PROFILE_FIELDS_EN: list[tuple[str, str]] = [
    ("phone", "Add a phone number so donors can coordinate pickup with you."),
    ("address", "Add your address so we can show you food nearby and auto-fill pickup locations."),
    ("dietary_restrictions", "Share any dietary restrictions so we can filter food recommendations for you."),
    ("community_role", "Let us know if you're a donor or recipient so we can personalise your experience."),
]

_PROFILE_FIELDS_ES: list[tuple[str, str]] = [
    ("phone", "Agrega tu teléfono para que los donantes puedan coordinar la recogida contigo."),
    ("address", "Agrega tu dirección para mostrarte comida cercana y rellenar automáticamente la ubicación."),
    ("dietary_restrictions", "Comparte tus restricciones alimentarias para filtrar recomendaciones."),
    ("community_role", "Cuéntanos si eres donante o recipiente para personalizar tu experiencia."),
]


async def _get_profile_gaps(user_id: str) -> dict:
    """Return a list of nudge prompts for profile fields the user hasn't filled in.

    Called by ai_engine._profile_gap_prompt() to inject gentle reminders
    into the system prompt so the model can naturally ask the user to
    complete their profile without being aggressive.
    """
    from backend.ai_engine import supabase_get

    if not user_id:
        return {"prompts_en": [], "prompts_es": []}

    try:
        rows = await supabase_get("users", {
            "id": f"eq.{user_id}",
            "select": "phone,address,dietary_restrictions,community_role",
            "limit": "1",
        })
    except Exception as exc:
        logger.warning("_get_profile_gaps: fetch failed: %s", exc)
        return {"prompts_en": [], "prompts_es": []}

    if not rows:
        return {"prompts_en": [], "prompts_es": []}

    profile = rows[0]
    prompts_en: list[str] = []
    prompts_es: list[str] = []

    for (field, msg_en), (_, msg_es) in zip(_PROFILE_FIELDS_EN, _PROFILE_FIELDS_ES):
        val = profile.get(field)
        is_missing = (
            val is None
            or val == ""
            or val == []
            or (isinstance(val, list) and len(val) == 0)
        )
        if is_missing:
            prompts_en.append(msg_en)
            prompts_es.append(msg_es)

    return {"prompts_en": prompts_en, "prompts_es": prompts_es}

