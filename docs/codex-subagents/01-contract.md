# Codex Runtime Contract

This contract is specific to Codex sessions and Codex subagents.

## Primary Codex Session

Owns:

```text
choosing or writing scenario.yaml
initializing the workspace
claiming preset agents in the engine
spawning/resuming/closing Codex subagents
starting/re-arming watcher
deciding critique, revision, curation, and finish points
```

It should not routinely edit worker lanes. If a worker needs to react, wake that
worker with context.

## Worker Subagents

Worker subagents own only:

```text
workspace/agents/{agent_id}/
```

They should:

```text
read AGENT.md and trajectory.md
run ws.py perceive first
use tools normally
write artifacts in their own lane
call ws.py publish for world-relevant facts
return artifact ids, next intent, and blockers
```

Workers do not register themselves. The primary session or bootstrap step
claims preset agents once.

## WorldSeed Engine

Required API surface for this adapter:

```text
POST /register
GET  /perceive
POST /act
GET  /api/director/signals
POST /api/director/signals/{id}/ack
```

Do not document DM endpoints here unless they exist and are exercised by this
adapter.

## Watcher Subagent

Watcher does one job:

```text
GET /api/director/signals?timeout_s=30&limit=10
return signal ids, type, target_agent_id, reason, refs, payload
stop and wait for the primary session to continue
```

Watcher does not wake workers, write files, or decide strategy.

If a future deterministic control/DM handler exists, watcher may call it only
when the signal fully specifies a mechanical operation. Anything requiring
interpretation returns to the primary session.

## Wait Loop

```text
spawn workers needed now
spawn watcher

while not done:
  wait_agent(active_workers + [watcher])

  watcher returned:
    inspect signal
    ack handled signal
    wake/resume target worker if needed
    re-arm watcher

  worker returned:
    inspect artifact ids/blockers
    close/resume/wake/spawn next worker
```

Use non-interrupting wakes by default. Queue context for the worker's next model
turn rather than stopping an active tool call.

