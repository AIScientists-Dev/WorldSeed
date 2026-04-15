"""Edge-case tests for new DSL features: rotate+when, max_by, count WHERE, consequences."""

from __future__ import annotations

import pytest

from worldseed.dsl.effects import execute
from worldseed.dsl.functions.aggregation import _call_max_by, count
from worldseed.dsl.path_resolver import resolve
from worldseed.engine.consequence_scanner import ConsequenceScanner
from worldseed.engine.event_log import EventLog
from worldseed.engine.state_store import StateStore
from worldseed.models.config_schema import (
    ConsequenceConfig,
    EffectConfig,
    PreconditionConfig,
    SceneConfig,
    SceneMetaConfig,
)
from worldseed.models.entity import Entity

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(consequences: dict[str, ConsequenceConfig]) -> SceneConfig:
    return SceneConfig(
        scene=SceneMetaConfig(id="test", description="test"),
        entities=[],
        actions={},
        consequences=consequences,
    )


# ---------------------------------------------------------------------------
# 1. rotate + when combined
# ---------------------------------------------------------------------------


class TestRotateWithWhen:
    """An effect that rotates only when a condition is true."""

    @pytest.fixture()
    def store(self) -> StateStore:
        s = StateStore()
        s.add(
            Entity(
                id="game",
                type="game_state",
                _data={
                    "phase": "night",
                    "active_role": "werewolf",
                    "role_order": ["werewolf", "seer", "witch", "hunter"],
                },
            )
        )
        return s

    @pytest.fixture()
    def event_log(self) -> EventLog:
        return EventLog()

    @pytest.fixture()
    def ctx(self) -> dict:
        return {"agent_id": "someone", "action_params": {}, "tick": 1}

    def test_rotate_executes_when_condition_true(self, store, event_log, ctx):
        """Rotate fires when the `when` condition is satisfied."""
        effect = EffectConfig(
            operator="rotate",
            target="game.active_role",
            sequence="game.role_order",
            when=PreconditionConfig(
                operator="check",
                left="game.phase",
                op="==",
                right="night",
            ),
        )
        execute(effect, store, event_log, ctx, tick=1)
        assert store.get("game")["active_role"] == "seer"

    def test_rotate_skipped_when_condition_false(self, store, event_log, ctx):
        """Rotate does NOT fire when the `when` condition is false."""
        store.update_property("game", "phase", "day")
        effect = EffectConfig(
            operator="rotate",
            target="game.active_role",
            sequence="game.role_order",
            when=PreconditionConfig(
                operator="check",
                left="game.phase",
                op="==",
                right="night",
            ),
        )
        execute(effect, store, event_log, ctx, tick=1)
        # Should NOT have rotated
        assert store.get("game")["active_role"] == "werewolf"

    def test_rotate_with_when_and_skip(self, store, event_log, ctx):
        """Rotate fires with both when and skip active."""
        store.update_property("game", "phase", "night")
        effect = EffectConfig(
            operator="rotate",
            target="game.active_role",
            sequence="game.role_order",
            skip="game.role_order",  # skip all -> no advance
            when=PreconditionConfig(
                operator="check",
                left="game.phase",
                op="==",
                right="night",
            ),
        )
        # when=True but all skipped, so no change
        execute(effect, store, event_log, ctx, tick=1)
        assert store.get("game")["active_role"] == "werewolf"


# ---------------------------------------------------------------------------
# 2. max_by with all zeros (tie)
# ---------------------------------------------------------------------------


class TestMaxByAllZeros:
    """What does max_by return when all entities have the same value?"""

    @pytest.fixture()
    def store(self) -> StateStore:
        s = StateStore()
        s.add(Entity(id="p1", type="player", _data={"score": 0}))
        s.add(Entity(id="p2", type="player", _data={"score": 0}))
        s.add(Entity(id="p3", type="player", _data={"score": 0}))
        return s

    @pytest.fixture()
    def ctx(self) -> dict:
        return {"agent_id": "", "action_params": {}, "tick": 1}

    def test_all_zeros_returns_empty(self, store, ctx):
        """Tied max_by returns empty string (no unique winner)."""
        result = _call_max_by("type=player, property=score", store, ctx)
        assert result == ""

    def test_all_same_nonzero_returns_empty(self, store, ctx):
        """All tied at same non-zero value also returns empty."""
        store.update_property("p1", "score", 5)
        store.update_property("p2", "score", 5)
        store.update_property("p3", "score", 5)
        result = _call_max_by("type=player, property=score", store, ctx)
        assert result == ""

    def test_two_tied_one_lower(self, store, ctx):
        """Two tied at max, one lower -- still a tie, returns empty."""
        store.update_property("p1", "score", 10)
        store.update_property("p2", "score", 10)
        store.update_property("p3", "score", 5)
        result = _call_max_by("type=player, property=score", store, ctx)
        assert result == ""

    def test_one_winner_among_zeros(self, store, ctx):
        """Single unique max returns that entity's id."""
        store.update_property("p2", "score", 1)
        result = _call_max_by("type=player, property=score", store, ctx)
        assert result == "p2"


# ---------------------------------------------------------------------------
# 3. max_by with no matching entities
# ---------------------------------------------------------------------------


class TestMaxByNoMatch:
    """What does max_by return when WHERE matches nothing?"""

    @pytest.fixture()
    def store(self) -> StateStore:
        s = StateStore()
        s.add(Entity(id="p1", type="player", _data={"score": 10, "alive": "true"}))
        s.add(Entity(id="p2", type="player", _data={"score": 20, "alive": "true"}))
        return s

    @pytest.fixture()
    def ctx(self) -> dict:
        return {"agent_id": "", "action_params": {}, "tick": 1}

    def test_no_matching_type_returns_empty(self, store, ctx):
        """No entities of requested type -> empty string."""
        result = _call_max_by("type=nonexistent, property=score", store, ctx)
        assert result == ""

    def test_where_matches_nothing_returns_empty(self, store, ctx):
        """WHERE clause eliminates all entities -> empty string."""
        result = _call_max_by(
            "type=player, property=score, where=alive == false",
            store,
            ctx,
        )
        assert result == ""

    def test_all_none_values_returns_empty(self, store, ctx):
        """All entities have None for the property -> empty string."""
        store.update_property("p1", "score", None)
        store.update_property("p2", "score", None)
        result = _call_max_by("type=player, property=score", store, ctx)
        assert result == ""

    def test_missing_property_returns_empty(self, store, ctx):
        """Property doesn't exist on any entity -> empty string."""
        result = _call_max_by("type=player, property=nonexistent_prop", store, ctx)
        assert result == ""


# ---------------------------------------------------------------------------
# 4. count WHERE with nested entity ref
# ---------------------------------------------------------------------------


class TestCountWhereEntityRef:
    """count(type=agent, where=role == night_state.active_role) -- entity property ref in RHS."""

    @pytest.fixture()
    def store(self) -> StateStore:
        s = StateStore()
        # Game state entity that holds the active role
        s.add(
            Entity(
                id="night_state",
                type="game_state",
                _data={"active_role": "werewolf"},
            )
        )
        # Agents with roles
        s.add(Entity(id="alice", type="agent", _data={"role": "werewolf"}))
        s.add(Entity(id="bob", type="agent", _data={"role": "seer"}))
        s.add(Entity(id="carol", type="agent", _data={"role": "werewolf"}))
        s.add(Entity(id="dave", type="agent", _data={"role": "villager"}))
        return s

    @pytest.fixture()
    def ctx(self) -> dict:
        return {"agent_id": "", "action_params": {}, "tick": 1}

    def test_count_where_entity_ref_resolves(self, store, ctx):
        """WHERE with entity.property ref resolves correctly."""
        result = count(
            store,
            "agent",
            where="role == night_state.active_role",
            ctx=ctx,
        )
        assert result == 2  # alice and carol are werewolves

    def test_count_where_entity_ref_after_change(self, store, ctx):
        """After changing active_role, count reflects the new value."""
        store.update_property("night_state", "active_role", "seer")
        result = count(
            store,
            "agent",
            where="role == night_state.active_role",
            ctx=ctx,
        )
        assert result == 1  # only bob is seer

    def test_count_where_entity_ref_no_match(self, store, ctx):
        """Entity ref resolves to a value no agent has."""
        store.update_property("night_state", "active_role", "hunter")
        result = count(
            store,
            "agent",
            where="role == night_state.active_role",
            ctx=ctx,
        )
        assert result == 0

    def test_count_via_path_resolver_in_precondition(self, store, ctx):
        """count() used in a precondition expression with entity ref WHERE."""
        result = resolve(
            "count(type=agent, where=role == night_state.active_role)",
            store,
            ctx,
        )
        assert result == 2


# ---------------------------------------------------------------------------
# 5. Cascading consequences: max_by in trigger, rotate in effects
# ---------------------------------------------------------------------------


class TestCascadingConsequenceMaxByRotate:
    """A consequence that uses max_by in trigger, then rotate in effects."""

    @pytest.fixture()
    def store(self) -> StateStore:
        s = StateStore()
        # Game state with round tracking
        s.add(
            Entity(
                id="game",
                type="game_state",
                _data={
                    "phase": "voting",
                    "phase_order": ["voting", "action", "night"],
                },
            )
        )
        # Players with vote counts
        s.add(Entity(id="p1", type="player", _data={"votes": 0, "eliminated": "false"}))
        s.add(Entity(id="p2", type="player", _data={"votes": 3, "eliminated": "false"}))
        s.add(Entity(id="p3", type="player", _data={"votes": 1, "eliminated": "false"}))
        return s

    @pytest.fixture()
    def event_log(self) -> EventLog:
        return EventLog()

    def test_max_by_trigger_fires_rotate_effect(self, store, event_log):
        """Consequence: when max_by(votes) != "" (unique winner), rotate phase."""
        consequence = ConsequenceConfig(
            trigger=[
                # Check that there IS a unique vote leader
                PreconditionConfig(
                    operator="check",
                    left="max_by(type=player, property=votes)",
                    op="!=",
                    right="",
                ),
            ],
            effects=[
                EffectConfig(
                    operator="rotate",
                    target="game.phase",
                    sequence="game.phase_order",
                ),
            ],
        )
        config = _make_config({"vote_resolve": consequence})
        scanner = ConsequenceScanner(config, store, event_log)

        # p2 has unique max votes (3), so trigger fires
        triggered, _dm = scanner.scan(tick=1)
        assert "vote_resolve" in triggered
        assert store.get("game")["phase"] == "action"

    def test_max_by_tie_does_not_trigger(self, store, event_log):
        """When votes are tied, max_by returns '' and trigger does not fire."""
        store.update_property("p1", "votes", 3)  # tie with p2 at 3
        consequence = ConsequenceConfig(
            trigger=[
                PreconditionConfig(
                    operator="check",
                    left="max_by(type=player, property=votes)",
                    op="!=",
                    right="",
                ),
            ],
            effects=[
                EffectConfig(
                    operator="rotate",
                    target="game.phase",
                    sequence="game.phase_order",
                ),
            ],
        )
        config = _make_config({"vote_resolve": consequence})
        scanner = ConsequenceScanner(config, store, event_log)

        triggered, _dm = scanner.scan(tick=1)
        assert triggered == []
        # Phase unchanged
        assert store.get("game")["phase"] == "voting"


# ---------------------------------------------------------------------------
# 6. `when` clause with $entity reference (inside consequence)
# ---------------------------------------------------------------------------


class TestWhenWithEntityRef:
    """An effect inside a consequence that uses when: { check: $entity.role == werewolf }."""

    @pytest.fixture()
    def store(self) -> StateStore:
        s = StateStore()
        s.add(Entity(id="alice", type="agent", _data={"role": "werewolf", "hp": 10}))
        s.add(Entity(id="bob", type="agent", _data={"role": "villager", "hp": 10}))
        s.add(Entity(id="carol", type="agent", _data={"role": "werewolf", "hp": 10}))
        return s

    @pytest.fixture()
    def event_log(self) -> EventLog:
        return EventLog()

    def test_for_each_with_when_filters_by_role(self, store, event_log):
        """for_each all agents, but 'when' only applies effect to werewolves."""
        effect = EffectConfig(
            operator="for_each",
            match={"type": "agent"},
            sub_effects=[
                EffectConfig(
                    operator="decrement",
                    target="$entity.hp",
                    by=5,
                    when=PreconditionConfig(
                        operator="check",
                        left="$entity.role",
                        op="==",
                        right="werewolf",
                    ),
                ),
            ],
        )
        ctx = {"agent_id": "", "action_params": {}, "tick": 1}
        execute(effect, store, event_log, ctx, tick=1)

        # Werewolves lost HP
        assert store.get("alice")["hp"] == 5
        assert store.get("carol")["hp"] == 5
        # Villager unaffected
        assert store.get("bob")["hp"] == 10

    def test_when_with_entity_ref_in_consequence(self, store, event_log):
        """Consequence with $entity trigger + when clause on effect.

        Trigger: $entity is an agent (fires per entity).
        Effect: decrement HP only when role == werewolf.
        """
        consequence = ConsequenceConfig(
            trigger=[
                PreconditionConfig(
                    operator="check",
                    left="$entity.type",
                    op="==",
                    right="agent",
                ),
            ],
            effects=[
                EffectConfig(
                    operator="decrement",
                    target="$entity.hp",
                    by=3,
                    when=PreconditionConfig(
                        operator="check",
                        left="$entity.role",
                        op="==",
                        right="werewolf",
                    ),
                ),
            ],
            frequency="every_tick",
        )
        config = _make_config({"sun_damage": consequence})
        scanner = ConsequenceScanner(config, store, event_log)

        triggered, _dm = scanner.scan(tick=1)
        assert "sun_damage" in triggered
        # Only werewolves take damage
        assert store.get("alice")["hp"] == 7
        assert store.get("carol")["hp"] == 7
        assert store.get("bob")["hp"] == 10

    def test_when_false_for_all_entities(self, store, event_log):
        """When condition is false for ALL entities -- effect never fires."""
        effect = EffectConfig(
            operator="for_each",
            match={"type": "agent"},
            sub_effects=[
                EffectConfig(
                    operator="set",
                    target="$entity.hp",
                    value=0,
                    when=PreconditionConfig(
                        operator="check",
                        left="$entity.role",
                        op="==",
                        right="dragon",  # nobody is a dragon
                    ),
                ),
            ],
        )
        ctx = {"agent_id": "", "action_params": {}, "tick": 1}
        execute(effect, store, event_log, ctx, tick=1)

        # Nobody's HP changed
        assert store.get("alice")["hp"] == 10
        assert store.get("bob")["hp"] == 10
        assert store.get("carol")["hp"] == 10


# ---------------------------------------------------------------------------
# Additional edge cases
# ---------------------------------------------------------------------------


class TestMaxByWithWhere:
    """max_by with WHERE clause edge cases."""

    @pytest.fixture()
    def store(self) -> StateStore:
        s = StateStore()
        s.add(Entity(id="p1", type="player", _data={"score": 10, "alive": "true"}))
        s.add(Entity(id="p2", type="player", _data={"score": 20, "alive": "false"}))
        s.add(Entity(id="p3", type="player", _data={"score": 15, "alive": "true"}))
        return s

    @pytest.fixture()
    def ctx(self) -> dict:
        return {"agent_id": "", "action_params": {}, "tick": 1}

    def test_max_by_with_where_filters_correctly(self, store, ctx):
        """max_by respects WHERE clause -- dead player excluded."""
        result = _call_max_by(
            "type=player, property=score, where=alive == true",
            store,
            ctx,
        )
        # p2 has highest score (20) but alive==false, so p3 (15) wins
        assert result == "p3"

    def test_max_by_single_alive_entity(self, store, ctx):
        """Only one matching entity -> that entity wins (no tie)."""
        store.update_property("p3", "alive", "false")
        result = _call_max_by(
            "type=player, property=score, where=alive == true",
            store,
            ctx,
        )
        assert result == "p1"


class TestCountWhereCompound:
    """count with compound WHERE (AND) and entity refs."""

    @pytest.fixture()
    def store(self) -> StateStore:
        s = StateStore()
        s.add(
            Entity(
                id="game",
                type="game_state",
                _data={"target_location": "town", "target_role": "guard"},
            )
        )
        s.add(Entity(id="a1", type="agent", _data={"location": "town", "role": "guard"}))
        s.add(Entity(id="a2", type="agent", _data={"location": "town", "role": "thief"}))
        s.add(Entity(id="a3", type="agent", _data={"location": "forest", "role": "guard"}))
        s.add(Entity(id="a4", type="agent", _data={"location": "town", "role": "guard"}))
        return s

    @pytest.fixture()
    def ctx(self) -> dict:
        return {"agent_id": "", "action_params": {}, "tick": 1}

    def test_count_compound_where_with_entity_refs(self, store, ctx):
        """count with AND conditions, both sides referencing entity properties."""
        result = count(
            store,
            "agent",
            where="location == game.target_location AND role == game.target_role",
            ctx=ctx,
        )
        # a1 and a4 are guards in town
        assert result == 2

    def test_count_compound_where_no_match(self, store, ctx):
        """Compound WHERE where one condition matches but AND fails."""
        store.update_property("game", "target_role", "wizard")
        result = count(
            store,
            "agent",
            where="location == game.target_location AND role == game.target_role",
            ctx=ctx,
        )
        assert result == 0
