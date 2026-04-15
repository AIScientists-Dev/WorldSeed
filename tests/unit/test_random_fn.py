"""Stress tests for random() DSL function."""

import pytest

from worldseed.dsl.path_resolver import resolve
from worldseed.engine.state_store import StateStore
from worldseed.models.entity import Entity


@pytest.fixture()
def store() -> StateStore:
    s = StateStore()
    s.add(Entity(id="a1", type="agent", _data={"hp": 100}))
    s.add(Entity(id="a2", type="agent", _data={"hp": 80}))
    s.add(Entity(id="a3", type="agent", _data={"hp": 60}))
    return s


@pytest.fixture()
def ctx() -> dict:
    return {"agent_id": "a1", "action_params": {}, "tick": 1}


class TestRandomBasic:
    def test_in_range(self, store, ctx):
        """All results should be within [1, 6]."""
        results = set()
        for _ in range(200):
            val = resolve("random(1, 6)", store, ctx)
            assert 1 <= val <= 6
            results.add(val)
        # Should hit most values across 200 rolls
        assert len(results) >= 4

    def test_same_min_max(self, store, ctx):
        """random(5, 5) should always return 5."""
        for _ in range(20):
            assert resolve("random(5, 5)", store, ctx) == 5

    def test_returns_integer(self, store, ctx):
        val = resolve("random(1, 100)", store, ctx)
        assert isinstance(val, int)


class TestRandomWithExpressions:
    def test_with_count(self, store, ctx):
        """random(1, count(type=agent)) → [1, 3]."""
        results = set()
        for _ in range(100):
            val = resolve("random(1, count(type=agent))", store, ctx)
            assert 1 <= val <= 3
            results.add(val)
        assert len(results) >= 2

    def test_with_property(self, store, ctx):
        """random(1, a1.hp) → [1, 100]."""
        val = resolve("random(1, a1.hp)", store, ctx)
        assert 1 <= val <= 100


class TestRandomInArithmetic:
    def test_random_times_ten(self, store, ctx):
        """random(1, 6) * 10 → [10, 60]."""
        results = set()
        for _ in range(100):
            val = resolve("random(1, 6) * 10", store, ctx)
            assert 10 <= val <= 60
            assert val % 10 == 0
            results.add(val)
        assert len(results) >= 3

    def test_random_plus_base(self, store, ctx):
        """5 + random(1, 3) → [6, 8]."""
        results = set()
        for _ in range(100):
            val = resolve("5 + random(1, 3)", store, ctx)
            assert 6 <= val <= 8
            results.add(val)
        assert len(results) >= 2


class TestRandomEdgeCases:
    def test_bad_args_returns_zero(self, store, ctx):
        """random() with no args — regex won't match empty parens, returns string."""
        result = resolve("random()", store, ctx)
        # Empty parens don't match the function regex, so returns as-is
        assert result == "random()"

    def test_single_arg_returns_zero(self, store, ctx):
        result = resolve("random(5)", store, ctx)
        # Single arg: _call_random gets "5", parts < 2, returns 0
        assert result == 0
