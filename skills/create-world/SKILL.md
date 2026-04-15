---
name: create-world
description: Generate WorldSeed scene configs (YAML + UI JSON) from a scenario description.
---

# World Architect

## What WorldSeed Is

WorldSeed is the interaction and coordination layer between AI agents. Each agent has its own tools and capabilities (trading, coding, researching) via its react loop. WorldSeed manages the shared space: state, visibility, rules, and consequences. WorldSeed never touches what agents do on their own.

When designing a world, ask:
1. **What can agents already do on their own?** (anything their tools enable)
2. **What does WorldSeed add?** (information asymmetry, social dynamics, consequences, workflow enforcement, shared coordination state)
3. **What should WorldSeed NOT build?** (don't reimplement what agents' tools already do)

## Output

Two files per world:
- `configs/{scene_id}.yaml` — scene config (entities, agents, actions, rules, consequences)
- `frontend/public/configs/{scene_id}.ui.json` — UI config (how entities render on the dashboard)

## Process

### Step 1: Generate Scene Config

Read these references, then generate a valid YAML config. Save to `configs/{scene_id}.yaml`.

- `configs/template.yaml` — starting template with every key commented
- `configs/SCENE_CONFIG.md` — full schema reference
- `configs/SCENE_DSL.md` — DSL expressions (preconditions, effects, functions)
- `references/design-patterns.md` — patterns + anti-patterns (read anti-patterns first)
- `configs/SCENE_DESIGN.md` — practical implementation: action design, resource modeling, urgency math, testing
- `references/character-guide.md` — character cards, drives, playbooks
- `references/preset-catalog.md` — reusable presets (`scene.use`) — don't rewrite talk/attempt/move
- `configs/teahouse.yaml` — worked example of a complete config

### Narrator

The narrator is **on by default** (`style: "storyteller"`, `interval: 10`). Decide whether to keep the default, change the style, or disable it.

**Built-in styles** (full descriptions in `configs/SCENE_CONFIG.md`):
`storyteller`, `poet`, `intel`, `noir`, `gossip`, `conspiracy`, `bureaucrat`, `gameshow`, `trickster`

**When to adjust:**
- Story-driven scenes (intrigue, social dynamics, hidden information) → keep default `"storyteller"`, or pick `"noir"` / `"gossip"` / `"conspiracy"` to match tone
- Data-heavy or operational scenes (resource management, workflow) → `"intel"` for concise briefings, `"bureaucrat"` for procedural framing
- Atmospheric or experimental scenes → `"poet"` for minimal imagery, `"trickster"` for unreliable narration
- Pure mechanical simulations with no observer → `narrator: false`

**`prompt` vs `style`:** Setting `prompt` **replaces** the built-in style entirely — the two are not combined. Use `prompt` when no built-in style fits. Use `style` when a preset is close enough.

**`interval`:** Default 10 ticks. Lower (e.g. 5) for fast-paced scenes where a lot happens per tick. Higher (e.g. 20) for slow scenes where the narrator would repeat itself.

```yaml
# Examples
narrator: "storyteller"                      # shorthand — default style
narrator: false                              # disable
narrator:
  style: "intel"
  interval: 5
narrator:
  prompt: "Write as a noir detective's internal monologue. Short, cynical sentences."
  interval: 15
```

See `configs/SCENE_CONFIG.md` → `narrator` section for full field reference.

### Step 2: Select Assets (optional but encouraged)

Check `frontend/public/assets/library/manifest.json` for reusable images.

Three paths:
1. **User provides images** — custom images matching the scene are always best
2. **Pick from library** — copy to `frontend/public/assets/scenes/{scene_id}/`
3. **No images** — set `asset_pack: ""`. Renders as fallback text.

Asset pack directory structure:
```
frontend/public/assets/scenes/{scene_id}/
  agents/{agent_id}.png
  entities/{entity_id}.png
```

### Step 3: Generate UI Config

Read these references, then generate a matching UI JSON. Save to `frontend/public/configs/{scene_id}.ui.json`.

- `references/ui-config-guide.md` — decision tree for scene types, what to show/hide
- `frontend/src/lib/ui-fragments.ts` — copy-paste building blocks with JSDoc
- `configs/UI_CONFIG.md` — full schema reference
- `configs/UI_SCAFFOLD.jsonc` — starting template

Set `asset_pack` to scene ID (if assets exist) or `""`. Every entity type needs a matching rule. Always set `event_defaults: {"bubble": "action"}`.

### Step 4: Self-Check

Run through `references/config-checklist.md`. Focus on:
- **Section H** — highlight markers on key actions/events
- **Section I** — drive quality (dilemmas not instructions, no cross-agent secret leaks, engine-enforced mechanics)

### Step 5: Validate

```
uv run worldseed validate configs/{scene_id}.yaml
```

Fix all errors before proceeding.

### Step 6: Deliver

```
uv run worldseed play configs/{scene_id}.yaml
```

Custom port: `--port <port>`. Multiple worlds run simultaneously on different ports.

## Rules

- Find natural tension, don't inject it. Tension can be dramatic or operational.
- Prefer fewer, richer actions (5-8). Use `attempt` as overflow.
- Every agent needs asymmetric information, goals, or capabilities.
- Structured scenarios need playbooks AND engine-enforced preconditions — see `references/design-patterns.md` Moderator Agent Pattern.
- Read anti-patterns before generating — they're tested across 65+ runs.
