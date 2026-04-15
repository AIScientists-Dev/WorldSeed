"""Test: max_ticks and timeout_min server-side auto-stop.

scene.max_ticks: stop after N ticks.
scene.timeout_min: stop after N minutes wall-clock time.
Both None by default (no limit). Both enforced in TickRunner only.

ZERO HARDCODE: Tests create configs programmatically.
"""

from __future__ import annotations

import asyncio

from tests.helpers import CONFIGS_DIR, load_any_config, standard_config_paths
from worldseed.dm.providers.mock import MockDMProvider
from worldseed.models.config_schema import SceneMetaConfig
from worldseed.server.tick_runner import TickRunner
from worldseed.world import WorldEngine


def _make_engine(
    max_ticks: int | None = None,
    timeout_min: float | None = None,
) -> WorldEngine:
    """Create a WorldEngine from minimal config with custom limits."""
    config = load_any_config(CONFIGS_DIR / "minimal.yaml")
    config.scene.max_ticks = max_ticks
    config.scene.timeout_min = timeout_min
    return WorldEngine(config=config, dm_provider=MockDMProvider())


# -- max_ticks tests (carried over from test_max_ticks.py) --


class TestMaxTicksConfig:
    def test_default_is_100(self) -> None:
        meta = SceneMetaConfig(id="test", description="test")
        assert meta.max_ticks == 100

    def test_can_set_positive(self) -> None:
        meta = SceneMetaConfig(id="test", description="test", max_ticks=50)
        assert meta.max_ticks == 50

    def test_can_set_none(self) -> None:
        meta = SceneMetaConfig(id="test", description="test", max_ticks=None)
        assert meta.max_ticks is None


class TestTickRunnerMaxTicks:
    def test_stops_at_max_ticks(self) -> None:
        engine = _make_engine(max_ticks=5)
        engine.register_from_config()
        runner = TickRunner(engine, connector=None, interval=0.01)

        async def _go() -> None:
            await runner.start()
            assert runner._task is not None
            await asyncio.wait_for(runner._task, timeout=5.0)

        asyncio.run(_go())
        assert engine.tick == 5
        assert not runner.running

    def test_no_limit_when_none(self) -> None:
        engine = _make_engine(max_ticks=None)
        engine.register_from_config()
        runner = TickRunner(engine, connector=None, interval=0.01)

        async def _go() -> None:
            await runner.start()
            await asyncio.sleep(0.15)
            await runner.stop()

        asyncio.run(_go())
        assert engine.tick > 0
        assert not runner.running

    def test_max_ticks_1(self) -> None:
        engine = _make_engine(max_ticks=1)
        engine.register_from_config()
        runner = TickRunner(engine, connector=None, interval=0.01)

        async def _go() -> None:
            await runner.start()
            assert runner._task is not None
            await asyncio.wait_for(runner._task, timeout=5.0)

        asyncio.run(_go())
        assert engine.tick == 1


class TestMaxTicksWorldEngine:
    def test_engine_exposes_max_ticks(self) -> None:
        engine = _make_engine(max_ticks=42)
        assert engine.config.scene.max_ticks == 42

    def test_step_ignores_max_ticks(self) -> None:
        engine = _make_engine(max_ticks=3)
        engine.register_from_config()
        for _ in range(10):
            engine.step()
        assert engine.tick == 10


# -- timeout_min tests --


class TestTimeoutMinConfig:
    def test_default_is_none(self) -> None:
        meta = SceneMetaConfig(id="test", description="test")
        assert meta.timeout_min is None

    def test_can_set_positive(self) -> None:
        meta = SceneMetaConfig(id="test", description="test", timeout_min=30.0)
        assert meta.timeout_min == 30.0

    def test_existing_configs_have_none(self) -> None:
        for path in standard_config_paths():
            config = load_any_config(path)
            assert config.scene.timeout_min is None


class TestTickRunnerTimeout:
    def test_stops_after_timeout(self) -> None:
        """TickRunner stops after timeout_min expires."""
        # Use a very short timeout: 0.005 min = 0.3 seconds
        engine = _make_engine(timeout_min=0.005)
        engine.register_from_config()
        runner = TickRunner(engine, connector=None, interval=0.01)

        async def _go() -> None:
            await runner.start()
            assert runner._task is not None
            await asyncio.wait_for(runner._task, timeout=5.0)

        asyncio.run(_go())
        assert engine.tick > 0  # ran some ticks before timeout
        assert not runner.running

    def test_no_timeout_when_none(self) -> None:
        """With timeout_min=None, runner continues until stopped."""
        engine = _make_engine(timeout_min=None)
        engine.register_from_config()
        runner = TickRunner(engine, connector=None, interval=0.01)

        async def _go() -> None:
            await runner.start()
            await asyncio.sleep(0.15)
            await runner.stop()

        asyncio.run(_go())
        assert engine.tick > 0
        assert not runner.running

    def test_step_ignores_timeout(self) -> None:
        """Direct step() doesn't enforce timeout — only TickRunner does."""
        engine = _make_engine(timeout_min=0.001)
        engine.register_from_config()
        import time

        time.sleep(0.1)  # past timeout
        for _ in range(5):
            engine.step()
        assert engine.tick == 5


class TestCombinedLimits:
    """max_ticks and timeout_min can coexist — first reached wins."""

    def test_max_ticks_wins_when_faster(self) -> None:
        """max_ticks=3 with long timeout — ticks stop first."""
        engine = _make_engine(max_ticks=3, timeout_min=60.0)
        engine.register_from_config()
        runner = TickRunner(engine, connector=None, interval=0.01)

        async def _go() -> None:
            await runner.start()
            assert runner._task is not None
            await asyncio.wait_for(runner._task, timeout=5.0)

        asyncio.run(_go())
        assert engine.tick == 3

    def test_timeout_wins_when_faster(self) -> None:
        """Large max_ticks with very short timeout — time stops first."""
        engine = _make_engine(max_ticks=99999, timeout_min=0.003)
        engine.register_from_config()
        runner = TickRunner(engine, connector=None, interval=0.01)

        async def _go() -> None:
            await runner.start()
            assert runner._task is not None
            await asyncio.wait_for(runner._task, timeout=5.0)

        asyncio.run(_go())
        assert engine.tick < 99999  # stopped before max_ticks
        assert not runner.running
