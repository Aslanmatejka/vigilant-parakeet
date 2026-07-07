"""
Navigation Tools
=================

LangChain wrappers for UI navigation commands.
"""

import logging
from typing import Dict, Any, Optional
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
async def navigate_ui(action: str, path: Optional[str] = None) -> Dict[str, Any]:
    """
    Navigate the user to a specific page in the app.
    
    Args:
        action: Navigation action (navigate, open_map, open_page, etc.)
        path: Page path when action is navigate (dashboard, find, share, etc.)
    
    Returns:
        Dict with navigation instruction for frontend
    """
    try:
        from backend.tools import _navigate_ui as original_navigate
        
        kwargs: Dict[str, Any] = {"action": action}
        if path is not None:
            kwargs["path"] = path
        result = await original_navigate(**kwargs)
        return result
        
    except Exception as e:
        logger.error(f"Navigation failed: {e}")
        return {
            "error": str(e),
            "action": action,
            "path": path,
            "success": False,
        }
