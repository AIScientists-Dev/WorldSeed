"""Tests for DM Context Builder — full world state format."""

from __future__ import annotations

from worldseed.dm.builder import DMContextBuilder
from worldseed.engine.event_log import EventLog
from worldseed.engine.state_store import StateStore
from worldseed.models import ActionSubmission, Entity, Event
from worldseed.models.config_schema import (
    ActionConfig,
    DMConfig,
    SceneConfig,
    SceneMetaConfig,
)


def _make_config(
    scene_id: str = "test",
    description: str = "A test scene",
) -> SceneConfig:
    return SceneConfig(
        scene=SceneMetaConfig(id=scene_id, description=description),
        entities=[],
        actions={
            "attempt": ActionConfig(
                description="Try anything",
                dm=DMConfig(
                    hint="Judge physical plausibility",
                    allowed_ops=["set", "increment", "emit_event"],
                    max_effects=3,
                ),
            ),
        },
    )


def _make_dm_config(**kwargs: object) -> DMConfig:
    return DMConfig(**kwargs)  # type: ignore[arg-type]


def _make_action(
    agent_id: str = "alice",
    action_type: str = "attempt",
    **params: object,
) -> ActionSubmission:
    return ActionSubmission(
        agent_id=agent_id,
        action_type=action_type,
        params=dict(params),
    )


def _evt(
    tick: int,
    type: str,
    source: str,
    detail: str,
    ttl: int = 5,
    scope: str = "global",
) -> Event:
    return Event(
        tick=tick,
        type=type,
        source=source,
        detail=detail,
        ttl=ttl,
        scope=scope,
    )


class TestWorldState:
    """world_state contains all entities from the store."""

    def test_all_entities_present(self) -> None:
        store = StateStore()
        store.add(Entity(id="food", type="resource", _data={"quantity": 10}))
        store.add(Entity(id="room", type="space", _data={"size": "large"}))
        store.add(Entity(id="alice", type="agent", _data={"hp": 100}))

        builder = DMContextBuilder(store, EventLog(), _make_config())
        ctx = builder.build(_make_action(), _make_dm_config(), tick=1)

        assert "food (resource):" in ctx.world_state
        assert "quantity: 10" in ctx.world_state
        assert "room (space):" in ctx.world_state
        assert "size: large" in ctx.world_state
        assert "alice (agent):" in ctx.world_state
        assert "hp: 100" in ctx.world_state

    def test_agents_grouped_separately(self) -> None:
        store = StateStore()
        store.add(Entity(id="rock", type="object", _data={}))
        store.add(Entity(id="bob", type="agent", _data={"mood": "calm"}))

        builder = DMContextBuilder(store, EventLog(), _make_config())
        ctx = builder.build(_make_action(), _make_dm_config(), tick=1)

        # "Entities:" section should appear before "Agents:" section
        entities_pos = ctx.world_state.find("Entities:")
        agents_pos = ctx.world_state.find("Agents:")
        assert entities_pos >= 0
        assert agents_pos > entities_pos

    def test_dict_and_list_formatting(self) -> None:
        store = StateStore()
        store.add(
            Entity(
                id="alice",
                type="agent",
                _data={
                    "skills": ["cooking", "survival"],
                    "trusts": {"bob": 50, "carol": 70},
                },
            )
        )

        builder = DMContextBuilder(store, EventLog(), _make_config())
        ctx = builder.build(_make_action(), _make_dm_config(), tick=1)

        assert "skills: [cooking, survival]" in ctx.world_state
        assert "trusts: {bob: 50, carol: 70}" in ctx.world_state

    def test_empty_store(self) -> None:
        store = StateStore()
        builder = DMContextBuilder(store, EventLog(), _make_config())
        ctx = builder.build(_make_action(), _make_dm_config(), tick=1)

        # No entities → empty string
        assert ctx.world_state == ""


class TestRecentEvents:
    """recent_events contains events from last 5 ticks."""

    def test_events_within_lookback(self) -> None:
        event_log = EventLog()
        event_log.append(_evt(tick=3, type="move", source="alice", detail="went north"))
        event_log.append(_evt(tick=4, type="say", source="bob", detail="hello"))

        builder = DMContextBuilder(StateStore(), event_log, _make_config())
        ctx = builder.build(_make_action(), _make_dm_config(), tick=5)

        assert "[tick 3] move (alice): went north" in ctx.recent_events
        assert "[tick 4] say (bob): hello" in ctx.recent_events

    def test_old_events_excluded(self) -> None:
        event_log = EventLog()
        event_log.append(_evt(tick=1, type="ancient", source="sys", detail="old stuff", ttl=10))
        event_log.append(_evt(tick=8, type="recent", source="sys", detail="new stuff"))

        builder = DMContextBuilder(StateStore(), event_log, _make_config())
        ctx = builder.build(_make_action(), _make_dm_config(), tick=10)

        # tick 1 is outside lookback window (10 - 5 = 5, so since_tick=5)
        assert "ancient" not in ctx.recent_events
        assert "[tick 8] recent (sys): new stuff" in ctx.recent_events

    def test_no_events(self) -> None:
        builder = DMContextBuilder(StateStore(), EventLog(), _make_config())
        ctx = builder.build(_make_action(), _make_dm_config(), tick=1)

        assert ctx.recent_events == "  (none)"

    def test_chronological_order(self) -> None:
        event_log = EventLog()
        event_log.append(_evt(tick=2, type="first", source="a", detail="one"))
        event_log.append(_evt(tick=3, type="second", source="b", detail="two"))
        event_log.append(_evt(tick=4, type="third", source="c", detail="three"))

        builder = DMContextBuilder(StateStore(), event_log, _make_config())
        ctx = builder.build(_make_action(), _make_dm_config(), tick=5)

        lines = ctx.recent_events.strip().split("\n")
        assert len(lines) == 3
        assert "first" in lines[0]
        assert "second" in lines[1]
        assert "third" in lines[2]

    def test_source_omitted_when_empty(self) -> None:
        event_log = EventLog()
        event_log.append(_evt(tick=1, type="system", source="", detail="tick started"))

        builder = DMContextBuilder(StateStore(), event_log, _make_config())
        ctx = builder.build(_make_action(), _make_dm_config(), tick=3)

        # No "()" around empty source
        assert "[tick 1] system: tick started" in ctx.recent_events
        assert "()" not in ctx.recent_events


class TestSceneDescription:
    """scene_description comes from config."""

    def test_scene_description(self) -> None:
        config = _make_config(description="A doomsday bunker")
        builder = DMContextBuilder(StateStore(), EventLog(), config)
        ctx = builder.build(_make_action(), _make_dm_config(), tick=1)

        assert ctx.scene_description == "A doomsday bunker"

    def test_different_scenes(self) -> None:
        for desc in ["A small bakery", "An internet forum", "A starship in deep space"]:
            config = _make_config(description=desc)
            builder = DMContextBuilder(StateStore(), EventLog(), config)
            ctx = builder.build(_make_action(), _make_dm_config(), tick=1)
            assert ctx.scene_description == desc


class TestDMConfig:
    """hint, allowed_ops, max_effects come from DMConfig."""

    def test_hint_passed_through(self) -> None:
        dm_config = _make_dm_config(hint="Judge physical plausibility")
        builder = DMContextBuilder(StateStore(), EventLog(), _make_config())
        ctx = builder.build(_make_action(), dm_config, tick=1)

        assert ctx.hint == "Judge physical plausibility"

    def test_allowed_ops_passed_through(self) -> None:
        dm_config = _make_dm_config(allowed_ops=["set", "emit_event"])
        builder = DMContextBuilder(StateStore(), EventLog(), _make_config())
        ctx = builder.build(_make_action(), dm_config, tick=1)

        assert ctx.allowed_ops == ["set", "emit_event"]

    def test_max_effects_passed_through(self) -> None:
        dm_config = _make_dm_config(max_effects=7)
        builder = DMContextBuilder(StateStore(), EventLog(), _make_config())
        ctx = builder.build(_make_action(), dm_config, tick=1)

        assert ctx.max_effects == 7

    def test_default_dm_config(self) -> None:
        dm_config = DMConfig()
        builder = DMContextBuilder(StateStore(), EventLog(), _make_config())
        ctx = builder.build(_make_action(), dm_config, tick=1)

        assert ctx.hint == ""
        assert ctx.allowed_ops == ["set", "increment", "decrement", "emit_event"]
        assert ctx.max_effects == 5

    def test_action_preserved(self) -> None:
        action = _make_action(agent_id="old_chen", description="steal some cans")
        builder = DMContextBuilder(StateStore(), EventLog(), _make_config())
        ctx = builder.build(action, _make_dm_config(), tick=1)

        assert ctx.action is action
        assert ctx.action.agent_id == "old_chen"
        assert ctx.action.params["description"] == "steal some cans"


class TestDiverseScenes:
    """Integration: different scene schemas produce correct context."""

    def test_bunker_scene(self) -> None:
        store = StateStore()
        store.add(
            Entity(
                id="old_chen",
                type="agent",
                _data={"location": "storage_room", "stress": 80},
            )
        )
        store.add(
            Entity(
                id="food_supply",
                type="resource",
                _data={"quantity": 18, "location": "storage_room"},
            )
        )
        event_log = EventLog()
        event_log.append(
            Event(
                tick=46,
                type="scarcity",
                source="system",
                detail="food critically low",
                ttl=5,
                scope="global",
            )
        )

        config = _make_config(description="A doomsday bunker")
        dm_config = _make_dm_config(
            hint="Judge based on physical plausibility and survival pressure",
        )
        builder = DMContextBuilder(store, event_log, config)
        action = _make_action(agent_id="old_chen", description="steal some cans")
        ctx = builder.build(action, dm_config, tick=48)

        assert "old_chen (agent):" in ctx.world_state
        assert "food_supply (resource):" in ctx.world_state
        assert "scarcity" in ctx.recent_events
        assert ctx.scene_description == "A doomsday bunker"

    def test_bakery_no_location(self) -> None:
        store = StateStore()
        store.add(Entity(id="baker", type="agent", _data={"skill": 80, "coins": 10}))
        store.add(Entity(id="oven", type="equipment", _data={"temperature": 200}))

        config = _make_config(description="A small bakery")
        builder = DMContextBuilder(store, EventLog(), config)
        ctx = builder.build(_make_action(agent_id="baker"), _make_dm_config(), tick=1)

        assert "baker (agent):" in ctx.world_state
        assert "skill: 80" in ctx.world_state
        assert "oven (equipment):" in ctx.world_state
        assert "location" not in ctx.world_state

    def test_starship_uses_sector(self) -> None:
        store = StateStore()
        store.add(
            Entity(
                id="captain",
                type="agent",
                _data={"sector": "bridge", "rank": "commander"},
            )
        )
        store.add(Entity(id="engine_room", type="module", _data={"power_output": 85}))

        config = _make_config(description="A starship in deep space")
        builder = DMContextBuilder(store, EventLog(), config)
        ctx = builder.build(_make_action(agent_id="captain"), _make_dm_config(), tick=1)

        assert "sector: bridge" in ctx.world_state
        assert "engine_room (module):" in ctx.world_state
