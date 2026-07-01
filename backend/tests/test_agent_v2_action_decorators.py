"""
AGENT_V2 — Decorator sugar tests
=================================

Verifies `@action`, `@rollback_for`, and `@fetch_before_for` register
callables into the same action registry that `register_action(...)` uses.

Run:
    python -m pytest backend/tests/test_agent_v2_action_decorators.py -v
"""

from __future__ import annotations

import asyncio

import pytest

from backend.agent import actions as actions_mod
from backend.agent.actions import (
    action,
    fetch_before_for,
    get_action,
    list_actions,
    register_action,
    rollback_for,
)


@pytest.fixture(autouse=True)
def _isolate_registry(monkeypatch):
    """Swap the module-level registry with a fresh dict per test so we
    can't leak test-only registrations into other test modules."""
    monkeypatch.setattr(actions_mod, "_REGISTRY", {})
    yield


class TestActionDecorator:
    def test_registers_handler(self):
        @action("__test_a", requires_confirmation=False,
                summary_template="Test A {x}")
        async def _handler(args, user_id):
            return ({"x": args.get("x")}, "test_table", "row-1")

        spec = get_action("__test_a")
        assert spec is not None
        assert spec.name == "__test_a"
        assert spec.requires_confirmation is False
        assert spec.summary_template == "Test A {x}"
        # Handler is left directly callable.
        result = asyncio.run(_handler({"x": 42}, "u1"))
        assert result == ({"x": 42}, "test_table", "row-1")

    def test_eager_rollback_and_fetch_before(self):
        async def _rb(_row): return True
        async def _fb(_args, _uid): return {"snapshot": "before"}

        @action("__test_b", rollback=_rb, fetch_before=_fb)
        async def _handler(args, user_id):
            return ({}, "t", "id")

        spec = get_action("__test_b")
        assert spec is not None
        assert spec.rollback is _rb
        assert spec.fetch_before is _fb


class TestRollbackForDecorator:
    def test_attaches_after_action_registered(self):
        @action("__test_c")
        async def _handler(args, user_id):
            return ({}, "t", None)

        @rollback_for("__test_c")
        async def _rb(_row):
            return True

        spec = get_action("__test_c")
        assert spec is not None
        assert spec.rollback is _rb

    def test_raises_when_action_missing(self):
        with pytest.raises(ValueError):
            @rollback_for("__never_registered")
            async def _rb(_row):
                return True

    def test_preserves_other_fields(self):
        @action("__test_d", requires_confirmation=True,
                summary_template="Do {thing}")
        async def _handler(args, user_id):
            return ({}, "t", None)

        @rollback_for("__test_d")
        async def _rb(_row):
            return True

        spec = get_action("__test_d")
        assert spec.summary_template == "Do {thing}"
        assert spec.requires_confirmation is True
        assert spec.rollback is _rb


class TestFetchBeforeForDecorator:
    def test_attaches_fetch_before(self):
        @action("__test_e")
        async def _handler(args, user_id):
            return ({}, "t", None)

        @fetch_before_for("__test_e")
        async def _fb(_args, _uid):
            return {"before": True}

        spec = get_action("__test_e")
        assert spec.fetch_before is _fb

    def test_raises_when_action_missing(self):
        with pytest.raises(ValueError):
            @fetch_before_for("__no_such_thing")
            async def _fb(_args, _uid):
                return {}


class TestParityWithRegisterAction:
    def test_decorator_and_functional_forms_produce_equivalent_spec(self):
        async def _h1(args, uid): return ({}, "t", None)

        @action("__parity_a", requires_confirmation=False,
                summary_template="s {y}")
        async def _h2(args, uid): return ({}, "t", None)

        register_action(
            "__parity_b",
            _h1,
            requires_confirmation=False,
            summary_template="s {y}",
        )

        a = get_action("__parity_a")
        b = get_action("__parity_b")
        assert a is not None and b is not None
        assert a.requires_confirmation == b.requires_confirmation
        assert a.summary_template == b.summary_template
        # Both should show up in list_actions.
        names = list_actions()
        assert "__parity_a" in names
        assert "__parity_b" in names
