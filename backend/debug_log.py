"""No-op debug logger stub (agent session logs removed for production)."""
from __future__ import annotations

from typing import Any, Optional


def agent_debug_log(
    location: str,
    message: str,
    data: Optional[dict[str, Any]] = None,
    *,
    hypothesis_id: str = "",
    run_id: str = "pre-fix",
) -> None:
    return
