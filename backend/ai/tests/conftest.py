"""
Shared pytest configuration for FoodMaps AI tests.

Sets hermetic environment variables BEFORE any backend module is imported
so tests never touch the real MySQL database, Twilio, OpenAI, or Mapbox.
"""
from __future__ import annotations

import os
import sys
import pathlib

# Locate the project root (…/project) and make it importable
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Neutralise outbound integrations — these must be set BEFORE backend imports
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("MAPBOX_TOKEN", "")
os.environ.setdefault("TWILIO_ACCOUNT_SID", "")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "")
os.environ.setdefault("AI_BROADCAST_AUTO_APPROVE", "0")
# Provide an in-memory SQLite DB so backend.db / backend.app can import without
# requiring a real MySQL instance. Tests mock or stub DB calls themselves.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("PUBLIC_BASE_URL", "http://testserver")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-not-for-production-use")
# Tests exercise route logic without minting real Supabase JWTs, so
# gate off the strict auth enforcement (see `_require_owner` /
# `_require_authenticated` in backend/ai/routes.py). Production leaves
# `AI_REQUIRE_AUTH` unset which defaults to True.
os.environ.setdefault("AI_REQUIRE_AUTH", "false")

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Make sure per-IP rate-limiter state does not leak between tests."""
    from backend.ai import ai_engine
    ai_engine._rate_store.clear()
    yield
    ai_engine._rate_store.clear()
