"""Tests for per-agent WORLD.md filtering (available_to)."""

from worldseed.models.config_schema import SceneConfig
from worldseed.world import WorldEngine


class TestPerAgentConfig:
    def _make_engine(self):
        config = SceneConfig.model_validate(
            {
                "scene": {"id": "t", "description": "t"},
                "entities": [],
                "agents": [
                    {
                        "id": "player1",
                        "character": {"personality": "test"},
                        "role": "player",
                    },
                    {
                        "id": "dealer",
                        "character": {"personality": "test"},
                        "role": "dealer",
                    },
                ],
                "actions": {
                    "fold": {
                        "description": "Fold",
                        "params": [],
                        "preconditions": [],
                        "effects": [],
                        "available_to": [
                            {
                                "operator": "check",
                                "left": "$agent.role",
                                "op": "==",
                                "right": "player",
                            },
                        ],
                    },
                    "deal": {
                        "description": "Deal cards",
                        "params": [],
                        "preconditions": [],
                        "effects": [],
                        "available_to": [
                            {
                                "operator": "check",
                                "left": "$agent.role",
                                "op": "==",
                                "right": "dealer",
                            },
                        ],
                    },
                    "talk": {
                        "description": "Talk",
                        "params": [],
                        "preconditions": [],
                        "effects": [],
                        # No available_to → visible to all
                    },
                },
            }
        )
        engine = WorldEngine(config=config)
        engine.register_from_config()
        return engine

    def test_player_sees_only_player_actions(self):
        """Verify per-agent action filtering via _build_action_options."""
        engine = self._make_engine()
        options = engine._build_action_options("player1")
        assert "fold" in options, "Player should see fold"
        assert "talk" in options, "Player should see talk (no filter)"
        assert "deal" not in options, "Player should NOT see deal"

    def test_dealer_sees_only_dealer_actions(self):
        engine = self._make_engine()
        options = engine._build_action_options("dealer")
        assert "deal" in options, "Dealer should see deal"
        assert "talk" in options, "Dealer should see talk (no filter)"
        assert "fold" not in options, "Dealer should NOT see fold"

    def test_action_options_filtered(self):
        """_build_action_options should also filter by available_to."""
        engine = self._make_engine()
        player_options = engine._build_action_options("player1")
        dealer_options = engine._build_action_options("dealer")

        assert "fold" in player_options
        assert "deal" not in player_options
        assert "deal" in dealer_options
        assert "fold" not in dealer_options
