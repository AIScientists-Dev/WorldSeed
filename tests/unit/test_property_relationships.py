"""Tests for property-based relationship model (no Relationship dataclass)."""

from __future__ import annotations

from worldseed.dsl.effects import execute
from worldseed.dsl.functions import relationships_of
from worldseed.engine.event_log import EventLog
from worldseed.engine.state_store import StateStore
from worldseed.models import Entity
from worldseed.models.config_schema import EffectConfig


def _store() -> StateStore:
    s = StateStore()
    s.add(Entity(id="alice", type="agent", _data={"location": "room_a"}))
    s.add(Entity(id="bob", type="agent", _data={"location": "room_b"}))
    s.add(Entity(id="carol", type="agent", _data={"location": "room_a"}))
    return s


def _ctx(agent: str = "alice") -> dict:  # type: ignore[type-arg]
    return {"agent_id": agent, "action_params": {}}


def _add(s: StateStore, frm: str, typ: str, to: str, val: object = None) -> None:
    e = EffectConfig(
        operator="add_relationship",
        from_entity=frm,
        type=typ,
        to=to,
        value=val,
    )
    execute(e, s, EventLog(), _ctx(frm), tick=1)


def _rm(s: StateStore, frm: str, typ: str, to: str) -> None:
    e = EffectConfig(operator="remove_relationship", from_entity=frm, type=typ, to=to)
    execute(e, s, EventLog(), _ctx(frm), tick=1)


# 1. List property — relationships_of returns targets
def test_list_relationships_of() -> None:
    s = _store()
    s.get("alice")["connects_to"] = ["bob", "carol"]  # type: ignore[union-attr]
    assert relationships_of("alice", "connects_to", s) == ["bob", "carol"]


# 2. Dict property — relationships_of returns keys
def test_dict_relationships_of() -> None:
    s = _store()
    s.get("alice")["trusts"] = {"bob": 80, "carol": 50}  # type: ignore[union-attr]
    assert set(relationships_of("alice", "trusts", s)) == {"bob", "carol"}


# 3. add_relationship creates list property when none exists
def test_add_rel_creates_list() -> None:
    s = _store()
    _add(s, "alice", "allies", "bob")
    assert s.get("alice")["allies"] == ["bob"]  # type: ignore[union-attr]


def test_add_rel_appends_no_dup() -> None:
    s = _store()
    _add(s, "alice", "allies", "bob")
    _add(s, "alice", "allies", "carol")
    _add(s, "alice", "allies", "bob")  # duplicate — should not appear twice
    assert s.get("alice")["allies"] == ["bob", "carol"]  # type: ignore[union-attr]


# 4. add_relationship with value creates dict property
def test_add_rel_creates_dict_with_value() -> None:
    s = _store()
    _add(s, "alice", "trusts", "bob", val=70)
    assert s.get("alice")["trusts"] == {"bob": 70}  # type: ignore[union-attr]


# 5. add_relationship upserts existing dict entry
def test_add_rel_upserts_dict() -> None:
    s = _store()
    _add(s, "alice", "trusts", "bob", val=50)
    _add(s, "alice", "trusts", "bob", val=90)
    _add(s, "alice", "trusts", "carol", val=60)
    assert s.get("alice")["trusts"] == {"bob": 90, "carol": 60}  # type: ignore[union-attr]


# 6. remove_relationship removes from list
def test_remove_rel_from_list() -> None:
    s = _store()
    _add(s, "alice", "allies", "bob")
    _add(s, "alice", "allies", "carol")
    _rm(s, "alice", "allies", "bob")
    assert s.get("alice")["allies"] == ["carol"]  # type: ignore[union-attr]


# 7. remove_relationship removes from dict
def test_remove_rel_from_dict() -> None:
    s = _store()
    _add(s, "alice", "trusts", "bob", val=50)
    _add(s, "alice", "trusts", "carol", val=60)
    _rm(s, "alice", "trusts", "bob")
    assert s.get("alice")["trusts"] == {"carol": 60}  # type: ignore[union-attr]


# 8. Mixed: entity has both list-type and dict-type relationship properties
def test_mixed_list_and_dict() -> None:
    s = _store()
    _add(s, "alice", "allies", "bob")
    _add(s, "alice", "trusts", "carol", val=75)
    alice = s.get("alice")
    assert alice is not None
    assert alice["allies"] == ["bob"]
    assert alice["trusts"] == {"carol": 75}
    assert relationships_of("alice", "allies", s) == ["bob"]
    assert relationships_of("alice", "trusts", s) == ["carol"]


# 9. Empty list/dict handling
def test_empty_list_returns_empty() -> None:
    s = _store()
    s.get("alice")["allies"] = []  # type: ignore[union-attr]
    assert relationships_of("alice", "allies", s) == []


def test_empty_dict_returns_empty() -> None:
    s = _store()
    s.get("alice")["trusts"] = {}  # type: ignore[union-attr]
    assert relationships_of("alice", "trusts", s) == []


def test_remove_last_list_entry() -> None:
    s = _store()
    _add(s, "alice", "allies", "bob")
    _rm(s, "alice", "allies", "bob")
    assert s.get("alice")["allies"] == []  # type: ignore[union-attr]


def test_remove_last_dict_entry() -> None:
    s = _store()
    _add(s, "alice", "trusts", "bob", val=50)
    _rm(s, "alice", "trusts", "bob")
    assert s.get("alice")["trusts"] == {}  # type: ignore[union-attr]


# 10. relationships_of on entity with no matching property → empty list
def test_no_matching_property() -> None:
    s = _store()
    assert relationships_of("alice", "enemies", s) == []


def test_nonexistent_entity() -> None:
    s = _store()
    assert relationships_of("nobody", "allies", s) == []
