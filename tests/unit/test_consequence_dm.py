"""Stress tests for Consequence + DM feature."""

from worldseed.engine.consequence_scanner import ConsequenceScanner
from worldseed.engine.event_log import EventLog
from worldseed.engine.state_store import StateStore
from worldseed.models.config_schema import (
    SceneConfig,
)
from worldseed.models.entity import Entity


def _make_config(consequences: dict) -> SceneConfig:
    return SceneConfig.model_validate(
        {
            "scene": {"id": "test", "description": "test"},
            "entities": [
                {"id": "food", "type": "resource", "quantity": 4},
                {"id": "room", "type": "space", "temperature": 120},
            ],
            "actions": {
                "wait": {
                    "description": "wait",
                    "params": [],
                    "preconditions": [],
                    "effects": [],
                }
            },
            "consequences": consequences,
        }
    )


class TestConsequenceDMPending:
    def test_consequence_with_dm_returns_pending(self):
        """A consequence with dm: should return a pending DM call."""
        config = _make_config(
            {
                "fire_alarm": {
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
                            "type": "alarm",
                            "detail": "Fire!",
                            "ttl": 3,
                        }
                    ],
                    "dm": {
                        "hint": "Determine what burns",
                        "allowed_ops": ["set", "decrement"],
                        "max_effects": 3,
                    },
                }
            }
        )
        store = StateStore()
        for e in config.entities:
            store.add(Entity(id=e.id, type=e.type, _data=dict(e.properties)))
        event_log = EventLog()
        scanner = ConsequenceScanner(config, store, event_log)

        triggered, dm_pending = scanner.scan(1)

        assert "fire_alarm" in triggered
        # Deterministic effects should have executed
        assert len(event_log.get_events()) == 1
        # DM pending should be queued
        assert len(dm_pending) == 1
        assert dm_pending[0]["consequence_name"] == "fire_alarm"
        assert dm_pending[0]["dm_config"].hint == "Determine what burns"

    def test_consequence_dm_only_no_effects(self):
        """A consequence with only dm: (no effects) should work."""
        config = _make_config(
            {
                "judge": {
                    "trigger": [
                        {
                            "operator": "check",
                            "left": "food.quantity",
                            "op": "<",
                            "right": 5,
                        }
                    ],
                    "dm": {
                        "hint": "Judge the food situation",
                        "allowed_ops": ["set", "emit_event"],
                        "max_effects": 3,
                    },
                }
            }
        )
        store = StateStore()
        for e in config.entities:
            store.add(Entity(id=e.id, type=e.type, _data=dict(e.properties)))
        event_log = EventLog()
        scanner = ConsequenceScanner(config, store, event_log)

        triggered, dm_pending = scanner.scan(1)

        assert "judge" in triggered
        assert len(dm_pending) == 1
        assert len(event_log.get_events()) == 0  # no deterministic effects

    def test_consequence_without_dm_no_pending(self):
        """A normal consequence (no dm:) should return empty pending list."""
        config = _make_config(
            {
                "scarcity": {
                    "trigger": [
                        {
                            "operator": "check",
                            "left": "food.quantity",
                            "op": "<",
                            "right": 5,
                        }
                    ],
                    "effects": [
                        {
                            "operator": "emit_event",
                            "type": "alert",
                            "detail": "Low food",
                            "ttl": 3,
                        }
                    ],
                }
            }
        )
        store = StateStore()
        for e in config.entities:
            store.add(Entity(id=e.id, type=e.type, _data=dict(e.properties)))
        event_log = EventLog()
        scanner = ConsequenceScanner(config, store, event_log)

        triggered, dm_pending = scanner.scan(1)

        assert "scarcity" in triggered
        assert len(dm_pending) == 0

    def test_on_change_dm_fires_once(self):
        """DM pending should only appear on false→true transition."""
        config = _make_config(
            {
                "fire_alarm": {
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
                    "frequency": "on_change",
                }
            }
        )
        store = StateStore()
        for e in config.entities:
            store.add(Entity(id=e.id, type=e.type, _data=dict(e.properties)))
        event_log = EventLog()
        scanner = ConsequenceScanner(config, store, event_log)

        # First scan: fires
        triggered1, dm_pending1 = scanner.scan(1)
        assert "fire_alarm" in triggered1
        assert len(dm_pending1) == 1

        # Second scan: still true but already fired (on_change)
        triggered2, dm_pending2 = scanner.scan(2)
        assert "fire_alarm" not in triggered2
        assert len(dm_pending2) == 0

    def test_every_tick_dm_fires_repeatedly(self):
        """With every_tick frequency, DM pending appears every tick."""
        config = _make_config(
            {
                "fire_spread": {
                    "trigger": [
                        {
                            "operator": "check",
                            "left": "room.temperature",
                            "op": ">=",
                            "right": 100,
                        }
                    ],
                    "dm": {
                        "hint": "Determine fire spread",
                        "allowed_ops": ["set", "decrement"],
                        "max_effects": 3,
                    },
                    "frequency": "every_tick",
                }
            }
        )
        store = StateStore()
        for e in config.entities:
            store.add(Entity(id=e.id, type=e.type, _data=dict(e.properties)))
        event_log = EventLog()
        scanner = ConsequenceScanner(config, store, event_log)

        _, dm1 = scanner.scan(1)
        _, dm2 = scanner.scan(2)
        _, dm3 = scanner.scan(3)

        assert len(dm1) == 1
        assert len(dm2) == 1
        assert len(dm3) == 1

    def test_multiple_consequences_mixed(self):
        """Mix of DM and non-DM consequences."""
        config = _make_config(
            {
                "alert": {
                    "trigger": [
                        {
                            "operator": "check",
                            "left": "food.quantity",
                            "op": "<",
                            "right": 5,
                        }
                    ],
                    "effects": [
                        {
                            "operator": "emit_event",
                            "type": "alert",
                            "detail": "Low food",
                            "ttl": 3,
                        }
                    ],
                },
                "fire": {
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
                            "type": "fire",
                            "detail": "Fire!",
                            "ttl": 3,
                        }
                    ],
                    "dm": {
                        "hint": "Determine fire damage",
                        "allowed_ops": ["set", "decrement"],
                        "max_effects": 3,
                    },
                },
            }
        )
        store = StateStore()
        for e in config.entities:
            store.add(Entity(id=e.id, type=e.type, _data=dict(e.properties)))
        event_log = EventLog()
        scanner = ConsequenceScanner(config, store, event_log)

        triggered, dm_pending = scanner.scan(1)

        assert "alert" in triggered
        assert "fire" in triggered
        assert len(event_log.get_events()) == 2  # both emit events
        assert len(dm_pending) == 1  # only fire has DM
        assert dm_pending[0]["consequence_name"] == "fire"
