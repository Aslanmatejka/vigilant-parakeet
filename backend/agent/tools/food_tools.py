"""
Food-Related Tools
===================

LangChain wrappers for food search, claim, and donation operations.
"""

import logging
from typing import Dict, Any, List, Optional
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
async def search_food_near_user(
    user_id: str,
    food_type: Optional[str] = None,
    radius_km: int = 10,
    dietary_tags: Optional[List[str]] = None,
    exclude_allergens: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Search for available food near the user.
    
    Args:
        user_id: User's UUID
        food_type: Optional food category filter (vegetables, bakery, prepared_meals, etc.)
        radius_km: Search radius in kilometers (default 10)
        dietary_tags: Optional dietary requirements (vegan, gluten_free, halal, kosher)
        exclude_allergens: Optional allergens to exclude (nuts, dairy, soy, eggs)
    
    Returns:
        Dict with available food listings
    """
    try:
        # Import the original function from backend.tools
        from backend.tools import _search_food_near_user as original_search
        
        # Call the original function
        result = await original_search(
            user_id=user_id,
            food_type=food_type,
            radius_km=radius_km,
            dietary_tags=dietary_tags or [],
            exclude_allergens=exclude_allergens or [],
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Food search failed: {e}")
        return {
            "error": str(e),
            "found": 0,
            "listings": [],
        }


@tool
async def claim_listing(
    user_id: str,
    listing_id: Optional[str] = None,
    food_id: Optional[str] = None,
    quantity: Optional[int] = None,
    quantity_requested: Optional[int] = None,
    pickup_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Claim a food listing.

    Args:
        user_id: User's UUID
        listing_id: Food listing UUID to claim
        food_id: Legacy alias for listing_id
        quantity: How many units to claim (default 1)
        quantity_requested: Legacy alias for quantity
        pickup_date: Optional pickup date (ISO YYYY-MM-DD)

    Returns:
        Dict with claim confirmation details
    """
    try:
        from backend.tools import _claim_food_listing as original_claim

        resolved_listing_id = listing_id or food_id
        resolved_quantity = quantity if quantity is not None else quantity_requested

        result = await original_claim(
            user_id=user_id,
            listing_id=resolved_listing_id,
            quantity=resolved_quantity,
            pickup_date=pickup_date,
        )

        return result

    except Exception as e:
        logger.error(f"Claim listing failed: {e}")
        return {
            "error": str(e),
            "success": False,
        }


@tool
async def post_food_listing(
    user_id: str,
    title: str,
    quantity: float,
    unit: str = "servings",
    category: str = "other",
    address: Optional[str] = None,
    location: Optional[str] = None,
    description: Optional[str] = None,
    expiry_date: Optional[str] = None,
    dietary_tags: Optional[List[str]] = None,
    allergens: Optional[List[str]] = None,
    community_name: Optional[str] = None,
    community_id: Optional[str] = None,
    community_confirmed: bool = False,
    image_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Post a food donation listing.
    
    Args:
        user_id: User's UUID
        title: Food title/description
        quantity: Amount available
        unit: Unit of measurement (servings, kg, pieces, etc.)
        category: Food category (vegetables, bakery, prepared_meals, etc.)
        address: Pickup address
        description: Optional detailed description
        expiry_date: Optional expiry date (ISO format)
        dietary_tags: Optional tags (vegan, gluten_free, halal, kosher)
        allergens: Optional allergen warnings (nuts, dairy, soy, eggs)
    
    Returns:
        Dict with listing confirmation details
    """
    try:
        from backend.tools import _create_food_listing as original_post
        
        result = await original_post(
            user_id=user_id,
            title=title,
            quantity=float(quantity),
            unit=unit or "servings",
            category=category or "other",
            location=location or address,
            description=description,
            expiry_date=expiry_date,
            dietary_tags=dietary_tags or [],
            allergens=allergens or [],
            community_name=community_name,
            community_id=community_id,
            community_confirmed=bool(community_confirmed),
            image_url=image_url,
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Post listing failed: {e}")
        return {
            "error": str(e),
            "success": False,
        }
