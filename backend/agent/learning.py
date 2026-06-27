"""
User Preference Learning
=========================

Tracks and learns user preferences over time to improve suggestions.

Learns:
- Frequently searched food types
- Preferred communities
- Typical claim quantities
- Search radius preferences
- Conversation patterns

Stores preferences in Supabase `user_preferences` table (JSONB column).
"""

import logging
from typing import Dict, Any, List
from datetime import datetime, timezone
import json

logger = logging.getLogger(__name__)


async def update_user_preferences(
    user_id: str,
    intent: str,
    entities: Dict[str, Any],
    tool_results: List[Dict[str, Any]],
) -> None:
    """
    Update user preferences based on conversation.
    
    Args:
        user_id: User's UUID
        intent: Classified intent (search, claim, donate)
        entities: Extracted entities from message
        tool_results: Results from tool executions
    """
    logger.info(f"Updating preferences for user {user_id}, intent {intent}")
    
    try:
        from backend.ai_engine import supabase_get, supabase_post
        
        # Get existing preferences
        pref_rows = await supabase_get("user_preferences", {
            "user_id": f"eq.{user_id}",
            "select": "preferences",
        })
        
        if pref_rows:
            preferences = pref_rows[0].get("preferences", {})
        else:
            preferences = _get_default_preferences()
        
        # Update based on intent
        if intent == "search":
            preferences = _update_search_preferences(preferences, entities, tool_results)
        elif intent == "claim":
            preferences = _update_claim_preferences(preferences, entities, tool_results)
        elif intent == "donate":
            preferences = _update_donate_preferences(preferences, entities)
        
        # Save updated preferences
        if pref_rows:
            # Update existing
            from backend.ai_engine import SUPABASE_URL, SUPABASE_SERVICE_KEY
            import httpx
            
            async with httpx.AsyncClient(timeout=10) as client:
                await client.patch(
                    f"{SUPABASE_URL}/rest/v1/user_preferences?user_id=eq.{user_id}",
                    json={"preferences": preferences},
                    headers={
                        "apikey": SUPABASE_SERVICE_KEY,
                        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                        "Content-Type": "application/json",
                    },
                )
        else:
            # Create new
            await supabase_post("user_preferences", {
                "user_id": user_id,
                "preferences": preferences,
            })
        
        logger.info(f"Preferences updated for user {user_id}")
        
    except Exception as e:
        logger.error(f"Failed to update preferences: {e}")


def _get_default_preferences() -> Dict[str, Any]:
    """Get default preferences structure."""
    return {
        "food_types": {},  # {category: count}
        "search_radius": 10,  # Default km
        "communities": {},  # {community_id: count}
        "typical_quantities": {},  # {category: avg_quantity}
        "dietary_tags": [],
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "search_count": 0,
        "claim_count": 0,
        "donate_count": 0,
    }


def _update_search_preferences(
    preferences: Dict[str, Any],
    entities: Dict[str, Any],
    tool_results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Update preferences based on search behavior."""
    
    # Track searched food types
    food_type = entities.get("food_type")
    if food_type:
        food_types = preferences.get("food_types", {})
        food_types[food_type] = food_types.get(food_type, 0) + 1
        preferences["food_types"] = food_types
    
    # Track search radius
    radius = entities.get("radius")
    if radius:
        # Running average
        current_avg = preferences.get("search_radius", 10)
        search_count = preferences.get("search_count", 0)
        new_avg = (current_avg * search_count + radius) / (search_count + 1)
        preferences["search_radius"] = round(new_avg, 1)
    
    preferences["search_count"] = preferences.get("search_count", 0) + 1
    preferences["last_updated"] = datetime.now(timezone.utc).isoformat()
    
    return preferences


def _update_claim_preferences(
    preferences: Dict[str, Any],
    entities: Dict[str, Any],
    tool_results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Update preferences based on claim behavior."""
    
    # Track claimed quantities by category
    quantity = entities.get("quantity")
    category = entities.get("food_type")
    
    if quantity and category:
        typical_quantities = preferences.get("typical_quantities", {})
        if category in typical_quantities:
            # Running average
            current_avg = typical_quantities[category]
            count = typical_quantities.get(f"{category}_count", 1)
            new_avg = (current_avg * count + quantity) / (count + 1)
            typical_quantities[category] = round(new_avg, 2)
            typical_quantities[f"{category}_count"] = count + 1
        else:
            typical_quantities[category] = quantity
            typical_quantities[f"{category}_count"] = 1
        
        preferences["typical_quantities"] = typical_quantities
    
    preferences["claim_count"] = preferences.get("claim_count", 0) + 1
    preferences["last_updated"] = datetime.now(timezone.utc).isoformat()
    
    return preferences


def _update_donate_preferences(
    preferences: Dict[str, Any],
    entities: Dict[str, Any],
) -> Dict[str, Any]:
    """Update preferences based on donation behavior."""
    
    # Track donated food types
    food_type = entities.get("food_type")
    if food_type:
        food_types = preferences.get("donated_food_types", {})
        food_types[food_type] = food_types.get(food_type, 0) + 1
        preferences["donated_food_types"] = food_types
    
    preferences["donate_count"] = preferences.get("donate_count", 0) + 1
    preferences["last_updated"] = datetime.now(timezone.utc).isoformat()
    
    return preferences


async def get_user_preferences(user_id: str) -> Dict[str, Any]:
    """
    Fetch user preferences from database.
    
    Returns default preferences if none exist.
    """
    try:
        from backend.ai_engine import supabase_get
        
        pref_rows = await supabase_get("user_preferences", {
            "user_id": f"eq.{user_id}",
            "select": "preferences",
        })
        
        if pref_rows:
            return pref_rows[0].get("preferences", _get_default_preferences())
        else:
            return _get_default_preferences()
            
    except Exception as e:
        logger.error(f"Failed to fetch preferences: {e}")
        return _get_default_preferences()


def get_preferred_search_params(preferences: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract preferred search parameters from preferences.
    
    Used to pre-fill search queries with user's typical values.
    """
    # Get most frequently searched food type
    food_types = preferences.get("food_types", {})
    preferred_food_type = max(food_types, key=food_types.get) if food_types else None
    
    return {
        "radius_km": preferences.get("search_radius", 10),
        "food_type": preferred_food_type,
        "dietary_tags": preferences.get("dietary_tags", []),
    }
