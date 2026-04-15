"""Tests for the preset loading and merging system."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.helpers import CONFIGS_DIR
from worldseed.models.config_schema import SceneConfig
from worldseed.scene.config import _deep_merge, _resolve_presets, load_config


def _minimal_raw(**overrides: object) -> dict:
    """Minimal valid raw config dict."""
    base = {
        "scene": {"id": "test", "description": "test"},
        "entities": [],
        "actions": {},
    }
    for k, v in overrides.items():
        if k.startswith("scene."):
            base["scene"][k.split(".", 1)[1]] = v
        else:
            base[k] = v
    return base


class TestLoadWithoutPresets:
    def test_load_without_use(self) -> None:
        config = load_config(CONFIGS_DIR / "minimal.yaml")
        assert config.scene.id == "test_minimal"

    def test_use_empty_list(self, tmp_path: Path) -> None:
        raw = _minimal_raw()
        raw["scene"]["use"] = []
        p = tmp_path / "test.yaml"
        p.write_text(yaml.dump(raw))
        config = load_config(p)
        assert config.scene.id == "test"


class TestSinglePreset:
    def test_use_talk(self) -> None:
        raw = _minimal_raw()
        raw["scene"]["use"] = ["talk"]
        resolved = _resolve_presets(raw, CONFIGS_DIR / "minimal.yaml")
        config = SceneConfig.model_validate(resolved)
        assert "talk" in config.actions

    def test_use_attempt(self) -> None:
        raw = _minimal_raw()
        raw["scene"]["use"] = ["attempt"]
        resolved = _resolve_presets(raw, CONFIGS_DIR / "minimal.yaml")
        config = SceneConfig.model_validate(resolved)
        assert "attempt" in config.actions
        assert config.actions["attempt"].dm is not None

    def test_use_deck(self) -> None:
        raw = _minimal_raw()
        raw["scene"]["use"] = ["deck"]
        resolved = _resolve_presets(raw, CONFIGS_DIR / "minimal.yaml")
        config = SceneConfig.model_validate(resolved)
        deck = next(e for e in config.entities if e.id == "deck")
        assert len(deck.properties["cards"]) == 52


class TestMultiplePresets:
    def test_talk_and_move_simple(self) -> None:
        raw = _minimal_raw()
        raw["scene"]["use"] = ["talk", "directed_talk", "move_simple"]
        resolved = _resolve_presets(raw, CONFIGS_DIR / "minimal.yaml")
        config = SceneConfig.model_validate(resolved)
        assert "talk" in config.actions
        assert "directed_talk" in config.actions
        assert "move" in config.actions

    def test_perception_from_preset(self) -> None:
        raw = _minimal_raw()
        raw["scene"]["use"] = ["same_location_perception"]
        resolved = _resolve_presets(raw, CONFIGS_DIR / "minimal.yaml")
        config = SceneConfig.model_validate(resolved)
        assert len(config.perception.visibility) > 0
        assert "same_location" in config.perception.event_scopes


class TestConfigOverridesPreset:
    def test_override_attempt_hint(self) -> None:
        raw = _minimal_raw()
        raw["scene"]["use"] = ["attempt"]
        raw["actions"] = {
            "attempt": {
                "description": "Custom attempt",
                "dm": {"hint": "Poker only"},
            }
        }
        resolved = _resolve_presets(raw, CONFIGS_DIR / "minimal.yaml")
        config = SceneConfig.model_validate(resolved)
        assert config.actions["attempt"].description == "Custom attempt"
        assert config.actions["attempt"].dm.hint == "Poker only"

    def test_config_visibility_wins(self) -> None:
        raw = _minimal_raw()
        raw["scene"]["use"] = ["same_location_perception"]
        raw["perception"] = {"visibility": []}
        resolved = _resolve_presets(raw, CONFIGS_DIR / "minimal.yaml")
        config = SceneConfig.model_validate(resolved)
        assert config.perception.visibility == []
        # Event scopes from preset should still merge
        assert "same_location" in config.perception.event_scopes


class TestPresetErrors:
    def test_not_found(self) -> None:
        raw = _minimal_raw()
        raw["scene"]["use"] = ["nonexistent_preset_xyz"]
        with pytest.raises(FileNotFoundError, match="nonexistent_preset_xyz"):
            _resolve_presets(raw, CONFIGS_DIR / "minimal.yaml")

    def test_circular_reference(self, tmp_path: Path) -> None:
        # Config at tmp_path/configs/test.yaml, presets at tmp_path/configs/presets/
        configs = tmp_path / "configs"
        configs.mkdir()
        presets = configs / "presets"
        presets.mkdir()
        (presets / "a.yaml").write_text(yaml.dump({"scene": {"use": ["b"]}, "actions": {}}))
        (presets / "b.yaml").write_text(yaml.dump({"scene": {"use": ["a"]}, "actions": {}}))
        raw = _minimal_raw()
        raw["scene"]["use"] = ["a"]
        with pytest.raises(ValueError, match="Circular"):
            _resolve_presets(raw, configs / "test.yaml")


class TestMergeStrategies:
    def test_actions_merge(self) -> None:
        base: dict = {"actions": {"a": 1}}
        override: dict = {"actions": {"b": 2}}
        _deep_merge(base, override)
        assert base["actions"] == {"a": 1, "b": 2}

    def test_actions_override_same_key(self) -> None:
        base: dict = {"actions": {"a": 1}}
        override: dict = {"actions": {"a": 2}}
        _deep_merge(base, override)
        assert base["actions"]["a"] == 2

    def test_entities_append(self) -> None:
        base: dict = {"entities": [{"id": "a", "type": "x"}]}
        override: dict = {"entities": [{"id": "b", "type": "y"}]}
        _deep_merge(base, override)
        assert len(base["entities"]) == 2

    def test_entities_dedupe_by_id(self) -> None:
        base: dict = {"entities": [{"id": "a", "type": "x", "v": 1}]}
        override: dict = {"entities": [{"id": "a", "type": "x", "v": 2}]}
        _deep_merge(base, override)
        assert len(base["entities"]) == 1
        assert base["entities"][0]["v"] == 2

    def test_auto_tick_append(self) -> None:
        base: dict = {"auto_tick": [{"description": "a"}]}
        override: dict = {"auto_tick": [{"description": "b"}]}
        _deep_merge(base, override)
        assert len(base["auto_tick"]) == 2

    def test_hidden_properties_union(self) -> None:
        base: dict = {"hidden_properties": ["a", "b"]}
        override: dict = {"hidden_properties": ["b", "c"]}
        _deep_merge(base, override)
        assert sorted(base["hidden_properties"]) == ["a", "b", "c"]

    def test_preset_order_matters(self) -> None:
        base: dict = {}
        _deep_merge(base, {"actions": {"x": {"description": "from_a"}}})
        _deep_merge(base, {"actions": {"x": {"description": "from_b"}}})
        assert base["actions"]["x"]["description"] == "from_b"
