# Scene Config Reference

> A YAML file defines a complete world. This document explains every section, every field, every pattern. Use it as a reference when designing new scenes.

## Quick Reference

### Structure Overview

Every scene config has up to 10 top-level sections:

```yaml
scene:            # 1. What is this world?
entities:         # 2. What exists in it?
templates:        # 3. Reusable starting stats (optional)
agents:           # 4. Who lives in it? (optional)
actions:          # 5. What can agents do?
consequences:     # 6. What does the world detect automatically? (optional)
auto_tick:        # 7. What changes every tick on its own? (optional)
perception:       # 8. Who can see what? (optional, defaults to global)
sanity_checks:    # 9. Scripted tests for the world (optional)
narrator:         # 10. Auto-narrator that writes chapter summaries (on by default)
```

Only `scene`, `entities`, and `actions` are required. The rest default to empty/permissive.

### Flat vs Nested Property Format

Entities, agents, and templates support two equivalent formats. Flat is preferred for readability.

```yaml
# Flat format (preferred) -- all keys except reserved become properties
- id: food_supply
  type: resource
  quantity: 20
  unit: "person-days"
  located_in: [storage]

# Nested format (legacy) -- properties in explicit dict
- id: food_supply
  type: resource
  properties:
    quantity: 20
    unit: "person-days"
    located_in: [storage]
```

Reserved keys that are NOT treated as properties:

| Section | Reserved keys |
|---|---|
| `entities` | `id`, `type`, `properties`, `constraints` |
| `agents` | `id`, `template`, `properties`, `character` |
| `templates` | `properties` |

Both formats can coexist. If both flat keys and a `properties` dict are present, they are merged (flat keys take precedence on conflict).

---

## Syntax Reference

### Scene -- Metadata

```yaml
scene:
  id: string                    # Required. Unique identifier.
  description: string           # Required. Natural language. Fed to DM for context.
  tick_interval: number         # Optional. Seconds between ticks. Default: 5.0.
  tick_narrative_time: string   # Optional. Story time per tick. "~30 minutes", "1 day".
  narrative_speed: number       # Optional. Multiplier for time progression.
  default_spawn: { key: value } # Optional. Default properties for dynamically registered agents.
  dm_knowledge: string         # Optional. Domain rules for DM. Not visible to agents.
  max_ticks: number | null     # Optional. Auto-stop after N ticks. Default: 100. null = unlimited.
  timeout_min: number | null   # Optional. Auto-stop after N minutes. Default: null.
  max_dm_calls: number | null  # Optional. Skip DM after N total calls. Default: null.
  use: [string]               # Optional. Import preset action/config fragments from configs/presets/.
```

#### Presets (`scene.use`)

Presets are reusable config fragments that add actions, perception rules, and consequences. List preset names in `scene.use` to import them. They expand at load time into `actions`, `perception`, etc.

```yaml
scene:
  use: [talk, directed_talk, attempt, move_connected, same_location_perception]
```

See `references/preset-catalog.md` for all available presets. Common ones: `talk` (speech), `directed_talk` (private speech), `attempt` (freeform action), `move_connected` (spatial movement), `same_location_perception` (only see entities in your room).

The `description` matters -- when the DM resolves `attempt` or `observe` actions, it reads this to understand the world's tone and constraints.

`dm_knowledge` is domain-specific rules the DM needs but agents should NOT see. It's injected into every DM prompt. Example: poker hand rankings, combat damage formulas, legal precedents. This is stripped from agent-facing config.

`tick_interval` controls the real-world pacing. At `5.0` (default), the engine ticks every 5 seconds. Increase for slower simulations; decrease for rapid testing.

`default_spawn` provides fallback properties (e.g., `location`, `hp`) for agents that register at runtime without a preset profile.

**Examples:**

```yaml
# Tense survival
scene:
  id: doomsday_bunker
  description: "Underground bunker. 5 survivors. Limited supplies. 20 days of food. No contact with outside."
  tick_narrative_time: "~30 minutes"

# Abstract debate
scene:
  id: free_will_debate
  description: "Three philosophers in a debate hall. No physical constraints. Pure discourse."
  tick_interval: 10.0

# Economic simulation with dynamic agents
scene:
  id: island_market
  description: "Tropical island. 8 traders. Each has a specialty resource. No currency exists yet."
  tick_narrative_time: "~1 day"
  default_spawn: { location: town_square, gold: 50 }
```

---

### Entities -- World State

Entities define everything in the world. Agents define the characters who inhabit it. They are separate sections.

```yaml
entities:
  - id: string                  # Required. Unique within this scene.
    type: string                # Required. Free string. Engine only treats "agent" specially.
    constraints: { prop: ... }  # Optional. Numeric bounds enforced on writes.
    # All other keys are properties (flat format), or use properties: dict
```

#### Entity types

The engine only treats `type: "agent"` specially (the Perceiver delivers perceptions to agents). Everything else is just a label for your DSL expressions.

**Common types** (conventions, not requirements):
- `agent` -- autonomous actors. Get inboxes, perception, can submit actions. **Do not define agents in `entities:`. Use the `agents:` section instead.** The engine creates agent entities automatically on `/register`.
- `space` -- places. Often have `connects_to` relationships.
- `resource` -- consumable quantities. Often have `quantity` property.
- `object` -- things that can be taken, used, created.
- `concept` -- abstract entities (laws, agreements, weather, time).

You can invent any type. The engine does not care. Your DSL expressions reference types in `count()`, `exists()`, etc.

#### Properties

Properties are the primary state container. Free key-value pairs. The engine does not know any property names -- "location", "health", "mood", "price", "trust" are all just strings.

```yaml
# Properties are completely free-form
- id: example
  type: object
  location: sleeping_quarters     # A string
  health: 100                     # A number
  mood: "anxious"                 # A string
  inventory: ["key", "torch"]     # A list
  is_locked: true                 # A boolean
  stats:                          # Nested dict (accessible via dot paths)
    strength: 8
    charisma: 12
```

Properties can be **created at runtime** by DSL `set` effects. An entity can gain properties it did not start with. This is how trust, reputation, emotional state, etc. get added as the world evolves.

#### Constraints

Entities can declare `constraints` to enforce numeric bounds on any property. The engine clamps values on **every write path** -- action effects, DM effects, auto_tick, and god-mode -- so invalid values never reach state.

```yaml
entities:
  - id: duct_tape
    type: tool
    quantity: 3
    constraints:
      quantity: { min: 0 }          # quantity will never go below 0

  - id: air_filter
    type: equipment
    condition: 70
    constraints:
      condition: { min: 0, max: 100 }  # condition stays in [0, 100]
```

Each constraint is a dict keyed by property name. Supported keys inside the dict:

| Key | Type | Meaning |
|---|---|---|
| `min` | number | Floor. Writes below this are clamped up. |
| `max` | number | Ceiling. Writes above this are clamped down. |

Both `min` and `max` are optional -- you can set one or both. Constraints only apply to numeric properties; they are ignored for strings, lists, and booleans.

#### Relationships

Typed, directed edges between entities. Used for spatial connections, social bonds, ownership, or any relationship. Relationships are stored as **regular properties** using the flat format:

- **Unvalued** (e.g. spatial connections): stored as lists of target IDs.
- **Valued** (e.g. trust scores): stored as dicts of `{target: value}`.

```yaml
entities:
  - id: hallway
    type: space
    # Unvalued relationships — list of target IDs
    connects_to: [storage_room, sleeping_quarters]

  - id: agent_a
    type: agent
    # Valued relationships — dict of {target: value}
    trusts: { agent_b: 40 }
    # Unvalued — list
    owned_by: [old_chen]
    warp_gate: [engineering_bay]
```

The DSL operators `add_relationship` and `remove_relationship` manipulate these properties at runtime. **Upsert semantics:** `add_relationship` with the same `(from, type, to)` updates `value` instead of duplicating.

The DSL function `relationships_of(entity, type=rel_type)` reads these properties to return target lists or values.

#### Examples: Different world types

```yaml
# Spatial world (bunker, RPG, dungeon)
entities:
  - id: hallway
    type: space
    description: "Central corridor"
    connects_to: [storage_room, sleeping_quarters]
agents:
  - id: old_chen
    location: hallway
    health: 100
    private_stash: 0
    character:
      personality: "Cautious, selfish"
      goals: ["Survive at any cost"]

# Non-spatial world (forum, debate, social network)
entities:
  - id: philosophy_channel
    type: channel
    topic: "Free will"
    post_count: 0
agents:
  - id: thinker_a
    reputation: 50
    stance: "determinism"
    character:
      personality: "Logical, aggressive"
      goals: ["Prove determinism is correct"]

# Economic world (market, trade)
entities:
  - id: fish_market
    type: space
    description: "Open-air market by the docks"
  - id: fish_stock
    type: resource
    quantity: 200
    price: 5
    location: fish_market
    quality: "fresh"
agents:
  - id: merchant_zhao
    location: fish_market
    gold: 100
    specialty: "fish"
    character:
      personality: "Shrewd, fair"
      goals: ["Maximize profit while maintaining reputation"]

# Abstract world (simulation, thought experiment)
entities:
  - id: population
    type: concept
    count: 1000
    growth_rate: 0.02
    happiness: 0.7
agents:
  - id: policy_maker
    ideology: "utilitarian"
    influence: 50
    character:
      personality: "Pragmatic, data-driven"
      goals: ["Maximize population happiness"]
```

---

### Templates -- Reusable Starting Stats

If multiple agents share the same starting properties, use templates to avoid repetition:

```yaml
templates:
  trader:
    gold: 100
    reputation: 50

agents:
  - id: merchant_a
    template: trader
    character: { personality: "Aggressive haggler" }
  - id: merchant_b
    template: trader
    character: { personality: "Honest and patient" }
```

Template properties are merged into agent properties at registration. Agent-level properties override template values on conflict. Templates support the same flat/nested format as entities.

---

### Agents -- Character Identity

Agents are defined separately from entities. Each agent entry creates an entity (`type: "agent"`) in the world state AND stores the `character` card for prompt building.

```yaml
agents:
  - id: string                   # Required. Becomes the agent's entity ID.
    template: string              # Optional. Inherit starting properties from a named template.
    character:                    # Free-form dict. Engine never reads it; prompt builder does.
      [any_key]: any
    think_interval: number         # Optional. Seconds between agent wakes. Default: 5. Set high (50-99) for waiting roles, low (2-3) for active workers.
    # All other keys are starting properties (flat format)
```

**Key distinction:** Entity properties = world state (what the world sees). Character = agent identity (what the agent knows about itself). The engine, perceiver, and inbox never access `character`.

#### Character card design

Shallow character cards produce shallow behavior. A 2-line card creates agents that announce their goals and do nothing else. Use the full template:

**Required fields:**

```yaml
character:
  # WHO: one sentence. Name, age, background, competence.
  identity: "Chen Guowei, 58. Former logistics manager. Practical, calculating."

  # HOW: behavioral tendencies under pressure.
  personality: >
    Cautious, selfish, strong survival instinct. Frames selfish
    actions as pragmatic group decisions.

  # WHAT: concrete goals with reasoning, not abstract values.
  goals:
    - "Survive -- you believe the supplies cannot sustain 3 people long-term"

  # WHY: action-prompting drives. Each must map to a specific game action.
  drives:
    - "Secure resources for yourself before others realize the shortage"
    - "Scout the entrance -- if escape is possible, you want to know first"
    - "Maintain a cooperative facade so others don't turn on you"
    - "Investigate anything useful -- tools, radio, equipment"
```

**Strongly recommended fields:**

```yaml
  # Asymmetric opinions toward each other agent. Drives social conflict.
  relationships:
    doctor_wang: >
      Resents his authority but needs his medical knowledge --
      your knee aches badly
    xiao_li: >
      Physically the strongest. Dangerous if she turns on you.
      Keep her on your side.

  # Creates information asymmetry. Agents with secrets act more cautiously.
  secret: >
    You checked the supply math. At current rates, food runs out
    in days. You have told no one.
```

**What makes drives work:**

The key test: can the agent execute the drive as a concrete action (`move`, `observe`, `attempt`, `take`)? If not, rewrite it.

```yaml
# BAD: abstract values -> agents say "I believe in fairness" and do nothing
drives:
  - "Value fairness"
  - "Help the group"
  - "Be cautious"

# GOOD: action-prompting -> agents physically do things
drives:
  - "If someone takes more than their fair share, confront them directly"
  - "Physically guard the storage room when resources are low"
  - "Use observe and attempt to investigate threats before discussing them"
  - "When you propose a plan, execute the first step immediately"
```

Drives must reference the config. Every entity_id in a drive must exist in `entities`. Every action verb must exist in `actions`. A drive referencing a "generator" when no generator entity exists is dead weight -- the agent tries, fails, and falls back to `say`.

---

### Actions -- What Agents Can Do

Actions defined here are **world-level** — things that happen in the world (move, trade, say, attack), validated by preconditions, producing state changes via effects. They are not the agent's own capabilities (reasoning, web search, image generation, tool use). Those happen on the agent side and are invisible to the engine. The agent decides *which* world action to submit; the engine decides *whether* it's allowed and *what* happens.

Each action has: a description (shown to agents), parameters, preconditions (when is it allowed), effects (what changes), and events (what gets announced).

```yaml
actions:
  [action_name]:
    description: string                   # Shown to agents. Natural language.
    params:
      - name: string                      # Referenced as $name in DSL
        type: entity_ref | number | string | free_text
        required: boolean
        description: string               # Optional. Hint for LLM agents.
        enum_from: string                 # Optional. DSL expr -> dynamic enum.
        enum_filter: { type: string }     # Optional. Filter enum results by entity type.
    preconditions:                         # All must pass. Empty [] = always allowed.
      - { operator: check|exists|not|all|any, ... }
    effects:                               # What changes in the world.
      - { operator: set|increment|decrement|create_entity|remove_entity|
                    add_relationship|remove_relationship|emit_event|
                    list_append|list_remove|list_pop_random, ... }
    dm:                                    # Optional. Escalates to LLM DM for judgment.
      hint: string
      scope: string
      allowed_ops: [string]
      max_effects: number
      push_events: [string]
    available_to:                          # Optional. Per-agent action filtering.
      - { operator: check|exists|not|all|any, ... }
    highlight: boolean                      # Optional. Mark action as pivotal — appears in chapter panel.
    events:                                # Shorthand for emit_event effects.
      - { type: string, detail: string, ttl: number, scope: string, highlight: boolean }
```

**`enum_filter`:** Filters the entity list produced by `enum_from`. Both a UI hint (agents only see filtered options) and server-enforced. Example: `enum_filter: { type: "equipment" }` filters to only equipment entities.

**`highlight`:** Marks an action as a pivotal moment. When this action executes, it appears as a chapter marker in the observer's stream panel. Use sparingly (2-4 per config) for irreversible decisions, turning points, victories. Can also be set on individual `events` entries and on `emit_event` effects in consequences.

**`available_to`:** DSL preconditions evaluated per agent. Both a **visibility filter** (agents that fail don't see the action in `action_options`) and **server-enforced** (the engine rejects the action even if submitted directly). Omit for actions available to everyone.

```yaml
# Only players see fold/call/raise. Dealer sees deal/reset.
fold:
  available_to:
    - { operator: check, left: "$agent.role", op: "==", right: "player" }
deal_hands:
  available_to:
    - { operator: check, left: "$agent.role", op: "==", right: "dealer" }
```

Each agent gets a filtered WORLD.md containing only the actions they can see.

#### Parameter types

| Type | Meaning | DSL resolution |
|---|---|---|
| `entity_ref` | An entity ID | `$param` resolves to the ID string. `$param.x` accesses entity state. |
| `number` | A numeric value | `$param` resolves to the number. |
| `string` | A fixed string | `$param` resolves to the string. |
| `free_text` | Arbitrary text | `$param` resolves to the text. Used for `say` and `attempt`. |

#### Parameter description

The optional `description` field provides a natural-language hint for LLM agents, explaining what value to supply. The engine ignores it; it is passed through in the action schema so agents can make better choices.

```yaml
params:
  - { name: amount, type: number, required: true,
      description: "How much to take (must be <= available quantity)" }
```

#### Parameter enum_from

The optional `enum_from` field provides a DSL expression evaluated **per agent** at perceive time. The resolved values populate an `enum` list in the action schema sent to the agent.

**Three modes:**

| `enum_from` value | Resolves to |
|---|---|
| `"$visible"` | All entity/agent IDs currently visible to the acting agent. |
| DSL expression | Evaluated via `path_resolver`. E.g. `"relationships_of($agent.location, type=connects_to)"` returns connected space IDs. |
| Entity-as-list | If the resolved value is an entity ID, its properties are checked for list values to use as the enum. |

**Examples:**

```yaml
# Movement -- enum is the connected spaces for the agent's current location
move:
  params:
    - { name: to, type: entity_ref, required: true,
        enum_from: "relationships_of($agent.location, type=connects_to)",
        description: "Space ID from connects_to" }

# Take -- enum is everything the agent can see
take:
  params:
    - { name: target, type: entity_ref, required: true,
        enum_from: "$visible",
        description: "Resource at your location" }

# Say -- optional addressee from visible entities
say:
  params:
    - { name: to, type: entity_ref, required: false,
        enum_from: "$visible",
        description: "Agent to address (optional)" }
```

When `enum_from` is absent, the agent receives no enum constraint and can pass any value (validated by preconditions at action time).

#### DSL Expressions

Preconditions, effects, functions, path expressions, and arithmetic are documented in [SCENE_DSL.md](SCENE_DSL.md).

---

### Consequences -- Automatic Detection

Consequences are rules the engine evaluates every tick after all actions are processed. They detect emergent situations -- things no single action caused.

```yaml
consequences:
  [rule_name]:
    trigger:                     # Same DSL as preconditions
      - { operator: check|exists, ... }
    effects:                     # Same DSL as action effects (optional if dm is set)
      - { operator: ..., ... }
    frequency: on_change         # on_change (default) or every_tick
    dm:                          # Optional. DM judgment when consequence triggers.
      hint: string               # What to judge
      allowed_ops: [string]
      max_effects: number
      scope: string
```

**DM on consequences:** When a consequence has a `dm:` block, the DM is called after deterministic effects execute. Use this when the world needs to react to a condition but the reaction requires judgment (e.g., dealing cards when all players have acted, describing environmental damage).

```yaml
# Example: DM deals flop cards when all players have acted
deal_flop:
  trigger:
    - { operator: check, left: "table.phase", op: "==", right: "pre_flop_done" }
  effects:
    - { operator: set, target: "table.phase", value: "flop" }
  dm:
    hint: "Deal 3 cards from deck.cards to table.community_cards. Remove dealt cards from deck."
    allowed_ops: [set, list_remove, list_append, emit_event]
    max_effects: 8
```

**Two frequency modes:**

| Mode | Behavior | Use for |
|---|---|---|
| `on_change` (default) | Fire once on false-to-true transition. Will not re-fire until condition resets. | Alerts, state transitions, one-time events |
| `every_tick` | Fire every tick while condition is true. | Continuous damage, decay, healing, environmental effects |

**`$entity` in consequences:** Both trigger and effects support `$entity`. The scanner iterates all entities -- each matching entity independently triggers the consequence. The scanner creates a context with `$entity` bound to each entity's ID in turn.

```yaml
# every_tick + $entity: agents in reactor take continuous damage
radiation_damage:
  trigger:
    - { operator: check, left: "$entity.type", op: "==", right: "agent" }
    - { operator: check, left: "$entity.location", op: "==",
        right: "reactor" }
  effects:
    - { operator: decrement, target: "$entity.health", by: 10, min: 0 }
    - { operator: increment, target: "$entity.radiation", by: 5 }
  frequency: every_tick

# on_change + $entity: fire once when agent first enters reactor
radiation_warning:
  trigger:
    - { operator: check, left: "$entity.type", op: "==", right: "agent" }
    - { operator: check, left: "$entity.location", op: "==",
        right: "reactor" }
  effects:
    - { operator: emit_event, type: "warning",
        detail: "Agent entered radiation zone!", ttl: 3, scope: "global" }
  frequency: on_change
```

**Note:** `every_tick` with `emit_event` produces one event per tick. Use short TTLs (0-1) to prevent event log bloat.

#### Common consequence patterns

```yaml
# Co-location detection (spatial worlds)
co_location:
  trigger:
    - { operator: check, left: "count(type=agent, where=location == $location)",
        op: ">=", right: 2 }
  effects:
    - { operator: emit_event, type: co_location, detail: "Multiple agents present",
        ttl: 0 }
  frequency: on_change

# Resource threshold
scarcity_alert:
  trigger:
    - { operator: check, left: "food_supply.quantity", op: "<", right: 5 }
  effects:
    - { operator: emit_event, type: scarcity, detail: "Food critically low",
        ttl: 5, scope: global }
  frequency: on_change

# State transition
metamorphosis:
  trigger:
    - { operator: check, left: "$entity.age_in_stage", op: ">=",
        right: "$entity.stage_duration" }
  effects:
    - { operator: set, target: "$entity.stage", value: "next_stage" }
    - { operator: set, target: "$entity.age_in_stage", value: 0 }
  frequency: on_change

# Market condition
price_crash:
  trigger:
    - { operator: check, left: "fish_stock.quantity", op: ">", right: 500 }
  effects:
    - { operator: decrement, target: "fish_stock.price", by: 2 }
    - { operator: emit_event, type: market, detail: "Fish prices crashing due to oversupply",
        ttl: 3, scope: global }
  frequency: on_change
```

---

### Auto-Tick -- Passive Time Effects

Effects applied every tick automatically. Represent natural processes: consumption, decay, growth, aging.

```yaml
auto_tick:
  - description: string          # Human-readable explanation
    effects:                     # Same DSL as action effects
      - { operator: ..., ... }
    condition:                   # Optional. Effects only apply when ALL conditions are true.
      - { operator: check, ... }
```

#### Guard decrements with conditions

The engine executes effects honestly -- `decrement` will go below zero. Prevent this with `min: 0` on the effect, or with a `condition` on the auto_tick entry:

```yaml
# Option 1: min clamp on the effect
auto_tick:
  - description: "Food consumed"
    effects:
      - { operator: decrement, target: "food.quantity",
          by: "0.1 * count(type=agent)", min: 0 }

# Option 2: condition guard on the auto_tick entry
auto_tick:
  - description: "Food consumed"
    effects:
      - { operator: decrement, target: "food.quantity",
          by: "0.1 * count(type=agent)" }
    condition:
      - { operator: check, left: "food.quantity", op: ">", right: 0 }
```

Both work. Use `min: 0` for simple floor clamping. Use `condition` when you want to skip the entire effect (e.g., stop regeneration entirely when a resource hits zero, not just clamp it).

If negative values are meaningful (debt, temperature below zero), do not guard.

#### Common patterns

```yaml
# Resource consumption (per agent)
- description: "Food consumed by survivors"
  effects:
    - { operator: decrement, target: "food_supply.quantity",
        by: "0.1 * count(type=agent)", min: 0 }

# Natural decay
- description: "Equipment deterioration"
  effects:
    - { operator: decrement, target: "generator.durability", by: 0.5, min: 0 }

# Growth / regeneration with collapse threshold
- description: "Fish population recovery"
  effects:
    - { operator: increment, target: "fish_stock.quantity",
        by: "0.05 * fish_stock.quantity" }
  condition:
    - { operator: check, left: "fish_stock.quantity", op: ">", right: 0 }

# Time progression
- description: "Day counter"
  effects:
    - { operator: increment, target: "world_clock.day", by: 1 }
```

---

### Perception -- Who Sees What

Defines what each agent can perceive. Uses the same DSL as preconditions. This is where information asymmetry comes from.

```yaml
perception:
  visibility:                    # List of DSL rules. ALL must pass for entity to be visible.
    - { operator: check|exists|not|all|any, ... }
  event_scopes:                  # Named rules for event delivery.
    [scope_name]:
      rules:
        - { operator: check, ... }
  hidden_properties:             # Properties stripped from other agents' view.
    - string
```

**Context variables for visibility rules:**
- `$observer` -- the agent receiving perception
- `$entity` -- the entity being checked for visibility

**Context variables for event scope rules:**
- `$observer` -- the agent receiving the event
- `$event_source` -- the entity that caused the event

**Empty visibility list `[]`** = everything visible to everyone (no filtering).

#### Event scopes

**Built-in scopes** (do not need to be declared):

| Scope | Behavior |
|---|---|
| `"global"` | All agents receive the event |
| `"target_only"` | Only `event.target` receives the event |
| `"admin"` | No agents receive. Dashboard/god-view only. Useful for system diagnostics. |

**Custom scopes** are defined in `perception.event_scopes` with DSL rules:

```yaml
event_scopes:
  same_location:
    rules:
      - { operator: check, left: "$observer.location", op: "==",
          right: "$event_source.location" }
```

**Undeclared scopes** (referenced in events but not defined in `event_scopes`) default to global delivery. This is intentional -- it prevents silent event loss from typos, but means you should declare scopes explicitly for non-global behavior.

#### Direct message delivery

When an event has `event_target` set to an agent ID, that agent always receives it as a **direct message** in its inbox, regardless of scope rules. This is in addition to any scope-based delivery. Direct messages appear in a separate `whispers` section of the agent's perception, distinct from regular events.

#### Hidden properties

Properties listed in `hidden_properties` are stripped from other agents' perception. Each agent still sees its own hidden properties in `self_state`.

```yaml
hidden_properties: ["private_stash", "goals", "mood", "secret"]
```

**What to hide vs reveal:** Hide motivation (goals, secrets, suspicion). Reveal state (condition, quantity, damage). Hiding physical state breaks agent feedback loops -- they cannot tell if their actions worked.

#### Perception patterns by world type

```yaml
# Spatial: see entities at your location + the space you're in
# The `any` is critical -- space entities have no `location` property,
# so the second condition lets agents see their current room.
perception:
  visibility:
    - operator: any
      conditions:
        - { operator: check, left: "$observer.location", op: "==",
            right: "$entity.location" }
        - { operator: check, left: "$observer.location", op: "==",
            right: "$entity.id" }
  event_scopes:
    same_location:
      rules:
        - { operator: check, left: "$observer.location", op: "==",
            right: "$event_source.location" }
  hidden_properties: ["private_stash", "goals", "mood"]

# Global: everyone sees everything (forum, debate)
perception:
  visibility: []
  hidden_properties: ["ip_address"]

# Social graph: see people you follow
perception:
  visibility:
    - { operator: check, left: "$entity.id", op: in,
        right: "relationships_of($observer, type=follows)" }
  hidden_properties: ["mood", "private_notes"]

# Sector-based (starship, large map)
perception:
  visibility:
    - { operator: check, left: "$observer.sector", op: "==",
        right: "$entity.sector" }
  hidden_properties: ["stress", "secret_orders"]

# Hybrid: ghosts see everything, mortals see by location
perception:
  visibility:
    - { operator: any, conditions: [
        { operator: check, left: "$observer.type_tag", op: "==", right: "ghost" },
        { operator: check, left: "$observer.district", op: "==",
          right: "$entity.district" }
      ]}
  hidden_properties: ["essence"]
```

#### Wake Summary

Controls what state info appears in agent wake notification messages. The server sends full perception to the gateway; `wake_summary` selects what to display in the text notification.

**Semantics:**
- Key absent → that section is not shown
- Empty list `[]` → show all fields (no filter)
- Non-empty list → show only listed fields
- No `wake_summary` at all → wake contains only events, no state

```yaml
perception:
  wake_summary:
    self_fields: [chips, hand, bet_this_round, folded]    # agent's own properties
    entities:                                               # entities by ID
      table: [pot, current_bet, phase, community_cards]
    entity_types:                                           # entities by type (dynamic)
      resource: [quantity, location]
    agent_fields: [chips, bet_this_round, folded]           # other agents' properties
```

| Key | Type | Purpose |
|-----|------|---------|
| `self_fields` | `list[str] \| null` | Which of the agent's own properties to show |
| `entities` | `dict[str, list[str]]` | Specific entities by ID + field filter |
| `entity_types` | `dict[str, list[str]]` | Match entities by type + field filter |
| `agent_fields` | `list[str] \| null` | Other agents' properties to show |

**Example wake message produced:**
```
[WORLDSEED SYSTEM] shark — tick 7
You: chips=990, hand=["9♥","4♠"], bet_this_round=10, folded=false
table: pot=150, current_bet=70, phase=pre_flop, community_cards=[], current_turn=shark
Others: rookie(chips=980, bet=20, folded=false) | hustler(chips=930, bet=70, folded=false)
Actions: fold, call, raise_bet, all_in, talk
- analyst folds.
- Your turn.
→ perceive then act.
```

**Wake summary patterns:**

```yaml
# Poker: show hand, table state, other players' chips
wake_summary:
  self_fields: [chips, hand, bet_this_round, folded]
  entities:
    table: [pot, current_bet, phase, community_cards, current_turn]
  agent_fields: [chips, bet_this_round, folded]

# Survival: show HP, nearby resources
wake_summary:
  self_fields: [hp, hunger, location, inventory]
  entities:
    generator: [fuel, running]
  entity_types:
    resource: [quantity]
  agent_fields: [hp, location]

# Social simulation: minimal state
wake_summary:
  self_fields: [mood, location, money]
  agent_fields: [mood, location]

# No wake summary: events only, agent must perceive for state
# (just omit wake_summary entirely)
```

---

### Push Wake -- Waking Sleeping Agents

Agents sleep between thinks (controlled by `think_interval`). Events with `push: true` wake them immediately. Direct messages always wake the target agent.

Push is set per-event, not globally. Add `push: true` to any event that demands immediate reaction:

```yaml
# In action events
actions:
  take:
    events:
      - { type: "take", detail: "$agent took $amount from $target",
          ttl: 1, scope: "same_location", push: true }

# In consequence effects
consequences:
  scarcity_alert:
    trigger: [...]
    effects:
      - { operator: emit_event, type: "scarcity",
          detail: "Food is running low", ttl: 5,
          scope: global, push: true }
```

Events without `push: true` are delivered to the inbox but do not wake the agent -- they see it on the next regular wake cycle.

For DM-generated events, use `push_events` on the DM config to auto-set push by event type:

```yaml
dm:
  hint: "Judge the outcome"
  push_events: ["emergency", "direct_address"]
```

**When to push vs when not to:**

| Event type | push? | Why |
|---|---|---|
| `say` | **NO** | Creates conversation cascade: A speaks -> B wakes -> B responds -> A wakes -> infinite loop. |
| `take` (shared resource) | YES | Someone taking food demands response. |
| Consequence: critical alert | YES | "Air filter failing" demands action. |
| `move` | NO | Routine. Agents learn about arrivals on next perceive. |
| Consequence: co-location | NO | Ambient awareness, not an emergency. |

```yaml
# BAD: creates conversation cascade
say:
  events:
    - { type: "say", detail: "$agent: $message", ttl: 2,
        scope: "same_location", push: true }

# GOOD: say is perceived passively
say:
  events:
    - { type: "say", detail: "$agent: $message", ttl: 2,
        scope: "same_location" }
```

---

### Sanity Checks -- The World Tests Itself

A list of scripted action sequences that verify the world works as designed. Like doctests for a scene config.

```yaml
sanity_checks:
  - name: "Human-readable test name"
    ticks: 5                              # Optional: advance N ticks before steps
    steps:
      # Submit an action
      - { agent: agent_id, action: action_name, params: {key: value} }

      # Assert a condition
      - { assert: "entity.key == expected_value" }

      # Expect an action to be rejected
      - { agent: agent_id, action: action_name, params: {}, expect: fail }

      # Repeat an action N times
      - { agent: agent_id, action: action_name, params: {amount: 10}, repeat: 5 }

      # Advance ticks mid-sequence
      - { ticks: 10 }
```

**Note:** `auto_tick` effects run every tick during sanity checks, including between steps and during `ticks:` advances. Account for this when writing assertions -- entity values may change between an action step and the next assert due to auto_tick.

#### Assertion syntax

```yaml
# Comparison operators
- { assert: "entity.key == value" }
- { assert: "entity.key != value" }
- { assert: "entity.key > 100" }
- { assert: "entity.key < 5" }
- { assert: "entity.key >= 0" }
- { assert: "entity.key <= 50" }

# String values (no quotes needed for simple strings)
- { assert: "agent.location == hallway" }

# Numeric values
- { assert: "resource.quantity == 17" }
```

#### Five categories of good sanity checks

A good sanity check suite covers all five. Skipping any category leaves real bugs undetected.

**1. Happy path** -- does the basic flow work?

```yaml
- name: "Full fishing loop"
  steps:
    - { agent: wu, action: move, params: {to: sea} }
    - { agent: wu, action: fish, params: {amount: 5} }
    - { assert: "wu.catch == 5" }
    - { agent: wu, action: move, params: {to: dock} }
    - { agent: wu, action: move, params: {to: market} }
    - { agent: wu, action: sell, params: {} }
    - { assert: "wu.catch == 0" }
    - { assert: "wu.gold == 15" }
```

**2. Rejections** -- does the engine say no when it should?

```yaml
- name: "Cannot fish on land"
  steps:
    - { agent: wu, action: fish, params: {amount: 1}, expect: fail }
    - { assert: "wu.catch == 0" }

- name: "Cannot move to unconnected space"
  steps:
    - { agent: wu, action: move, params: {to: sea} }
    - { agent: wu, action: move, params: {to: market}, expect: fail }
```

**3. Multi-agent** -- do agents interact correctly?

```yaml
- name: "Two agents fish from same stock"
  steps:
    - { agent: wu, action: move, params: {to: sea} }
    - { agent: mei, action: move, params: {to: sea} }
    - { agent: wu, action: fish, params: {amount: 10} }
    - { agent: mei, action: fish, params: {amount: 8} }
    - { assert: "wu.catch == 10" }
    - { assert: "mei.catch == 8" }
```

**4. Resource dynamics** -- does the economy work?

```yaml
- name: "Regeneration works without fishing"
  ticks: 10
  steps:
    - { assert: "fish.quantity > 200" }

- name: "Heavy fishing depletes stock"
  steps:
    - { agent: wu, action: move, params: {to: sea} }
    - { agent: wu, action: fish, params: {amount: 50}, repeat: 3 }
    - { assert: "wu.total_harvested == 150" }
```

**5. Consequences** -- do triggers fire?

```yaml
- name: "Low stock triggers warning"
  steps:
    - { agent: wu, action: move, params: {to: sea} }
    - { agent: wu, action: fish, params: {amount: 50}, repeat: 3 }
    - { assert: "fish.status == declining" }
```

#### Coverage checklist

Before marking a scene config as ready, verify:

- [ ] Every action has at least one happy-path test
- [ ] Every precondition has a rejection test
- [ ] At least one test uses a different agent (not just the first one)
- [ ] If the scene has resources, test depletion and regeneration
- [ ] If the scene has consequences, test at least one trigger
- [ ] If the scene has spatial movement, test that unreachable paths are rejected
- [ ] Edge cases: zero values, maximum values, empty params

#### Running sanity checks

```bash
# Validate everything (Level 1-5)
uv run worldseed validate config.yaml

# Just load + reference check (fast, no simulation)
uv run worldseed validate config.yaml --ticks 0
```

**Note on "unreachable" warnings:** Smoke tests check action executability in the **initial state only**. Actions gated by preconditions (e.g., `location == target_room`, `evidence >= 1`) will show "0 agents (unreachable in initial state)" if no agent meets the conditions at tick 0. This is expected for actions that require movement or prior actions before they become available.

---

## `narrator` — Auto-Narrator

An auto-created system agent that observes the entire world (omniscient) and periodically writes structured chapter summaries. The narrator is hidden from other agents and excluded from DSL queries.

**Default: on** — if you omit `narrator` from your config, the engine creates one with `style: "storyteller"` and `interval: 10`. Set `narrator: false` to disable.

### Syntax

```yaml
# Shorthand — style name
narrator: "storyteller"

# Disable
narrator: false

# Full form
narrator:
  style: "noir"           # see styles below (default: "storyteller")
  interval: 10            # Wake every N ticks (default: 10)
  prompt: null            # Custom prompt — overrides style if set
```

### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `style` | see styles below | `"storyteller"` | Built-in writing style preset |
| `interval` | `int` | `10` | How often the narrator wakes and writes a chapter (in ticks) |
| `prompt` | `string` \| `null` | `null` | Custom writing instructions. **Overrides `style`** — the two are mutually exclusive, not combined |

### Styles

- **`storyteller`** — Dramatic serial narrator. Balanced title pairs, rising tension, cliffhanger endings.
- **`poet`** — Minimal imagery, juxtaposition. One image per line, silence between stanzas.
- **`intel`** — Wire-service facts, bullet-point briefing. No adjectives, no commentary.
- **`noir`** — Hard-boiled narrator. Short sentences, atmospheric, weary precision.
- **`gossip`** — Second-hand narration. Mixes facts with speculation and "I heard from someone who..."
- **`conspiracy`** — Pattern-finding narrator. Draws connections between events, sees patterns everywhere.
- **`bureaucrat`** — Official documentation voice. Incident reports, procedural language, reference numbers.
- **`gameshow`** — Game show host. Agents are contestants, every choice is a wager, cheerfully cruel.
- **`trickster`** — Inside the chaos and loving it. Celebrates reversals, addresses the reader directly.

### How it works

The engine auto-registers a narrator agent with:
- `omniscient: true` — sees all entities, all properties (including hidden), all events (including admin-scoped)
- `system: true` — invisible to other agents, excluded from `$visible`, `count()`, and other DSL queries

The narrator submits a `narrate` action each interval, producing a `narration` event with scope `"admin"` (only visible on the dashboard, never to agents). The action has five fields: `title`, `tldr`, `body`, `asides` (things the reader sees but agents don't), and `whisper_options` (suggested interventions).

---

## Design Guide

World design checklists, action design, resource modeling, patterns, anti-patterns, and testing are documented in [SCENE_DESIGN.md](SCENE_DESIGN.md).
