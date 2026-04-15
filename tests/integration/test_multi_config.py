"""Test: Multi-config validation — every config runs 20+ ticks cleanly.

The ultimate non-hardcode test. For EVERY config in configs/:
  - Scene validator passes
  - Engine creates without error
  - 20+ ticks execute cleanly
  - Perception is well-formed
  - No assertion errors or crashes
  - Constraints respected throughout

ZERO HARDCODE: Parametrized across all 30 configs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers import (
    ConfigIntrospector,
    all_config_paths,
    assert_hidden_not_visible,
    assert_no_metadata_leak,
    load_any_config,
    make_world,
    standard_config_paths,
)


@pytest.fixture(params=all_config_paths(), ids=lambda p: p.stem)
def every_config(request: pytest.FixtureRequest) -> Path:
    """Every config, including chaos."""
    return request.param


@pytest.fixture(params=standard_config_paths(), ids=lambda p: p.stem)
def standard_config(request: pytest.FixtureRequest) -> Path:
    return request.param


class TestConfigValidation:
    """Scene validator catches errors before runtime."""

    def test_config_loads(self, every_config: Path) -> None:
        """Every YAML config loads without parse errors."""
        config = load_any_config(every_config)
        assert config.scene.id, "Scene must have an id"

    def test_scene_validator_no_errors(self, standard_config: Path) -> None:
        """Scene validator finds no errors (warnings ok) in standard configs."""
        from worldseed.scene.validator import validate

        config = load_any_config(standard_config)
        result = validate(config)
        errors = [m for m in result.messages if m.level == "error"]
        assert not errors, f"Validation errors: {[(e.code, e.summary) for e in errors]}"


class TestConfigRuns20Ticks:
    """Every standard config runs 20+ ticks without error."""

    def test_20_ticks_no_crash(self, standard_config: Path) -> None:
        """20 ticks with no actions — auto_tick + consequences run cleanly."""
        engine = make_world(standard_config)
        for _ in range(20):
            engine.step()
        assert engine.tick == 20

    def test_20_ticks_with_paramless_actions(self, standard_config: Path) -> None:
        """20 ticks submitting paramless actions each tick."""
        config = load_any_config(standard_config)
        intro = ConfigIntrospector(config)
        paramless = intro.paramless_actions()

        engine = make_world(standard_config)
        agents = engine.get_registered_agents()

        for i in range(20):
            if paramless and agents:
                for agent_id in agents:
                    engine.submit(agent_id, paramless[i % len(paramless)])
            engine.step()

        assert engine.tick == 20

    def test_perception_valid_after_20_ticks(self, standard_config: Path) -> None:
        """After 20 ticks, perception is well-formed for every agent."""
        config = load_any_config(standard_config)
        engine = make_world(standard_config)

        for _ in range(20):
            engine.step()

        for agent_id in engine.get_registered_agents():
            perception = engine.perceive(agent_id)
            pdict = perception.to_dict()

            # Structure check
            assert isinstance(pdict["self_state"], dict)
            assert isinstance(pdict["nearby_entities"], dict)
            assert isinstance(pdict["nearby_agents"], dict)
            assert isinstance(pdict["events"], list)
            assert isinstance(pdict["action_options"], dict)

            # No metadata leak
            assert_no_metadata_leak(pdict)

            # Hidden properties respected (skip omniscient agents —
            # they intentionally see all properties by design)
            profile = engine.get_agent_profile(agent_id)
            if not (profile and profile.omniscient):
                assert_hidden_not_visible(pdict, config.perception.hidden_properties)


class TestConfigConstraints:
    """Constraints hold after sustained running."""

    def test_constraints_hold_after_20_ticks(self, standard_config: Path) -> None:
        """No constrained property violates min/max after 20 ticks."""
        config = load_any_config(standard_config)
        intro = ConfigIntrospector(config)
        constrained = intro.entities_with_constraints()
        if not constrained:
            pytest.skip("No constrained entities")

        engine = make_world(standard_config)
        for _ in range(20):
            engine.step()

        for ce in constrained:
            entity = engine.state.get(ce["id"])
            if entity is None:
                continue
            for prop_name, constraint in ce["constraints"].items():
                val = entity.data.get(prop_name)
                if not isinstance(val, (int, float)):
                    continue
                if "min" in constraint:
                    assert val >= constraint["min"], f"{ce['id']}.{prop_name}={val} < min={constraint['min']}"
                if "max" in constraint:
                    assert val <= constraint["max"], f"{ce['id']}.{prop_name}={val} > max={constraint['max']}"


class TestConfigStateIntegrity:
    """World state remains consistent after running."""

    def test_all_agents_still_in_store(self, standard_config: Path) -> None:
        """After 20 ticks, all registered agents still exist in StateStore."""
        engine = make_world(standard_config)
        agents = engine.get_registered_agents()

        for _ in range(20):
            engine.step()

        for agent_id in agents:
            entity = engine.state.get(agent_id)
            assert entity is not None, f"Agent '{agent_id}' disappeared from StateStore"
            assert entity.type == "agent"

    def test_entities_from_config_still_exist(self, standard_config: Path) -> None:
        """After 20 ticks, all config-defined entities still exist."""
        config = load_any_config(standard_config)
        engine = make_world(standard_config)

        for _ in range(20):
            engine.step()

        for entity_cfg in config.entities:
            entity = engine.state.get(entity_cfg.id)
            assert entity is not None, f"Config entity '{entity_cfg.id}' disappeared from StateStore"

    def test_no_duplicate_entities(self, standard_config: Path) -> None:
        """No duplicate entity IDs in StateStore."""
        engine = make_world(standard_config)
        for _ in range(20):
            engine.step()

        all_entities = engine.state.all_entities()
        ids = [e.id for e in all_entities]
        assert len(ids) == len(set(ids)), f"Duplicate entity IDs: {[x for x in ids if ids.count(x) > 1]}"


class TestChaosConfigs:
    """Chaos configs (degenerate edge cases) don't crash the engine."""

    @pytest.fixture(
        params=[p for p in all_config_paths() if p.stem.startswith("chaos_")],
        ids=lambda p: p.stem,
    )
    def chaos_config(self, request: pytest.FixtureRequest) -> Path:
        return request.param

    def test_chaos_config_runs_20_ticks(self, chaos_config: Path) -> None:
        """Chaos configs run without crash even with extreme edge cases."""
        engine = make_world(chaos_config)
        for _ in range(20):
            engine.step()
        assert engine.tick == 20
