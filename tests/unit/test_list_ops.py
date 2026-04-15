"""Stress tests for list_append, list_remove, list_pop_random."""

import pytest

from worldseed.dsl.effects import execute
from worldseed.engine.event_log import EventLog
from worldseed.engine.state_store import StateStore
from worldseed.models.config_schema import EffectConfig
from worldseed.models.entity import Entity


@pytest.fixture()
def store() -> StateStore:
    s = StateStore()
    s.add(Entity(id="player", type="agent", _data={"hand": ["A♠", "K♥"], "inventory": []}))
    s.add(
        Entity(
            id="deck",
            type="card_deck",
            _data={"cards": ["Q♦", "J♣", "10♠", "9♥", "8♦"]},
        )
    )
    s.add(Entity(id="empty", type="test", _data={"items": None}))
    s.add(Entity(id="not_list", type="test", _data={"value": 42}))
    return s


@pytest.fixture()
def event_log() -> EventLog:
    return EventLog()


@pytest.fixture()
def ctx() -> dict:
    return {"agent_id": "player", "action_params": {}, "tick": 1}


class TestListAppend:
    def test_append_to_existing_list(self, store, event_log, ctx):
        effect = EffectConfig(operator="list_append", target="player.hand", value="2♣")
        execute(effect, store, event_log, ctx, tick=1)
        assert store.get("player")["hand"] == ["A♠", "K♥", "2♣"]

    def test_append_to_empty_list(self, store, event_log, ctx):
        effect = EffectConfig(operator="list_append", target="player.inventory", value="sword")
        execute(effect, store, event_log, ctx, tick=1)
        assert store.get("player")["inventory"] == ["sword"]

    def test_append_to_none_creates_list(self, store, event_log, ctx):
        effect = EffectConfig(operator="list_append", target="empty.items", value="first")
        execute(effect, store, event_log, ctx, tick=1)
        assert store.get("empty")["items"] == ["first"]

    def test_append_duplicate_allowed(self, store, event_log, ctx):
        effect = EffectConfig(operator="list_append", target="player.hand", value="A♠")
        execute(effect, store, event_log, ctx, tick=1)
        assert store.get("player")["hand"] == ["A♠", "K♥", "A♠"]

    def test_append_to_non_list_warns(self, store, event_log, ctx):
        """Appending to a non-list property should warn and do nothing."""
        effect = EffectConfig(operator="list_append", target="not_list.value", value="x")
        execute(effect, store, event_log, ctx, tick=1)
        assert store.get("not_list")["value"] == 42  # unchanged

    def test_append_with_param_resolution(self, store, event_log):
        ctx = {"agent_id": "player", "action_params": {"card": "3♦"}, "tick": 1}
        effect = EffectConfig(operator="list_append", target="$agent.hand", value="$card")
        execute(effect, store, event_log, ctx, tick=1)
        assert "3♦" in store.get("player")["hand"]

    def test_append_multiple_times(self, store, event_log, ctx):
        for card in ["2♣", "3♦", "4♠"]:
            effect = EffectConfig(operator="list_append", target="player.hand", value=card)
            execute(effect, store, event_log, ctx, tick=1)
        hand = store.get("player")["hand"]
        assert hand == ["A♠", "K♥", "2♣", "3♦", "4♠"]


class TestListRemove:
    def test_remove_existing(self, store, event_log, ctx):
        effect = EffectConfig(operator="list_remove", target="player.hand", value="A♠")
        execute(effect, store, event_log, ctx, tick=1)
        assert store.get("player")["hand"] == ["K♥"]

    def test_remove_missing_warns(self, store, event_log, ctx):
        """Removing a value not in list should warn and do nothing."""
        effect = EffectConfig(operator="list_remove", target="player.hand", value="JOKER")
        execute(effect, store, event_log, ctx, tick=1)
        assert store.get("player")["hand"] == ["A♠", "K♥"]  # unchanged

    def test_remove_from_non_list_warns(self, store, event_log, ctx):
        effect = EffectConfig(operator="list_remove", target="not_list.value", value="x")
        execute(effect, store, event_log, ctx, tick=1)
        assert store.get("not_list")["value"] == 42

    def test_remove_first_occurrence_only(self, store, event_log, ctx):
        # Add duplicate first
        store.update_property("player", "hand", ["A♠", "K♥", "A♠"])
        effect = EffectConfig(operator="list_remove", target="player.hand", value="A♠")
        execute(effect, store, event_log, ctx, tick=1)
        assert store.get("player")["hand"] == ["K♥", "A♠"]  # only first removed

    def test_remove_with_param(self, store, event_log):
        ctx = {"agent_id": "player", "action_params": {"card": "K♥"}, "tick": 1}
        effect = EffectConfig(operator="list_remove", target="$agent.hand", value="$card")
        execute(effect, store, event_log, ctx, tick=1)
        assert store.get("player")["hand"] == ["A♠"]


class TestListPopRandom:
    def test_pop_moves_element(self, store, event_log, ctx):
        """Element should move from source to target."""
        original_deck = list(store.get("deck")["cards"])
        original_hand = list(store.get("player")["hand"])

        effect = EffectConfig(
            operator="list_pop_random",
            source="deck.cards",
            target="player.hand",
        )
        execute(effect, store, event_log, ctx, tick=1)

        new_deck = store.get("deck")["cards"]
        new_hand = store.get("player")["hand"]

        assert len(new_deck) == len(original_deck) - 1
        assert len(new_hand) == len(original_hand) + 1
        # The picked card should be in hand but not in deck
        picked = set(original_deck) - set(new_deck)
        assert len(picked) == 1
        assert picked.pop() in new_hand

    def test_pop_from_empty_warns(self, store, event_log, ctx):
        """Popping from empty list should warn and do nothing."""
        store.update_property("deck", "cards", [])
        effect = EffectConfig(
            operator="list_pop_random",
            source="deck.cards",
            target="player.hand",
        )
        execute(effect, store, event_log, ctx, tick=1)
        assert store.get("player")["hand"] == ["A♠", "K♥"]  # unchanged

    def test_pop_creates_target_list(self, store, event_log, ctx):
        """If target property is None, creates a new list."""
        effect = EffectConfig(
            operator="list_pop_random",
            source="deck.cards",
            target="empty.items",
        )
        execute(effect, store, event_log, ctx, tick=1)
        assert len(store.get("empty")["items"]) == 1
        assert len(store.get("deck")["cards"]) == 4

    def test_pop_all_cards(self, store, event_log, ctx):
        """Pop all cards from deck to hand."""
        effect = EffectConfig(
            operator="list_pop_random",
            source="deck.cards",
            target="player.hand",
        )
        for _ in range(5):
            execute(effect, store, event_log, ctx, tick=1)

        assert store.get("deck")["cards"] == []
        assert len(store.get("player")["hand"]) == 7  # 2 original + 5 popped

    def test_pop_with_param_resolution(self, store, event_log):
        ctx = {"agent_id": "player", "action_params": {}, "tick": 1}
        effect = EffectConfig(
            operator="list_pop_random",
            source="deck.cards",
            target="$agent.hand",
        )
        execute(effect, store, event_log, ctx, tick=1)
        assert len(store.get("player")["hand"]) == 3

    def test_pop_randomness(self, store, event_log, ctx):
        """Run many pops and check distribution isn't always the same element."""
        picks = set()
        for _ in range(50):
            # Reset
            store.update_property("deck", "cards", ["A", "B", "C", "D", "E"])
            store.update_property("player", "hand", [])
            effect = EffectConfig(
                operator="list_pop_random",
                source="deck.cards",
                target="player.hand",
            )
            execute(effect, store, event_log, ctx, tick=1)
            picks.add(store.get("player")["hand"][0])

        # Should have picked more than 1 distinct card across 50 trials
        assert len(picks) > 1
