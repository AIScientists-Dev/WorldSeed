# Scene DSL Reference

The expression language used in preconditions, effects, consequences, and auto_tick.
For the config structure that uses these expressions, see [SCENE_CONFIG.md](SCENE_CONFIG.md).
For design patterns and quality guidelines, see [SCENE_DESIGN.md](SCENE_DESIGN.md).

---


#### Precondition DSL

```yaml
# check: compare two values
- { operator: check, left: EXPR, op: COMPARISON, right: EXPR }
#   EXPR: "$agent.location", "$to", "relationships_of(...)", number, string
#   COMPARISON: ==, !=, >, <, >=, <=, in, contains

# exists: is the expression truthy? (not None, not empty list, not empty string)
- { operator: exists, expression: EXPR }

# not: negate a single condition
- { operator: not, condition: { operator: check, ... } }

# all: AND (a precondition list is implicitly an "all")
- { operator: all, conditions: [ ... ] }

# any: OR
- { operator: any, conditions: [ ... ] }
```

**Comparison operators:**

| Op | Meaning | Notes |
|---|---|---|
| `==` | Equal | Works for strings, numbers, booleans, None |
| `!=` | Not equal | |
| `>` `<` `>=` `<=` | Numeric comparison | Returns false if either side is None or non-numeric |
| `in` | Left is member of right list | Right must be a list |
| `contains` | Right is member of left list | Left must be a list |

#### Effect DSL

```yaml
# set: change a property
- { operator: set, target: "entity.key", value: EXPR }

# increment: increase a number (null treated as 0)
- { operator: increment, target: "entity.key", by: EXPR }
- { operator: increment, target: "entity.key", by: EXPR, min: 0, max: 100 }

# decrement: decrease a number (null treated as 0)
- { operator: decrement, target: "entity.key", by: EXPR }
- { operator: decrement, target: "entity.key", by: EXPR, min: 0 }

# create_entity: add a new entity to the world
- { operator: create_entity, id: "new_id", type: "object",
    properties: { key: value } }

# remove_entity: delete an entity (cleans dangling relationships)
- { operator: remove_entity, target: "entity_id" }

# add_relationship: add/update a relationship (upsert)
- { operator: add_relationship, from: "entity_a", type: "trusts",
    to: "entity_b", value: 50 }

# remove_relationship: remove a relationship edge
- { operator: remove_relationship, from: "entity_a", type: "trusts",
    to: "entity_b" }

# emit_event: create a perceivable event
- { operator: emit_event, type: "theft",
    detail: "$agent stole $amount from $target",
    ttl: 3, scope: "same_location" }

# emit_event with highlight — appears as chapter marker in observer dashboard
- { operator: emit_event, type: "victory",
    detail: "The heist succeeded!",
    ttl: 5, scope: "global", highlight: true }
```

**`min` / `max` clamp (increment and decrement only):**

Optional floor and ceiling for the resulting value. The engine computes the new value first, then clamps. Use `min: 0` to prevent negative quantities. Use both for bounded ranges:

```yaml
# Prevent negative food
- { operator: decrement, target: "food.quantity", by: 1, min: 0 }

# Clamp health between 0 and 100
- { operator: increment, target: "$agent.health", by: 10, min: 0, max: 100 }
```

**`event_target` (emit_event only):**

Directs an event to a specific agent. The targeted agent receives it as a direct message in addition to any scope-based delivery:

```yaml
- { operator: emit_event, type: "whisper",
    detail: "$agent whispers to $to",
    ttl: 1, scope: "target_only",
    event_target: "$to" }
```

**`by` in increment/decrement** can be an expression:

```yaml
by: 3                                    # literal
by: "$amount"                            # param reference
by: "0.1 * count(type=agent)"            # arithmetic with function
```

**List operations:**

Three operators for manipulating list-valued properties:

```yaml
# list_append: add an element to a list (creates list if property is None)
- { operator: list_append, target: "$agent.inventory", value: "sword" }

# list_remove: remove first occurrence from a list (warns if not found)
- { operator: list_remove, target: "$agent.inventory", value: "sword" }

# list_pop_random: randomly move one element from source list to target list
# Useful for dealing cards, random loot, etc.
- { operator: list_pop_random, source: "deck.cards", target: "$agent.hand" }
```

`list_pop_random` uses `source` (the list to pick from) and `target` (the list to add to). The picked element is removed from source and appended to target atomically.

**rotate — advance a property through a sequence:**

```yaml
# Advance to the next role in the night turn order, skipping dead roles
- operator: rotate
  target: "game.active_role"
  sequence: "game.role_order"     # path to list: [werewolf, seer, witch, hunter]
  skip: "game.dead_roles"         # path to list of values to skip (optional)

# After a poker raise: advance to next player from raiser's position, skip folded
- operator: rotate
  target: "table.active_seat"
  sequence: "table.seat_order"
  skip: "table.out_seats"
  value: "$agent.id"              # start from this position instead of current (optional)
```

`rotate` advances `target` to the next value in `sequence` (a list property), wrapping around at the end. If `skip` is provided, entries present in that list are skipped. If `value` is provided, rotation starts from that position instead of the current value of `target`. If the current value is not found in the sequence, rotation starts from the beginning. If all entries are skipped, no change occurs.

Useful for turn-based games: night role rotation (werewolf), seat rotation (poker), speaker rotation (debate).

**for_each — iterate entities and apply sub-effects:**

```yaml
# Deal a card to every non-folded player
- operator: for_each
  match: { type: agent }
  where: "role == player AND folded == false"
  effects:
    - { operator: list_pop_random, source: "deck.cards", target: "$entity.hand" }

# Reset all players' bets to 0
- operator: for_each
  match: { type: agent }
  where: "role == player"
  effects:
    - { operator: set, target: "$entity.bet_this_round", value: 0 }
```

`match` selects entities by properties (required: `type`). `where` is an optional filter string with `AND` support. Inside sub-effects, `$entity` refers to the current iteration entity. `for_each` is not allowed in DM responses (DM cannot iterate).

`for_each` works in action effects, consequence effects, AND auto_tick effects:

```yaml
auto_tick:
  - description: "All equipment degrades"
    effects:
      - operator: for_each
        match: { type: equipment }
        where: "status == active"
        effects:
          - { operator: decrement, target: "$entity.condition", by: 1, min: 0 }
```

#### Events shorthand

The `events` list on an action is syntactic sugar for `emit_event` effects. These two are equivalent:

```yaml
# Using events shorthand
events:
  - { type: "move", detail: "$agent moved to $to", ttl: 1, scope: "same_location" }

# Using explicit emit_event effect
effects:
  - { operator: emit_event, type: "move", detail: "$agent moved to $to",
      ttl: 1, scope: "same_location" }
```

Events from the `events` list are appended **after** all explicit effects. The shorthand also supports `target` (maps to `event_target`) and `push`.

#### DM configuration

The `dm` field on an action escalates judgment to an LLM Dungeon Master. The DM receives world state + the action, and returns structured effects + a narrative.

**DM is stateless.** Each DM call is independent — the DM sees the current world snapshot, nothing more. Any information that must persist across ticks or be referenced by multiple actions must be stored in entity state (properties), not relied on the DM to remember. DM makes decisions; state records results. Example: in a card game, dealt cards must be stored as entity properties (removed from deck, added to hand) — if they only exist in a DM response, the next DM call won't know what was already dealt.

```yaml
dm:
  hint: string            # What to judge. The most important field.
  scope: string           # Event scope for DM narrative. Default: "same_location".
  allowed_ops: [string]   # Which effect operators the DM may use.
                          # Default: [set, increment, decrement, emit_event].
  max_effects: number     # Maximum effects per judgment. Default: 5.
  push_events: [string]   # Event types that should push-wake agents.
```

**`push_events`:** When the DM emits events, any event whose `type` is in this list will have `push: true` set automatically. This lets the DM generate urgent events without hard-coding push in effect definitions:

```yaml
attempt:
  dm:
    hint: "Judge the physical outcome."
    push_events: ["emergency", "discovery"]
    # If the DM emits a type:"emergency" event, it will push-wake agents
```

**DM validation and retry:** The engine validates every DM response before applying it. Checks include: effect count within `max_effects`, each operator in `allowed_ops`, and entity existence for targeted effects. If validation fails, the engine sends the error reason back to the DM as `error_feedback` and retries once (2 attempts total). If both attempts fail, a fallback narrative ("The outcome is unclear.") is emitted.

**DM narrative emission:** After applying valid DM effects, the engine always emits a `dm_narrative` event with the DM's narrative text. This event uses the `scope` from the DM config and has `ttl: 3`. Agents perceive it like any other event.

#### Common action patterns

```yaml
# Movement (spatial world)
move:
  description: "Move to a connected space"
  params:
    - { name: to, type: entity_ref, required: true,
        enum_from: "relationships_of($agent.location, type=connects_to)",
        description: "Space ID from connects_to" }
  preconditions:
    - { operator: check, left: "$to", op: in,
        right: "relationships_of($agent.location, type=connects_to)" }
  effects:
    - { operator: set, target: "$agent.location", value: "$to" }
  events:
    - { type: move, detail: "$agent moved to $to", ttl: 1, scope: same_location }

# Taking a resource
take:
  description: "Take from a resource at your location"
  params:
    - { name: target, type: entity_ref, required: true }
    - { name: amount, type: number, required: true }
  preconditions:
    - { operator: check, left: "$target.location", op: "==",
        right: "$agent.location" }
    - { operator: check, left: "$target.quantity", op: ">=", right: "$amount" }
  effects:
    - { operator: decrement, target: "$target.quantity", by: "$amount" }
    - { operator: increment, target: "$agent.inventory.$target", by: "$amount" }
  events:
    - { type: take, detail: "$agent took $amount from $target", ttl: 1,
        scope: same_location }

# Speaking (no state change, only event)
say:
  description: "Speak to nearby agents"
  params: [{ name: message, type: free_text, required: true }]
  preconditions: []
  effects: []
  events:
    - { type: say, detail: "$agent: $message", ttl: 2, scope: same_location }

# Trading (give resource to another agent)
give:
  description: "Give something to another agent"
  params:
    - { name: target, type: entity_ref, required: true }
    - { name: resource, type: entity_ref, required: true }
    - { name: amount, type: number, required: true }
  preconditions:
    - { operator: check, left: "$target.location", op: "==",
        right: "$agent.location" }
    - { operator: check, left: "$agent.inventory.$resource", op: ">=",
        right: "$amount" }
  effects:
    - { operator: decrement, target: "$agent.inventory.$resource", by: "$amount" }
    - { operator: increment, target: "$target.inventory.$resource", by: "$amount" }
  events:
    - { type: give, detail: "$agent gave $amount $resource to $target", ttl: 2,
        scope: same_location }

# Free-form attempt (escalates to DM)
# RECOMMENDED: Every scene should include `attempt`. Without it, agents can
# only do predefined actions and will refuse creative instructions.
# See configs/template.yaml for a ready-to-copy version.
attempt:
  description: "Try anything not covered by other actions"
  params:
    - { name: description, type: free_text, required: true }
    - { name: target, type: entity_ref, required: false,
        enum_from: "$visible",
        description: "Entity you are acting on (optional)" }
  preconditions: []
  effects: []
  events: []
  dm:
    hint: >
      Judge the physical outcome. Check tool quantities before use
      (quantity must be > 0). Decrement consumable tool quantity when used.
      If the agent searches and finds new items, use create_entity.
      Do NOT reference entities that do not exist in world state.
      Be realistic about what is physically possible.
    allowed_ops: [set, increment, decrement, emit_event, create_entity]

# Observation (DM describes what you see)
observe:
  description: "Look closely at something"
  params:
    - { name: target, type: entity_ref, required: true,
        enum_from: "$visible" }
  preconditions:
    - { operator: check, left: "$target.location", op: "==",
        right: "$agent.location" }
  effects: []
  events: []
  dm:
    hint: >
      Describe what the agent discovers. Include hidden details,
      current condition, and anything actionable. If observing
      equipment, report its current state and what might fix it.

# Voting (non-spatial)
vote:
  description: "Cast a vote on a proposal"
  params:
    - { name: proposal, type: entity_ref, required: true }
    - { name: choice, type: string, required: true }
  preconditions:
    - { operator: not, condition:
        { operator: check, left: "$agent.has_voted_$proposal", op: "==",
          right: true } }
  effects:
    - { operator: set, target: "$agent.has_voted_$proposal", value: true }
    - { operator: increment, target: "$proposal.votes_$choice", by: 1 }
  events:
    - { type: vote, detail: "$agent voted on $proposal", ttl: 1, scope: global }
```

---

### DSL Function Reference

These functions are available in any DSL expression (preconditions, effects, enum_from).

#### relationships_of

```
relationships_of(entity_expr, type=REL_TYPE)
relationships_of(entity_expr, type=REL_TYPE, to=TARGET)
relationships_of(entity_expr, type=REL_TYPE, to=TARGET, value)
```

| Mode | Returns | Example |
|---|---|---|
| Basic | List of target entity IDs | `relationships_of($agent.location, type=connects_to)` -> `["hallway", "storage"]` |
| Targeted | `[TARGET]` if relationship exists, else `[]` | `relationships_of($agent, type=trusts, to=$target)` -> `["agent_b"]` or `[]` |
| Value | The relationship value (number, string, etc.) | `relationships_of($agent, type=trusts, to=$target, value)` -> `80` |

#### count

```
count(type=ENTITY_TYPE)
count(type=ENTITY_TYPE, where=CONDITION)
```

Counts entities matching the type, optionally filtered by a property condition. Compound conditions supported with `AND`:

```yaml
# How many agents exist
by: "0.1 * count(type=agent)"

# Agents at a specific location
- { operator: check,
    left: "count(type=agent, where=location == reactor)",
    op: ">", right: 0 }

# Compound: agents at reactor who are NOT folded
- { operator: check,
    left: "count(type=agent, where=location == reactor AND folded == false)",
    op: ">", right: 0 }
```

#### sum

```
sum(type=ENTITY_TYPE, property=PROP_NAME)
sum(type=ENTITY_TYPE, property=PROP_NAME, where=CONDITION)
```

Aggregates a numeric property across all matching entities:

```yaml
# Total gold across all traders
- { operator: check,
    left: "sum(type=agent, property=gold)",
    op: "<", right: 100 }
```

#### max_by

```
max_by(type=ENTITY_TYPE, property=PROP_NAME)
max_by(type=ENTITY_TYPE, property=PROP_NAME, where=CONDITION)
```

Returns the entity ID with the largest numeric value of `property` across the matching entities, or `""` when there is a tie or no matching entity. The `""` sentinel is intentional — a consequence can branch on it to ask the director for a tiebreak.

```yaml
# Pick the agent with most influence
- { operator: set, target: "winner.id",
    value: "max_by(type=agent, property=influence)" }
```

#### max_by_key

```
max_by_key(PATH)
```

Same idea as `max_by`, but operating on a dict-shaped property. Returns the key whose value is largest, or `""` on tie / empty / non-numeric values. Useful for vote tallies and similar dictionary aggregations:

```yaml
# Winner of a vote stored as { yes: 3, no: 2, abstain: 1 }
- { operator: set, target: "vote.winner",
    value: "max_by_key(vote.tally)" }
```

#### event

```
event(type=EVENT_TYPE)
```

Returns a list of matching events from the event log. Each event is a dict with `tick`, `type`, `source`, `detail`, `ttl`, `scope`. Useful in preconditions to check if something has happened:

```yaml
# Check if an alarm has been raised
- { operator: exists, expression: "event(type=alarm)" }
```

#### events_since

```
events_since(type=EVENT_TYPE, max_age_ticks=N)
```

Returns events of the given type within the last `N` ticks (inclusive on the lower bound). Use this for time-windowed detection — "any X in the last few ticks":

```yaml
# Fire if no progress event in 10 ticks
- { operator: not,
    condition: { operator: exists,
                 expression: "events_since(type=progress, max_age_ticks=10)" } }
```

#### last_event_tick

```
last_event_tick(type=EVENT_TYPE)
```

Returns the highest tick at which an event of that type was seen, or `-1` if none. Combine with `$tick` to express "ticks since last X":

```yaml
# 20 ticks since last accepted paper → convergence
- { operator: check,
    left: "$tick - last_event_tick(type=paper_accepted)",
    op: ">=", right: 20 }
```

The `-1` cold-start sentinel makes the comparison fire after enough total ticks even if the event never happened, which is usually what you want for timeouts.

#### random

```
random(min, max)
```

Returns a random integer in `[min, max]` inclusive. Arguments are resolved as DSL expressions, so they can reference properties or functions:

```yaml
# Roll a die
value: "random(1, 6)"

# Random damage based on attacker count
by: "random(1, count(type=agent, where=role == attacker))"

# 30% chance (random(1,100) <= 30)
- { operator: check, left: "random(1, 100)", op: "<=", right: 30 }
```

Uses true randomness (Python `random.randint`), not DM judgment.

#### length

```
length(EXPR)
```

Returns the length of a list or string. If the value is None, returns 0:

```yaml
# Check if agent has cards
- { operator: check, left: "length($agent.hand)", op: ">", right: 0 }

# Check deck has enough cards
- { operator: check, left: "length(deck.cards)", op: ">=", right: 5 }
```

#### Path expression syntax

| Expression | Resolves to |
|---|---|
| `$agent` | The acting agent's entity ID |
| `$agent.location` | The agent's `location` property |
| `$param_name` | An action parameter value |
| `$param_name.x` | Property `x` of the entity referenced by param |
| `entity_id.x` | Direct entity property access |
| `entity_id.nested.path` | Nested property via dot path |
| `$tick` | Current tick number |
| `$entity` | Current entity in consequence iteration |

`$param` references are resolved BEFORE path splitting, so embedded params work: `$agent.inventory.$resource` resolves to e.g. `old_chen.inventory.food`.

#### Arithmetic

Five arithmetic operators are supported: `+`, `-`, `*`, `//` (floor division), `%` (modulo). Standard precedence: `*`, `//`, `%` bind tighter than `+`, `-`. Operands can be any DSL expression:

```yaml
by: "0.1 * count(type=agent)"                    # number * function
by: "food_supply.quantity - 5"                    # entity property - literal
by: "table.current_bet - $agent.bet_this_round"   # entity - entity
value: "$tick % 5"                                # modulo (useful for phases)
value: "total_score // count(type=agent)"          # floor division (average)
value: "$agent.gold + 100"                        # addition
```

Division by zero (`//` or `%` with 0 divisor) returns 0 with a warning.

