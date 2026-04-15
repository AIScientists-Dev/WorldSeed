"""Tests for StateStore."""

from __future__ import annotations

import pytest

from worldseed.engine.state_store import StateStore
from worldseed.models import Entity
from worldseed.world import WorldEngine

from ..conftest import CONFIGS_DIR


class TestStateStore:
    def test_add_and_get(self, state_store: StateStore) -> None:
        entity = Entity(id="chen", type="agent", _data={"location": "room"})
        state_store.add(entity)
        assert state_store.get("chen") is entity

    def test_get_nonexistent(self, state_store: StateStore) -> None:
        assert state_store.get("ghost") is None

    def test_add_duplicate_raises(self, state_store: StateStore) -> None:
        state_store.add(Entity(id="chen", type="agent"))
        with pytest.raises(ValueError, match="already exists"):
            state_store.add(Entity(id="chen", type="agent"))

    def test_remove(self, state_store: StateStore) -> None:
        state_store.add(Entity(id="chen", type="agent"))
        removed = state_store.remove("chen")
        assert removed is not None
        assert state_store.get("chen") is None

    def test_remove_leaves_stale_refs(self, state_store: StateStore) -> None:
        """After entity removal, stale refs stay in properties.

        No write-time cleanup — avoids false positives on
        non-relationship properties. Preconditions validate targets.
        """
        state_store.add(
            Entity(
                id="a",
                type="agent",
                _data={"trusts": ["b"]},
            )
        )
        state_store.add(Entity(id="b", type="agent"))
        state_store.remove("b")
        assert state_store.get("b") is None
        # Stale ref preserved in properties
        assert state_store.get("a")["trusts"] == ["b"]  # type: ignore[union-attr]

    def test_update_property(self, state_store: StateStore) -> None:
        state_store.add(Entity(id="chen", type="agent", _data={"location": "room_a"}))
        result = state_store.update_property("chen", "location", "room_b")
        assert result == ("room_a", "room_b")
        assert state_store.get("chen")["location"] == "room_b"  # type: ignore[union-attr]

    def test_update_creates_new_property(self, state_store: StateStore) -> None:
        state_store.add(Entity(id="chen", type="agent"))
        result = state_store.update_property("chen", "anxiety", "high")
        assert result == (None, "high")
        assert state_store.get("chen")["anxiety"] == "high"  # type: ignore[union-attr]

    def test_update_nonexistent_entity(self, state_store: StateStore) -> None:
        assert state_store.update_property("ghost", "x", 1) is None

    def test_query_by_type(self, state_store: StateStore) -> None:
        state_store.add(Entity(id="chen", type="agent"))
        state_store.add(Entity(id="li", type="agent"))
        state_store.add(Entity(id="room", type="space"))
        agents = state_store.query_by_type("agent")
        assert len(agents) == 2
        assert all(a.type == "agent" for a in agents)

    def test_add_relationship_upsert_via_properties(self, state_store: StateStore) -> None:
        state_store.add(Entity(id="chen", type="agent", _data={}))
        # Add via property (dict stores valued relationships)
        state_store.update_property("chen", "trusts", {"li": 40})
        state_store.update_property("chen", "trusts", {"li": 80})
        trusts = state_store.get("chen")["trusts"]  # type: ignore[union-attr]
        assert trusts == {"li": 80}

    def test_remove_relationship_via_properties(self, state_store: StateStore) -> None:
        state_store.add(
            Entity(
                id="chen",
                type="agent",
                _data={"trusts": ["li"]},
            )
        )
        # Remove by updating the property
        chen = state_store.get("chen")
        assert chen is not None
        chen["trusts"] = [x for x in chen["trusts"] if x != "li"]
        assert chen["trusts"] == []


class TestPopulateFromConfig:
    def test_bunker_entities_loaded(self) -> None:
        w = WorldEngine(CONFIGS_DIR / "bunker.yaml")
        w.register_from_config()
        store = w.state

        assert store.get("old_chen") is not None
        assert store.get("food_supply") is not None
        assert store.get("hallway") is not None
        assert store.get("old_chen")["location"] == "sleeping_quarters"  # type: ignore[union-attr]
        assert store.get("food_supply")["quantity"] == 20  # type: ignore[union-attr]
        # 3 preset agents + 1 narrator (auto-created, default on)
        assert len(store.query_by_type("agent")) == 4
        assert len(store.query_by_type("space")) == 4
        assert len(store.query_by_type("resource")) == 2

    def test_bunker_relationships_loaded(self) -> None:
        w = WorldEngine(CONFIGS_DIR / "bunker.yaml")
        w.register_from_config()
        store = w.state

        # Sleeping quarters connects to hallway (via properties)
        sq = store.get("sleeping_quarters")
        assert sq is not None
        sq_targets = set(sq.get("connects_to", []))
        assert sq_targets == {"hallway"}

        # Hallway connects to 3 spaces
        hw = store.get("hallway")
        assert hw is not None
        hw_targets = set(hw.get("connects_to", []))
        assert hw_targets == {"storage_room", "sleeping_quarters", "entrance"}

        # Food supply located_in storage_room
        food = store.get("food_supply")
        assert food is not None
        food_loc = food.get("located_in", [])
        assert food_loc == ["storage_room"]
