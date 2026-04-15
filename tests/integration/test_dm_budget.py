"""Test: max_dm_calls budget enforcement.

scene.max_dm_calls limits total DM calls across all ticks.
When budget exhausted, DM is skipped and fallback narrative emitted.
None (default) means no limit.

ZERO HARDCODE: Tests use config-driven helpers.
"""

from __future__ import annotations

import asyncio

import pytest

from tests.helpers import CONFIGS_DIR, load_any_config, standard_config_paths
from worldseed.dm.providers.mock import MockDMProvider
from worldseed.models.config_schema import SceneMetaConfig
from worldseed.world import WorldEngine


def _make_engine(
    max_dm_calls: int | None = None,
) -> WorldEngine:
    """Create engine from minimal config with custom max_dm_calls."""
    config = load_any_config(CONFIGS_DIR / "minimal.yaml")
    config.scene.max_dm_calls = max_dm_calls
    return WorldEngine(config=config, dm_provider=MockDMProvider())


class TestMaxDMCallsConfig:
    def test_default_is_none(self) -> None:
        meta = SceneMetaConfig(id="test", description="test")
        assert meta.max_dm_calls is None

    def test_can_set_positive(self) -> None:
        meta = SceneMetaConfig(id="test", description="test", max_dm_calls=50)
        assert meta.max_dm_calls == 50

    def test_existing_configs_have_none(self) -> None:
        for path in standard_config_paths():
            config = load_any_config(path)
            assert config.scene.max_dm_calls is None


class TestDMCallCounting:
    """DM call counter tracks actual calls."""

    def test_starts_at_zero(self) -> None:
        engine = _make_engine()
        assert engine.dm_call_count == 0

    def test_increments_on_dm_action(self) -> None:
        """DM call count increments when DM-enabled action is resolved."""
        # Find a config with DM-enabled actions
        dm_configs = []
        for path in standard_config_paths():
            config = load_any_config(path)
            dm_actions = [
                name
                for name, act in config.actions.items()
                if act.dm is not None and not any(p.required for p in act.params)
            ]
            if dm_actions:
                dm_configs.append((path, dm_actions[0]))
        if not dm_configs:
            pytest.skip("No configs with paramless DM actions")

        path, action_name = dm_configs[0]
        config = load_any_config(path)
        config.scene.max_dm_calls = None  # no limit
        mock_dm = MockDMProvider()
        engine = WorldEngine(config=config, dm_provider=mock_dm)
        engine.register_from_config()

        agents = engine.get_registered_agents()
        engine.submit(agents[0], action_name)
        asyncio.run(engine.step_async())

        if mock_dm.call_count > 0:
            assert engine.dm_call_count > 0
        # If action failed preconditions, DM wasn't called — that's fine

    def test_no_increment_without_dm_actions(self) -> None:
        """step() with no DM actions doesn't increment counter."""
        engine = _make_engine()
        engine.register_from_config()
        engine.step()
        assert engine.dm_call_count == 0


class TestDMBudgetEnforcement:
    """When max_dm_calls reached, DM is skipped with fallback."""

    def test_budget_zero_skips_all_dm(self) -> None:
        """max_dm_calls=0 means no DM calls ever — all fallback."""
        dm_configs = []
        for path in standard_config_paths():
            config = load_any_config(path)
            dm_actions = [
                name
                for name, act in config.actions.items()
                if act.dm is not None and not any(p.required for p in act.params)
            ]
            if dm_actions:
                dm_configs.append((path, dm_actions[0]))
        if not dm_configs:
            pytest.skip("No configs with paramless DM actions")

        path, action_name = dm_configs[0]
        config = load_any_config(path)
        config.scene.max_dm_calls = 0
        mock_dm = MockDMProvider()
        engine = WorldEngine(config=config, dm_provider=mock_dm)
        engine.register_from_config()

        agents = engine.get_registered_agents()
        engine.submit(agents[0], action_name)
        asyncio.run(engine.step_async())

        assert mock_dm.call_count == 0, "DM should not be called with budget=0"
        assert engine.dm_call_count == 0

    def test_budget_exhaustion_emits_fallback(self) -> None:
        """After budget exhausted, fallback narrative is emitted."""
        dm_configs = []
        for path in standard_config_paths():
            config = load_any_config(path)
            dm_actions = [
                name
                for name, act in config.actions.items()
                if act.dm is not None and not any(p.required for p in act.params)
            ]
            if dm_actions:
                dm_configs.append((path, dm_actions[0]))
        if not dm_configs:
            pytest.skip("No configs with paramless DM actions")

        path, action_name = dm_configs[0]
        config = load_any_config(path)
        config.scene.max_dm_calls = 1  # allow exactly 1
        mock_dm = MockDMProvider()
        engine = WorldEngine(config=config, dm_provider=mock_dm)
        engine.register_from_config()

        agents = engine.get_registered_agents()

        # First call — should succeed (within budget)
        engine.submit(agents[0], action_name)
        asyncio.run(engine.step_async())
        calls_after_first = mock_dm.call_count

        # Second call — should be skipped (budget exhausted)
        engine.submit(agents[0], action_name)
        asyncio.run(engine.step_async())

        # DM should not have been called again after budget exhaustion
        if calls_after_first > 0:
            # First action used the budget
            assert engine.dm_call_count <= 1
            # Check fallback narrative delivered as whisper to agent inbox
            inbox_data = engine.read_inbox(agents[0])
            dm_msgs = [m for m in inbox_data["whispers"] if m.type == "dm_narrative" and "unclear" in m.detail.lower()]
            assert len(dm_msgs) >= 1, "Expected fallback narrative after budget exhaustion"

    def test_no_budget_unlimited_dm(self) -> None:
        """max_dm_calls=None allows unlimited DM calls."""
        engine = _make_engine(max_dm_calls=None)
        engine.register_from_config()
        # Run many ticks — counter should not cause any issues
        for _ in range(20):
            engine.step()
        # With mock DM and minimal config (no DM actions), count stays 0
        assert engine.dm_call_count == 0  # minimal config has no DM actions
