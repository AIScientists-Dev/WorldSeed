"""Tests for constraints separation — engine metadata vs game data.

Constraints (min/max enforcement) are stored on Entity._constraints,
NOT in Entity._data. This ensures they never leak into perception,
API responses, or agent-visible data.
"""

from __future__ import annotations

from worldseed.engine.event_log import EventLog
from worldseed.engine.inbox import InboxManager
from worldseed.engine.perceiver import Perceiver
from worldseed.engine.state_store import StateStore
from worldseed.models.config_schema import PerceptionConfig, PreconditionConfig
from worldseed.models.entity import Entity
from worldseed.world import WorldEngine

from ..conftest import CONFIGS_DIR

# ---------------------------------------------------------------------------
# 1. Entity data model
# ---------------------------------------------------------------------------


class TestEntityConstraintsSeparation:
    def test_constraints_not_in_data(self) -> None:
        """Constraints stored in _constraints, not in _data."""
        e = Entity(
            id="food",
            type="resource",
            _data={"quantity": 20},
            _constraints={"quantity": {"min": 0}},
        )
        assert "constraints" not in e.data
        assert e.constraints == {"quantity": {"min": 0}}

    def test_constraints_default_empty(self) -> None:
        e = Entity(id="room", type="space")
        assert e.constraints == {}

    def test_to_dict_excludes_constraints(self) -> None:
        """to_dict() is for API/perception — no engine metadata."""
        e = Entity(
            id="food",
            type="resource",
            _data={"quantity": 20, "location": "storage"},
            _constraints={"quantity": {"min": 0, "max": 100}},
        )
        d = e.to_dict()
        assert "constraints" not in d
        assert d["quantity"] == 20
        assert d["id"] == "food"
        assert d["type"] == "resource"

    def test_to_full_dict_includes_constraints(self) -> None:
        """to_full_dict() is for persistence — includes everything."""
        e = Entity(
            id="food",
            type="resource",
            _data={"quantity": 20},
            _constraints={"quantity": {"min": 0, "max": 100}},
        )
        d = e.to_full_dict()
        assert d["constraints"] == {"quantity": {"min": 0, "max": 100}}
        assert d["quantity"] == 20
        assert d["id"] == "food"

    def test_to_full_dict_no_constraints_key_when_empty(self) -> None:
        """No spurious 'constraints' key when entity has none."""
        e = Entity(id="room", type="space", _data={"desc": "a room"})
        d = e.to_full_dict()
        assert "constraints" not in d

    def test_mutable_defaults_not_shared(self) -> None:
        """Each entity gets its own constraints dict."""
        a = Entity(id="a", type="t")
        b = Entity(id="b", type="t")
        a.constraints["hp"] = {"min": 0}
        assert "hp" not in b.constraints


# ---------------------------------------------------------------------------
# 2. StateStore enforcement
# ---------------------------------------------------------------------------


class TestStateStoreConstraintEnforcement:
    def test_min_clamp(self) -> None:
        store = StateStore()
        e = Entity(
            id="food",
            type="resource",
            _data={"quantity": 10},
            _constraints={"quantity": {"min": 0}},
        )
        store.add(e)
        store.update_property("food", "quantity", -5)
        assert store.get("food")["quantity"] == 0  # type: ignore[union-attr]

    def test_max_clamp(self) -> None:
        store = StateStore()
        e = Entity(
            id="filter",
            type="equipment",
            _data={"condition": 50},
            _constraints={"condition": {"min": 0, "max": 100}},
        )
        store.add(e)
        store.update_property("filter", "condition", 150)
        assert store.get("filter")["condition"] == 100  # type: ignore[union-attr]

    def test_no_constraints_no_clamp(self) -> None:
        store = StateStore()
        e = Entity(id="x", type="t", _data={"val": 10})
        store.add(e)
        store.update_property("x", "val", -100)
        assert store.get("x")["val"] == -100  # type: ignore[union-attr]

    def test_constraints_on_entity_not_in_data(self) -> None:
        """After enforcement, constraints still not in data."""
        store = StateStore()
        e = Entity(
            id="food",
            type="resource",
            _data={"quantity": 10},
            _constraints={"quantity": {"min": 0}},
        )
        store.add(e)
        store.update_property("food", "quantity", 5)
        assert "constraints" not in store.get("food").data  # type: ignore[union-attr]

    def test_non_numeric_value_skips_constraints(self) -> None:
        store = StateStore()
        e = Entity(
            id="x",
            type="t",
            _data={"status": "ok"},
            _constraints={"status": {"min": 0}},
        )
        store.add(e)
        store.update_property("x", "status", "broken")
        assert store.get("x")["status"] == "broken"  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# 3. Populator — config loading
# ---------------------------------------------------------------------------


class TestPopulatorConstraintExtraction:
    def test_bunker_food_supply_constraints_separated(self) -> None:
        """Bunker food_supply has constraints in config → separated on entity."""
        w = WorldEngine(CONFIGS_DIR / "bunker.yaml")
        w.register_from_config()
        food = w.state.get("food_supply")
        assert food is not None

        # Constraints NOT in data
        assert "constraints" not in food.data

        # Constraints accessible via property
        assert food.constraints.get("quantity") is not None
        assert food.constraints["quantity"]["min"] == 0

        # Game data still there
        assert food["quantity"] == 20

    def test_bunker_spaces_no_constraints(self) -> None:
        """Spaces in bunker have no constraints → empty dict."""
        w = WorldEngine(CONFIGS_DIR / "bunker.yaml")
        w.register_from_config()
        hallway = w.state.get("hallway")
        assert hallway is not None
        assert hallway.constraints == {}

    def test_bunker_agents_no_constraints_leak(self) -> None:
        """Agents should not have constraints in data."""
        w = WorldEngine(CONFIGS_DIR / "bunker.yaml")
        w.register_from_config()
        for aid in ["old_chen", "xiao_li", "doctor_wang"]:
            agent = w.state.get(aid)
            assert agent is not None
            assert "constraints" not in agent.data


# ---------------------------------------------------------------------------
# 4. Perception — constraints never visible
# ---------------------------------------------------------------------------


class TestPerceptionNoConstraints:
    def test_snapshot_visible_entities_no_constraints(self) -> None:
        """Perceiver snapshot must not contain constraints for any entity."""
        store = StateStore()
        store.add(
            Entity(
                id="agent_a",
                type="agent",
                _data={"location": "room"},
            )
        )
        store.add(
            Entity(
                id="room",
                type="space",
                _data={"location": "room", "description": "a room"},
            )
        )
        store.add(
            Entity(
                id="food",
                type="resource",
                _data={"location": "room", "quantity": 10},
                _constraints={"quantity": {"min": 0, "max": 100}},
            )
        )
        perception = PerceptionConfig(
            visibility=[
                PreconditionConfig(
                    operator="check",
                    left="$observer.location",
                    op="==",
                    right="$entity.location",
                )
            ],
        )
        perceiver = Perceiver(store, EventLog(), InboxManager(), perception)
        perceiver.deliver(tick=1)

        inbox = perceiver._inbox_manager.get_or_create("agent_a")
        data = inbox.read()
        state = data["current_state"]

        # self_state: agent's own data
        assert "constraints" not in state.self_state

        # visible_entities: food should not have constraints
        assert "food" in state.visible_entities
        assert "constraints" not in state.visible_entities["food"]
        assert state.visible_entities["food"]["quantity"] == 10

    def test_engine_perceive_no_constraints(self) -> None:
        """Full engine.perceive() path — no constraints anywhere."""
        w = WorldEngine(CONFIGS_DIR / "bunker.yaml")
        w.register_from_config()

        # Move old_chen to storage_room where food_supply is
        w.state.update_property("old_chen", "location", "storage_room")
        w._tick_engine.step()  # advance tick to deliver perception

        p = w.perceive("old_chen")
        result = p.to_dict()

        # self_state
        assert "constraints" not in result["self_state"]

        # nearby_entities — food_supply should be visible
        for eid, props in result["nearby_entities"].items():
            assert "constraints" not in props, f"{eid} has constraints in perception"

        # nearby_agents
        for aid, props in result["nearby_agents"].items():
            assert "constraints" not in props, f"{aid} has constraints in perception"


# ---------------------------------------------------------------------------
# 5. Save/Load roundtrip
# ---------------------------------------------------------------------------


class TestSaveLoadConstraintsRoundtrip:
    def test_to_full_dict_and_back(self) -> None:
        """Entity → to_full_dict → reconstruct → constraints preserved."""
        original = Entity(
            id="food",
            type="resource",
            _data={"quantity": 15, "location": "storage"},
            _constraints={"quantity": {"min": 0, "max": 100}},
        )
        saved = original.to_full_dict()

        # Simulate load_state reconstruction
        d = dict(saved)
        eid = d.pop("id")
        etype = d.pop("type")
        constraints = d.pop("constraints", {})
        restored = Entity(id=eid, type=etype, _data=d, _constraints=constraints)

        assert restored.id == "food"
        assert restored["quantity"] == 15
        assert "constraints" not in restored.data
        assert restored.constraints == {"quantity": {"min": 0, "max": 100}}

    def test_save_load_no_constraints_entity(self) -> None:
        """Entity without constraints survives roundtrip cleanly."""
        original = Entity(id="room", type="space", _data={"desc": "a room"})
        saved = original.to_full_dict()

        d = dict(saved)
        eid = d.pop("id")
        etype = d.pop("type")
        constraints = d.pop("constraints", {})
        restored = Entity(id=eid, type=etype, _data=d, _constraints=constraints)

        assert restored.constraints == {}
        assert restored["desc"] == "a room"
        assert "constraints" not in restored.data
