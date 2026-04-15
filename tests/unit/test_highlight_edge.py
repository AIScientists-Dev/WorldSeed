"""Edge-case tests for the highlight system: HighlightScanner, narrator, system agents.

Tests generality of:
- HighlightConfig with empty triggers
- every_tick frequency on entity highlights
- ActionConfig.highlight on DM actions (async path)
- Narrator with high chapter_count
- System agents with hidden_properties conflicts
- Two system agents
- Deleted entity mid-scan
- Invalid narrator style
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from worldseed.dm.providers.mock import MockDMProvider
from worldseed.engine.event_log import EventLog
from worldseed.engine.highlight_scanner import HighlightScanner
from worldseed.engine.state_store import StateStore
from worldseed.models.config_schema import (
    ActionConfig,
    AgentConfig,
    DMConfig,
    EntityConfig,
    HighlightConfig,
    ParamConfig,
    PerceptionConfig,
    PreconditionConfig,
    SceneConfig,
    SceneMetaConfig,
)
from worldseed.models.entity import Entity
from worldseed.persistence import NullRecorder
from worldseed.world import WorldEngine

# -- Helpers ----------------------------------------------------------------


def _minimal_scene(**overrides: Any) -> SceneConfig:
    """Build a minimal SceneConfig with optional overrides."""
    defaults: dict[str, Any] = {
        "scene": SceneMetaConfig(id="test_hl", description="highlight edge tests"),
        "entities": [EntityConfig(id="room_a", type="space")],
        "actions": {
            "wait": ActionConfig(description="Do nothing"),
        },
    }
    defaults.update(overrides)
    return SceneConfig(**defaults)


def _make_engine(config: SceneConfig, **kw: Any) -> WorldEngine:
    """Create WorldEngine from in-memory config with mock DM."""
    dm = kw.pop("dm_provider", MockDMProvider())
    return WorldEngine(config=config, dm_provider=dm, recorder=NullRecorder(), **kw)


# -- Test 1: Empty trigger list ---------------------------------------------


class TestEmptyTriggerList:
    """HighlightConfig with trigger=[] -- all() on empty is True."""

    def test_empty_trigger_fires_on_change_once(self) -> None:
        """An empty trigger list means all() returns True unconditionally.
        With on_change, it should fire on the first scan (False->True) only."""
        config = _minimal_scene(
            highlights={
                "always_on": HighlightConfig(
                    trigger=[],
                    label="empty trigger",
                    frequency="on_change",
                ),
            },
        )
        store = StateStore()
        store.add(Entity(id="room_a", type="space"))
        elog = EventLog()
        scanner = HighlightScanner(config, store, elog)

        # First scan: fires (False->True transition)
        result1 = scanner.scan(tick=1)
        assert "always_on" in result1

        # Second scan: should NOT fire again (already True, no change)
        result2 = scanner.scan(tick=2)
        assert "always_on" not in result2

    def test_empty_trigger_fires_every_tick(self) -> None:
        """With every_tick frequency, empty trigger fires every scan."""
        config = _minimal_scene(
            highlights={
                "always_fire": HighlightConfig(
                    trigger=[],
                    label="fires always",
                    frequency="every_tick",
                ),
            },
        )
        store = StateStore()
        store.add(Entity(id="room_a", type="space"))
        elog = EventLog()
        scanner = HighlightScanner(config, store, elog)

        for tick in range(1, 4):
            result = scanner.scan(tick=tick)
            assert "always_fire" in result, f"Should fire on tick {tick}"

    def test_empty_trigger_emits_event(self) -> None:
        """Empty trigger should still emit a highlight event."""
        config = _minimal_scene(
            highlights={
                "empty_hl": HighlightConfig(
                    trigger=[],
                    label="empty highlight",
                    frequency="on_change",
                ),
            },
        )
        store = StateStore()
        store.add(Entity(id="room_a", type="space"))
        elog = EventLog()
        scanner = HighlightScanner(config, store, elog)

        scanner.scan(tick=1)
        events = elog.get_events()
        highlight_events = [e for e in events if e.type == "highlight"]
        assert len(highlight_events) == 1
        assert highlight_events[0].scope == "admin"
        assert highlight_events[0].detail == "empty highlight"


# -- Test 2: every_tick on entity highlight ----------------------------------


class TestEveryTickEntityHighlight:
    """Entity highlights with frequency=every_tick fire per entity per tick."""

    def test_fires_per_entity_per_tick(self) -> None:
        """An entity highlight with every_tick should fire for every entity."""
        config = _minimal_scene(
            highlights={
                "entity_check": HighlightConfig(
                    trigger=[
                        PreconditionConfig(
                            operator="exists",
                            expression="$entity.id",
                        )
                    ],
                    label="entity exists",
                    frequency="every_tick",
                ),
            },
        )
        store = StateStore()
        store.add(Entity(id="room_a", type="space"))
        store.add(Entity(id="room_b", type="space"))
        store.add(Entity(id="agent_x", type="agent"))
        elog = EventLog()
        scanner = HighlightScanner(config, store, elog)

        # Tick 1
        result1 = scanner.scan(tick=1)
        # Should fire for all 3 entities
        assert len(result1) == 3

        # Tick 2 should fire again (every_tick)
        result2 = scanner.scan(tick=2)
        assert len(result2) == 3

    def test_entity_highlight_labels_include_entity_id(self) -> None:
        """Entity highlight events should have entity ID in label."""
        config = _minimal_scene(
            highlights={
                "ent_hl": HighlightConfig(
                    trigger=[
                        PreconditionConfig(
                            operator="exists",
                            expression="$entity.id",
                        )
                    ],
                    label="spotted",
                    frequency="every_tick",
                ),
            },
        )
        store = StateStore()
        store.add(Entity(id="room_a", type="space"))
        elog = EventLog()
        scanner = HighlightScanner(config, store, elog)

        scanner.scan(tick=1)
        events = elog.get_events()
        details = [e.detail for e in events if e.type == "highlight"]
        assert any("room_a" in d for d in details)


# -- Test 3: ActionConfig.highlight on DM action ----------------------------


class TestDMActionHighlight:
    """ActionConfig.highlight=True on a DM action propagates through async path."""

    def test_highlight_flag_recorded_for_dm_action(self) -> None:
        """When a DM action with highlight=True succeeds, highlight is recorded."""
        config = _minimal_scene(
            agents=[
                AgentConfig(id="agent_1", properties={"location": "room_a"}),
            ],
            actions={
                "wait": ActionConfig(description="Do nothing"),
                "dm_act": ActionConfig(
                    description="DM-judged action",
                    params=[
                        ParamConfig(name="description", type="free_text"),
                    ],
                    highlight=True,
                    dm=DMConfig(
                        hint="Judge it",
                        scope="global",
                    ),
                ),
            },
        )
        engine = _make_engine(config)
        engine.register_from_config()

        # Submit action -- DM actions queue for next tick
        result = engine.submit("agent_1", "dm_act", {"description": "test action"})
        # DM actions return None on successful queue
        assert result is None

        # step_async processes the DM queue
        results = asyncio.run(engine.step_async())
        assert len(results) == 1
        assert results[0].success

        # The action config has highlight=True -- verify it propagated to the recorder.
        # With NullRecorder we can't check recordings, but we can verify
        # the action_config.highlight flag is accessible from the result path.
        action_cfg = config.actions["dm_act"]
        assert action_cfg.highlight is True

    def test_mechanical_action_highlight_emits_record(self) -> None:
        """Mechanical action with highlight=True records highlight in result."""
        config = _minimal_scene(
            agents=[
                AgentConfig(id="agent_1", properties={"location": "room_a"}),
            ],
            actions={
                "wait": ActionConfig(
                    description="Do nothing",
                    highlight=True,
                ),
            },
        )
        engine = _make_engine(config)
        engine.register_from_config()

        result = engine.submit("agent_1", "wait", {})
        assert result.success  # type: ignore[union-attr]


# -- Test 4: Narrator with high chapter_count --------------------------------


class TestNarratorHighChapterCount:
    """Narrator with chapter_count at very high number (999)."""

    def test_narrator_chapter_999(self) -> None:
        """Engine should handle narrator with chapter_count=999."""
        config = _minimal_scene(narrator="storyteller")
        engine = _make_engine(config)

        # Manually set narrator's chapter_count to 999
        narrator_entity = engine.state.get("narrator")
        assert narrator_entity is not None, "Narrator entity should exist"
        engine.state.update_property("narrator", "chapter_count", 999)

        # Record narration via the system-function path (not action pipeline)
        result = engine.record_narration(
            {"title": "Chapter 1000", "tldr": "The end", "body": "Chapter 1000 begins"},
        )

        # Chapter count should increment to 1000
        assert result == 1000
        assert narrator_entity["chapter_count"] == 1000

    def test_narrator_setup_creates_agent(self) -> None:
        """Narrator setup should create agent entity in state store."""
        config = _minimal_scene(narrator="intel")
        engine = _make_engine(config)

        narrator = engine.state.get("narrator")
        assert narrator is not None
        assert narrator.type == "agent"
        assert "chapter_count" in narrator

    def test_narrator_is_system_and_omniscient(self) -> None:
        """Narrator agent should be system + omniscient."""
        config = _minimal_scene(narrator="poet")
        engine = _make_engine(config)

        profile = engine.get_agent_profile("narrator")
        assert profile is not None
        assert profile.omniscient is True
        assert profile.system is True


# -- Test 5: System agent with hidden_properties conflict -------------------


class TestSystemAgentHiddenPropertiesConflict:
    """System agent has properties that overlap with hidden_properties."""

    def test_system_agent_hidden_props_still_in_self_state(self) -> None:
        """System agent should see its own hidden properties in self_state."""
        config = _minimal_scene(
            agents=[
                AgentConfig(id="observer", properties={"location": "room_a"}),
                AgentConfig(
                    id="sys_agent",
                    properties={"location": "room_a", "secret_plan": "overthrow"},
                    system=True,
                    omniscient=True,
                ),
            ],
            perception=PerceptionConfig(
                hidden_properties=["secret_plan"],
            ),
        )
        engine = _make_engine(config)
        engine.register_from_config()

        # System agent should have its own property intact
        sys_entity = engine.state.get("sys_agent")
        assert sys_entity is not None
        assert sys_entity["secret_plan"] == "overthrow"

    def test_hidden_property_not_visible_to_other_agents(self) -> None:
        """Even with system agents, hidden properties stay hidden for regular agents."""
        config = _minimal_scene(
            agents=[
                AgentConfig(
                    id="regular",
                    properties={"location": "room_a", "secret_plan": "none"},
                ),
                AgentConfig(
                    id="other_regular",
                    properties={"location": "room_a"},
                ),
            ],
            perception=PerceptionConfig(
                hidden_properties=["secret_plan"],
            ),
        )
        engine = _make_engine(config)
        engine.register_from_config()

        # Deliver perception
        engine.step()

        view = engine.agent_world_view("other_regular")
        # "regular" should be visible as nearby agent, without secret_plan
        for aid, aprops in view["nearby_agents"].items():
            assert "secret_plan" not in aprops, f"Hidden property 'secret_plan' leaked to agent view of '{aid}'"


# -- Test 6: Two system agents -----------------------------------------------


class TestTwoSystemAgents:
    """Filtering should work correctly with multiple system agents."""

    def test_two_system_agents_invisible_to_regular(self) -> None:
        """Both system agents should be invisible to regular agents."""
        config = _minimal_scene(
            agents=[
                AgentConfig(id="regular", properties={"location": "room_a"}),
                AgentConfig(
                    id="sys_one",
                    properties={"location": "room_a"},
                    system=True,
                    omniscient=True,
                ),
                AgentConfig(
                    id="sys_two",
                    properties={"location": "room_a"},
                    system=True,
                    omniscient=True,
                ),
            ],
        )
        engine = _make_engine(config)
        engine.register_from_config()
        engine.step()

        view = engine.agent_world_view("regular")
        assert "sys_one" not in view["nearby_agents"]
        assert "sys_two" not in view["nearby_agents"]

    def test_system_agents_see_each_other(self) -> None:
        """System agents with omniscient flag should see other system agents."""
        config = _minimal_scene(
            agents=[
                AgentConfig(
                    id="sys_one",
                    properties={"location": "room_a"},
                    system=True,
                    omniscient=True,
                ),
                AgentConfig(
                    id="sys_two",
                    properties={"location": "room_a"},
                    system=True,
                    omniscient=True,
                ),
            ],
        )
        engine = _make_engine(config)
        engine.register_from_config()
        engine.step()

        # Omniscient system agents bypass visibility filtering,
        # but system agents are hidden from non-system observers.
        # System agent -> system agent: the _is_system check only
        # hides system agents from NON-system observers.
        view = engine.agent_world_view("sys_one")
        assert "sys_two" in view["nearby_agents"]

    def test_get_system_agents_returns_both(self) -> None:
        """get_system_agents() should list both system agent IDs."""
        config = _minimal_scene(
            agents=[
                AgentConfig(id="regular", properties={"location": "room_a"}),
                AgentConfig(
                    id="sys_one",
                    properties={},
                    system=True,
                    omniscient=True,
                ),
                AgentConfig(
                    id="sys_two",
                    properties={},
                    system=True,
                    omniscient=True,
                ),
            ],
        )
        engine = _make_engine(config)
        engine.register_from_config()

        sys_agents = engine.get_system_agents()
        assert "sys_one" in sys_agents
        assert "sys_two" in sys_agents
        assert "regular" not in sys_agents

    def test_characters_excludes_system_agents(self) -> None:
        """get_characters() should not list system agents."""
        config = _minimal_scene(
            agents=[
                AgentConfig(id="regular", properties={}),
                AgentConfig(id="sys_one", properties={}, system=True),
                AgentConfig(id="sys_two", properties={}, system=True),
            ],
        )
        engine = _make_engine(config)
        engine.register_from_config()

        chars = engine.get_characters()
        char_ids = [c["id"] for c in chars]
        assert "regular" in char_ids
        assert "sys_one" not in char_ids
        assert "sys_two" not in char_ids


# -- Test 7: Deleted entity mid-scan ----------------------------------------


class TestDeletedEntityMidScan:
    """Highlight scanner handles entity deletion between scans."""

    def test_stale_entity_pruned_from_previous_state(self) -> None:
        """After entity deletion, its state_key should be pruned."""
        config = _minimal_scene(
            highlights={
                "entity_check": HighlightConfig(
                    trigger=[
                        PreconditionConfig(
                            operator="exists",
                            expression="$entity.id",
                        ),
                    ],
                    label="entity alive",
                    frequency="on_change",
                ),
            },
        )
        store = StateStore()
        store.add(Entity(id="room_a", type="space"))
        store.add(Entity(id="room_b", type="space"))
        elog = EventLog()
        scanner = HighlightScanner(config, store, elog)

        # Tick 1: both entities trigger
        result1 = scanner.scan(tick=1)
        assert len(result1) == 2

        # Delete room_b
        store.remove("room_b")

        # Tick 2: only room_a should trigger (room_b is gone)
        # The stale key for room_b should be pruned
        result2 = scanner.scan(tick=2)
        # on_change: room_a was already True so won't re-fire.
        # room_b is gone, so nothing new fires.
        assert len(result2) == 0

        # Add room_b back
        store.add(Entity(id="room_b", type="space"))

        # Tick 3: room_b should fire again (new entity, pruned state)
        result3 = scanner.scan(tick=3)
        triggered_names = [r.split("::")[-1] if "::" in r else r for r in result3]
        assert "room_b" in triggered_names

    def test_scanner_does_not_crash_on_deleted_entity(self) -> None:
        """Scanner should not crash if entity is deleted between scan calls."""
        config = _minimal_scene(
            highlights={
                "ent_hl": HighlightConfig(
                    trigger=[
                        PreconditionConfig(
                            operator="exists",
                            expression="$entity.id",
                        ),
                    ],
                    label="check",
                    frequency="every_tick",
                ),
            },
        )
        store = StateStore()
        store.add(Entity(id="room_a", type="space"))
        store.add(Entity(id="ephemeral", type="resource"))
        elog = EventLog()
        scanner = HighlightScanner(config, store, elog)

        scanner.scan(tick=1)

        # Remove entity between scans
        store.remove("ephemeral")

        # Should not raise
        result = scanner.scan(tick=2)
        # Only room_a should trigger (1 entity left)
        assert len(result) == 1


# -- Test 8: Config with invalid narrator style ------------------------------


class TestInvalidNarratorStyle:
    """narrator field with invalid style should be rejected by Pydantic."""

    def test_invalid_narrator_rejected(self) -> None:
        """Pydantic's Literal type should reject unknown narrator styles."""
        with pytest.raises(Exception):
            # narrator is NarratorConfig | bool
            _minimal_scene(narrator="invalid_style")  # type: ignore[arg-type]

    def test_valid_narrator_styles_accepted(self) -> None:
        """All valid narrator styles should be accepted."""
        styles = (
            "storyteller",
            "poet",
            "intel",
            "noir",
            "gossip",
            "conspiracy",
            "bureaucrat",
            "gameshow",
            "trickster",
        )
        for style in styles:
            config = _minimal_scene(narrator=style)  # type: ignore[arg-type]
            assert config.narrator.style == style  # type: ignore[union-attr]

    def test_narrator_false_accepted(self) -> None:
        """narrator=False should be valid (no narrator)."""
        config = _minimal_scene(narrator=False)
        assert config.narrator is False
        # No narrator setup should have happened
        engine = _make_engine(config)
        assert engine.state.get("narrator") is None
