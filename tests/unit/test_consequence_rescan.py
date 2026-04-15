"""Test consequence re-scan: cascading consequences across passes."""

from worldseed.engine.consequence_scanner import ConsequenceScanner
from worldseed.engine.event_log import EventLog
from worldseed.engine.state_store import StateStore
from worldseed.models.config_schema import SceneConfig
from worldseed.models.entity import Entity


def _make_store(config: SceneConfig) -> StateStore:
    store = StateStore()
    for e in config.entities:
        store.add(Entity(id=e.id, type=e.type, _data=dict(e.properties)))
    return store


class TestRescanCascade:
    """Consequences that change state should trigger other consequences in the same tick."""

    def test_three_step_cascade(self):
        """A → sets phase=b → B fires → sets phase=c → C fires. All in one tick."""
        config = SceneConfig.model_validate(
            {
                "scene": {"id": "t", "description": "t"},
                "entities": [{"id": "game", "type": "game", "phase": "a", "result": "none"}],
                "actions": {
                    "wait": {
                        "description": "w",
                        "params": [],
                        "preconditions": [],
                        "effects": [],
                    }
                },
                "consequences": {
                    "step_a": {
                        "trigger": [
                            {
                                "operator": "check",
                                "left": "game.phase",
                                "op": "==",
                                "right": "a",
                            }
                        ],
                        "effects": [{"operator": "set", "target": "game.phase", "value": "b"}],
                    },
                    "step_b": {
                        "trigger": [
                            {
                                "operator": "check",
                                "left": "game.phase",
                                "op": "==",
                                "right": "b",
                            }
                        ],
                        "effects": [{"operator": "set", "target": "game.phase", "value": "c"}],
                    },
                    "step_c": {
                        "trigger": [
                            {
                                "operator": "check",
                                "left": "game.phase",
                                "op": "==",
                                "right": "c",
                            }
                        ],
                        "effects": [
                            {
                                "operator": "set",
                                "target": "game.result",
                                "value": "done",
                            }
                        ],
                    },
                },
            }
        )
        store = _make_store(config)
        event_log = EventLog()
        scanner = ConsequenceScanner(config, store, event_log)

        triggered, _ = scanner.scan(1)

        assert "step_a" in triggered
        assert "step_b" in triggered
        assert "step_c" in triggered
        assert store.get("game")["phase"] == "c"
        assert store.get("game")["result"] == "done"

    def test_entity_then_global_cascade(self):
        """Entity consequence fires → changes state → global consequence fires."""
        config = SceneConfig.model_validate(
            {
                "scene": {"id": "t", "description": "t"},
                "entities": [
                    {"id": "game", "type": "game", "phase": "start", "ready_count": 0},
                    {"id": "p1", "type": "agent", "status": "waiting"},
                    {"id": "p2", "type": "agent", "status": "waiting"},
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
                    "player_ready": {
                        "trigger": [
                            {
                                "operator": "check",
                                "left": "$entity.type",
                                "op": "==",
                                "right": "agent",
                            },
                            {
                                "operator": "check",
                                "left": "game.phase",
                                "op": "==",
                                "right": "start",
                            },
                        ],
                        "effects": [
                            {
                                "operator": "set",
                                "target": "$entity.status",
                                "value": "ready",
                            },
                            {
                                "operator": "increment",
                                "target": "game.ready_count",
                                "by": 1,
                            },
                        ],
                    },
                    "all_ready": {
                        "trigger": [
                            {
                                "operator": "check",
                                "left": "game.ready_count",
                                "op": ">=",
                                "right": 2,
                            },
                        ],
                        "effects": [
                            {
                                "operator": "set",
                                "target": "game.phase",
                                "value": "playing",
                            },
                        ],
                    },
                },
            }
        )
        store = _make_store(config)
        event_log = EventLog()
        scanner = ConsequenceScanner(config, store, event_log)

        triggered, _ = scanner.scan(1)

        # Entity consequence fires for both agents → ready_count=2
        # Then global all_ready fires → phase=playing
        assert "player_ready" in triggered
        assert "all_ready" in triggered
        assert store.get("game")["phase"] == "playing"
        assert store.get("p1")["status"] == "ready"
        assert store.get("p2")["status"] == "ready"

    def test_every_tick_does_not_refire_in_rescan(self):
        """every_tick consequences fire once per tick, not once per pass."""
        config = SceneConfig.model_validate(
            {
                "scene": {"id": "t", "description": "t"},
                "entities": [{"id": "counter", "type": "test", "value": 0, "trigger": "yes"}],
                "actions": {
                    "wait": {
                        "description": "w",
                        "params": [],
                        "preconditions": [],
                        "effects": [],
                    }
                },
                "consequences": {
                    "count_up": {
                        "trigger": [
                            {
                                "operator": "check",
                                "left": "counter.trigger",
                                "op": "==",
                                "right": "yes",
                            },
                        ],
                        "effects": [
                            {
                                "operator": "increment",
                                "target": "counter.value",
                                "by": 1,
                            }
                        ],
                        "frequency": "every_tick",
                    },
                },
            }
        )
        store = _make_store(config)
        event_log = EventLog()
        scanner = ConsequenceScanner(config, store, event_log)

        scanner.scan(1)
        assert store.get("counter")["value"] == 1  # exactly once, not 10

        scanner.scan(2)
        assert store.get("counter")["value"] == 2  # once more

    def test_long_cascade_within_one_pass(self):
        """15 chained consequences all fire within a single scan (within-pass cascade)."""
        consequences = {}
        for i in range(15):
            consequences[f"step_{i}"] = {
                "trigger": [
                    {
                        "operator": "check",
                        "left": "game.phase",
                        "op": "==",
                        "right": f"s{i}",
                    }
                ],
                "effects": [{"operator": "set", "target": "game.phase", "value": f"s{i + 1}"}],
            }
        config = SceneConfig.model_validate(
            {
                "scene": {"id": "t", "description": "t"},
                "entities": [{"id": "game", "type": "game", "phase": "s0"}],
                "actions": {
                    "wait": {
                        "description": "w",
                        "params": [],
                        "preconditions": [],
                        "effects": [],
                    }
                },
                "consequences": consequences,
            }
        )
        store = _make_store(config)
        event_log = EventLog()
        scanner = ConsequenceScanner(config, store, event_log)

        triggered, _ = scanner.scan(1)

        # All 15 fire — within-pass cascade handles chains of on_change consequences
        assert store.get("game")["phase"] == "s15"
        assert len(triggered) == 15
