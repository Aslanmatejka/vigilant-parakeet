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
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

logger = logging.getLogger("ai_tools")

MAPBOX_TOKEN = os.getenv("MAPBOX_TOKEN") or os.getenv("VITE_MAPBOX_TOKEN", "")
MAPBOX_DIRECTIONS_URL = "https://api.mapbox.com/directions/v5/mapbox"

_PERISHABLE_CATEGORY_MAX_AGE_HOURS = {
    "prepared": 24,
    "prepared food": 24,
    "prepared foods": 24,
    "dairy": 24,
    "meat": 24,
    "seafood": 24,
    "bakery": 48,
    "produce": 48,
    "vegetables": 48,
    "fruits": 48,
    "beverages": 72,
    "other": 72,
    "pantry": 168,
    "canned": 168,
    "grains": 168,
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


def _suggested_expiry_for_category(category: str) -> str:
    cat = str(category or "other").strip().lower()
    hours = _PERISHABLE_CATEGORY_MAX_AGE_HOURS.get(cat, 72)
    days = max(1, int(math.ceil(hours / 24)))
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
        # If we cannot determine freshness at all, fail closed.
        return False

    category = str(listing.get("category") or "other").strip().lower()
    max_age_hours = _PERISHABLE_CATEGORY_MAX_AGE_HOURS.get(category, 72)
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
                            "Optional food category filter: "
                            "proteins, grains, vegetables, fruits, dairy, prepared, bakery, other"
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
            "name": "post_food_request",
            "description": (
                "Post a food REQUEST on behalf of the authenticated recipient "
                "(opposite of a donation). Use when the user says things like "
                "'I need X', 'looking for Y', 'request food'. Confirm key "
                "fields (title, quantity, when needed) with the user before "
                "calling."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "title": {"type": "string", "description": "What's being requested (e.g. 'Baby formula', 'Rice')."},
                    "quantity": {"type": "number"},
                    "unit": {"type": "string"},
                    "category": {
                        "type": "string",
                        "enum": ["produce", "bakery", "dairy", "pantry", "meat", "prepared", "other"],
                    },
                    "description": {"type": "string", "description": "Why it's needed / who it's for."},
                    "needed_by": {"type": "string", "description": "ISO date (YYYY-MM-DD) — when the user needs it by."},
                    "location": {"type": "string"},
                    "people": {"type": "integer", "description": "Number of people this will feed."},
                },
                "required": ["user_id", "title", "quantity", "unit", "category"],
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
        "post_food_request": _post_food_request,
        "bulk_post_food_listings": _bulk_import_listings,
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
        "expiry_date": f"gte.{today_str}",
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
            "donor_name": row.get("donor_name"),
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

async def _search_food_near_user(
    user_id: str,
    radius_km: float = 10,
    food_type: Optional[str] = None,
    max_results: int = 10,
) -> dict:
    """Search available food listings near the user's location.

    1. Fetch the user's location from the users table
    2. Query food_listings with status in [approved, active], not expired
    3. Filter by Haversine distance and optional food_type
    4. Format natural-language-friendly results
    """
    from backend.ai_engine import supabase_get

    logger.info(
        "search_food_near_user: user=%s radius=%skm type=%s",
        user_id, radius_km, food_type,
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
            "latitude,longitude,full_address,location,donor_name,"
            "community_id,communities(id,name),"
            "expiry_date,pickup_by,status,"
            "dietary_tags,allergens,created_at"
        ),
        "status": "in.(approved,active)",
        # Search returns donations only; requests live in their own feed.
        "listing_type": "eq.donation",
        "expiry_date": f"gte.{today_str}",
        "order": "created_at.desc",
        "limit": "100",
    }
    if food_type:
        params["category"] = f"eq.{food_type}"

    # Bounding box pre-filter: narrow DB results to ~radius before fetching
    if user_lat is not None and user_lng is not None:
        # Rough degree offset for the given radius (1 deg lat ≈ 111 km)
        lat_offset = radius_km / 111.0
        lng_offset = radius_km / (111.0 * max(math.cos(math.radians(user_lat)), 0.01))
        params["latitude"] = f"gte.{user_lat - lat_offset}"
        params["latitude"] = f"lte.{user_lat + lat_offset}"
        # PostgREST doesn't support duplicate keys; use AND filter
        params["and"] = (
            f"(latitude.gte.{user_lat - lat_offset},"
            f"latitude.lte.{user_lat + lat_offset},"
            f"longitude.gte.{user_lng - lng_offset},"
            f"longitude.lte.{user_lng + lng_offset})"
        )
        # Remove individual lat filter since we use 'and'
        params.pop("latitude", None)

    try:
        listings = await supabase_get("food_listings", params)
    except Exception as exc:
        logger.error("Food listings fetch failed: %s", exc)
        return {"results": [], "total": 0, "error": f"Database query failed: {exc}"}

    # --- 3. Filter by distance ---
    now = datetime.now(timezone.utc)
    results = []
    for listing in listings:
        if not _listing_is_fresh_enough(listing, now=now):
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

        result = {
            "id": listing.get("id"),
            "title": listing.get("title"),
            "description": listing.get("description", "")[:200],
            "category": listing.get("category"),
            "quantity": listing.get("quantity"),
            "unit": listing.get("unit"),
            "address": listing.get("full_address") or _extract_location_text(listing.get("location")),
            "donor_name": listing.get("donor_name"),
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
        summary = f"Found {len(results)} food item(s) near you:\n" + "\n".join(summary_parts)
    else:
        summary = (
            "No available food listings found within your area right now. "
            "Try expanding your search radius or check back later!"
        )

    return {
        "results": results,
        "listings": results,
        "total": len(results),
        "radius_km": radius_km,
        "user_location_available": user_lat is not None,
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
        "trigger_time": f"lte.{future_iso}",
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

_LISTING_CATEGORIES = {"produce", "bakery", "dairy", "pantry", "meat", "prepared", "other"}


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
        rows = await supabase_get("communities", {
            "name": f"ilike.{name}",
            "select": "id,name",
            "limit": "1",
        })
        if not rows:
            # Fall back to fuzzy contains match.
            rows = await supabase_get("communities", {
                "name": f"ilike.*{name}*",
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


async def _claim_food_listing(
    user_id: str,
    listing_id: str,
    quantity: Optional[int] = None,
    pickup_date: Optional[str] = None,
    people: Optional[int] = None,
    **_ignored,
) -> dict:
    """Create a food_claims row for the authenticated user and decrement the listing."""
    from backend.ai_engine import supabase_get, supabase_post, supabase_patch

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
            "error": f"Listing is no longer available (status: {status}).",
        }
    if status not in {"", "active", "approved", "available"}:
        return {
            "success": False,
            "error": f"Listing is not available to claim yet (status: {status}).",
        }

    try:
        available_qty = float(listing.get("quantity") or 0)
    except (TypeError, ValueError):
        available_qty = 0
    if available_qty <= 0:
        return {"success": False, "error": "Listing has no quantity left to claim."}

    # --- 2. Normalize claim quantity (food_claims.quantity is INTEGER NOT NULL) ---
    try:
        requested_qty = int(quantity) if quantity is not None else 1
    except (TypeError, ValueError):
        requested_qty = 1
    if requested_qty < 1:
        requested_qty = 1
    if requested_qty > int(available_qty):
        requested_qty = int(available_qty) if available_qty >= 1 else 1

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

    # --- 5. Decrement the listing quantity (or mark claimed if fully taken) ---
    remaining = available_qty - requested_qty
    patch_body = {"status": "claimed"} if remaining <= 0 else {"quantity": remaining}
    try:
        await supabase_patch("food_listings", {"id": f"eq.{listing_id}"}, patch_body)
    except Exception as exc:
        logger.warning("claim_food_listing: listing patch failed (non-fatal): %s", exc)

    title = str(listing.get("title") or "the listing")
    unit = str(listing.get("unit") or "")

    summary_parts = [f"Claimed {requested_qty} {unit}".rstrip(), f"of '{title}'"]
    summary = " ".join(p for p in summary_parts if p).strip() + "."
    if pickup_loc:
        summary += f" Pickup at {pickup_loc}."

    return {
        "success": True,
        "claim_id": str(claim_id),
        "receipt_id": str(receipt_id) if receipt_id else None,
        "listing_id": str(listing_id),
        "title": title,
        "quantity": requested_qty,
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
    if status in {"cancelled", "expired"}:
        return {"success": False, "error": f"Cannot confirm a {status} claim."}

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

    try:
        rows = await supabase_get("food_listings", {
            "user_id": f"eq.{user_id}",
            "status": "in.(approved,active)",
            # Donor view: their donations expiring soon, never their requests.
            "listing_type": "eq.donation",
            "expiry_date": f"lte.{cutoff}",
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
# post_food_request — recipient asks the community for food
# ---------------------------------------------------------------------------


async def _post_food_request(
    user_id: str,
    title: str,
    quantity: float,
    unit: str,
    category: str,
    description: Optional[str] = None,
    needed_by: Optional[str] = None,
    location: Optional[str] = None,
    people: Optional[int] = None,
    **_ignored,
) -> dict:
    from backend.ai_engine import supabase_post

    logger.info("post_food_request: user=%s title=%s qty=%s", user_id, title, quantity)
    if not user_id:
        return {"success": False, "error": "missing user_id"}
    title = (title or "").strip()
    if not title:
        return {"success": False, "error": "title is required"}
    try:
        qty = float(quantity)
    except (TypeError, ValueError):
        return {"success": False, "error": "quantity must be a number"}
    if qty <= 0:
        return {"success": False, "error": "quantity must be > 0"}

    cat = (category or "other").lower()
    if cat not in _LISTING_CATEGORIES:
        cat = "other"

    row: dict = {
        "user_id": str(user_id),
        "title": title[:200],
        "quantity": qty,
        "unit": (unit or "items")[:40],
        "category": cat,
        "listing_type": "request",
        "status": "active",
    }
    if description:
        row["description"] = str(description)[:1000]
    if needed_by:
        # food_listings.expiry_date doubles as 'needed_by' for requests
        row["expiry_date"] = str(needed_by).strip()[:40]
    if location:
        loc_s = str(location)[:400]
        row["location"] = loc_s
        row["full_address"] = loc_s
        # Geocode so the request appears on the map with the correct pin.
        try:
            coords = await _forward_geocode(loc_s)
            if coords:
                row["latitude"], row["longitude"] = coords
        except Exception as geo_exc:
            logger.warning("post_food_request: geocode failed (non-fatal): %s", geo_exc)
    if people is not None:
        try:
            # food_listings has no `people` column; fold into description.
            note = f"For {max(1, int(people))} people."
            row["description"] = (row.get("description", "") + " " + note).strip()[:1000]
        except (TypeError, ValueError):
            pass

    try:
        result = await supabase_post("food_listings", row)
    except Exception as exc:
        logger.error("post_food_request: insert failed: %s", exc)
        return {"success": False, "error": f"Could not post request: {exc}"}

    if not (isinstance(result, list) and result):
        return {"success": False, "error": "Insert returned no row."}
    request_id = result[0].get("id")
    return {
        "success": True,
        "request_id": str(request_id),
        "listing_id": str(request_id),
        "title": title,
        "quantity": qty,
        "unit": row["unit"],
        "category": cat,
        "summary": f"Request posted: {qty} {row['unit']} of '{title}'. It's live for nearby donors.",
    }


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

