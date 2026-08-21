"""Load/save accessibility profile in user_preferences.preferences JSONB."""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("ai_accessibility")

ACCESSIBILITY_PREF_KEY = "accessibility"


def merge_accessibility_profiles(
    stored: Optional[dict],
    incoming: Optional[dict],
) -> Optional[dict]:
    """Merge stored + incoming accessibility settings (incoming wins)."""
    if not stored and not incoming:
        return None
    merged: dict[str, Any] = {}
    if isinstance(stored, dict):
        merged.update(stored)
    if isinstance(incoming, dict):
        merged.update(incoming)
    return merged or None


async def load_accessibility_profile(user_id: str) -> Optional[dict]:
    if not user_id:
        return None
    try:
        from backend.agent.learning import get_user_preferences

        prefs = await get_user_preferences(user_id)
        block = prefs.get(ACCESSIBILITY_PREF_KEY)
        return block if isinstance(block, dict) else None
    except Exception as exc:
        logger.debug("load_accessibility_profile failed (non-fatal): %s", exc)
        return None


async def save_accessibility_profile(user_id: str, profile: dict) -> None:
    if not user_id or not isinstance(profile, dict) or not profile:
        return
    try:
        from backend.ai_engine import supabase_get, supabase_post, supabase_patch

        pref_rows = await supabase_get("user_preferences", {
            "user_id": f"eq.{user_id}",
            "select": "id,preferences",
        })
        if pref_rows:
            row = pref_rows[0]
            prefs = row.get("preferences") or {}
            if not isinstance(prefs, dict):
                prefs = {}
            prefs[ACCESSIBILITY_PREF_KEY] = profile
            await supabase_patch(
                "user_preferences",
                {"id": f"eq.{row['id']}"},
                {"preferences": prefs},
            )
        else:
            await supabase_post("user_preferences", {
                "user_id": user_id,
                "preferences": {ACCESSIBILITY_PREF_KEY: profile},
            })
    except Exception as exc:
        logger.debug("save_accessibility_profile failed (non-fatal): %s", exc)


def preferred_language_from_profile(profile: Optional[dict]) -> Optional[str]:
    if not profile or not isinstance(profile, dict):
        return None
    lang = profile.get("preferredLanguage") or profile.get("language")
    if isinstance(lang, str) and lang.strip():
        return lang.strip().lower()
    return None
