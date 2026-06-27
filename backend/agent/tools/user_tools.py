"""
User Profile Tools
===================

LangChain wrappers for user profile management.
"""

import logging
from typing import Dict, Any, Optional
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
async def get_user_profile(user_id: str) -> Dict[str, Any]:
    """
    Get user profile information.
    
    Args:
        user_id: User's UUID
    
    Returns:
        Dict with user profile data (name, address, dietary restrictions, etc.)
    """
    try:
        from backend.tools import _get_user_profile as original_get_profile
        
        result = await original_get_profile(user_id=user_id)
        return result
        
    except Exception as e:
        logger.error(f"Get user profile failed: {e}")
        return {
            "error": str(e),
            "user_id": user_id,
        }


@tool
async def update_user_profile(
    user_id: str,
    name: Optional[str] = None,
    address: Optional[str] = None,
    phone: Optional[str] = None,
    dietary_restrictions: Optional[list] = None,
    allergies: Optional[list] = None,
) -> Dict[str, Any]:
    """
    Update user profile information.
    
    Args:
        user_id: User's UUID
        name: Optional new name
        address: Optional new address
        phone: Optional phone number
        dietary_restrictions: Optional dietary restrictions list
        allergies: Optional allergies list
    
    Returns:
        Dict with success status and updated profile
    """
    try:
        from backend.tools import _update_user_profile as original_update_profile
        
        result = await original_update_profile(
            user_id=user_id,
            name=name,
            address=address,
            phone=phone,
            dietary_restrictions=dietary_restrictions,
            allergies=allergies,
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Update user profile failed: {e}")
        return {
            "error": str(e),
            "success": False,
        }
