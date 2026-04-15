"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers import (
    ConfigIntrospector,
    all_config_paths,
    make_world,
    standard_config_paths,
)
from worldseed.engine.event_log import EventLog
from worldseed.engine.inbox import InboxManager
from worldseed.engine.state_store import StateStore
from worldseed.scene.config import load_config
from worldseed.world import WorldEngine

CONFIGS_DIR = Path(__file__).parent.parent / "configs"


# -- Generic fixtures (zero hardcode) --


@pytest.fixture(params=standard_config_paths(), ids=lambda p: p.stem)
def any_config_path(request: pytest.FixtureRequest) -> Path:
    """Parametrized fixture: yields each standard config path."""
    return request.param


@pytest.fixture(params=all_config_paths(), ids=lambda p: p.stem)
def every_config_path(request: pytest.FixtureRequest) -> Path:
    """Parametrized fixture: yields every config path (including chaos)."""
    return request.param


@pytest.fixture
def any_world(any_config_path: Path) -> WorldEngine:
    """WorldEngine with mock DM for any standard config."""
    return make_world(any_config_path)


@pytest.fixture
def introspector(any_config_path: Path) -> ConfigIntrospector:
    """ConfigIntrospector for the current config."""
    return ConfigIntrospector(load_config(any_config_path))


@pytest.fixture
def state_store() -> StateStore:
    return StateStore()


@pytest.fixture
def event_log() -> EventLog:
    return EventLog()


@pytest.fixture
def inbox_manager() -> InboxManager:
    return InboxManager()


@pytest.fixture
def minimal_config():  # type: ignore[no-untyped-def]
    return load_config(CONFIGS_DIR / "minimal.yaml")


@pytest.fixture
def bunker_config():  # type: ignore[no-untyped-def]
    return load_config(CONFIGS_DIR / "bunker.yaml")


@pytest.fixture
def populated_bunker_store():  # type: ignore[no-untyped-def]
    w = WorldEngine(CONFIGS_DIR / "bunker.yaml")
    w.register_from_config()
    return w.state


@pytest.fixture
def bunker_world() -> WorldEngine:
    w = WorldEngine(CONFIGS_DIR / "bunker.yaml")
    w.register_from_config()
    return w
