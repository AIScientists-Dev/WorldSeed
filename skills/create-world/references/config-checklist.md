# Config Quality Checklist

After generating a scene config + UI config, run through this checklist. **[MUST]** items cause broken configs or bad experiences. **[SHOULD]** items improve quality.

## A. Correctness — Will it run?

1. **[MUST] ID uniqueness** — All entity and agent IDs are unique. Agent IDs do not collide with entity IDs.
2. **[MUST] References resolve** — Every entity_id.property in effects, preconditions, and consequences points to an existing entity. Every $param matches a declared param name.
3. **[MUST] Property names consistent** — If the scene uses `sector` instead of `location`, ALL references (actions, perception, auto_tick, consequences) use `sector`. No mixing.
4. **[MUST] Perception context variables** — Visibility rules use `$observer`/`$entity`. Event scope rules use `$observer`/`$event_source`. Never `$agent` in perception context.
5. **[SHOULD] Event scopes declared** — Every scope used in events is either built-in (`global`, `target_only`, `admin`) or declared in `perception.event_scopes`.
6. **[SHOULD] enum_from returns non-empty** — At least one agent in the starting state can get options from every `enum_from` expression.
7. **[SHOULD] Constraint property names match** — `constraints: {health: {min: 0}}` only works if the entity property is called `health`, not `hp`.
8. **[SHOULD] Spatial graph connected** — Spaces with `connects_to` are bidirectional. No dead-end rooms unless intentional.
9. **[MUST] Agent locations valid** — Every agent's starting location references an existing space entity.
10. **[SHOULD] Relationship type strings match** — The type string in `add_relationship` matches exactly what `relationships_of()` queries use.

## B. Design — Is it interesting?

Aim for at least 3 tension sources from either or both categories. Fewer than 2 is almost certainly boring.

### Dramatic Tension Sources

11. **[MUST] Conflict** — At least two agents want incompatible things.
12. **[SHOULD] Dramatic irony** — The observer knows things agents don't. Implemented via `hidden_properties` and asymmetric perception.
13. **[SHOULD] Stakes** — Something meaningful can be permanently lost. An irreversible consequence that agents care about.
14. **[SHOULD] Time pressure** — A ticking clock via `auto_tick` decay or countdown.
15. **[MUST] Dilemma** — No good choice, only tradeoffs. Multiple pressures pulling in different directions.
16. **[SHOULD] Suspense / Mystery** — Unknown information agents need to discover.
17. **[SHOULD] Character contradiction** — At least one agent has competing internal motivations.
18. **[SHOULD] Power asymmetry** — Agents have unequal capabilities, resources, or information.
19. **[SHOULD] Betrayal potential** — Trust that could be broken. Hidden roles, secret goals.
20. **[SHOULD] Reversal potential** — DM judgment on ambiguous actions, unexpected consequence triggers.

### Operational Tension Sources

20b. **[SHOULD] Dependency pressure** — Downstream work blocked until upstream completes.
20c. **[SHOULD] Resource contention** — Multiple agents need the same limited resource.
20d. **[SHOULD] Quality vs speed tradeoff** — DM judgment on review actions creates quality gates.
20e. **[SHOULD] Specialization mismatch** — Tasks don't perfectly match available agents.
20f. **[SHOULD] Handoff friction** — Work passes between agents with potential delay at each handoff.

### Structural Requirements

21. **[MUST] `attempt` action exists** — Without it, agents cannot do anything creative beyond predefined actions.
22. **[MUST] Communication action exists** — At least `talk`. Preferably `directed_talk` too.
23. **[MUST] Meaningful preconditions** — Actions that affect the world have preconditions gated by state. No preconditions = chatroom.
24. **[SHOULD] Actionable drives** — Character drives reference concrete actions and entity IDs that exist.
25. **[MUST] Scene description is specific** — At least 2-3 sentences describing setting, core tension, and physical constraints. The DM reads this on every call.
26. **[MUST] `wake_summary` configured** — Without it, agents only see events in wake messages, not world state.
27. **[SHOULD] `dm_knowledge` for domain rules** — If the DM needs domain expertise, put it in `scene.dm_knowledge`.
28. **[SHOULD] `available_to` for role-based actions** — If different agents should see different actions, use `available_to`.
29. **[MUST] Character cards follow guide** — Every agent needs: specific personality, concrete goals, at least one secret.
30. **[SHOULD] Playbooks for structured scenarios** — Turn-based or phase-based scenarios need playbooks teaching agents what actions to use when.
31. **[MUST] Moderator preconditions** — If a moderator controls flow, its actions MUST have preconditions preventing premature advancement. Never rely solely on playbook.

## C. Robustness — Will it hold up over 100 ticks?

32. **[MUST] DM stateless check** — For every action with `dm:`, does the DM need to remember anything from a previous call? If yes, that info must be in entity state.
33. **[SHOULD] Decay rates sustainable** — starting_value ÷ decay_per_tick ≥ 20-30 ticks.
34. **[SHOULD] Numeric floors exist** — Every depleting resource should use `min: 0` in decrement effects.
35. **[SHOULD] every_tick consequences bounded** — Calculate cumulative effect at tick 100. Is that handled?
36. **[SHOULD] Avoid emit_event in auto_tick** — Events in auto_tick fire every tick, which can flood the event log. Use short TTL (1) if needed, or use consequences with `on_change` frequency for state-driven events instead.
37. **[SHOULD] DM allowed_ops restricted** — `observe` should not allow `remove_entity`.
38. **[SHOULD] DM hint is specific** — "Judge the outcome" is too vague. Be concrete about what to check and what ops to use.
39. **[SHOULD] Hidden properties don't hide feedback** — Don't hide `health` or `condition`. Hide motivations, not physical state.
40. **[MUST] Consequence $entity has type filter** — If effects use `$entity.property`, trigger must include `$entity.type == "agent"` (or appropriate type).
41. **[SHOULD] Event TTLs appropriate** — Routine events: ttl 1-2. Important events: ttl 3-5. Never permanent on routine.

## D. Agent Awareness — Do agents get useful wakes?

42. **[MUST] wake_summary configured** — duplicate of #26, here for completeness.
43. **[SHOULD] self_fields covers decision inputs** — Every property an agent checks before acting should be in `self_fields`.
44. **[SHOULD] Key world entities tracked** — Entities with changing state listed in `wake_summary.entities`.
45. **[SHOULD] agent_fields shows relevant info** — What agents need to know about each other.
46. **[SHOULD] available_to used for role-specific actions** — duplicate of #28, here for completeness.

## E. Observer Experience — Is it compelling to watch?

47. **[SHOULD] Agents don't all start in same location** — Spread agents out or give drives to separate.
48. **[SHOULD] Key state visible on dashboard** — Properties driving preconditions/consequences surfaced in UI config `show` bindings.
49. **[SHOULD] Multiple threads of activity** — With 3+ agents, at least two independent threads.
50. **[SHOULD] Observer has informational advantage** — Observer sees hidden_properties, secrets, full state.
51. **[SHOULD] Spatial structure matters** — Location affects preconditions and perception scope. Structure gates behavior.
52. **[SHOULD] UI config has state_effects** — Entities with condition/status have visual state changes. Every property name in conditions MUST exist on the matched entities (in YAML properties, agent template, or set by effects).
53. **[SHOULD] UI config has gauge for numeric bars** — Depleting resources use `gauge` scene type.

## F. Emergence — Will each run be different?

54. **[MUST] No dominant strategy** — At key decision points, no obviously correct answer.
55. **[SHOULD] DM judgment has real ambiguity** — At least one action where DM could rule either way.
56. **[MUST] Multiple endings reachable** — At least two qualitatively different end states possible.
57. **[SHOULD] Emergent interaction possible** — One agent's action changes conditions for another via consequences.
58. **[SHOULD] Unequal stakes** — At least one agent has more to lose than others.

## G. Agent Behavior — Will agents do what you intend?

59. **[SHOULD] think_interval set per role** — Workers: low (2-3). Waiting roles: high (50-99).
60. **[SHOULD] Idle agents told to be silent** — Drives say "if nothing to do, do NOT talk."
61. **[SHOULD] Phase gates have timer fallback** — "3 submissions OR tick >= 25."
62. **[SHOULD] Agents use own tools for work** — WorldSeed actions are for coordination, not doing the work itself.
63. **[SHOULD] Drives reference phases explicitly** — "Phase 1: do X. Phase 2: do Y."
64. **[SHOULD] Post-processing roles are not agents** — Summary-only roles handled post-run.

## H. Highlight & Narrative

65. **[MUST] Key actions have `highlight: true`** — 2-4 pivotal actions per config. Without it, the chapter panel is empty.
66. **[MUST] Key consequence events have `highlight: true`** — Verdict reached, elimination, victory, crisis.
67. **[SHOULD] Don't over-highlight** — Highlight only irreversible decisions and turning points.

## I. Drive Quality

68. **[MUST] Drives are dilemmas, not instructions** — Competing pressures, not directives. See `references/character-guide.md`.
69. **[MUST] No cross-agent secret leaks** — Agent A's drives must not contain Agent B's secret.
70. **[SHOULD] Argument balance** — If scenario involves judgment, balance the count of arguments on each side.
71. **[MUST] Critical mechanics are engine-enforced** — Income caps, elimination triggers, vote thresholds → consequences, not DM hints.

## J. UI Config Completeness

72. **[MUST] Every entity type has a matching UI rule** — Custom types without rules render as gray fallback badges. See `references/ui-config-guide.md`.
73. **[MUST] Internal trackers hidden** — Timers, game phase trackers, internal state entities → `"scene": "hidden"`.
74. **[MUST] event_defaults set** — Without `{"bubble": "action"}`, unmatched events produce no visual feedback.
75. **[SHOULD] Highlight actions have event effects** — Actions with `highlight: true` in scene config should have matching event rules with effects (flash-red, flash-green, etc.) in UI config.
76. **[MUST] Run `worldseed validate`** — Check for UI consistency warnings (U001-U011). Fix all errors before delivery. Key checks: U001 (entity coverage), U007 (event_defaults), U009 (zone overlap), U010 (no state_effects on agents), U011 (state_effects reference existing properties).
