"""Protocol data structures for DM communication.

Pure data — zero logic, zero side effects.
These are the contracts between Builder and Provider.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from worldseed.models.action import ActionSubmission
from worldseed.models.config_schema import EffectConfig


@dataclass
class DMContext:
    """Input to the DM: full world state + action being judged.

    The DM is omniscient — it sees everything in the State Store.
    Context is formatted as plain text for LLM comprehension.
    """

    action: ActionSubmission
    world_state: str  # all entities + agents, formatted as plain text
    recent_events: str  # last N ticks of events, one line each
    scene_description: str  # from SceneConfig.scene.description
    hint: str  # from DMConfig.hint — what to judge
    allowed_ops: list[str]  # from DMConfig.allowed_ops
    max_effects: int  # from DMConfig.max_effects
    dm_knowledge: str = ""  # domain-specific rules for the DM (not visible to agents)
    target_history: str = ""  # recent events involving the action's target entity
    error_feedback: str | None = None  # validation error from previous attempt
    prompt_mode: str = "action"  # "action" (normal) or "gm_resolve" (GM command)
    language: str = ""  # ISO language code (e.g. "zh", "en")


@dataclass
class DMResponse:
    """Output from the DM: its judgment.

    narrative: what physically happened (actor + world only, never
    describes other agents). Engine auto-emits as event with scope
    from dm config.

    effects: DSL effects to apply (same format as EffectConfig).
    Can include emit_event for targeted information delivery.
    """

    narrative: str
    effects: list[EffectConfig] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
