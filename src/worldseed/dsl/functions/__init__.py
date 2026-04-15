"""DSL functions — registry-based dispatcher.

To add a new DSL function:
1. Create a handler function: def _call_foo(args_str, store, ctx) -> Any
2. Call register_function("foo", _call_foo) at module level
That's it. path_resolver will find it automatically.
"""

from __future__ import annotations

import worldseed.dsl.functions.aggregation  # noqa: F401
import worldseed.dsl.functions.events  # noqa: F401
import worldseed.dsl.functions.length_fn  # noqa: F401
import worldseed.dsl.functions.random_fn  # noqa: F401

# Import modules to trigger registration
import worldseed.dsl.functions.relationships  # noqa: F401
from worldseed.dsl.functions._registry import (
    get_all_functions,
    get_function_handler,
    register_function,
)
from worldseed.dsl.functions.aggregation import (  # noqa: F401
    _filter_entities,
    _matches_where,
    count,
    sum_property,
)

# Re-export commonly used items for backward compatibility
from worldseed.dsl.functions.helpers import (  # noqa: F401
    try_numeric,
    walk_entity_path,
)
from worldseed.dsl.functions.relationships import (  # noqa: F401
    relationship_value,
    relationships_of,
)

__all__ = [
    "count",
    "get_all_functions",
    "get_function_handler",
    "register_function",
    "relationship_value",
    "relationships_of",
    "sum_property",
    "try_numeric",
    "walk_entity_path",
]
