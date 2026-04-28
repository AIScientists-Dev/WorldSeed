# Codex Orchestration Loop

Use this as the primary Codex session's runbook.

## 1. Clarify The Run

Clarify:

```text
objective
final output shape
roles
success criteria
critique pressure
tools or APIs needed
```

## 2. Start Runtime

```bash
uv run worldseed run configs/{scenario}.yaml \
  --workspace ~/.worldseed/workspaces/{run_id} \
  --port 8000 \
  --force
```

The launcher initializes workspace files, starts the server, claims preset
agents, and prints prompts for watcher and workers.

For multi-step Codex runs, the scenario should not stop early:

```yaml
scene:
  max_ticks: null
```

If a scene has a small `max_ticks`, the engine can pause while workers still
need to publish critiques, selections, or final packages. Use an explicit cap
only for bounded demos.

## 3. Spawn Workers

Worker prompt should include:

```text
You are {agent_id}.

Read:
  {workspace}/agents/{agent_id}/AGENT.md
  {workspace}/trajectory.md

Use:
  WORLDSEED_WORKSPACE={workspace}
  WORLDSEED_AGENT_ID={agent_id}
  WORLDSEED_URL={engine_url}

Run perceive first.
Work only under {workspace}/agents/{agent_id}/.
Publish world-relevant facts with ws.py publish.
Return artifact ids, next intent, and blockers.
```

Spawn only workers needed for the next unit. Let workers run multi-step when it
helps: research, write scratch files, generate assets, then publish.

Parallel workers are useful when they have disjoint lanes and the same upstream
context, for example three generators reacting to the same API note and prompt
pattern. Close completed workers after recording their artifact ids so Codex
has free subagent slots for judges or curators.

## 4. Spawn Watcher

Watcher prompt:

```text
Long-poll {engine_url}/api/director/signals?timeout_s=30&limit=10.
Return signal ids, type, target_agent_id, reason, refs, payload.
Do not wake agents.
Do not write workspace files.
Pause after returning; wait to be continued.
```

## 5. Wait And Steer

```text
wait_agent(active_workers + [watcher])
```

When a worker returns, read its artifact ids and blockers. Decide whether to
close it, resume it, wake a critic, or start a curator.

When watcher returns, inspect signals, ack handled ones, wake the relevant
worker if needed, then re-arm watcher.

Typical pressure sequence:

```text
discovery
divergent generation
critique
revision or rebuttal
selection
final package
story.md
optional final HTML
```

Do not rely on live HTML to explain the process. The final story should come
from workspace evidence after the run has enough material.
