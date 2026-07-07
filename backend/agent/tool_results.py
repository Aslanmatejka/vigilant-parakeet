"""Normalize agent tool outputs to the legacy {tool, ok, summary, result} shape.

The frontend ``normalizeToolResults`` helper drops entries without a ``tool``
key. The legacy ``conversation_engine`` always wraps handler payloads; the
LangGraph agent previously returned raw dicts — this module bridges the gap.
"""

from __future__ import annotations

from typing import Any


def wrap_tool_result(tool_name: str, result: Any) -> dict[str, Any]:
    """Wrap a raw handler payload for API + UI consumption."""
    if not isinstance(result, dict):
        return {
            "tool": tool_name or "unknown",
            "ok": False,
            "summary": str(result)[:240] if result is not None else None,
            "result": {"raw": result},
        }

    if result.get("tool") and "ok" in result:
        entry = dict(result)
        if "result" not in entry or not isinstance(entry.get("result"), dict):
            nested = {
                k: v for k, v in entry.items()
                if k not in {"tool", "ok", "summary", "result"}
            }
            if nested:
                entry["result"] = nested
        return entry

    name = tool_name or result.get("tool") or "unknown"
    err_val = result.get("error")
    if err_val or result.get("success") is False or result.get("created") is False:
        ok = False
    elif result.get("requires_user_input") or result.get("skipped"):
        ok = True
    elif result.get("success") is True or result.get("created") is True:
        ok = True
    elif result.get("listings") is not None or result.get("claims") is not None:
        ok = True
    else:
        ok = not bool(err_val)

    summary = result.get("summary") or result.get("message")
    if not summary and isinstance(err_val, str):
        summary = err_val[:240]

    entry: dict[str, Any] = {
        "tool": name,
        "ok": bool(ok),
        "summary": summary,
        "result": result,
    }

    for extra_key in (
        "action", "target", "view", "focus", "path", "listing_id", "lang",
        "target_id", "geometry", "origin", "destination", "verified",
        "claim_id", "receipt_id", "pending_action", "awaiting_confirmation",
        "question", "requires_user_input",
    ):
        if extra_key in result and result[extra_key] is not None:
            entry[extra_key] = result[extra_key]

    if isinstance(result.get("route"), dict):
        entry["route"] = result["route"]
    elif result.get("geometry"):
        entry["route"] = {
            "geometry": result.get("geometry"),
            "origin": result.get("origin"),
            "destination": result.get("destination"),
            "distance_km": result.get("distance_km"),
            "duration_text": result.get("duration_text"),
            "profile": result.get("profile"),
        }

    return entry


def normalize_tool_results(raw_results: list[Any]) -> list[dict[str, Any]]:
    """Ensure every entry in ``recent_tool_results`` is UI-safe."""
    normalized: list[dict[str, Any]] = []
    for item in raw_results or []:
        if not isinstance(item, dict):
            continue
        if item.get("tool") and "ok" in item:
            normalized.append(item)
            continue
        tool_name = item.get("tool") or "unknown"
        normalized.append(wrap_tool_result(tool_name, item))
    return normalized


def compact_actions_for_metadata(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mirror ``conversation_engine.chat`` metadata.actions compaction."""
    compact: list[dict[str, Any]] = []
    for a in (actions or [])[-8:]:
        if not isinstance(a, dict):
            continue
        res = a.get("result") or {}
        listings = res.get("listings") or res.get("results") or []
        compact_listings = []
        for item in (listings[:12] if isinstance(listings, list) else []):
            if not isinstance(item, dict):
                continue
            compact_listings.append({
                "id": item.get("id"),
                "title": item.get("title") or item.get("name"),
                "category": item.get("category"),
                "quantity": item.get("quantity"),
                "unit": item.get("unit"),
                "latitude": item.get("latitude") or item.get("lat"),
                "longitude": item.get("longitude") or item.get("lng"),
                "distance_km": item.get("distance_km"),
                "address": item.get("full_address") or item.get("address"),
                "listing_owner_id": item.get("listing_owner_id"),
            })
        entry_compact: dict[str, Any] = {
            "tool": a.get("tool"),
            "ok": a.get("ok"),
            "summary": (a.get("summary") or "")[:240],
            "success": bool(a.get("ok")),
            "listing_id": res.get("listing_id") or a.get("listing_id"),
            "claim_id": res.get("claim_id") or a.get("claim_id"),
            "receipt_id": res.get("receipt_id") or a.get("receipt_id"),
            "title": res.get("title"),
            "quantity": res.get("quantity"),
            "unit": res.get("unit"),
            "pickup_location": res.get("pickup_location"),
            "listings": compact_listings,
        }
        for k in ("action", "path", "target", "view", "focus", "target_id", "lang"):
            if a.get(k) is not None:
                entry_compact[k] = a[k]
        if isinstance(a.get("route"), dict):
            entry_compact["route"] = {
                "geometry": a["route"].get("geometry"),
                "origin": a["route"].get("origin"),
                "destination": a["route"].get("destination"),
                "distance_km": a["route"].get("distance_km"),
                "duration_text": a["route"].get("duration_text"),
                "profile": a["route"].get("profile"),
            }
        compact.append(entry_compact)
    return compact
