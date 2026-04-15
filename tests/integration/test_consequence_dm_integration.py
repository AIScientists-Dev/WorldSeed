"""Integration test: consequence + DM — full tick cycle with mock DM provider.

This tests the REAL flow: consequence triggers → DM is called → effects applied to state.
Not just unit-testing that pending info is returned.
"""

import asyncio

from worldseed.dm.providers.mock import MockDMProvider
from worldseed.engine.action_queue import ActionQueue
from worldseed.engine.event_log import EventLog
from worldseed.engine.state_store import StateStore
from worldseed.engine.tick import TickEngine
from worldseed.models.config_schema import EffectConfig, SceneConfig
from worldseed.models.entity import Entity
from worldseed.protocol.dm import DMResponse


def _make_config(consequences: dict) -> SceneConfig:
    return SceneConfig.model_validate(
        {
            "scene": {"id": "test_csq_dm", "description": "Test consequence DM"},
            "entities": [
                {"id": "room", "type": "space", "temperature": 120, "damage": 0},
                {"id": "deck", "type": "card_deck", "cards": ["A♠", "K♥", "Q♦", "J♣"]},
                {"id": "table", "type": "game", "phase": "deal", "community_cards": ""},
            ],
            "actions": {
                "wait": {
                    "description": "wait",
                    "params": [],
                    "preconditions": [],
                    "effects": [],
                },
            },
            "consequences": consequences,
        }
    )


class TestConsequenceDMFullCycle:
    """Test the full tick cycle: consequence triggers → DM called → effects applied."""

    def test_consequence_dm_applies_effects(self):
        """DM effects from a consequence should change world state."""
        config = _make_config(
            {
                "fire_damage": {
                    "trigger": [
                        {
                            "operator": "check",
                            "left": "room.temperature",
                            "op": ">=",
                            "right": 100,
                        }
                    ],
                    "effects": [
                        {
                            "operator": "emit_event",
                            "type": "fire_alarm",
                            "detail": "Fire!",
                            "ttl": 3,
                        }
                    ],
                    "dm": {
                        "hint": "Determine structural damage from fire",
                        "allowed_ops": ["set", "increment", "decrement", "emit_event"],
                        "max_effects": 3,
                        "scope": "global",
                    },
                }
            }
        )

        store = StateStore()
        for e in config.entities:
            store.add(Entity(id=e.id, type=e.type, _data=dict(e.properties)))
        event_log = EventLog()
        action_queue = ActionQueue()

        # Mock DM: when called for consequence, set room.damage = 50
        dm_response = DMResponse(
            narrative="The fire causes structural damage.",
            effects=[
                EffectConfig(operator="set", target="room.damage", value=50),
                EffectConfig(
                    operator="emit_event",
                    type="fire_damage",
                    detail="Room sustains damage",
                    ttl=3,
                    scope="global",
                ),
            ],
        )
        mock_dm = MockDMProvider(responses={"consequence:fire_damage": dm_response})

        engine = TickEngine(
            config=config,
            store=store,
            event_log=event_log,
            action_queue=action_queue,
            dm_provider=mock_dm,
        )

        # Run one async tick
        asyncio.run(engine.step_async())

        # DM should have been called
        assert mock_dm.call_count == 1
        assert mock_dm.last_context is not None
        assert "consequence:fire_damage" in mock_dm.last_context.action.action_type

        # DM effects should have been applied
        assert store.get("room")["damage"] == 50

        # Both deterministic event AND DM event should exist
        events = event_log.get_events()
        event_types = [e.type for e in events]
        assert "fire_alarm" in event_types  # from deterministic effect
        assert "fire_damage" in event_types  # from DM effect

    def test_consequence_dm_only_no_deterministic_effects(self):
        """Consequence with only dm: (no effects:) should call DM."""
        config = _make_config(
            {
                "deal_cards": {
                    "trigger": [
                        {
                            "operator": "check",
                            "left": "table.phase",
                            "op": "==",
                            "right": "deal",
                        }
                    ],
                    "dm": {
                        "hint": "Deal 2 cards from deck to community_cards",
                        "allowed_ops": ["set", "emit_event"],
                        "max_effects": 5,
                        "scope": "global",
                    },
                }
            }
        )

        store = StateStore()
        for e in config.entities:
            store.add(Entity(id=e.id, type=e.type, _data=dict(e.properties)))
        event_log = EventLog()
        action_queue = ActionQueue()

        dm_response = DMResponse(
            narrative="Cards are dealt.",
            effects=[
                EffectConfig(operator="set", target="table.community_cards", value="A♠ K♥"),
                EffectConfig(operator="set", target="table.phase", value="betting"),
            ],
        )
        mock_dm = MockDMProvider(responses={"consequence:deal_cards": dm_response})

        engine = TickEngine(
            config=config,
            store=store,
            event_log=event_log,
            action_queue=action_queue,
            dm_provider=mock_dm,
        )

        asyncio.run(engine.step_async())

        assert mock_dm.call_count == 1
        assert store.get("table")["community_cards"] == "A♠ K♥"
        assert store.get("table")["phase"] == "betting"

    def test_consequence_dm_budget_enforcement(self):
        """DM calls from consequences should respect the global budget."""
        config = _make_config(
            {
                "fire": {
                    "trigger": [
                        {
                            "operator": "check",
                            "left": "room.temperature",
                            "op": ">=",
                            "right": 100,
                        }
                    ],
                    "dm": {
                        "hint": "Determine damage",
                        "allowed_ops": ["set"],
                        "max_effects": 2,
                    },
                }
            }
        )
        # Set max_dm_calls to 0 — no budget
        config.scene.max_dm_calls = 0

        store = StateStore()
        for e in config.entities:
            store.add(Entity(id=e.id, type=e.type, _data=dict(e.properties)))
        event_log = EventLog()
        action_queue = ActionQueue()

        mock_dm = MockDMProvider()

        engine = TickEngine(
            config=config,
            store=store,
            event_log=event_log,
            action_queue=action_queue,
            dm_provider=mock_dm,
        )

        asyncio.run(engine.step_async())

        # DM should NOT have been called (budget = 0)
        assert mock_dm.call_count == 0

    def test_consequence_dm_on_change_fires_once(self):
        """on_change consequence with DM should only call DM once."""
        config = _make_config(
            {
                "fire": {
                    "trigger": [
                        {
                            "operator": "check",
                            "left": "room.temperature",
                            "op": ">=",
                            "right": 100,
                        }
                    ],
                    "dm": {
                        "hint": "Fire!",
                        "allowed_ops": ["set"],
                        "max_effects": 2,
                    },
                    "frequency": "on_change",
                }
            }
        )

        store = StateStore()
        for e in config.entities:
            store.add(Entity(id=e.id, type=e.type, _data=dict(e.properties)))
        event_log = EventLog()
        action_queue = ActionQueue()

        mock_dm = MockDMProvider(
            responses={
                "consequence:fire": DMResponse(
                    narrative="Fire!",
                    effects=[EffectConfig(operator="set", target="room.damage", value=10)],
                )
            }
        )

        engine = TickEngine(
            config=config,
            store=store,
            event_log=event_log,
            action_queue=action_queue,
            dm_provider=mock_dm,
        )

        # Tick 1: fires
        asyncio.run(engine.step_async())
        assert mock_dm.call_count == 1
        assert store.get("room")["damage"] == 10

        # Tick 2: still true but on_change — should NOT call DM again
        asyncio.run(engine.step_async())
        assert mock_dm.call_count == 1  # still 1, not 2

    def test_sync_step_skips_consequence_dm(self):
        """sync step() should not crash on consequence DM (just ignores pending)."""
        config = _make_config(
            {
                "fire": {
                    "trigger": [
                        {
                            "operator": "check",
                            "left": "room.temperature",
                            "op": ">=",
                            "right": 100,
                        }
                    ],
                    "dm": {
                        "hint": "Fire!",
                        "allowed_ops": ["set"],
                        "max_effects": 2,
                    },
                }
            }
        )

        store = StateStore()
        for e in config.entities:
            store.add(Entity(id=e.id, type=e.type, _data=dict(e.properties)))
        event_log = EventLog()
        action_queue = ActionQueue()

        # No DM provider — sync mode
        engine = TickEngine(
            config=config,
            store=store,
            event_log=event_log,
            action_queue=action_queue,
        )

        # Should not crash
        engine.step()
        assert store.get("room")["damage"] == 0  # DM effects not applied (no provider)
