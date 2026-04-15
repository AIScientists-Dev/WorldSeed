"""Stress tests for for_each effect operator."""

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
            id="a1",
            type="agent",
            _data={
                "role": "player",
                "acted": True,
                "bet": 50,
                "folded": False,
                "hp": 100,
            },
        )
    )
    s.add(
        Entity(
            id="a2",
            type="agent",
            _data={
                "role": "player",
                "acted": True,
                "bet": 30,
                "folded": False,
                "hp": 80,
            },
        )
    )
    s.add(
        Entity(
            id="a3",
            type="agent",
            _data={
                "role": "player",
                "acted": False,
                "bet": 0,
                "folded": True,
                "hp": 60,
            },
        )
    )
    s.add(Entity(id="dealer", type="agent", _data={"role": "dealer", "acted": False}))
    s.add(Entity(id="table", type="game", _data={"phase": "flop"}))
    return s


@pytest.fixture()
def event_log() -> EventLog:
    return EventLog()


@pytest.fixture()
def ctx() -> dict:
    return {"agent_id": "", "action_params": {}, "tick": 1}


class TestForEachBasic:
    def test_resets_all_matching(self, store, event_log, ctx):
        """Reset acted for all agents."""
        effect = EffectConfig(
            operator="for_each",
            match={"type": "agent"},
            sub_effects=[
                EffectConfig(operator="set", target="$entity.acted", value=False),
            ],
        )
        execute(effect, store, event_log, ctx, tick=1)
        assert store.get("a1")["acted"] is False
        assert store.get("a2")["acted"] is False
        assert store.get("a3")["acted"] is False
        assert store.get("dealer")["acted"] is False

    def test_with_where_filter(self, store, event_log, ctx):
        """Only reset non-folded players."""
        effect = EffectConfig(
            operator="for_each",
            match={"type": "agent"},
            where="folded == false",
            sub_effects=[
                EffectConfig(operator="set", target="$entity.acted", value=False),
                EffectConfig(operator="set", target="$entity.bet", value=0),
            ],
        )
        execute(effect, store, event_log, ctx, tick=1)
        assert store.get("a1")["acted"] is False
        assert store.get("a1")["bet"] == 0
        assert store.get("a2")["acted"] is False
        assert store.get("a3")["acted"] is False  # was already False
        assert store.get("a3")["bet"] == 0  # was already 0

    def test_with_match_property(self, store, event_log, ctx):
        """Match by type AND property."""
        effect = EffectConfig(
            operator="for_each",
            match={"type": "agent", "role": "player"},
            sub_effects=[
                EffectConfig(operator="set", target="$entity.acted", value=False),
            ],
        )
        execute(effect, store, event_log, ctx, tick=1)
        assert store.get("a1")["acted"] is False
        assert store.get("a2")["acted"] is False
        assert store.get("dealer")["acted"] is False  # dealer role != player, should be unchanged

    def test_empty_match(self, store, event_log, ctx):
        """No matching entities → nothing happens."""
        effect = EffectConfig(
            operator="for_each",
            match={"type": "nonexistent"},
            sub_effects=[
                EffectConfig(operator="set", target="$entity.acted", value=False),
            ],
        )
        execute(effect, store, event_log, ctx, tick=1)
        # No crash, no change
        assert store.get("a1")["acted"] is True

    def test_where_filters_all(self, store, event_log, ctx):
        """Where filter excludes all → nothing happens."""
        effect = EffectConfig(
            operator="for_each",
            match={"type": "agent"},
            where="hp == 999",
            sub_effects=[
                EffectConfig(operator="set", target="$entity.acted", value=False),
            ],
        )
        execute(effect, store, event_log, ctx, tick=1)
        assert store.get("a1")["acted"] is True  # unchanged

    def test_missing_match(self, store, event_log, ctx):
        """No match field → warning, no crash."""
        effect = EffectConfig(
            operator="for_each",
            sub_effects=[
                EffectConfig(operator="set", target="$entity.acted", value=False),
            ],
        )
        execute(effect, store, event_log, ctx, tick=1)  # no crash

    def test_missing_sub_effects(self, store, event_log, ctx):
        """No sub_effects → warning, no crash."""
        effect = EffectConfig(operator="for_each", match={"type": "agent"})
        execute(effect, store, event_log, ctx, tick=1)  # no crash


class TestForEachWithOtherOps:
    def test_increment_all(self, store, event_log, ctx):
        """Increment hp for all players."""
        effect = EffectConfig(
            operator="for_each",
            match={"type": "agent", "role": "player"},
            sub_effects=[
                EffectConfig(operator="increment", target="$entity.hp", by=10),
            ],
        )
        execute(effect, store, event_log, ctx, tick=1)
        assert store.get("a1")["hp"] == 110
        assert store.get("a2")["hp"] == 90
        assert store.get("a3")["hp"] == 70

    def test_list_pop_random_per_entity(self, store, event_log, ctx):
        """Deal cards to each player."""
        store.add(
            Entity(
                id="deck",
                type="card_deck",
                _data={"cards": ["A", "K", "Q", "J", "10", "9"]},
            )
        )
        effect = EffectConfig(
            operator="for_each",
            match={"type": "agent", "role": "player"},
            where="folded == false",
            sub_effects=[
                EffectConfig(
                    operator="list_pop_random",
                    source="deck.cards",
                    target="$entity.hand",
                ),
            ],
        )
        # a1 and a2 are not folded → each gets 1 card
        store.update_property("a1", "hand", [])
        store.update_property("a2", "hand", [])
        execute(effect, store, event_log, ctx, tick=1)
        assert len(store.get("a1")["hand"]) == 1
        assert len(store.get("a2")["hand"]) == 1
        assert len(store.get("deck")["cards"]) == 4  # 6 - 2

    def test_emit_event_per_entity(self, store, event_log, ctx):
        """Emit targeted event per entity."""
        effect = EffectConfig(
            operator="for_each",
            match={"type": "agent", "role": "player"},
            where="folded == false",
            sub_effects=[
                EffectConfig(
                    operator="emit_event",
                    type="your_turn",
                    detail="Wake up",
                    scope="target_only",
                    event_target="$entity",
                    push=True,
                    ttl=1,
                ),
            ],
        )
        execute(effect, store, event_log, ctx, tick=1)
        events = event_log.get_events()
        assert len(events) == 2  # a1 and a2 (a3 is folded)
        targets = {e.target for e in events}
        assert targets == {"a1", "a2"}


class TestForEachInConsequence:
    def test_consequence_with_for_each(self):
        """for_each works inside consequence effects."""
        from worldseed.engine.consequence_scanner import ConsequenceScanner
        from worldseed.models.config_schema import SceneConfig

        config = SceneConfig.model_validate(
            {
                "scene": {"id": "t", "description": "t"},
                "entities": [
                    {"id": "game", "type": "game", "phase": "reset"},
                    {"id": "p1", "type": "player", "score": 50},
                    {"id": "p2", "type": "player", "score": 30},
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
                    "reset_scores": {
                        "trigger": [
                            {
                                "operator": "check",
                                "left": "game.phase",
                                "op": "==",
                                "right": "reset",
                            },
                        ],
                        "effects": [
                            {
                                "operator": "for_each",
                                "match": {"type": "player"},
                                "effects": [
                                    {
                                        "operator": "set",
                                        "target": "$entity.score",
                                        "value": 0,
                                    },
                                ],
                            },
                        ],
                    },
                },
            }
        )
        store = StateStore()
        for e in config.entities:
            store.add(Entity(id=e.id, type=e.type, _data=dict(e.properties)))
        event_log = EventLog()
        scanner = ConsequenceScanner(config, store, event_log)

        triggered, _ = scanner.scan(1)
        assert "reset_scores" in triggered
        assert store.get("p1")["score"] == 0
        assert store.get("p2")["score"] == 0
