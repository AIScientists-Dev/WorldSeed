"""Edge-case tests for Entity migration + DM system.

Covers gaps NOT in test_generality_audit.py or test_generality_edge.py:
  1. Deeply nested properties (3+ levels) accessed via flat path
  2. Entity with property named "data" (collision with .data accessor)
  3. Entity with property named "id" or "type" — to_dict() behaviour
  4. DM effect targeting nested property like "old_chen.inventory.food"
  5. Config with mixed flat + legacy properties format
  6. walk_entity_path through Entity -> nested dict -> deeper dict
  7. _parse_target with $param in various positions
"""

from __future__ import annotations

from worldseed.dsl.effects import execute as exec_effect
from worldseed.dsl.effects._helpers import parse_target as _parse_target
from worldseed.dsl.functions import walk_entity_path
from worldseed.dsl.path_resolver import resolve
from worldseed.dsl.preconditions import evaluate as eval_precond
from worldseed.engine.event_log import EventLog
from worldseed.engine.state_store import StateStore
from worldseed.models import Entity
from worldseed.models.config_schema import (
    AgentConfig,
    EffectConfig,
    EntityConfig,
    PreconditionConfig,
)
from worldseed.utils.nested import nested_get

# ── 1. Deeply nested properties (3+ levels) via flat path ────────────


class TestDeeplyNestedProperties:
    """walk_entity_path and state_store must handle 3-4 level nesting."""

    def test_walk_4_level_nesting(self) -> None:
        e = Entity(id="x", type="t", _data={"a": {"b": {"c": {"d": 42}}}})
        assert walk_entity_path(e, "a.b.c.d") == 42

    def test_walk_3_level_nesting_returns_dict(self) -> None:
        e = Entity(
            id="x",
            type="t",
            _data={"inventory": {"backpack": {"slot1": "sword", "slot2": "shield"}}},
        )
        result = walk_entity_path(e, "inventory.backpack")
        assert isinstance(result, dict)
        assert result["slot1"] == "sword"

    def test_state_store_update_deep_path(self) -> None:
        store = StateStore()
        store.add(Entity(id="x", type="t", _data={}))
        store.update_property("x", "a.b.c.d", 99)
        e = store.get("x")
        assert e is not None
        assert nested_get(e.data, "a.b.c.d") == 99

    def test_effect_set_deep_nested(self) -> None:
        store = StateStore()
        store.add(Entity(id="x", type="t", _data={"stats": {"combat": {"attack": 10}}}))
        el = EventLog()
        ctx = {"agent_id": "x", "action_params": {}, "tick": 1}
        exec_effect(
            EffectConfig(operator="set", target="x.stats.combat.attack", value=25),
            store,
            el,
            ctx,
            tick=1,
        )
        assert nested_get(store.get("x").data, "stats.combat.attack") == 25

    def test_effect_increment_deep_nested(self) -> None:
        store = StateStore()
        store.add(
            Entity(
                id="hero",
                type="agent",
                _data={"skills": {"magic": {"fire": {"level": 3}}}},
            )
        )
        el = EventLog()
        ctx = {"agent_id": "hero", "action_params": {}, "tick": 1}
        exec_effect(
            EffectConfig(
                operator="increment",
                target="hero.skills.magic.fire.level",
                by=2,
            ),
            store,
            el,
            ctx,
            tick=1,
        )
        assert nested_get(store.get("hero").data, "skills.magic.fire.level") == 5

    def test_precondition_check_deep_nested(self) -> None:
        store = StateStore()
        store.add(Entity(id="x", type="t", _data={"a": {"b": {"c": 7}}}))
        ctx = {"agent_id": "x", "action_params": {}, "tick": 1}
        p = PreconditionConfig(
            operator="check",
            left="x.a.b.c",
            op="==",
            right=7,
        )
        assert eval_precond(p, store, ctx) is True

    def test_resolve_deep_nested_path(self) -> None:
        store = StateStore()
        store.add(Entity(id="x", type="t", _data={"a": {"b": {"c": "found"}}}))
        ctx = {"agent_id": "x", "action_params": {}, "tick": 1}
        assert resolve("x.a.b.c", store, ctx) == "found"


# ── 2. Entity with property named "data" ─────────────────────────────


class TestPropertyNamedData:
    """Property named 'data' collides with Entity.data property accessor."""

    def test_entity_property_named_data_getitem(self) -> None:
        e = Entity(id="x", type="t", _data={"data": "payload"})
        # Dict access should return the property, not the .data dict
        assert e["data"] == "payload"

    def test_entity_data_accessor_returns_dict(self) -> None:
        e = Entity(id="x", type="t", _data={"data": "payload"})
        # .data property must return the raw _data dict, not the value
        assert isinstance(e.data, dict)
        assert e.data == {"data": "payload"}

    def test_walk_entity_path_data_property(self) -> None:
        """walk_entity_path('data') should find the property first."""
        e = Entity(id="x", type="t", _data={"data": "payload"})
        # Since "data" is in the entity's properties, walk_entity_path
        # checks `part in current` first (which checks _data dict),
        # so it should return "payload"
        result = walk_entity_path(e, "data")
        assert result == "payload"

    def test_walk_entity_path_data_nested(self) -> None:
        """'data.info' when 'data' is a property with nested dict."""
        e = Entity(id="x", type="t", _data={"data": {"info": "secret", "count": 5}})
        assert walk_entity_path(e, "data.info") == "secret"
        assert walk_entity_path(e, "data.count") == 5

    def test_store_update_property_named_data(self) -> None:
        store = StateStore()
        store.add(Entity(id="x", type="t", _data={"data": "old"}))
        store.update_property("x", "data", "new")
        assert store.get("x")["data"] == "new"

    def test_effect_set_on_data_property(self) -> None:
        store = StateStore()
        store.add(Entity(id="x", type="t", _data={"data": 0}))
        el = EventLog()
        ctx = {"agent_id": "x", "action_params": {}, "tick": 1}
        exec_effect(
            EffectConfig(operator="set", target="x.data", value=42),
            store,
            el,
            ctx,
            tick=1,
        )
        assert store.get("x")["data"] == 42


# ── 3. Entity with property named "id" or "type" — to_dict() ─────────


class TestPropertyNamedIdOrType:
    """Property named 'id' or 'type' in _data must not shadow metadata."""

    def test_to_dict_id_wins_over_property(self) -> None:
        """to_dict() merges _data first, then overwrites id and type."""
        e = Entity(
            id="real_id",
            type="real_type",
            _data={
                "id": "fake_id",
                "type": "fake_type",
                "hp": 100,
            },
        )
        d = e.to_dict()
        # Reserved keys always win
        assert d["id"] == "real_id"
        assert d["type"] == "real_type"
        assert d["hp"] == 100

    def test_getitem_returns_data_id(self) -> None:
        """e['id'] reads from _data, where 'id' was stored as a property."""
        e = Entity(
            id="real_id",
            type="real_type",
            _data={
                "id": "fake_id",
            },
        )
        # __getitem__ goes to _data
        assert e["id"] == "fake_id"
        # but the metadata is still correct
        assert e.id == "real_id"

    def test_property_named_type_in_precondition(self) -> None:
        """Precondition reading entity.type vs entity['type'] in _data."""
        store = StateStore()
        store.add(Entity(id="x", type="agent", _data={"type": "warrior"}))
        ctx = {"agent_id": "x", "action_params": {}, "tick": 1}
        # Path "x.type" — walk_entity_path checks "type" in current (the _data),
        # finds "warrior", returns it (not "agent")
        p = PreconditionConfig(
            operator="check",
            left="x.type",
            op="==",
            right="warrior",
        )
        assert eval_precond(p, store, ctx) is True

    def test_walk_path_id_in_data(self) -> None:
        """walk_entity_path('id') returns _data['id'] if present."""
        e = Entity(id="real_id", type="t", _data={"id": "data_id"})
        # "id" is in current (_data), so it returns data_id
        assert walk_entity_path(e, "id") == "data_id"

    def test_walk_path_id_not_in_data_falls_back(self) -> None:
        """walk_entity_path('id') falls back to entity.id if not in _data."""
        e = Entity(id="real_id", type="t", _data={"hp": 10})
        # "id" is not in _data, but hasattr(entity, "id") is True
        assert walk_entity_path(e, "id") == "real_id"


# ── 4. DM effect targeting nested property like old_chen.inventory.food ──


class TestDMEffectNestedTarget:
    """Effects with targets like 'agent.inventory.food' — 3-part paths."""

    def test_set_nested_with_agent_param(self) -> None:
        store = StateStore()
        store.add(
            Entity(
                id="old_chen",
                type="agent",
                _data={"inventory": {"food": 5, "water": 3}},
            )
        )
        el = EventLog()
        ctx = {"agent_id": "old_chen", "action_params": {}, "tick": 1}
        exec_effect(
            EffectConfig(
                operator="set",
                target="$agent.inventory.food",
                value=10,
            ),
            store,
            el,
            ctx,
            tick=1,
        )
        assert nested_get(store.get("old_chen").data, "inventory.food") == 10

    def test_increment_nested_with_resource_param(self) -> None:
        store = StateStore()
        store.add(
            Entity(
                id="old_chen",
                type="agent",
                _data={"inventory": {"food": 5, "water": 3}},
            )
        )
        el = EventLog()
        ctx = {
            "agent_id": "old_chen",
            "action_params": {"resource": "food"},
            "tick": 1,
        }
        exec_effect(
            EffectConfig(
                operator="increment",
                target="$agent.inventory.$resource",
                by=2,
            ),
            store,
            el,
            ctx,
            tick=1,
        )
        assert nested_get(store.get("old_chen").data, "inventory.food") == 7

    def test_decrement_nested_with_literal_entity(self) -> None:
        store = StateStore()
        store.add(Entity(id="old_chen", type="agent", _data={"inventory": {"food": 10}}))
        el = EventLog()
        ctx = {"agent_id": "old_chen", "action_params": {}, "tick": 1}
        exec_effect(
            EffectConfig(
                operator="decrement",
                target="old_chen.inventory.food",
                by=3,
            ),
            store,
            el,
            ctx,
            tick=1,
        )
        assert nested_get(store.get("old_chen").data, "inventory.food") == 7

    def test_precondition_check_nested_inventory(self) -> None:
        store = StateStore()
        store.add(Entity(id="old_chen", type="agent", _data={"inventory": {"food": 5}}))
        ctx = {"agent_id": "old_chen", "action_params": {}, "tick": 1}
        p = PreconditionConfig(
            operator="check",
            left="$agent.inventory.food",
            op=">=",
            right=3,
        )
        assert eval_precond(p, store, ctx) is True


# ── 5. Config with mixed flat + legacy properties format ──────────────


class TestMixedFlatLegacyConfig:
    """EntityConfig and AgentConfig must handle mixed flat+legacy inputs."""

    def test_entity_flat_only(self) -> None:
        cfg = EntityConfig(id="x", type="resource", quantity=20, location="room")
        assert cfg.properties == {"quantity": 20, "location": "room"}

    def test_entity_legacy_only(self) -> None:
        cfg = EntityConfig(
            id="x",
            type="resource",
            properties={"quantity": 20, "location": "room"},
        )
        assert cfg.properties == {"quantity": 20, "location": "room"}

    def test_entity_mixed_flat_and_legacy(self) -> None:
        """Flat keys merge INTO properties dict. Flat wins on collision."""
        cfg = EntityConfig(
            id="x",
            type="resource",
            properties={"quantity": 20},
            location="room",
            quality="high",
        )
        assert cfg.properties["quantity"] == 20
        assert cfg.properties["location"] == "room"
        assert cfg.properties["quality"] == "high"

    def test_entity_flat_overrides_legacy_on_collision(self) -> None:
        """When flat key and properties have same name, flat wins (update)."""
        cfg = EntityConfig(
            id="x",
            type="resource",
            properties={"quantity": 20},
            quantity=99,
        )
        # extra dict's .update() runs after base, so flat wins
        assert cfg.properties["quantity"] == 99

    def test_agent_mixed_flat_and_legacy(self) -> None:
        cfg = AgentConfig(
            id="hero",
            properties={"hp": 100},
            stress=50,
            character={"personality": "brave"},
        )
        assert cfg.properties["hp"] == 100
        assert cfg.properties["stress"] == 50
        assert cfg.character == {"personality": "brave"}

    def test_agent_flat_with_template(self) -> None:
        cfg = AgentConfig(
            id="hero",
            template="warrior",
            strength=18,
            dexterity=14,
        )
        assert cfg.template == "warrior"
        assert cfg.properties == {"strength": 18, "dexterity": 14}

    def test_entity_nested_property_in_flat_format(self) -> None:
        """Nested dict as a flat key value."""
        cfg = EntityConfig(
            id="chest",
            type="container",
            inventory={"gold": 100, "gems": 5},
        )
        assert cfg.properties["inventory"] == {"gold": 100, "gems": 5}


# ── 6. walk_entity_path through Entity -> nested dict -> deeper dict ──


class TestWalkEntityPathChained:
    """walk_entity_path must transition Entity -> dict -> dict seamlessly."""

    def test_entity_to_dict_to_value(self) -> None:
        e = Entity(id="x", type="t", _data={"stats": {"hp": 100}})
        assert walk_entity_path(e, "stats.hp") == 100

    def test_entity_to_dict_to_dict_to_value(self) -> None:
        e = Entity(
            id="x",
            type="t",
            _data={"equipment": {"weapon": {"name": "sword", "damage": 10}}},
        )
        assert walk_entity_path(e, "equipment.weapon.name") == "sword"
        assert walk_entity_path(e, "equipment.weapon.damage") == 10

    def test_entity_to_dict_missing_key(self) -> None:
        e = Entity(id="x", type="t", _data={"a": {"b": 1}})
        assert walk_entity_path(e, "a.nonexistent") is None

    def test_entity_to_dict_to_dict_missing_intermediate(self) -> None:
        e = Entity(id="x", type="t", _data={"a": {"b": 1}})
        # "a.c.d" — "c" doesn't exist in {"b": 1}
        assert walk_entity_path(e, "a.c.d") is None

    def test_entity_to_scalar_then_further_path(self) -> None:
        """Walking past a scalar should return None, not crash."""
        e = Entity(id="x", type="t", _data={"hp": 10})
        assert walk_entity_path(e, "hp.sub") is None

    def test_entity_to_list_then_further_path(self) -> None:
        """Walking into a list (not dict) should return None."""
        e = Entity(id="x", type="t", _data={"items": ["a", "b"]})
        assert walk_entity_path(e, "items.0") is None

    def test_walk_with_data_prefix(self) -> None:
        """'data.X' path resolves through .data accessor."""
        e = Entity(id="x", type="t", _data={"hp": 100})
        assert walk_entity_path(e, "data.hp") == 100

    def test_walk_with_data_prefix_and_nested(self) -> None:
        """'data.a.b' goes through .data accessor -> dict walk."""
        e = Entity(id="x", type="t", _data={"a": {"b": 42}})
        # If "data" is not a property key but an attribute, use that
        # But here, "data" is NOT in _data, so hasattr fallback
        assert walk_entity_path(e, "data.a.b") == 42


# ── 7. _parse_target with $param in various positions ─────────────────


class TestParseTargetParams:
    """_parse_target must resolve $param in prefix, middle, suffix."""

    def test_param_as_entity_id(self) -> None:
        store = StateStore()
        store.add(Entity(id="hero", type="agent", _data={"hp": 100}))
        ctx = {"agent_id": "hero", "action_params": {}, "tick": 1}
        eid, prop = _parse_target("$agent.hp", store, ctx)
        assert eid == "hero"
        assert prop == "hp"

    def test_param_in_property_segment(self) -> None:
        store = StateStore()
        ctx = {
            "agent_id": "hero",
            "action_params": {"resource": "food"},
            "tick": 1,
        }
        eid, prop = _parse_target("$agent.inventory.$resource", store, ctx)
        assert eid == "hero"
        assert prop == "inventory.food"

    def test_param_embedded_in_segment(self) -> None:
        """$param embedded within a segment: 'votes_$choice'."""
        store = StateStore()
        ctx = {
            "agent_id": "hero",
            "action_params": {"choice": "agree"},
            "tick": 1,
        }
        eid, prop = _parse_target("poll.votes_$choice", store, ctx)
        assert eid == "poll"
        assert prop == "votes_agree"

    def test_param_with_legacy_properties_prefix(self) -> None:
        store = StateStore()
        ctx = {
            "agent_id": "hero",
            "action_params": {},
            "tick": 1,
        }
        eid, prop = _parse_target("$agent.hp", store, ctx)
        assert eid == "hero"
        assert prop == "hp"

    def test_param_in_nested_property_with_legacy(self) -> None:
        store = StateStore()
        ctx = {
            "agent_id": "hero",
            "action_params": {"slot": "weapon"},
            "tick": 1,
        }
        eid, prop = _parse_target(
            "$agent.equipment.$slot",
            store,
            ctx,
        )
        assert eid == "hero"
        assert prop == "equipment.weapon"

    def test_multiple_params_in_target(self) -> None:
        store = StateStore()
        ctx = {
            "agent_id": "hero",
            "action_params": {"container": "chest", "item": "gold"},
            "tick": 1,
        }
        eid, prop = _parse_target(
            "$container.$item",
            store,
            ctx,
        )
        assert eid == "chest"
        assert prop == "gold"

    def test_unresolvable_param_stays_literal(self) -> None:
        store = StateStore()
        ctx = {"agent_id": "hero", "action_params": {}, "tick": 1}
        eid, prop = _parse_target("$agent.$unknown_param", store, ctx)
        assert eid == "hero"
        # $unknown_param is not resolvable, stays as literal
        assert prop == "$unknown_param"

    def test_bare_agent_keyword(self) -> None:
        """'agent.hp' resolves 'agent' to agent_id."""
        store = StateStore()
        ctx = {"agent_id": "hero", "action_params": {}, "tick": 1}
        eid, prop = _parse_target("agent.hp", store, ctx)
        assert eid == "hero"
        assert prop == "hp"

    def test_tick_param_in_target(self) -> None:
        store = StateStore()
        ctx = {"agent_id": "hero", "action_params": {}, "tick": 42}
        eid, prop = _parse_target("log.entry_$tick", store, ctx)
        assert eid == "log"
        assert prop == "entry_42"
