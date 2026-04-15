"""Parametrized tests for all scene configs.

Every YAML config in configs/ is automatically tested:
- Schema + logic validation passes
- Engine loads and runs 10 ticks without crash
- Config's own sanity_checks pass (if defined)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers import CONFIGS_DIR
from worldseed.scene.config import load_config
from worldseed.scene.validator import validate
from worldseed.world import WorldEngine

CONFIGS = sorted(CONFIGS_DIR.glob("*.yaml"))


@pytest.mark.parametrize("path", CONFIGS, ids=lambda p: p.stem)
def test_schema_valid(path: Path) -> None:
    """Every config passes schema + logic validation."""
    config = load_config(path)
    result = validate(config, physics_ticks=10)
    assert result.ok, f"{path.stem}: {result.summary()}"


@pytest.mark.parametrize("path", CONFIGS, ids=lambda p: p.stem)
def test_runs_10_ticks(path: Path) -> None:
    """Every config survives 10 ticks without crash."""
    engine = WorldEngine(path)
    engine.register_from_config()
    for _ in range(10):
        engine.step()


@pytest.mark.parametrize("path", CONFIGS, ids=lambda p: p.stem)
def test_sanity_checks(path: Path) -> None:
    """Run config's own sanity checks if defined."""
    config = load_config(path)
    if not config.sanity_checks:
        pytest.skip("no sanity checks defined")

    from worldseed.scene.sanity_runner import run_sanity_check

    for check in config.sanity_checks:
        result = run_sanity_check(config, check)
        assert result.passed, f"{path.stem}/{check.name}: {result.failure_detail}"
