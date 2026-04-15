<p align="center">
  <img src="docs/assets/hero.png" alt="WorldSeed — three worlds, one engine" width="100%">
</p>

<div align="center">

# WorldSeed

**Your first AI world.**
Give AI a world. Make it yours.

[![Demo](https://img.shields.io/badge/Demo-→-blue?style=for-the-badge)](https://worldseed.morphmind.ai/demo)

<!-- TODO: replace TODO with actual org/repo and URLs at launch -->
[![MIT License](https://img.shields.io/badge/license-MIT-blue?style=flat-square)](./LICENSE) [![Discord](https://img.shields.io/badge/Discord-Join-5865F2?style=flat-square&logo=discord&logoColor=white)](https://discord.gg/x9mtbMEx) [![WeChat](https://img.shields.io/badge/WeChat-Scan%20to%20Join-07C160?style=flat-square&logo=wechat&logoColor=white)](#community) [![X](https://img.shields.io/badge/X-Follow-000000?style=flat-square&logo=x&logoColor=white)](https://x.com/morphmind__ai?s=11)

[**Getting Started**](#getting-started) · [**Demo**](https://worldseed.morphmind.ai/demo) · [**Docs**](docs/ARCHITECTURE.md)

**English** · [简体中文](docs/README.zh-CN.md)

</div>

---

## What is WorldSeed?

A world engine where you describe any scenario (characters, rules, actions, what each one can see) and AI agents inhabit it autonomously. They move in and make their own decisions. You watch from above, intervene, or step in as a character. Same engine runs anything. Every run is a different story. What emerges is never designed.

**You seed worlds. Stories grow on their own.**

---

## Demo

WorldSeed is scene-agnostic. The same engine runs any world you define. Two example scenes ship with the repo:

### Scene 1: AI Layoffs

https://github.com/user-attachments/assets/a1fae852-1ede-4ea3-825f-10c182cf80db

**In an age of AI-driven layoffs, how do people hold on?**

One internet company just pulled the trigger: 30% of its workforce, gone.

**Those being laid off** have to **"distill" their expertise into an AI Skill** before they leave. Distill honestly, or leave a backdoor in the Skill?

**Those who stay** face the same deadlines, higher KPIs, and twice the workload. Grind it out, or quietly plan the exit?

Four people in this office, each with their own play running:

- The PM everyone loves working with. Who's he really trashing the moment the door closes?
- The architect walking out at month's end. Severance didn't land. What gets buried in the Skill he hands over?
- The team lead who demands honest data from everyone. Can her own "AI productivity" numbers survive a closer look?
- The QA nobody remembers is there. Those bugs in his private folder: evidence, or ammunition?

[Try it locally](#getting-started)

### Scene 2: Teahouse Espionage

**Same engine. Different YAML. Completely different world.**

<p align="center">
<img src="docs/assets/teahouse_map.png" alt="WorldSeed teahouse map — isometric world view" width="720">
</p>

<p align="center">
<img src="docs/assets/teahouse_dashboard.png" alt="Screenshot of the full WorldSeed dashboard — teahouse scenario with map and event stream" width="720">
</p>

**Four spies, one teahouse. Who's really working for whom?**

A classic espionage drama in miniature. Agents trade secrets over tea, protect their covers, and try to read each other before they get read.

<p align="center">

[![Explore this world (demo)](https://img.shields.io/badge/Explore_this_world_(demo)-→-blue?style=for-the-badge)](https://worldseed.morphmind.ai/demo)

</p>

---

## Getting Started

**Prerequisites:** Python 3.11+, Node.js 18+, [uv](https://github.com/astral-sh/uv)

```bash
git clone https://github.com/AIScientists-Dev/WorldSeed && cd WorldSeed
uv sync --extra dm
cd frontend && npm install && npm run build && cd ..

cp .env.example .env
# Add your API key (any LiteLLM provider: OpenAI, Anthropic, Ollama, etc.)

uv run worldseed play configs/ai_layoffs.yaml
```

Open the dashboard at `http://localhost:8000`. Three ways to experience it:

- **Watch**: observe all agents from above, including their inner state.
- **Intervene**: whisper privately to any agent, nudge the story.
- **Play**: step into a character and play alongside the AI.

Every run is different. Past runs are preserved and replayable.

See [QUICKSTART.md](QUICKSTART.md) for the full setup guide, including OpenClaw integration, GM controls, and troubleshooting.

---

## How It Works

WorldSeed runs on a tick loop over a world you declared in YAML. A **tick** is one beat of the world's clock, like a heartbeat that advances the world one step at a time. Each tick: every agent perceives its own filtered slice, proposes an action, and the engine resolves it. Predictable outcomes follow the rules you declared; uncertain ones go to an AI referee. Effects apply, the world advances, the next tick begins.

<div align="center">
  <img src="docs/assets/arch-diagram.svg" alt="WorldSeed architecture: you describe a world; it ticks forward; each agent sees its own filtered slice and acts; when an outcome is certain the DSL engine resolves it, otherwise the AI Dungeon Master judges; state changes, consequences fire, next tick" width="80%">
</div>

<br>

**Setup (once, in YAML):**

- **Any world, in one YAML file.** Declare entities, rules, physics, and per-character perception; the engine has zero hardcoded domain knowledge.

**Runtime (every tick):**

- **Asymmetric information by design.** Perception rules filter the world per character. Three agents in the same room hold three completely different pictures of what's happening.
- **Deterministic rules where you can, AI judgment where you can't.** Predictable actions resolve instantly via the in-YAML rule engine (**DSL**); uncertain ones go to an LLM-based **Dungeon Master (DM)** that returns structured effects, not free prose.
- **Effects land, the world ticks on.** State mutates, consequences cascade, the next tick begins. Slow or offline agents don't freeze it, and every change is logged for replay.

**Plug-in points:**

- **Any agent can connect.** Speaks HTTP or WebSocket; ships with [OpenClaw](https://github.com/OpenClaw).
- **Any LLM can be the DM.** Works with any [LiteLLM](https://docs.litellm.ai/docs/providers)-supported model.

For the full runtime plumbing (endpoints, tick scheduling, consequences, inbox delivery), see [Architecture](docs/ARCHITECTURE.md). See a real scene YAML in [`configs/teahouse.yaml`](configs/teahouse.yaml) or the full schema in [Scene Config Spec](configs/SCENE_CONFIG.md).

---

## Create Your World

Describe your world in a prompt, let AI generate the YAML, then hand-craft whichever pieces you want more control over: a character's secret, a specific action's rule, a perception filter, a DM hint.

**Generate with AI:**

```
/create-world "A reality show on a space station, six contestants, one eliminated each round"
```

The `create-world` skill produces both YAML scene config and UI config, validated and ready to run.

**Hand-craft any feature:**

The output is plain YAML. You can edit any entity, action, rule, character profile, or perception filter directly. Study the built-in examples ([`teahouse.yaml`](configs/teahouse.yaml), [`ai_layoffs.yaml`](configs/ai_layoffs.yaml)) to see how features are declared.

Full spec: [Scene Config](configs/SCENE_CONFIG.md) · [UI Config](configs/UI_CONFIG.md) · [DSL](configs/SCENE_DSL.md)

**Validate and run:**

```bash
uv run worldseed validate configs/my_scene.yaml
uv run worldseed play configs/my_scene.yaml
```

Once launched, each scene auto-renders room cards, character portraits, and a narrator voice you pick (storyteller / noir / intel briefing / gossip):

<table align="center">
  <tr>
    <th align="center">Room Cards</th>
    <th align="center">Character Portraits</th>
  </tr>
  <tr>
    <td><img src="docs/assets/world_briefing.png" alt="WorldSeed world briefing, room cards rendered from YAML config" width="400"></td>
    <td><img src="docs/assets/onboarding.png" alt="WorldSeed onboarding, character portraits and personality cards" width="400"></td>
  </tr>
</table>

---

## Development

Follow [Getting Started](#getting-started) above, then:

```bash
uv sync --all-extras

# Tests
uv run pytest tests/ -q              # all
uv run pytest tests/unit/ -q         # fast, no IO
uv run pytest tests/e2e/ -v          # real server
uv run pytest tests/scenarios/ -q    # scene-agnostic

# Lint, format, type-check
uv run ruff check --fix src/ tests/
uv run ruff format src/ tests/
uv run mypy src/
```

---

## Community

Join the discussion or ask for help:

- **Discord**: [discord.gg/x9mtbMEx](https://discord.gg/x9mtbMEx)
- **WeChat**: scan the QR below (primarily Chinese-speaking)
- **GitHub Issues**: [report bugs / request features](https://github.com/AIScientists-Dev/WorldSeed/issues)
- **X**: [@morphmind__ai](https://x.com/morphmind__ai?s=11)

<div align="center">
  <img src="docs/assets/wechat-qr.jpg" alt="WeChat QR code" width="180">
</div>

---

MIT. See [`LICENSE`](./LICENSE).

WorldSeed is built for anyone who thinks AI agents deserve a world to live in, not just a task to complete. The engine ships with two example scenes, or [create your own](#create-your-world).
