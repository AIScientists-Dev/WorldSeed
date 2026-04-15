"""Level 5: Sanity checks (run config's own tests)."""

from __future__ import annotations

from worldseed.models.config_schema import SceneConfig
from worldseed.scene.validator import SanityResult


def run_sanity_checks(config: SceneConfig) -> list[SanityResult]:
    """Run each sanity_check defined in the config."""
    from worldseed.scene.sanity_runner import run_sanity_check

    results: list[SanityResult] = []
    for check in config.sanity_checks:
        result = run_sanity_check(config, check)
        results.append(result)
    return results
