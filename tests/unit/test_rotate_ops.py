"""Tests for the rotate DSL effect operator."""

import pytest

from worldseed.dsl.effects import execute
from worldseed.engine.event_log import EventLog
from worldseed.engine.state_store import StateStore
from worldseed.models.config_schema import EffectConfig
from worldseed.models.entity import Entity


@pytest.fixture()
def store() -> StateStore:
    s = StateStore()
    s.add(
        Entity(
            id="game",
            type="game_state",
            _data={
                "active_role": "werewolf",
                "role_order": ["werewolf", "seer", "witch", "hunter"],
                "dead_roles": [],
            },
        )
    )
    s.add(Entity(id="empty", type="test", _data={"seq": [], "current": "x"}))
    s.add(Entity(id="not_list", type="test", _data={"seq": 42, "current": "x"}))
    s.add(
        Entity(
            id="single",
            type="test",
            _data={"seq": ["only"], "current": "only"},
        )
    )
    s.add(
        Entity(
            id="agent_a",
            type="agent",
            _data={"active_turn": "a", "turn_order": ["a", "b", "c"]},
        )
    )
    return s


@pytest.fixture()
def event_log() -> EventLog:
    return EventLog()


@pytest.fixture()
def ctx() -> dict:
    return {"agent_id": "agent_a", "action_params": {}, "tick": 1}


class TestRotate:
    def test_basic_advance(self, store, event_log, ctx):
        effect = EffectConfig(
            operator="rotate",
            target="game.active_role",
            sequence="game.role_order",
        )
        execute(effect, store, event_log, ctx, tick=1)
        assert store.get("game")["active_role"] == "seer"

    def test_wrap_around(self, store, event_log, ctx):
        store.update_property("game", "active_role", "hunter")
        effect = EffectConfig(
            operator="rotate",
            target="game.active_role",
            sequence="game.role_order",
        )
        execute(effect, store, event_log, ctx, tick=1)
        assert store.get("game")["active_role"] == "werewolf"

    def test_skip_single(self, store, event_log, ctx):
        store.update_property("game", "dead_roles", ["seer"])
        effect = EffectConfig(
            operator="rotate",
            target="game.active_role",
            sequence="game.role_order",
            skip="game.dead_roles",
        )
        execute(effect, store, event_log, ctx, tick=1)
        assert store.get("game")["active_role"] == "witch"

    def test_skip_multiple(self, store, event_log, ctx):
        store.update_property("game", "dead_roles", ["seer", "witch"])
        effect = EffectConfig(
            operator="rotate",
            target="game.active_role",
            sequence="game.role_order",
            skip="game.dead_roles",
        )
        execute(effect, store, event_log, ctx, tick=1)
        assert store.get("game")["active_role"] == "hunter"

    def test_all_skipped(self, store, event_log, ctx):
        store.update_property("game", "dead_roles", ["werewolf", "seer", "witch", "hunter"])
        effect = EffectConfig(
            operator="rotate",
            target="game.active_role",
            sequence="game.role_order",
            skip="game.dead_roles",
        )
        execute(effect, store, event_log, ctx, tick=1)
        # No change — all skipped
        assert store.get("game")["active_role"] == "werewolf"

    def test_value_override(self, store, event_log, ctx):
        # active_role is "werewolf" but value overrides start position to "seer"
        effect = EffectConfig(
            operator="rotate",
            target="game.active_role",
            sequence="game.role_order",
            value="seer",
        )
        execute(effect, store, event_log, ctx, tick=1)
        assert store.get("game")["active_role"] == "witch"

    def test_current_not_in_sequence(self, store, event_log, ctx):
        store.update_property("game", "active_role", "unknown")
        effect = EffectConfig(
            operator="rotate",
            target="game.active_role",
            sequence="game.role_order",
        )
        execute(effect, store, event_log, ctx, tick=1)
        # Not in sequence → starts from -1, first non-skipped = "werewolf"
        assert store.get("game")["active_role"] == "werewolf"

    def test_skip_with_wrap(self, store, event_log, ctx):
        # Current = witch, hunter is dead → wraps to werewolf
        store.update_property("game", "active_role", "witch")
        store.update_property("game", "dead_roles", ["hunter"])
        effect = EffectConfig(
            operator="rotate",
            target="game.active_role",
            sequence="game.role_order",
            skip="game.dead_roles",
        )
        execute(effect, store, event_log, ctx, tick=1)
        assert store.get("game")["active_role"] == "werewolf"

    def test_empty_sequence(self, store, event_log, ctx):
        effect = EffectConfig(
            operator="rotate",
            target="empty.current",
            sequence="empty.seq",
        )
        execute(effect, store, event_log, ctx, tick=1)
        assert store.get("empty")["current"] == "x"

    def test_not_a_list(self, store, event_log, ctx):
        effect = EffectConfig(
            operator="rotate",
            target="not_list.current",
            sequence="not_list.seq",
        )
        execute(effect, store, event_log, ctx, tick=1)
        assert store.get("not_list")["current"] == "x"

    def test_no_skip_field(self, store, event_log, ctx):
        # skip=None (omitted) — normal rotation
        effect = EffectConfig(
            operator="rotate",
            target="game.active_role",
            sequence="game.role_order",
        )
        execute(effect, store, event_log, ctx, tick=1)
        assert store.get("game")["active_role"] == "seer"

    def test_param_resolution(self, store, event_log, ctx):
        effect = EffectConfig(
            operator="rotate",
            target="$agent.active_turn",
            sequence="$agent.turn_order",
        )
        execute(effect, store, event_log, ctx, tick=1)
        assert store.get("agent_a")["active_turn"] == "b"

    def test_single_element(self, store, event_log, ctx):
        effect = EffectConfig(
            operator="rotate",
            target="single.current",
            sequence="single.seq",
        )
        execute(effect, store, event_log, ctx, tick=1)
        assert store.get("single")["current"] == "only"

    def test_only_one_available(self, store, event_log, ctx):
        # 3 of 4 skipped — always lands on the remaining one
        store.update_property("game", "dead_roles", ["seer", "witch", "hunter"])
        effect = EffectConfig(
            operator="rotate",
            target="game.active_role",
            sequence="game.role_order",
            skip="game.dead_roles",
        )
        execute(effect, store, event_log, ctx, tick=1)
        assert store.get("game")["active_role"] == "werewolf"
