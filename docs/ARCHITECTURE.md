# Architecture

## Overview

```
Agent (OpenClaw / external)
  │
  ├─ POST /register   → AgentRegistry   → Entity(type=agent) + AgentConfig
  ├─ GET  /perceive   → Perceiver       → filtered world state per agent
  ├─ POST /act        → ActionQueue     → queued for next tick
  └─ WS   /ws         → WebSocket       → bidirectional (auth, perceive, act, wake)
                          │
                          ▼
                    TickRunner (every N seconds)
                          │
                    WorldEngine.step_async
                          │
           ┌──────────────┼──────────────┐
           ▼              ▼              ▼
      ActionQueue   ConsequenceScanner  AutoTick
           │              │              │
           └──────────────┼──────────────┘
                          ▼
                  StateStore + EventLog
                          │
                          ▼
                  Perceiver.deliver → InboxManager (per-agent)
                          │
                          ▼
                  ConnectorProvider.notify → wake push to gateway
```

## Key Modules

| Module | Path | Purpose |
|--------|------|---------|
| WorldEngine | `world.py` | Top-level facade. All external access goes through here. |
| TickEngine | `engine/tick.py` | Clock orchestration, action processing per tick. |
| RulesEngine | `engine/rules_engine.py` | Precondition checking, effect execution. |
| StateStore | `engine/state_store.py` | Entity CRUD. All state as flat properties. |
| EventLog | `engine/event_log.py` | Events with TTL, auto-expiration. |
| Perceiver | `engine/perceiver.py` | Filters world state per agent based on config rules. |
| ConsequenceScanner | `engine/consequence_scanner.py` | Reactive rules. Fires when world state meets conditions. |
| InboxManager | `engine/inbox.py` | Per-agent inbox for events and whispers. |
| ActionQueue | `engine/action_queue.py` | Queues agent actions for tick processing. |
| DM Providers | `dm/providers/` | LLM DM (`llm.py`), mock (`mock.py`). |
| DSL Effects | `dsl/effects.py`, `dsl/effect_ops.py` | Dispatcher + executors for deterministic effects. |
| Preconditions | `dsl/preconditions.py` | Gate actions with DSL expressions. |
| PathResolver | `dsl/path_resolver.py` | Resolves `$param` references in DSL expressions. |
| AgentRegistry | `agent_registry.py` | Agent lifecycle, profiles, think_interval, property merge. |
| Scene Config | `scene/config.py` | YAML loader, populator, validator. |
| Server | `server/app.py` | FastAPI factory, routes, tick runner, WebSocket. |
| CLI | `cli/` | `play`, `validate`, `runs` commands. Lobby mode. |
| Persistence | `persistence.py` | Event-sourcing to `~/.worldseed/runs/{run_id}/`. |
| Frontend | `frontend/` | React + TypeScript + Tailwind + shadcn/ui + Zustand. |

## Data Flow: One Tick

1. `TickRunner` fires `WorldEngine.step_async()`.
2. Actions are pulled from `ActionQueue`, one per agent per tick.
3. For each action, `RulesEngine` checks preconditions (DSL expressions).
4. If preconditions pass:
   - Actions with static `effects` → `DSL effect_ops` execute immediately (set, increment, emit_event, etc.).
   - Actions with a `dm:` section → parallel `asyncio.gather()` calls to `LiteLLMDMProvider`. DM returns structured `DMResponse` (narrative + effects), validated by Pydantic.
5. All effects applied to `StateStore`. Events written to `EventLog`.
6. `ConsequenceScanner` runs. Checks all consequence rules against new state, fires additional effects.
7. `AutoTick` effects run (decay, progression, scheduled events).
8. `Perceiver.deliver()`: for each agent, filters visible entities/events based on config-defined visibility rules, writes to `InboxManager`.
9. `ConnectorProvider.notify()`: pushes wake signals to connected agents via WebSocket.
10. `RunRecorder` appends all events to `stream.jsonl`.

## Data Separation

- **Entity** = world state only (id, type, flat properties). No personality, no goals.
- **AgentConfig** = agent identity. `character: dict[str, Any]`, free-form per scene. Stored in AgentRegistry, NOT in Entity.
- Engine, Perceiver, and Inbox never access AgentConfig. Only the DM prompt builder reads it.

## DM System

- Stateless: each call is independent. Persistent info must be in entity state.
- Uses LiteLLM + Instructor for structured output.
- Per-call token tracking via `DMResponse`.
- Parallel calls per tick via `asyncio.gather()`.
- DM judges physical outcomes ONLY. Never describes other agents' behavior.
- Rate-limited: `MAX_DM_CALLS_PER_TICK`.
- Fallback model support.

## Perception Model

- `perception.visibility`: DSL rules evaluated per observer per entity per tick.
- `perception.event_scopes`: custom scopes evaluated per observer per event.
- `hidden_properties`: properties never sent to agents.
- Built-in scopes: `global`, `target_only`, `admin`.
- Undeclared scopes default to global.

## Persistence

Run data at `~/.worldseed/runs/{run_id}/`:
- `meta.json`: scene_id, dm_model, status, timing, counts.
- `config.yaml`: copy of scene config.
- `stream.jsonl`: append-only event stream (event, action, dm_call, perceive, register, wakeup, whisper).
- `state.json` + `tick`: saveable mid-run state.
- `state_final.json`: snapshot at shutdown.
- `summary.json`: kind counts + token totals.

## Scene Config Reference

See [SCENE_CONFIG.md](../configs/SCENE_CONFIG.md) for the full YAML schema.
See [SCENE_DSL.md](../configs/SCENE_DSL.md) for DSL expression syntax.
See [UI_CONFIG.md](../configs/UI_CONFIG.md) for dashboard rendering config.
