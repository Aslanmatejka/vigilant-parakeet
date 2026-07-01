"""
AGENT_V2 — Rollout tests
========================

Verify the per-user rollout gate behaves correctly across the master
switch (AGENT_V2) and the percentage knob (AGENT_V2_ROLLOUT_PCT).

Run:
    python -m pytest backend/tests/test_agent_v2_rollout.py -v
"""

from __future__ import annotations

import os

import pytest

from backend.agent.rollout import (
    bucket_for_user,
    is_agent_v2_enabled_for_user,
    is_agent_v2_globally_enabled,
    rollout_percentage,
    rollout_snapshot,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # Clear both knobs so each test starts from a clean slate.
    monkeypatch.delenv("AGENT_V2", raising=False)
    monkeypatch.delenv("AGENT_V2_ROLLOUT_PCT", raising=False)
    yield


NIL_UUID = "00000000-0000-0000-0000-000000000000"
USER_A = "11111111-2222-3333-4444-555555555555"
USER_B = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


class TestBucketing:
    def test_bucket_range(self):
        assert 0 <= bucket_for_user(USER_A) < 100
        assert 0 <= bucket_for_user(USER_B) < 100

    def test_bucket_stable(self):
        assert bucket_for_user(USER_A) == bucket_for_user(USER_A)

    def test_bucket_distinct_for_distinct_ids(self):
        # Not strictly guaranteed, but astronomically likely with md5.
        assert bucket_for_user(USER_A) != bucket_for_user(USER_B)

    def test_empty_bucket_is_out_of_range(self):
        # Empty / missing ids get 100 which is outside every valid pct.
        assert bucket_for_user("") == 100
        assert bucket_for_user(None) == 100


class TestMasterSwitch:
    def test_off_by_default(self):
        assert is_agent_v2_globally_enabled() is False
        assert is_agent_v2_enabled_for_user(USER_A) is False

    def test_on_flag_variants(self, monkeypatch):
        for val in ("true", "1", "yes", "on", "TRUE"):
            monkeypatch.setenv("AGENT_V2", val)
            assert is_agent_v2_globally_enabled() is True


class TestRolloutPercentage:
    def test_default_is_100(self):
        assert rollout_percentage() == 100

    def test_bounded(self, monkeypatch):
        monkeypatch.setenv("AGENT_V2_ROLLOUT_PCT", "-42")
        assert rollout_percentage() == 0
        monkeypatch.setenv("AGENT_V2_ROLLOUT_PCT", "999")
        assert rollout_percentage() == 100

    def test_garbage_falls_back(self, monkeypatch):
        monkeypatch.setenv("AGENT_V2_ROLLOUT_PCT", "not-a-number")
        assert rollout_percentage() == 100


class TestRoutingDecision:
    def test_anonymous_never_v2(self, monkeypatch):
        monkeypatch.setenv("AGENT_V2", "true")
        monkeypatch.setenv("AGENT_V2_ROLLOUT_PCT", "100")
        assert is_agent_v2_enabled_for_user(NIL_UUID) is False
        assert is_agent_v2_enabled_for_user(None) is False
        assert is_agent_v2_enabled_for_user("") is False

    def test_full_rollout(self, monkeypatch):
        monkeypatch.setenv("AGENT_V2", "true")
        monkeypatch.setenv("AGENT_V2_ROLLOUT_PCT", "100")
        assert is_agent_v2_enabled_for_user(USER_A) is True
        assert is_agent_v2_enabled_for_user(USER_B) is True

    def test_zero_rollout(self, monkeypatch):
        monkeypatch.setenv("AGENT_V2", "true")
        monkeypatch.setenv("AGENT_V2_ROLLOUT_PCT", "0")
        assert is_agent_v2_enabled_for_user(USER_A) is False
        assert is_agent_v2_enabled_for_user(USER_B) is False

    def test_partial_rollout_uses_bucket(self, monkeypatch):
        monkeypatch.setenv("AGENT_V2", "true")
        # Pick a percentage that splits our fixture users.
        bucket_a = bucket_for_user(USER_A)
        # Force pct exactly at bucket_a so USER_A is out but bucket_a-1 users are in.
        monkeypatch.setenv("AGENT_V2_ROLLOUT_PCT", str(bucket_a))
        assert is_agent_v2_enabled_for_user(USER_A) is False
        monkeypatch.setenv("AGENT_V2_ROLLOUT_PCT", str(bucket_a + 1))
        assert is_agent_v2_enabled_for_user(USER_A) is True

    def test_master_off_overrides_pct(self, monkeypatch):
        monkeypatch.setenv("AGENT_V2", "false")
        monkeypatch.setenv("AGENT_V2_ROLLOUT_PCT", "100")
        assert is_agent_v2_enabled_for_user(USER_A) is False


class TestSnapshot:
    def test_shape(self, monkeypatch):
        monkeypatch.setenv("AGENT_V2", "true")
        monkeypatch.setenv("AGENT_V2_ROLLOUT_PCT", "42")
        snap = rollout_snapshot()
        assert snap == {"enabled": True, "rollout_pct": 42}
