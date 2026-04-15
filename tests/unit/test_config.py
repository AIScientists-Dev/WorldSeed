"""Tests for Scene Config loading and validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from worldseed.models.config_schema import (
    AutoTickConfig,
    ConsequenceConfig,
    EffectConfig,
    EventConfig,
    ParamConfig,
    PreconditionConfig,
    SceneConfig,
)
from worldseed.scene.config import load_config

from ..conftest import CONFIGS_DIR


class TestLoadConfig:
    def test_load_minimal(self) -> None:
        config = load_config(CONFIGS_DIR / "minimal.yaml")
        assert config.scene.id == "test_minimal"
        assert len(config.entities) == 2  # 2 rooms (agents in config.agents)
        assert len(config.agents) == 1  # 1 agent
        assert "move" in config.actions
        assert "wait" in config.actions

    def test_load_bunker(self) -> None:
        config = load_config(CONFIGS_DIR / "bunker.yaml")
        assert config.scene.id == "doomsday_bunker"
        assert len(config.agents) == 3
        spaces = [e for e in config.entities if e.type == "space"]
        assert len(spaces) == 4
        assert "move" in config.actions
        assert "take" in config.actions
        assert "say" in config.actions
        assert "observe" in config.actions
        assert "attempt" in config.actions
        assert len(config.auto_tick) == 5
        # take has push: true (resource-take should alert nearby agents)
        take_events = config.actions["take"].events
        assert any(e.push for e in take_events)

    def test_load_nonexistent_file(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path.yaml")

    def test_reject_missing_scene_id(self) -> None:
        raw = {
            "scene": {"description": "no id"},
            "entities": [],
            "actions": {},
        }
        with pytest.raises(ValidationError):
            SceneConfig.model_validate(raw)

    def test_reject_missing_entities(self) -> None:
        raw = {
            "scene": {"id": "test", "description": "no entities"},
            "actions": {},
        }
        with pytest.raises(ValidationError):
            SceneConfig.model_validate(raw)

    def test_accept_empty_optional_sections(self) -> None:
        raw = {
            "scene": {"id": "test", "description": "minimal"},
            "entities": [],
            "actions": {},
        }
        config = SceneConfig.model_validate(raw)
        assert config.consequences == {}
        assert config.auto_tick == []
        assert config.perception.visibility == []


class TestLiteralValidation:
    """Verify Literal types reject invalid values at parse time."""

    def test_reject_invalid_param_type(self) -> None:
        with pytest.raises(ValidationError):
            ParamConfig(name="x", type="boolean")  # type: ignore[arg-type]

    def test_reject_invalid_precondition_operator(self) -> None:
        with pytest.raises(ValidationError):
            PreconditionConfig(operator="compare")  # type: ignore[arg-type]

    def test_reject_invalid_precondition_op(self) -> None:
        with pytest.raises(ValidationError):
            PreconditionConfig(operator="check", left="a", op="like", right="b")  # type: ignore[arg-type]

    def test_reject_invalid_effect_operator(self) -> None:
        with pytest.raises(ValidationError):
            EffectConfig(operator="delete")  # type: ignore[arg-type]

    def test_reject_invalid_event_ttl_string(self) -> None:
        with pytest.raises(ValidationError):
            EventConfig(type="x", detail="y", ttl="infinite", scope="global")  # type: ignore[arg-type]


class TestPhase2Config:
    def test_perception_hidden_properties(self) -> None:
        config = load_config(CONFIGS_DIR / "bunker.yaml")
        assert config.perception.hidden_properties == [
            "private_stash",
            "goals",
        ]

    def test_perception_visibility_rules(self) -> None:
        config = load_config(CONFIGS_DIR / "bunker.yaml")
        assert len(config.perception.visibility) == 1
        rule = config.perception.visibility[0]
        assert rule.operator == "any"
        assert len(rule.conditions) == 2
        assert rule.conditions[0].operator == "check"
        assert rule.conditions[1].operator == "check"

    def test_auto_tick_with_condition(self) -> None:
        auto = AutoTickConfig(
            description="test",
            effects=[],
            condition=[PreconditionConfig(operator="check", left="x", op="==", right="y")],
        )
        assert auto.condition is not None
        assert len(auto.condition) == 1

    def test_auto_tick_without_condition(self) -> None:
        auto = AutoTickConfig(description="test", effects=[])
        assert auto.condition is None

    def test_consequence_only_on_change(self) -> None:
        with pytest.raises(ValidationError):
            ConsequenceConfig(
                trigger=[],
                effects=[],
                frequency="per_tick",  # type: ignore[arg-type]
            )
