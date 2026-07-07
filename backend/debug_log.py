"""Session-scoped NDJSON debug logger for agent debugging."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

_LOG_PATH = Path(__file__).resolve().parent.parent / "debug-4d1b71.log"
_SESSION_ID = "4d1b71"


def agent_debug_log(
    location: str,
    message: str,
    data: Optional[dict[str, Any]] = None,
    *,
    hypothesis_id: str = "",
    run_id: str = "pre-fix",
) -> None:
    # #region agent log
    try:
        payload = {
            "sessionId": _SESSION_ID,
            "location": location,
            "message": message,
            "data": data or {},
            "hypothesisId": hypothesis_id,
            "runId": run_id,
            "timestamp": int(time.time() * 1000),
        }
        with open(_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, default=str) + "\n")
    except Exception:
        pass
    # #endregion
