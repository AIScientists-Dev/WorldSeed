"""Tests for DSL helper functions."""

from __future__ import annotations

from worldseed.dsl.functions import count, relationships_of
from worldseed.engine.state_store import StateStore
from worldseed.models import Entity


def _bunker_store() -> StateStore:
    """Create a minimal bunker state for testing."""
    store = StateStore()
    store.add(
        Entity(
            id="sleeping_quarters",
            type="space",
            _data={
                "description": "Shared sleeping area",
                "connects_to": ["hallway"],
            },
        )
    )
    store.add(
        Entity(
            id="hallway",
            type="space",
            _data={
                "description": "Central corridor",
                "connects_to": ["storage_room", "sleeping_quarters", "entrance"],
            },
        )
    )
    store.add(
        Entity(
            id="storage_room",
            type="space",
            _data={
                "description": "Supply storage room",
                "connects_to": ["hallway"],
            },
        )
    )
    store.add(
        Entity(
            id="entrance",
            type="space",
            _data={
                "description": "Heavy metal door",
                "connects_to": ["hallway"],
            },
        )
    )
    store.add(
        Entity(
            id="food_supply",
            type="resource",
            _data={
                "quantity": 20,
                "unit": "person-days",
                "located_in": ["storage_room"],
            },
        )
    )
    store.add(
        Entity(
            id="old_chen",
            type="agent",
            _data={"location": "sleeping_quarters", "private_stash": 0},
        )
    )
    store.add(
        Entity(
            id="xiao_li",
            type="agent",
            _data={"location": "sleeping_quarters"},
        )
    )
    store.add(
        Entity(
            id="doctor_wang",
            type="agent",
            _data={"location": "hallway"},
        )
    )
    return store


class TestRelationshipsOf:
    def test_single_connection(self) -> None:
        store = _bunker_store()
        result = relationships_of("sleeping_quarters", "connects_to", store)
        assert result == ["hallway"]

    def test_multiple_connections(self) -> None:
        store = _bunker_store()
        result = relationships_of("hallway", "connects_to", store)
        assert set(result) == {"storage_room", "sleeping_quarters", "entrance"}

    def test_nonexistent_entity(self) -> None:
        store = _bunker_store()
        assert relationships_of("ghost", "connects_to", store) == []

    def test_no_matching_type(self) -> None:
        store = _bunker_store()
        assert relationships_of("hallway", "trusts", store) == []


class TestCount:
    def test_count_agents(self) -> None:
        store = _bunker_store()
        assert count(store, "agent") == 3

    def test_count_with_where(self) -> None:
        store = _bunker_store()
        result = count(
            store,
            "agent",
            where="location == sleeping_quarters",
        )
        assert result == 2

    def test_count_no_match(self) -> None:
        store = _bunker_store()
        result = count(
            store,
            "agent",
            where="location == storage_room",
        )
        assert result == 0
