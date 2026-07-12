#!/usr/bin/env python3
"""Nightly job: mine procedural + antipattern rules from agent trajectories.

The v2 agent stack (backend/agent/procedural.py, backend/agent/procedural_store.py)
was retired when the AI runtime moved to backend/ai/. This script is now a
no-op wrapper kept for cron / task-scheduler compatibility so ops jobs that
still call it do not fail with a hard ImportError.

If you want to re-enable procedural rule mining, re-introduce the modules
(or a replacement) in backend/agent/ and restore the real implementation
here.

Usage:
    python scripts/mine_procedural_rules.py [--user-id UUID] [--persist]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mine_procedural_rules")


def main() -> None:
    parser = argparse.ArgumentParser(description="Mine agent procedural rules (retired)")
    parser.add_argument("--user-id", help="Mine for one user (default: skip)")
    parser.add_argument("--persist", action="store_true", help="Write to Supabase")
    args = parser.parse_args()

    logger.info(
        "procedural rule mining is disabled — backend/agent/procedural* modules "
        "were removed with the backend/ai/ refactor. Exiting cleanly (no-op)."
    )
    print(
        json.dumps(
            {
                "user_id": args.user_id,
                "persist": bool(args.persist),
                "status": "disabled",
                "reason": "backend/agent/procedural* modules removed",
                "procedural_rules": [],
                "antipattern_rules": [],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
