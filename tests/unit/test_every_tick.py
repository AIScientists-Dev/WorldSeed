"""Tests for every_tick consequence frequency."""

from __future__ import annotations

from worldseed.engine.consequence_scanner import ConsequenceScanner
from worldseed.engine.event_log import EventLog
from worldseed.engine.state_store import StateStore
from worldseed.models.config_schema import (
    ConsequenceConfig,
    EffectConfig,
    PreconditionConfig,
    SceneConfig,
    SceneMetaConfig,
)
from worldseed.models.entity import Entity


def _make_config(consequences: dict[str, ConsequenceConfig]) -> SceneConfig:
    return SceneConfig(
        scene=SceneMetaConfig(id="test", description="test"),
        entities=[],
        actions={},
        consequences=consequences,
    )


# ---------------------------------------------------------------------------
# Helpers: reusable consequence configs
# ---------------------------------------------------------------------------


def _radiation_consequence() -> ConsequenceConfig:
    """Per-entity, every_tick: agents in reactor lose 10 health/tick."""
    return ConsequenceConfig(
        trigger=[
            PreconditionConfig(
                operator="check",
                left="$entity.type",
                op="==",
                right="agent",
            ),
            PreconditionConfig(
                operator="check",
                left="$entity.location",
                op="==",
                right="reactor",
            ),
        ],
        effects=[
            EffectConfig(
                operator="decrement",
                target="$entity.health",
                by=10,
                min=0,
            ),
        ],
        frequency="every_tick",
    )


def _radiation_alert_on_change() -> ConsequenceConfig:
    """Per-entity, on_change: fires once when agent enters reactor."""
    return ConsequenceConfig(
        trigger=[
            PreconditionConfig(
                operator="check",
                left="$entity.type",
                op="==",
                right="agent",
            ),
            PreconditionConfig(
                operator="check",
                left="$entity.location",
                op="==",
                right="reactor",
            ),
        ],
        effects=[
            EffectConfig(
                operator="emit_event",
                type="warning",
                detail="Agent entered radiation zone",
                ttl=3,
                scope="global",
            ),
        ],
        frequency="on_change",
    )


def _global_decay_consequence() -> ConsequenceConfig:
    """Global, every_tick: decrement temperature when heater is off."""
    return ConsequenceConfig(
        trigger=[
            PreconditionConfig(
                operator="check",
                left="heater.active",
                op="==",
                right=False,
            ),
        ],
        effects=[
            EffectConfig(
                operator="decrement",
                target="room.temperature",
                by=2,
            ),
        ],
        frequency="every_tick",
    )


def _store_with_reactor() -> StateStore:
    store = StateStore()
    store.add(
        Entity(
            id="reactor",
            type="space",
            _data={"description": "Reactor room"},
        )
    )
    store.add(
        Entity(
            id="hallway",
            type="space",
            _data={"description": "Hallway"},
        )
    )
    store.add(
        Entity(
            id="alice",
            type="agent",
            _data={"location": "reactor", "health": 100},
        )
    )
    store.add(
        Entity(
            id="bob",
            type="agent",
            _data={"location": "hallway", "health": 100},
        )
    )
    return store


# ---------------------------------------------------------------------------
# Test 1: Basic every_tick behavior — fires every tick while condition is true
# ---------------------------------------------------------------------------


class TestEveryTickBasic:
    def test_fires_every_tick(self) -> None:
        """every_tick consequence fires on every tick while condition holds."""
        config = _make_config({"radiation": _radiation_consequence()})
        store = _store_with_reactor()
        event_log = EventLog()
        scanner = ConsequenceScanner(config, store, event_log)

        # Tick 1: alice is in reactor → health 100 → 90
        triggered, _dm_pending = scanner.scan(1)
        assert "radiation" in triggered
        assert store.get("alice")["health"] == 90

        # Tick 2: still in reactor → 90 → 80
        triggered, _dm_pending = scanner.scan(2)
        assert "radiation" in triggered
        assert store.get("alice")["health"] == 80

        # Tick 3: still in reactor → 80 → 70
        triggered, _dm_pending = scanner.scan(3)
        assert "radiation" in triggered
        assert store.get("alice")["health"] == 70

    def test_does_not_affect_non_matching_entity(self) -> None:
        """Bob in hallway is unaffected by reactor radiation."""
        config = _make_config({"radiation": _radiation_consequence()})
        store = _store_with_reactor()
        event_log = EventLog()
        scanner = ConsequenceScanner(config, store, event_log)

        triggered, _dm_pending = scanner.scan(1)
        assert "radiation" in triggered
        scanner.scan(2)
        scanner.scan(3)

        assert store.get("alice")["health"] == 70
        assert store.get("bob")["health"] == 100  # untouched


# ---------------------------------------------------------------------------
# Test 2: Condition true → false → true (stop and resume)
# ---------------------------------------------------------------------------


class TestEveryTickStopResume:
    def test_stops_when_condition_becomes_false(self) -> None:
        """Effect stops when agent leaves the reactor."""
        config = _make_config({"radiation": _radiation_consequence()})
        store = _store_with_reactor()
        event_log = EventLog()
        scanner = ConsequenceScanner(config, store, event_log)

        # Tick 1: in reactor → 100 → 90
        triggered, _dm_pending = scanner.scan(1)
        assert "radiation" in triggered
        assert store.get("alice")["health"] == 90

        # Alice leaves reactor
        store.update_property("alice", "location", "hallway")

        # Tick 2: NOT in reactor → no damage
        triggered, _dm_pending = scanner.scan(2)
        assert triggered == []
        assert store.get("alice")["health"] == 90

        # Tick 3: still in hallway → no damage
        triggered, _dm_pending = scanner.scan(3)
        assert triggered == []
        assert store.get("alice")["health"] == 90

    def test_resumes_when_condition_becomes_true_again(self) -> None:
        """Effect resumes immediately when agent re-enters reactor."""
        config = _make_config({"radiation": _radiation_consequence()})
        store = _store_with_reactor()
        event_log = EventLog()
        scanner = ConsequenceScanner(config, store, event_log)

        # Tick 1: in reactor → 90
        triggered, _dm_pending = scanner.scan(1)
        assert "radiation" in triggered
        assert store.get("alice")["health"] == 90

        # Leave
        store.update_property("alice", "location", "hallway")
        triggered, _dm_pending = scanner.scan(2)
        assert triggered == []
        assert store.get("alice")["health"] == 90

        # Re-enter
        store.update_property("alice", "location", "reactor")
        triggered, _dm_pending = scanner.scan(3)
        assert "radiation" in triggered
        assert store.get("alice")["health"] == 80


# ---------------------------------------------------------------------------
# Test 3: every_tick + on_change coexist on same condition
# ---------------------------------------------------------------------------


class TestEveryTickWithOnChange:
    def test_on_change_fires_once_every_tick_fires_always(self) -> None:
        """Same condition, different frequencies: on_change fires once,
        every_tick fires every tick."""
        config = _make_config(
            {
                "radiation_damage": _radiation_consequence(),
                "radiation_alert": _radiation_alert_on_change(),
            }
        )
        store = _store_with_reactor()
        event_log = EventLog()
        scanner = ConsequenceScanner(config, store, event_log)

        # Tick 1: both fire
        triggered, _dm_pending = scanner.scan(1)
        assert "radiation_damage" in triggered
        assert "radiation_alert" in triggered
        assert store.get("alice")["health"] == 90
        alerts = [e for e in event_log.get_events() if e.type == "warning"]
        assert len(alerts) == 1

        # Tick 2: every_tick fires again, on_change does NOT
        triggered, _dm_pending = scanner.scan(2)
        assert "radiation_damage" in triggered
        assert "radiation_alert" not in triggered
        assert store.get("alice")["health"] == 80
        alerts = [e for e in event_log.get_events() if e.type == "warning"]
        assert len(alerts) == 1  # still 1, not 2

        # Tick 3: same
        triggered, _dm_pending = scanner.scan(3)
        assert "radiation_damage" in triggered
        assert store.get("alice")["health"] == 70
        alerts = [e for e in event_log.get_events() if e.type == "warning"]
        assert len(alerts) == 1


# ---------------------------------------------------------------------------
# Test 4: Effect modifies its own trigger dependency (self-feeding loop)
# ---------------------------------------------------------------------------


class TestEveryTickSelfFeeding:
    def test_effect_modifies_trigger_dependency(self) -> None:
        """health < 50 → decrement health by 10. Should keep draining."""
        consequence = ConsequenceConfig(
            trigger=[
                PreconditionConfig(
                    operator="check",
                    left="$entity.type",
                    op="==",
                    right="agent",
                ),
                PreconditionConfig(
                    operator="check",
                    left="$entity.health",
                    op="<",
                    right=50,
                ),
            ],
            effects=[
                EffectConfig(
                    operator="decrement",
                    target="$entity.health",
                    by=10,
                    min=0,
                ),
            ],
            frequency="every_tick",
        )
        config = _make_config({"bleed": consequence})
        store = StateStore()
        store.add(Entity(id="wounded", type="agent", _data={"health": 45}))
        event_log = EventLog()
        scanner = ConsequenceScanner(config, store, event_log)

        triggered, _dm_pending = scanner.scan(1)  # 45 → 35
        assert "bleed" in triggered
        assert store.get("wounded")["health"] == 35

        triggered, _dm_pending = scanner.scan(2)  # 35 → 25
        assert "bleed" in triggered
        assert store.get("wounded")["health"] == 25

        scanner.scan(3)  # 25 → 15
        assert store.get("wounded")["health"] == 15

        scanner.scan(4)  # 15 → 5
        assert store.get("wounded")["health"] == 5

        scanner.scan(5)  # 5 → 0 (clamped by min: 0)
        assert store.get("wounded")["health"] == 0

        # Still fires (0 < 50), but min clamp means no visible change
        triggered, _dm_pending = scanner.scan(6)
        assert "bleed" in triggered
        assert store.get("wounded")["health"] == 0


# ---------------------------------------------------------------------------
# Test 5: Entity removed during scan
# ---------------------------------------------------------------------------


class TestEveryTickEntityRemoval:
    def test_removed_entity_continues_scan(self) -> None:
        """Entity removed between ticks: no crash, other entities unaffected."""
        config = _make_config({"radiation": _radiation_consequence()})
        store = _store_with_reactor()
        event_log = EventLog()
        scanner = ConsequenceScanner(config, store, event_log)

        triggered, _dm_pending = scanner.scan(1)
        assert "radiation" in triggered
        assert store.get("alice")["health"] == 90

        # Remove alice
        store.remove("alice")

        # Should not crash, bob (in hallway) still unaffected
        triggered, _dm_pending = scanner.scan(2)
        assert triggered == []
        assert store.get("bob")["health"] == 100


# ---------------------------------------------------------------------------
# Test 6: every_tick + emit_event (event accumulation)
# ---------------------------------------------------------------------------


class TestEveryTickEmitEvent:
    def test_emits_event_every_tick(self) -> None:
        """every_tick with emit_event produces one event per tick."""
        consequence = ConsequenceConfig(
            trigger=[
                PreconditionConfig(
                    operator="check",
                    left="alarm.active",
                    op="==",
                    right=True,
                ),
            ],
            effects=[
                EffectConfig(
                    operator="emit_event",
                    type="alarm",
                    detail="BEEP BEEP BEEP",
                    ttl=1,
                    scope="global",
                ),
            ],
            frequency="every_tick",
        )
        config = _make_config({"alarm_sound": consequence})
        store = StateStore()
        store.add(Entity(id="alarm", type="device", _data={"active": True}))
        event_log = EventLog()
        scanner = ConsequenceScanner(config, store, event_log)

        triggered, _dm_pending = scanner.scan(1)
        assert "alarm_sound" in triggered
        triggered, _dm_pending = scanner.scan(2)
        assert "alarm_sound" in triggered
        triggered, _dm_pending = scanner.scan(3)
        assert "alarm_sound" in triggered

        alarm_events = [e for e in event_log.get_events() if e.type == "alarm"]
        assert len(alarm_events) == 3


# ---------------------------------------------------------------------------
# Test 7: Multiple every_tick consequences on same entity (stacking)
# ---------------------------------------------------------------------------


class TestEveryTickStacking:
    def test_multiple_consequences_stack(self) -> None:
        """Two every_tick consequences both affect the same entity."""
        radiation = ConsequenceConfig(
            trigger=[
                PreconditionConfig(
                    operator="check",
                    left="$entity.type",
                    op="==",
                    right="agent",
                ),
                PreconditionConfig(
                    operator="check",
                    left="$entity.location",
                    op="==",
                    right="reactor",
                ),
            ],
            effects=[
                EffectConfig(
                    operator="decrement",
                    target="$entity.health",
                    by=10,
                    min=0,
                ),
            ],
            frequency="every_tick",
        )
        poison = ConsequenceConfig(
            trigger=[
                PreconditionConfig(
                    operator="check",
                    left="$entity.type",
                    op="==",
                    right="agent",
                ),
                PreconditionConfig(
                    operator="check",
                    left="$entity.poisoned",
                    op="==",
                    right=True,
                ),
            ],
            effects=[
                EffectConfig(
                    operator="decrement",
                    target="$entity.health",
                    by=5,
                    min=0,
                ),
            ],
            frequency="every_tick",
        )
        config = _make_config({"radiation": radiation, "poison": poison})
        store = StateStore()
        store.add(
            Entity(
                id="victim",
                type="agent",
                _data={
                    "location": "reactor",
                    "health": 100,
                    "poisoned": True,
                },
            )
        )
        store.add(Entity(id="reactor", type="space", _data={}))
        event_log = EventLog()
        scanner = ConsequenceScanner(config, store, event_log)

        # Both fire: -10 (radiation) + -5 (poison) = -15/tick
        triggered, _dm_pending = scanner.scan(1)
        assert "radiation" in triggered
        assert "poison" in triggered
        assert store.get("victim")["health"] == 85

        triggered, _dm_pending = scanner.scan(2)
        assert "radiation" in triggered
        assert "poison" in triggered
        assert store.get("victim")["health"] == 70


# ---------------------------------------------------------------------------
# Test 8: Global every_tick (no $entity)
# ---------------------------------------------------------------------------


class TestEveryTickGlobal:
    def test_global_every_tick_fires_continuously(self) -> None:
        """Global (non-entity) every_tick consequence fires every tick."""
        config = _make_config({"cooling": _global_decay_consequence()})
        store = StateStore()
        store.add(Entity(id="heater", type="device", _data={"active": False}))
        store.add(Entity(id="room", type="space", _data={"temperature": 20}))
        event_log = EventLog()
        scanner = ConsequenceScanner(config, store, event_log)

        triggered, _dm_pending = scanner.scan(1)  # 20 → 18
        assert "cooling" in triggered
        assert store.get("room")["temperature"] == 18

        triggered, _dm_pending = scanner.scan(2)  # 18 → 16
        assert "cooling" in triggered
        assert store.get("room")["temperature"] == 16

        # Turn heater on → stops
        store.update_property("heater", "active", True)
        triggered, _dm_pending = scanner.scan(3)
        assert triggered == []
        assert store.get("room")["temperature"] == 16

        # Turn heater off → resumes
        store.update_property("heater", "active", False)
        triggered, _dm_pending = scanner.scan(4)
        assert "cooling" in triggered
        assert store.get("room")["temperature"] == 14


# ---------------------------------------------------------------------------
# Test 9: Zero matching entities — no crash, no effect
# ---------------------------------------------------------------------------


class TestEveryTickEmpty:
    def test_no_matching_entities(self) -> None:
        """No entities match the trigger — no crash, no effects."""
        config = _make_config({"radiation": _radiation_consequence()})
        store = StateStore()
        # Only non-agent entities
        store.add(Entity(id="reactor", type="space", _data={}))
        event_log = EventLog()
        scanner = ConsequenceScanner(config, store, event_log)

        triggered, _dm_pending = scanner.scan(1)
        assert triggered == []


# ---------------------------------------------------------------------------
# Test 10: Entity added between ticks — immediately subject to every_tick
# ---------------------------------------------------------------------------


class TestEveryTickEntityAddition:
    def test_new_entity_immediately_affected(self) -> None:
        """A new agent added between ticks is immediately subject
        to every_tick consequences on the next scan."""
        config = _make_config({"radiation": _radiation_consequence()})
        store = StateStore()
        store.add(
            Entity(
                id="reactor",
                type="space",
                _data={},
            )
        )
        event_log = EventLog()
        scanner = ConsequenceScanner(config, store, event_log)

        # Tick 1: no agents → nothing fires
        triggered, _dm_pending = scanner.scan(1)
        assert triggered == []

        # Add a new agent in the reactor
        store.add(
            Entity(
                id="newcomer",
                type="agent",
                _data={"location": "reactor", "health": 100},
            )
        )

        # Tick 2: newcomer is in reactor → takes damage immediately
        triggered, _dm_pending = scanner.scan(2)
        assert "radiation" in triggered
        assert store.get("newcomer")["health"] == 90

        # Tick 3: continues to take damage
        triggered, _dm_pending = scanner.scan(3)
        assert "radiation" in triggered
        assert store.get("newcomer")["health"] == 80
