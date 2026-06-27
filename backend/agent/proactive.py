"""
Proactive Suggestion Engine
============================

Generates context-aware suggestions to help users take action.

Suggestion types:
- Reminders: Unclaimed pickups approaching deadline
- Opportunities: New food matching user preferences
- Tips: Profile completion, app features
- Milestones: Impact achievements (50 meals shared!)

Cooldown logic prevents spam (max 1 suggestion per session).
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone

from backend.agent.state import ProactiveSuggestion

logger = logging.getLogger(__name__)


async def generate_proactive_suggestions(
    user_id: str,
    user_context: Dict[str, Any],
    recent_intent: Optional[str] = None,
) -> List[ProactiveSuggestion]:
    """
    Generate proactive suggestions based on user context.
    
    Args:
        user_id: User's UUID
        user_context: User profile and activity
        recent_intent: Recently classified intent (avoid suggesting same thing)
    
    Returns:
        List of ProactiveSuggestion objects, sorted by priority
    """
    logger.info(f"Generating proactive suggestions for user {user_id}")
    
    suggestions = []
    
    # Check for upcoming pickups
    pickup_suggestions = await _check_upcoming_pickups(user_id)
    suggestions.extend(pickup_suggestions)
    
    # Check for profile completeness
    if not user_context.get("address"):
        suggestions.append(ProactiveSuggestion(
            type="tip",
            message="💡 Add your address to find food near you",
            priority="medium",
            action_required=True,
            action_label="Set location",
        ))
    
    # Check for new food matching preferences
    if recent_intent != "search":
        new_food_suggestions = await _check_new_food(user_id, user_context)
        suggestions.extend(new_food_suggestions)
    
    # Check for impact milestones
    milestone_suggestions = await _check_milestones(user_id)
    suggestions.extend(milestone_suggestions)
    
    # Sort by priority (high → medium → low)
    priority_order = {"high": 0, "medium": 1, "low": 2}
    suggestions.sort(key=lambda s: priority_order.get(s.get("priority", "low"), 2))
    
    # Return top 2 suggestions to avoid overwhelming user
    return suggestions[:2]


async def _check_upcoming_pickups(user_id: str) -> List[ProactiveSuggestion]:
    """Check for unclaimed pickups with approaching deadlines."""
    suggestions = []
    
    try:
        from backend.ai_engine import supabase_get
        
        # Get approved claims with pickup dates in next 24 hours
        tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        claims = await supabase_get("food_claims", {
            "claimer_id": f"eq.{user_id}",
            "status": "eq.approved",
            "pickup_date": f"gte.{today}",
            "pickup_date": f"lte.{tomorrow}",
            "select": "id,food_id,pickup_date,pickup_time",
            "limit": "5",
        })
        
        for claim in claims:
            food_id = claim.get("food_id")
            pickup_date = claim.get("pickup_date")
            pickup_time = claim.get("pickup_time", "")
            
            # Get food title
            food_rows = await supabase_get("food_listings", {
                "id": f"eq.{food_id}",
                "select": "title",
            })
            food_title = food_rows[0].get("title", "your claimed food") if food_rows else "your claimed food"
            
            suggestions.append(ProactiveSuggestion(
                type="reminder",
                message=f"🍎 Don't forget to pick up {food_title} on {pickup_date} {pickup_time}",
                priority="high",
                action_required=True,
                action_label="Get directions",
            ))
        
    except Exception as e:
        logger.error(f"Failed to check upcoming pickups: {e}")
    
    return suggestions


async def _check_new_food(user_id: str, user_context: Dict[str, Any]) -> List[ProactiveSuggestion]:
    """Check for new food listings matching user preferences."""
    suggestions = []
    
    try:
        from backend.ai_engine import supabase_get
        
        # Get food posted in last 2 hours near user
        two_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        
        listings = await supabase_get("food_listings", {
            "status": "in.(approved,active)",
            "created_at": f"gte.{two_hours_ago}",
            "listing_type": "eq.donation",
            "select": "id,title,category,quantity,unit",
            "limit": "10",
        })
        
        # Check if any match user preferences (learned from backend.agent.learning)
        # For now, just notify if there are new listings
        if len(listings) > 0:
            suggestions.append(ProactiveSuggestion(
                type="opportunity",
                message=f"🆕 {len(listings)} new food listing(s) just posted in your area",
                priority="medium",
                action_required=False,
                action_label="View listings",
            ))
        
    except Exception as e:
        logger.error(f"Failed to check new food: {e}")
    
    return suggestions


async def _check_milestones(user_id: str) -> List[ProactiveSuggestion]:
    """Check for impact milestones."""
    suggestions = []
    
    try:
        from backend.ai_engine import supabase_get
        
        # Count total food claimed
        claims = await supabase_get("food_claims", {
            "claimer_id": f"eq.{user_id}",
            "status": "in.(approved,completed,confirmed)",
            "select": "id",
        })
        
        total_claims = len(claims)
        
        # Milestone thresholds
        milestones = {
            5: "🎉 You've claimed 5 food items! You're making a difference.",
            10: "🌟 10 claims! You're a food-saving champion!",
            25: "🏆 Amazing! 25 food items claimed. You've prevented serious food waste.",
            50: "💚 WOW! 50 claims. You're a community hero!",
        }
        
        if total_claims in milestones:
            suggestions.append(ProactiveSuggestion(
                type="milestone",
                message=milestones[total_claims],
                priority="low",
                action_required=False,
                action_label=None,
            ))
        
    except Exception as e:
        logger.error(f"Failed to check milestones: {e}")
    
    return suggestions


def should_show_suggestion(
    suggestion: ProactiveSuggestion,
    last_shown_at: Optional[str],
    cooldown_hours: int = 4,
) -> bool:
    """
    Check if a suggestion should be shown based on cooldown.
    
    Args:
        suggestion: Suggestion to check
        last_shown_at: ISO timestamp of last time a suggestion was shown
        cooldown_hours: Minimum hours between suggestions
    
    Returns:
        True if suggestion should be shown
    """
    if not last_shown_at:
        return True
    
    try:
        last_shown = datetime.fromisoformat(last_shown_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        elapsed = now - last_shown
        
        # High-priority suggestions (pickups) bypass cooldown
        if suggestion.get("priority") == "high":
            return True
        
        # Other suggestions respect cooldown
        return elapsed > timedelta(hours=cooldown_hours)
        
    except Exception as e:
        logger.error(f"Cooldown check failed: {e}")
        return False
