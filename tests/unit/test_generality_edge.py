"""Generality edge cases NOT covered by test_generality_audit.py.

Python reserved-word property names, empty-string keys, circular/self
relationships, [] vs None vs missing, large ticks, Unicode, empty params.
"""

from __future__ import annotations

from worldseed.dsl.effects import execute as exec_effect
from worldseed.dsl.functions import relationships_of, walk_entity_path
from worldseed.dsl.path_resolver import resolve_params
from worldseed.dsl.preconditions import evaluate as eval_precond
from worldseed.engine.event_log import EventLog
from worldseed.engine.rules_engine import RulesEngine
from worldseed.engine.state_store import StateStore
from worldseed.models import ActionSubmission, Entity
from worldseed.models.config_schema import (
    ActionConfig,
    EffectConfig,
    PreconditionConfig,
    SceneConfig,
    SceneMetaConfig,
)
from worldseed.models.event import Event
from worldseed.utils.nested import nested_get, nested_set

CTX = {"agent_id": "x", "action_params": {}, "tick": 1}


class TestReservedWordProperties:
    def test_store_and_update_reserved_names(self) -> None:
        store = StateStore()
        store.add(Entity(id="x", type="t", _data={"class": "a", "import": 0}))
        store.update_property("x", "class", "b")
        store.update_property("x", "import", 99)
        e = store.get("x")
        assert e["class"] == "b" and e["import"] == 99  # type: ignore

    def test_nested_path_with_reserved_words(self) -> None:
        d: dict = {}
        nested_set(d, "class.type.return", 42)
        assert nested_get(d, "class.type.return") == 42

    def test_precondition_on_property_named_None(self) -> None:
        store = StateStore()
        store.add(Entity(id="x", type="t", _data={"None": "surprise"}))
        p = PreconditionConfig(operator="check", left="x.None", op="==", right="surprise")
        assert eval_precond(p, store, CTX) is True

    def test_effect_set_reserved_word(self) -> None:
        store = StateStore()
        store.add(Entity(id="e1", type="t", _data={"import": 0}))
        el = EventLog()
        exec_effect(
            EffectConfig(operator="set", target="e1.import", value="done"),
            store,
            el,
            {"agent_id": "e1", "action_params": {}, "tick": 1},
            tick=1,
        )
        assert store.get("e1")["import"] == "done"  # type: ignore


class TestEmptyAndBoundaryIds:
    def test_empty_string_property_name(self) -> None:
        d: dict = {}
        nested_set(d, "", "value")
        assert d.get("") == "value"

    def test_numeric_and_hyphenated_entity_ids(self) -> None:
        store = StateStore()
        store.add(Entity(id="42", type="t", _data={"v": True}))
        store.add(Entity(id="my-entity-01", type="t", _data={"ok": True}))
        assert store.get("42")["v"] is True  # type: ignore
        assert store.get("my-entity-01") is not None


class TestCircularRelationships:
    def test_circular_triple(self) -> None:
        store = StateStore()
        for src, tgt in [("a", "b"), ("b", "c"), ("c", "a")]:
            store.add(
                Entity(
                    id=src,
                    type="t",
                    _data={"next": [tgt]},
                )
            )
        assert store.get("c")["next"] == ["a"]  # type: ignore

    def test_self_reference(self) -> None:
        store = StateStore()
        store.add(
            Entity(
                id="me",
                type="t",
                _data={"ref": ["me"]},
            )
        )
        assert store.get("me")["ref"] == ["me"]  # type: ignore

    def test_remove_from_cycle_leaves_stale_ref(self) -> None:
        """Removing from cycle leaves stale ref — no write-time cleanup."""
        store = StateStore()
        store.add(Entity(id="a", type="t", _data={"next": ["b"]}))
        store.add(Entity(id="b", type="t", _data={"next": ["a"]}))
        store.remove("b")
        assert store.get("b") is None
        # Stale ref preserved — relationships_of returns it as-is
        assert store.get("a")["next"] == ["b"]  # type: ignore
        assert relationships_of("a", "next", store) == ["b"]


class TestArrayNoneMissing:
    def test_empty_list_vs_none_vs_missing(self) -> None:
        store = StateStore()
        store.add(Entity(id="x", type="t", _data={"a": [], "b": None}))
        e = store.get("x")
        assert e["a"] == [] and e["b"] is None  # type: ignore
        assert nested_get(e.data, "absent") is None  # type: ignore

    def test_exists_empty_vs_nonempty_list(self) -> None:
        store = StateStore()
        store.add(Entity(id="x", type="t", _data={"empty": [], "full": ["a"]}))
        assert (
            eval_precond(
                PreconditionConfig(operator="exists", expression="x.empty"),
                store,
                CTX,
            )
            is False
        )
        assert (
            eval_precond(
                PreconditionConfig(operator="exists", expression="x.full"),
                store,
                CTX,
            )
            is True
        )

    def test_set_to_empty_list_then_none(self) -> None:
        store = StateStore()
        store.add(Entity(id="x", type="t", _data={"v": [1, 2]}))
        store.update_property("x", "v", [])
        assert store.get("x")["v"] == []  # type: ignore
        store.update_property("x", "v", None)
        assert store.get("x")["v"] is None  # type: ignore


class TestLargeTickNumbers:
    def test_large_tick_effect(self) -> None:
        store = StateStore()
        store.add(Entity(id="x", type="t", _data={"v": 0}))
        el = EventLog()
        big = 2**53
        exec_effect(
            EffectConfig(operator="increment", target="x.v", by=1),
            store,
            el,
            {"agent_id": "x", "action_params": {}, "tick": big},
            tick=big,
        )
        assert store.get("x")["v"] == 1  # type: ignore

    def test_tick_param_resolves_large(self) -> None:
        assert resolve_params("t_$tick", {"agent_id": "a", "action_params": {}, "tick": 10**15}) == "t_1000000000000000"

    def test_event_log_large_tick(self) -> None:
        el = EventLog()
        big = 2**40
        el.append(Event(tick=big, type="t", source="s", detail="d", ttl=1, scope="global"))
        assert el.get_events(event_type="t")[0].tick == big


class TestUnicodePropertiesAndValues:
    def test_cjk_key_and_value(self) -> None:
        d: dict = {}
        nested_set(d, "\u751f\u547d\u503c", 100)
        assert nested_get(d, "\u751f\u547d\u503c") == 100
        store = StateStore()
        store.add(Entity(id="x", type="t", _data={"msg": "\u4f60\u597d"}))
        assert store.get("x")["msg"] == "\u4f60\u597d"  # type: ignore

    def test_emoji_value(self) -> None:
        store = StateStore()
        store.add(Entity(id="x", type="t", _data={"mood": "\U0001f525"}))
        assert store.get("x")["mood"] == "\U0001f525"  # type: ignore

    def test_unicode_entity_id_and_type(self) -> None:
        store = StateStore()
        store.add(Entity(id="\u7075\u72d0", type="\u5996\u602a", _data={"hp": 30}))
        assert store.get("\u7075\u72d0")["hp"] == 30  # type: ignore
        assert store.query_by_type("\u5996\u602a")[0].id == "\u7075\u72d0"

    def test_unicode_relationship_type(self) -> None:
        store = StateStore()
        store.add(Entity(id="a", type="t", _data={}))
        store.add(Entity(id="b", type="t", _data={}))
        store.update_property("a", "\u4fe1\u4efb", {"b": 80})
        assert store.get("a")["\u4fe1\u4efb"] == {"b": 80}  # type: ignore

    def test_walk_path_unicode_keys(self) -> None:
        e = Entity(id="x", type="t", _data={"\u529b": {"\u7ea7": 99}})
        assert walk_entity_path(e, "data.\u529b.\u7ea7") == 99

    def test_rtl_arabic_value(self) -> None:
        store = StateStore()
        store.add(Entity(id="x", type="t", _data={"n": "\u0645\u0631\u062d\u0628\u0627"}))
        assert store.get("x")["n"] == "\u0645\u0631\u062d\u0628\u0627"  # type: ignore


class TestEmptyVsMissingParams:
    def test_action_with_empty_params(self) -> None:
        config = SceneConfig(
            scene=SceneMetaConfig(id="test", description="test"),
            entities=[],
            actions={
                "rest": ActionConfig(
                    description="Rest",
                    params=[],
                    preconditions=[],
                    effects=[EffectConfig(operator="increment", target="$agent.hp", by=5)],
                )
            },
        )
        store = StateStore()
        store.add(Entity(id="hero", type="agent", _data={"hp": 10}))
        r = RulesEngine(config, store, EventLog()).process_action(
            ActionSubmission(agent_id="hero", action_type="rest", params={}), tick=1
        )
        assert r.success and store.get("hero")["hp"] == 15  # type: ignore

    def test_unresolvable_param_stays_literal(self) -> None:
        ctx = {"agent_id": "hero", "action_params": {}, "tick": 1}
        assert resolve_params("$unknown", ctx) == "$unknown"
        assert resolve_params("$agent.props", ctx) == "hero.props"
