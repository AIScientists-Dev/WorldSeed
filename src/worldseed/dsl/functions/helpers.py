"""Shared helpers for DSL functions."""

from __future__ import annotations

__all__ = ["try_numeric", "walk_entity_path", "split_args", "parse_kwargs"]

from worldseed.models.entity import Entity


def walk_entity_path(obj: object, path: str) -> object:
    """Walk a dot-separated path on any object (Entity, dict, etc.).

    Shared walker used by both functions and path_resolver.

    For Entity objects, property keys live in entity.data (a dict).
    Paths like "location" resolve to entity.get("location").
    """
    current: object = obj
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, Entity):
            if part in current:
                current = current[part]
            elif hasattr(current, part):
                current = getattr(current, part)
            else:
                return None
        elif hasattr(current, part):
            current = getattr(current, part)
        else:
            return None
    return current


def try_numeric(expr: str) -> int | float | None:
    """Try to parse a string as a number."""
    try:
        return int(expr)
    except ValueError:
        pass
    try:
        return float(expr)
    except ValueError:
        pass
    return None


def split_args(args_str: str) -> list[str]:
    """Split function arguments, respecting nested parens."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for char in args_str:
        if char == "(":
            depth += 1
            current.append(char)
        elif char == ")":
            depth -= 1
            current.append(char)
        elif char == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    if current:
        parts.append("".join(current))
    return parts


def parse_kwargs(args_str: str) -> dict[str, str]:
    """Parse DSL function keyword arguments into a dict."""
    result: dict[str, str] = {}
    for part in split_args(args_str):
        part = part.strip()
        if "=" in part:
            key, val = part.split("=", 1)
            result[key.strip()] = val.strip().strip("'\"")
    return result
