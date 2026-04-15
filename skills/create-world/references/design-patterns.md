# Design Patterns & Anti-Patterns

**Structure:** Patterns (what to do) → Implementation Guidance → Anti-Patterns (what not to do). Anti-patterns are tested across 65+ runs — read those first if short on time.

## What Makes a World Interesting

These are the core mechanics that create tension, strategy, and emergence. Combine multiple patterns for richer worlds.

### Core Patterns

1. **Information Asymmetry** — Each agent knows different things. Use `hidden_properties` and `perception.visibility` rules. When agents must decide with incomplete information, they develop strategies, bluff, and negotiate.

2. **Resource Scarcity** — Not enough to go around. Use `auto_tick` to continuously deplete critical resources. Scarcity forces prioritization, competition, and cooperation.

3. **Hidden Roles** — Some agents aren't who they appear to be. Put the real objective in `character.secret`. Surface behavior and true goals diverge, creating dramatic tension.

4. **Conflicting Goals** — Agents want incompatible things. One agent's success requires another's loss. This creates negotiation, alliance formation, and betrayal.

5. **Time Pressure** — A countdown entity decremented by `auto_tick`. Deadlines force action and prevent infinite deliberation. Use consequences to trigger phase changes when timers hit zero.

6. **Evaluation & Judgment** — A judge agent (or DM) evaluates output. Agents must perform under scrutiny. Quality gates via preconditions (e.g., `quality >= 70` to advance).

7. **Rule Constraints** — Preconditions that prevent agents from doing whatever they want. Constraints force creative solutions. A world without preconditions is just a chatroom.

8. **Hidden Structure** — The world has rules or countdowns agents don't know about. They must discover the rules through experimentation. Use hidden entities or hidden properties on world-state entities.

9. **Automatic Evolution** — `auto_tick` and `consequences` make the world change on its own. Resources decay, infections spread, prices fluctuate, deadlines approach — even if no agent acts.

10. **Parallel Comparison** — Same world, same starting conditions, different rules or strategies. Run multiple instances and let state tell you which approach works. Useful for comparing philosophies, management styles, economic systems, or any "which way is better?" question.

### Coordination Patterns

Not all worlds are dramatic. Some are operational — agents doing real work that needs to be coordinated. These patterns apply when agents have their own tools and capabilities, and WorldSeed manages the interaction layer.

11. **Dependency Chain** — Task B cannot start until Task A is done. Preconditions enforce sequencing: `status == "done"` gates the next action. Creates natural pressure: downstream agents are blocked, upstream agents feel urgency. No drama needed — the dependency IS the tension.

12. **Peer Review Gate** — An agent cannot approve its own work. `assigned_to != $agent` as a precondition. Forces collaboration and catches errors. The DM can judge quality on review actions. Creates a natural feedback loop: submit → review → revise or approve.

13. **Shared Resource Contention** — Multiple agents compete for the same limited resource (time slots, budget, compute, shared equipment). A `claim` action sets `status: claimed`, making it unavailable to others via preconditions. First-come-first-served creates natural urgency. No hidden information needed — the contention is visible and real.

### Conditional Escalation

Chain consequences that escalate automatically: state change → consequence → escalating pressure → crisis. Each link is engine-enforced. Agents can prevent the cascade by acting or suffer it by inaction.

```yaml
# When quiet hours is repealed AND it's nighttime → noise rises automatically
noise_without_quiet_hours:
  trigger:
    - { operator: check, left: "rule_quiet_hours.status", op: "!=", right: "active" }
    - { operator: check, left: "apartment.hour", op: ">=", right: 22 }
  effects:
    - { operator: increment, target: "apartment.noise_level", by: 4, max: 100 }
  frequency: every_tick

# High noise at night → building complaints accumulate
building_noise_complaint:
  trigger:
    - { operator: check, left: "apartment.noise_level", op: ">=", right: 8 }
  effects:
    - { operator: increment, target: "apartment.building_warnings", by: 1 }
  frequency: on_change

# 3 complaints → eviction crisis
eviction_crisis:
  trigger:
    - { operator: check, left: "apartment.building_warnings", op: ">=", right: 3 }
  effects:
    - operator: for_each
      match: { type: agent }
      effects:
        - { operator: decrement, target: "$entity.happiness", by: 25, min: 0 }
  frequency: on_change
```

## Implementation Guidance

### Moderator Agent Pattern

When a scenario has structured flow (turns, phases, voting rounds), consider a **moderator agent** that controls progression. The moderator is an LLM agent with special actions: advance turns, call votes, announce results, declare winners.

**Critical rule: moderator actions MUST have preconditions, not just playbook instructions.** LLM agents will rush through phases if not constrained by the engine. The playbook tells the moderator WHAT to do; preconditions prevent it from doing things TOO EARLY.

Example:
```yaml
resolve_vote:
  available_to: [moderator only]
  preconditions:
    # Engine-enforced: cannot resolve until all alive players have voted
    - { operator: check, left: "count(type=agent, where=alive == true AND has_voted == false AND role != god)", op: "==", right: 0 }
```

Without this precondition, the moderator might resolve the vote before everyone has voted. The playbook says "wait for all votes" but the LLM may decide "close enough" and act early.

**Every moderator action that advances state should have a precondition that verifies readiness.** This includes: advancing turns (current role must have all acted), calling votes (discussion must be complete), resolving votes (all votes must be in), and starting new phases (previous phase must be finished).

### Agent Playbooks

Agents are LLMs — they need to be TAUGHT how to operate in the engine. Character cards define who the agent is. **Playbooks** define how they play. Every agent in a structured scenario needs a `playbook` in their character card.

Key things a playbook must cover:
- What actions to use in each phase
- **What to do when you have NO available actions** (wait silently, do not send messages)
- Role-specific decision guidance (when to save vs poison, who to investigate)
- How to interpret wake messages and state

Without playbooks, agents will: talk when they should be waiting, use wrong actions, not understand turn structure, and spam chat during other agents' turns.

See `references/character-guide.md` for playbook structure and examples.

### Observer Capability

The human can whisper to agents (private messages the agent doesn't know come from outside) and use GM ops to change world state directly. This is not a pattern — it's a capability that can enhance any pattern.

### Key Principle

**Find the natural tension, don't inject it.** The design patterns are a lens to SEE existing tension in a domain, not a toolkit to bolt mechanics onto it. Tension can be dramatic (hidden information, conflicting goals, betrayal) or operational (dependencies that block, resources that are shared, quality that must be reviewed). If a mechanic doesn't arise naturally, don't force it.

## Design Validation

Before generating a config, verify the world uses WorldSeed's stateful mechanics. Answer at least two concretely:

- What entity properties change over ticks?
- What preconditions enforce sequencing or access control?
- What auto_tick effects drive the world forward?
- What consequences fire when thresholds are crossed?
- What perception rules create asymmetry or scoped visibility?

If fewer than two have answers, the world needs more stateful mechanics.

## Anti-Patterns

### DM Memory Dependence
**Wrong:** Relying on the DM to remember what happened in previous ticks.
**Right:** Store all persistent information in entity state (properties). DM is stateless — each call is independent. DM makes decisions; state records results.
**Example:** In a card game, dealt cards must be stored as entity properties (removed from deck list, added to hand list). If cards only exist in DM responses, the next DM call might re-deal the same cards.

### Unconstrained Actions
**Wrong:** Actions with no preconditions and no effects — just a description.
**Right:** Every action should either change state (effects) or be gated by rules (preconditions). Without these, WorldSeed adds no value over a chatroom.

### Omniscient Agents
**Wrong:** No `hidden_properties`, no perception rules — every agent sees everything.
**Right:** Use `hidden_properties` for secrets, internal scores, private resources. Use `perception.visibility` for spatial or relational filtering. Information asymmetry is what creates strategy.

### Static World
**Wrong:** No `auto_tick`, no `consequences` — the world only changes when agents act.
**Right:** The world should evolve on its own. Resources decay, timers count down, conditions worsen. This creates urgency and prevents stalemate.

### Symmetric Agents
**Wrong:** All agents have the same starting state, same goals, same information.
**Right:** Each agent should have different capabilities, knowledge, goals, or resources. Asymmetry creates interesting dynamics.

### Property-less DM Decisions
**Wrong:** DM decides outcomes but doesn't write them to state properties.
**Right:** Every DM decision should be recorded as a state change (set, increment, create_entity). If it's not in state, it didn't happen.

### Idle Agents Spam Talk
**Wrong:** Agents with nothing to do fill time by talking ("still waiting", "keeping an eye out"). 36 talk messages from one agent that should have been silent.
**Right:** Character drives must explicitly say "If nothing to do, set think_interval high and wait silently. Do NOT talk to fill time." Also use `available_to` and phase-based perception to prevent agents from acting when it's not their turn.

### All-or-Nothing Phase Gates
**Wrong:** Phase 2 requires ALL agents to complete Phase 1 before ANYONE can proceed. The slowest agent blocks everything.
**Right:** Use timer-based fallback for phase transitions. "3 submissions OR tick >= 25, whichever comes first." This prevents one slow agent from stalling the entire world.

### Post-Processing Roles as Agents
**Wrong:** A "moderator" agent sits in the world for 40 ticks, wasting tokens, just to write a summary at the end.
**Right:** If a role's only job is post-run (comparison report, summary, HTML generation), it should NOT be an in-world agent. Handle it as a post-run step (like gazette) or as a dedicated phase where the agent is only woken via push event.

### Agents Doing Work via WorldSeed Actions
**Wrong:** Agents submit deliverable content as action parameters (`content: free_text`). The "work" is a text string in an entity property.
**Right:** Agents use their own tools (file write, scripts, skills) to produce real files in the shared workspace. WorldSeed actions only register metadata (title, file_path, author, status). Other agents read the actual files using their own tools.

### think_interval Left at Default
**Wrong:** All agents use default think_interval=5 regardless of their role. Judges wake every 5 ticks during a phase where they have nothing to do.
**Right:** Set think_interval per-role. Active workers: low (2-3). Waiting/judge roles: high (50-99). Agents can adjust their own think_interval in their drives: "set think_interval to 10 and wait."

### DM Hint Dependence
**Wrong:** Relying on DM hints for critical game mechanics (income caps, elimination rules, damage formulas).
**Right:** Critical mechanics must be engine-enforced via `consequences`. The DM **can and will ignore hints** — it's an LLM making judgment calls, not a rules engine. Use consequences for anything that MUST happen.
**Example:** In a territory war, "max income 3 troops/round" as a DM hint was routinely ignored — the DM gave a faction 21 troops in one round. Fix: add a `supply_limit` consequence that mechanically caps troops at 10 via `every_tick`. The engine enforces; the DM flavor-texts.

### Expecting Agents to Initiate
**Wrong:** Blank-slate scenarios where agents must create conflict from nothing (propose new rules, invent problems, start drama).
**Right:** Pre-seed the world with interesting state for agents to REACT to. LLMs are excellent at reacting to concrete stimuli and poor at generating novel problems from scratch.
**Example:** A roommate scenario with "propose house rules" produced zero proposals. The same scenario with 4 pre-active contradicting rules produced 26 mechanical actions — agents engaged with existing contradictions rather than creating new ones.

### No Highlights
**Wrong:** No `highlight: true` on any actions or events. The dashboard chapter panel is empty — the observer has no way to see key moments at a glance.
**Right:** Mark pivotal actions and important consequence events with `highlight: true`. These appear as chapter markers in the stream panel, making the timeline navigable.
```yaml
# On action definitions — marks execution records as highlights:
accuse:
  highlight: true

# On emit_event effects in consequences — marks events as highlights:
effects:
  - operator: emit_event
    type: verdict_reached
    highlight: true
    scope: global
```
**What to highlight:** Irreversible decisions (votes, accusations, betrayals), turning-point events (eliminations, victories, crises), phase transitions. Do NOT highlight routine actions (move, talk) — highlights should be rare and significant.
