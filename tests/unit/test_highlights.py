"""Tests for the highlights system — all three layers."""

from __future__ import annotations

from worldseed.engine.event_log import EventLog
from worldseed.engine.highlight_scanner import HighlightScanner
from worldseed.engine.inbox import InboxManager
from worldseed.engine.perceiver import Perceiver
from worldseed.engine.state_store import StateStore
from worldseed.models.config_schema import (
    AgentConfig,
    HighlightConfig,
    PreconditionConfig,
    SceneConfig,
)
from worldseed.models.entity import Entity
from worldseed.models.event import Event

# ── Helpers ──────────────────────────────────────────────────────────


def _make_config(
    *,
    highlights: dict | None = None,
    hidden_properties: list[str] | None = None,
    agents: list[AgentConfig] | None = None,
) -> SceneConfig:
    return SceneConfig.model_validate(
        {
            "scene": {"id": "test", "description": "test"},
            "entities": [],
            "actions": {},
            "highlights": highlights or {},
            "agents": agents or [],
            "perception": {
                "hidden_properties": hidden_properties or [],
            },
        }
    )


# ── Layer 2: Event model highlight field ─────────────────────────────


class TestEventHighlightField:
    def test_highlight_default_false(self) -> None:
        e = Event(tick=1, type="t", source="s", detail="d", ttl=1, scope="global")
        assert e.highlight is False

    def test_highlight_not_in_dict_when_false(self) -> None:
        e = Event(tick=1, type="t", source="s", detail="d", ttl=1, scope="global")
        assert "highlight" not in e.to_dict()

    def test_highlight_in_dict_when_true(self) -> None:
        e = Event(
            tick=1,
            type="t",
            source="s",
            detail="d",
            ttl=1,
            scope="global",
            highlight=True,
        )
        d = e.to_dict()
        assert d["highlight"] is True


# ── Layer 1: Highlight scanner ───────────────────────────────────────


class TestHighlightScanner:
    def test_global_highlight_fires_on_change(self) -> None:
        store = StateStore()
        store.add(Entity(id="food", type="resource", _data={"quantity": 5}))
        event_log = EventLog()

        config = _make_config(
            highlights={
                "low_food": HighlightConfig(
                    trigger=[
                        PreconditionConfig(
                            operator="check",
                            left="food.quantity",
                            op="<=",
                            right=2,
                        )
                    ],
                    label="Food is running low!",
                )
            }
        )
        scanner = HighlightScanner(config, store, event_log)

        # food=5, should not fire
        triggered = scanner.scan(tick=1)
        assert triggered == []
        assert len(event_log.get_events()) == 0

        # Drop food to 2, should fire
        store.update_property("food", "quantity", 2)
        triggered = scanner.scan(tick=2)
        assert triggered == ["low_food"]

        events = event_log.get_events()
        assert len(events) == 1
        assert events[0].type == "highlight"
        assert events[0].detail == "Food is running low!"
        assert events[0].highlight is True
        assert events[0].scope == "admin"

    def test_on_change_no_retrigger(self) -> None:
        store = StateStore()
        store.add(Entity(id="food", type="resource", _data={"quantity": 1}))
        event_log = EventLog()

        config = _make_config(
            highlights={
                "low_food": HighlightConfig(
                    trigger=[
                        PreconditionConfig(
                            operator="check",
                            left="food.quantity",
                            op="<=",
                            right=2,
                        )
                    ],
                    label="Food is running low!",
                )
            }
        )
        scanner = HighlightScanner(config, store, event_log)

        # First scan fires
        triggered = scanner.scan(tick=1)
        assert len(triggered) == 1

        # Second scan should NOT re-trigger (still true)
        triggered = scanner.scan(tick=2)
        assert len(triggered) == 0
        assert len(event_log.get_events()) == 1

    def test_every_tick_retriggers(self) -> None:
        store = StateStore()
        store.add(Entity(id="food", type="resource", _data={"quantity": 1}))
        event_log = EventLog()

        config = _make_config(
            highlights={
                "danger": HighlightConfig(
                    trigger=[
                        PreconditionConfig(
                            operator="check",
                            left="food.quantity",
                            op="<=",
                            right=2,
                        )
                    ],
                    label="DANGER",
                    frequency="every_tick",
                )
            }
        )
        scanner = HighlightScanner(config, store, event_log)

        scanner.scan(tick=1)
        scanner.scan(tick=2)
        assert len(event_log.get_events()) == 2

    def test_entity_highlight(self) -> None:
        store = StateStore()
        store.add(Entity(id="alice", type="agent", _data={"health": 50}))
        store.add(Entity(id="bob", type="agent", _data={"health": 5}))
        event_log = EventLog()

        config = _make_config(
            highlights={
                "low_health": HighlightConfig(
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
                            op="<=",
                            right=10,
                        ),
                    ],
                    label="An agent is critically wounded!",
                )
            }
        )
        scanner = HighlightScanner(config, store, event_log)

        triggered = scanner.scan(tick=1)
        # Only bob should trigger
        assert len(triggered) == 1
        assert "bob" in triggered[0]


# ── Layer 2: Structural engine events ────────────────────────────────


class TestEngineHighlightEvents:
    def test_entity_creation_emits_highlight(self) -> None:
        from worldseed.dsl.effects import execute as execute_effect
        from worldseed.models.config_schema import EffectConfig

        store = StateStore()
        event_log = EventLog()
        ctx = {"agent_id": "alice", "action_params": {}, "tick": 1}

        effect = EffectConfig(
            operator="create_entity",
            id="sword",
            type="weapon",
            properties={"damage": 10},
        )
        execute_effect(effect, store, event_log, ctx, tick=1)

        events = [e for e in event_log.get_events() if e.highlight]
        assert len(events) == 1
        assert events[0].type == "entity_created"
        assert "sword" in events[0].detail

    def test_entity_removal_emits_highlight(self) -> None:
        from worldseed.dsl.effects import execute as execute_effect
        from worldseed.models.config_schema import EffectConfig

        store = StateStore()
        store.add(Entity(id="sword", type="weapon", _data={"damage": 10}))
        event_log = EventLog()
        ctx = {"agent_id": "alice", "action_params": {}, "tick": 1}

        effect = EffectConfig(operator="remove_entity", target="sword")
        execute_effect(effect, store, event_log, ctx, tick=1)

        events = [e for e in event_log.get_events() if e.highlight]
        assert len(events) == 1
        assert events[0].type == "entity_removed"
        assert "sword" in events[0].detail

    def test_relationship_add_emits_highlight(self) -> None:
        from worldseed.dsl.effects import execute as execute_effect
        from worldseed.models.config_schema import EffectConfig

        store = StateStore()
        store.add(Entity(id="alice", type="agent", _data={"allies": []}))
        store.add(Entity(id="bob", type="agent", _data={}))
        event_log = EventLog()
        ctx = {"agent_id": "alice", "action_params": {}, "tick": 1}

        effect = EffectConfig(
            operator="add_relationship",
            **{"from": "alice"},
            type="allies",
            to="bob",
        )
        execute_effect(effect, store, event_log, ctx, tick=1)

        events = [e for e in event_log.get_events() if e.highlight]
        assert len(events) == 1
        assert events[0].type == "relationship_changed"
        assert "alice" in events[0].detail
        assert "bob" in events[0].detail

    def test_relationship_remove_emits_highlight(self) -> None:
        from worldseed.dsl.effects import execute as execute_effect
        from worldseed.models.config_schema import EffectConfig

        store = StateStore()
        store.add(Entity(id="alice", type="agent", _data={"allies": ["bob"]}))
        store.add(Entity(id="bob", type="agent", _data={}))
        event_log = EventLog()
        ctx = {"agent_id": "alice", "action_params": {}, "tick": 1}

        effect = EffectConfig(
            operator="remove_relationship",
            **{"from": "alice"},
            type="allies",
            to="bob",
        )
        execute_effect(effect, store, event_log, ctx, tick=1)

        events = [e for e in event_log.get_events() if e.highlight]
        assert len(events) == 1
        assert "removed" in events[0].detail


# ── Layer 3: Omniscient perception ───────────────────────────────────


class TestOmniscientPerception:
    def _setup(
        self,
        *,
        omniscient_agent: bool = False,
        hidden_properties: list[str] | None = None,
    ) -> tuple[StateStore, EventLog, InboxManager, Perceiver]:
        from worldseed.agent_registry import AgentRegistry

        agents = [
            AgentConfig(id="observer", omniscient=omniscient_agent),
            AgentConfig(id="spy"),
        ]
        config = _make_config(
            hidden_properties=hidden_properties or ["secret"],
            agents=agents,
        )

        store = StateStore()
        store.add(
            Entity(
                id="item",
                type="object",
                _data={"secret": "hidden_val", "name": "key"},
            )
        )

        event_log = EventLog()
        inbox_manager = InboxManager()
        registry = AgentRegistry(config, store)
        # Register agents via registry (creates entities in store)
        registry.register(
            "observer",
            {"role": "narrator"},
            {},
            omniscient=omniscient_agent,
        )
        registry.register("spy", {"secret": "double_agent", "visible": "yes"}, {})

        perceiver = Perceiver(store, event_log, inbox_manager, config.perception, registry=registry)
        return store, event_log, inbox_manager, perceiver

    def test_omniscient_sees_hidden_properties(self) -> None:
        store, event_log, inbox_mgr, perceiver = self._setup(omniscient_agent=True)
        perceiver.deliver(tick=1)

        inbox = inbox_mgr.get_or_create("observer")
        snapshot = inbox._current_state
        assert snapshot is not None
        # Omniscient observer should see spy's secret
        assert "secret" in snapshot.visible_agents["spy"]
        assert snapshot.visible_agents["spy"]["secret"] == "double_agent"
        # And item's secret
        assert "secret" in snapshot.visible_entities["item"]

    def test_normal_agent_hidden_properties_filtered(self) -> None:
        store, event_log, inbox_mgr, perceiver = self._setup(omniscient_agent=False)
        perceiver.deliver(tick=1)

        inbox = inbox_mgr.get_or_create("observer")
        snapshot = inbox._current_state
        assert snapshot is not None
        # Normal observer should NOT see spy's secret
        assert "secret" not in snapshot.visible_agents["spy"]

    def test_omniscient_does_not_see_admin_events(self) -> None:
        """Admin-scoped events are dashboard-only — no agent receives them."""
        store, event_log, inbox_mgr, perceiver = self._setup(omniscient_agent=True)

        event_log.append(
            Event(
                tick=0,
                type="system",
                source="engine",
                detail="internal event",
                ttl=5,
                scope="admin",
            )
        )

        perceiver.deliver(tick=1)
        inbox = inbox_mgr.get_or_create("observer")
        event_types = [e.type for e in inbox._events]
        assert "system" not in event_types

    def test_normal_agent_cannot_see_admin_events(self) -> None:
        store, event_log, inbox_mgr, perceiver = self._setup(omniscient_agent=False)

        event_log.append(
            Event(
                tick=0,
                type="system",
                source="engine",
                detail="internal event",
                ttl=5,
                scope="admin",
            )
        )

        perceiver.deliver(tick=1)
        inbox = inbox_mgr.get_or_create("spy")
        event_types = [e.type for e in inbox._events]
        assert "system" not in event_types


# ── Emit event highlight flag ────────────────────────────────────────


class TestEmitEventHighlight:
    def test_emit_event_with_highlight_flag(self) -> None:
        from worldseed.dsl.effects import execute as execute_effect
        from worldseed.models.config_schema import EffectConfig

        store = StateStore()
        event_log = EventLog()
        ctx = {"agent_id": "narrator", "action_params": {}, "tick": 1}

        effect = EffectConfig(
            operator="emit_event",
            type="narration",
            detail="Chapter 1: The story begins.",
            ttl=10,
            scope="admin",
            highlight=True,
        )
        execute_effect(effect, store, event_log, ctx, tick=1)

        events = event_log.get_events()
        assert len(events) == 1
        assert events[0].highlight is True


# ── Edge cases ───────────────────────────────────────────────────────


class TestHighlightScannerEdgeCases:
    def test_on_change_retriggers_after_recovery(self) -> None:
        """false → true → false → true should fire twice."""
        store = StateStore()
        store.add(Entity(id="food", type="r", _data={"qty": 5}))
        event_log = EventLog()

        config = _make_config(
            highlights={
                "low": HighlightConfig(
                    trigger=[
                        PreconditionConfig(
                            operator="check",
                            left="food.qty",
                            op="<=",
                            right=2,
                        )
                    ],
                    label="low",
                )
            }
        )
        scanner = HighlightScanner(config, store, event_log)

        # false
        scanner.scan(tick=1)
        assert len(event_log.get_events()) == 0

        # → true (fire)
        store.update_property("food", "qty", 1)
        scanner.scan(tick=2)
        assert len(event_log.get_events()) == 1

        # → false (recover)
        store.update_property("food", "qty", 5)
        scanner.scan(tick=3)
        assert len(event_log.get_events()) == 1

        # → true again (should fire again)
        store.update_property("food", "qty", 0)
        scanner.scan(tick=4)
        assert len(event_log.get_events()) == 2

    def test_multiple_highlights_fire_same_tick(self) -> None:
        store = StateStore()
        store.add(Entity(id="food", type="r", _data={"qty": 0}))
        store.add(Entity(id="water", type="r", _data={"qty": 0}))
        event_log = EventLog()

        config = _make_config(
            highlights={
                "no_food": HighlightConfig(
                    trigger=[
                        PreconditionConfig(
                            operator="check",
                            left="food.qty",
                            op="<=",
                            right=0,
                        )
                    ],
                    label="No food",
                ),
                "no_water": HighlightConfig(
                    trigger=[
                        PreconditionConfig(
                            operator="check",
                            left="water.qty",
                            op="<=",
                            right=0,
                        )
                    ],
                    label="No water",
                ),
            }
        )
        scanner = HighlightScanner(config, store, event_log)
        triggered = scanner.scan(tick=1)
        assert len(triggered) == 2
        labels = {e.detail for e in event_log.get_events()}
        assert labels == {"No food", "No water"}

    def test_entity_highlight_stale_key_pruned(self) -> None:
        """After entity deletion, stale key should be pruned
        so a new entity with the same ID can re-trigger."""
        store = StateStore()
        store.add(Entity(id="a", type="agent", _data={"hp": 1}))
        event_log = EventLog()

        config = _make_config(
            highlights={
                "low_hp": HighlightConfig(
                    trigger=[
                        PreconditionConfig(
                            operator="check",
                            left="$entity.type",
                            op="==",
                            right="agent",
                        ),
                        PreconditionConfig(
                            operator="check",
                            left="$entity.hp",
                            op="<=",
                            right=5,
                        ),
                    ],
                    label="Low HP",
                )
            }
        )
        scanner = HighlightScanner(config, store, event_log)

        # First fire
        scanner.scan(tick=1)
        assert len(event_log.get_events()) == 1

        # Delete entity
        store.remove("a")
        scanner.scan(tick=2)

        # Re-create with same ID
        store.add(Entity(id="a", type="agent", _data={"hp": 1}))
        scanner.scan(tick=3)
        # Should fire again because stale key was pruned
        assert len(event_log.get_events()) == 2

    def test_trigger_eval_error_does_not_crash(self) -> None:
        """Bad trigger expression should not crash the scanner."""
        store = StateStore()
        event_log = EventLog()

        config = _make_config(
            highlights={
                "bad": HighlightConfig(
                    trigger=[
                        PreconditionConfig(
                            operator="check",
                            left="nonexistent.prop",
                            op="==",
                            right=1,
                        )
                    ],
                    label="bad",
                )
            }
        )
        scanner = HighlightScanner(config, store, event_log)
        # Should not raise
        triggered = scanner.scan(tick=1)
        assert triggered == []


class TestOmniscientEdgeCases:
    def _setup_omniscient(
        self,
    ) -> tuple[StateStore, EventLog, InboxManager, Perceiver]:
        from worldseed.agent_registry import AgentRegistry

        config = _make_config(
            hidden_properties=["secret"],
            agents=[
                AgentConfig(id="narrator", omniscient=True),
                AgentConfig(id="spy"),
            ],
        )
        store = StateStore()
        event_log = EventLog()
        inbox_mgr = InboxManager()
        registry = AgentRegistry(config, store)
        registry.register(
            "narrator",
            {},
            {},
            omniscient=True,
        )
        registry.register("spy", {"secret": "x"}, {})

        perceiver = Perceiver(
            store,
            event_log,
            inbox_mgr,
            config.perception,
            registry=registry,
        )
        return store, event_log, inbox_mgr, perceiver

    def test_omniscient_sees_target_only_for_others(self) -> None:
        """Omniscient should see target_only events for other agents."""
        store, event_log, inbox_mgr, perceiver = self._setup_omniscient()
        event_log.append(
            Event(
                tick=0,
                type="whisper",
                source="system",
                detail="secret msg for spy",
                ttl=5,
                scope="target_only",
                target="spy",
            )
        )
        perceiver.deliver(tick=1)

        inbox = inbox_mgr.get_or_create("narrator")
        event_types = [e.type for e in inbox._events]
        assert "whisper" in event_types

    def test_omniscient_sees_custom_scoped_events(self) -> None:
        """Omniscient should see events with custom scopes."""
        store, event_log, inbox_mgr, perceiver = self._setup_omniscient()
        event_log.append(
            Event(
                tick=0,
                type="faction_msg",
                source="spy",
                detail="faction only",
                ttl=5,
                scope="same_faction",
            )
        )
        perceiver.deliver(tick=1)

        inbox = inbox_mgr.get_or_create("narrator")
        event_types = [e.type for e in inbox._events]
        assert "faction_msg" in event_types

    def test_registry_none_falls_back_to_normal(self) -> None:
        """Without registry, all agents get normal perception."""
        store = StateStore()
        store.add(
            Entity(
                id="obs",
                type="agent",
                _data={"role": "n"},
            )
        )
        event_log = EventLog()
        inbox_mgr = InboxManager()

        config = _make_config(hidden_properties=["secret"])
        perceiver = Perceiver(
            store,
            event_log,
            inbox_mgr,
            config.perception,
            registry=None,
        )
        assert perceiver._is_omniscient("obs") is False

    def test_build_agent_view_omniscient(self) -> None:
        """build_agent_view should respect omniscient flag."""
        store, event_log, inbox_mgr, perceiver = self._setup_omniscient()
        event_log.append(
            Event(
                tick=0,
                type="system",
                source="engine",
                detail="admin event",
                ttl=5,
                scope="admin",
            )
        )

        view = perceiver.build_agent_view("narrator", tick=1)
        # Should see spy's hidden property
        assert "secret" in view["visible_agents"]["spy"]
        # Should see admin events
        event_types = [e["type"] for e in view["events"]]
        assert "system" in event_types


class TestEngineHighlightEdgeCases:
    def test_duplicate_entity_creation_no_highlight(self) -> None:
        """Creating an entity that already exists should not emit."""
        from worldseed.dsl.effects import execute as execute_effect
        from worldseed.models.config_schema import EffectConfig

        store = StateStore()
        store.add(Entity(id="sword", type="w", _data={}))
        event_log = EventLog()
        ctx = {"agent_id": "a", "action_params": {}, "tick": 1}

        effect = EffectConfig(
            operator="create_entity",
            id="sword",
            type="w",
        )
        execute_effect(effect, store, event_log, ctx, tick=1)
        highlights = [e for e in event_log.get_events() if e.highlight]
        assert len(highlights) == 0

    def test_remove_nonexistent_entity_no_highlight(self) -> None:
        """Removing nonexistent entity should not emit highlight."""
        from worldseed.dsl.effects import execute as execute_effect
        from worldseed.models.config_schema import EffectConfig

        store = StateStore()
        event_log = EventLog()
        ctx = {"agent_id": "a", "action_params": {}, "tick": 1}

        effect = EffectConfig(
            operator="remove_entity",
            target="ghost",
        )
        execute_effect(effect, store, event_log, ctx, tick=1)
        highlights = [e for e in event_log.get_events() if e.highlight]
        assert len(highlights) == 0
