"""Test: All perception paths produce clean, consistent output.

Three paths exist:
  1. perceive()       — REST/WS perceive (AgentPerception.to_dict())
  2. peek_perception() — wake message source (tick_runner uses this)
  3. agent_world_view() — dashboard inspector

All must:
  - Never contain engine metadata (constraints, _constraints)
  - Never expose hidden_properties in other entities/agents
  - Produce structurally consistent data

ZERO HARDCODE: All data read from config dynamically.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers import (
    ConfigIntrospector,
    assert_hidden_not_visible,
    assert_no_metadata_leak,
    load_any_config,
    make_world,
    standard_config_paths,
)


@pytest.fixture(params=standard_config_paths(), ids=lambda p: p.stem)
def config_path(request: pytest.FixtureRequest) -> Path:
    return request.param


class TestPerceptionNoMetadataLeak:
    """Constraints and internal metadata never appear in any perception path."""

    def test_perceive_path_no_metadata(self, config_path: Path) -> None:
        """Path 1: engine.perceive() → AgentPerception.to_dict()."""
        engine = make_world(config_path)
        # Step a few ticks so state changes occur
        for _ in range(3):
            engine.step()

        for agent_id in engine.get_registered_agents():
            perception = engine.perceive(agent_id)
            pdict = perception.to_dict()
            assert_no_metadata_leak(pdict)

    def test_peek_perception_no_metadata(self, config_path: Path) -> None:
        """Path 2: engine.peek_perception() — wake message source."""
        engine = make_world(config_path)
        for _ in range(3):
            engine.step()

        for agent_id in engine.get_registered_agents():
            peek = engine.peek_perception(agent_id)
            assert_no_metadata_leak(peek)

    def test_agent_world_view_no_metadata(self, config_path: Path) -> None:
        """Path 3: engine.agent_world_view() — dashboard inspector."""
        engine = make_world(config_path)
        for _ in range(3):
            engine.step()

        for agent_id in engine.get_registered_agents():
            view = engine.agent_world_view(agent_id)
            assert_no_metadata_leak(view)


class TestPerceptionHiddenProperties:
    """Hidden properties never leak into other entities/agents."""

    def test_perceive_hides_from_others(self, config_path: Path) -> None:
        """Hidden props invisible in nearby_entities/nearby_agents."""
        config = load_any_config(config_path)
        hidden = config.perception.hidden_properties
        if not hidden:
            pytest.skip("No hidden_properties in this config")

        engine = make_world(config_path)
        for _ in range(3):
            engine.step()

        for agent_id in engine.get_registered_agents():
            profile = engine.get_agent_profile(agent_id)
            if profile and profile.omniscient:
                continue
            perception = engine.perceive(agent_id)
            assert_hidden_not_visible(perception.to_dict(), hidden)

    def test_peek_perception_hides_from_others(self, config_path: Path) -> None:
        """Hidden props invisible in peek_perception nearby_entities/agents."""
        config = load_any_config(config_path)
        hidden = config.perception.hidden_properties
        if not hidden:
            pytest.skip("No hidden_properties in this config")

        engine = make_world(config_path)
        for _ in range(3):
            engine.step()

        for agent_id in engine.get_registered_agents():
            profile = engine.get_agent_profile(agent_id)
            if profile and profile.omniscient:
                continue
            peek = engine.peek_perception(agent_id)
            assert_hidden_not_visible(peek, hidden)

    def test_world_view_hides_from_others(self, config_path: Path) -> None:
        """Hidden props invisible in agent_world_view nearby_entities/agents."""
        config = load_any_config(config_path)
        hidden = config.perception.hidden_properties
        if not hidden:
            pytest.skip("No hidden_properties in this config")

        engine = make_world(config_path)
        for _ in range(3):
            engine.step()

        for agent_id in engine.get_registered_agents():
            profile = engine.get_agent_profile(agent_id)
            if profile and profile.omniscient:
                continue
            view = engine.agent_world_view(agent_id)
            assert_hidden_not_visible(view, hidden)


class TestPerceptionStructure:
    """All perception paths return well-structured data."""

    REQUIRED_PERCEIVE_KEYS = {
        "self_state",
        "nearby_entities",
        "nearby_agents",
        "events",
        "whispers",
        "action_options",
    }

    REQUIRED_PEEK_KEYS = {
        "self_state",
        "nearby_entities",
        "nearby_agents",
        "events",
        "whispers",
        "action_options",
        "tick",
    }

    REQUIRED_VIEW_KEYS = {
        "self_state",
        "nearby_entities",
        "nearby_agents",
        "events",
    }

    def test_perceive_structure(self, config_path: Path) -> None:
        """perceive() returns all required keys with correct types."""
        engine = make_world(config_path)
        engine.step()

        for agent_id in engine.get_registered_agents():
            pdict = engine.perceive(agent_id).to_dict()
            assert self.REQUIRED_PERCEIVE_KEYS <= set(pdict.keys()), (
                f"Missing keys: {self.REQUIRED_PERCEIVE_KEYS - set(pdict.keys())}"
            )
            assert isinstance(pdict["self_state"], dict)
            assert isinstance(pdict["nearby_entities"], dict)
            assert isinstance(pdict["nearby_agents"], dict)
            assert isinstance(pdict["events"], list)
            assert isinstance(pdict["whispers"], list)
            assert isinstance(pdict["action_options"], dict)

    def test_peek_structure(self, config_path: Path) -> None:
        """peek_perception() returns all required keys."""
        engine = make_world(config_path)
        engine.step()

        for agent_id in engine.get_registered_agents():
            peek = engine.peek_perception(agent_id)
            assert self.REQUIRED_PEEK_KEYS <= set(peek.keys()), (
                f"Missing keys: {self.REQUIRED_PEEK_KEYS - set(peek.keys())}"
            )
            assert isinstance(peek["tick"], int)

    def test_view_structure(self, config_path: Path) -> None:
        """agent_world_view() returns all required keys."""
        engine = make_world(config_path)
        engine.step()

        for agent_id in engine.get_registered_agents():
            view = engine.agent_world_view(agent_id)
            assert self.REQUIRED_VIEW_KEYS <= set(view.keys()), (
                f"Missing keys: {self.REQUIRED_VIEW_KEYS - set(view.keys())}"
            )


class TestPerceptionContentAccuracy:
    """Perception contains accurate world state, not stale or fabricated data."""

    def test_self_state_matches_entity(self, config_path: Path) -> None:
        """Agent's self_state matches actual Entity.data in StateStore."""
        engine = make_world(config_path)
        for _ in range(3):
            engine.step()

        for agent_id in engine.get_registered_agents():
            entity = engine.state.get(agent_id)
            assert entity is not None, f"Agent {agent_id} not in StateStore"

            perception = engine.perceive(agent_id)
            self_state = perception.to_dict()["self_state"]

            # Every property in entity.data should be in self_state
            for key, value in entity.data.items():
                assert key in self_state, f"Property '{key}' in entity.data but missing from self_state"
                assert self_state[key] == value, f"Property '{key}': entity={value}, perception={self_state[key]}"

    def test_nearby_entities_exist_in_store(self, config_path: Path) -> None:
        """Every visible entity actually exists in StateStore."""
        engine = make_world(config_path)
        engine.step()

        for agent_id in engine.get_registered_agents():
            perception = engine.perceive(agent_id)
            pdict = perception.to_dict()

            for eid in pdict["nearby_entities"]:
                assert engine.state.get(eid) is not None, f"Visible entity '{eid}' does not exist in StateStore"

            for aid in pdict["nearby_agents"]:
                assert engine.state.get(aid) is not None, f"Visible agent '{aid}' does not exist in StateStore"

    def test_agent_does_not_see_self_in_visible(self, config_path: Path) -> None:
        """Agent should NOT appear in their own nearby_agents."""
        engine = make_world(config_path)
        engine.step()

        for agent_id in engine.get_registered_agents():
            perception = engine.perceive(agent_id)
            pdict = perception.to_dict()
            assert agent_id not in pdict["nearby_agents"], f"Agent '{agent_id}' sees itself in nearby_agents"
            assert agent_id not in pdict["nearby_entities"], f"Agent '{agent_id}' sees itself in nearby_entities"

    def test_action_options_from_config(self, config_path: Path) -> None:
        """Each agent's action_options is a subset of config actions.
        available_to + game state may hide actions that aren't reachable yet."""
        engine = make_world(config_path)
        engine.step()

        config_actions = set(engine.config.actions.keys())
        for agent_id in engine.get_registered_agents():
            perception = engine.perceive(agent_id)
            pdict = perception.to_dict()
            action_names = set(pdict["action_options"].keys())
            extra = action_names - config_actions
            assert not extra, f"Agent {agent_id} sees actions not in config: {extra}"


class TestPerceptionConstraintsWithData:
    """Configs with constraints: verify enforcement works but constraints invisible."""

    def test_constrained_entities_enforced_but_invisible(self, config_path: Path) -> None:
        """Entities with constraints: values clamped, constraints not in perception."""
        config = load_any_config(config_path)
        intro = ConfigIntrospector(config)
        constrained = intro.entities_with_constraints()
        if not constrained:
            pytest.skip("No constrained entities in this config")

        engine = make_world(config_path)
        # Run enough ticks for auto_tick to modify values
        for _ in range(10):
            engine.step()

        for agent_id in engine.get_registered_agents():
            perception = engine.perceive(agent_id)
            pdict = perception.to_dict()

            all_visible = {
                **pdict.get("nearby_entities", {}),
                **pdict.get("nearby_agents", {}),
            }

            for ce in constrained:
                if ce["id"] not in all_visible:
                    continue  # Not visible to this agent
                visible_props = all_visible[ce["id"]]
                assert "constraints" not in visible_props, f"Constraints visible for '{ce['id']}'"

                # Verify constrained properties respect bounds
                for prop_name, constraint in ce["constraints"].items():
                    if prop_name not in visible_props:
                        continue
                    val = visible_props[prop_name]
                    if not isinstance(val, (int, float)):
                        continue
                    if "min" in constraint:
                        assert val >= constraint["min"], f"'{ce['id']}.{prop_name}'={val} below min={constraint['min']}"
                    if "max" in constraint:
                        assert val <= constraint["max"], f"'{ce['id']}.{prop_name}'={val} above max={constraint['max']}"
