"""Nested dict utilities — shared read/write for dot-separated paths.

These are pure dict operations with no DSL or engine dependencies.
Used by state_store (engine layer) and functions (DSL layer).
"""

from __future__ import annotations

from typing import Any


def nested_get(d: dict[str, Any], dotpath: str) -> Any:
    """Read a value from a nested dict using a dot-separated path.

    Like walk_entity_path in dsl/functions.py, but dict-only.
    Use this when the root is known to be a dict (e.g., entity.data).

    >>> nested_get({"a": {"b": 3}}, "a.b")
    3
    >>> nested_get({"a": {"b": 3}}, "a.c") is None
    True
    >>> nested_get({"x": 5}, "x")
    5
    """
    parts = dotpath.split(".")
    current: Any = d
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def nested_set(d: dict[str, Any], dotpath: str, value: Any) -> Any:
    """Write a value into a nested dict using a dot-separated path.

    Creates intermediate dicts as needed.
    Returns the old value (or None if the key didn't exist).

    >>> d = {"a": {"b": 3}}
    >>> nested_set(d, "a.b", 5)
    3
    >>> d
    {'a': {'b': 5}}
    >>> nested_set(d, "a.c", 10)
    >>> d
    {'a': {'b': 5, 'c': 10}}
    """
    parts = dotpath.split(".")
    old = nested_get(d, dotpath)
    current = d
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value
    return old
