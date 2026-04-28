# Dashboard / OpenClaw Quick Start

This guide is for dashboard runs and OpenClaw agents.

For Codex subagents, read [Codex Subagents Adapter](docs/codex-subagents/00-core.md)
first, then [Scenario Architecture](docs/codex-subagents/05-scenario-architecture.md).

## Prerequisites

- Python 3.11+ with [uv](https://docs.astral.sh/uv/)
- Node.js 18+ with npm
- An LLM API key (any provider supported by [LiteLLM](https://docs.litellm.ai/docs/providers), or ChatGPT subscription for OpenAI OAuth)

## First-Time Setup

### 1. Install WorldSeed

```bash
git clone https://github.com/AIScientists-Dev/WorldSeed && cd WorldSeed
uv sync --extra dm
cd frontend && npm install && npm run build && cd ..
```

### 2. Install OpenClaw (the agent runtime)

```bash
npm install -g openclaw@latest
openclaw --version
```

### 3. Install the WorldSeed plugin

```bash
cd openclaw-plugin && npm install && cd ..
openclaw plugins install -l openclaw-plugin
```

> **After modifying plugin code**, rebuild before reinstalling:
> ```bash
> cd openclaw-plugin && npm install && openclaw plugins install -l .
> ```

### 4. Configure OpenClaw

```bash
# Gateway mode
openclaw config set gateway.mode local
openclaw config set plugins.allow '["worldseed"]'

# LLM model: set to a cheap model for testing
openclaw config set agents.defaults.model \
  "your-preferred-model"

# CRITICAL: Remove tools.profile if set (e.g., by onboard wizard).
# The "coding" profile blocks plugin tools. Agents won't be able to
# call worldseed_perceive/worldseed_act and will try bash instead.
openclaw config unset tools.profile

# API key (option A, pay-per-token):
#   Copy .env.example to .env and set your provider's API key
#   See .env.example for supported providers
#
# API key (option B, ChatGPT OAuth, uses your subscription quota):
#   openclaw models auth login --provider openai-codex
#   openclaw config set agents.defaults.model "openai-codex/gpt-5.1-codex-mini"
#   Note: OAuth has rate limits. See "LLM Model Costs" below.

# Gateway token is configured automatically by the server.
# No manual setup needed.
```

Verify:

```bash
cat ~/.openclaw/openclaw.json | python3 -c "
import sys,json; d=json.load(sys.stdin)
print('model:', d.get('agents',{}).get('defaults',{}).get('model','NOT SET'))
print('token:', d.get('plugins',{}).get('entries',{}).get('worldseed',{}).get('config',{}).get('gatewayToken','NOT SET'))
print('API key: check .env file')
"
```

## Running a World

### Lobby Mode (recommended)

```bash
uv run worldseed
```

No arguments needed. This starts the server in **lobby mode** at http://127.0.0.1:8888.
Open the dashboard in your browser to configure and start a world:

1. Pick a scene config from the dropdown
2. Set DM model, tick interval, gateway token
3. Click **Start**. The server creates the engine, registers agents, and spawns the gateway

The dashboard transitions from lobby → ready (agents initializing) → live (ticks running).
Press **Ctrl+C** in the terminal to stop everything.

Lobby mode uses the `/api/world/start` endpoint under the hood. You can also stop and resume worlds from the dashboard (see [World Lifecycle API](#world-lifecycle-api) below).

### One-Click CLI (automated)

```bash
uv run worldseed play configs/ai_layoffs.yaml
```

This automatically:
1. Starts WorldSeed server with real DM
2. Registers all agents from the scene config
3. Starts OpenClaw gateway
4. Opens the dashboard at http://localhost:8000

Press **Ctrl+C** to stop everything.

**Budget controls:**

```bash
# Stop after 100 ticks
uv run worldseed play configs/ai_layoffs.yaml --max-ticks 100

# Stop after 10 minutes
uv run worldseed play configs/ai_layoffs.yaml --timeout 10

# Use a specific model (LiteLLM format: provider/model)
uv run worldseed play configs/ai_layoffs.yaml --dm-model your-model

# All options
uv run worldseed play configs/ai_layoffs.yaml \
  --max-ticks 200 \
  --timeout 15 \
  --dm-model your-model \
  --dm-fallback your-fallback-model
```


On connect, the plugin automatically registers all preset agents from the scene config. No manual registration needed.

You should see:

```
[worldseed] Connected to WorldSeed at ws://localhost:8000/ws
[worldseed] Authenticated as gateway in scene <scene_id> run=<run_id> (<N> agents: ...)
[worldseed] Auto-registered <agent_1>, <agent_2>, ...
[worldseed] Wrote SOUL.md for <agent_1>, <agent_2>, ...
```

Each agent gets its own OpenClaw agent (not a shared "main"), with an independent session key (`agent:{agentId}:worldseed:{runId}`). The plugin writes a SOUL.md character card into each agent's workspace on connect, so agents know who they are from the start.

Agents will start perceiving and acting automatically. Perceive responses include full action schemas (name, description, parameters) so agents know exactly what they can do and how.

<details>
<summary>Manual override (optional)</summary>

If you need to register agents manually (e.g., for debugging):

```bash
# List available characters
curl -s http://localhost:8000/characters | python3 -m json.tool

# Register a specific agent
curl -s -X POST http://localhost:8000/register \
  -H "Content-Type: application/json" \
  -d '{"mode":"claim","agent_id":"<agent_id>"}'
```

</details>

### Dashboard

Open http://localhost:8000 in your browser.

> **For development with hot-reload:** `cd frontend && npm install && npm run dev` (opens at :5173 with proxy to :8000).

- Header bar: run status, transport controls (play/pause/step), wake all, gazette, data inspector toggle, settings
- Main area: collage-art map view with zone cards and agent avatars
- Map toolbar (top-right overlay): agent avatar row, theater mode toggle, command bar
- Right panel: event stream (digest/story/all modes), or agent detail panel when an agent is selected on the map
- Data inspector (toggle): entity state browser with GM editing controls

## Switching Scenes

In **lobby mode**, stop the current world from the dashboard (or `POST /api/world/stop`), then start a new one with a different config.

Via CLI:

```bash
# Ctrl+C the current run, then:
uv run worldseed play configs/ai_layoffs.yaml
```

Available scenes:

```bash
ls configs/*.yaml
```

## Restarting (Fresh Run)

Each server restart generates a new `run_id`. Agents get fresh sessions. Previous runs are saved to `~/.worldseed/runs/{run_id}/`. You can resume a stopped run from the dashboard or via `POST /api/world/resume`.

```bash
# Terminal 1: Ctrl+C, re-run the serve command
# Gateway auto-reconnects and re-registers agents, no manual steps needed
```

## Adding Agents Mid-Run

You can add new agents while the world is running:

```bash
curl -s -X POST http://localhost:8000/register \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "create",
    "agent_id": "newcomer",
    "character": {
      "personality": "Mysterious stranger",
      "goals": ["Find the exit"]
    }
  }'
```

Initial properties (like `location`) come from the scene's `default_spawn` config or a `template`. Pass `"template": "template_name"` to use a specific template.

The server notifies the plugin via WebSocket. The plugin writes a SOUL.md character card and the agent starts acting on the next wake cycle.

## GM Controls

From the dashboard header bar, or via curl:

```bash
# Send a whisper to an agent (appears in their inbox)
curl -s -X POST http://localhost:8000/api/whisper \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"<agent_id>","message":"Something is wrong with the server room."}'

# Force-wake an agent immediately
curl -s -X POST http://localhost:8000/api/notify \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"<agent_id>"}'

# Pause / resume world ticks
curl -s -X POST http://localhost:8000/api/tick/pause
curl -s -X POST http://localhost:8000/api/tick/resume

# View world state for current run
curl -s http://localhost:8000/api/runs/{run_id}/state | python3 -m json.tool
```

## World Lifecycle API

These endpoints power the lobby-mode dashboard. You can also call them directly.

```bash
# Start a world (lobby mode)
curl -s -X POST http://localhost:8000/api/world/start \
  -H "Content-Type: application/json" \
  -d '{
    "config_path": "configs/ai_layoffs.yaml",
    "tick_interval": 5,
    "gateway_token": "worldseed-gw-token",
    "dm_model": "your-model"
  }'

# Stop the current world (saves state, returns to lobby)
curl -s -X POST http://localhost:8000/api/world/stop

# Resume a previously stopped run
curl -s -X POST http://localhost:8000/api/world/resume \
  -H "Content-Type: application/json" \
  -d '{"run_id": "a3f8b2c1"}'
```

## Event Sourcing & Persistence

Each run is saved to `~/.worldseed/runs/{run_id}/` with:

| File | Description |
|------|-------------|
| `meta.json` | Scene ID, DM model, start/end time, tick count, agent count |
| `config.yaml` | Copy of the scene config used |
| `stream.jsonl` | Single append-only event stream (source of truth) |
| `state.json` | World state snapshot (written on pause/stop, used for resume) |
| `state_final.json` | Final world state at shutdown |
| `summary.json` | Event kind counts + token totals (written at finalize) |

`stream.jsonl` event kinds: `event`, `action`, `dm_call`, `perceive`, `register`, `wakeup`, `whisper`, `gm_set`, `gm_set_queued`, `gm_remove`, `gm_remove_queued`, `gm_resolve`, `gm_resolve_queued`, `consequence`, `run_resumed`.

List past runs:

```bash
uv run worldseed runs
```

## WORLD.md

On gateway connect, the plugin writes a `WORLD.md` file into each agent's workspace. This contains:

1. **DSL reference**: how effects, parameters, and entity_ref types work
2. **Filtered scene config**: the full YAML with agent `character` blocks and hidden properties stripped

Agents read `WORLD.md` to understand the scene rules and available actions. The server generates the filtered config via `engine.public_config_yaml()`.

## Scene Config Notes

### Flat Entity Properties

Entity properties are flat. There is no nested `properties:` dict. In YAML configs:

```yaml
agents:
  - id: detective
    location: library
    trust: 50
    character:
      personality: "Methodical, observant, trusts no one easily"
      goals: ["Find the killer", "Protect the innocent"]
```

In the engine, access is `entity.location`, `entity.trust`, not `entity.properties.location`.

### enum_from for Dynamic Valid Values

Action parameters of type `entity_ref` can use `enum_from` to declare dynamic valid values. The perceive response includes the resolved enum for each parameter, so agents know exactly which entity IDs are valid:

```yaml
actions:
  move:
    params:
      - name: to
        type: entity_ref
        required: true
        enum_from: "relationships_of($agent.location, type=connects_to)"
        description: "Space ID from connects_to"
```

## Options

### `worldseed play`

| Option | Default | Description |
|--------|---------|-------------|
| `config` | (required) | Scene config YAML (positional arg) |
| `--dm-model` | (from env or built-in) | DM model in LiteLLM format |
| `--dm-fallback` | none | Fallback model |
| `--port` | 8000 | Server port |
| `--max-ticks` | none | Stop after N ticks |
| `--max-dm-calls` | none | Stop DM after N calls |
| `--timeout` | none | Stop after N minutes |

## LLM Model Costs

| Model | Cost (approx per agent turn) | Quality |
|-------|------------------------------|---------|
| Small models (e.g. flash, mini) | ~$0.005–0.01 | Good for testing |
| Medium models (e.g. pro) | ~$0.03 | Recommended for demos |
| Large models (e.g. ultra) | ~$0.20 | Best quality, expensive |

The lobby dashboard shows available models with pricing. Pick one that fits your budget.

Change model:

```bash
openclaw config set agents.defaults.model "your-preferred-model"
# Restart gateway to apply
```

## Troubleshooting

**Agents not acting / no wake signals**
Agents should auto-register on gateway connect. Check gateway logs for registration errors. As a fallback, register manually (see "Manual override" above).

**"worldseed_perceive: command not found" / agents writing fiction instead of acting**
`tools.profile` is set to `"coding"`, which blocks plugin tools. Fix: `openclaw config unset tools.profile` and restart gateway. The onboard wizard may set this automatically. Always remove it for WorldSeed.

**Dashboard shows empty session log**
Server was restarted. Gateway auto-reconnects and re-registers agents. Wait for the next wake cycle.

**Expensive API bills**
Check model: `openclaw config get agents.defaults.model`. If empty, it uses the default. Set to a cheaper model if costs are high.
