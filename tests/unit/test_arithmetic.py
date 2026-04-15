"""Stress tests for extended arithmetic: +, -, %, //."""

import pytest

from worldseed.dsl.path_resolver import resolve
from worldseed.engine.state_store import StateStore
from worldseed.models.entity import Entity


@pytest.fixture()
def store() -> StateStore:
    s = StateStore()
    s.add(Entity(id="food", type="resource", _data={"quantity": 20}))
    s.add(Entity(id="table", type="game", _data={"pot": 150, "current_bet": 40}))
    s.add(Entity(id="alice", type="agent", _data={"chips": 500, "bet": 10, "seat": 3}))
    s.add(Entity(id="bob", type="agent", _data={"chips": 300, "bet": 20}))
    return s


@pytest.fixture()
def ctx() -> dict:
    return {"agent_id": "alice", "action_params": {"amount": 50}, "tick": 5}


class TestAddition:
    def test_literal_addition(self, store, ctx):
        assert resolve("5 + 3", store, ctx) == 8.0

    def test_property_addition(self, store, ctx):
        assert resolve("food.quantity + 10", store, ctx) == 30.0

    def test_two_properties(self, store, ctx):
        assert resolve("alice.chips + bob.chips", store, ctx) == 800.0

    def test_param_addition(self, store, ctx):
        assert resolve("$amount + 10", store, ctx) == 60.0


class TestSubtraction:
    def test_literal_subtraction(self, store, ctx):
        assert resolve("10 - 3", store, ctx) == 7.0

    def test_property_subtraction(self, store, ctx):
        assert resolve("table.current_bet - alice.bet", store, ctx) == 30.0

    def test_result_negative(self, store, ctx):
        assert resolve("3 - 10", store, ctx) == -7.0

    def test_negative_literal_not_arithmetic(self, store, ctx):
        """A leading minus is a negative number, not subtraction."""
        result = resolve("-5", store, ctx)
        assert result == -5


class TestFloorDivision:
    def test_basic(self, store, ctx):
        assert resolve("10 // 3", store, ctx) == 3.0

    def test_exact(self, store, ctx):
        assert resolve("10 // 5", store, ctx) == 2.0

    def test_property(self, store, ctx):
        assert resolve("table.pot // 40", store, ctx) == 3.0

    def test_division_by_zero(self, store, ctx):
        """Should return 0.0 gracefully, not crash."""
        assert resolve("10 // 0", store, ctx) == 0.0


class TestModulo:
    def test_basic(self, store, ctx):
        assert resolve("10 % 3", store, ctx) == 1.0

    def test_tick_modulo(self, store, ctx):
        """Common pattern: do something every N ticks."""
        assert resolve("$tick % 3", store, ctx) == 2.0  # tick=5, 5%3=2

    def test_seat_modulo(self, store, ctx):
        assert resolve("alice.seat % 2", store, ctx) == 1.0  # 3%2=1

    def test_modulo_by_zero(self, store, ctx):
        assert resolve("10 % 0", store, ctx) == 0.0


class TestPrecedence:
    def test_add_multiply(self, store, ctx):
        """* binds tighter than +."""
        assert resolve("2 + 3 * 4", store, ctx) == 14.0

    def test_subtract_multiply(self, store, ctx):
        assert resolve("10 - 2 * 3", store, ctx) == 4.0

    def test_multiply_before_add(self, store, ctx):
        assert resolve("3 * 4 + 2", store, ctx) == 14.0

    def test_multiple_additions(self, store, ctx):
        assert resolve("1 + 2 + 3", store, ctx) == 6.0


class TestWithFunctions:
    def test_count_plus_literal(self, store, ctx):
        result = resolve("count(type=agent) + 1", store, ctx)
        assert result == 3.0  # 2 agents + 1

    def test_count_times_literal(self, store, ctx):
        result = resolve("0.1 * count(type=agent)", store, ctx)
        assert result == pytest.approx(0.2)

    def test_complex_expression(self, store, ctx):
        """table.pot // count(type=agent) = 150 // 2 = 75."""
        result = resolve("table.pot // count(type=agent)", store, ctx)
        assert result == 75.0


class TestMultiplication:
    def test_still_works(self, store, ctx):
        """Existing * multiplication must not break."""
        assert resolve("0.1 * food.quantity", store, ctx) == pytest.approx(2.0)

    def test_with_function(self, store, ctx):
        assert resolve("0.05 * table.pot", store, ctx) == pytest.approx(7.5)
