"""Test: StateStore constraint enforcement across all write paths.

Constraints (min/max) are defined per-entity in config.
They must be enforced consistently regardless of HOW the value is written:
  - Action effects (DSL set/add/subtract)
  - DM effects
  - auto_tick effects
  - God-mode API
  - Direct update_property calls

ZERO HARDCODE: Constrained entities and their limits read from config.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers import (
    ConfigIntrospector,
    load_any_config,
    make_world,
    standard_config_paths,
)


@pytest.fixture(params=standard_config_paths(), ids=lambda p: p.stem)
def config_path(request: pytest.FixtureRequest) -> Path:
    return request.param


class TestConstraintEnforcementViaUpdateProperty:
    """Direct StateStore.update_property enforces min/max."""

    def test_min_constraint_clamps(self, config_path: Path) -> None:
        """Values below min are clamped to min."""
        config = load_any_config(config_path)
        intro = ConfigIntrospector(config)
        constrained = intro.entities_with_constraints()
        if not constrained:
            pytest.skip("No constrained entities")

        engine = make_world(config_path)

        for ce in constrained:
            entity = engine.state.get(ce["id"])
            if entity is None:
                continue
            for prop_name, constraint in ce["constraints"].items():
                if "min" not in constraint:
                    continue
                min_val = constraint["min"]
                # Try to set far below min
                engine.state.update_property(ce["id"], prop_name, min_val - 1000)
                actual = entity.data.get(prop_name)
                assert actual == min_val, (
                    f"{ce['id']}.{prop_name}: set to {min_val - 1000}, expected clamped to {min_val}, got {actual}"
                )

    def test_max_constraint_clamps(self, config_path: Path) -> None:
        """Values above max are clamped to max."""
        config = load_any_config(config_path)
        intro = ConfigIntrospector(config)
        constrained = intro.entities_with_constraints()
        if not constrained:
            pytest.skip("No constrained entities")

        engine = make_world(config_path)

        for ce in constrained:
            entity = engine.state.get(ce["id"])
            if entity is None:
                continue
            for prop_name, constraint in ce["constraints"].items():
                if "max" not in constraint:
                    continue
                max_val = constraint["max"]
                engine.state.update_property(ce["id"], prop_name, max_val + 1000)
                actual = entity.data.get(prop_name)
                assert actual == max_val, (
                    f"{ce['id']}.{prop_name}: set to {max_val + 1000}, expected clamped to {max_val}, got {actual}"
                )

    def test_within_bounds_unchanged(self, config_path: Path) -> None:
        """Values within bounds are stored as-is."""
        config = load_any_config(config_path)
        intro = ConfigIntrospector(config)
        constrained = intro.entities_with_constraints()
        if not constrained:
            pytest.skip("No constrained entities")

        engine = make_world(config_path)

        for ce in constrained:
            entity = engine.state.get(ce["id"])
            if entity is None:
                continue
            for prop_name, constraint in ce["constraints"].items():
                lo = constraint.get("min", 0)
                hi = constraint.get("max", 100)
                mid = (lo + hi) / 2
                engine.state.update_property(ce["id"], prop_name, mid)
                actual = entity.data.get(prop_name)
                assert actual == mid, f"{ce['id']}.{prop_name}: set to {mid}, got {actual}"


class TestConstraintEnforcementViaAutoTick:
    """auto_tick effects respect constraints (indirect via update_property)."""

    def test_auto_tick_respects_min(self, config_path: Path) -> None:
        """auto_tick degradation cannot push values below min."""
        config = load_any_config(config_path)
        intro = ConfigIntrospector(config)
        constrained = intro.entities_with_constraints()
        if not constrained or not intro.has_auto_tick():
            pytest.skip("No constrained entities or no auto_tick")

        engine = make_world(config_path)

        # Run many ticks — auto_tick typically degrades values
        for _ in range(500):
            engine.step()

        # Verify no constrained property went below min
        for ce in constrained:
            entity = engine.state.get(ce["id"])
            if entity is None:
                continue
            for prop_name, constraint in ce["constraints"].items():
                if "min" not in constraint:
                    continue
                val = entity.data.get(prop_name)
                if not isinstance(val, (int, float)):
                    continue
                assert val >= constraint["min"], (
                    f"After 500 ticks: {ce['id']}.{prop_name}={val} below min={constraint['min']}"
                )

    def test_auto_tick_respects_max(self, config_path: Path) -> None:
        """auto_tick cannot push values above max."""
        config = load_any_config(config_path)
        intro = ConfigIntrospector(config)
        constrained = intro.entities_with_constraints()
        if not constrained or not intro.has_auto_tick():
            pytest.skip("No constrained entities or no auto_tick")

        engine = make_world(config_path)

        for _ in range(500):
            engine.step()

        for ce in constrained:
            entity = engine.state.get(ce["id"])
            if entity is None:
                continue
            for prop_name, constraint in ce["constraints"].items():
                if "max" not in constraint:
                    continue
                val = entity.data.get(prop_name)
                if not isinstance(val, (int, float)):
                    continue
                assert val <= constraint["max"], (
                    f"After 500 ticks: {ce['id']}.{prop_name}={val} above max={constraint['max']}"
                )


class TestConstraintSeparation:
    """Constraints exist in Entity._constraints, never in Entity._data."""

    def test_constraints_not_in_data(self, config_path: Path) -> None:
        """Entity.data (game state) never contains constraints key."""
        engine = make_world(config_path)

        for entity in engine.state.all_entities():
            assert "constraints" not in entity.data, f"Entity '{entity.id}' has 'constraints' in data dict"

    def test_constrained_entities_have_metadata(self, config_path: Path) -> None:
        """Entities defined with constraints have them in _constraints."""
        config = load_any_config(config_path)
        intro = ConfigIntrospector(config)
        constrained = intro.entities_with_constraints()
        if not constrained:
            pytest.skip("No constrained entities")

        engine = make_world(config_path)

        for ce in constrained:
            entity = engine.state.get(ce["id"])
            assert entity is not None, f"Entity '{ce['id']}' not in store"
            assert entity.constraints, f"Entity '{ce['id']}' defined with constraints but entity.constraints is empty"
            # Verify constraint keys match config
            for prop_name in ce["constraints"]:
                assert prop_name in entity.constraints, f"Entity '{ce['id']}' missing constraint for '{prop_name}'"

    def test_to_dict_never_has_constraints(self, config_path: Path) -> None:
        """Entity.to_dict() (used for perception) never includes constraints."""
        engine = make_world(config_path)

        for _ in range(5):
            engine.step()

        for entity in engine.state.all_entities():
            d = entity.to_dict()
            assert "constraints" not in d, f"to_dict() for '{entity.id}' includes constraints"
            assert "_constraints" not in d, f"to_dict() for '{entity.id}' includes _constraints"

    def test_to_full_dict_has_constraints(self, config_path: Path) -> None:
        """Entity.to_full_dict() (for persistence) includes constraints."""
        config = load_any_config(config_path)
        intro = ConfigIntrospector(config)
        constrained = intro.entities_with_constraints()
        if not constrained:
            pytest.skip("No constrained entities")

        engine = make_world(config_path)

        for ce in constrained:
            entity = engine.state.get(ce["id"])
            if entity is None:
                continue
            full = entity.to_full_dict()
            assert "constraints" in full, f"to_full_dict() for '{ce['id']}' missing constraints"


class TestConstraintPersistenceRoundtrip:
    """Constraints survive save/load cycle."""

    def test_save_load_preserves_constraints(self, config_path: Path) -> None:
        """After save_state + load_state, constraints still enforced."""
        config = load_any_config(config_path)
        intro = ConfigIntrospector(config)
        constrained = intro.entities_with_constraints()
        if not constrained:
            pytest.skip("No constrained entities")

        engine = make_world(config_path)
        for _ in range(5):
            engine.step()

        # Collect state for save
        saved_entities = [e.to_full_dict() for e in engine.state.all_entities()]
        saved_tick = engine.tick

        # Create fresh engine and load
        engine2 = make_world(config_path, register_agents=False)
        engine2.load_state(saved_entities, saved_tick)

        # Verify constraints still enforced
        for ce in constrained:
            entity = engine2.state.get(ce["id"])
            if entity is None:
                continue
            assert entity.constraints, f"After load: '{ce['id']}' lost constraints"
            for prop_name, constraint in ce["constraints"].items():
                if "min" not in constraint:
                    continue
                min_val = constraint["min"]
                engine2.state.update_property(ce["id"], prop_name, min_val - 100)
                actual = entity.data.get(prop_name)
                assert actual == min_val, f"After load: constraint not enforced for '{ce['id']}.{prop_name}'"
