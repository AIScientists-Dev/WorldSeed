"""Canonical data directory resolution.

WORLDSEED_HOME env var overrides the default ~/.worldseed.
All modules import from here instead of hardcoding paths.
"""

from __future__ import annotations

import os
from pathlib import Path


def worldseed_home() -> Path:
    """Root data directory. WORLDSEED_HOME env var or ~/.worldseed."""
    return Path(os.environ.get("WORLDSEED_HOME", "~/.worldseed")).expanduser()


def runs_dir() -> Path:
    """Directory containing all run data."""
    return worldseed_home() / "runs"


def run_dir(run_id: str) -> Path:
    """Directory for a specific run."""
    return runs_dir() / run_id


def discovery_file() -> Path:
    """Server discovery JSON (written on startup, read by OpenClaw)."""
    return worldseed_home() / "server.json"
