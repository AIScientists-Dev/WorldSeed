"""Tests for DSL path resolver."""

from __future__ import annotations

from worldseed.dsl.path_resolver import resolve
from worldseed.engine.state_store import StateStore
from worldseed.models import Entity


def _bunker_store() -> StateStore:
    """Create a minimal bunker state for testing."""
    store = StateStore()
    store.add(
        Entity(
            id="sleeping_quarters",
            type="space",
            _data={"connects_to": ["hallway"]},
        )
    )
    store.add(
        Entity(
            id="hallway",
            type="space",
            _data={
                "connects_to": ["storage_room", "sleeping_quarters"],
            },
        )
    )
    store.add(
        Entity(
            id="storage_room",
            type="space",
            _data={"connects_to": ["hallway"]},
        )
    )
    store.add(
        Entity(
            id="food_supply",
            type="resource",
            _data={"quantity": 20},
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


def _ctx(agent_id: str = "old_chen", **params: object) -> dict:  # type: ignore[type-arg]
    return {"agent_id": agent_id, "action_params": params}


class TestResolveParam:
    def test_agent(self) -> None:
        store = _bunker_store()
        assert resolve("$agent", store, _ctx()) == "old_chen"

    def test_named_param(self) -> None:
        store = _bunker_store()
        assert resolve("$to", store, _ctx(to="hallway")) == "hallway"

    def test_numeric_param(self) -> None:
        store = _bunker_store()
        assert resolve("$amount", store, _ctx(amount=3)) == 3


class TestResolvePath:
    def test_agent_property(self) -> None:
        store = _bunker_store()
        result = resolve(
            "$agent.location",
            store,
            _ctx(),
        )
        assert result == "sleeping_quarters"

    def test_entity_property(self) -> None:
        store = _bunker_store()
        result = resolve(
            "food_supply.quantity",
            store,
            _ctx(),
        )
        assert result == 20

    def test_missing_property_returns_none(self) -> None:
        store = _bunker_store()
        result = resolve(
            "$agent.nonexistent",
            store,
            _ctx(),
        )
        assert result is None

    def test_nonexistent_entity_returns_none(self) -> None:
        store = _bunker_store()
        result = resolve(
            "ghost.x",
            store,
            _ctx(),
        )
        assert result is None

    def test_bare_agent_in_path(self) -> None:
        store = _bunker_store()
        result = resolve(
            "agent.location",
            store,
            _ctx(),
        )
        assert result == "sleeping_quarters"


class TestResolveFunction:
    def test_relationships_of(self) -> None:
        store = _bunker_store()
        result = resolve(
            "relationships_of($agent.location, type=connects_to)",
            store,
            _ctx(),
        )
        assert result == ["hallway"]

    def test_count(self) -> None:
        store = _bunker_store()
        result = resolve("count(type=agent)", store, _ctx())
        assert result == 3


class TestResolveArithmetic:
    def test_multiply(self) -> None:
        store = _bunker_store()
        result = resolve(
            "0.1 * count(type=agent)",
            store,
            _ctx(),
        )
        assert abs(result - 0.3) < 1e-9

    def test_numeric_literal(self) -> None:
        store = _bunker_store()
        assert resolve("42", store, _ctx()) == 42
        assert resolve("3.14", store, _ctx()) == 3.14
