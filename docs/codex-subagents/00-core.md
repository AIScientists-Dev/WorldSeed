# Codex Subagents Adapter

This directory documents one practical way to run WorldSeed with Codex
subagents. It is not the general product README and not the only possible
runtime.

The pattern is useful for production-style workflows:

```text
research -> generate -> critique -> revise -> select -> package
```

WorldSeed provides the world facts, action validation, events, inboxes, and
signals. Codex provides the orchestration and subagent lifecycle.

Use [Scenario Architecture](05-scenario-architecture.md) when designing the
scene itself. Runtime wiring is not enough; interesting runs need role pressure,
private information, consequences, and artifact history.

## Runtime Pieces

```text
primary Codex session   talks to the user, starts the run, spawns/wakes subagents
Codex subagents         do bounded work: research, generation, critique, curation
WorldSeed engine        validates actions, records events/state, routes inboxes
watcher subagent        waits for engine signals and reports them back
workspace               durable artifact lanes and final outputs
```

The watcher is not a scheduler. It is a receiver included in the primary
session's `wait_agent([...])` set.

Codex cannot currently receive arbitrary external push messages into an already
running session. That is why the watcher must be waited on like any other
subagent.

Codex subagents are limited resources. Completed workers should be closed once
their artifact ids and blockers have been captured, otherwise new parallel
workers may fail to spawn because old threads still occupy slots.

## Workspace Shape

```text
workspace/
  manifest.json
  scenario.yaml
  trajectory.md       # Codex operating plan
  story.md            # final user-facing narrative
  ws.py               # agent wrapper: perceive, act, publish, status
  agents/{id}/
    AGENT.md
    status.json
    *.jsonl           # append-only artifact lanes
    files/
    scratch/
  deliverable/
```

`trajectory.md` is for Codex and subagents during the run. `story.md` is for
the user near the end.

## Basic Loop

```text
subagent writes artifact body in its own lane
subagent calls ws.py publish
engine records event/inbox/signal
watcher returns signal to primary Codex session
primary session decides who to wake next
curator/final worker writes final package
story.md and optional final HTML are generated from the workspace
```

During the run, prioritize clean artifact records over live UI. A final page can
be generated after enough evidence exists.

For Codex-subagent runs, avoid low world `max_ticks` limits. Use
`scene.max_ticks: null` or a value high enough for discovery, parallel
generation, critique, revision, and curation. A low limit can pause the engine
while the primary session still has workers to wake.
