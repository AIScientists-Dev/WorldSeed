"""Tests for DSL precondition evaluator."""

from __future__ import annotations

from worldseed.dsl.preconditions import evaluate
from worldseed.engine.state_store import StateStore
from worldseed.models import Entity
from worldseed.models.config_schema import PreconditionConfig


def _bunker_store() -> StateStore:
    store = StateStore()
    store.add(
        Entity(
            id="sleeping_quarters",
            type="space",
            _data={"connects_to": ["hallway"]},
        )
    )
    store.add(
        Entity(
            id="hallway",
            type="space",
            _data={
                "connects_to": ["storage_room", "sleeping_quarters"],
            },
        )
    )
    store.add(
        Entity(
            id="storage_room",
            type="space",
            _data={"connects_to": ["hallway"]},
        )
    )
    store.add(
        Entity(
            id="food_supply",
            type="resource",
            _data={
                "quantity": 20,
                "located_in": ["storage_room"],
            },
        )
    )
    store.add(
        Entity(
            id="old_chen",
            type="agent",
            _data={"location": "sleeping_quarters", "private_stash": 0},
        )
    )
    return store


def _ctx(**params: object) -> dict:  # type: ignore[type-arg]
    return {"agent_id": "old_chen", "action_params": params}


class TestCheck:
    def test_numeric_gte_true(self) -> None:
        store = _bunker_store()
        p = PreconditionConfig(operator="check", left=20, op=">=", right=3)
        assert evaluate(p, store, _ctx()) is True

    def test_numeric_gte_false(self) -> None:
        store = _bunker_store()
        p = PreconditionConfig(operator="check", left=2, op=">=", right=3)
        assert evaluate(p, store, _ctx()) is False

    def test_string_eq(self) -> None:
        store = _bunker_store()
        p = PreconditionConfig(operator="check", left="x", op="==", right="x")
        assert evaluate(p, store, _ctx()) is True

    def test_string_ne(self) -> None:
        store = _bunker_store()
        p = PreconditionConfig(operator="check", left="a", op="!=", right="b")
        assert evaluate(p, store, _ctx()) is True

    def test_in_list(self) -> None:
        store = _bunker_store()
        p = PreconditionConfig(
            operator="check",
            left="hallway",
            op="in",
            right=["hallway", "entrance"],
        )
        assert evaluate(p, store, _ctx()) is True

    def test_in_list_false(self) -> None:
        store = _bunker_store()
        p = PreconditionConfig(
            operator="check",
            left="storage",
            op="in",
            right=["hallway", "entrance"],
        )
        assert evaluate(p, store, _ctx()) is False

    def test_contains(self) -> None:
        store = _bunker_store()
        p = PreconditionConfig(
            operator="check",
            left=["storage_room"],
            op="contains",
            right="storage_room",
        )
        assert evaluate(p, store, _ctx()) is True

    def test_null_comparison_returns_false(self) -> None:
        store = _bunker_store()
        p = PreconditionConfig(operator="check", left=None, op=">", right=5)
        assert evaluate(p, store, _ctx()) is False

    def test_null_eq_null(self) -> None:
        store = _bunker_store()
        p = PreconditionConfig(operator="check", left=None, op="==", right=None)
        assert evaluate(p, store, _ctx()) is True


class TestMovePrecondition:
    def test_valid_move(self) -> None:
        """$to in relationships_of($agent.location, connects_to)"""
        store = _bunker_store()
        p = PreconditionConfig(
            operator="check",
            left="$to",
            op="in",
            right="relationships_of($agent.location, type=connects_to)",
        )
        assert evaluate(p, store, _ctx(to="hallway")) is True

    def test_invalid_move(self) -> None:
        store = _bunker_store()
        p = PreconditionConfig(
            operator="check",
            left="$to",
            op="in",
            right="relationships_of($agent.location, type=connects_to)",
        )
        assert evaluate(p, store, _ctx(to="storage_room")) is False


class TestExists:
    def test_property_exists(self) -> None:
        """exists: property path resolves to non-None."""
        store = _bunker_store()
        p = PreconditionConfig(
            operator="exists",
            expression="$agent.location",
        )
        assert evaluate(p, store, _ctx()) is True

    def test_property_not_exists(self) -> None:
        """exists: property path resolves to None."""
        store = _bunker_store()
        p = PreconditionConfig(
            operator="exists",
            expression="$agent.nonexistent",
        )
        assert evaluate(p, store, _ctx()) is False

    def test_relationship_exists(self) -> None:
        """exists: relationships_of returns non-empty list."""
        store = _bunker_store()
        p = PreconditionConfig(
            operator="exists",
            expression="relationships_of($agent.location, type=connects_to)",
        )
        assert evaluate(p, store, _ctx()) is True

    def test_relationship_not_exists(self) -> None:
        """exists: relationships_of returns empty list."""
        store = _bunker_store()
        p = PreconditionConfig(
            operator="exists",
            expression="relationships_of($agent, type=owns)",
        )
        assert evaluate(p, store, _ctx()) is False

    def test_no_expression(self) -> None:
        """exists: no expression field -> False."""
        store = _bunker_store()
        p = PreconditionConfig(operator="exists")
        assert evaluate(p, store, _ctx()) is False

    def test_not_exists_combo(self) -> None:
        """not + exists: property missing -> True."""
        store = _bunker_store()
        inner = PreconditionConfig(
            operator="exists",
            expression="$agent.nonexistent",
        )
        p = PreconditionConfig(operator="not", condition=inner)
        assert evaluate(p, store, _ctx()) is True

    def test_entity_ref_exists(self) -> None:
        """exists: bare entity id resolves to string (truthy)."""
        store = _bunker_store()
        p = PreconditionConfig(
            operator="exists",
            expression="food_supply.quantity",
        )
        assert evaluate(p, store, _ctx()) is True

    def test_zero_is_truthy(self) -> None:
        """exists: zero value is falsy (property exists but value is 0)."""
        store = _bunker_store()
        p = PreconditionConfig(
            operator="exists",
            expression="$agent.private_stash",
        )
        # 0 is falsy — exists checks truthiness, not just None
        assert evaluate(p, store, _ctx()) is False


class TestSum:
    def test_sum_all_resources(self) -> None:
        """sum(type=resource, property=quantity) across all resources."""
        store = _bunker_store()
        p = PreconditionConfig(
            operator="check",
            left="sum(type=resource, property=quantity)",
            op="==",
            right=20,
        )
        assert evaluate(p, store, _ctx()) is True

    def test_sum_multiple_resources(self) -> None:
        """sum works across multiple entities of same type."""
        store = _bunker_store()
        # Add a second resource
        store.add(
            Entity(
                id="water_supply",
                type="resource",
                _data={"quantity": 15},
            )
        )
        p = PreconditionConfig(
            operator="check",
            left="sum(type=resource, property=quantity)",
            op="==",
            right=35,  # 20 + 15
        )
        assert evaluate(p, store, _ctx()) is True

    def test_sum_no_match(self) -> None:
        """sum of nonexistent type -> 0."""
        store = _bunker_store()
        p = PreconditionConfig(
            operator="check",
            left="sum(type=weapon, property=damage)",
            op="==",
            right=0,
        )
        assert evaluate(p, store, _ctx()) is True


class TestEvent:
    def test_event_exists(self) -> None:
        """event(type=X) returns non-empty list when events exist."""
        from worldseed.engine.event_log import EventLog
        from worldseed.models.event import Event

        store = _bunker_store()
        event_log = EventLog()
        event_log.append(
            Event(
                tick=1,
                type="confrontation",
                source="old_chen",
                detail="chen confronted li",
                ttl=5,
                scope="global",
            )
        )
        ctx = {
            "agent_id": "old_chen",
            "action_params": {},
            "tick": 2,
            "event_log": event_log,
        }
        p = PreconditionConfig(
            operator="exists",
            expression="event(type=confrontation)",
        )
        assert evaluate(p, store, ctx) is True

    def test_event_not_exists(self) -> None:
        """event(type=X) returns empty list when no matching events."""
        from worldseed.engine.event_log import EventLog

        store = _bunker_store()
        event_log = EventLog()
        ctx = {
            "agent_id": "old_chen",
            "action_params": {},
            "tick": 1,
            "event_log": event_log,
        }
        p = PreconditionConfig(
            operator="exists",
            expression="event(type=confrontation)",
        )
        assert evaluate(p, store, ctx) is False

    def test_event_no_event_log(self) -> None:
        """event() without event_log in ctx -> empty (no crash)."""
        store = _bunker_store()
        p = PreconditionConfig(
            operator="exists",
            expression="event(type=confrontation)",
        )
        assert evaluate(p, store, _ctx()) is False


class TestCompound:
    def test_not(self) -> None:
        store = _bunker_store()
        inner = PreconditionConfig(operator="check", left=1, op=">", right=10)
        p = PreconditionConfig(operator="not", condition=inner)
        assert evaluate(p, store, _ctx()) is True

    def test_all_true(self) -> None:
        store = _bunker_store()
        c1 = PreconditionConfig(operator="check", left=5, op=">", right=3)
        c2 = PreconditionConfig(operator="check", left=10, op="==", right=10)
        p = PreconditionConfig(operator="all", conditions=[c1, c2])
        assert evaluate(p, store, _ctx()) is True

    def test_all_one_false(self) -> None:
        store = _bunker_store()
        c1 = PreconditionConfig(operator="check", left=5, op=">", right=3)
        c2 = PreconditionConfig(operator="check", left=1, op=">", right=10)
        p = PreconditionConfig(operator="all", conditions=[c1, c2])
        assert evaluate(p, store, _ctx()) is False

    def test_any(self) -> None:
        store = _bunker_store()
        c1 = PreconditionConfig(operator="check", left=1, op=">", right=10)
        c2 = PreconditionConfig(operator="check", left=5, op="<", right=10)
        p = PreconditionConfig(operator="any", conditions=[c1, c2])
        assert evaluate(p, store, _ctx()) is True
