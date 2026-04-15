# Scene Design Guide

How to write a good scene config. Patterns, anti-patterns, checklists, and testing.
For the config syntax reference, see [SCENE_CONFIG.md](SCENE_CONFIG.md).
For the DSL expression language, see [SCENE_DSL.md](SCENE_DSL.md).

---

## Design Guide

> Everything below is about WHEN and WHY, not WHAT. Every rule comes from observed agent behavior across 8+ rounds of live testing, not theory.

### World Design Checklist

Follow these steps to design a new scene. Quality gates are inline.

1. **What is the world about?** Write `scene.description`. One paragraph max.

2. **What exists?** List entities. Every entity needs `id` and `type`. Think about:
   - Spaces (if spatial) -- what connects to what?
   - Resources -- what is scarce? What is consumed?
   - Objects -- what can be used, taken, created?
   - **Quality gate:** Every space contains 2+ interactable entities (excluding agents). Rooms with nothing to touch produce agents that only `say`.

3. **Who are the characters?** Define agents with `character` cards and starting properties.
   - **Quality gate:** Agents start with asymmetric positions, goals, or information. Symmetric starts converge to polite consensus in ~5 ticks.
   - **Quality gate:** At least 1 agent goal that conflicts with the group.

4. **What can agents do?** Define actions. For each: preconditions, effects, events.
   - **Quality gate:** 5-8 actions is the sweet spot. Use `attempt` as the overflow valve.

5. **What happens automatically?** Auto-tick for consumption, decay, growth. Guard decrements.
   - **Quality gate:** At least 2 independent systems degrade via `auto_tick`.

6. **What does the world detect?** Consequences for thresholds, co-location, state transitions.

7. **Who sees what?** Perception rules -- the most important design decision.
   - Spatial? Graph? Global? Hybrid?
   - What properties are hidden?
   - How do events propagate?
   - **Quality gate:** At least 1 hidden property or secret. At least 1 resource with numeric `quantity` and a meaningful `unit`.

8. **What wakes sleeping agents?** Push rules for important events. Never push `say`.

9. **Write sanity checks.** Cover all 5 categories.

10. **Validate.** Run `uv run worldseed validate <config.yaml>`. All levels should pass.

**Should also have:**
- [ ] Discoverable items not visible at first glance (locked cabinet, hidden panel)
- [ ] At least 1 multi-step interaction chain (observe -> learn requirement -> attempt with tool -> verify)
- [ ] Multiple spaces (3-5 is the sweet spot)

**Why environmental density matters:** In testing, identical character cards in an empty environment produced 42% say, 9% attempt. The same characters in an enriched environment produced 4% say, 40% attempt. The world determines behavior, not the character card.

**Minimum viable survival config:**

```yaml
entities:
  - id: main_hall
    type: space
    connects_to: [storage, outside]

  - id: storage
    type: space
    connects_to: [main_hall]

  - id: outside
    type: space
    connects_to: [main_hall]
    danger_level: high

  - id: food_supply
    type: resource
    quantity: 15
    unit: "person-days"
    located_in: [storage]

  - id: generator
    type: equipment
    condition: 60
    status: "running"
    located_in: [main_hall]

  - id: locked_box
    type: item
    description: "A rusted metal box with a broken latch"
    located_in: [storage]
    contents: "unknown"       # DM reveals on observe

  - id: toolkit
    type: tool
    quantity: 2
    located_in: [storage]
```

---

### Action Design

#### Action vocabulary size

5-8 actions is the sweet spot. Below 5, agents lack expressive range. Above 10, agents struggle to choose and the DM struggles to differentiate. Use `attempt` as the overflow valve.

**When to create a dedicated action vs rely on `attempt`:**
- Deterministic effects (increment, decrement, set) -> dedicated action with DSL effects
- Mechanically enforced preconditions (must be at location X, must have quantity > 0) -> dedicated action
- Purely narrative, situational outcome -> `attempt` is fine

#### Observe must be actionable

The DM hint for `observe` determines whether agents learn that `observe` is useful or useless:

```yaml
# BAD: produces flavor text, agents stop observing
observe:
  dm:
    hint: "Describe what the agent sees."

# GOOD: produces intelligence, agents keep observing
observe:
  dm:
    hint: >
      Describe what the agent discovers. Include hidden details,
      current condition, and anything actionable. If observing
      equipment, report its current state and what might fix it.
```

#### Attempt needs a target param

Without a `target` param, the DM has no anchor entity. Two agents attempting to repair the same equipment get resolved independently with no coordination context. Always include an optional target.

#### Event TTL guidelines

Short TTLs (1-2) for routine events (speech, movement). Medium TTLs (3-5) for warnings. `"permanent"` only for irreversible state changes (ecosystem collapse, relationship broken beyond repair). Warnings should fade. Status effects should be ongoing, not permanent events.

---

### Resource & Tool Modeling

#### Resource lifecycle

| Pattern | Entity type | Key property | Consumed? | Example |
|---|---|---|---|---|
| Depletable supply | `resource` | `quantity` (numeric) | Yes, by actions + auto_tick | food_supply, water_supply |
| Consumable tool | `tool` | `quantity` (numeric) | Yes, by DM on use | duct_tape, bandages |
| Durable tool | `tool` | `quantity: 1` | No, reusable | wrench, wire_cutters |
| Stateful item | `item` | `condition` (string/number) | No, state changes | radio, locked_box |
| Degrading equipment | `equipment` | `condition` (numeric) | Degrades via auto_tick | air_filter, water_recycler |

#### The infinite tool problem

Modeling tools as string lists creates infinite-use items that trivialize every challenge:

```yaml
# BAD: tools as capability flags -- never runs out
- id: engineer
  type: agent
  tools: ["wrench", "duct_tape"]

# GOOD: tools as finite entities
- id: duct_tape
  type: tool
  description: "Roll of duct tape, partially used"
  quantity: 3
  located_in: [storage_room]

- id: wrench
  type: tool
  description: "Heavy wrench from a rusty toolbox"
  quantity: 1
  located_in: [storage_room]
```

Then in the DM hint: "Check tool quantities before use (quantity must be > 0). Decrement quantity for consumable tools (duct_tape, bandages). Do NOT decrement durable tools (wrench, wire_cutters)."

#### Guard with constraints

DM hints are advisory -- the DM can still return an effect that sets `quantity: -2`. Use entity-level `constraints` as a hard floor so the engine clamps invalid values automatically:

```yaml
- id: duct_tape
  type: tool
  quantity: 3
  constraints:
    quantity: { min: 0 }

- id: air_filter
  type: equipment
  condition: 70
  constraints:
    condition: { min: 0, max: 100 }
```

This protects against DM over-decrement, double-consume bugs, and auto_tick overshoot. Constraints are enforced on all write paths, so a single declaration covers every source of change.

#### Tool proximity matters

Keep tools near the problems they solve. Testing showed agents attempt repairs ~3x more often when tools and targets share a room. If the wrench is in storage and the failing equipment is in the hallway, five steps are needed, making `say` relatively more attractive.

#### Location matters for resources

Resources must be `located_in` a specific space. Without it, agents can take resources from anywhere, eliminating movement as a cost and removing spatial strategy entirely.

---

### Urgency & Consequence Design

#### The core pattern: degradation + tiered consequences

Auto_tick creates the clock. Consequences create awareness of the clock.

```yaml
auto_tick:
  - description: "Air filter degradation"
    effects:
      - { operator: decrement, target: "air_filter.condition", by: 1, min: 0 }

consequences:
  # Tier 1: Early warning. Local scope. No push.
  air_quality_notice:
    trigger:
      - { operator: check, left: "air_filter.condition", op: "<", right: 50 }
    effects:
      - { operator: emit_event, type: "maintenance",
          detail: "Air filter indicator has turned yellow.",
          ttl: 3, scope: "same_location" }
    frequency: on_change

  # Tier 2: Critical alert. Global scope. Push.
  air_quality_warning:
    trigger:
      - { operator: check, left: "air_filter.condition", op: "<", right: 30 }
    effects:
      - { operator: emit_event, type: "air_warning",
          detail: "Air quality deteriorating -- filter needs maintenance NOW",
          ttl: 5, scope: "global", push: true }
    frequency: on_change

  # Tier 3: Catastrophe. Permanent. Real state change.
  air_filter_failure:
    trigger:
      - { operator: check, left: "air_filter.condition", op: "<=", right: 0 }
    effects:
      - { operator: set, target: "air_filter.status", value: "failed" }
      - { operator: emit_event, type: "catastrophe",
          detail: "Air filtration has failed. Breathing is difficult.",
          ttl: "permanent", scope: "global", push: true }
    frequency: on_change
```

**Why three tiers:** Without an intermediate warning, agents go from "everything is fine" to "catastrophe" in one step. The warning tier gives agents information and time to act.

#### Degradation rate math

Compute ticks-to-crisis before shipping:

```
air_filter: starts 70, degrades 1/tick
  Tier 1 (< 50):  tick 20  -> ~10 hours at 30min/tick
  Tier 2 (< 30):  tick 40  -> ~20 hours
  Tier 3 (<= 0):  tick 70  -> ~35 hours

With 3 agents, roughly:
  60 agent-actions before first warning
  120 agent-actions before critical
  210 agent-actions before failure
```

If agents hit Tier 3 before taking ~30 actions, lower the rate. If they never reach Tier 1, raise it.

#### Competing urgencies

A single crisis is solvable. Two simultaneous crises create dilemmas. Design at least two independent degrading systems that drain at different rates. Spatial separation amplifies the dilemma.

#### Regeneration with collapse threshold

Resources that regenerate proportionally can hit a point of no return when they reach zero:

```yaml
auto_tick:
  - description: "Fish regeneration"
    effects:
      - { operator: increment, target: "fish.quantity",
          by: "0.05 * fish.quantity" }
    condition:
      - { operator: check, left: "fish.quantity", op: ">", right: 0 }
consequences:
  ecosystem_collapse:
    trigger:
      - { operator: check, left: "fish.quantity", op: "<=", right: 0 }
    effects:
      - { operator: set, target: "fish.regenerating", value: false }
      - { operator: emit_event, type: catastrophe,
          detail: "Fish population extinct",
          ttl: permanent, scope: global }
    frequency: on_change
```

---

### Design Patterns

#### Scarce resources drive conflict

```yaml
entities:
  - id: food
    type: resource
    quantity: 20
auto_tick:
  - description: "Everyone eats"
    effects:
      - { operator: decrement, target: "food.quantity",
          by: "0.1 * count(type=agent)", min: 0 }
consequences:
  scarcity:
    trigger:
      - { operator: check, left: "food.quantity", op: "<", right: 5 }
    effects:
      - { operator: emit_event, type: scarcity, detail: "Food running out",
          ttl: 5, scope: global }
    frequency: on_change
```

#### Topology creates chokepoints

```yaml
entities:
  - id: north
    type: space
    connects_to: [crossroads]
  - id: south
    type: space
    connects_to: [crossroads]
  - id: east
    type: space
    connects_to: [crossroads]
  - id: crossroads
    type: space
    connects_to: [north, south, east]
# Anyone controlling crossroads controls movement
```

#### Hidden information creates drama

```yaml
agents:
  - id: insider
    location: office
    knows_secret: true
    secret_content: "water supply is poisoned"
    character:
      secret: "You know the water is poisoned but telling would implicate you"
perception:
  hidden_properties: ["knows_secret", "secret_content"]
# Other agents cannot see the secret -- insider must choose to share or exploit
```

#### Reputation through relationships

```yaml
# No global score. Trust exists between pairs.
agents:
  - id: agent_a
    relationships:
      - { type: trusts, target: agent_b, value: 80 }
      - { type: trusts, target: agent_c, value: 20 }
actions:
  vouch_for:
    description: "Publicly vouch for someone's trustworthiness"
    params: [{ name: target, type: entity_ref, required: true }]
    effects: []
    events:
      - { type: vouch, detail: "$agent vouches for $target", ttl: 5,
          scope: same_location }
    dm:
      hint: "Determine how the vouch shifts trust values based on reputation."
```

---

### Anti-Patterns

| Anti-pattern | Symptom | Root cause | Fix |
|---|---|---|---|
| **Talking Head World** | 40%+ of actions are `say`. | No interactable objects, no degradation, no urgency. | Add entities with changeable state. Add auto_tick + consequences. |
| **Conversation Cascade** | Rapid back-and-forth `say` dominates event feed. | `say` has `push: true`. | Remove push from say. Reserve push for physical/urgent events. |
| **God DM** | `attempt` resolves every problem easily. | DM hint too permissive. No tool quantity checks. | Write hints that constrain: check quantities, decrement on use, be realistic. |
| **Shallow Characters** | All agents behave identically. Polite consensus. | 2-line character cards. LLMs default to cooperative behavior. | Use the full character card template. Every drive must be action-prompting. |
| **Symmetric World** | Nothing interesting happens. Immediate consensus. | All agents start in same room with same goals. | Asymmetry in 3 dimensions: starting position, goals, capabilities. |
| **Leaky Abstraction** | Properties that do nothing. `door.strength: 80` unreferenced. | Decorative numbers create false expectations. | Every numeric property must be referenced by something. If nothing reads it, delete it. |
| **No-Observability Trap** | Agents cannot tell if actions worked. Random behavior. | Too many hidden_properties, or state changes without events. | Hide motivation (goals, secrets). Reveal state (condition, quantity). |

---

### Testing Your Config

#### Static validation

```bash
uv run worldseed validate configs/your_config.yaml
```

Fix every error. Warnings are often real problems.

#### The 10-tick behavioral test

After sanity checks pass, run the server with real agents for 10 ticks. Check:

- [ ] At least one agent used `observe` on an entity (not just talked)
- [ ] At least one agent used `attempt` or a domain-specific action
- [ ] At least one agent moved between locations
- [ ] No agent said the same thing more than twice
- [ ] A consequence fired and agents reacted to it

#### Behavioral symptom table

If the 10-tick test fails, diagnose:

| Symptom | Likely cause | Fix |
|---|---|---|
| Agents only `say` | Empty rooms, nothing to interact with | Add items, tools, equipment per space |
| Agents all wake at once, talk forever | `say` has `push: true` | Remove push from say |
| Agents announce goals but never act | Abstract drives ("be fair") | Rewrite drives as concrete actions |
| Agent uses same tool infinitely | Tool modeled as capability | Model tools with `quantity` |
| No urgency, agents plan endlessly | No degrading systems | Add auto_tick + consequence tiers |
| DM creates phantom items | `attempt` hint missing guidance | Add create_entity to hint + allowed_ops |
| DM gives same result for repeated repairs | No target param on attempt | Add optional target param |
| Agent does nothing for many ticks | Character card too vague | Add action-prompting drives and relationships |

---
