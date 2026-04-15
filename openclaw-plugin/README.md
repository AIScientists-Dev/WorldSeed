# WorldSeed OpenClaw Plugin

Channel plugin that connects [OpenClaw](https://github.com/nicepkg/openclaw) gateway agents to a [WorldSeed](https://github.com/AIScientists-Dev/WorldSeed) persistent world engine. A single WebSocket connection serves as a gateway for all agents in a scene.

## Prerequisites

- [OpenClaw](https://github.com/nicepkg/openclaw) installed and configured (uses Bun to run TypeScript directly)
- A WorldSeed scene config (e.g., `configs/your_scene.yaml`)

## Setup

### 1. Configure in openclaw.json

Add the plugin to `~/.openclaw/openclaw.json`:

```json
{
  "plugins": {
    "allow": ["worldseed"],
    "load": {
      "paths": ["/absolute/path/to/WorldSeed/openclaw-plugin"]
    },
    "entries": {
      "worldseed": {
        "enabled": true,
        "config": {
          "serverUrl": "ws://localhost:8000/ws",
          "gatewayToken": "your-gateway-token"
        }
      }
    }
  }
}
```

The `gatewayToken` is printed to the WorldSeed server logs on startup.

**Important:** Use `load.paths` pointing to the project source directory. Do NOT also add an `installs` entry for the same plugin. Having both causes a "duplicate plugin id detected" warning and unpredictable behavior where one copy silently overrides the other.

Environment variables `WORLDSEED_URL` and `WORLDSEED_TOKEN` override the config file values if set.

### 2. Run

```bash
# Start WorldSeed server + OpenClaw gateway together:
uv run worldseed play configs/your_scene.yaml
```

The `play` command starts the WorldSeed server, launches the OpenClaw gateway, and opens the dashboard.

## How It Works

### Connection Lifecycle

1. The gateway opens a WebSocket to the WorldSeed server and authenticates with the `gatewayToken`.
2. The server responds with `auth_ok` containing the agent list (with character data), per-agent scene config (YAML), and the scene description.
3. The plugin writes three files to each agent's workspace (`~/.openclaw/workspace-{agentId}/`):
   - **SOUL.md** -- Character identity, personality, goals, and scene rules. Injected into the agent's system prompt.
   - **WORLD.md** -- Filtered scene config as YAML (actions, preconditions, effects, auto_tick, consequences).
   - **SKILL.md** -- How to use WorldSeed tools. Copied from this plugin directory.
4. The server sends wake signals on each tick. The plugin formats a summary and dispatches it to the appropriate agent.
5. Agents use `worldseed_perceive` and `worldseed_act` tools to observe and interact with the world.

### Agent Knowledge Delivery

Knowledge reaches agents through two channels with different reliability:

| File | Delivery | Reliability |
|------|----------|-------------|
| SOUL.md | Injected into system prompt by OpenClaw | Guaranteed -- always in context |
| WORLD.md | Agent must read from workspace via file tool | Best-effort -- agents sometimes read the wrong path |
| SKILL.md | Agent must read from workspace via file tool | Best-effort -- same caveat as WORLD.md |

Because WORLD.md requires a file read that agents may fail to perform, the `scene_description` field from the scene config is inlined into SOUL.md as a "Scene Rules" section. This ensures that high-level strategy guidance and game rules reach the agent regardless of whether it successfully reads WORLD.md.

### Workspace Path Issue

OpenClaw's default agent workspace is `~/.openclaw/workspace/`. The WorldSeed plugin writes to per-agent workspaces at `~/.openclaw/workspace-{agentId}/`. Agents sometimes default to reading from `~/.openclaw/workspace/` instead of their per-agent directory.

SOUL.md includes an explicit line: `Your workspace is /path/to/workspace-{agentId}/` and SKILL.md instructs agents to read this path and `ls` the directory before proceeding. Critical content (character, scene rules) is inlined into SOUL.md rather than relying on file reads.

### Agent Tools

The plugin provides three tools to agents:

- **worldseed_register(agent_id)** -- Register in the world. Must be called once before perceive or act.
- **worldseed_perceive(agent_id)** -- Observe current state, nearby entities, events, whispers, and available actions with resolved targets.
- **worldseed_act(agent_id, action, ...)** -- Submit an action. Parameters are passed as top-level keys alongside `agent_id` and `action` (not nested in a `params` object).

### Wake Flow

When the server sends a `wake` message:

1. The plugin formats a summary with tick number, state snapshot (filtered by `wake_summary` config), recent events, and whispers.
2. The summary is dispatched to the agent as an inbound message, and `turn_done` is sent back to the server (signaling delivery, not completion).
3. The agent perceives, decides, and acts asynchronously inside OpenClaw. The plugin does not observe or block on this step.

Session keys follow the format `agent:{agentId}:worldseed:{runId}`, giving each agent a separate conversation context per run.

## Code Structure

```
openclaw-plugin/
  index.ts          Entry point. Registers the worldseed channel plugin with OpenClaw.
  SKILL.md          Agent skill guide. Copied to each agent's workspace as SKILL.md.
  openclaw.plugin.json   Plugin manifest (id, name, config schema).
  package.json      Package metadata and dependencies (ws, typebox).
  src/
    channel.ts      Channel plugin definition. Account resolution, capabilities,
                    outbound adapter, agent prompt hints, tool factory.
    gateway.ts      Gateway adapter. WebSocket lifecycle, auth, wake handling,
                    SOUL.md/WORLD.md/SKILL.md generation, reconnect logic.
    connection.ts   ConnectionBridge class. Multiplexes request/response pairs
                    over a single WebSocket using request_id correlation.
    tools.ts        Agent tool definitions (worldseed_perceive, worldseed_act,
                    worldseed_register). Routes calls through ConnectionBridge.
```

## Troubleshooting

### "duplicate plugin id detected"

Two copies of the plugin are being loaded. Check `~/.openclaw/openclaw.json` and ensure you have either `plugins.load.paths` or `plugins.installs.worldseed`, not both. Remove the `installs` entry if present.

### Agents not acting (wake dispatched but no actions taken)

- Check gateway logs for errors: `grep "error\|rate limit\|timed out" /tmp/openclaw/openclaw-$(date +%Y-%m-%d).log`
- Verify agents read their workspace files: search logs for "WORLD.md" or "failed".
- Check if agents are using the correct workspace path (per-agent, not default).
- Remove stale lock files: `find ~/.openclaw -name "*.lock" -delete`

### Gateway keeps crashing (returncode=1)

- Kill zombie gateway processes: `pkill -9 -f "bun server"`
- Remove stale session locks: `find ~/.openclaw/agents -name "*.lock" -delete`
- Restart cleanly: stop the gateway (`openclaw gateway stop`), then rerun `uv run worldseed play ...`

### Stale gateway lock

Only one `worldseed play` session can run at a time because the OpenClaw gateway holds a global lock. If a previous session did not shut down cleanly:

```bash
openclaw gateway stop
# Then retry:
uv run worldseed play configs/your_scene.yaml
```

Do not kill gateway processes manually unless `openclaw gateway stop` fails.

### WORLD.md read failures

Agents may fail to read WORLD.md if they use the default workspace path instead of their per-agent workspace. Symptoms: the agent acts without understanding the action schema or preconditions. The scene_description inlined in SOUL.md provides a fallback, but for full rule awareness the agent must read WORLD.md.

If this happens consistently, check that the agent's SOUL.md contains the correct workspace path and that the file exists at that location.

## Development

The plugin is loaded directly from source via `load.paths`. OpenClaw uses Bun, which executes TypeScript directly -- no build step needed. To modify the plugin:

1. Edit TypeScript files in `openclaw-plugin/src/`.
2. Restart the game (`uv run worldseed play ...`). The gateway reloads the plugin from source on startup.
3. Changes to SKILL.md take effect on the next game start (the file is copied to agent workspaces during `auth_ok`).

Dependencies (`ws`, `@sinclair/typebox`) are installed locally in the plugin's `node_modules/`.
