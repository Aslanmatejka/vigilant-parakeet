"""Post-process assistant replies — structural cleanup only, no content injection."""
from __future__ import annotations

import re
from typing import Optional

_UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.I,
)
_NUMBERED_LINE_RE = re.compile(r"^\s*\d+[\.)]\s", re.M)
_INTERNAL_TOOL_RE = re.compile(
    r"\b(search_food_near_user|claim_listing|post_food_listing|confirm_claim|"
    r"delete_listing|get_user_listings|deactivate_listing)\b",
    re.I,
)
_LISTING_ID_RE = re.compile(
    r"\b(?:listing\s*)?#\s*[0-9a-f-]{8,}\b|\blisting_id\s*[:=]\s*\S+",
    re.I,
)

_LISTING_UI_KEYS = (
    "id", "title", "quantity", "unit", "distance_km", "distance_miles",
    "display_index", "address", "full_address", "image_url", "category",
    "expiry_date", "pickup_by", "community_name", "dietary_tags", "is_own_listing",
)

_CLAIM_UI_KEYS = (
    "success", "title", "quantity", "unit", "pickup_location", "pickup_deadline",
    "image_url", "category", "community_name", "already_claimed", "message",
    "error", "next_step", "claim_id", "listing_id",
)


def tool_result_ok(result: dict) -> bool:
    """True when a tool handler returned a successful outcome."""
    if not isinstance(result, dict):
        return False
    if result.get("success") is True:
        return True
    if result.get("created") is True:
        return True
    err = result.get("error")
    if err in (None, False, ""):
        return True
    return False


def _trim_listing(item: dict) -> dict:
    return {k: item[k] for k in _LISTING_UI_KEYS if item.get(k) is not None}


def enrich_tool_action(fn_name: str, result: dict, entry: dict) -> dict:
    """Attach UI-friendly fields so the chat panel can render rich cards."""
    if not isinstance(result, dict):
        return entry

    if fn_name == "search_food_near_user":
        listings = result.get("listings") or []
        if listings:
            entry["listings"] = [_trim_listing(row) for row in listings[:5]]
        entry["total"] = result.get("total", len(listings))
        if "user_location_available" in result:
            entry["user_location_available"] = result["user_location_available"]

    elif fn_name in {"claim_listing", "claim_food"}:
        for key in _CLAIM_UI_KEYS:
            if key in result and result[key] is not None:
                entry[key] = result[key]

    elif fn_name in {"post_food_listing", "create_food_listing"}:
        for key in (
            "success", "title", "quantity", "unit", "category", "address",
            "community_name", "summary", "message", "listing_id", "image_url",
            "coords_lat", "coords_lng", "on_map", "error", "next_step",
            "suggested_community_name",
        ):
            if key in result and result[key] is not None:
                entry[key] = result[key]

    elif fn_name in {"cancel_claim", "confirm_claim", "create_reminder"}:
        for key in ("success", "title", "summary", "message", "listing_id", "claim_id"):
            if key in result and result[key] is not None:
                entry[key] = result[key]

    elif fn_name == "delete_listing":
        for key in (
            "success", "title", "titles", "summary", "message", "listing_id",
            "error", "ok", "deleted_count", "deleted", "failed_count", "failed",
            "delete_duplicates",
        ):
            if key in result and result[key] is not None:
                entry[key] = result[key]

    elif fn_name == "deactivate_listing":
        for key in ("success", "title", "summary", "message", "error", "ok"):
            if key in result and result[key] is not None:
                entry[key] = result[key]

    elif fn_name == "get_user_listings":
        listings = result.get("listings") or []
        if listings:
            entry["listings"] = [_trim_listing(row) for row in listings[:8]]
        if result.get("summary"):
            entry["summary"] = result["summary"]

    elif fn_name in {"update_food_listing", "update_listing", "edit_listing"}:
        listing = result.get("listing") or {}
        for key in (
            "success", "ok", "title", "previous_title", "listing_id",
            "updated_fields", "summary", "message", "error",
        ):
            if key in result and result[key] is not None:
                entry[key] = result[key]
        if listing:
            entry["listing"] = _trim_listing(listing)
            for key in _LISTING_UI_KEYS:
                if listing.get(key) is not None:
                    entry[key] = listing[key]

    return entry


def _strip_uuids(text: str) -> str:
    cleaned = _UUID_RE.sub("", text)
    cleaned = _LISTING_ID_RE.sub("", cleaned)
    cleaned = re.sub(r"\(\s*\)", "", cleaned)
    cleaned = re.sub(r"\bid:\s*,?\s*", "", cleaned, flags=re.I)
    return cleaned


def _strip_internal_refs(text: str) -> str:
    return _INTERNAL_TOOL_RE.sub("the app", text)


def _dedupe_search_prose(text: str, actions: list[dict]) -> str:
    """When search cards render below, drop redundant numbered lists from prose."""
    has_search = any(
        a.get("tool") == "search_food_near_user" and a.get("listings")
        for a in (actions or [])
    )
    if not has_search or not text:
        return text

    if not _NUMBERED_LINE_RE.findall(text):
        return text

    lines = []
    for line in text.splitlines():
        if _NUMBERED_LINE_RE.match(line):
            continue
        if re.match(r"^\s*[-•]\s+\*\*", line):
            continue
        lines.append(line)

    trimmed = "\n".join(lines).strip()
    return re.sub(r"\n{3,}", "\n\n", trimmed)


def polish_assistant_response(
    text: str,
    actions: Optional[list[dict]] = None,
    lang: str = "en",
) -> str:
    """Structural cleanup only — never inject canned phrases."""
    if not text:
        return text

    out = _strip_uuids(text)
    out = _strip_internal_refs(out)
    out = _dedupe_search_prose(out, actions or [])
    return re.sub(r"\n{3,}", "\n\n", out).strip()
