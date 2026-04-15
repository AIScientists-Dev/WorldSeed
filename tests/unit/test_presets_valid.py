"""Validate that all preset YAML files are well-formed and usable."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.helpers import CONFIGS_DIR
from worldseed.models.config_schema import SceneConfig
from worldseed.scene.config import _resolve_presets

PRESETS_DIR = CONFIGS_DIR / "presets"
PRESET_FILES = sorted(PRESETS_DIR.glob("*.yaml"))
PRESET_NAMES = [p.stem for p in PRESET_FILES]


def _minimal_raw_with_preset(name: str) -> dict:
    return {
        "scene": {
            "id": f"test_{name}",
            "description": f"Test {name} preset",
            "use": [name],
        },
        "entities": [],
        "actions": {},
    }


class TestAllPresetsParseAndValidate:
    @pytest.mark.parametrize("preset_path", PRESET_FILES, ids=PRESET_NAMES)
    def test_preset_is_valid_yaml(self, preset_path: Path) -> None:
        with preset_path.open() as f:
            data = yaml.safe_load(f)
        assert isinstance(data, dict), f"{preset_path.name} is not a dict"

    @pytest.mark.parametrize("name", PRESET_NAMES)
    def test_preset_standalone_validates(self, name: str) -> None:
        raw = _minimal_raw_with_preset(name)
        configs_dir = PRESETS_DIR.parent
        resolved = _resolve_presets(raw, configs_dir / "minimal.yaml")
        config = SceneConfig.model_validate(resolved)
        assert config.scene.id == f"test_{name}"


class TestActionPresets:
    @pytest.mark.parametrize(
        "name,action",
        [
            ("talk", "talk"),
            ("directed_talk", "directed_talk"),
            ("attempt", "attempt"),
            ("move_simple", "move"),
            ("move_connected", "move"),
            ("observation", "observe"),
            ("attack", "attack"),
            ("rest", "rest"),
            ("steal", "steal"),
            ("search", "search"),
            ("use_item", "use_item"),
            ("consume", "consume"),
            ("trade", "give"),
        ],
    )
    def test_action_preset_adds_action(self, name: str, action: str) -> None:
        data = yaml.safe_load((PRESETS_DIR / f"{name}.yaml").read_text())
        assert action in data.get("actions", {}), f"{name} missing action {action}"


class TestDMPresets:
    @pytest.mark.parametrize(
        "name",
        ["attempt", "observation", "attack", "steal", "search", "use_item"],
    )
    def test_dm_preset_has_dm_config(self, name: str) -> None:
        data = yaml.safe_load((PRESETS_DIR / f"{name}.yaml").read_text())
        actions = data.get("actions", {})
        for action_config in actions.values():
            assert action_config.get("dm") is not None, f"{name} action missing dm"


class TestEntityPresets:
    def test_deck_has_52_cards(self) -> None:
        data = yaml.safe_load((PRESETS_DIR / "deck.yaml").read_text())
        deck = next(e for e in data["entities"] if e["id"] == "deck")
        assert len(deck["cards"]) == 52

    def test_timer_has_entity(self) -> None:
        data = yaml.safe_load((PRESETS_DIR / "timer.yaml").read_text())
        timer = next(e for e in data["entities"] if e["id"] == "timer")
        assert timer["remaining"] == 20

    def test_day_night_has_clock(self) -> None:
        data = yaml.safe_load((PRESETS_DIR / "day_night.yaml").read_text())
        clock = next(e for e in data["entities"] if e["id"] == "clock")
        assert clock["time_of_day"] == "day"


class TestSystemPresets:
    def test_hunger_system_has_auto_tick_and_consequence(self) -> None:
        data = yaml.safe_load((PRESETS_DIR / "hunger_system.yaml").read_text())
        assert len(data.get("auto_tick", [])) > 0
        assert "starvation" in data.get("consequences", {})

    def test_resource_decay_has_auto_tick(self) -> None:
        data = yaml.safe_load((PRESETS_DIR / "resource_decay.yaml").read_text())
        assert len(data.get("auto_tick", [])) > 0

    def test_elimination_hp(self) -> None:
        data = yaml.safe_load((PRESETS_DIR / "elimination_hp.yaml").read_text())
        assert "eliminated" in data.get("consequences", {})

    def test_elimination_chips(self) -> None:
        data = yaml.safe_load((PRESETS_DIR / "elimination_chips.yaml").read_text())
        assert "eliminated" in data.get("consequences", {})


class TestPerceptionPreset:
    def test_same_location_has_visibility_and_scope(self) -> None:
        data = yaml.safe_load((PRESETS_DIR / "same_location_perception.yaml").read_text())
        perc = data.get("perception", {})
        assert len(perc.get("visibility", [])) > 0
        assert "same_location" in perc.get("event_scopes", {})


class TestAllPresetsComposed:
    def test_all_presets_together(self) -> None:
        """Loading all presets at once must not conflict."""
        # move_simple and move_connected both define 'move' — last wins
        raw = {
            "scene": {
                "id": "all_presets",
                "description": "Test all presets together",
                "use": PRESET_NAMES,
            },
            "entities": [],
            "actions": {},
        }
        configs_dir = PRESETS_DIR.parent
        resolved = _resolve_presets(raw, configs_dir / "minimal.yaml")
        config = SceneConfig.model_validate(resolved)
        assert "talk" in config.actions
        assert "attempt" in config.actions
        assert "move" in config.actions
        assert "give" in config.actions
        assert "observe" in config.actions
        assert "attack" in config.actions
        assert "rest" in config.actions
