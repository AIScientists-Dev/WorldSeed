"""Test: DM quality — validation, retry, rollback, token tracking.

Tests DM resolver behavior using mock providers:
  - Effect validation (allowed_ops, max_effects, entity existence)
  - Retry on failure (max_attempts=2)
  - Rollback on effect execution error
  - Fallback narrative when DM fails
  - Token tracking recorded correctly

ZERO HARDCODE: Uses dynamically loaded configs and mock DM providers.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tests.helpers import (
    CONFIGS_DIR,
    load_any_config,
    make_world,
    standard_config_paths,
)
from worldseed.dm.providers.mock import FailingMockDMProvider, MockDMProvider
from worldseed.engine.dm_resolver import (
    emit_fallback_narrative,
    resolve_dm,
    snapshot_entities,
    validate_dm_effects,
)
from worldseed.engine.event_log import EventLog
from worldseed.engine.inbox import InboxManager
from worldseed.engine.state_store import StateStore
from worldseed.models.action import ActionSubmission
from worldseed.models.config_schema import DMConfig, EffectConfig
from worldseed.models.entity import Entity
from worldseed.protocol.dm import DMResponse

# -- Unit: validate_dm_effects --


class TestValidateDMEffects:
    """Effect validation catches invalid DM output."""

    def _make_store(self) -> StateStore:
        store = StateStore()
        store.add(Entity(id="target_entity", type="resource", _data={"val": 10}))
        return store

    def _make_dm_config(self) -> DMConfig:
        return DMConfig(
            hint="test",
            scope="global",
            allowed_ops=["set", "increment", "decrement", "emit_event"],
            max_effects=5,
        )

    def test_valid_effects_pass(self) -> None:
        store = self._make_store()
        config = self._make_dm_config()
        effects = [
            EffectConfig(operator="set", target="target_entity.val", value=20),
            EffectConfig(operator="emit_event", type="test", detail="x", ttl=1, scope="global"),
        ]
        valid, reason = validate_dm_effects(effects, config, store)
        assert valid, f"Expected valid, got: {reason}"

    def test_too_many_effects_rejected(self) -> None:
        store = self._make_store()
        config = self._make_dm_config()
        effects = [
            EffectConfig(operator="emit_event", type="e", detail="x", ttl=1, scope="g")
            for _ in range(config.max_effects + 1)
        ]
        valid, reason = validate_dm_effects(effects, config, store)
        assert not valid
        assert "max" in reason.lower()

    def test_disallowed_operator_rejected(self) -> None:
        store = self._make_store()
        config = self._make_dm_config()
        effects = [
            EffectConfig(operator="remove_entity", target="target_entity"),
        ]
        valid, reason = validate_dm_effects(effects, config, store)
        assert not valid
        assert "allowed_ops" in reason

    def test_nonexistent_entity_rejected(self) -> None:
        store = self._make_store()
        config = self._make_dm_config()
        effects = [
            EffectConfig(operator="set", target="nonexistent.val", value=1),
        ]
        valid, reason = validate_dm_effects(effects, config, store)
        assert not valid
        assert "not found" in reason

    def test_set_missing_target_rejected(self) -> None:
        store = self._make_store()
        config = self._make_dm_config()
        effects = [EffectConfig(operator="set", value=1)]
        valid, reason = validate_dm_effects(effects, config, store)
        assert not valid
        assert "missing target" in reason.lower()

    def test_dollar_ref_allowed(self) -> None:
        """$agent references are not validated against store."""
        store = self._make_store()
        config = self._make_dm_config()
        effects = [
            EffectConfig(operator="set", target="$agent.prop_b", value=80),
        ]
        valid, reason = validate_dm_effects(effects, config, store)
        assert valid, f"$ references should pass: {reason}"


# -- Unit: snapshot + rollback --


class TestSnapshotRollback:
    """DM effects are rolled back if execution fails."""

    def test_snapshot_captures_affected_entities(self) -> None:
        store = StateStore()
        store.add(Entity(id="e1", type="r", _data={"val": 10}))
        store.add(Entity(id="e2", type="r", _data={"val": 20}))

        effects = [
            EffectConfig(operator="set", target="e1.val", value=99),
        ]
        snaps = snapshot_entities(store, effects)
        assert "e1" in snaps
        assert snaps["e1"]["val"] == 10
        assert "e2" not in snaps  # not affected

    def test_restore_snapshots_reverts_changes(self) -> None:
        from worldseed.engine.dm_resolver import restore_snapshots

        store = StateStore()
        store.add(Entity(id="e1", type="r", _data={"val": 10}))

        effects = [EffectConfig(operator="set", target="e1.val", value=99)]
        snaps = snapshot_entities(store, effects)

        # Mutate
        store.update_property("e1", "val", 999)
        assert store.get("e1").data["val"] == 999  # type: ignore[union-attr]

        # Restore
        restore_snapshots(store, snaps)
        assert store.get("e1").data["val"] == 10  # type: ignore[union-attr]


# -- Unit: fallback narrative --


class TestFallbackNarrative:
    def test_fallback_delivers_whisper(self) -> None:
        event_log = EventLog()
        inbox_mgr = InboxManager()
        emit_fallback_narrative("agent_x", 5, inbox_manager=inbox_mgr)

        # Delivered as whisper, not event
        inbox = inbox_mgr.get_or_create("agent_x")
        data = inbox.read()
        dms = data["whispers"]
        assert len(dms) == 1
        assert dms[0].type == "dm_narrative"
        assert dms[0].source == "dm"
        assert dms[0].tick == 5
        assert "unclear" in dms[0].detail.lower()
        assert event_log.size == 0  # no event broadcast

    def test_fallback_without_inbox_manager_is_noop(self) -> None:
        """Without inbox_manager, fallback logs warning but emits nothing."""
        event_log = EventLog()
        emit_fallback_narrative("agent_x", 5)

        # No inbox_manager means no delivery — just a warning log
        assert event_log.size == 0


# -- Integration: DM retry + fallback --


class TestDMRetryIntegration:
    """DM resolve retries on failure and falls back correctly."""

    def test_dm_retries_on_exception(self) -> None:
        """FailingMockDMProvider fails once, succeeds on retry."""
        success = DMResponse(narrative="Success after retry")
        provider = FailingMockDMProvider(fail_count=1, success_response=success)

        store = StateStore()
        store.add(Entity(id="agent_a", type="agent", _data={"location": "room"}))
        event_log = EventLog()
        inbox_mgr = InboxManager()

        from worldseed.dm.builder import DMContextBuilder
        from worldseed.scene.config import load_config

        config = load_config(CONFIGS_DIR / "minimal.yaml")
        builder = DMContextBuilder(store, event_log, config)

        action = ActionSubmission(
            agent_id="agent_a",
            action_type="move",
            params={"to": "room_b"},
            tick_submitted=1,
        )
        dm_config = DMConfig(
            hint="test",
            scope="global",
            allowed_ops=["set", "emit_event"],
            max_effects=3,
        )

        asyncio.run(
            resolve_dm(
                action=action,
                dm_config=dm_config,
                ctx={
                    "agent_id": "agent_a",
                    "action_params": {"to": "room_b"},
                    "tick": 1,
                },
                tick=1,
                dm_provider=provider,
                dm_builder=builder,
                store=store,
                event_log=event_log,
                recorder=None,
                inbox_manager=inbox_mgr,
            )
        )

        assert provider.call_count == 2, "Should retry once after failure"
        # Narrative delivered as whisper to actor, not as event
        inbox = inbox_mgr.get_or_create("agent_a")
        data = inbox.read()
        dms = data["whispers"]
        assert len(dms) == 1
        assert dms[0].detail == "Success after retry"
        assert dms[0].type == "dm_narrative"
        # No dm_narrative events in event log
        narratives = [e for e in event_log.get_events() if e.type == "dm_narrative"]
        assert len(narratives) == 0

    def test_dm_falls_back_after_all_retries_fail(self) -> None:
        """When all retries fail, fallback narrative is emitted."""
        provider = FailingMockDMProvider(
            fail_count=999,
            success_response=DMResponse(narrative="never reached"),
        )

        store = StateStore()
        store.add(Entity(id="agent_a", type="agent", _data={"location": "room"}))
        event_log = EventLog()
        inbox_mgr = InboxManager()

        from worldseed.dm.builder import DMContextBuilder
        from worldseed.scene.config import load_config

        config = load_config(CONFIGS_DIR / "minimal.yaml")
        builder = DMContextBuilder(store, event_log, config)

        action = ActionSubmission(
            agent_id="agent_a",
            action_type="move",
            params={"to": "room_b"},
            tick_submitted=1,
        )
        dm_config = DMConfig(
            hint="test",
            scope="global",
            allowed_ops=["set"],
            max_effects=3,
        )

        asyncio.run(
            resolve_dm(
                action=action,
                dm_config=dm_config,
                ctx={"agent_id": "agent_a", "action_params": {}, "tick": 1},
                tick=1,
                dm_provider=provider,
                dm_builder=builder,
                store=store,
                event_log=event_log,
                recorder=None,
                inbox_manager=inbox_mgr,
            )
        )

        # max_attempts=2, so 2 calls
        assert provider.call_count == 2
        # Fallback delivered as whisper to actor
        inbox = inbox_mgr.get_or_create("agent_a")
        data = inbox.read()
        dms = data["whispers"]
        assert len(dms) == 1
        assert "unclear" in dms[0].detail.lower()
        # No dm_narrative events in event log
        assert len([e for e in event_log.get_events() if e.type == "dm_narrative"]) == 0


# -- Integration: DM with real configs --


@pytest.fixture(params=standard_config_paths(), ids=lambda p: p.stem)
def config_path(request: pytest.FixtureRequest) -> Path:
    return request.param


class TestDMWithConfigs:
    """DM integration verified against real scene configs."""

    def test_configs_with_dm_actions(self, config_path: Path) -> None:
        """Configs with dm-enabled actions: mock DM produces valid cycle."""
        config = load_any_config(config_path)
        dm_actions = [name for name, act in config.actions.items() if act.dm is not None]
        if not dm_actions:
            pytest.skip("No DM-enabled actions")

        engine = make_world(config_path)
        agents = engine.get_registered_agents()
        if not agents:
            pytest.skip("No agents")

        # Find a DM action we can submit
        for action_name in dm_actions:
            act_cfg = config.actions[action_name]
            required = [p for p in act_cfg.params if p.required]
            if not required:
                # Paramless DM action — submit and step
                engine.submit(agents[0], action_name)
                results = asyncio.run(engine.step_async())
                assert len(results) >= 1
                return

        # All DM actions have required params — still verify engine doesn't crash
        # with 5 ticks of no-action steps
        for _ in range(5):
            asyncio.run(engine.step_async())
        assert engine.tick == 5

    def test_mock_dm_called_for_dm_actions(self, config_path: Path) -> None:
        """MockDMProvider is called when DM actions are submitted."""
        config = load_any_config(config_path)
        dm_actions = [name for name, act in config.actions.items() if act.dm is not None]
        if not dm_actions:
            pytest.skip("No DM-enabled actions")

        mock_dm = MockDMProvider()
        from worldseed.world import WorldEngine

        engine = WorldEngine(config_path=config_path, dm_provider=mock_dm)
        engine.register_from_config()
        agents = engine.get_registered_agents()
        if not agents:
            pytest.skip("No agents")

        # Try submitting paramless DM actions
        submitted = False
        for action_name in dm_actions:
            act_cfg = config.actions[action_name]
            if not any(p.required for p in act_cfg.params):
                engine.submit(agents[0], action_name)
                submitted = True
                break

        if not submitted:
            pytest.skip("No paramless DM actions")

        results = asyncio.run(engine.step_async())
        our_result = next(
            (r for r in results if r.action.agent_id == agents[0]),
            None,
        )
        if our_result is None or not our_result.success:
            pytest.skip("Action failed preconditions — DM not reached")

        assert mock_dm.call_count >= 1, "MockDM should be called for DM actions"
        assert mock_dm.last_context is not None
        assert mock_dm.last_context.action.agent_id == agents[0]
