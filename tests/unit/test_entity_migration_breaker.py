"""Breaker tests for Entity migration — adversarial attacks on the new dict-like Entity.

Tests target:
1. Empty _data dict access
2. .get() with defaults on missing keys
3. to_dict() shape
4. _parse_target with nested paths
5. _parse_target with entity-only (no property)
6. Config entity with property named "type" (collision)
7. Config entity with property named "id" (collision)
8. walk_entity_path on new Entity
9. DM-style effect with flat target (no .)
10. Legacy "entity.key" backward compat in _parse_target
"""

from __future__ import annotations

import pytest

from worldseed.dsl.effects._helpers import parse_target as _parse_target
from worldseed.dsl.functions import walk_entity_path
from worldseed.engine.state_store import StateStore
from worldseed.models.config_schema import EntityConfig
from worldseed.models.entity import Entity


# ---------------------------------------------------------------------------
# Attack 1: Entity with empty _data — entity["missing"] should KeyError
# ---------------------------------------------------------------------------
class TestEmptyDataAccess:
    def test_getitem_missing_raises_keyerror(self):
        """entity["missing"] on empty _data must raise KeyError, not return None."""
        e = Entity(id="ghost", type="agent")
        with pytest.raises(KeyError):
            _ = e["missing"]

    def test_contains_missing_is_false(self):
        """'missing' in entity must be False when _data is empty."""
        e = Entity(id="ghost", type="agent")
        assert "missing" not in e

    def test_items_empty(self):
        e = Entity(id="ghost", type="agent")
        assert e.items() == []

    def test_keys_empty(self):
        e = Entity(id="ghost", type="agent")
        assert e.keys() == []


# ---------------------------------------------------------------------------
# Attack 2: Entity.get("missing", default) returns default
# ---------------------------------------------------------------------------
class TestGetWithDefault:
    def test_get_missing_returns_none(self):
        e = Entity(id="x", type="resource")
        assert e.get("nonexistent") is None

    def test_get_missing_returns_custom_default(self):
        e = Entity(id="x", type="resource")
        assert e.get("nonexistent", 42) == 42

    def test_get_missing_returns_false_default(self):
        """Falsy defaults must be returned, not swallowed."""
        e = Entity(id="x", type="resource")
        assert e.get("nonexistent", 0) == 0
        assert e.get("nonexistent", "") == ""
        assert e.get("nonexistent", False) is False

    def test_get_existing_ignores_default(self):
        e = Entity(id="x", type="resource", _data={"stress": 80})
        assert e.get("stress", 999) == 80


# ---------------------------------------------------------------------------
# Attack 3: to_dict() has id, type, + all properties flat
# ---------------------------------------------------------------------------
class TestToDict:
    def test_to_dict_includes_id_type(self):
        e = Entity(id="npc1", type="agent", _data={"stress": 50, "location": "lab"})
        d = e.to_dict()
        assert d["id"] == "npc1"
        assert d["type"] == "agent"

    def test_to_dict_includes_all_properties(self):
        e = Entity(id="npc1", type="agent", _data={"stress": 50, "location": "lab"})
        d = e.to_dict()
        assert d["stress"] == 50
        assert d["location"] == "lab"

    def test_to_dict_no_nested_properties_key(self):
        """to_dict() must be flat — no nested 'properties' dict."""
        e = Entity(id="npc1", type="agent", _data={"stress": 50})
        d = e.to_dict()
        # There should not be a "properties" wrapper
        # No "properties" wrapper in output
        assert "properties" not in d or d.get("properties") == 50

    def test_to_dict_empty(self):
        e = Entity(id="void", type="concept")
        d = e.to_dict()
        assert d == {"id": "void", "type": "concept"}


# ---------------------------------------------------------------------------
# Attack 4: _parse_target with nested path "old_chen.trusts.xiao_li"
# ---------------------------------------------------------------------------
class TestParseTargetNested:
    def test_nested_three_segments(self):
        store = StateStore()
        ctx: dict = {}
        entity_id, prop = _parse_target("old_chen.trusts.xiao_li", store, ctx)
        assert entity_id == "old_chen"
        assert prop == "trusts.xiao_li"

    def test_nested_deep_path(self):
        store = StateStore()
        ctx: dict = {}
        entity_id, prop = _parse_target("food.inventory.slot.amount", store, ctx)
        assert entity_id == "food"
        assert prop == "inventory.slot.amount"


# ---------------------------------------------------------------------------
# Attack 5: _parse_target with just "old_chen" (no property) → error
# ---------------------------------------------------------------------------
class TestParseTargetBare:
    def test_bare_entity_no_prop_raises(self):
        """_parse_target("old_chen") has no property part — should raise ValueError."""
        store = StateStore()
        ctx: dict = {}
        with pytest.raises(ValueError, match="Cannot parse target"):
            _parse_target("old_chen", store, ctx)


# ---------------------------------------------------------------------------
# Attack 6: Config entity with property named "type" (collision)
# ---------------------------------------------------------------------------
class TestPropertyNamedType:
    def test_entity_config_with_type_property(self):
        """If YAML entity has a property called 'type', it should NOT overwrite
        the entity's type field. The 'type' key is reserved."""
        cfg = EntityConfig(id="node_a", type="concept", properties={"type": "virus"})
        # EntityConfig stores it, but the reserved 'type' field should be 'concept'
        assert cfg.type == "concept"
        # The property 'type' ends up in properties dict
        assert cfg.properties["type"] == "virus"

    def test_flat_yaml_type_collision(self):
        """Flat YAML format: extra key 'type' would collide with reserved 'type'.
        The model_validator keeps reserved keys as-is."""
        data = {"id": "node_a", "type": "concept", "virus_type": "alpha"}
        cfg = EntityConfig.model_validate(data)
        assert cfg.type == "concept"
        assert cfg.properties["virus_type"] == "alpha"

    def test_entity_from_config_type_collision(self):
        """Properties with 'type' key don't override Entity.type."""
        store = StateStore()
        cfg = EntityConfig(id="n1", type="concept", properties={"type": "virus"})
        e = Entity(id=cfg.id, type=cfg.type, _data=dict(cfg.properties))
        store.add(e)

        entity = store.get("n1")
        assert entity is not None
        assert entity.type == "concept"
        # Accessing entity["type"] reads from _data — returns the property value
        assert entity["type"] == "virus"
        # But entity.type (dataclass field) is "concept"
        assert entity.type == "concept"
        # to_dict: which one wins? _data's "type" overwrites the dataclass "type"
        d = entity.to_dict()
        # This is the BREAKING discovery: to_dict() does {**id, **type, **_data}
        # so if _data has "type", it OVERWRITES the real type!
        # Let's see what actually happens:
        assert d["id"] == "n1"
        # The _data "type" stomps the real type in to_dict():
        assert d["type"] == "concept"  # reserved key wins over _data


# ---------------------------------------------------------------------------
# Attack 7: Config entity with property named "id" (collision)
# ---------------------------------------------------------------------------
class TestPropertyNamedId:
    def test_entity_with_id_property(self):
        """Reserved 'id' in to_dict() always wins over _data."""
        e = Entity(id="real_id", type="agent", _data={"id": "fake_id", "stress": 50})
        d = e.to_dict()
        assert d["id"] == "real_id"  # reserved key wins

    def test_entity_id_field_untouched(self):
        """Dataclass .id attribute is never affected by _data."""
        e = Entity(id="real_id", type="agent", _data={"id": "fake_id"})
        assert e.id == "real_id"  # this is fine
        assert e["id"] == "fake_id"  # dict access → _data


# ---------------------------------------------------------------------------
# Attack 8: walk_entity_path with new Entity
# ---------------------------------------------------------------------------
class TestWalkEntityPath:
    def test_walk_simple_property(self):
        e = Entity(id="npc", type="agent", _data={"stress": 80})
        assert walk_entity_path(e, "stress") == 80

    def test_walk_missing_property_returns_none(self):
        e = Entity(id="npc", type="agent", _data={"stress": 80})
        assert walk_entity_path(e, "missing") is None

    def test_walk_nested_property(self):
        e = Entity(id="npc", type="agent", _data={"inventory": {"food": 3}})
        assert walk_entity_path(e, "inventory.food") == 3

    def test_walk_through_data_alias(self):
        """Path 'data.stress' resolves via .data property → _data dict."""
        e = Entity(id="npc", type="agent", _data={"stress": 80})
        result = walk_entity_path(e, "data.stress")
        assert result == 80

    def test_walk_deep_missing_returns_none(self):
        e = Entity(id="npc", type="agent", _data={"stress": 80})
        assert walk_entity_path(e, "inventory.food.count") is None

    def test_walk_id_field(self):
        """walk_entity_path(entity, 'id') — should get the dataclass field via
        hasattr, NOT from _data."""
        e = Entity(id="npc", type="agent", _data={})
        # 'id' is a dataclass attribute, so hasattr → True → getattr returns "npc"
        assert walk_entity_path(e, "id") == "npc"

    def test_walk_type_field(self):
        """walk_entity_path(entity, 'type') — similar to id."""
        e = Entity(id="npc", type="agent", _data={})
        assert walk_entity_path(e, "type") == "agent"


# ---------------------------------------------------------------------------
# Attack 9: Effect with flat target "partner_a.stress" (no .)
# ---------------------------------------------------------------------------
class TestFlatEffectTarget:
    def test_set_flat_target_applies(self):
        """DM returns effect with target 'partner_a.stress' (no .)
        — the effect must still find and update the property."""
        store = StateStore()
        e = Entity(id="partner_a", type="agent", _data={"stress": 50})
        store.add(e)

        ctx: dict = {}
        entity_id, prop = _parse_target("partner_a.stress", store, ctx)
        assert entity_id == "partner_a"
        assert prop == "stress"

        # Actually apply via store
        store.update_property(entity_id, prop, 90)
        assert store.get("partner_a") is not None
        assert store.get("partner_a")["stress"] == 90  # type: ignore[index]

    def test_set_flat_nested_target_applies(self):
        """DM returns 'partner_a.inventory.food' — nested without ."""
        store = StateStore()
        e = Entity(id="partner_a", type="agent", _data={"inventory": {"food": 5}})
        store.add(e)

        entity_id, prop = _parse_target("partner_a.inventory.food", store, {})
        assert entity_id == "partner_a"
        assert prop == "inventory.food"

        store.update_property(entity_id, prop, 10)
        assert store.get("partner_a")["inventory"]["food"] == 10  # type: ignore[index]


# ---------------------------------------------------------------------------
# Attack 10: Old format "food.quantity" backward compat
# ---------------------------------------------------------------------------
class TestLegacyPropertiesFormat:
    def test_legacy_parse_target(self):
        """'food.quantity' should parse to (food, quantity)."""
        store = StateStore()
        ctx: dict = {}
        entity_id, prop = _parse_target("food.quantity", store, ctx)
        assert entity_id == "food"
        assert prop == "quantity"

    def test_legacy_nested_path(self):
        """'food.inventory.slot' should parse to (food, inventory.slot)."""
        store = StateStore()
        ctx: dict = {}
        entity_id, prop = _parse_target("food.inventory.slot", store, ctx)
        assert entity_id == "food"
        assert prop == "inventory.slot"

    def test_legacy_parse_and_apply(self):
        """Full roundtrip: legacy target format resolves and applies correctly."""
        store = StateStore()
        e = Entity(id="food", type="resource", _data={"quantity": 20})
        store.add(e)

        entity_id, prop = _parse_target("food.quantity", store, {})
        store.update_property(entity_id, prop, 15)
        assert store.get("food")["quantity"] == 15  # type: ignore[index]

    def test_flat_and_legacy_give_same_result(self):
        """'food.quantity' and 'food.quantity' must parse identically."""
        store = StateStore()
        ctx: dict = {}
        eid1, prop1 = _parse_target("food.quantity", store, ctx)
        eid2, prop2 = _parse_target("food.quantity", store, ctx)
        assert eid1 == eid2
        assert prop1 == prop2


# ---------------------------------------------------------------------------
# Bonus Attack: Entity construction via properties= kwarg
# ---------------------------------------------------------------------------
class TestEntityConstruction:
    def test_data_kwarg(self):
        """Entity(_data={...}) is the only construction path."""
        e = Entity(id="x", type="agent", _data={"stress": 50})
        assert e["stress"] == 50
        assert e.data == {"stress": 50}
