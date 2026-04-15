"""Regression tests: verify ChangeHistory removal has no side effects.

Tests that:
1. ChangeHistory/ChangeRecord are fully gone from production code.
2. All effect types still work without history.
3. Property changes are observable via entity, perceive, and the state API.
4. Validator physics/smoke/sanity still work.
5. /api/runs/{run_id}/stream returns only stream records (no changes field).
6. Connector notify mechanism works correctly.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from tests.helpers import CONFIGS_DIR
from worldseed.connector.mock import MockConnector
from worldseed.engine.event_log import EventLog
from worldseed.engine.state_store import StateStore
from worldseed.models.config_schema import (
    ActionConfig,
    AgentConfig,
    AutoTickConfig,
    EffectConfig,
    EntityConfig,
    EventConfig,
    ParamConfig,
    PerceptionConfig,
    PreconditionConfig,
    SceneConfig,
    SceneMetaConfig,
)
from worldseed.models.entity import Entity
from worldseed.persistence import RunRecorder
from worldseed.scene.validator import validate
from worldseed.server.app import create_app
from worldseed.server.tick_runner import TickRunner
from worldseed.world import WorldEngine

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"


def _build_api_engine(
    config: SceneConfig,
) -> tuple[WorldEngine, TestClient, str]:
    """Build an engine with a real RunRecorder + TestClient for API tests.

    Returns (engine, client, run_id). Caller must clean up run dir after test.
    """
    import secrets

    run_id = "test_" + secrets.token_hex(4)
    recorder = RunRecorder(
        run_id=run_id,
        config_path=None,
        scene_id=config.scene.id,
        dm_model="",
    )
    engine = WorldEngine(config=config, recorder=recorder)
    engine.register_from_config()
    # Write initial state so API can read it before any step()
    engine.save_state()
    app = create_app(engine, tick_interval=1.0, run_id=run_id)
    client = TestClient(app)
    return engine, client, run_id


def _cleanup_run(run_id: str) -> None:
    """Remove test run directory."""
    import shutil

    run_dir = Path.home() / ".worldseed" / "runs" / run_id
    if run_dir.exists():
        shutil.rmtree(run_dir)


# ============================================================
# Helper: build inline configs for tests
# ============================================================


def _mini_config(
    *,
    entities: list[EntityConfig] | None = None,
    agents: list[AgentConfig] | None = None,
    actions: dict[str, ActionConfig] | None = None,
    auto_tick: list[AutoTickConfig] | None = None,
) -> SceneConfig:
    """Build a minimal inline SceneConfig."""
    return SceneConfig(
        narrator=False,
        scene=SceneMetaConfig(
            id="regression_test",
            description="Regression test scene",
        ),
        entities=entities
        or [
            EntityConfig(
                id="room",
                type="space",
                properties={"description": "A room"},
            ),
        ],
        agents=agents
        or [
            AgentConfig(
                id="alice",
                properties={"location": "room", "hp": 100, "gold": 50},
                character={"personality": "tester"},
            ),
        ],
        actions=actions
        or {
            "wait": ActionConfig(description="Do nothing"),
        },
        auto_tick=auto_tick or [],
    )


def _build_engine(config: SceneConfig) -> WorldEngine:
    """Create and populate a WorldEngine from an inline config."""
    engine = WorldEngine(config=config)
    engine.register_from_config()
    return engine


# ============================================================
# 1. ChangeHistory fully gone
# ============================================================


class TestChangeHistoryRemoved:
    """Confirm ChangeHistory/ChangeRecord have no presence in production code."""

    def test_world_engine_has_no_history_attribute(self) -> None:
        """WorldEngine must not have a .history attribute."""
        engine = _build_engine(_mini_config())
        assert not hasattr(engine, "history"), "WorldEngine should not have .history attribute"

    def test_no_change_record_import_in_production(self) -> None:
        """No Python file under src/ should import ChangeRecord."""
        result = subprocess.run(
            ["grep", "-r", "ChangeRecord", str(SRC_DIR)],
            capture_output=True,
            text=True,
        )
        # Filter out __pycache__ and .pyc files
        matches = [
            line
            for line in result.stdout.strip().splitlines()
            if line and "__pycache__" not in line and ".pyc" not in line
        ]
        assert matches == [], f"ChangeRecord found in production code: {matches}"

    def test_no_change_history_in_production(self) -> None:
        """No Python file under src/ should reference ChangeHistory."""
        result = subprocess.run(
            ["grep", "-r", "ChangeHistory", str(SRC_DIR)],
            capture_output=True,
            text=True,
        )
        matches = [
            line
            for line in result.stdout.strip().splitlines()
            if line and "__pycache__" not in line and ".pyc" not in line
        ]
        assert matches == [], f"ChangeHistory found in production code: {matches}"

    def test_grep_src_for_both_terms_zero_hits(self) -> None:
        """Combined grep for ChangeHistory OR ChangeRecord in src/ yields zero."""
        result = subprocess.run(
            ["grep", "-rE", "ChangeHistory|ChangeRecord", str(SRC_DIR)],
            capture_output=True,
            text=True,
        )
        matches = [
            line
            for line in result.stdout.strip().splitlines()
            if line and "__pycache__" not in line and ".pyc" not in line
        ]
        assert matches == [], f"ChangeHistory/ChangeRecord found: {matches}"

    def test_state_store_has_no_history(self) -> None:
        """StateStore should not carry any history-related attribute."""
        store = StateStore()
        assert not hasattr(store, "history")
        assert not hasattr(store, "change_history")
        assert not hasattr(store, "_history")

    def test_rules_engine_has_no_history(self) -> None:
        """RulesEngine should not reference history."""
        from worldseed.engine.rules_engine import RulesEngine

        config = _mini_config()
        store = StateStore()
        event_log = EventLog()
        rules = RulesEngine(config, store, event_log)
        assert not hasattr(rules, "history")
        assert not hasattr(rules, "_history")


# ============================================================
# 2. Effects still work without history
# ============================================================


class TestEffectsStillWork:
    """All effect types must function without ChangeHistory."""

    def _make_engine_with_effects(self) -> WorldEngine:
        """Build engine with actions exercising every effect type."""
        config = SceneConfig(
            scene=SceneMetaConfig(id="effects_test", description="Effects regression"),
            entities=[
                EntityConfig(
                    id="room",
                    type="space",
                    properties={"description": "Test room"},
                ),
                EntityConfig(
                    id="crate",
                    type="object",
                    properties={"durability": 10, "weight": 5},
                ),
            ],
            agents=[
                AgentConfig(
                    id="tester",
                    properties={"location": "room", "hp": 100, "gold": 50, "xp": 0},
                    character={"personality": "test"},
                ),
            ],
            actions={
                "set_hp": ActionConfig(
                    description="Set hp",
                    params=[ParamConfig(name="value", type="number")],
                    effects=[
                        EffectConfig(
                            operator="set",
                            target="$agent.hp",
                            value="$value",
                        ),
                    ],
                ),
                "gain_gold": ActionConfig(
                    description="Gain gold",
                    params=[ParamConfig(name="amount", type="number")],
                    effects=[
                        EffectConfig(
                            operator="increment",
                            target="$agent.gold",
                            by="$amount",
                        ),
                    ],
                ),
                "spend_gold": ActionConfig(
                    description="Spend gold",
                    params=[ParamConfig(name="amount", type="number")],
                    effects=[
                        EffectConfig(
                            operator="decrement",
                            target="$agent.gold",
                            by="$amount",
                        ),
                    ],
                ),
                "create_item": ActionConfig(
                    description="Create an item",
                    effects=[
                        EffectConfig(
                            operator="create_entity",
                            id="new_item",
                            type="object",
                            properties={"name": "sword"},
                        ),
                    ],
                ),
                "destroy_crate": ActionConfig(
                    description="Destroy the crate",
                    effects=[
                        EffectConfig(
                            operator="remove_entity",
                            target="crate",
                        ),
                    ],
                ),
                "shout": ActionConfig(
                    description="Shout a message",
                    effects=[
                        EffectConfig(
                            operator="emit_event",
                            type="shout",
                            detail="$agent shouts!",
                            ttl=2,
                            scope="global",
                        ),
                    ],
                ),
                "wait": ActionConfig(description="Do nothing"),
            },
        )
        engine = WorldEngine(config=config)
        engine.register_from_config()
        return engine

    def test_set_effect(self) -> None:
        """set effect changes property correctly."""
        from worldseed.engine.rules_engine import ActionResult

        engine = self._make_engine_with_effects()
        result = engine.submit("tester", "set_hp", {"value": 75})
        assert isinstance(result, ActionResult) and result.success
        engine.step()  # still needed for auto_tick/consequences/perceiver
        entity = engine.state.get("tester")
        assert entity is not None
        assert entity["hp"] == 75

    def test_increment_effect(self) -> None:
        """increment works correctly."""
        from worldseed.engine.rules_engine import ActionResult

        engine = self._make_engine_with_effects()
        result = engine.submit("tester", "gain_gold", {"amount": 10})
        assert isinstance(result, ActionResult) and result.success
        engine.step()
        entity = engine.state.get("tester")
        assert entity is not None
        assert entity["gold"] == 60

    def test_decrement_effect(self) -> None:
        """decrement works correctly."""
        from worldseed.engine.rules_engine import ActionResult

        engine = self._make_engine_with_effects()
        result = engine.submit("tester", "spend_gold", {"amount": 15})
        assert isinstance(result, ActionResult) and result.success
        engine.step()
        entity = engine.state.get("tester")
        assert entity is not None
        assert entity["gold"] == 35

    def test_create_entity_effect(self) -> None:
        """create_entity works correctly."""
        from worldseed.engine.rules_engine import ActionResult

        engine = self._make_engine_with_effects()
        assert engine.state.get("new_item") is None
        result = engine.submit("tester", "create_item")
        assert isinstance(result, ActionResult) and result.success
        engine.step()
        new_item = engine.state.get("new_item")
        assert new_item is not None
        assert new_item.type == "object"
        assert new_item["name"] == "sword"

    def test_remove_entity_effect(self) -> None:
        """remove_entity works correctly."""
        from worldseed.engine.rules_engine import ActionResult

        engine = self._make_engine_with_effects()
        assert engine.state.get("crate") is not None
        result = engine.submit("tester", "destroy_crate")
        assert isinstance(result, ActionResult) and result.success
        engine.step()
        assert engine.state.get("crate") is None

    def test_emit_event_effect(self) -> None:
        """emit_event works correctly."""
        from worldseed.engine.rules_engine import ActionResult

        engine = self._make_engine_with_effects()
        result = engine.submit("tester", "shout")
        assert isinstance(result, ActionResult) and result.success
        engine.step()
        events = engine.event_log.get_events()
        assert any(e.type == "shout" for e in events)
        shout_event = next(e for e in events if e.type == "shout")
        assert shout_event.detail == "tester shouts!"
        assert shout_event.source == "tester"

    def test_all_effects_in_sequence(self) -> None:
        """Run all effect types in sequence without error."""
        from worldseed.engine.rules_engine import ActionResult

        engine = self._make_engine_with_effects()

        # set (mechanical: executes immediately)
        r = engine.submit("tester", "set_hp", {"value": 80})
        assert isinstance(r, ActionResult) and r.success
        engine.step()

        # increment
        r = engine.submit("tester", "gain_gold", {"amount": 5})
        assert isinstance(r, ActionResult) and r.success
        engine.step()

        # decrement
        r = engine.submit("tester", "spend_gold", {"amount": 3})
        assert isinstance(r, ActionResult) and r.success
        engine.step()

        # create
        r = engine.submit("tester", "create_item")
        assert isinstance(r, ActionResult) and r.success
        engine.step()

        # emit
        r = engine.submit("tester", "shout")
        assert isinstance(r, ActionResult) and r.success
        engine.step()

        # remove
        r = engine.submit("tester", "destroy_crate")
        assert isinstance(r, ActionResult) and r.success
        engine.step()

        # Verify final state
        tester = engine.state.get("tester")
        assert tester is not None
        assert tester["gold"] == 52  # 50 + 5 - 3
        assert engine.state.get("new_item") is not None
        assert engine.state.get("crate") is None

    def test_add_relationship_effect(self) -> None:
        """add_relationship effect works without history."""
        from worldseed.dsl.effects import execute

        store = StateStore()
        store.add(Entity(id="a", type="agent", _data={}))
        store.add(Entity(id="b", type="agent", _data={}))
        event_log = EventLog()

        effect = EffectConfig(
            operator="add_relationship",
            from_entity="a",
            type="trusts",
            to="b",
            value=50,
        )
        ctx = {"agent_id": "a", "action_params": {}}
        execute(effect, store, event_log, ctx, tick=1)

        a = store.get("a")
        assert a is not None
        assert a["trusts"] == {"b": 50}

    def test_remove_relationship_effect(self) -> None:
        """remove_relationship effect works without history."""
        from worldseed.dsl.effects import execute

        store = StateStore()
        store.add(
            Entity(
                id="a",
                type="agent",
                _data={"trusts": {"b": 50}},
            )
        )
        store.add(Entity(id="b", type="agent", _data={}))
        event_log = EventLog()

        effect = EffectConfig(
            operator="remove_relationship",
            from_entity="a",
            type="trusts",
            to="b",
        )
        ctx = {"agent_id": "a", "action_params": {}}
        execute(effect, store, event_log, ctx, tick=1)

        a = store.get("a")
        assert a is not None
        assert a.get("trusts", {}) == {}


# ============================================================
# 3. Property changes still observable
# ============================================================


class TestPropertyChangesObservable:
    """After effects execute, changes must be visible through all read paths."""

    def _effects_config(self) -> SceneConfig:
        return SceneConfig(
            scene=SceneMetaConfig(id="observable_test", description="Observable changes"),
            entities=[
                EntityConfig(
                    id="room",
                    type="space",
                    properties={"description": "Room"},
                ),
                EntityConfig(
                    id="food",
                    type="resource",
                    properties={"quantity": 100, "location": "room"},
                ),
            ],
            agents=[
                AgentConfig(
                    id="obs_agent",
                    properties={"location": "room", "hp": 100, "energy": 50},
                    character={"personality": "observer"},
                ),
            ],
            actions={
                "heal": ActionConfig(
                    description="Heal self",
                    effects=[
                        EffectConfig(
                            operator="increment",
                            target="$agent.hp",
                            by=20,
                        ),
                    ],
                ),
                "rest": ActionConfig(
                    description="Rest",
                    effects=[
                        EffectConfig(
                            operator="set",
                            target="$agent.energy",
                            value=100,
                        ),
                    ],
                ),
                "wait": ActionConfig(description="Do nothing"),
            },
            auto_tick=[
                AutoTickConfig(
                    description="Food decay",
                    effects=[
                        EffectConfig(
                            operator="decrement",
                            target="food.quantity",
                            by=1,
                        ),
                    ],
                ),
            ],
        )

    def test_entity_properties_reflect_set(self) -> None:
        """After set, entity data shows the new value."""
        engine = _build_engine(self._effects_config())
        engine.submit("obs_agent", "rest")
        engine.step()
        entity = engine.state.get("obs_agent")
        assert entity is not None
        assert entity["energy"] == 100

    def test_entity_properties_reflect_increment(self) -> None:
        """After increment, entity data shows the new value."""
        engine = _build_engine(self._effects_config())
        engine.submit("obs_agent", "heal")
        engine.step()
        entity = engine.state.get("obs_agent")
        assert entity is not None
        assert entity["hp"] == 120

    def test_perceive_shows_updated_values(self) -> None:
        """perceive() returns updated property values after effects."""
        engine = _build_engine(self._effects_config())
        engine.submit("obs_agent", "rest")
        engine.step()

        perception = engine.perceive("obs_agent")
        assert perception.self_state["energy"] == 100

    def test_api_state_shows_updated_values(self) -> None:
        """The /api/runs/{run_id}/state endpoint reflects property changes."""
        config = self._effects_config()
        engine, client, run_id = _build_api_engine(config)
        try:
            engine.submit("obs_agent", "heal")
            engine.step()

            resp = client.get(f"/api/runs/{run_id}/state")
            assert resp.status_code == 200
            data = resp.json()
            entities = {e["id"]: e for e in data["entities"]}
            assert entities["obs_agent"]["hp"] == 120
        finally:
            _cleanup_run(run_id)

    def test_multiple_auto_tick_food_decay(self) -> None:
        """auto_tick food decay accumulates across multiple ticks."""
        engine = _build_engine(self._effects_config())
        for _ in range(10):
            engine.step()

        food = engine.state.get("food")
        assert food is not None
        # 100 - 10*1 = 90
        assert food["quantity"] == 90

    def test_auto_tick_and_action_in_same_tick(self) -> None:
        """Both action effects and auto_tick run in the same tick."""
        engine = _build_engine(self._effects_config())
        engine.submit("obs_agent", "heal")
        engine.step()

        obs = engine.state.get("obs_agent")
        food = engine.state.get("food")
        assert obs is not None
        assert food is not None
        # heal: 100 + 20 = 120
        assert obs["hp"] == 120
        # food decay: 100 - 1 = 99
        assert food["quantity"] == 99


# ============================================================
# 4. Validator still works
# ============================================================


class TestValidatorStillWorks:
    """Validator physics, smoke, and sanity tests work without ChangeHistory."""

    def _validator_config(self) -> SceneConfig:
        return SceneConfig(
            scene=SceneMetaConfig(id="validator_test", description="Validator regression"),
            entities=[
                EntityConfig(
                    id="room",
                    type="space",
                    properties={"description": "Room"},
                ),
                EntityConfig(
                    id="supplies",
                    type="resource",
                    properties={"quantity": 50, "location": "room"},
                ),
            ],
            agents=[
                AgentConfig(
                    id="val_agent",
                    properties={"location": "room", "hp": 100},
                    character={"personality": "validator"},
                ),
            ],
            actions={
                "wait": ActionConfig(description="Do nothing"),
            },
            auto_tick=[
                AutoTickConfig(
                    description="Supply decay",
                    effects=[
                        EffectConfig(
                            operator="decrement",
                            target="supplies.quantity",
                            by=1,
                        ),
                    ],
                ),
            ],
        )

    def test_run_physics_without_error(self) -> None:
        """validator._run_physics() works without ChangeHistory."""
        from worldseed.scene.checks.physics import run_physics

        config = self._validator_config()
        report = run_physics(config, ticks=20)
        assert report.ticks == 20
        # supplies.quantity should decrease from 50 to 30
        traj = report.trajectories.get("supplies.quantity")
        assert traj is not None
        assert len(traj) == 21  # initial + 20 ticks
        assert traj[0] == 50.0
        assert traj[-1] == 30.0

    def test_physics_n_ticks_no_crash(self) -> None:
        """Physics simulation runs 100 ticks without error."""
        from worldseed.scene.checks.physics import run_physics

        config = self._validator_config()
        report = run_physics(config, ticks=100)
        assert report.ticks == 100

    def test_full_validate_without_error(self) -> None:
        """Full validate() call completes without error."""
        config = self._validator_config()
        result = validate(config, physics_ticks=10)
        assert result.ok

    def test_smoke_test_works(self) -> None:
        """Smoke test runs without error."""
        from worldseed.scene.checks.smoke import run_smoke

        config = self._validator_config()
        report = run_smoke(config)
        assert "wait" in report.action_agents

    def test_validate_with_real_config(self) -> None:
        """Run validate() on the bunker config to exercise full path."""
        from worldseed.scene.config import load_config

        configs_dir = CONFIGS_DIR
        config = load_config(configs_dir / "bunker.yaml")
        result = validate(config, physics_ticks=20, run_sanity=True)
        # bunker config should pass validation (no errors)
        assert result.ok
        # Physics report should exist
        assert result.physics is not None
        assert result.physics.ticks == 20


# ============================================================
# 5. /api/runs/{run_id}/stream returns stream records only
# ============================================================


class TestApiEventsNoChanges:
    """/api/runs/{run_id}/stream must not contain a 'changes' field."""

    def _events_config(self) -> SceneConfig:
        return SceneConfig(
            scene=SceneMetaConfig(id="events_test", description="Events regression"),
            entities=[
                EntityConfig(
                    id="room",
                    type="space",
                    properties={"description": "Room"},
                ),
            ],
            agents=[
                AgentConfig(
                    id="evt_agent",
                    properties={"location": "room"},
                    character={"personality": "tester"},
                ),
            ],
            actions={
                "signal": ActionConfig(
                    description="Send a signal",
                    effects=[
                        EffectConfig(
                            operator="emit_event",
                            type="signal",
                            detail="$agent sends signal",
                            ttl=5,
                            scope="global",
                        ),
                    ],
                ),
                "wait": ActionConfig(description="Do nothing"),
            },
        )

    def test_no_changes_field_in_response(self) -> None:
        """Response from /api/runs/{run_id}/stream must not have 'changes' key."""
        engine, client, run_id = _build_api_engine(self._events_config())
        try:
            # Step once so recorder writes to stream.jsonl
            engine.step()
            resp = client.get(f"/api/runs/{run_id}/stream")
            assert resp.status_code == 200
            data = resp.json()
            assert "events" in data
            assert "changes" not in data
        finally:
            _cleanup_run(run_id)

    def test_events_from_emit_event_appear(self) -> None:
        """Actions triggering emit_event show up in /api/runs/{run_id}/stream."""
        engine, client, run_id = _build_api_engine(self._events_config())
        try:
            engine.submit("evt_agent", "signal")
            engine.step()

            resp = client.get(f"/api/runs/{run_id}/stream")
            data = resp.json()
            events = data["events"]
            action_events = [e for e in events if e.get("kind") == "action" and e.get("action_type") == "signal"]
            assert len(action_events) >= 1
            assert action_events[0]["agent_id"] == "evt_agent"
        finally:
            _cleanup_run(run_id)

    def test_event_ttl_works(self) -> None:
        """Events expire after their TTL."""
        config = SceneConfig(
            scene=SceneMetaConfig(id="ttl_test", description="TTL test"),
            entities=[
                EntityConfig(
                    id="room",
                    type="space",
                    properties={"description": "Room"},
                ),
            ],
            agents=[
                AgentConfig(
                    id="ttl_agent",
                    properties={"location": "room"},
                    character={"personality": "tester"},
                ),
            ],
            actions={
                "ping": ActionConfig(
                    description="Short-lived event",
                    effects=[
                        EffectConfig(
                            operator="emit_event",
                            type="ping",
                            detail="ping!",
                            ttl=1,
                            scope="global",
                        ),
                    ],
                ),
                "wait": ActionConfig(description="Do nothing"),
            },
        )
        engine = WorldEngine(config=config)
        engine.register_from_config()

        engine.submit("ttl_agent", "ping")
        # Mechanical action executes immediately at tick 0, event created at tick 0
        engine.step()  # tick 1 - cleanup: 0+1 >= 1 -> still alive

        events = engine.event_log.get_events(event_type="ping")
        assert len(events) == 1

        engine.step()  # tick 2 - cleanup: 0+1 >= 2 -> False, expired
        events = engine.event_log.get_events(event_type="ping")
        assert len(events) == 0

    def test_events_response_structure(self) -> None:
        """Stream response has run_id and events keys."""
        engine, client, run_id = _build_api_engine(self._events_config())
        try:
            engine.step()
            resp = client.get(f"/api/runs/{run_id}/stream")
            data = resp.json()
            assert "run_id" in data
            assert "events" in data
        finally:
            _cleanup_run(run_id)

    def test_event_to_dict_format(self) -> None:
        """Each stream record has kind and tick (no history fields)."""
        engine, client, run_id = _build_api_engine(self._events_config())
        try:
            engine.submit("evt_agent", "signal")
            engine.step()

            resp = client.get(f"/api/runs/{run_id}/stream")
            data = resp.json()
            for event in data["events"]:
                assert "kind" in event
                assert "tick" in event
                # Must NOT have ChangeHistory-related fields
                assert "changes" not in event
                assert "history" not in event
        finally:
            _cleanup_run(run_id)


# ============================================================
# 6. Notify mechanism
# ============================================================


class TestNotifyMechanism:
    """Connector notify (not wake) mechanism works correctly."""

    def test_mock_connector_notify_works(self) -> None:
        """MockConnector.notify() records notifications."""

        async def _test() -> None:
            connector = MockConnector()
            await connector.notify("agent_1", "test_reason")
            assert len(connector.notifications) == 1
            assert connector.notifications[0].agent_id == "agent_1"
            assert connector.notifications[0].reason == "test_reason"

        asyncio.run(_test())

    def test_connector_has_notify_not_wake(self) -> None:
        """ConnectorProvider protocol uses notify(), not wake()."""
        from worldseed.connector.base import ConnectorProvider

        assert hasattr(ConnectorProvider, "notify")
        # Verify wake is not part of the protocol
        # (runtime_checkable protocols expose methods as attributes)
        connector = MockConnector()
        assert hasattr(connector, "notify")
        assert not hasattr(connector, "wake")

    def test_tick_runner_checks_every_tick(self) -> None:
        """TickRunner runs connector checks every tick, not just ticks with results."""

        config = _mini_config()
        engine = _build_engine(config)
        connector = MockConnector()
        runner = TickRunner(engine, connector=connector, interval=0.01)

        async def _test() -> None:
            await runner.start()
            # Let a few ticks run
            await asyncio.sleep(0.1)
            await runner.stop()

        asyncio.run(_test())

        # Should have notifications even though no actions submitted
        # (regular interval notifications)
        assert len(connector.notifications) > 0

    def test_think_interval_tracked_per_agent(self) -> None:
        """Each agent has an independent think_interval."""
        config = SceneConfig(
            scene=SceneMetaConfig(id="think_test", description="Think interval test"),
            entities=[
                EntityConfig(
                    id="room",
                    type="space",
                    properties={"description": "Room"},
                ),
            ],
            agents=[
                AgentConfig(
                    id="fast_agent",
                    properties={"location": "room"},
                    character={"personality": "fast"},
                ),
                AgentConfig(
                    id="slow_agent",
                    properties={"location": "room"},
                    character={"personality": "slow"},
                ),
            ],
            actions={
                "wait": ActionConfig(description="Do nothing"),
            },
        )
        engine = _build_engine(config)

        engine.set_think_interval("fast_agent", 1)
        engine.set_think_interval("slow_agent", 10)

        assert engine.get_think_interval("fast_agent") == 1
        assert engine.get_think_interval("slow_agent") == 10

    def test_tick_runner_respects_think_interval(self) -> None:
        """TickRunner notifies agents based on their think_interval."""

        config = SceneConfig(
            scene=SceneMetaConfig(id="interval_test", description="Interval test"),
            entities=[
                EntityConfig(
                    id="room",
                    type="space",
                    properties={"description": "Room"},
                ),
            ],
            agents=[
                AgentConfig(
                    id="freq_agent",
                    properties={"location": "room"},
                    character={"personality": "frequent"},
                ),
            ],
            actions={
                "wait": ActionConfig(description="Do nothing"),
            },
        )
        engine = _build_engine(config)
        engine.set_think_interval("freq_agent", 2)

        connector = MockConnector()
        runner = TickRunner(engine, connector=connector, interval=0.01)

        async def _test() -> None:
            await runner.start()
            # Run enough ticks for at least 2 notification cycles
            await asyncio.sleep(0.15)
            await runner.stop()

        asyncio.run(_test())

        # Should have notifications for freq_agent
        freq_notifs = [n for n in connector.notifications if n.agent_id == "freq_agent"]
        assert len(freq_notifs) >= 1

    def test_agent_sets_own_think_interval_via_rest(self) -> None:
        """Agent can set its own think_interval through POST /act."""
        config = _mini_config()
        engine = _build_engine(config)
        app = create_app(engine, tick_interval=1.0)
        client = TestClient(app)

        # Default is 3
        assert engine.get_think_interval("alice") == 5

        # Agent sets its own interval via act
        resp = client.post(
            "/act",
            json={
                "agent_id": "alice",
                "action": "wait",
                "params": {},
                "think_interval": 2,
            },
        )
        assert resp.status_code == 200
        assert engine.get_think_interval("alice") == 2

    def test_think_interval_clamps_boundaries(self) -> None:
        """think_interval is clamped to [1, 100]."""
        config = _mini_config()
        engine = _build_engine(config)

        engine.set_think_interval("alice", 0)
        assert engine.get_think_interval("alice") == 1

        engine.set_think_interval("alice", -5)
        assert engine.get_think_interval("alice") == 1

        engine.set_think_interval("alice", 200)
        assert engine.get_think_interval("alice") == 100

        engine.set_think_interval("alice", 50)
        assert engine.get_think_interval("alice") == 50

    def test_two_agents_different_intervals_notify_rates(self) -> None:
        """Agent with interval=1 gets notified more often than interval=10."""

        config = SceneConfig(
            scene=SceneMetaConfig(id="rate_test", description="Rate test"),
            entities=[
                EntityConfig(
                    id="room",
                    type="space",
                    properties={"description": "Room"},
                ),
            ],
            agents=[
                AgentConfig(
                    id="fast",
                    properties={"location": "room"},
                    character={"personality": "fast"},
                ),
                AgentConfig(
                    id="slow",
                    properties={"location": "room"},
                    character={"personality": "slow"},
                ),
            ],
            actions={
                "wait": ActionConfig(description="Do nothing"),
            },
        )
        engine = _build_engine(config)
        engine.set_think_interval("fast", 1)
        engine.set_think_interval("slow", 10)

        connector = MockConnector()
        runner = TickRunner(
            engine,
            connector=connector,
            interval=0.01,
        )

        async def _test() -> None:
            await runner.start()
            await asyncio.sleep(0.25)
            await runner.stop()

        asyncio.run(_test())

        fast_notifs = [n for n in connector.notifications if n.agent_id == "fast"]
        slow_notifs = [n for n in connector.notifications if n.agent_id == "slow"]
        # fast (interval=1) should be notified much more than slow (interval=10)
        assert len(fast_notifs) > len(slow_notifs)
        assert len(fast_notifs) >= 5  # at least 5 in ~25 ticks

    def test_think_interval_change_midrun_takes_effect(self) -> None:
        """Changing think_interval mid-run affects subsequent notifications."""

        config = SceneConfig(
            narrator=False,
            scene=SceneMetaConfig(id="midrun_test", description="Midrun test"),
            entities=[
                EntityConfig(
                    id="room",
                    type="space",
                    properties={"description": "Room"},
                ),
            ],
            agents=[
                AgentConfig(
                    id="dynamic",
                    properties={"location": "room"},
                    character={"personality": "adaptive"},
                ),
            ],
            actions={
                "wait": ActionConfig(description="Do nothing"),
            },
        )
        engine = _build_engine(config)
        # Start with high interval (infrequent)
        engine.set_think_interval("dynamic", 50)

        connector = MockConnector()
        runner = TickRunner(
            engine,
            connector=connector,
            interval=0.01,
        )

        async def _test() -> None:
            await runner.start()
            # Run 15 ticks with interval=50 — should get 0 notifications
            await asyncio.sleep(0.15)
            count_before = len(connector.notifications)

            # Switch to interval=1 — should start getting frequent notifications
            engine.set_think_interval("dynamic", 1)
            await asyncio.sleep(0.15)
            await runner.stop()
            return count_before

        count_before = asyncio.run(_test())
        total = len(connector.notifications)
        count_after = total - count_before

        # Before: interval=50, ~15 ticks → 1 notification (tick-1 immediate)
        assert count_before <= 1
        # After: interval=1, ~15 ticks → many notifications
        assert count_after >= 5

    def test_wake_sent_every_interval_no_busy_gating(self) -> None:
        """Without BusyTracker, wakes are sent every think_interval unconditionally."""

        config = _mini_config()
        engine = _build_engine(config)
        engine.set_think_interval("alice", 1)

        connector = MockConnector()
        runner = TickRunner(
            engine,
            connector=connector,
            interval=0.01,
        )

        async def _test() -> None:
            await runner.start()
            await asyncio.sleep(0.1)
            await runner.stop()

        asyncio.run(_test())

        # Agent should receive multiple wakes — no busy gating blocks them
        alice_notifs = [n for n in connector.notifications if n.agent_id == "alice"]
        assert len(alice_notifs) >= 2

    def test_notify_endpoint_calls_connector(self) -> None:
        """POST /api/notify calls connector.notify()."""
        config = _mini_config()
        engine = _build_engine(config)
        connector = MockConnector()
        app = create_app(engine, tick_interval=1.0)
        # Wire connector via tick_runner
        if app.state.tick_runner:
            app.state.tick_runner.connector = connector
        client = TestClient(app)

        resp = client.post("/api/notify", json={"agent_id": "alice"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["notified"] is True
        alice_notifs = [n for n in connector.notifications if n.agent_id == "alice"]
        assert len(alice_notifs) == 1


# ============================================================
# 7. Integration: full cycle without ChangeHistory
# ============================================================


class TestFullCycleWithoutHistory:
    """End-to-end tests confirming the engine works without ChangeHistory."""

    def test_submit_step_perceive_cycle(self) -> None:
        """Full submit -> step -> perceive cycle works."""
        config = SceneConfig(
            scene=SceneMetaConfig(id="cycle_test", description="Cycle test"),
            entities=[
                EntityConfig(
                    id="room_a",
                    type="space",
                    properties={"description": "Room A", "connects_to": ["room_b"]},
                ),
                EntityConfig(
                    id="room_b",
                    type="space",
                    properties={"description": "Room B", "connects_to": ["room_a"]},
                ),
            ],
            agents=[
                AgentConfig(
                    id="traveler",
                    properties={"location": "room_a"},
                    character={"personality": "wanderer"},
                ),
            ],
            actions={
                "move": ActionConfig(
                    description="Move to connected space",
                    params=[
                        ParamConfig(name="to", type="entity_ref"),
                    ],
                    preconditions=[
                        PreconditionConfig(
                            operator="check",
                            left="$to",
                            op="in",
                            right=("relationships_of($agent.location, type=connects_to)"),
                        ),
                    ],
                    effects=[
                        EffectConfig(
                            operator="set",
                            target="$agent.location",
                            value="$to",
                        ),
                    ],
                    events=[
                        EventConfig(
                            type="move",
                            detail="$agent moved to $to",
                            ttl=1,
                            scope="global",
                        ),
                    ],
                ),
                "wait": ActionConfig(description="Do nothing"),
            },
            perception=PerceptionConfig(),  # empty = everything visible
        )
        engine = WorldEngine(config=config)
        engine.register_from_config()

        # Submit (mechanical action executes immediately) and step
        from worldseed.engine.rules_engine import ActionResult

        result = engine.submit("traveler", "move", {"to": "room_b"})
        assert isinstance(result, ActionResult) and result.success
        engine.step()  # still needed for auto_tick/consequences/perceiver

        # Verify property changed
        entity = engine.state.get("traveler")
        assert entity is not None
        assert entity["location"] == "room_b"

        # Perceive
        perception = engine.perceive("traveler")
        assert perception.self_state["location"] == "room_b"

    def test_multiple_agents_concurrent_actions(self) -> None:
        """Multiple agents acting in the same tick all work."""
        config = SceneConfig(
            scene=SceneMetaConfig(id="multi_test", description="Multi-agent"),
            entities=[
                EntityConfig(
                    id="room",
                    type="space",
                    properties={"description": "Room"},
                ),
            ],
            agents=[
                AgentConfig(
                    id="agent_a",
                    properties={"location": "room", "score": 0},
                    character={"personality": "a"},
                ),
                AgentConfig(
                    id="agent_b",
                    properties={"location": "room", "score": 0},
                    character={"personality": "b"},
                ),
            ],
            actions={
                "score": ActionConfig(
                    description="Increment score",
                    effects=[
                        EffectConfig(
                            operator="increment",
                            target="$agent.score",
                            by=1,
                        ),
                    ],
                ),
                "wait": ActionConfig(description="Do nothing"),
            },
        )
        engine = WorldEngine(config=config)
        engine.register_from_config()

        from worldseed.engine.rules_engine import ActionResult

        result_a = engine.submit("agent_a", "score")
        result_b = engine.submit("agent_b", "score")
        assert isinstance(result_a, ActionResult) and result_a.success
        assert isinstance(result_b, ActionResult) and result_b.success
        engine.step()  # still needed for auto_tick/consequences/perceiver

        a = engine.state.get("agent_a")
        b = engine.state.get("agent_b")
        assert a is not None and b is not None
        assert a["score"] == 1
        assert b["score"] == 1

    def test_consequence_scanner_works_without_history(self) -> None:
        """Consequence scanning fires correctly without ChangeHistory."""
        config = SceneConfig(
            scene=SceneMetaConfig(id="consequence_test", description="Consequence test"),
            entities=[
                EntityConfig(
                    id="room",
                    type="space",
                    properties={"description": "Room"},
                ),
                EntityConfig(
                    id="supply",
                    type="resource",
                    properties={"quantity": 5, "location": "room"},
                ),
            ],
            agents=[
                AgentConfig(
                    id="consumer",
                    properties={"location": "room"},
                    character={"personality": "consumer"},
                ),
            ],
            actions={
                "wait": ActionConfig(description="Do nothing"),
            },
            auto_tick=[
                AutoTickConfig(
                    description="Supply drain",
                    effects=[
                        EffectConfig(
                            operator="decrement",
                            target="supply.quantity",
                            by=2,
                        ),
                    ],
                ),
            ],
            consequences={
                "low_supply": {  # type: ignore[dict-item]
                    "trigger": [
                        {
                            "operator": "check",
                            "left": "supply.quantity",
                            "op": "<",
                            "right": 3,
                        }
                    ],
                    "effects": [
                        {
                            "operator": "emit_event",
                            "type": "warning",
                            "detail": "Supplies critically low",
                            "ttl": 5,
                            "scope": "global",
                        }
                    ],
                    "frequency": "on_change",
                },
            },
        )
        engine = WorldEngine(config=config)
        engine.register_from_config()

        # Tick 1: 5 - 2 = 3 (not < 3, no trigger)
        engine.step()
        events = engine.event_log.get_events(event_type="warning")
        assert len(events) == 0

        # Tick 2: 3 - 2 = 1 (< 3, trigger fires)
        engine.step()
        events = engine.event_log.get_events(event_type="warning")
        assert len(events) == 1
        assert events[0].detail == "Supplies critically low"

    def test_bunker_20_ticks_no_error(self) -> None:
        """Run the bunker config for 20 ticks with no crashes."""
        configs_dir = CONFIGS_DIR
        engine = WorldEngine(configs_dir / "bunker.yaml")
        engine.register_from_config()

        for _ in range(20):
            engine.step()

        # Food should have decayed
        food = engine.state.get("food_supply")
        assert food is not None
        assert food["quantity"] < 20
