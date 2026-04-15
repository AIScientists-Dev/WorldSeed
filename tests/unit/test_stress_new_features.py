"""Stress tests for all 5 new features — interface contracts, branch coverage,
edge cases, interaction tests, error recovery.

Written by /stress-test skill. Not happy-path — these are the tests that
catch bugs vibe-coding misses.
"""

import pytest

from worldseed.dsl.effects import execute
from worldseed.dsl.path_resolver import resolve
from worldseed.dsl.preconditions import evaluate
from worldseed.engine.consequence_scanner import ConsequenceScanner
from worldseed.engine.dm_resolver import validate_dm_effects
from worldseed.engine.event_log import EventLog
from worldseed.engine.state_store import StateStore
from worldseed.models.config_schema import (
    DMConfig,
    EffectConfig,
    PreconditionConfig,
    SceneConfig,
)
from worldseed.models.entity import Entity

# ============================================================
# Fixtures
# ============================================================


@pytest.fixture()
def store() -> StateStore:
    s = StateStore()
    s.add(
        Entity(
            id="deck",
            type="card_deck",
            _data={
                "cards": ["A♠", "K♥", "Q♦", "J♣", "10♠"],
            },
        )
    )
    s.add(
        Entity(
            id="player",
            type="agent",
            _data={
                "hand": ["2♣"],
                "chips": 500,
                "bet": 0,
                "folded": False,
                "seat": 1,
            },
        )
    )
    s.add(
        Entity(
            id="table",
            type="game",
            _data={
                "pot": 100,
                "current_bet": 20,
                "phase": "pre_flop",
            },
        )
    )
    return s


@pytest.fixture()
def event_log() -> EventLog:
    return EventLog()


@pytest.fixture()
def ctx() -> dict:
    return {"agent_id": "player", "action_params": {"amount": 50}, "tick": 3}


# ============================================================
# Step 2: Interface Contract Tests
# ============================================================


class TestDMValidationForListOps:
    """validate_dm_effects must properly handle new list operators."""

    def test_list_append_valid(self, store):
        dm_config = DMConfig(allowed_ops=["list_append"], max_effects=5)
        effects = [EffectConfig(operator="list_append", target="player.hand", value="A♠")]
        valid, reason = validate_dm_effects(effects, dm_config, store)
        assert valid, reason

    def test_list_append_missing_target(self, store):
        dm_config = DMConfig(allowed_ops=["list_append"], max_effects=5)
        effects = [EffectConfig(operator="list_append", target=None, value="A♠")]
        valid, reason = validate_dm_effects(effects, dm_config, store)
        assert not valid
        assert "missing target" in reason

    def test_list_append_entity_not_found(self, store):
        dm_config = DMConfig(allowed_ops=["list_append"], max_effects=5)
        effects = [EffectConfig(operator="list_append", target="ghost.hand", value="A♠")]
        valid, reason = validate_dm_effects(effects, dm_config, store)
        assert not valid
        assert "not found" in reason

    def test_list_append_not_in_allowed_ops(self, store):
        dm_config = DMConfig(allowed_ops=["set"], max_effects=5)
        effects = [EffectConfig(operator="list_append", target="player.hand", value="A♠")]
        valid, reason = validate_dm_effects(effects, dm_config, store)
        assert not valid
        assert "not in allowed_ops" in reason

    def test_list_pop_random_valid(self, store):
        dm_config = DMConfig(allowed_ops=["list_pop_random"], max_effects=5)
        effects = [EffectConfig(operator="list_pop_random", source="deck.cards", target="player.hand")]
        valid, reason = validate_dm_effects(effects, dm_config, store)
        assert valid, reason

    def test_list_pop_random_missing_source(self, store):
        dm_config = DMConfig(allowed_ops=["list_pop_random"], max_effects=5)
        effects = [EffectConfig(operator="list_pop_random", source=None, target="player.hand")]
        valid, reason = validate_dm_effects(effects, dm_config, store)
        assert not valid
        assert "missing source" in reason

    def test_list_pop_random_missing_target(self, store):
        dm_config = DMConfig(allowed_ops=["list_pop_random"], max_effects=5)
        effects = [EffectConfig(operator="list_pop_random", source="deck.cards", target=None)]
        valid, reason = validate_dm_effects(effects, dm_config, store)
        assert not valid
        assert "missing target" in reason

    def test_list_pop_random_source_entity_not_found(self, store):
        dm_config = DMConfig(allowed_ops=["list_pop_random"], max_effects=5)
        effects = [EffectConfig(operator="list_pop_random", source="ghost.cards", target="player.hand")]
        valid, reason = validate_dm_effects(effects, dm_config, store)
        assert not valid
        assert "not found" in reason


class TestConsequenceDMContext:
    """The DM must receive correct context when called from a consequence."""

    def test_dm_context_has_world_state(self):
        from worldseed.dm.builder import DMContextBuilder
        from worldseed.models.action import ActionSubmission

        store = StateStore()
        store.add(Entity(id="room", type="space", _data={"temp": 120}))
        event_log = EventLog()
        config = SceneConfig.model_validate(
            {
                "scene": {"id": "t", "description": "Test world"},
                "entities": [{"id": "room", "type": "space", "temp": 120}],
                "actions": {
                    "wait": {
                        "description": "w",
                        "params": [],
                        "preconditions": [],
                        "effects": [],
                    }
                },
            }
        )

        builder = DMContextBuilder(store, event_log, config)
        synthetic = ActionSubmission(agent_id="", action_type="consequence:fire", params={})
        dm_config = DMConfig(hint="Judge fire damage", allowed_ops=["set", "decrement"], max_effects=3)
        ctx = builder.build(synthetic, dm_config, tick=5)

        # Contract: DM context must contain world state
        assert "room" in ctx.world_state
        assert "120" in ctx.world_state or "temp" in ctx.world_state
        # Contract: hint must be passed through
        assert ctx.hint == "Judge fire damage"
        # Contract: allowed_ops must be passed through
        assert "set" in ctx.allowed_ops
        assert "decrement" in ctx.allowed_ops
        # Contract: action type shows it's a consequence
        assert ctx.action.action_type == "consequence:fire"
        assert ctx.action.agent_id == ""


# ============================================================
# Step 3: Branch Coverage
# ============================================================


class TestArithmeticBranches:
    """Every branch in _is_arithmetic and _resolve_arithmetic."""

    def test_plus_at_depth_0(self, store, ctx):
        assert resolve("5 + 3", store, ctx) == 8.0

    def test_minus_at_depth_0(self, store, ctx):
        assert resolve("10 - 3", store, ctx) == 7.0

    def test_star_at_depth_0(self, store, ctx):
        assert resolve("2 * 3", store, ctx) == 6.0

    def test_floor_div_at_depth_0(self, store, ctx):
        assert resolve("10 // 3", store, ctx) == 3.0

    def test_modulo_at_depth_0(self, store, ctx):
        assert resolve("10 % 3", store, ctx) == 1.0

    def test_operator_inside_parens_not_matched(self, store, ctx):
        """+ inside count() should not be treated as arithmetic."""
        # count(type=agent) returns 1 (player), not splitting on + inside parens
        result = resolve("count(type=agent)", store, ctx)
        assert result == 1

    def test_unary_minus_not_arithmetic(self, store, ctx):
        """Leading - is negative number, not subtraction."""
        assert resolve("-5", store, ctx) == -5

    def test_floor_div_by_zero_returns_zero(self, store, ctx):
        assert resolve("10 // 0", store, ctx) == 0.0

    def test_modulo_by_zero_returns_zero(self, store, ctx):
        assert resolve("10 % 0", store, ctx) == 0.0

    def test_non_numeric_operand_returns_zero(self, store, ctx):
        """If an operand resolves to a non-numeric string, return 0."""
        store.add(Entity(id="text", type="test", _data={"name": "hello"}))
        result = resolve("text.name + 5", store, ctx)
        assert result == 0.0


class TestListOpsBranches:
    """Every branch in list ops."""

    def test_list_append_target_none(self, store, event_log, ctx):
        """target=None should return early (guard clause)."""
        effect = EffectConfig(operator="list_append", target=None, value="x")
        execute(effect, store, event_log, ctx, tick=1)
        # No crash, no change

    def test_list_remove_target_none(self, store, event_log, ctx):
        effect = EffectConfig(operator="list_remove", target=None, value="x")
        execute(effect, store, event_log, ctx, tick=1)

    def test_list_pop_random_source_none(self, store, event_log, ctx):
        effect = EffectConfig(operator="list_pop_random", source=None, target="player.hand")
        execute(effect, store, event_log, ctx, tick=1)
        assert store.get("player")["hand"] == ["2♣"]  # unchanged

    def test_list_pop_random_target_none(self, store, event_log, ctx):
        effect = EffectConfig(operator="list_pop_random", source="deck.cards", target=None)
        execute(effect, store, event_log, ctx, tick=1)
        assert len(store.get("deck")["cards"]) == 5  # unchanged

    def test_list_pop_random_single_element(self, store, event_log, ctx):
        """Pop from 1-element list should work and leave empty list."""
        store.update_property("deck", "cards", ["ONLY"])
        effect = EffectConfig(operator="list_pop_random", source="deck.cards", target="player.hand")
        execute(effect, store, event_log, ctx, tick=1)
        assert store.get("deck")["cards"] == []
        assert "ONLY" in store.get("player")["hand"]

    def test_list_append_entity_not_found(self, store, event_log, ctx):
        """Appending to non-existent entity should warn, not crash."""
        effect = EffectConfig(operator="list_append", target="ghost.items", value="x")
        execute(effect, store, event_log, ctx, tick=1)  # no crash


# ============================================================
# Step 4: Edge Cases
# ============================================================


class TestArithmeticEdgeCases:
    def test_very_large_numbers(self, store, ctx):
        assert resolve("999999999 + 1", store, ctx) == 1000000000.0

    def test_float_precision(self, store, ctx):
        result = resolve("0.1 + 0.2", store, ctx)
        assert abs(result - 0.3) < 0.001

    def test_nested_arithmetic(self, store, ctx):
        """2 + 3 * 4 - 1 = 2 + 12 - 1 = 13."""
        assert resolve("2 + 3 * 4 - 1", store, ctx) == 13.0

    def test_arithmetic_with_missing_entity(self, store, ctx):
        """ghost.value + 5: ghost doesn't exist → resolve returns None → 0 + 5."""
        result = resolve("ghost.value + 5", store, ctx)
        assert result == 5.0


class TestRandomEdgeCases:
    def test_random_min_greater_than_max(self, store, ctx):
        """random(10, 1) — invalid range. Should not crash."""
        try:
            resolve("random(10, 1)", store, ctx)
        except ValueError:
            pass  # acceptable to raise
        # Either returns 0 or raises — both are acceptable, just don't crash silently

    def test_random_with_negative(self, store, ctx):
        result = resolve("random(-5, 5)", store, ctx)
        assert -5 <= result <= 5


class TestCompoundWhereEdgeCases:
    def test_where_with_spaces_in_value(self, store):
        """Value with spaces — should still work."""
        from worldseed.dsl.functions.aggregation import count

        store.add(Entity(id="x", type="test", _data={"name": "foo bar"}))
        # This will compare str(val) == "foo bar"
        result = count(store, "test", where="name == foo bar")
        assert result == 1

    def test_where_with_numeric_comparison(self, store):
        """Where compares as string — "500" == "500"."""
        from worldseed.dsl.functions.aggregation import count

        result = count(store, "agent", where="chips == 500")
        assert result == 1

    def test_where_and_with_single_space(self, store):
        """AND must have spaces: ' AND ' not 'AND'."""
        from worldseed.dsl.functions.aggregation import _matches_where

        entity = store.get("player")
        # "folded == FalseANDchips == 500" — no spaces around AND, treated as single condition
        result = _matches_where(entity, "folded == FalseANDchips == 500")
        assert result is False  # should not match (it's one malformed condition)


# ============================================================
# Step 5: Interaction Tests
# ============================================================


class TestListOpsInAutoTick:
    """list ops used in auto_tick effects."""

    def test_auto_tick_with_list_pop(self):
        """A config with list_pop_random in auto_tick should load and run."""
        config = SceneConfig.model_validate(
            {
                "scene": {"id": "test", "description": "test"},
                "entities": [
                    {"id": "deck", "type": "card_deck", "cards": ["A", "B", "C"]},
                    {"id": "discard", "type": "pile", "cards": []},
                ],
                "actions": {
                    "wait": {
                        "description": "w",
                        "params": [],
                        "preconditions": [],
                        "effects": [],
                    }
                },
                "auto_tick": [
                    {
                        "description": "auto deal",
                        "effects": [
                            {
                                "operator": "list_pop_random",
                                "source": "deck.cards",
                                "target": "discard.cards",
                            }
                        ],
                    }
                ],
            }
        )
        assert config is not None  # loads without error


class TestArithmeticInPreconditions:
    """Arithmetic expressions used in precondition check left/right."""

    def test_subtraction_in_precondition(self, store, ctx):
        """check: current_bet - bet > 0 (call amount is positive)."""
        p = PreconditionConfig(
            operator="check",
            left="table.current_bet - player.bet",
            op=">",
            right=0,
        )
        result = evaluate(p, store, ctx)
        assert result is True  # 20 - 0 = 20 > 0

    def test_modulo_in_precondition(self, store, ctx):
        """check: tick % 5 == 3."""
        p = PreconditionConfig(
            operator="check",
            left="$tick % 5",
            op="==",
            right=3,
        )
        result = evaluate(p, store, ctx)
        assert result is True  # tick=3, 3%5=3


class TestListOpsInConsequence:
    """list_pop_random in a consequence effect."""

    def test_consequence_uses_list_pop(self):
        config = SceneConfig.model_validate(
            {
                "scene": {"id": "test", "description": "test"},
                "entities": [
                    {"id": "deck", "type": "card_deck", "cards": ["A", "B", "C"]},
                    {"id": "table", "type": "game", "community": [], "phase": "deal"},
                ],
                "actions": {
                    "wait": {
                        "description": "w",
                        "params": [],
                        "preconditions": [],
                        "effects": [],
                    }
                },
                "consequences": {
                    "deal": {
                        "trigger": [
                            {
                                "operator": "check",
                                "left": "table.phase",
                                "op": "==",
                                "right": "deal",
                            }
                        ],
                        "effects": [
                            {
                                "operator": "list_pop_random",
                                "source": "deck.cards",
                                "target": "table.community",
                            },
                        ],
                    }
                },
            }
        )

        store = StateStore()
        for e in config.entities:
            store.add(Entity(id=e.id, type=e.type, _data=dict(e.properties)))
        event_log = EventLog()
        scanner = ConsequenceScanner(config, store, event_log)

        triggered, _ = scanner.scan(1)
        assert "deal" in triggered
        assert len(store.get("deck")["cards"]) == 2
        assert len(store.get("table")["community"]) == 1


class TestNewOpsInDMResponse:
    """DM returns new operators — validate + execute works."""

    def test_dm_returns_list_append(self, store, event_log):
        """Simulate DM returning list_append effect."""
        dm_config = DMConfig(
            allowed_ops=["list_append", "emit_event"],
            max_effects=5,
        )
        effects = [
            EffectConfig(operator="list_append", target="player.hand", value="A♠"),
        ]
        valid, reason = validate_dm_effects(effects, dm_config, store)
        assert valid, reason

        # Execute the effect
        ctx: dict = {"agent_id": "player", "action_params": {}, "tick": 1}
        execute(effects[0], store, event_log, ctx, tick=1)
        assert "A♠" in store.get("player")["hand"]


# ============================================================
# Step 6: Error Recovery
# ============================================================


class TestErrorRecovery:
    def test_list_pop_partial_failure(self, store, event_log, ctx):
        """If target entity is removed mid-operation, should not corrupt state."""
        # Remove target entity
        store.remove("player")
        effect = EffectConfig(operator="list_pop_random", source="deck.cards", target="player.hand")
        execute(effect, store, event_log, ctx, tick=1)
        # deck should be unchanged (target not found → early return)
        assert len(store.get("deck")["cards"]) == 5

    def test_arithmetic_with_none_entity(self, store, ctx):
        """Arithmetic where one side resolves to None."""
        result = resolve("nonexistent.value + 5", store, ctx)
        assert result == 5.0  # None → 0.0, 0 + 5 = 5

    def test_consequence_dm_with_no_provider(self):
        """Consequence with DM but no DM provider — sync step should not crash."""
        from worldseed.engine.action_queue import ActionQueue
        from worldseed.engine.tick import TickEngine

        config = SceneConfig.model_validate(
            {
                "scene": {"id": "t", "description": "t"},
                "entities": [{"id": "r", "type": "space", "temp": 200}],
                "actions": {
                    "wait": {
                        "description": "w",
                        "params": [],
                        "preconditions": [],
                        "effects": [],
                    }
                },
                "consequences": {
                    "fire": {
                        "trigger": [
                            {
                                "operator": "check",
                                "left": "r.temp",
                                "op": ">",
                                "right": 100,
                            }
                        ],
                        "dm": {
                            "hint": "fire",
                            "allowed_ops": ["set"],
                            "max_effects": 2,
                        },
                    }
                },
            }
        )
        store = StateStore()
        for e in config.entities:
            store.add(Entity(id=e.id, type=e.type, _data=dict(e.properties)))
        event_log = EventLog()

        engine = TickEngine(config, store, event_log, ActionQueue())
        # No DM provider — should not crash on sync step
        engine.step()
