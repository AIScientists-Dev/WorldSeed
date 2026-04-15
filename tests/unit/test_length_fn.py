"""Stress tests for length() DSL function."""

import pytest

from worldseed.dsl.path_resolver import resolve
from worldseed.dsl.preconditions import evaluate
from worldseed.engine.state_store import StateStore
from worldseed.models.config_schema import PreconditionConfig
from worldseed.models.entity import Entity


@pytest.fixture()
def store() -> StateStore:
    s = StateStore()
    s.add(Entity(id="deck", type="card", _data={"cards": ["A", "K", "Q", "J"]}))
    s.add(
        Entity(
            id="p",
            type="agent",
            _data={
                "hand": [],
                "name": "alice",
                "empty": None,
                "data": {"a": 1, "b": 2},
            },
        )
    )
    return s


@pytest.fixture()
def ctx() -> dict:
    return {"agent_id": "p", "action_params": {}, "tick": 1}


class TestLengthBasic:
    def test_list(self, store, ctx):
        assert resolve("length(deck.cards)", store, ctx) == 4

    def test_empty_list(self, store, ctx):
        assert resolve("length(p.hand)", store, ctx) == 0

    def test_string(self, store, ctx):
        assert resolve("length(p.name)", store, ctx) == 5

    def test_dict(self, store, ctx):
        assert resolve("length(p.data)", store, ctx) == 2

    def test_none(self, store, ctx):
        assert resolve("length(p.empty)", store, ctx) == 0

    def test_nonexistent(self, store, ctx):
        assert resolve("length(ghost.items)", store, ctx) == 0


class TestLengthInArithmetic:
    def test_length_plus_number(self, store, ctx):
        assert resolve("length(deck.cards) + 1", store, ctx) == 5.0

    def test_length_in_multiplication(self, store, ctx):
        assert resolve("2 * length(deck.cards)", store, ctx) == 8.0


class TestLengthInPrecondition:
    def test_hand_empty(self, store, ctx):
        p = PreconditionConfig(
            operator="check",
            left="length(p.hand)",
            op="==",
            right=0,
        )
        assert evaluate(p, store, ctx) is True

    def test_deck_has_cards(self, store, ctx):
        p = PreconditionConfig(
            operator="check",
            left="length(deck.cards)",
            op=">",
            right=0,
        )
        assert evaluate(p, store, ctx) is True

    def test_hand_has_2_cards(self, store, ctx):
        store.update_property("p", "hand", ["A♠", "K♥"])
        p = PreconditionConfig(
            operator="check",
            left="length($agent.hand)",
            op="==",
            right=2,
        )
        assert evaluate(p, store, ctx) is True
