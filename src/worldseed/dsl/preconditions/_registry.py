"""Precondition operator registry."""

from __future__ import annotations

from collections.abc import Callable

PreconditionHandler = Callable[..., bool]

_REGISTRY: dict[str, PreconditionHandler] = {}


def register_precondition(name: str, handler: PreconditionHandler) -> None:
    """Register a precondition operator handler."""
    _REGISTRY[name] = handler


def get_precondition_handler(name: str) -> PreconditionHandler | None:
    """Look up a precondition handler by operator name."""
    return _REGISTRY.get(name)


def get_all_precondition_operators() -> list[str]:
    """Return all registered operator names."""
    return list(_REGISTRY.keys())
