"""
AGENT_V2 — Destructive-intent interception tests
================================================

Verifies `pending_intercept.build_intercepted_action` returns the right
action envelope for each destructive intent + world-snapshot combo, and
`format_intercept_text` / `build_pending_action_envelope` shape the
frontend-facing payload correctly.

Run:
    python -m pytest backend/tests/test_agent_v2_intercept.py -v
"""

from __future__ import annotations

import pytest

from backend.agent.pending_intercept import (
    build_intercepted_action,
    build_pending_action_envelope,
    format_intercept_text,
    _MIN_INTERCEPT_CONFIDENCE,
)


# ============================================================================
# Helpers
# ============================================================================

def _world(**over):
    """Duck-typed snapshot as a plain dict — pending_intercept uses _get_attr."""
    base = {
        "user_id": "u1",
        "communities": [],
        "open_claims": [],
        "open_claims_count": 0,
        "open_listings": [],
        "open_listings_count": 0,
    }
    base.update(over)
    return base


# ============================================================================
# leave_community
# ============================================================================

class TestLeaveCommunity:
    def test_intercepts_with_community_name(self):
        ia = build_intercepted_action(
            intent="leave_community",
            confidence=0.9,
            world_snapshot=_world(communities=["Mission Hub"]),
        )
        assert ia is not None
        assert ia.tool == "leave_community"
        assert ia.args == {}
        assert "Mission Hub" in ia.summary_en
        assert "Mission Hub" in ia.summary_es

    def test_intercepts_without_community_name(self):
        ia = build_intercepted_action(
            intent="leave_community",
            confidence=0.9,
            world_snapshot=_world(),
        )
        assert ia is not None
        assert ia.tool == "leave_community"
        assert ia.args == {}
        assert ia.summary_en

    def test_skipped_when_confidence_too_low(self):
        ia = build_intercepted_action(
            intent="leave_community",
            confidence=_MIN_INTERCEPT_CONFIDENCE - 0.01,
            world_snapshot=_world(),
        )
        assert ia is None


# ============================================================================
# forget_about_me
# ============================================================================

class TestForgetAboutMe:
    def test_zero_arg_intercept(self):
        ia = build_intercepted_action(
            intent="forget_about_me",
            confidence=0.95,
            world_snapshot=_world(),
        )
        assert ia is not None
        assert ia.tool == "forget_about_me"
        assert ia.args == {}


# ============================================================================
# cancel_claim
# ============================================================================

class TestCancelClaim:
    def test_intercepts_when_exactly_one_open_claim(self):
        ia = build_intercepted_action(
            intent="cancel_claim",
            confidence=0.85,
            world_snapshot=_world(
                open_claims=[{
                    "id": "claim-abc",
                    "food_listings": {"title": "Sourdough loaf"},
                }],
                open_claims_count=1,
            ),
        )
        assert ia is not None
        assert ia.tool == "cancel_claim"
        assert ia.args == {"claim_id": "claim-abc"}
        assert "Sourdough loaf" in ia.summary_en

    def test_skipped_when_zero_open_claims(self):
        ia = build_intercepted_action(
            intent="cancel_claim",
            confidence=0.9,
            world_snapshot=_world(),
        )
        assert ia is None

    def test_skipped_when_multiple_open_claims(self):
        ia = build_intercepted_action(
            intent="cancel_claim",
            confidence=0.9,
            world_snapshot=_world(
                open_claims=[
                    {"id": "c1"},
                    {"id": "c2"},
                ],
                open_claims_count=2,
            ),
        )
        assert ia is None


# ============================================================================
# delete_listing
# ============================================================================

class TestDeleteListing:
    def test_intercepts_when_exactly_one_open_listing(self):
        ia = build_intercepted_action(
            intent="delete_listing",
            confidence=0.9,
            world_snapshot=_world(
                open_listings=[{"id": "listing-xyz", "title": "Extra pears"}],
                open_listings_count=1,
            ),
        )
        assert ia is not None
        assert ia.tool == "delete_listing"
        assert ia.args == {"listing_id": "listing-xyz", "confirmed": True}
        assert "Extra pears" in ia.summary_en

    def test_skipped_when_multiple(self):
        ia = build_intercepted_action(
            intent="delete_listing",
            confidence=0.9,
            world_snapshot=_world(
                open_listings=[{"id": "l1"}, {"id": "l2"}],
                open_listings_count=2,
            ),
        )
        assert ia is None


# ============================================================================
# Non-destructive intents pass through
# ============================================================================

class TestPassThrough:
    @pytest.mark.parametrize("intent", [
        "find_food", "search", "share_food", "claim_food", "greeting", "",
    ])
    def test_non_destructive_intents_never_intercepted(self, intent):
        ia = build_intercepted_action(
            intent=intent,
            confidence=1.0,
            world_snapshot=_world(open_listings=[{"id": "x"}], open_listings_count=1),
        )
        assert ia is None


# ============================================================================
# Envelope + text formatters
# ============================================================================

class TestEnvelope:
    def test_envelope_shape(self):
        env = build_pending_action_envelope(
            pending_id="pend-1",
            tool="leave_community",
            args={},
            summary="Leave community: Mission Hub.",
            expires_at="2026-07-01T12:00:00+00:00",
        )
        assert env["pending_id"] == "pend-1"
        assert env["tool"] == "leave_community"
        assert env["summary"].startswith("Leave community")
        assert env["requires_confirmation"] is True
        assert env["expires_at"].startswith("2026-07-01")

    def test_format_intercept_text_english(self):
        ia = build_intercepted_action(
            intent="forget_about_me", confidence=0.9, world_snapshot=_world(),
        )
        assert ia is not None
        text = format_intercept_text(ia, language="en")
        assert "Confirm or cancel" in text

    def test_format_intercept_text_spanish(self):
        ia = build_intercepted_action(
            intent="forget_about_me", confidence=0.9, world_snapshot=_world(),
        )
        assert ia is not None
        text = format_intercept_text(ia, language="es")
        assert "Confirma o cancela" in text or "confirma" in text.lower()
