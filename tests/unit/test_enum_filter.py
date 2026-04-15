"""Tests for enum_filter on action params.

Covers: type filter, multi-property filter, empty results, missing properties,
non-$visible enum_from, backward compatibility, edge cases.
"""

from __future__ import annotations

from worldseed.world import WorldEngine


def _make_config(actions_yaml: str, entities_yaml: str = "", agents_yaml: str = "") -> str:
    """Build a minimal scene config YAML string."""
    return f"""
scene:
  id: test_enum_filter
  description: "Test enum_filter"

entities:
{entities_yaml}

agents:
{agents_yaml}

actions:
{actions_yaml}

perception:
  visibility: []
  hidden_properties: []

auto_tick: []
"""


def _engine_with_config(yaml_str: str) -> WorldEngine:
    """Create a WorldEngine from inline YAML config."""
    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_str)
        f.flush()
        engine = WorldEngine(config_path=Path(f.name))
    engine.register_from_config()
    return engine


# ── Basic type filter ──


class TestTypeFilter:
    """enum_filter: { type: "agent" } should only return agents."""

    def test_filter_agents_only(self) -> None:
        cfg = _make_config(
            actions_yaml="""
  test_act:
    description: "test"
    params:
      - { name: target, type: entity_ref, enum_from: "$visible", enum_filter: { type: "agent" } }
    preconditions: []
    effects: []
    events: []
""",
            entities_yaml="""
  - id: room_a
    type: space
    description: "A room"
  - id: sword
    type: item
    description: "A sword"
    location: room_a
  - id: table
    type: prop
    description: "A table"
    location: room_a
""",
            agents_yaml="""
  - id: hero
    location: room_a
    character: {}
  - id: villain
    location: room_a
    character: {}
""",
        )
        engine = _engine_with_config(cfg)
        # Perceive first to populate inbox
        engine.perceive("hero")
        options = engine._build_action_options("hero")
        targets = options["test_act"]["target"]
        assert isinstance(targets, list)
        assert "villain" in targets
        assert "hero" not in targets  # self excluded by $visible? depends on config
        assert "sword" not in targets
        assert "table" not in targets
        assert "room_a" not in targets

    def test_filter_items_only(self) -> None:
        cfg = _make_config(
            actions_yaml="""
  grab:
    description: "grab item"
    params:
      - { name: item, type: entity_ref, enum_from: "$visible", enum_filter: { type: "item" } }
    preconditions: []
    effects: []
    events: []
""",
            entities_yaml="""
  - id: room_a
    type: space
    description: "A room"
  - id: sword
    type: item
    location: room_a
  - id: shield
    type: item
    location: room_a
  - id: table
    type: prop
    location: room_a
""",
            agents_yaml="""
  - id: hero
    location: room_a
    character: {}
""",
        )
        engine = _engine_with_config(cfg)
        engine.perceive("hero")
        options = engine._build_action_options("hero")
        items = options["grab"]["item"]
        assert isinstance(items, list)
        assert "sword" in items
        assert "shield" in items
        assert "table" not in items
        assert "room_a" not in items
        assert "hero" not in items


# ── Multi-property filter (AND logic) ──


class TestMultiPropertyFilter:
    """enum_filter with multiple keys: ALL must match."""

    def test_multi_property_and(self) -> None:
        cfg = _make_config(
            actions_yaml="""
  test_act:
    description: "test"
    params:
      - { name: target, type: entity_ref, enum_from: "$visible", enum_filter: { type: "item", location: "room_a" } }
    preconditions: []
    effects: []
    events: []
""",
            entities_yaml="""
  - id: room_a
    type: space
  - id: room_b
    type: space
  - id: sword
    type: item
    location: room_a
  - id: axe
    type: item
    location: room_b
  - id: table
    type: prop
    location: room_a
""",
            agents_yaml="""
  - id: hero
    location: room_a
    character: {}
""",
        )
        engine = _engine_with_config(cfg)
        engine.perceive("hero")
        options = engine._build_action_options("hero")
        targets = options["test_act"]["target"]
        assert isinstance(targets, list)
        # sword is item + location room_a → pass
        assert "sword" in targets
        # axe is item but location room_b → fail (but also not visible)
        assert "axe" not in targets
        # table is prop, not item → fail
        assert "table" not in targets


# ── Missing property on entity ──


class TestMissingProperty:
    """Entity without the filtered property should be excluded."""

    def test_missing_property_excluded(self) -> None:
        cfg = _make_config(
            actions_yaml="""
  test_act:
    description: "test"
    params:
      - { name: target, type: entity_ref, enum_from: "$visible", enum_filter: { type: "item", holder: "hero" } }
    preconditions: []
    effects: []
    events: []
""",
            entities_yaml="""
  - id: room_a
    type: space
  - id: sword
    type: item
    location: room_a
    holder: hero
  - id: rock
    type: item
    location: room_a
""",
            agents_yaml="""
  - id: hero
    location: room_a
    character: {}
""",
        )
        engine = _engine_with_config(cfg)
        engine.perceive("hero")
        options = engine._build_action_options("hero")
        targets = options["test_act"]["target"]
        assert isinstance(targets, list)
        # sword: type=item, holder=hero → pass
        assert "sword" in targets
        # rock: type=item, no holder property → fail
        assert "rock" not in targets


# ── Empty result fallback ──


class TestEmptyResult:
    """Filter that removes everything falls back to type string."""

    def test_empty_falls_back_to_type(self) -> None:
        cfg = _make_config(
            actions_yaml="""
  test_act:
    description: "test"
    params:
      - { name: target, type: entity_ref, enum_from: "$visible", enum_filter: { type: "dragon" } }
    preconditions: []
    effects: []
    events: []
""",
            entities_yaml="""
  - id: room_a
    type: space
  - id: sword
    type: item
    location: room_a
""",
            agents_yaml="""
  - id: hero
    location: room_a
    character: {}
""",
        )
        engine = _engine_with_config(cfg)
        engine.perceive("hero")
        options = engine._build_action_options("hero")
        # No dragons exist → falls back to type string
        assert options["test_act"]["target"] == "entity_ref"


# ── Non-$visible enum_from with filter ──


class TestNonVisibleEnumFrom:
    """enum_filter works with DSL expressions like relationships_of(...)."""

    def test_filter_on_relationships(self) -> None:
        cfg = _make_config(
            actions_yaml="""
  move:
    description: "move"
    params:
      - name: to
        type: entity_ref
        enum_from: "relationships_of($agent.location, type=connects_to)"
        enum_filter: { type: "space" }
    preconditions: []
    effects: []
    events: []
""",
            entities_yaml="""
  - id: room_a
    type: space
    connects_to: [room_b, room_c]
  - id: room_b
    type: space
    connects_to: [room_a]
  - id: room_c
    type: space
    connects_to: [room_a]
""",
            agents_yaml="""
  - id: hero
    location: room_a
    character: {}
""",
        )
        engine = _engine_with_config(cfg)
        engine.perceive("hero")
        options = engine._build_action_options("hero")
        targets = options["move"]["to"]
        assert isinstance(targets, list)
        assert "room_b" in targets
        assert "room_c" in targets


# ── Backward compatibility ──


class TestBackwardCompatibility:
    """Params without enum_filter work exactly as before."""

    def test_no_filter_returns_all_visible(self) -> None:
        cfg = _make_config(
            actions_yaml="""
  test_act:
    description: "test"
    params:
      - { name: target, type: entity_ref, enum_from: "$visible" }
    preconditions: []
    effects: []
    events: []
""",
            entities_yaml="""
  - id: room_a
    type: space
  - id: sword
    type: item
    location: room_a
""",
            agents_yaml="""
  - id: hero
    location: room_a
    character: {}
""",
        )
        engine = _engine_with_config(cfg)
        engine.perceive("hero")
        options = engine._build_action_options("hero")
        targets = options["test_act"]["target"]
        assert isinstance(targets, list)
        # Without filter, ALL visible entities are included
        assert "sword" in targets
        assert "room_a" in targets

    def test_no_enum_from_returns_type_string(self) -> None:
        cfg = _make_config(
            actions_yaml="""
  test_act:
    description: "test"
    params:
      - { name: msg, type: free_text }
    preconditions: []
    effects: []
    events: []
""",
            entities_yaml="""
  - id: room_a
    type: space
""",
            agents_yaml="""
  - id: hero
    location: room_a
    character: {}
""",
        )
        engine = _engine_with_config(cfg)
        options = engine._build_action_options("hero")
        assert options["test_act"]["msg"] == "free_text"


# ── Two params with different filters on same action ──


class TestDifferentFiltersPerParam:
    """pass_item: item param filtered to items, to param filtered to agents."""

    def test_different_filters(self) -> None:
        cfg = _make_config(
            actions_yaml="""
  pass:
    description: "pass item"
    params:
      - { name: item, type: entity_ref, enum_from: "$visible", enum_filter: { type: "item" } }
      - { name: to, type: entity_ref, enum_from: "$visible", enum_filter: { type: "agent" } }
    preconditions: []
    effects: []
    events: []
""",
            entities_yaml="""
  - id: room_a
    type: space
  - id: sword
    type: item
    location: room_a
  - id: table
    type: prop
    location: room_a
""",
            agents_yaml="""
  - id: hero
    location: room_a
    character: {}
  - id: friend
    location: room_a
    character: {}
""",
        )
        engine = _engine_with_config(cfg)
        engine.perceive("hero")
        options = engine._build_action_options("hero")
        items = options["pass"]["item"]
        recipients = options["pass"]["to"]
        assert isinstance(items, list)
        assert isinstance(recipients, list)
        # item param: only items
        assert "sword" in items
        assert "table" not in items
        assert "friend" not in items
        # to param: only agents
        assert "friend" in recipients
        assert "sword" not in recipients
        assert "table" not in recipients


# ── Entity removed between deliver and options build ──


class TestEntityRemovedRace:
    """If entity disappears from state, it should be silently excluded."""

    def test_removed_entity_excluded(self) -> None:
        cfg = _make_config(
            actions_yaml="""
  test_act:
    description: "test"
    params:
      - { name: target, type: entity_ref, enum_from: "$visible", enum_filter: { type: "agent" } }
    preconditions: []
    effects: []
    events: []
""",
            entities_yaml="""
  - id: room_a
    type: space
""",
            agents_yaml="""
  - id: hero
    location: room_a
    character: {}
  - id: ghost
    location: room_a
    character: {}
""",
        )
        engine = _engine_with_config(cfg)
        engine.perceive("hero")
        # Remove ghost from state after perceive (simulates race condition)
        engine.state.remove("ghost")
        options = engine._build_action_options("hero")
        targets = options["test_act"]["target"]
        # ghost was in inbox snapshot but removed from state → excluded by filter
        if isinstance(targets, list):
            assert "ghost" not in targets


# ── Config validation ──


class TestConfigValidation:
    """enum_filter should be accepted by config loader without errors."""

    def test_config_loads_with_enum_filter(self) -> None:
        cfg = _make_config(
            actions_yaml="""
  test:
    description: "test"
    params:
      - { name: t, type: entity_ref, enum_from: "$visible", enum_filter: { type: "agent" } }
    preconditions: []
    effects: []
    events: []
""",
            entities_yaml="""
  - id: room_a
    type: space
""",
            agents_yaml="""
  - id: hero
    location: room_a
    character: {}
""",
        )
        engine = _engine_with_config(cfg)
        assert engine._config.actions["test"].params[0].enum_filter == {"type": "agent"}

    def test_config_loads_without_enum_filter(self) -> None:
        cfg = _make_config(
            actions_yaml="""
  test:
    description: "test"
    params:
      - { name: t, type: entity_ref, enum_from: "$visible" }
    preconditions: []
    effects: []
    events: []
""",
            entities_yaml="""
  - id: room_a
    type: space
""",
            agents_yaml="""
  - id: hero
    location: room_a
    character: {}
""",
        )
        engine = _engine_with_config(cfg)
        assert engine._config.actions["test"].params[0].enum_filter is None


# ── Chinese entity IDs ──


class TestChineseEntityIds:
    """enum_filter works with Chinese entity IDs and type names."""

    def test_chinese_ids(self) -> None:
        cfg = _make_config(
            actions_yaml="""
  观察:
    description: "observe"
    params:
      - { name: target, type: entity_ref, enum_from: "$visible", enum_filter: { type: "agent" } }
    preconditions: []
    effects: []
    events: []
""",
            entities_yaml="""
  - id: 大堂
    type: space
  - id: 紫砂壶
    type: prop
    location: 大堂
""",
            agents_yaml="""
  - id: 老赵
    location: 大堂
    character: {}
  - id: 王富
    location: 大堂
    character: {}
""",
        )
        engine = _engine_with_config(cfg)
        engine.perceive("老赵")
        options = engine._build_action_options("老赵")
        targets = options["观察"]["target"]
        assert isinstance(targets, list)
        assert "王富" in targets
        assert "紫砂壶" not in targets
        assert "大堂" not in targets
