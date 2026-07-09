"""Regression tests for Bearer-token verification on /api/ai/* routes.

Covers the three verification strategies used by `_auth_user_id_async`:

1. Local `JWT_SECRET` (HS256) — app-issued tokens from
   ``backend/app.py`` login flow.
2. `SUPABASE_JWT_SECRET` (HS256) — offline fast path for
   Supabase-issued tokens.
3. Supabase GoTrue REST fallback (`GET /auth/v1/user`) — used when
   `SUPABASE_JWT_SECRET` isn't set. This is the exact scenario that
   caused the "401 storm" bug: frontend sends a Supabase JWT but the
   backend only knew about its own local secret.

The `AI_REQUIRE_AUTH` env is set in conftest to "false" so these tests
patch state directly without a live TestClient. That's fine — we're
testing the verification helpers themselves.
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

import jwt
import pytest
from fastapi.security import HTTPAuthorizationCredentials

from backend.ai import routes as ai_routes


def _bearer(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def _mint_hs256(secret: str, sub: str, extra: dict | None = None) -> str:
    payload = {"sub": sub, "exp": int(time.time()) + 3600}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, secret, algorithm="HS256")


class TestLocalJwtSecret:
    """Tokens minted with our own JWT_SECRET must verify offline."""

    def test_valid_local_token_returns_sub(self):
        token = _mint_hs256(ai_routes.JWT_SECRET, "user-123")
        result = asyncio.run(ai_routes._auth_user_id_async(_bearer(token)))
        assert result == "user-123"

    def test_expired_local_token_returns_none(self):
        payload = {"sub": "user-123", "exp": int(time.time()) - 60}
        token = jwt.encode(payload, ai_routes.JWT_SECRET, algorithm="HS256")
        result = asyncio.run(ai_routes._auth_user_id_async(_bearer(token)))
        assert result is None

    def test_wrong_signature_returns_none(self):
        token = _mint_hs256("not-our-secret", "user-123")
        # Without a Supabase secret configured and no network fallback
        # patched, this should fail cleanly.
        with patch.object(ai_routes, "SUPABASE_JWT_SECRET", ""), \
             patch.object(ai_routes, "SUPABASE_URL", ""):
            result = asyncio.run(ai_routes._auth_user_id_async(_bearer(token)))
        assert result is None


class TestSupabaseJwtSecret:
    """When SUPABASE_JWT_SECRET is set, Supabase-issued tokens verify offline."""

    def test_supabase_secret_verifies_supabase_token(self):
        supa_secret = "supabase-project-jwt-secret-abcdef123456"
        token = _mint_hs256(
            supa_secret,
            "56e3c110-8e22-4756-b98e-02d2d5c81a36",
            extra={"aud": "authenticated", "role": "authenticated"},
        )
        with patch.object(ai_routes, "SUPABASE_JWT_SECRET", supa_secret):
            result = asyncio.run(ai_routes._auth_user_id_async(_bearer(token)))
        assert result == "56e3c110-8e22-4756-b98e-02d2d5c81a36"

    def test_supabase_secret_ignores_aud_claim(self):
        """Supabase tokens carry aud=`authenticated`. PyJWT would reject
        that by default; we must have disabled aud verification."""
        supa_secret = "supabase-project-jwt-secret-abcdef123456"
        token = _mint_hs256(supa_secret, "u-1", extra={"aud": "authenticated"})
        with patch.object(ai_routes, "SUPABASE_JWT_SECRET", supa_secret):
            assert asyncio.run(ai_routes._auth_user_id_async(_bearer(token))) == "u-1"


class TestSupabaseRestFallback:
    """When SUPABASE_JWT_SECRET is missing, we hit GoTrue for verification."""

    def setup_method(self):
        ai_routes._SUPABASE_TOKEN_CACHE.clear()

    def test_rest_fallback_returns_user_id_on_200(self):
        opaque_token = "supabase-issued-token-we-cannot-decode"

        async def fake_get(self, url, headers=None):  # noqa: ARG001
            class R:
                status_code = 200

                @staticmethod
                def json():
                    return {"id": "supabase-uuid-123", "email": "u@x.com"}
            return R()

        with patch.object(ai_routes, "SUPABASE_JWT_SECRET", ""), \
             patch.object(ai_routes, "SUPABASE_URL", "https://x.supabase.co"), \
             patch.object(ai_routes, "SUPABASE_ANON_KEY", "anon-key"), \
             patch("httpx.AsyncClient.get", new=fake_get):
            result = asyncio.run(ai_routes._auth_user_id_async(_bearer(opaque_token)))
        assert result == "supabase-uuid-123"

    def test_rest_fallback_returns_none_on_401(self):
        async def fake_get(self, url, headers=None):  # noqa: ARG001
            class R:
                status_code = 401

                @staticmethod
                def json():
                    return {"error": "invalid token"}
            return R()

        with patch.object(ai_routes, "SUPABASE_JWT_SECRET", ""), \
             patch.object(ai_routes, "SUPABASE_URL", "https://x.supabase.co"), \
             patch.object(ai_routes, "SUPABASE_ANON_KEY", "anon-key"), \
             patch("httpx.AsyncClient.get", new=fake_get):
            result = asyncio.run(ai_routes._auth_user_id_async(_bearer("bad-token")))
        assert result is None

    def test_rest_fallback_cached_across_calls(self):
        """A single GoTrue call should serve subsequent verifications
        within the TTL so we don't 401-storm the network on chat bursts."""
        calls = {"n": 0}

        async def fake_get(self, url, headers=None):  # noqa: ARG001
            calls["n"] += 1

            class R:
                status_code = 200

                @staticmethod
                def json():
                    return {"id": "cached-user"}
            return R()

        with patch.object(ai_routes, "SUPABASE_JWT_SECRET", ""), \
             patch.object(ai_routes, "SUPABASE_URL", "https://x.supabase.co"), \
             patch.object(ai_routes, "SUPABASE_ANON_KEY", "anon-key"), \
             patch("httpx.AsyncClient.get", new=fake_get):
            r1 = asyncio.run(ai_routes._auth_user_id_async(_bearer("tok-abc")))
            r2 = asyncio.run(ai_routes._auth_user_id_async(_bearer("tok-abc")))
            r3 = asyncio.run(ai_routes._auth_user_id_async(_bearer("tok-abc")))
        assert r1 == r2 == r3 == "cached-user"
        assert calls["n"] == 1, "expected token verification to be cached"


class TestRequireOwnerAsync:
    """`_require_owner` glues the token verification to the requested user_id."""

    def test_matching_local_token_accepted(self):
        token = _mint_hs256(ai_routes.JWT_SECRET, "u-1")
        # AI_REQUIRE_AUTH is "false" in test env, but ownership still checks.
        asyncio.run(ai_routes._require_owner(_bearer(token), "u-1"))

    def test_mismatched_local_token_403(self):
        from fastapi import HTTPException
        token = _mint_hs256(ai_routes.JWT_SECRET, "u-1")
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(ai_routes._require_owner(_bearer(token), "u-2"))
        assert exc_info.value.status_code == 403

    def test_supabase_rest_verified_token_accepted(self):
        async def fake_get(self, url, headers=None):  # noqa: ARG001
            class R:
                status_code = 200

                @staticmethod
                def json():
                    return {"id": "supa-99"}
            return R()

        with patch.object(ai_routes, "SUPABASE_JWT_SECRET", ""), \
             patch.object(ai_routes, "SUPABASE_URL", "https://x.supabase.co"), \
             patch.object(ai_routes, "SUPABASE_ANON_KEY", "anon-key"), \
             patch("httpx.AsyncClient.get", new=fake_get):
            ai_routes._SUPABASE_TOKEN_CACHE.clear()
            # Should not raise
            asyncio.run(ai_routes._require_owner(_bearer("opaque"), "supa-99"))
