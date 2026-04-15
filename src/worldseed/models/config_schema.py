"""Pydantic models for Scene Config YAML validation."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class EntityConfig(BaseModel):
    """Entity definition in scene config.

    Flat format: id, type, and all other keys are properties.
      - id: foo
        type: resource
        quantity: 20
        location: storage_room

    Legacy format with explicit properties: dict is also accepted.
    """

    id: str
    type: str
    properties: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="before")
    @classmethod
    def _flatten_properties(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        reserved = {"id", "type", "properties"}
        extra = {k: v for k, v in data.items() if k not in reserved}
        if extra:
            props = dict(data.get("properties") or {})
            props.update(extra)
            data = {k: v for k, v in data.items() if k in reserved}
            data["properties"] = props
        return data


class TemplateConfig(BaseModel):
    """Reusable character archetype — starting stats for new agents."""

    properties: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="before")
    @classmethod
    def _flatten_properties(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        reserved = {"properties"}
        extra = {k: v for k, v in data.items() if k not in reserved}
        if extra:
            props = dict(data.get("properties") or {})
            props.update(extra)
            data = {"properties": props}
        return data


class AgentConfig(BaseModel):
    """Preset character in scene config.

    Flat format: id, template, character are reserved keys;
    all other keys become properties.
      - id: old_chen
        location: storage_room
        stress: 80
        character:
          personality: "cautious"

    Legacy format with explicit properties: dict is also accepted.
    """

    id: str
    template: str | None = None
    # Initial world state — merged with template, used by register_agent()
    properties: dict[str, Any] = Field(default_factory=dict)
    # Character card — free-form, engine never reads, given to claiming agent
    character: dict[str, Any] = Field(default_factory=dict)
    # Omniscient agents bypass all perception filtering (visibility, hidden
    # properties, event scopes).  Used for narrator/observer agents.
    omniscient: bool = False
    # System agents are auto-created by the engine. Not visible to other
    # agents, not shown on map, not included in characters list.
    system: bool = False
    # Whether push events trigger urgent wake. Default True for normal agents.
    # Set False for observer agents (e.g. narrator) that should only wake on interval + whisper.
    wake_on_push: bool = True

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="before")
    @classmethod
    def _flatten_properties(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        reserved = {"id", "template", "properties", "character", "omniscient", "system", "wake_on_push"}
        extra = {k: v for k, v in data.items() if k not in reserved}
        if extra:
            props = dict(data.get("properties") or {})
            props.update(extra)
            data = {k: v for k, v in data.items() if k in reserved}
            data["properties"] = props
        return data


class ParamConfig(BaseModel):
    name: str
    type: Literal["entity_ref", "number", "string", "free_text"]
    required: bool = True
    description: str = ""
    # DSL expression to resolve enum dynamically per agent.
    # "$visible" = all visible entities/agents.
    # Any other DSL path (e.g. "$agent.location") is resolved via path_resolver.
    # If the resolved value is an entity ID, its properties are checked for lists.
    enum_from: str | None = None
    # Filter resolved enum by matching entity properties.
    # Dict of {property: value}. ALL must match (AND logic).
    # "type" matches entity.type; other keys match entity properties.
    enum_filter: dict[str, Any] | None = None


class PreconditionConfig(BaseModel):
    operator: str  # Validated against precondition registry at runtime

    @field_validator("operator")
    @classmethod
    def check_operator(cls, v: str) -> str:
        from worldseed.dsl.preconditions._registry import get_all_precondition_operators

        valid = get_all_precondition_operators()
        if valid and v not in valid:
            msg = f"Unknown precondition operator: {v!r}. Valid: {valid}"
            raise ValueError(msg)
        return v

    # check-specific
    left: Any | None = None
    op: (
        Literal[
            "==",
            "!=",
            ">",
            "<",
            ">=",
            "<=",
            "in",
            "contains",
        ]
        | None
    ) = None
    right: Any | None = None
    # exists-specific
    expression: str | None = None
    # not/all/any: nested conditions
    conditions: list[PreconditionConfig] | None = None
    # not: single nested condition
    condition: PreconditionConfig | None = None


class EffectConfig(BaseModel):
    operator: str  # Validated against effect registry at runtime

    @field_validator("operator")
    @classmethod
    def check_operator(cls, v: str) -> str:
        from worldseed.dsl.effects._registry import get_all_effect_operators

        valid = get_all_effect_operators()
        if valid and v not in valid:
            msg = f"Unknown effect operator: {v!r}. Valid: {valid}"
            raise ValueError(msg)
        return v

    # set
    target: str | None = None
    value: Any | None = None
    # increment / decrement
    by: Any | None = None
    # create_entity / emit_event (shared field, distinguished by operator)
    id: str | None = None
    type: str | None = None
    properties: dict[str, Any] | None = None
    # add_relationship / remove_relationship
    from_entity: str | None = Field(
        default=None,
        validation_alias=AliasChoices("from", "from_entity"),
    )
    to: str | None = None
    # emit_event
    detail: str | None = None
    ttl: int | Literal["permanent"] | None = None
    scope: str | None = None  # free string, defined per scene
    event_target: str | None = None  # target agent for directed events
    # increment / decrement optional clamp
    min: float | int | None = None
    max: float | int | None = None
    # emit_event: push wake + highlight flag
    push: bool = False
    highlight: bool = False
    # list_pop_random: source list
    source: str | None = None
    # rotate: advance through a sequence
    sequence: str | None = None  # path to list property defining order
    skip: str | None = None  # path to list of values to skip
    # for_each: iterate matching entities and apply sub-effects
    match: dict[str, Any] | None = None  # { type: "agent", ... }
    where: str | None = None  # optional filter: "folded == false"
    sub_effects: list[EffectConfig] | None = Field(
        default=None,
        validation_alias=AliasChoices("effects", "sub_effects"),
    )
    # conditional execution: skip this effect if condition is false
    when: PreconditionConfig | None = None

    model_config = ConfigDict(populate_by_name=True)


class EventConfig(BaseModel):
    type: str
    detail: str
    ttl: int | Literal["permanent"]
    scope: str = "global"  # free string, defined per scene
    target: str | None = None
    push: bool = False  # wake agents immediately when this event fires
    highlight: bool = False  # mark as important for observer dashboard


class DMConfig(BaseModel):
    """DM (Dungeon Master) configuration for actions that need judgment."""

    hint: str = ""
    scope: str = "same_location"
    allowed_ops: list[str] = Field(
        default_factory=lambda: [
            "set",
            "increment",
            "decrement",
            "emit_event",
        ]
    )
    max_effects: int = 5
    push_events: list[str] = Field(default_factory=list)


class ActionConfig(BaseModel):
    description: str
    params: list[ParamConfig] = Field(default_factory=list)
    preconditions: list[PreconditionConfig] = Field(default_factory=list)
    effects: list[EffectConfig] = Field(default_factory=list)
    events: list[EventConfig] = Field(default_factory=list)
    dm: DMConfig | None = None
    available_to: list[PreconditionConfig] | None = (
        None  # Visibility filter. Same DSL as preconditions. None = all agents.
    )
    highlight: bool = False  # Mark action records as highlights for dashboard


class ConsequenceConfig(BaseModel):
    trigger: list[PreconditionConfig]
    effects: list[EffectConfig] = Field(default_factory=list)
    frequency: Literal["on_change", "every_tick"] = "on_change"
    dm: DMConfig | None = None  # Optional DM judgment when consequence triggers


class HighlightConfig(BaseModel):
    """A config-defined highlight trigger for the observer dashboard."""

    trigger: list[PreconditionConfig]
    label: str = ""
    frequency: Literal["on_change", "every_tick"] = "on_change"


class AutoTickConfig(BaseModel):
    description: str
    effects: list[EffectConfig]
    condition: list[PreconditionConfig] | None = None


class EventScopeConfig(BaseModel):
    """A named event scope with DSL-based delivery rules.

    rules: DSL precondition expressions evaluated per (observer, event_source).
           ALL must be true for the agent to receive the event.
           Empty list = deliver to all agents.
    """

    rules: list[PreconditionConfig] = Field(default_factory=list)


class WakeSummaryConfig(BaseModel):
    """Config for what state info to include in agent wake messages.

    Controls what the gateway plugin puts in the wake notification text.
    Server sends full perception; this selects what to display.

    Semantics:
      - Key absent → don't show that section
      - Empty list [] → show all fields (no filter)
      - Non-empty list → show only those fields

    If wake_summary is not configured at all, wake messages contain
    only events and a perceive+act instruction (no state).
    """

    self_fields: list[str] | None = None
    """Which of the agent's own properties to show. None = don't show self.
    Empty list = all properties. Non-empty = only listed fields."""

    entities: dict[str, list[str]] = Field(default_factory=dict)
    """Entities to show, by ID. Key = entity ID, value = field list.
    Example: {table: [pot, phase]} shows table with only pot and phase."""

    entity_types: dict[str, list[str]] = Field(default_factory=dict)
    """Entities to show, by type. Matches all visible entities of that type.
    Example: {resource: [quantity]} shows all resources with their quantity."""

    agent_fields: list[str] | None = None
    """Which fields of other agents to show. None = don't show others.
    Empty list = all visible fields. Non-empty = only listed fields."""


class PerceptionConfig(BaseModel):
    """Scene-defined perception rules using DSL expressions.

    visibility: DSL expressions evaluated per (observer, entity) pair.
                ALL must be true for entity to be visible.
                Empty list = everything visible (no filtering).
    event_scopes: named scope rules for event delivery.
                  "global" and "target_only" are built-in.
                  All other scopes must be declared here.
                  Undeclared scopes default to global delivery.
    hidden_properties: property keys stripped from other agents' view.
    wake_summary: what state info to include in agent wake messages.
    """

    visibility: list[PreconditionConfig] = Field(default_factory=list)
    event_scopes: dict[str, EventScopeConfig] = Field(
        default_factory=dict,
    )
    hidden_properties: list[str] = Field(default_factory=list)
    wake_summary: WakeSummaryConfig = Field(default_factory=WakeSummaryConfig)

    @model_validator(mode="before")
    @classmethod
    def _coerce_wake_summary(cls, data: Any) -> Any:
        """Allow wake_summary: null in YAML (treat as default)."""
        if isinstance(data, dict) and "wake_summary" in data:
            if data["wake_summary"] is None:
                del data["wake_summary"]
        return data


class SceneMetaConfig(BaseModel):
    id: str
    description: str
    dm_knowledge: str = ""  # Domain-specific rules for the DM. Not visible to agents.
    tick_interval: float = 5.0  # seconds between ticks
    max_ticks: int | None = Field(default=100, ge=1)  # auto-stop after N ticks
    timeout_min: float | None = Field(default=None, gt=0)  # auto-stop after N minutes
    max_dm_calls: int | None = Field(default=None, ge=0)  # skip DM after N total calls
    # Default properties for custom agents (e.g. location, hp)
    default_spawn: dict[str, Any] = Field(default_factory=dict)
    # Import presets: use: [social, spatial] loads configs/presets/{name}.yaml
    use: list[str] = Field(default_factory=list)


class SanityStep(BaseModel):
    """One step in a sanity check sequence."""

    agent: str | None = None
    action: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    expect: Literal["success", "fail"] = "success"
    # assert is a Python keyword, so use alias
    assertion: str | None = Field(default=None, alias="assert")
    ticks: int | None = None  # Advance N ticks with no action
    repeat: int | None = None  # Repeat the action N times

    model_config = ConfigDict(populate_by_name=True)


class SanityCheckConfig(BaseModel):
    """A named sanity check: a sequence of actions + assertions."""

    name: str
    steps: list[SanityStep]
    ticks: int | None = None  # Advance N ticks before running steps


class NarratorConfig(BaseModel):
    """Narrator configuration — controls the auto-created narrator agent.

    Accepts shorthand (string style name or bool) or full object form:
      narrator: "storyteller"
      narrator: false
      narrator: { prompt: "Narrate as a weary war correspondent..." }
    """

    style: Literal[
        "storyteller",
        "poet",
        "intel",
        "noir",
        "gossip",
        "conspiracy",
        "bureaucrat",
        "gameshow",
        "trickster",
    ] = "storyteller"
    prompt: str | None = None  # Custom prompt — overrides built-in style
    interval: int = 10  # Think interval in ticks (how often narrator writes)
    wake_on_push: bool = False  # Narrator only wakes on interval + whisper by default

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        """Accept string shorthand: narrator: "storyteller" → {style: "storyteller"}."""
        if isinstance(data, str):
            return {"style": data}
        return data


class SceneConfig(BaseModel):
    scene: SceneMetaConfig
    entities: list[EntityConfig]
    templates: dict[str, TemplateConfig] = Field(default_factory=dict)
    agents: list[AgentConfig] = Field(default_factory=list)
    actions: dict[str, ActionConfig]
    consequences: dict[str, ConsequenceConfig] = Field(default_factory=dict)
    highlights: dict[str, HighlightConfig] = Field(default_factory=dict)
    auto_tick: list[AutoTickConfig] = Field(default_factory=list)
    perception: PerceptionConfig = Field(default_factory=PerceptionConfig)
    sanity_checks: list[SanityCheckConfig] = Field(default_factory=list)
    narrator: NarratorConfig | bool = Field(default_factory=NarratorConfig)
