"""Tests for WorldEngine.validate_params() — action param validation."""

from __future__ import annotations

from worldseed.models.config_schema import (
    ActionConfig,
    AgentConfig,
    EntityConfig,
    ParamConfig,
    SceneConfig,
    SceneMetaConfig,
)
from worldseed.world import WorldEngine


def _mini_config(
    *,
    actions: dict[str, ActionConfig] | None = None,
) -> SceneConfig:
    """Build a minimal inline SceneConfig for validation tests."""
    return SceneConfig(
        scene=SceneMetaConfig(
            id="validate_params_test",
            description="Param validation test scene",
        ),
        entities=[
            EntityConfig(
                id="room",
                type="space",
                properties={"description": "A room"},
            ),
        ],
        agents=[
            AgentConfig(
                id="alice",
                properties={"location": "room", "hp": 100},
                character={"personality": "tester"},
            ),
        ],
        actions=actions
        or {
            "say": ActionConfig(
                description="Speak",
                params=[
                    ParamConfig(name="message", type="free_text", required=True),
                ],
            ),
            "trade": ActionConfig(
                description="Trade item",
                params=[
                    ParamConfig(name="target", type="entity_ref", required=True),
                    ParamConfig(name="item", type="string", required=True),
                    ParamConfig(name="note", type="free_text", required=False),
                ],
            ),
            "wait": ActionConfig(description="Do nothing"),
        },
    )


def _build_engine(config: SceneConfig) -> WorldEngine:
    engine = WorldEngine(config=config)
    engine.register_from_config()
    return engine


class TestValidateParams:
    """Tests for WorldEngine.validate_params()."""

    def test_valid_params_returns_none(self) -> None:
        """Valid params for a known action returns None (no error)."""
        engine = _build_engine(_mini_config())
        result = engine.validate_params("say", {"message": "hello"})
        assert result is None

    def test_missing_required_param_returns_error(self) -> None:
        """Missing a required param returns an error dict with expected schema."""
        engine = _build_engine(_mini_config())
        result = engine.validate_params("say", {})
        assert result is not None
        assert result["code"] == "invalid_params"
        assert "message" in result["message"]
        assert "expected" in result
        assert "message" in result["expected"]
        assert result["expected"]["message"]["required"] is True

    def test_unknown_action_returns_error_with_available_actions(self) -> None:
        """Unknown action returns error listing available actions."""
        engine = _build_engine(_mini_config())
        result = engine.validate_params("fly", {"speed": "fast"})
        assert result is not None
        assert result["code"] == "unknown_action"
        assert "fly" in result["message"]
        assert "available_actions" in result
        assert "say" in result["available_actions"]
        assert "trade" in result["available_actions"]
        assert "wait" in result["available_actions"]

    def test_optional_param_missing_is_ok(self) -> None:
        """Missing an optional param does not cause an error."""
        engine = _build_engine(_mini_config())
        # trade requires target + item, note is optional
        result = engine.validate_params("trade", {"target": "bob", "item": "food"})
        assert result is None

    def test_extra_params_are_allowed(self) -> None:
        """Extra params not in the schema are allowed (forward compatibility)."""
        engine = _build_engine(_mini_config())
        result = engine.validate_params("say", {"message": "hello", "volume": "loud", "emoji": True})
        assert result is None

    def test_action_with_no_params_empty_dict_valid(self) -> None:
        """Action with no params defined accepts empty params."""
        engine = _build_engine(_mini_config())
        result = engine.validate_params("wait", {})
        assert result is None

    def test_action_with_no_params_extra_params_valid(self) -> None:
        """Action with no params defined also accepts extra params."""
        engine = _build_engine(_mini_config())
        result = engine.validate_params("wait", {"random_key": "value"})
        assert result is None

    def test_multiple_missing_required_params_lists_all(self) -> None:
        """Multiple missing required params are all listed in the error."""
        engine = _build_engine(_mini_config())
        result = engine.validate_params("trade", {})
        assert result is not None
        assert result["code"] == "invalid_params"
        # Both target and item should be mentioned
        assert "target" in result["message"]
        assert "item" in result["message"]
        # Expected should have all params
        assert "target" in result["expected"]
        assert "item" in result["expected"]
        assert "note" in result["expected"]

    def test_partial_required_params_missing(self) -> None:
        """Only the missing required params are reported."""
        engine = _build_engine(_mini_config())
        result = engine.validate_params("trade", {"target": "bob"})
        assert result is not None
        assert result["code"] == "invalid_params"
        assert "item" in result["message"]
        # target is provided, should not appear in the missing list
        assert "target" not in str(result.get("message", "")).split("Missing")[0]

    def test_expected_schema_includes_all_params(self) -> None:
        """Expected schema includes all params with types and required."""
        engine = _build_engine(_mini_config())
        result = engine.validate_params("trade", {})
        assert result is not None
        expected = result["expected"]
        assert expected["target"]["type"] == "entity_ref"
        assert expected["target"]["required"] is True
        assert expected["item"]["type"] == "string"
        assert expected["item"]["required"] is True
        assert expected["note"]["type"] == "free_text"
        assert expected["note"]["required"] is False
