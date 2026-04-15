"""DSL function registry."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

FunctionHandler = Callable[..., Any]

_REGISTRY: dict[str, FunctionHandler] = {}


def register_function(name: str, handler: FunctionHandler) -> None:
    """Register a DSL function handler."""
    _REGISTRY[name] = handler


def get_function_handler(name: str) -> FunctionHandler | None:
    """Look up a function handler by name."""
    return _REGISTRY.get(name)


def get_all_functions() -> list[str]:
    """Return all registered function names."""
    return list(_REGISTRY.keys())
