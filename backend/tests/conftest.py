"""
Shared pytest configuration for backend integration tests.

Sets hermetic environment variables BEFORE any backend module is
imported so tests never touch the real MySQL database, Twilio, OpenAI,
or Mapbox. Mirrors ``backend/ai/tests/conftest.py`` — the two suites
have different roots but the AI routes are shared, so both must gate
off strict production auth.
"""
from __future__ import annotations

import os
import pathlib
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Neutralise outbound integrations — MUST be set BEFORE backend imports.
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("MAPBOX_TOKEN", "")
os.environ.setdefault("TWILIO_ACCOUNT_SID", "")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "")
os.environ.setdefault("AI_BROADCAST_AUTO_APPROVE", "0")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("PUBLIC_BASE_URL", "http://testserver")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-not-for-production-use")

# Tests exercise route logic without minting real Supabase JWTs, so
# gate off the strict auth enforcement (see ``_require_owner`` /
# ``_require_authenticated`` in ``backend/ai/routes.py``). Production
# leaves ``AI_REQUIRE_AUTH`` unset, which defaults to True.
os.environ.setdefault("AI_REQUIRE_AUTH", "false")
