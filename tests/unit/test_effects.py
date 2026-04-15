"""Tests for DSL effect executor."""

from __future__ import annotations

from worldseed.dsl.effects import execute
from worldseed.engine.event_log import EventLog
from worldseed.engine.state_store import StateStore
from worldseed.models import Entity
from worldseed.models.config_schema import EffectConfig


def _store_with_chen() -> StateStore:
    store = StateStore()
    store.add(
        Entity(
            id="old_chen",
            type="agent",
            _data={"location": "storage_room", "private_stash": 0},
        )
    )
    store.add(
        Entity(
            id="food_supply",
            type="resource",
            _data={"quantity": 20},
        )
    )
    return store


def _ctx(**params: object) -> dict:  # type: ignore[type-arg]
    return {"agent_id": "old_chen", "action_params": params}


class TestSet:
    def test_set_property(self) -> None:
        store = _store_with_chen()
        effect = EffectConfig(
            operator="set",
            target="$agent.location",
            value="hallway",
        )
        execute(effect, store, EventLog(), _ctx(), tick=1)
        assert store.get("old_chen")["location"] == "hallway"  # type: ignore[union-attr]

    def test_set_creates_new_property(self) -> None:
        store = _store_with_chen()
        effect = EffectConfig(
            operator="set",
            target="$agent.anxiety",
            value="high",
        )
        execute(effect, store, EventLog(), _ctx(), tick=1)
        assert store.get("old_chen")["anxiety"] == "high"  # type: ignore[union-attr]

    def test_set_changes_property(self) -> None:
        store = _store_with_chen()
        effect = EffectConfig(
            operator="set",
            target="$agent.location",
            value="hallway",
        )
        execute(effect, store, EventLog(), _ctx(), tick=5)
        chen = store.get("old_chen")
        assert chen is not None
        assert chen["location"] == "hallway"

    def test_set_with_param_ref(self) -> None:
        store = _store_with_chen()
        effect = EffectConfig(
            operator="set",
            target="$agent.location",
            value="$to",
        )
        execute(
            effect,
            store,
            EventLog(),
            _ctx(to="hallway"),
            tick=1,
        )
        assert store.get("old_chen")["location"] == "hallway"  # type: ignore[union-attr]


class TestIncrement:
    def test_increment(self) -> None:
        store = _store_with_chen()
        effect = EffectConfig(
            operator="increment",
            target="$agent.private_stash",
            by=3,
        )
        execute(effect, store, EventLog(), _ctx(), tick=1)
        assert store.get("old_chen")["private_stash"] == 3  # type: ignore[union-attr]

    def test_increment_null_treats_as_zero(self) -> None:
        store = _store_with_chen()
        effect = EffectConfig(
            operator="increment",
            target="$agent.new_prop",
            by=5,
        )
        execute(effect, store, EventLog(), _ctx(), tick=1)
        assert store.get("old_chen")["new_prop"] == 5  # type: ignore[union-attr]

    def test_increment_with_param(self) -> None:
        store = _store_with_chen()
        effect = EffectConfig(
            operator="increment",
            target="$agent.private_stash",
            by="$amount",
        )
        execute(
            effect,
            store,
            EventLog(),
            _ctx(amount=7),
            tick=1,
        )
        assert store.get("old_chen")["private_stash"] == 7  # type: ignore[union-attr]


class TestDecrement:
    def test_decrement(self) -> None:
        store = _store_with_chen()
        effect = EffectConfig(
            operator="decrement",
            target="food_supply.quantity",
            by=3,
        )
        execute(effect, store, EventLog(), _ctx(), tick=1)
        assert store.get("food_supply")["quantity"] == 17  # type: ignore[union-attr]

    def test_decrement_null_treats_as_zero(self) -> None:
        store = _store_with_chen()
        effect = EffectConfig(
            operator="decrement",
            target="$agent.missing",
            by=5,
        )
        execute(effect, store, EventLog(), _ctx(), tick=1)
        assert store.get("old_chen")["missing"] == -5.0  # type: ignore[union-attr]

    def test_decrement_with_min_clamp(self) -> None:
        store = _store_with_chen()
        # food_supply starts at 20, decrement by 25 with min=0
        effect = EffectConfig(
            operator="decrement",
            target="food_supply.quantity",
            by=25,
            min=0,
        )
        execute(effect, store, EventLog(), _ctx(), tick=1)
        assert store.get("food_supply")["quantity"] == 0.0  # type: ignore[union-attr]

    def test_increment_with_max_clamp(self) -> None:
        store = _store_with_chen()
        # food_supply starts at 20, increment by 100 with max=50
        effect = EffectConfig(
            operator="increment",
            target="food_supply.quantity",
            by=100,
            max=50,
        )
        execute(effect, store, EventLog(), _ctx(), tick=1)
        assert store.get("food_supply")["quantity"] == 50.0  # type: ignore[union-attr]

    def test_decrement_without_min_allows_negative(self) -> None:
        store = _store_with_chen()
        # No min — should go negative as before
        effect = EffectConfig(
            operator="decrement",
            target="food_supply.quantity",
            by=25,
        )
        execute(effect, store, EventLog(), _ctx(), tick=1)
        assert store.get("food_supply")["quantity"] == -5  # type: ignore[union-attr]

    def test_clamp_min_and_max_together(self) -> None:
        store = _store_with_chen()
        # food_supply starts at 20, increment by 100 with min=0, max=50
        effect = EffectConfig(
            operator="increment",
            target="food_supply.quantity",
            by=100,
            min=0,
            max=50,
        )
        execute(effect, store, EventLog(), _ctx(), tick=1)
        assert store.get("food_supply")["quantity"] == 50  # type: ignore[union-attr]
        # Now decrement by 100 — should clamp to min=0
        effect2 = EffectConfig(
            operator="decrement",
            target="food_supply.quantity",
            by=100,
            min=0,
            max=50,
        )
        execute(effect2, store, EventLog(), _ctx(), tick=2)
        assert store.get("food_supply")["quantity"] == 0  # type: ignore[union-attr]


class TestCreateRemoveEntity:
    def test_create_entity(self) -> None:
        store = _store_with_chen()
        effect = EffectConfig(
            operator="create_entity",
            id="weapon",
            type="object",
            properties={"damage": "low"},
        )
        execute(effect, store, EventLog(), _ctx(), tick=1)
        weapon = store.get("weapon")
        assert weapon is not None
        assert weapon.type == "object"
        assert weapon["damage"] == "low"

    def test_remove_entity(self) -> None:
        store = _store_with_chen()
        effect = EffectConfig(operator="remove_entity", target="food_supply")
        execute(effect, store, EventLog(), _ctx(), tick=1)
        assert store.get("food_supply") is None


class TestRelationships:
    def test_add_relationship(self) -> None:
        store = _store_with_chen()
        effect = EffectConfig(
            operator="add_relationship",
            from_entity="old_chen",
            type="trusts",
            to="food_supply",
            value=50,
        )
        execute(effect, store, EventLog(), _ctx(), tick=1)
        chen = store.get("old_chen")
        assert chen is not None
        assert chen["trusts"] == {"food_supply": 50}

    def test_add_relationship_upsert(self) -> None:
        store = _store_with_chen()
        effect1 = EffectConfig(
            operator="add_relationship",
            from_entity="old_chen",
            type="trusts",
            to="food_supply",
            value=50,
        )
        effect2 = EffectConfig(
            operator="add_relationship",
            from_entity="old_chen",
            type="trusts",
            to="food_supply",
            value=80,
        )
        execute(effect1, store, EventLog(), _ctx(), tick=1)
        execute(effect2, store, EventLog(), _ctx(), tick=2)
        chen = store.get("old_chen")
        assert chen is not None
        assert chen["trusts"] == {"food_supply": 80}


class TestEmitEvent:
    def test_emit_event(self) -> None:
        store = _store_with_chen()
        event_log = EventLog()
        effect = EffectConfig(
            operator="emit_event",
            type="take",
            detail="$agent took food",
            ttl=1,
            scope="same_location",
        )
        execute(effect, store, event_log, _ctx(), tick=5)
        events = event_log.get_events()
        assert len(events) == 1
        assert events[0].type == "take"
        assert events[0].detail == "old_chen took food"
        assert events[0].source == "old_chen"
        assert events[0].tick == 5


class TestEmitEventInterpolation:
    def test_multiple_params_interpolated(self) -> None:
        store = _store_with_chen()
        event_log = EventLog()
        effect = EffectConfig(
            operator="emit_event",
            type="take",
            detail="$agent took $amount from $target",
            ttl=1,
            scope="same_location",
        )
        execute(
            effect,
            store,
            event_log,
            _ctx(target="food_supply", amount=3),
            tick=1,
        )
        events = event_log.get_events()
        assert events[0].detail == "old_chen took 3 from food_supply"


class TestEmitEventTarget:
    def test_emit_event_with_target(self) -> None:
        store = _store_with_chen()
        event_log = EventLog()
        effect = EffectConfig(
            operator="emit_event",
            type="say",
            detail="$agent says hello to $to",
            ttl=1,
            scope="same_location",
            event_target="$to",
        )
        execute(
            effect,
            store,
            event_log,
            _ctx(to="xiao_li"),
            tick=1,
        )
        events = event_log.get_events()
        assert len(events) == 1
        assert events[0].target == "xiao_li"

    def test_emit_event_without_target(self) -> None:
        store = _store_with_chen()
        event_log = EventLog()
        effect = EffectConfig(
            operator="emit_event",
            type="say",
            detail="$agent says hello",
            ttl=1,
            scope="same_location",
        )
        execute(effect, store, event_log, _ctx(), tick=1)
        events = event_log.get_events()
        assert len(events) == 1
        assert events[0].target is None
