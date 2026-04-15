"""Stress tests for compound WHERE conditions in count/sum."""

import pytest

from worldseed.dsl.functions.aggregation import _matches_where, count, sum_property
from worldseed.engine.state_store import StateStore
from worldseed.models.entity import Entity


@pytest.fixture()
def store() -> StateStore:
    s = StateStore()
    s.add(
        Entity(
            id="a1",
            type="agent",
            _data={
                "location": "reactor",
                "infected": "true",
                "health": 80,
                "team": "red",
            },
        )
    )
    s.add(
        Entity(
            id="a2",
            type="agent",
            _data={
                "location": "reactor",
                "infected": "false",
                "health": 60,
                "team": "blue",
            },
        )
    )
    s.add(
        Entity(
            id="a3",
            type="agent",
            _data={
                "location": "hallway",
                "infected": "true",
                "health": 40,
                "team": "red",
            },
        )
    )
    s.add(
        Entity(
            id="a4",
            type="agent",
            _data={
                "location": "hallway",
                "infected": "false",
                "health": 100,
                "team": "blue",
            },
        )
    )
    return s


class TestSingleCondition:
    """Backward compatibility: single conditions still work."""

    def test_equals(self, store):
        assert count(store, "agent", where="location == reactor") == 2

    def test_not_equals(self, store):
        assert count(store, "agent", where="location != reactor") == 2

    def test_no_where(self, store):
        assert count(store, "agent") == 4


class TestCompoundAND:
    def test_two_conditions_both_true(self, store):
        """Agents in reactor AND infected."""
        result = count(store, "agent", where="location == reactor AND infected == true")
        assert result == 1  # only a1

    def test_two_conditions_one_false(self, store):
        """Agents in reactor AND blue team — a2 only."""
        result = count(store, "agent", where="location == reactor AND team == blue")
        assert result == 1  # only a2

    def test_two_conditions_no_match(self, store):
        """Agents in hallway AND red AND infected==false — none."""
        result = count(
            store,
            "agent",
            where="location == hallway AND infected == false AND team == red",
        )
        assert result == 0

    def test_three_conditions(self, store):
        """Three ANDs."""
        result = count(
            store,
            "agent",
            where="location == hallway AND infected == false AND team == blue",
        )
        assert result == 1  # only a4

    def test_not_equals_in_compound(self, store):
        """Agents NOT in reactor AND infected."""
        result = count(
            store,
            "agent",
            where="location != reactor AND infected == true",
        )
        assert result == 1  # only a3


class TestCompoundWithSum:
    def test_sum_with_compound(self, store):
        """Sum health of red team agents."""
        result = sum_property(store, "agent", "health", where="team == red")
        assert result == 120.0  # 80 + 40

    def test_sum_with_two_conditions(self, store):
        """Sum health of agents in reactor AND blue team."""
        result = sum_property(
            store,
            "agent",
            "health",
            where="location == reactor AND team == blue",
        )
        assert result == 60.0  # only a2

    def test_sum_no_match(self, store):
        result = sum_property(
            store,
            "agent",
            "health",
            where="location == bunker AND team == red",
        )
        assert result == 0.0


class TestMatchesWhere:
    """Direct tests on _matches_where helper."""

    def test_entity_match(self, store):
        entity = store.get("a1")
        assert _matches_where(entity, "location == reactor") is True
        assert _matches_where(entity, "location == hallway") is False

    def test_compound_match(self, store):
        entity = store.get("a1")
        assert _matches_where(entity, "location == reactor AND infected == true") is True
        assert _matches_where(entity, "location == reactor AND infected == false") is False

    def test_triple_compound(self, store):
        entity = store.get("a1")
        assert _matches_where(entity, "location == reactor AND infected == true AND team == red") is True
        assert _matches_where(entity, "location == reactor AND infected == true AND team == blue") is False
