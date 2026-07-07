#!/usr/bin/env python3
"""Nightly job: mine procedural + antipattern rules and persist to Supabase.

Usage:
    python scripts/mine_procedural_rules.py [--user-id UUID] [--persist]

Without --persist, prints mined rules to stdout (dry run).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mine_procedural_rules")


async def _mine_for_user(user_id: str, *, persist: bool) -> dict:
    from backend.agent.procedural import (
        fetch_recent_trajectories,
        mine_antipatterns,
        mine_procedural_rules,
    )

    trajectories = await fetch_recent_trajectories(user_id, limit=50)
    rules = mine_procedural_rules(trajectories)
    antipatterns = mine_antipatterns(trajectories)

    if persist and (rules or antipatterns):
        from backend.agent.procedural_store import (
            upsert_antipattern_rules,
            upsert_procedural_rules,
        )
        await upsert_procedural_rules(user_id, rules)
        await upsert_antipattern_rules(user_id, antipatterns)

    return {
        "user_id": user_id,
        "trajectory_count": len(trajectories),
        "procedural_rules": [r.to_dict() for r in rules],
        "antipattern_rules": [a.to_dict() for a in antipatterns],
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Mine agent procedural rules")
    parser.add_argument("--user-id", help="Mine for one user (default: skip)")
    parser.add_argument("--persist", action="store_true", help="Write to Supabase")
    args = parser.parse_args()

    if not args.user_id:
        logger.info("No --user-id supplied; nothing to mine")
        return

    result = await _mine_for_user(args.user_id, persist=args.persist)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
