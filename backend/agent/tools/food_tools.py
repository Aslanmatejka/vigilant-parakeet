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
    food_id: str,
    quantity_requested: int = 1,
) -> Dict[str, Any]:
    """
    Claim a food listing.
    
    Args:
        user_id: User's UUID
        food_id: Food listing UUID to claim
        quantity_requested: Quantity to claim (default 1)
    
    Returns:
        Dict with claim confirmation details
    """
    try:
        from backend.tools import _claim_food_listing as original_claim
        
        result = await original_claim(
            user_id=user_id,
            food_id=food_id,
            quantity_requested=quantity_requested,
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
    quantity: int,
    unit: str,
    category: str,
    address: str,
    description: Optional[str] = None,
    expiry_date: Optional[str] = None,
    dietary_tags: Optional[List[str]] = None,
    allergens: Optional[List[str]] = None,
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
            quantity=quantity,
            unit=unit,
            category=category,
            address=address,
            description=description,
            expiry_date=expiry_date,
            dietary_tags=dietary_tags or [],
            allergens=allergens or [],
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Post listing failed: {e}")
        return {
            "error": str(e),
            "success": False,
        }
