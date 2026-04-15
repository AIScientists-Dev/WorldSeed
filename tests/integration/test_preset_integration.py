"""Integration tests — verify presets work at runtime via public WorldEngine API.

Pattern: config defines everything → register_from_config → submit/step/perceive.
No internal state access. Perceive is how we verify.
"""

from __future__ import annotations

from tests.helpers import CONFIGS_DIR
from worldseed.dm.providers.mock import MockDMProvider
from worldseed.engine.rules_engine import ActionResult
from worldseed.models.config_schema import SceneConfig
from worldseed.scene.config import _resolve_presets
from worldseed.world import WorldEngine


def _engine(raw: dict) -> WorldEngine:
    """Create a WorldEngine from raw config dict with preset resolution."""
    resolved = _resolve_presets(raw, CONFIGS_DIR / "minimal.yaml")
    config = SceneConfig.model_validate(resolved)
    engine = WorldEngine(config=config, dm_provider=MockDMProvider())
    engine.register_from_config()
    return engine


# --- Talk ---


class TestTalkPreset:
    def test_talk_produces_event(self) -> None:
        e = _engine(
            {
                "scene": {"id": "t", "description": "t", "use": ["talk"]},
                "entities": [],
                "actions": {},
                "agents": [{"id": "a1", "character": {}}],
            }
        )
        result = e.submit("a1", "talk", {"message": "hello"})
        assert isinstance(result, ActionResult) and result.success
        e.step()
        perc = e.perceive("a1")
        assert any("hello" in ev.get("detail", "") for ev in perc.events)


class TestDirectedTalkPreset:
    def test_directed_talk_targets_agent(self) -> None:
        e = _engine(
            {
                "scene": {"id": "t", "description": "t", "use": ["directed_talk"]},
                "entities": [],
                "actions": {},
                "agents": [{"id": "a1", "character": {}}, {"id": "a2", "character": {}}],
            }
        )
        result = e.submit("a1", "directed_talk", {"target": "a2", "message": "psst"})
        assert isinstance(result, ActionResult) and result.success


# --- Move ---


class TestMoveSimplePreset:
    def test_move_changes_location(self) -> None:
        e = _engine(
            {
                "scene": {"id": "t", "description": "t", "use": ["move_simple"]},
                "entities": [
                    {"id": "room_a", "type": "space"},
                    {"id": "room_b", "type": "space"},
                ],
                "actions": {},
                "agents": [{"id": "a1", "location": "room_a", "character": {}}],
            }
        )
        result = e.submit("a1", "move", {"to": "room_b"})
        assert isinstance(result, ActionResult) and result.success
        perc = e.perceive("a1")
        assert perc.self_state["location"] == "room_b"


class TestMoveConnectedPreset:
    def test_move_to_connected_room(self) -> None:
        e = _engine(
            {
                "scene": {"id": "t", "description": "t", "use": ["move_connected"]},
                "entities": [
                    {"id": "room_a", "type": "space"},
                    {"id": "room_b", "type": "space"},
                ],
                "actions": {
                    # Set up connections via a setup action
                    "setup": {
                        "description": "noop",
                        "effects": [
                            {"operator": "add_relationship", "from": "room_a", "type": "connects_to", "to": "room_b"},
                            {"operator": "add_relationship", "from": "room_b", "type": "connects_to", "to": "room_a"},
                        ],
                    },
                },
                "agents": [{"id": "a1", "location": "room_a", "character": {}}],
            }
        )
        # Set up connections
        e.submit("a1", "setup", {})
        # Now move
        result = e.submit("a1", "move", {"to": "room_b"})
        assert isinstance(result, ActionResult) and result.success
        perc = e.perceive("a1")
        assert perc.self_state["location"] == "room_b"


# --- Consume ---


class TestConsumePreset:
    def test_consume_decrements_and_resets_hunger(self) -> None:
        e = _engine(
            {
                "scene": {"id": "t", "description": "t", "use": ["consume"]},
                "entities": [{"id": "food", "type": "resource", "quantity": 5, "location": "here"}],
                "actions": {},
                "agents": [{"id": "a1", "location": "here", "hunger": 50, "character": {}}],
            }
        )
        result = e.submit("a1", "consume", {"target": "food"})
        assert isinstance(result, ActionResult) and result.success
        perc = e.perceive("a1")
        assert perc.self_state["hunger"] == 0
        assert perc.nearby_entities["food"]["quantity"] == 4


# --- Rest ---


class TestRestPreset:
    def test_rest_heals(self) -> None:
        e = _engine(
            {
                "scene": {"id": "t", "description": "t", "use": ["rest"]},
                "entities": [],
                "actions": {},
                "agents": [{"id": "a1", "hp": 50, "character": {}}],
            }
        )
        result = e.submit("a1", "rest", {})
        assert isinstance(result, ActionResult) and result.success
        perc = e.perceive("a1")
        assert perc.self_state["hp"] == 65

    def test_rest_caps_at_100(self) -> None:
        e = _engine(
            {
                "scene": {"id": "t", "description": "t", "use": ["rest"]},
                "entities": [],
                "actions": {},
                "agents": [{"id": "a1", "hp": 95, "character": {}}],
            }
        )
        e.submit("a1", "rest", {})
        perc = e.perceive("a1")
        assert perc.self_state["hp"] == 100


# --- Hunger System ---


class TestHungerSystemPreset:
    def test_hunger_increases_on_tick(self) -> None:
        e = _engine(
            {
                "scene": {"id": "t", "description": "t", "use": ["hunger_system"]},
                "entities": [],
                "actions": {"noop": {"description": "do nothing"}},
                "agents": [{"id": "a1", "hunger": 0, "hp": 100, "character": {}}],
            }
        )
        e.step()
        perc = e.perceive("a1")
        assert perc.self_state["hunger"] == 3

    def test_starvation_damages_hp(self) -> None:
        e = _engine(
            {
                "scene": {"id": "t", "description": "t", "use": ["hunger_system"]},
                "entities": [],
                "actions": {"noop": {"description": "do nothing"}},
                "agents": [{"id": "a1", "hunger": 79, "hp": 100, "character": {}}],
            }
        )
        e.step()  # hunger → 82, starvation triggers
        perc = e.perceive("a1")
        assert perc.self_state["hp"] < 100


# --- Elimination ---


class TestEliminationHpPreset:
    def test_elimination_on_hp_zero(self) -> None:
        e = _engine(
            {
                "scene": {"id": "t", "description": "t", "use": ["elimination_hp"]},
                "entities": [],
                "actions": {"noop": {"description": "do nothing"}},
                "agents": [{"id": "a1", "hp": 0, "character": {}}],
            }
        )
        e.step()
        perc = e.perceive("a1")
        assert perc.self_state.get("eliminated") is True


class TestEliminationChipsPreset:
    def test_elimination_on_chips_zero(self) -> None:
        e = _engine(
            {
                "scene": {"id": "t", "description": "t", "use": ["elimination_chips"]},
                "entities": [],
                "actions": {"noop": {"description": "do nothing"}},
                "agents": [{"id": "a1", "chips": 0, "character": {}}],
            }
        )
        e.step()
        perc = e.perceive("a1")
        assert perc.self_state.get("eliminated") is True


# --- Timer ---


class TestTimerPreset:
    def test_timer_counts_down(self) -> None:
        e = _engine(
            {
                "scene": {"id": "t", "description": "t", "use": ["timer"]},
                "entities": [],
                "actions": {"noop": {"description": "do nothing"}},
                "agents": [{"id": "a1", "character": {}}],
            }
        )
        # Timer is a non-agent entity visible to a1
        perc_before = e.perceive("a1")
        timer_before = perc_before.nearby_entities.get("timer", {})
        assert timer_before.get("remaining") == 20
        e.step()
        perc_after = e.perceive("a1")
        timer_after = perc_after.nearby_entities.get("timer", {})
        assert timer_after.get("remaining") == 19


# --- Day/Night ---


class TestDayNightPreset:
    def test_day_to_night_after_10_ticks(self) -> None:
        e = _engine(
            {
                "scene": {"id": "t", "description": "t", "use": ["day_night"]},
                "entities": [],
                "actions": {"noop": {"description": "do nothing"}},
                "agents": [{"id": "a1", "character": {}}],
            }
        )
        perc = e.perceive("a1")
        assert perc.nearby_entities.get("clock", {}).get("time_of_day") == "day"
        for _ in range(10):
            e.step()
        perc = e.perceive("a1")
        assert perc.nearby_entities.get("clock", {}).get("time_of_day") == "night"


# --- Resource Decay ---


class TestResourceDecayPreset:
    def test_resources_decay_each_tick(self) -> None:
        e = _engine(
            {
                "scene": {"id": "t", "description": "t", "use": ["resource_decay"]},
                "entities": [
                    {"id": "food", "type": "resource", "quantity": 10},
                    {"id": "water", "type": "resource", "quantity": 8},
                ],
                "actions": {"noop": {"description": "do nothing"}},
                "agents": [{"id": "a1", "character": {}}],
            }
        )
        e.step()
        perc = e.perceive("a1")
        assert perc.nearby_entities["food"]["quantity"] == 9
        assert perc.nearby_entities["water"]["quantity"] == 7


# --- Deck ---


class TestDeckPreset:
    def test_deck_has_52_cards(self) -> None:
        e = _engine(
            {
                "scene": {"id": "t", "description": "t", "use": ["deck"]},
                "entities": [],
                "actions": {"noop": {"description": "do nothing"}},
                "agents": [{"id": "a1", "character": {}}],
            }
        )
        perc = e.perceive("a1")
        deck = perc.nearby_entities.get("deck", {})
        assert len(deck.get("cards", [])) == 52


# --- Same Location Perception ---


class TestSameLocationPerceptionPreset:
    def test_visibility_filters_by_location(self) -> None:
        e = _engine(
            {
                "scene": {"id": "t", "description": "t", "use": ["same_location_perception"]},
                "entities": [
                    {"id": "room_a", "type": "space"},
                    {"id": "room_b", "type": "space"},
                    {"id": "item_a", "type": "object", "location": "room_a"},
                    {"id": "item_b", "type": "object", "location": "room_b"},
                ],
                "actions": {"noop": {"description": "do nothing"}},
                "agents": [{"id": "a1", "location": "room_a", "character": {}}],
            }
        )
        perc = e.perceive("a1")
        visible = set(perc.nearby_entities.keys())
        assert "room_a" in visible
        assert "item_a" in visible
        assert "item_b" not in visible


# --- Composed ---


class TestComposedPresets:
    def test_talk_move_consume_hunger(self) -> None:
        e = _engine(
            {
                "scene": {
                    "id": "t",
                    "description": "t",
                    "use": ["talk", "move_simple", "consume", "hunger_system"],
                },
                "entities": [
                    {"id": "kitchen", "type": "space"},
                    {"id": "bedroom", "type": "space"},
                    {"id": "food", "type": "resource", "quantity": 5, "location": "kitchen"},
                ],
                "actions": {},
                "agents": [{"id": "a1", "location": "kitchen", "hunger": 0, "hp": 100, "character": {}}],
            }
        )
        # Talk
        r = e.submit("a1", "talk", {"message": "hungry"})
        assert isinstance(r, ActionResult) and r.success

        # Move away and back
        r = e.submit("a1", "move", {"to": "bedroom"})
        assert isinstance(r, ActionResult) and r.success
        assert e.perceive("a1").self_state["location"] == "bedroom"
        e.submit("a1", "move", {"to": "kitchen"})

        # Tick → hunger rises
        e.step()
        assert e.perceive("a1").self_state["hunger"] > 0

        # Consume → hunger resets
        r = e.submit("a1", "consume", {"target": "food"})
        assert isinstance(r, ActionResult) and r.success
        perc = e.perceive("a1")
        assert perc.self_state["hunger"] == 0
        assert perc.nearby_entities["food"]["quantity"] == 4
