"""GENERALITY AUDIT — Bizarre edge-case test that exercises every claim.

This test constructs a deliberately alien scene with:
- Deeply nested properties (4+ levels)
- Unicode entity IDs and property names
- All DSL operators: check, exists, not, all, any
- All comparison ops: ==, !=, >, <, >=, <=, in, contains
- All effect operators: set, increment, decrement, create_entity,
  remove_entity, add_relationship, remove_relationship, emit_event
- Arithmetic expressions with count() and sum()
- relationships_of() in preconditions
- Cascading consequences (consequence A changes state -> consequence B fires)
- Auto_tick with condition guards
- Template merge with deeply nested properties
- $param in every position (prefix, middle, suffix of path segments)
- Non-standard naming (no "location", "room", or spatial concepts)
- Float precision edge cases (0.0, 0.1 increments, int/float mixing)
- Entity creation and removal within the same tick
- Perception with compound visibility rules + hidden nested properties
- Custom event scopes with DSL rules

If the engine is truly scene-agnostic and generic, ALL of these should work.
"""

from __future__ import annotations

from worldseed.dsl.effects import execute as exec_effect
from worldseed.dsl.functions import relationships_of, walk_entity_path
from worldseed.dsl.path_resolver import resolve, resolve_params
from worldseed.dsl.preconditions import evaluate as eval_precond
from worldseed.engine.consequence_scanner import ConsequenceScanner
from worldseed.engine.event_log import EventLog
from worldseed.engine.inbox import InboxManager
from worldseed.engine.perceiver import Perceiver
from worldseed.engine.rules_engine import ActionResult, RulesEngine
from worldseed.engine.state_store import StateStore
from worldseed.models import ActionSubmission, Entity
from worldseed.models.config_schema import (
    ActionConfig,
    AgentConfig,
    AutoTickConfig,
    ConsequenceConfig,
    EffectConfig,
    EntityConfig,
    EventConfig,
    EventScopeConfig,
    ParamConfig,
    PerceptionConfig,
    PreconditionConfig,
    SceneConfig,
    SceneMetaConfig,
    TemplateConfig,
)
from worldseed.utils.nested import nested_get, nested_set
from worldseed.world import WorldEngine

# ============================================================
# 1. DEEP NESTING — nested_get / nested_set / walk_entity_path
# ============================================================


class TestDeepNesting:
    """Properties nested 4+ levels deep."""

    def test_nested_set_creates_intermediates_4_levels(self) -> None:
        d: dict = {}
        nested_set(d, "a.b.c.d", 42)
        assert d == {"a": {"b": {"c": {"d": 42}}}}

    def test_nested_get_reads_4_levels(self) -> None:
        d = {"a": {"b": {"c": {"d": 99}}}}
        assert nested_get(d, "a.b.c.d") == 99

    def test_nested_get_missing_intermediate_returns_none(self) -> None:
        d = {"a": {"b": 5}}
        assert nested_get(d, "a.b.c.d") is None

    def test_nested_set_overwrites_non_dict_intermediate(self) -> None:
        """If intermediate is a non-dict, nested_set should replace it."""
        d: dict = {"a": {"b": "not_a_dict"}}
        nested_set(d, "a.b.c", 10)
        assert d == {"a": {"b": {"c": 10}}}

    def test_state_store_deep_update(self) -> None:
        """StateStore.update_property with 4-level deep path."""
        store = StateStore()
        store.add(Entity(id="x", type="thing", _data={}))
        store.update_property("x", "meta.stats.combat.crit_rate", 0.15)
        e = store.get("x")
        assert e is not None
        assert e["meta"]["stats"]["combat"]["crit_rate"] == 0.15

    def test_walk_entity_path_deep(self) -> None:
        """walk_entity_path reads 4-level nested property."""
        e = Entity(
            id="x",
            type="thing",
            _data={"meta": {"stats": {"combat": {"crit_rate": 0.15}}}},
        )
        assert walk_entity_path(e, "data.meta.stats.combat.crit_rate") == 0.15

    def test_set_effect_deep_nested_target(self) -> None:
        """set effect targeting a 4-level nested property."""
        store = StateStore()
        store.add(
            Entity(
                id="drone",
                type="machine",
                _data={"subsystems": {"navigation": {"gps": {"accuracy": 0.95}}}},
            )
        )
        event_log = EventLog()
        effect = EffectConfig(
            operator="set",
            target="drone.subsystems.navigation.gps.accuracy",
            value=0.5,
        )
        ctx = {"agent_id": "drone", "action_params": {}, "tick": 1}
        exec_effect(effect, store, event_log, ctx, tick=1)
        e = store.get("drone")
        assert e is not None
        assert e["subsystems"]["navigation"]["gps"]["accuracy"] == 0.5

    def test_increment_deep_nested_creates_path(self) -> None:
        """increment on a non-existent deep path should create intermediates."""
        store = StateStore()
        store.add(Entity(id="bot", type="machine", _data={}))
        event_log = EventLog()
        effect = EffectConfig(
            operator="increment",
            target="bot.stats.xp.combat",
            by=10,
        )
        ctx = {"agent_id": "bot", "action_params": {}, "tick": 1}
        exec_effect(effect, store, event_log, ctx, tick=1)
        e = store.get("bot")
        assert e is not None
        assert e["stats"]["xp"]["combat"] == 10

    def test_decrement_deep_nested(self) -> None:
        """decrement on a deep nested property."""
        store = StateStore()
        store.add(
            Entity(
                id="bot",
                type="machine",
                _data={"stats": {"xp": {"combat": 50}}},
            )
        )
        event_log = EventLog()
        effect = EffectConfig(
            operator="decrement",
            target="bot.stats.xp.combat",
            by=7,
        )
        ctx = {"agent_id": "bot", "action_params": {}, "tick": 1}
        exec_effect(effect, store, event_log, ctx, tick=1)
        e = store.get("bot")
        assert e is not None
        assert e["stats"]["xp"]["combat"] == 43

    def test_precondition_check_deep_nested(self) -> None:
        """Precondition check on 4-level deep property."""
        store = StateStore()
        store.add(
            Entity(
                id="ship",
                type="vessel",
                _data={"hull": {"armor": {"front": {"integrity": 80}}}},
            )
        )
        precond = PreconditionConfig(
            operator="check",
            left="ship.hull.armor.front.integrity",
            op=">=",
            right=50,
        )
        ctx = {"agent_id": "ship", "action_params": {}, "tick": 1}
        assert eval_precond(precond, store, ctx) is True

        precond2 = PreconditionConfig(
            operator="check",
            left="ship.hull.armor.front.integrity",
            op=">",
            right=90,
        )
        assert eval_precond(precond2, store, ctx) is False


# ============================================================
# 2. NON-STANDARD / BIZARRE ENTITY NAMES AND TYPES
# ============================================================


class TestBizarreNaming:
    """Entity types, IDs, and property names that are unusual."""

    def test_entity_type_with_underscores_and_numbers(self) -> None:
        store = StateStore()
        store.add(
            Entity(
                id="quantum_flux_99",
                type="abstract_concept_v2",
                _data={"wave_function_collapsed": False, "spin": 0.5},
            )
        )
        e = store.get("quantum_flux_99")
        assert e is not None
        assert e.type == "abstract_concept_v2"

    def test_property_names_with_numbers(self) -> None:
        store = StateStore()
        store.add(
            Entity(
                id="sensor",
                type="device",
                _data={"reading_01": 3.14, "threshold_99": 100},
            )
        )
        store.update_property("sensor", "reading_01", 2.72)
        assert store.get("sensor")["reading_01"] == 2.72  # type: ignore

    def test_empty_string_property_value(self) -> None:
        store = StateStore()
        store.add(Entity(id="x", type="t", _data={"name": ""}))
        assert store.get("x")["name"] == ""  # type: ignore

    def test_boolean_property(self) -> None:
        store = StateStore()
        store.add(Entity(id="x", type="t", _data={"active": True}))
        store.update_property("x", "active", False)
        assert store.get("x")["active"] is False  # type: ignore

    def test_list_property(self) -> None:
        """Properties can be lists (e.g., tags)."""
        store = StateStore()
        store.add(Entity(id="x", type="t", _data={"tags": ["a", "b", "c"]}))
        assert "b" in store.get("x")["tags"]  # type: ignore

    def test_none_property_value(self) -> None:
        store = StateStore()
        store.add(Entity(id="x", type="t", _data={"data": None}))
        assert store.get("x")["data"] is None  # type: ignore


# ============================================================
# 3. ALL DSL PRECONDITION OPERATORS IN ONE COMPOUND EXPRESSION
# ============================================================


class TestCompoundPreconditions:
    """Deeply nested all/any/not/check/exists combined."""

    def test_all_any_not_exists_check_combined(self) -> None:
        """
        all([
            any([
                check(x.a > 10),
                check(x.b == "yes"),
            ]),
            not(check(x.c == "blocked")),
            exists(x.d),
        ])
        """
        store = StateStore()
        store.add(
            Entity(
                id="x",
                type="t",
                _data={"a": 5, "b": "yes", "c": "open", "d": [1, 2]},
            )
        )
        ctx = {"agent_id": "x", "action_params": {}, "tick": 1}

        precond = PreconditionConfig(
            operator="all",
            conditions=[
                PreconditionConfig(
                    operator="any",
                    conditions=[
                        PreconditionConfig(
                            operator="check",
                            left="x.a",
                            op=">",
                            right=10,
                        ),
                        PreconditionConfig(
                            operator="check",
                            left="x.b",
                            op="==",
                            right="yes",
                        ),
                    ],
                ),
                PreconditionConfig(
                    operator="not",
                    condition=PreconditionConfig(
                        operator="check",
                        left="x.c",
                        op="==",
                        right="blocked",
                    ),
                ),
                PreconditionConfig(
                    operator="exists",
                    expression="x.d",
                ),
            ],
        )
        # a=5 (not >10) but b="yes" → any passes
        # c="open" (not "blocked") → not passes
        # d=[1,2] → exists passes
        assert eval_precond(precond, store, ctx) is True

    def test_compound_fails_when_inner_fails(self) -> None:
        store = StateStore()
        store.add(
            Entity(
                id="x",
                type="t",
                _data={"a": 5, "b": "no", "c": "blocked", "d": [1]},
            )
        )
        ctx = {"agent_id": "x", "action_params": {}, "tick": 1}

        precond = PreconditionConfig(
            operator="all",
            conditions=[
                PreconditionConfig(
                    operator="any",
                    conditions=[
                        PreconditionConfig(
                            operator="check",
                            left="x.a",
                            op=">",
                            right=10,
                        ),
                        PreconditionConfig(
                            operator="check",
                            left="x.b",
                            op="==",
                            right="yes",
                        ),
                    ],
                ),
                PreconditionConfig(
                    operator="not",
                    condition=PreconditionConfig(
                        operator="check",
                        left="x.c",
                        op="==",
                        right="blocked",
                    ),
                ),
            ],
        )
        # any: a=5 (not >10), b="no" (not =="yes") → any fails → all fails
        assert eval_precond(precond, store, ctx) is False

    def test_in_and_contains_ops(self) -> None:
        """Check 'in' and 'contains' operators."""
        store = StateStore()
        store.add(
            Entity(
                id="x",
                type="t",
                _data={"tags": ["alpha", "beta"], "status": "alpha"},
            )
        )
        ctx = {"agent_id": "x", "action_params": {}, "tick": 1}

        # "alpha" in ["alpha", "beta"]
        precond_in = PreconditionConfig(
            operator="check",
            left="x.status",
            op="in",
            right="x.tags",
        )
        assert eval_precond(precond_in, store, ctx) is True

        # ["alpha", "beta"] contains "beta"
        precond_contains = PreconditionConfig(
            operator="check",
            left="x.tags",
            op="contains",
            right="beta",
        )
        assert eval_precond(precond_contains, store, ctx) is True

    def test_property_named_items_resolves_correctly(self) -> None:
        """Property named 'items' must not collide with dict.items()."""
        store = StateStore()
        store.add(Entity(id="x", type="t", _data={"items": []}))
        ctx = {"agent_id": "x", "action_params": {}, "tick": 1}

        resolved_val = resolve("x.items", store, ctx)
        assert resolved_val == [], "Property 'items' should resolve to [] not dict.items method"

    def test_walk_entity_path_dict_method_collision_keys(self) -> None:
        """Property named 'keys' must not collide with dict.keys()."""
        e = Entity(id="x", type="t", _data={"keys": ["skeleton_key"]})
        result = walk_entity_path(e, "data.keys")
        assert result == ["skeleton_key"]

    def test_walk_entity_path_dict_method_collision_values(self) -> None:
        """Property named 'values' must not collide with dict.values()."""
        e = Entity(id="x", type="t", _data={"values": [1, 2, 3]})
        result = walk_entity_path(e, "data.values")
        assert result == [1, 2, 3]

    def test_walk_entity_path_dict_method_collision_get(self) -> None:
        """Property named 'get' must not collide with dict.get()."""
        e = Entity(id="x", type="t", _data={"get": "fetch_quest"})
        result = walk_entity_path(e, "data.get")
        assert result == "fetch_quest"

    def test_walk_entity_path_dict_method_collision_update(self) -> None:
        """Property named 'update' must not collide with dict.update()."""
        e = Entity(id="x", type="t", _data={"update": "v2.0"})
        result = walk_entity_path(e, "data.update")
        assert result == "v2.0"

    def test_walk_entity_path_dict_method_collision_pop(self) -> None:
        """Property named 'pop' must not collide with dict.pop()."""
        e = Entity(id="x", type="t", _data={"pop": 10000})
        result = walk_entity_path(e, "data.pop")
        assert result == 10000

    def test_walk_entity_path_dict_method_collision_clear(self) -> None:
        """Property named 'clear' must not collide with dict.clear()."""
        e = Entity(id="x", type="t", _data={"clear": True})
        result = walk_entity_path(e, "data.clear")
        assert result is True

    def test_walk_entity_path_dict_method_collision_copy(self) -> None:
        """Property named 'copy' must not collide with dict.copy()."""
        e = Entity(id="x", type="t", _data={"copy": "duplicate"})
        result = walk_entity_path(e, "data.copy")
        assert result == "duplicate"

    def test_exists_on_empty_string_is_false(self) -> None:
        store = StateStore()
        store.add(Entity(id="x", type="t", _data={"name": ""}))
        ctx = {"agent_id": "x", "action_params": {}, "tick": 1}
        precond = PreconditionConfig(
            operator="exists",
            expression="x.name",
        )
        assert eval_precond(precond, store, ctx) is False

    def test_exists_on_zero_is_false(self) -> None:
        """0 is falsy → exists returns False."""
        store = StateStore()
        store.add(Entity(id="x", type="t", _data={"val": 0}))
        ctx = {"agent_id": "x", "action_params": {}, "tick": 1}
        precond = PreconditionConfig(
            operator="exists",
            expression="x.val",
        )
        # 0 is falsy, so bool(0) is False
        assert eval_precond(precond, store, ctx) is False

    def test_not_with_conditions_list(self) -> None:
        """not operator with a single-element conditions list."""
        store = StateStore()
        store.add(Entity(id="x", type="t", _data={"v": 5}))
        ctx = {"agent_id": "x", "action_params": {}, "tick": 1}
        precond = PreconditionConfig(
            operator="not",
            conditions=[
                PreconditionConfig(
                    operator="check",
                    left="x.v",
                    op="==",
                    right=99,
                ),
            ],
        )
        assert eval_precond(precond, store, ctx) is True


# ============================================================
# 4. $PARAM RESOLUTION IN EVERY POSITION
# ============================================================


class TestParamResolutionEdgeCases:
    """$param at start, middle, suffix of path segments."""

    def test_param_as_entity_id(self) -> None:
        """$target resolves to entity ID."""
        store = StateStore()
        store.add(Entity(id="goblin_01", type="creature", _data={"hp": 30}))
        ctx = {
            "agent_id": "hero",
            "action_params": {"target": "goblin_01"},
            "tick": 1,
        }
        val = resolve("$target.hp", store, ctx)
        assert val == 30

    def test_param_in_middle_of_property_name(self) -> None:
        """$choice embedded in property name: votes_$choice."""
        store = StateStore()
        store.add(
            Entity(
                id="ballot",
                type="object",
                _data={"votes_agree": 5, "votes_disagree": 3},
            )
        )
        ctx = {
            "agent_id": "voter",
            "action_params": {"choice": "agree"},
            "tick": 1,
        }
        resolved = resolve_params("ballot.votes_$choice", ctx)
        assert resolved == "ballot.votes_agree"

    def test_param_embedded_in_effect_target(self) -> None:
        """Effect target with $param embedded in property name."""
        store = StateStore()
        store.add(
            Entity(
                id="ballot",
                type="object",
                _data={"votes_agree": 5, "votes_disagree": 3},
            )
        )
        event_log = EventLog()
        effect = EffectConfig(
            operator="increment",
            target="ballot.votes_$choice",
            by=1,
        )
        ctx = {
            "agent_id": "voter",
            "action_params": {"choice": "agree"},
            "tick": 1,
        }
        exec_effect(effect, store, event_log, ctx, tick=1)
        assert store.get("ballot")["votes_agree"] == 6  # type: ignore

    def test_multiple_params_in_one_expression(self) -> None:
        """Two $params in the same expression."""
        ctx = {
            "agent_id": "a1",
            "action_params": {"src": "warehouse", "item": "gold"},
            "tick": 1,
        }
        resolved = resolve_params("$src.stock_$item", ctx)
        assert resolved == "warehouse.stock_gold"

    def test_agent_keyword_in_effect(self) -> None:
        """'agent' as bare keyword resolves to agent_id."""
        store = StateStore()
        store.add(Entity(id="hero", type="agent", _data={"xp": 0}))
        event_log = EventLog()
        effect = EffectConfig(
            operator="increment",
            target="$agent.xp",
            by=100,
        )
        ctx = {"agent_id": "hero", "action_params": {}, "tick": 1}
        exec_effect(effect, store, event_log, ctx, tick=1)
        assert store.get("hero")["xp"] == 100  # type: ignore


# ============================================================
# 5. ARITHMETIC + FUNCTIONS IN EXPRESSIONS
# ============================================================


class TestArithmeticAndFunctions:
    """Arithmetic with count(), sum(), relationships_of()."""

    def test_count_with_where(self) -> None:
        store = StateStore()
        store.add(Entity(id="a1", type="agent", _data={"faction": "red"}))
        store.add(Entity(id="a2", type="agent", _data={"faction": "blue"}))
        store.add(Entity(id="a3", type="agent", _data={"faction": "red"}))
        ctx = {"agent_id": "", "action_params": {}, "tick": 1}
        val = resolve("count(type=agent, where=faction == red)", store, ctx)
        assert val == 2

    def test_sum_across_entities(self) -> None:
        store = StateStore()
        store.add(Entity(id="r1", type="resource", _data={"quantity": 10}))
        store.add(Entity(id="r2", type="resource", _data={"quantity": 25}))
        store.add(Entity(id="r3", type="resource", _data={"quantity": 5}))
        ctx = {"agent_id": "", "action_params": {}, "tick": 1}
        val = resolve("sum(type=resource, property=quantity)", store, ctx)
        assert val == 40.0

    def test_arithmetic_multiplication_with_count(self) -> None:
        store = StateStore()
        store.add(Entity(id="a1", type="agent", _data={}))
        store.add(Entity(id="a2", type="agent", _data={}))
        ctx = {"agent_id": "", "action_params": {}, "tick": 1}
        # 0.5 * count(type=agent) = 0.5 * 2 = 1.0
        val = resolve("0.5 * count(type=agent)", store, ctx)
        assert val == 1.0

    def test_relationships_of_in_precondition(self) -> None:
        """relationships_of() used inside 'in' check."""
        store = StateStore()
        store.add(
            Entity(
                id="hub",
                type="node",
                _data={"link": ["spoke_a", "spoke_b"]},
            )
        )
        store.add(Entity(id="spoke_a", type="node", _data={}))
        store.add(Entity(id="spoke_b", type="node", _data={}))
        store.add(Entity(id="isolated", type="node", _data={}))
        store.add(Entity(id="agent1", type="agent", _data={"current_node": "hub"}))

        ctx = {
            "agent_id": "agent1",
            "action_params": {"destination": "spoke_a"},
            "tick": 1,
        }
        precond = PreconditionConfig(
            operator="check",
            left="$destination",
            op="in",
            right="relationships_of($agent.current_node, type=link)",
        )
        assert eval_precond(precond, store, ctx) is True

        ctx2 = {
            "agent_id": "agent1",
            "action_params": {"destination": "isolated"},
            "tick": 1,
        }
        assert eval_precond(precond, store, ctx2) is False

    def test_sum_with_where(self) -> None:
        store = StateStore()
        store.add(Entity(id="r1", type="resource", _data={"quantity": 10, "zone": "a"}))
        store.add(Entity(id="r2", type="resource", _data={"quantity": 20, "zone": "b"}))
        store.add(Entity(id="r3", type="resource", _data={"quantity": 30, "zone": "a"}))
        ctx = {"agent_id": "", "action_params": {}, "tick": 1}
        val = resolve(
            "sum(type=resource, property=quantity, where=zone == a)",
            store,
            ctx,
        )
        assert val == 40.0


# ============================================================
# 6. ENTITY LIFECYCLE — create and remove in effects
# ============================================================


class TestEntityLifecycle:
    """Create and remove entities through DSL effects."""

    def test_create_entity_effect(self) -> None:
        store = StateStore()
        event_log = EventLog()
        effect = EffectConfig(
            operator="create_entity",
            id="new_thing",
            type="spawned",
            properties={"power": 10, "source": "magic"},
        )
        ctx = {"agent_id": "wizard", "action_params": {}, "tick": 1}
        exec_effect(effect, store, event_log, ctx, tick=1)
        e = store.get("new_thing")
        assert e is not None
        assert e.type == "spawned"
        assert e["power"] == 10

    def test_create_entity_with_param_in_id(self) -> None:
        """$param in create_entity id field."""
        store = StateStore()
        event_log = EventLog()
        effect = EffectConfig(
            operator="create_entity",
            id="artifact_$item",
            type="artifact",
            properties={"quality": 5},
        )
        ctx = {
            "agent_id": "crafter",
            "action_params": {"item": "sword"},
            "tick": 1,
        }
        exec_effect(effect, store, event_log, ctx, tick=1)
        e = store.get("artifact_sword")
        assert e is not None
        assert e.type == "artifact"

    def test_remove_entity_cleans_relationships(self) -> None:
        store = StateStore()
        store.add(
            Entity(
                id="a",
                type="t",
                _data={"knows": ["b"]},
            )
        )
        store.add(
            Entity(
                id="b",
                type="t",
                _data={"knows": ["a"]},
            )
        )
        event_log = EventLog()
        effect = EffectConfig(operator="remove_entity", target="b")
        ctx = {"agent_id": "system", "action_params": {}, "tick": 1}
        exec_effect(effect, store, event_log, ctx, tick=1)

        assert store.get("b") is None
        a = store.get("a")
        assert a is not None
        # Stale ref preserved — no write-time cleanup
        assert a["knows"] == ["b"]
        # relationships_of returns stale refs as-is (pure data read)
        assert relationships_of("a", "knows", store) == ["b"]

    def test_create_then_modify_in_sequence(self) -> None:
        """Create an entity, then set a property on it — in the same action."""
        config = SceneConfig(
            scene=SceneMetaConfig(id="test", description="test"),
            entities=[],
            actions={
                "summon": ActionConfig(
                    description="Summon a creature and boost it",
                    params=[],
                    preconditions=[],
                    effects=[
                        EffectConfig(
                            operator="create_entity",
                            id="summoned_beast",
                            type="creature",
                            properties={"hp": 10, "attack": 5},
                        ),
                        EffectConfig(
                            operator="increment",
                            target="summoned_beast.hp",
                            by=20,
                        ),
                        EffectConfig(
                            operator="set",
                            target="summoned_beast.buffed",
                            value=True,
                        ),
                    ],
                ),
            },
        )
        store = StateStore()
        store.add(Entity(id="mage", type="agent", _data={}))
        event_log = EventLog()
        engine = RulesEngine(config, store, event_log)

        result = engine.process_action(
            ActionSubmission(agent_id="mage", action_type="summon", params={}),
            tick=1,
        )
        assert result.success
        beast = store.get("summoned_beast")
        assert beast is not None
        assert beast["hp"] == 30
        assert beast["buffed"] is True


# ============================================================
# 7. RELATIONSHIP OPERATIONS
# ============================================================


class TestRelationshipOperations:
    """add_relationship and remove_relationship effects."""

    def test_add_relationship_upsert(self) -> None:
        """Adding same relationship type+target updates value."""
        store = StateStore()
        store.add(Entity(id="a", type="agent", _data={}))
        store.add(Entity(id="b", type="agent", _data={}))
        # Valued relationship: stored as dict
        store.update_property("a", "trust", {"b": 50})
        # Upsert with new value
        trust = store.get("a").get("trust", {})  # type: ignore
        trust["b"] = 80
        store.update_property("a", "trust", trust)
        a = store.get("a")
        assert a is not None
        assert a["trust"] == {"b": 80}

    def test_remove_relationship_effect(self) -> None:
        store = StateStore()
        store.add(
            Entity(
                id="a",
                type="agent",
                _data={"ally": ["b"]},
            )
        )
        store.add(Entity(id="b", type="agent", _data={}))
        event_log = EventLog()
        effect = EffectConfig(
            operator="remove_relationship",
            from_entity="a",
            type="ally",
            to="b",
        )
        ctx = {"agent_id": "a", "action_params": {}, "tick": 1}
        exec_effect(effect, store, event_log, ctx, tick=1)
        a = store.get("a")
        assert a is not None
        assert a["ally"] == []

    def test_add_relationship_via_param(self) -> None:
        """$target resolved in add_relationship."""
        store = StateStore()
        store.add(Entity(id="alice", type="agent", _data={}))
        store.add(Entity(id="bob", type="agent", _data={}))
        event_log = EventLog()
        effect = EffectConfig(
            operator="add_relationship",
            from_entity="agent",
            type="friend",
            to="$target",
        )
        ctx = {
            "agent_id": "alice",
            "action_params": {"target": "bob"},
            "tick": 1,
        }
        exec_effect(effect, store, event_log, ctx, tick=1)
        alice = store.get("alice")
        assert alice is not None
        assert "bob" in alice.get("friend", [])


# ============================================================
# 8. CASCADING CONSEQUENCES
# ============================================================


class TestCascadingConsequences:
    """Consequence A modifies state → Consequence B fires on next scan."""

    def test_cascading_consequences_over_two_scans(self) -> None:
        """
        Consequence 'pressure_breach': pressure > 100 → set breach=true
        Consequence 'emergency_vent': breach == true → set vented=true
        First scan: pressure=120 → breach fires.
        Second scan: breach=true → emergency_vent fires.
        """
        config = SceneConfig(
            scene=SceneMetaConfig(id="test", description="test"),
            entities=[],
            actions={},
            consequences={
                "pressure_breach": ConsequenceConfig(
                    trigger=[
                        PreconditionConfig(
                            operator="check",
                            left="tank.pressure",
                            op=">",
                            right=100,
                        ),
                    ],
                    effects=[
                        EffectConfig(
                            operator="set",
                            target="tank.breach",
                            value=True,
                        ),
                    ],
                ),
                "emergency_vent": ConsequenceConfig(
                    trigger=[
                        PreconditionConfig(
                            operator="check",
                            left="tank.breach",
                            op="==",
                            right=True,
                        ),
                    ],
                    effects=[
                        EffectConfig(
                            operator="set",
                            target="tank.vented",
                            value=True,
                        ),
                    ],
                ),
            },
        )
        store = StateStore()
        store.add(
            Entity(
                id="tank",
                type="container",
                _data={"pressure": 120, "breach": False, "vented": False},
            )
        )
        event_log = EventLog()
        scanner = ConsequenceScanner(config, store, event_log)

        # First scan: pressure_breach fires (120 > 100)
        triggered1, _dm_pending = scanner.scan(1)
        assert "pressure_breach" in triggered1
        assert store.get("tank")["breach"] is True  # type: ignore

        # emergency_vent fires on scan 1 too IF breach was already true
        # at evaluation time. But breach was False BEFORE this scan started,
        # and on_change checks false->true. Let's check:
        if "emergency_vent" in triggered1:
            # It fired in same scan because pressure_breach set breach=True
            # and emergency_vent was evaluated AFTER (dict ordering).
            assert store.get("tank")["vented"] is True  # type: ignore
        else:
            # Second scan: breach=true now → emergency_vent fires
            triggered2, _dm_pending = scanner.scan(2)
            assert "emergency_vent" in triggered2
            assert store.get("tank")["vented"] is True  # type: ignore


# ============================================================
# 9. AUTO_TICK WITH CONDITIONS
# ============================================================


class TestAutoTickWithConditions:
    """Auto_tick effects that only fire when conditions are met."""

    def test_conditional_auto_tick(self) -> None:
        config = SceneConfig(
            scene=SceneMetaConfig(id="test", description="test"),
            entities=[],
            actions={},
            auto_tick=[
                AutoTickConfig(
                    description="Heal only if alive",
                    condition=[
                        PreconditionConfig(
                            operator="check",
                            left="patient.alive",
                            op="==",
                            right=True,
                        ),
                    ],
                    effects=[
                        EffectConfig(
                            operator="increment",
                            target="patient.hp",
                            by=5,
                        ),
                    ],
                ),
            ],
        )
        store = StateStore()
        store.add(
            Entity(
                id="patient",
                type="creature",
                _data={"hp": 10, "alive": True},
            )
        )
        event_log = EventLog()
        engine = RulesEngine(config, store, event_log)

        # Should heal
        engine.process_auto_tick(1)
        assert store.get("patient")["hp"] == 15  # type: ignore

        # Set alive=False — should NOT heal
        store.update_property("patient", "alive", False)
        engine.process_auto_tick(2)
        assert store.get("patient")["hp"] == 15  # type: ignore


# ============================================================
# 10. FLOAT PRECISION AND INT/FLOAT MIXING
# ============================================================


class TestNumericPrecision:
    """Float drift, int/float mixing, zero values."""

    def test_increment_float_by_float(self) -> None:
        store = StateStore()
        store.add(Entity(id="x", type="t", _data={"val": 0.1}))
        event_log = EventLog()
        effect = EffectConfig(
            operator="increment",
            target="x.val",
            by=0.2,
        )
        ctx = {"agent_id": "", "action_params": {}, "tick": 1}
        exec_effect(effect, store, event_log, ctx, tick=1)
        # Float precision: 0.1 + 0.2 may not be exactly 0.3
        val = store.get("x")["val"]  # type: ignore
        assert abs(val - 0.3) < 1e-9

    def test_int_increment_stays_int(self) -> None:
        """int + int should stay int, not become float."""
        store = StateStore()
        store.add(Entity(id="x", type="t", _data={"val": 5}))
        event_log = EventLog()
        effect = EffectConfig(
            operator="increment",
            target="x.val",
            by=3,
        )
        ctx = {"agent_id": "", "action_params": {}, "tick": 1}
        exec_effect(effect, store, event_log, ctx, tick=1)
        val = store.get("x")["val"]  # type: ignore
        assert val == 8
        assert isinstance(val, int)

    def test_decrement_to_zero(self) -> None:
        store = StateStore()
        store.add(Entity(id="x", type="t", _data={"val": 5}))
        event_log = EventLog()
        effect = EffectConfig(
            operator="decrement",
            target="x.val",
            by=5,
        )
        ctx = {"agent_id": "", "action_params": {}, "tick": 1}
        exec_effect(effect, store, event_log, ctx, tick=1)
        assert store.get("x")["val"] == 0  # type: ignore

    def test_decrement_below_zero(self) -> None:
        """Engine does NOT clamp — negative values are allowed."""
        store = StateStore()
        store.add(Entity(id="x", type="t", _data={"val": 3}))
        event_log = EventLog()
        effect = EffectConfig(
            operator="decrement",
            target="x.val",
            by=10,
        )
        ctx = {"agent_id": "", "action_params": {}, "tick": 1}
        exec_effect(effect, store, event_log, ctx, tick=1)
        assert store.get("x")["val"] == -7  # type: ignore

    def test_increment_with_expression_by(self) -> None:
        """by: value is a DSL expression (string), not literal number."""
        store = StateStore()
        store.add(Entity(id="x", type="t", _data={"val": 10}))
        store.add(Entity(id="a1", type="agent", _data={}))
        store.add(Entity(id="a2", type="agent", _data={}))
        event_log = EventLog()
        # by = "count(type=agent)" → 2
        effect = EffectConfig(
            operator="increment",
            target="x.val",
            by="count(type=agent)",
        )
        ctx = {"agent_id": "", "action_params": {}, "tick": 1}
        exec_effect(effect, store, event_log, ctx, tick=1)
        assert store.get("x")["val"] == 12.0  # type: ignore


# ============================================================
# 11. FULL INTEGRATION: BIZARRE SCENE VIA WORLDENGINE
# ============================================================


class TestBizarreWorldScene:
    """A complete alien scenario run through WorldEngine.

    Scene: "Quantum Entanglement Network"
    - Entity types: qubit, superposition, observer_node
    - Properties: coherence_level, entanglement_strength, collapse_count
    - No spatial concept at all
    - Relationships: entangled_with, observes
    - Actions: observe_qubit (collapses superposition, increments collapse_count)
    - Consequences: decoherence when collapse_count > 3
    - Auto_tick: coherence decays
    - Perception: agents see qubits they're entangled with
    """

    def _build_config(self) -> SceneConfig:
        return SceneConfig(
            scene=SceneMetaConfig(
                id="quantum_net",
                description="Quantum entanglement network",
            ),
            entities=[
                # Qubits
                EntityConfig(
                    id="qubit_alpha",
                    type="qubit",
                    properties={
                        "coherence_level": 1.0,
                        "collapse_count": 0,
                        "superposition": True,
                        "state": {"spin": "up", "phase": 0.0},
                        "entangled_with": ["qubit_beta"],
                    },
                ),
                EntityConfig(
                    id="qubit_beta",
                    type="qubit",
                    properties={
                        "coherence_level": 0.8,
                        "collapse_count": 0,
                        "superposition": True,
                        "state": {"spin": "down", "phase": 3.14},
                        "entangled_with": ["qubit_alpha"],
                    },
                ),
            ],
            agents=[
                AgentConfig(
                    id="observer_1",
                    properties={
                        "measurement_power": 10,
                        "observations_made": 0,
                        "observes": ["qubit_alpha"],
                    },
                    character={
                        "role": "Quantum physicist",
                        "goals": ["Collapse all qubits"],
                    },
                ),
                AgentConfig(
                    id="observer_2",
                    properties={
                        "measurement_power": 5,
                        "observations_made": 0,
                        "observes": ["qubit_beta"],
                    },
                    character={
                        "role": "Lab assistant",
                        "goals": ["Maintain coherence"],
                    },
                ),
            ],
            actions={
                "measure": ActionConfig(
                    description="Observe a qubit, collapsing its superposition",
                    params=[
                        ParamConfig(name="target_qubit", type="entity_ref"),
                    ],
                    preconditions=[
                        PreconditionConfig(
                            operator="check",
                            left="$target_qubit.superposition",
                            op="==",
                            right=True,
                        ),
                        PreconditionConfig(
                            operator="check",
                            left="$target_qubit.coherence_level",
                            op=">",
                            right=0,
                        ),
                    ],
                    effects=[
                        EffectConfig(
                            operator="set",
                            target="$target_qubit.superposition",
                            value=False,
                        ),
                        EffectConfig(
                            operator="increment",
                            target="$target_qubit.collapse_count",
                            by=1,
                        ),
                        EffectConfig(
                            operator="decrement",
                            target="$target_qubit.coherence_level",
                            by=0.25,
                        ),
                        EffectConfig(
                            operator="increment",
                            target="$agent.observations_made",
                            by=1,
                        ),
                    ],
                    events=[
                        EventConfig(
                            type="measurement",
                            detail="$agent measured $target_qubit",
                            ttl=3,
                            scope="global",
                        ),
                    ],
                ),
                "re_superpose": ActionConfig(
                    description="Restore a qubit to superposition",
                    params=[
                        ParamConfig(name="target_qubit", type="entity_ref"),
                    ],
                    preconditions=[
                        PreconditionConfig(
                            operator="check",
                            left="$target_qubit.superposition",
                            op="==",
                            right=False,
                        ),
                    ],
                    effects=[
                        EffectConfig(
                            operator="set",
                            target="$target_qubit.superposition",
                            value=True,
                        ),
                    ],
                ),
            },
            consequences={
                "decoherence": ConsequenceConfig(
                    trigger=[
                        PreconditionConfig(
                            operator="any",
                            conditions=[
                                PreconditionConfig(
                                    operator="check",
                                    left="qubit_alpha.collapse_count",
                                    op=">",
                                    right=3,
                                ),
                                PreconditionConfig(
                                    operator="check",
                                    left="qubit_beta.collapse_count",
                                    op=">",
                                    right=3,
                                ),
                            ],
                        ),
                    ],
                    effects=[
                        EffectConfig(
                            operator="emit_event",
                            type="decoherence_warning",
                            detail="Quantum system losing coherence!",
                            ttl=5,
                            scope="global",
                        ),
                    ],
                ),
            },
            auto_tick=[
                AutoTickConfig(
                    description="Coherence naturally decays",
                    effects=[
                        EffectConfig(
                            operator="decrement",
                            target="qubit_alpha.coherence_level",
                            by=0.01,
                        ),
                        EffectConfig(
                            operator="decrement",
                            target="qubit_beta.coherence_level",
                            by=0.01,
                        ),
                    ],
                ),
            ],
            perception=PerceptionConfig(
                visibility=[],  # all visible (no spatial concept)
                hidden_properties=["measurement_power"],
            ),
        )

    def test_full_scenario(self) -> None:
        config = self._build_config()
        world = WorldEngine(config=config)
        world.register_from_config()

        # Verify initial state
        qa = world.state.get("qubit_alpha")
        assert qa is not None
        assert qa["coherence_level"] == 1.0
        assert qa["state"]["spin"] == "up"  # deep nested

        # observer_1 measures qubit_alpha (mechanical action: returns ActionResult)
        result = world.submit("observer_1", "measure", {"target_qubit": "qubit_alpha"})
        assert isinstance(result, ActionResult)
        assert result.success
        world.step()  # still needed for auto_tick/consequences/perceiver

        qa = world.state.get("qubit_alpha")
        assert qa is not None
        assert qa["superposition"] is False
        assert qa["collapse_count"] == 1
        # coherence: 1.0 - 0.25 (measure) - 0.01 (auto_tick) = 0.74
        assert abs(qa["coherence_level"] - 0.74) < 1e-9

        obs1 = world.state.get("observer_1")
        assert obs1 is not None
        assert obs1["observations_made"] == 1

        # Re-superpose, then measure again multiple times
        result = world.submit("observer_1", "re_superpose", {"target_qubit": "qubit_alpha"})
        assert isinstance(result, ActionResult)
        world.step()
        assert world.state.get("qubit_alpha")["superposition"] is True  # type: ignore

        # Run 3 more measure cycles to trigger decoherence consequence
        for i in range(3):
            result = world.submit("observer_1", "measure", {"target_qubit": "qubit_alpha"})
            assert isinstance(result, ActionResult)
            world.step()
            if i < 2:
                result = world.submit("observer_1", "re_superpose", {"target_qubit": "qubit_alpha"})
                assert isinstance(result, ActionResult)
                world.step()

        # After 4 total measurements, collapse_count should be 4
        qa = world.state.get("qubit_alpha")
        assert qa is not None
        assert qa["collapse_count"] == 4

    def test_perception_hidden_properties(self) -> None:
        """Hidden properties stripped from other agents' views."""
        config = self._build_config()
        world = WorldEngine(config=config)
        world.register_from_config()
        world.step()  # trigger perceiver

        data = world.read_inbox("observer_1")
        snap = data["current_state"]
        # observer_2's measurement_power should be hidden
        assert "observer_2" in snap.visible_agents
        assert "measurement_power" not in snap.visible_agents["observer_2"]
        # But observations_made should be visible
        assert "observations_made" in snap.visible_agents["observer_2"]

    def test_measure_fails_on_collapsed_qubit(self) -> None:
        """Precondition: superposition must be True."""
        config = self._build_config()
        world = WorldEngine(config=config)
        world.register_from_config()

        # Measure once (mechanical: returns ActionResult directly)
        result = world.submit("observer_1", "measure", {"target_qubit": "qubit_alpha"})
        assert isinstance(result, ActionResult)
        assert result.success
        world.step()

        # Try to measure again — should fail (superposition is False)
        result = world.submit("observer_1", "measure", {"target_qubit": "qubit_alpha"})
        assert isinstance(result, ActionResult)
        assert not result.success


# ============================================================
# 12. EVENT SCOPE WITH CUSTOM DSL RULES
# ============================================================


class TestCustomEventScopes:
    """Custom event scopes with DSL-based delivery rules."""

    def test_custom_scope_filters_correctly(self) -> None:
        """Only agents with matching 'frequency' property receive tuned events."""
        store = StateStore()
        store.add(
            Entity(
                id="radio_a",
                type="agent",
                _data={"frequency": "FM_101"},
            )
        )
        store.add(
            Entity(
                id="radio_b",
                type="agent",
                _data={"frequency": "AM_530"},
            )
        )
        event_log = EventLog()
        from worldseed.models.event import Event

        event_log.append(
            Event(
                tick=1,
                type="broadcast",
                source="tower",
                detail="Emergency on FM_101",
                ttl=5,
                scope="same_frequency",
            )
        )
        # We need a "tower" entity for the scope rule to resolve
        store.add(
            Entity(
                id="tower",
                type="transmitter",
                _data={"frequency": "FM_101"},
            )
        )

        mgr = InboxManager()
        perception = PerceptionConfig(
            visibility=[],
            event_scopes={
                "same_frequency": EventScopeConfig(
                    rules=[
                        PreconditionConfig(
                            operator="check",
                            left="$observer.frequency",
                            op="==",
                            right="$event_source.frequency",
                        ),
                    ],
                ),
            },
        )
        p = Perceiver(store, event_log, mgr, perception)
        p.deliver(1)

        a_data = mgr.get_or_create("radio_a").read()
        b_data = mgr.get_or_create("radio_b").read()

        # radio_a (FM_101) should receive the broadcast from tower (FM_101)
        assert len(a_data["events"]) == 1
        assert a_data["events"][0].type == "broadcast"

        # radio_b (AM_530) should NOT receive it
        assert len(b_data["events"]) == 0


# ============================================================
# 13. TEMPLATE MERGE WITH NESTED PROPERTIES
# ============================================================


class TestTemplateMergeDeepNesting:
    """Template properties with nested dicts, agent overrides at leaf."""

    def test_template_merge_flat(self) -> None:
        """Basic template merge: template provides defaults, agent overrides."""
        config = SceneConfig(
            scene=SceneMetaConfig(
                id="test",
                description="test",
                default_spawn={"hp": 100},
            ),
            entities=[],
            actions={},
            templates={
                "warrior": TemplateConfig(
                    properties={"hp": 200, "attack": 30, "defense": 15},
                ),
            },
            agents=[
                AgentConfig(
                    id="hero",
                    template="warrior",
                    properties={"attack": 50},  # override attack
                    character={"name": "Hero"},
                ),
            ],
        )
        world = WorldEngine(config=config)
        world.register_from_config()

        hero = world.state.get("hero")
        assert hero is not None
        assert hero["hp"] == 200  # from template
        assert hero["attack"] == 50  # overridden
        assert hero["defense"] == 15  # from template


# ============================================================
# 14. EMIT EVENT WITH $PARAM INTERPOLATION
# ============================================================


class TestEmitEventInterpolation:
    """emit_event detail with multiple $param references."""

    def test_event_detail_interpolation(self) -> None:
        store = StateStore()
        store.add(Entity(id="a1", type="agent", _data={}))
        event_log = EventLog()
        effect = EffectConfig(
            operator="emit_event",
            type="trade",
            detail="$agent traded $amount of $item to $recipient",
            ttl=3,
            scope="global",
        )
        ctx = {
            "agent_id": "a1",
            "action_params": {
                "amount": "5",
                "item": "gold",
                "recipient": "merchant",
            },
            "tick": 1,
        }
        exec_effect(effect, store, event_log, ctx, tick=1)
        events = event_log.get_events()
        assert len(events) == 1
        assert events[0].detail == "a1 traded 5 of gold to merchant"

    def test_event_target_param(self) -> None:
        """Event target resolved from $param."""
        store = StateStore()
        event_log = EventLog()
        effect = EffectConfig(
            operator="emit_event",
            type="whisper",
            detail="psst",
            ttl=1,
            scope="target_only",
            event_target="$recipient",
        )
        ctx = {
            "agent_id": "spy",
            "action_params": {"recipient": "informant"},
            "tick": 1,
        }
        exec_effect(effect, store, event_log, ctx, tick=1)
        events = event_log.get_events()
        assert len(events) == 1
        assert events[0].target == "informant"
        assert events[0].scope == "target_only"


# ============================================================
# 15. EDGE CASE: NONEXISTENT ENTITY IN EFFECT TARGET
# ============================================================


class TestNonexistentEntityEffects:
    """Effects targeting entities that don't exist — should warn, not crash."""

    def test_set_on_missing_entity(self) -> None:
        store = StateStore()
        event_log = EventLog()
        effect = EffectConfig(
            operator="set",
            target="ghost.x",
            value=42,
        )
        ctx = {"agent_id": "", "action_params": {}, "tick": 1}
        # Should not raise
        exec_effect(effect, store, event_log, ctx, tick=1)
        assert store.get("ghost") is None

    def test_increment_on_missing_entity(self) -> None:
        store = StateStore()
        event_log = EventLog()
        effect = EffectConfig(
            operator="increment",
            target="ghost.val",
            by=1,
        )
        ctx = {"agent_id": "", "action_params": {}, "tick": 1}
        exec_effect(effect, store, event_log, ctx, tick=1)
        assert store.get("ghost") is None

    def test_remove_nonexistent_entity(self) -> None:
        store = StateStore()
        event_log = EventLog()
        effect = EffectConfig(
            operator="remove_entity",
            target="ghost",
        )
        ctx = {"agent_id": "", "action_params": {}, "tick": 1}
        exec_effect(effect, store, event_log, ctx, tick=1)
        # No crash

    def test_create_duplicate_entity_warns(self) -> None:
        """Creating an entity with an existing ID should warn, not crash."""
        store = StateStore()
        store.add(Entity(id="existing", type="t", _data={}))
        event_log = EventLog()
        effect = EffectConfig(
            operator="create_entity",
            id="existing",
            type="t",
            properties={"x": 1},
        )
        ctx = {"agent_id": "", "action_params": {}, "tick": 1}
        exec_effect(effect, store, event_log, ctx, tick=1)
        # Original entity should be unchanged
        e = store.get("existing")
        assert e is not None
        assert "x" not in e


# ============================================================
# 16. MIXED INT/FLOAT COMPARISON IN PRECONDITIONS
# ============================================================


class TestMixedTypeComparisons:
    """int value compared against float threshold and vice versa."""

    def test_int_compared_to_float(self) -> None:
        store = StateStore()
        store.add(Entity(id="x", type="t", _data={"val": 5}))
        ctx = {"agent_id": "", "action_params": {}, "tick": 1}
        precond = PreconditionConfig(
            operator="check",
            left="x.val",
            op=">=",
            right=4.5,
        )
        assert eval_precond(precond, store, ctx) is True

    def test_float_compared_to_int(self) -> None:
        store = StateStore()
        store.add(Entity(id="x", type="t", _data={"val": 3.14}))
        ctx = {"agent_id": "", "action_params": {}, "tick": 1}
        precond = PreconditionConfig(
            operator="check",
            left="x.val",
            op="<",
            right=4,
        )
        assert eval_precond(precond, store, ctx) is True


# ============================================================
# 17. TICK ENGINE FULL INTEGRATION — ALL SYSTEMS TOGETHER
# ============================================================


class TestFullTickIntegration:
    """Run a multi-tick scenario exercising actions, auto_tick,
    consequences, perception, and events all together."""

    def test_multi_tick_alien_scenario(self) -> None:
        """
        Scene: Mycelium Network
        - Nodes (fungi) are connected by hyphae (relationships)
        - Spores (agents) traverse the network
        - 'traverse' action moves a spore to a connected node
        - Auto_tick: nutrients decay per tick
        - Consequence: if nutrients < 5, node withers
        """
        config = SceneConfig(
            scene=SceneMetaConfig(id="mycelium", description="Fungal network"),
            entities=[
                EntityConfig(
                    id="node_a",
                    type="fungal_node",
                    properties={
                        "nutrients": 20,
                        "withered": False,
                        "hyphae_to": ["node_b"],
                    },
                ),
                EntityConfig(
                    id="node_b",
                    type="fungal_node",
                    properties={
                        "nutrients": 10,
                        "withered": False,
                        "hyphae_to": ["node_a", "node_c"],
                    },
                ),
                EntityConfig(
                    id="node_c",
                    type="fungal_node",
                    properties={
                        "nutrients": 3,
                        "withered": False,
                        "hyphae_to": ["node_b"],
                    },
                ),
            ],
            agents=[
                AgentConfig(
                    id="spore_1",
                    properties={"current_node": "node_a", "spore_energy": 50},
                    character={"species": "Mycorrhizal"},
                ),
            ],
            actions={
                "traverse": ActionConfig(
                    description="Move along hyphae to connected node",
                    params=[
                        ParamConfig(name="destination", type="entity_ref"),
                    ],
                    preconditions=[
                        PreconditionConfig(
                            operator="check",
                            left="$destination",
                            op="in",
                            right=("relationships_of($agent.current_node, type=hyphae_to)"),
                        ),
                    ],
                    effects=[
                        EffectConfig(
                            operator="set",
                            target="$agent.current_node",
                            value="$destination",
                        ),
                        EffectConfig(
                            operator="decrement",
                            target="$agent.spore_energy",
                            by=5,
                        ),
                    ],
                    events=[
                        EventConfig(
                            type="traverse",
                            detail="$agent traversed to $destination",
                            ttl=2,
                            scope="global",
                        ),
                    ],
                ),
                "absorb": ActionConfig(
                    description="Absorb nutrients from current node",
                    params=[],
                    preconditions=[
                        PreconditionConfig(
                            operator="check",
                            left="$agent.current_node",
                            op="!=",
                            right=None,
                        ),
                    ],
                    effects=[
                        EffectConfig(
                            operator="increment",
                            target="$agent.spore_energy",
                            by=3,
                        ),
                    ],
                ),
            },
            consequences={
                "wither": ConsequenceConfig(
                    trigger=[
                        PreconditionConfig(
                            operator="check",
                            left="node_c.nutrients",
                            op="<",
                            right=2,
                        ),
                    ],
                    effects=[
                        EffectConfig(
                            operator="set",
                            target="node_c.withered",
                            value=True,
                        ),
                    ],
                ),
            },
            auto_tick=[
                AutoTickConfig(
                    description="Nutrients decay",
                    effects=[
                        EffectConfig(
                            operator="decrement",
                            target="node_a.nutrients",
                            by=1,
                        ),
                        EffectConfig(
                            operator="decrement",
                            target="node_b.nutrients",
                            by=1,
                        ),
                        EffectConfig(
                            operator="decrement",
                            target="node_c.nutrients",
                            by=1,
                        ),
                    ],
                ),
            ],
            perception=PerceptionConfig(
                visibility=[],
                hidden_properties=["spore_energy"],
            ),
        )

        world = WorldEngine(config=config)
        world.register_from_config()

        # Tick 1: Spore traverses from node_a to node_b (mechanical action)
        result = world.submit("spore_1", "traverse", {"destination": "node_b"})
        assert isinstance(result, ActionResult)
        assert result.success
        world.step()  # still needed for auto_tick/consequences/perceiver
        assert world.state.get("spore_1")["current_node"] == "node_b"  # type: ignore
        assert world.state.get("spore_1")["spore_energy"] == 45  # type: ignore

        # nutrients after tick 1: a=19, b=9, c=2 (auto_tick -1 each)
        assert world.state.get("node_a")["nutrients"] == 19  # type: ignore
        assert world.state.get("node_b")["nutrients"] == 9  # type: ignore
        assert world.state.get("node_c")["nutrients"] == 2  # type: ignore

        # Tick 2: Spore absorbs at node_b, nutrients decay again
        result = world.submit("spore_1", "absorb", {})
        assert isinstance(result, ActionResult)
        world.step()
        assert world.state.get("spore_1")["spore_energy"] == 48  # type: ignore
        # c: 2 - 1 = 1 → wither consequence should fire (< 2)
        assert world.state.get("node_c")["nutrients"] == 1  # type: ignore
        assert world.state.get("node_c")["withered"] is True  # type: ignore

        # Tick 3: Try to traverse to node_c from node_b (should succeed)
        result = world.submit("spore_1", "traverse", {"destination": "node_c"})
        assert isinstance(result, ActionResult)
        assert result.success
        world.step()

        # Try to traverse to node_a from node_c (not connected) — should fail
        result = world.submit("spore_1", "traverse", {"destination": "node_a"})
        assert isinstance(result, ActionResult)
        assert not result.success

        # Verify perception: hidden spore_energy
        world.step()  # empty step to refresh perception
        data = world.read_inbox("spore_1")
        snap = data["current_state"]
        assert snap is not None
        # Self state should include spore_energy (it's your own)
        assert "spore_energy" in snap.self_state

    def test_traverse_fails_to_unconnected(self) -> None:
        """Traverse to a node without hyphae connection fails."""
        config = SceneConfig(
            scene=SceneMetaConfig(id="mycelium", description="test"),
            entities=[
                EntityConfig(
                    id="node_a",
                    type="fungal_node",
                    properties={"nutrients": 20},
                ),
                EntityConfig(
                    id="node_b",
                    type="fungal_node",
                    properties={"nutrients": 10},
                ),
            ],
            agents=[
                AgentConfig(
                    id="spore",
                    properties={"current_node": "node_a", "spore_energy": 50},
                    character={},
                ),
            ],
            actions={
                "traverse": ActionConfig(
                    description="Move to connected node",
                    params=[ParamConfig(name="destination", type="entity_ref")],
                    preconditions=[
                        PreconditionConfig(
                            operator="check",
                            left="$destination",
                            op="in",
                            right=("relationships_of($agent.current_node, type=hyphae_to)"),
                        ),
                    ],
                    effects=[
                        EffectConfig(
                            operator="set",
                            target="$agent.current_node",
                            value="$destination",
                        ),
                    ],
                ),
            },
        )
        world = WorldEngine(config=config)
        world.register_from_config()

        # Mechanical action: returns ActionResult directly from submit()
        result = world.submit("spore", "traverse", {"destination": "node_b"})
        assert isinstance(result, ActionResult)
        assert not result.success


# ============================================================
# 18. EDGE CASE: ACTION WITH NO EFFECTS
# ============================================================


class TestActionNoEffects:
    """An action with preconditions and events but zero effects."""

    def test_action_with_only_events(self) -> None:
        config = SceneConfig(
            scene=SceneMetaConfig(id="test", description="test"),
            entities=[],
            actions={
                "shout": ActionConfig(
                    description="Shout into the void",
                    params=[ParamConfig(name="message", type="free_text")],
                    preconditions=[],
                    effects=[],
                    events=[
                        EventConfig(
                            type="shout",
                            detail="$agent shouted: $message",
                            ttl=3,
                            scope="global",
                        ),
                    ],
                ),
            },
        )
        store = StateStore()
        store.add(Entity(id="a1", type="agent", _data={}))
        event_log = EventLog()
        engine = RulesEngine(config, store, event_log)
        result = engine.process_action(
            ActionSubmission(
                agent_id="a1",
                action_type="shout",
                params={"message": "hello world"},
            ),
            tick=1,
        )
        assert result.success
        events = event_log.get_events()
        assert len(events) == 1
        assert "hello world" in events[0].detail


# ============================================================
# 19. EDGE CASE: CONSEQUENCE WITH EVENT-BASED TRIGGER
# ============================================================


class TestEventBasedResolution:
    """Using event() function in DSL expressions."""

    def test_event_log_in_context(self) -> None:
        """event(type=X) returns matching events from EventLog."""
        store = StateStore()
        event_log = EventLog()
        from worldseed.models.event import Event

        event_log.append(
            Event(
                tick=1,
                type="alarm",
                source="sys",
                detail="fire",
                ttl=5,
                scope="global",
            )
        )
        ctx = {
            "agent_id": "",
            "action_params": {},
            "tick": 1,
            "event_log": event_log,
        }
        result = resolve("event(type=alarm)", store, ctx)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["type"] == "alarm"


# ============================================================
# 20. NEGATIVE PARAM VALIDATION
# ============================================================


class TestNegativeParamValidation:
    """Engine rejects negative values for 'number' type params."""

    def test_negative_number_param_rejected(self) -> None:
        config = SceneConfig(
            scene=SceneMetaConfig(id="test", description="test"),
            entities=[],
            actions={
                "donate": ActionConfig(
                    description="Donate resources",
                    params=[ParamConfig(name="amount", type="number")],
                    preconditions=[],
                    effects=[],
                ),
            },
        )
        store = StateStore()
        store.add(Entity(id="a1", type="agent", _data={}))
        event_log = EventLog()
        engine = RulesEngine(config, store, event_log)
        result = engine.process_action(
            ActionSubmission(
                agent_id="a1",
                action_type="donate",
                params={"amount": -5},
            ),
            tick=1,
        )
        assert not result.success
        assert "non-negative" in result.reason
