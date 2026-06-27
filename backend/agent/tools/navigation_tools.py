"""
Navigation Tools
=================

LangChain wrappers for UI navigation commands.
"""

import logging
from typing import Dict, Any
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
async def navigate_ui(action: str, path: str) -> Dict[str, Any]:
    """
    Navigate the user to a specific page in the app.
    
    Args:
        action: Navigation action (always "open_page")
        path: Page path (dashboard, find-food, share-food, profile, community, etc.)
    
    Returns:
        Dict with navigation instruction for frontend
    """
    try:
        from backend.tools import _navigate_ui as original_navigate
        
        result = await original_navigate(action=action, path=path)
        return result
        
    except Exception as e:
        logger.error(f"Navigation failed: {e}")
        return {
            "error": str(e),
            "action": action,
            "path": path,
            "success": False,
        }
