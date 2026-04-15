"""Effect operator registry — single source of truth for valid operators."""

from __future__ import annotations

from collections.abc import Callable

# Unified handler signature: (effect, store, event_log, ctx, tick) -> None
EffectHandler = Callable[..., None]

_REGISTRY: dict[str, EffectHandler] = {}


def register_effect(name: str, handler: EffectHandler) -> None:
    """Register an effect operator handler."""
    _REGISTRY[name] = handler


def get_effect_handler(name: str) -> EffectHandler | None:
    """Look up an effect handler by operator name."""
    return _REGISTRY.get(name)


def get_all_effect_operators() -> list[str]:
    """Return all registered operator names."""
    return list(_REGISTRY.keys())
