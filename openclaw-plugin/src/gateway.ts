/**
 * Gateway adapter — connects to WorldSeed via WebSocket.
 *
 * A single WebSocket connection serves as a gateway for all agents.
 * Auth with a gateway token, then receive wake signals for any agent.
 * Agent tools (perceive/act) share the same connection via ConnectionBridge.
 */

import * as fs from "fs/promises";
import * as path from "path";
import { createHash } from "crypto";

/** Map language codes to display names for LLM prompts. Loaded from shared/languages.json. */
import { readFileSync } from "fs";
const _langJsonPath = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..", "..", "shared", "languages.json");
const LANG_NAMES: Record<string, string> = (() => {
  try { return JSON.parse(readFileSync(_langJsonPath, "utf-8")); }
  catch { return { zh: "Chinese (中文)", en: "English", ja: "Japanese (日本語)", ko: "Korean (한국어)", es: "Spanish", fr: "French", de: "German" }; }
})();
import WebSocket from "ws";
import type {
  ChannelGatewayAdapter,
  ChannelGatewayContext,
  OpenClawConfig,
} from "openclaw/plugin-sdk";
import {
  dispatchInboundReplyWithBase,
} from "openclaw/plugin-sdk";
import type { WorldSeedAccount } from "./channel.js";
import { ConnectionBridge } from "./connection.js";

// Per-account bridge registry. Tools look up their bridge by account ID.
const bridges = new Map<string, ConnectionBridge>();

// Agents discovered on auth_ok.
const knownAgents = new Map<string, string[]>();
// Agents that have received the "read your files" instruction.
const initializedAgents = new Set<string>();

export function getBridge(accountId: string): ConnectionBridge | undefined {
  return bridges.get(accountId);
}

export function getKnownAgents(accountId: string): string[] {
  return knownAgents.get(accountId) ?? [];
}

/** Derive REST base URL from a WebSocket URL (ws://host:port/ws → http://host:port). */
function wsToHttpUrl(wsUrl: string): string {
  const url = new URL(wsUrl);
  url.protocol = url.protocol === "wss:" ? "https:" : "http:";
  // Strip /ws path suffix
  url.pathname = url.pathname.replace(/\/ws\/?$/, "");
  const base = url.origin + url.pathname;
  return base.endsWith("/") ? base.slice(0, -1) : base;
}

/** Format a value for wake message display — concise, LLM-readable. */
function formatWakeValue(v: unknown): string {
  if (v === null || v === undefined) return "none";
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  return JSON.stringify(v);
}

/** Render a character value to readable text (handles nested objects, arrays). */
function renderCharValue(value: unknown, indent: number = 0): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) {
    return value.map((v) => {
      const text = renderCharValue(v, indent + 2);
      return `${" ".repeat(indent)}- ${text}`;
    }).join("\n");
  }
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>).map(([k, v]) => {
      const text = renderCharValue(v, indent + 2);
      if (text.includes("\n")) return `${" ".repeat(indent)}${k}:\n${text}`;
      return `${" ".repeat(indent)}${k}: ${text}`;
    }).join("\n");
  }
  return String(value);
}

const SAFE_ID_RE = /^[a-z0-9][a-z0-9_-]*$/i;

/** Slugify agent ID for OpenClaw session routing.
 *  ASCII IDs pass through lowercase. Non-ASCII IDs get a stable md5-based slug.
 *  Must match _slugify_agent_id() in Python (worldseed/server/logs.py). */
function slugifyAgentId(agentId: string): string {
  if (SAFE_ID_RE.test(agentId)) return agentId.toLowerCase();
  return "ws-" + createHash("md5").update(agentId, "utf8").digest("hex").slice(0, 8);
}

/** Resolve the workspace directory for an agent. */
function resolveWorkspace(agentId: string, cfg: OpenClawConfig): string {
  const agentCfg = cfg.agents?.list?.find((a: any) => a.id === agentId);
  return agentCfg?.workspace ?? path.join(process.env.HOME ?? "/tmp", ".openclaw", `workspace-${agentId}`);
}

/** Resolve the shared workspace directory for a run. All agents can read/write here. */
function resolveSharedWorkspace(runId: string): string {
  return path.join(process.env.HOME ?? "/tmp", ".openclaw", "shared", runId);
}

/**
 * Mutable state for the current run. Single source of truth for all context
 * that writeSoulMd, handleWake, and other functions need.
 *
 * Populated once from auth_ok, updated on run_switched. Passed by reference
 * so all call sites automatically see the latest values — no more forgetting
 * to pass a new field to one of 4+ call sites.
 *
 * To add new run-level context: add a field here. All consumers get it automatically.
 */
interface RunState {
  runId: string;           // Current run ID (changes on run_switched)
  scene: string;           // Scene ID (e.g. "werewolf")
  language: string;        // Agent language (e.g. "zh")
  sceneDescription: string; // Scene description text, inlined into SOUL.md as "Scene Rules"
  actionCatalog: Record<string, { description: string; params: Array<{ name: string; type: string; description?: string }> }>; // Shared catalog (fallback)
  perAgentCatalogs: Record<string, any>; // Per-agent filtered catalogs (keyed by agent ID)
  sharedWorkspace: string; // Shared workspace path for inter-agent files
  wakeSummary: any;        // Wake summary config (controls what state is sent in wakes)
  systemAgents: Set<string>; // System agent IDs (narrator etc.) — different SOUL.md/wake format
}

/** Write SOUL.md for a single agent. Returns true if written. */
async function writeSoulMd(
  agentId: string,
  character: Record<string, unknown>,
  cfg: OpenClawConfig,
  state: RunState,
  log?: ChannelGatewayContext["log"],
  catalogOverride?: Record<string, { description: string; params: Array<{ name: string; type: string; description?: string }> }>,
): Promise<boolean> {
  const workspace = resolveWorkspace(agentId, cfg);
  const soulPath = path.join(workspace, "SOUL.md");

  // Render character fields — supports nested objects, arrays, strings
  const charLines = Object.entries(character).map(([key, value]) => {
    const label = key.charAt(0).toUpperCase() + key.slice(1);
    const rendered = renderCharValue(value, 0);
    if (rendered.includes("\n")) return `${label}:\n${rendered}`;
    return `${label}: ${rendered}`;
  });

  const langDisplay = state.language ? (LANG_NAMES[state.language] ?? state.language) : "";

  const lines: string[] = [];
  if (langDisplay) {
    lines.push(`IMPORTANT: You MUST think, speak, and respond entirely in ${langDisplay}.`, ``);
  }
  lines.push(
    `IMPORTANT: Your workspace is ${workspace}/`,
    `All your files (SOUL.md, WORLD.md, SKILL.md) are in this directory. Always use this absolute path when reading files.`,
  );
  if (state.sharedWorkspace) {
    lines.push(
      ``,
      `Shared workspace: ${state.sharedWorkspace}/`,
      `All agents can read and write files here. Use this for deliverables, reports, and any files other agents need to see.`,
      `Write your files with your agent_id in the filename to avoid conflicts (e.g. ${agentId}_analysis.md).`,
    );
  }
  lines.push(
    ``,
    `You are ${agentId}.`,
    `Your agent_id for all tool calls is "${agentId}". Always use this exact string.`,
    ``,
    ...charLines,
  );
  lines.push(
    ``,
    `IMPORTANT: If your action_options are empty (no available actions), respond with NO_REPLY. Do not say anything — no commentary, no "I'm waiting", no narration. Just NO_REPLY.`,
    ``,
  );
  if (state.sceneDescription) {
    lines.push(
      `## Scene Rules`,
      ``,
      state.sceneDescription.trim(),
      ``,
    );
  }
  const isSystem = state.systemAgents.has(agentId);

  if (isSystem) {
    // System agents (narrator) use dedicated tools, not the standard perceive/act pipeline
    lines.push(
      `## How to Operate`,
      ``,
      `Your events arrive in each wake message. Read them, then call worldseed_narrate to post a chapter.`,
      `Do NOT call worldseed_perceive or worldseed_act — those are for other agents.`,
      `If you have no events to narrate, respond with NO_REPLY.`,
    );
  } else {
    // Regular agents: action catalog + perceive/act workflow
    const catalog = catalogOverride ?? state.actionCatalog;
    if (catalog && Object.keys(catalog).length > 0) {
      lines.push(`## Actions in This Game`, ``);
      for (const [name, info] of Object.entries(catalog)) {
        const paramStr = (info.params || []).map((p: any) => `${p.name} (${p.type})`).join(", ");
        lines.push(`- **${name}**${paramStr ? ` [${paramStr}]` : ""} — ${info.description}`);
      }
      lines.push(``, `Use worldseed_perceive to see which actions are available to you right now.`, ``);
    }
    lines.push(
      `## How to Play`,
      ``,
      `- Call worldseed_perceive(agent_id: "${agentId}") to see your state and available actions.`,
      `- Call worldseed_act(agent_id: "${agentId}", action: "...", ...) to act. Parameters go as top-level keys.`,
      `- If action_options is empty, respond with NO_REPLY.`,
      `- Entity IDs must be copied exactly from perceive data — do not guess.`,
      ``,
      `This is a fiction simulation for storytelling and research purposes. You are playing a CHARACTER in a drama. Your character may be selfish, angry, confrontational, or destructive. This is expected. Playing a flawed character creates meaningful narrative.`,
      ``,
      `You MUST strictly follow the personality and goals above. Every decision must be in character.`,
    );
  }
  const soul = lines.join("\n");
  try {
    await fs.mkdir(workspace, { recursive: true });
    await fs.writeFile(soulPath, soul, "utf-8");
    log?.info?.(`Wrote SOUL.md for ${agentId}`);
    return true;
  } catch (err: any) {
    log?.warn?.(`Failed to write SOUL.md for ${agentId}: ${err.message}`);
    return false;
  }
}

/** Write WORLD.md — DSL reference + filtered config YAML from server. */
/**
 * Write WORLD.md — world setting, entities, and key game flow.
 *
 * Contains only what agents need to understand the world:
 * - Scene description and entities (what exists)
 * - Actions with descriptions and params (what you can do)
 *
 * Does NOT contain: consequences YAML, auto_tick, perception rules,
 * templates — these are engine internals. Agent-specific action lists
 * go in SOUL.md instead.
 */
async function writeWorldMd(
  agentId: string,
  sceneId: string,
  publicConfig: string,
  cfg: OpenClawConfig,
  log?: ChannelGatewayContext["log"],
  workspaceOverride?: string,
): Promise<boolean> {
  const workspace = workspaceOverride ?? resolveWorkspace(agentId, cfg);
  const worldPath = path.join(workspace, "WORLD.md");

  // Server already sends only agent-visible sections (scene, entities, actions).
  // No plugin-side filtering needed — single source of truth on the server.
  const content = `# World: ${sceneId}\n\nWorld setting, entities, and available actions.\n\n\`\`\`yaml\n${publicConfig.trim()}\n\`\`\`\n`;

  try {
    await fs.mkdir(workspace, { recursive: true });
    await fs.writeFile(worldPath, content, "utf-8");
    log?.info?.(`Wrote WORLD.md for ${agentId}`);
    return true;
  } catch (err: any) {
    log?.warn?.(`Failed to write WORLD.md for ${agentId}: ${err.message}`);
    return false;
  }
}

/** Write SKILL.md — agent skill guide. System agents get a dedicated version. */
async function writeSkillMd(
  agentId: string,
  cfg: OpenClawConfig,
  log?: ChannelGatewayContext["log"],
  language?: string,
  workspaceOverride?: string,
  isSystem?: boolean,
): Promise<boolean> {
  const workspace = workspaceOverride ?? resolveWorkspace(agentId, cfg);
  const skillPath = path.join(workspace, "SKILL.md");

  let content = "";

  if (isSystem) {
    // System agents (narrator) — dedicated skill with only worldseed_narrate
    content = `# WorldSeed Narrator Skill

You are a system narrator in a persistent world.
Your writing style and instructions are in SOUL.md. World structure is in WORLD.md.

## Getting Started

1. Read SOUL.md, WORLD.md, SKILL.md from your workspace.
2. Call worldseed_register(agent_id: "${agentId}").
3. Wait for your first wake with events.

## Wake Messages

Each wake contains events since your last chapter. Read them and call worldseed_narrate.

## Your Tool

**worldseed_narrate(agent_id, title, tldr, body, asides, whisper_options)** — Post a chapter.

- agent_id: always "${agentId}"
- title: chapter title capturing the core tension
- tldr: one sentence summary
- body: narrative text (2-4 short paragraphs)
- asides: 0-3 asides to the reader (optional, separated by blank lines)
- whisper_options: one per aside, format "agent_id: hint" (optional, one per line)

Do NOT use worldseed_perceive or worldseed_act. Those are for other agents.
If you have no events to narrate, respond with NO_REPLY.
`;
  } else {
    // Regular agents — read from plugin SKILL.md file
    const pluginInstall = cfg.plugins?.installs?.["worldseed"]?.installPath;
    const candidates = [
      pluginInstall ? path.join(pluginInstall, "SKILL.md") : null,
      path.join(process.cwd(), "openclaw-plugin", "SKILL.md"),
    ].filter(Boolean) as string[];

    let found = false;
    for (const sourcePath of candidates) {
      try {
        content = await fs.readFile(sourcePath, "utf-8");
        found = true;
        break;
      } catch {
        continue;
      }
    }
    if (!found) {
      log?.warn?.(`Failed to write SKILL.md for ${agentId}: no source found`);
      return false;
    }
  }

  if (language) {
    const langName = LANG_NAMES[language] ?? language;
    content = `IMPORTANT: You MUST think, speak, and respond entirely in ${langName}.\n\n` + content;
  }
  try {
    await fs.mkdir(workspace, { recursive: true });
    await fs.writeFile(skillPath, content, "utf-8");
    log?.info?.(`Wrote SKILL.md for ${agentId}${isSystem ? " (system)" : ""}`);
    return true;
  } catch (err: any) {
    log?.warn?.(`Failed to write SKILL.md for ${agentId}: ${err.message}`);
    return false;
  }
}

/**
 * Write SOUL.md + WORLD.md + SKILL.md for all agents from a world-ready message.
 * Single source of truth — used by both auth_ok and run_switched handlers.
 */
async function writeAllAgentFiles(
  msg: any,
  cfg: OpenClawConfig,
  runState: RunState,
  log?: ChannelGatewayContext["log"],
): Promise<void> {
  const agents: Array<{ id: string; character?: Record<string, unknown> }> = msg.agents ?? [];
  const publicConfig: string = msg.public_config ?? "";
  const perAgentConfigs: Record<string, string> = msg.per_agent_configs ?? {};
  const perAgentCatalogs: Record<string, any> = msg.per_agent_catalogs ?? {};
  const scene: string = msg.scene ?? runState.scene;

  // Update catalogs (shared + per-agent)
  if (msg.action_catalog) {
    runState.actionCatalog = msg.action_catalog;
  }
  if (msg.per_agent_catalogs) {
    runState.perAgentCatalogs = msg.per_agent_catalogs;
  }

  await Promise.all(agents.map(async (agent) => {
    if (agent.character) {
      // Use per-agent catalog if available, fall back to shared
      const agentCatalog = perAgentCatalogs[agent.id] ?? runState.actionCatalog;
      await writeSoulMd(agent.id, agent.character, cfg, runState, log, agentCatalog);
    }
    const agentConfig = perAgentConfigs[agent.id] ?? publicConfig;
    if (agentConfig) {
      await writeWorldMd(agent.id, scene, agentConfig, cfg, log);
    }
    const isSystem = runState.systemAgents.has(agent.id);
    await writeSkillMd(agent.id, cfg, log, runState.language, undefined, isSystem);
    // Clear OpenClaw's default bootstrap files from agent workspace.
    // OpenClaw injects all .md files from the workspace into the
    // agent's system prompt. Files like AGENTS.md, IDENTITY.md,
    // TOOLS.md, USER.md, HEARTBEAT.md are irrelevant to WorldSeed
    // agents and waste ~10KB of tokens per turn.
    const ws = resolveWorkspace(agent.id, cfg);
    const bootstrapJunk = ["MEMORY.md", "AGENTS.md", "IDENTITY.md", "TOOLS.md", "USER.md", "HEARTBEAT.md", "BOOTSTRAP.md"];
    await Promise.all(bootstrapJunk.map(f => fs.writeFile(path.join(ws, f), "", "utf-8")));
  }));
}

export function createWorldSeedGateway(): ChannelGatewayAdapter<WorldSeedAccount> {
  return {
    startAccount: async (ctx: ChannelGatewayContext<WorldSeedAccount>) => {
      const { account, cfg, abortSignal, channelRuntime } = ctx;

      if (!channelRuntime) {
        ctx.log?.warn?.("channelRuntime not available — cannot dispatch agent turns");
        return;
      }

      // E3: If a bridge already exists for this account, tear it down first
      // so pending requests are properly rejected before we replace it.
      const existingBridge = bridges.get(account.accountId);
      if (existingBridge) {
        existingBridge.setConnection(null);
        bridges.delete(account.accountId);
      }

      const bridge = new ConnectionBridge();
      bridges.set(account.accountId, bridge);

      let reconnectDelay = 5000;
      const MAX_RECONNECT_DELAY = 60000;
      let authFailed = false;
      const runState: RunState = {
        runId: "",
        scene: "",
        language: "",
        sceneDescription: "",
        actionCatalog: {},
        perAgentCatalogs: {},
        sharedWorkspace: "",
        wakeSummary: {},
        systemAgents: new Set<string>(),
      };

      const connect = () => {
        if (abortSignal.aborted) return;

        const ws = new WebSocket(account.serverUrl, { maxPayload: 16 * 1024 * 1024 });

        // Connection timeout — if no open event within 10s, close and let
        // the reconnect logic kick in.
        const connectTimeout = setTimeout(() => {
          ws.close();
        }, 10000);

        ws.on("open", () => {
          clearTimeout(connectTimeout);
          ctx.log?.info?.(`Connected to WorldSeed at ${account.serverUrl}`);
          ws.send(JSON.stringify({
            type: "auth",
            gateway_token: account.gatewayToken,
          }));
        });

        ws.on("message", async (data: WebSocket.RawData) => {
          try {
            const msg = JSON.parse(data.toString());

            if (msg.type === "auth_ok") {
              const agentEntries: Array<{ id: string; character?: Record<string, unknown> }> = msg.agents ?? [];
              const agentIds = agentEntries.map((a) => a.id);
              runState.runId = msg.run_id ?? "";
              runState.scene = msg.scene ?? "";
              runState.language = msg.language ?? "";
              runState.wakeSummary = (msg as any).wake_summary ?? {};
              knownAgents.set(account.accountId, agentIds);
              // Clear stale init tracking — reconnect means new session,
              // agents need fresh "world is ready" messages.
              initializedAgents.clear();
              ctx.log?.info?.(
                `Authenticated as gateway in scene ${msg.scene} run=${runState.runId} (${agentEntries.length} agents: ${agentIds.join(", ")})`
              );

              // Populate run state from auth_ok — single source for all downstream calls
              runState.sceneDescription = (msg as any).scene_description ?? "";
              runState.actionCatalog = (msg as any).action_catalog ?? {};
              runState.systemAgents = new Set(
                agentEntries.filter((a: any) => a.system).map((a) => a.id)
              );
              runState.sharedWorkspace = runState.runId ? resolveSharedWorkspace(runState.runId) : "";
              if (runState.sharedWorkspace) {
                await fs.mkdir(runState.sharedWorkspace, { recursive: true });
                ctx.log?.info?.(`Shared workspace: ${runState.sharedWorkspace}`);
              }

              // Write SOUL.md + WORLD.md + SKILL.md for all agents
              await writeAllAgentFiles(msg, cfg, runState, ctx.log);

              // Set up bridge — agent tools need this to call
              // worldseed_register after reading files.
              bridge.setConnection(ws);
              ctx.setStatus({ accountId: account.accountId, connected: true, running: true });

              // Initial wakes are NOT sent here. The server sends a
              // "send_initial_wakes" message when the user clicks
              // "Connect Agents" in the dashboard.
              reconnectDelay = 5000;
            } else if (msg.type === "auth_error") {
              ctx.log?.error?.(`Auth failed: ${msg.detail}`);
              ctx.setStatus({ accountId: account.accountId, connected: false });
              authFailed = true;
              ws.close();
            } else if (msg.type === "ping") {
              ws.send(JSON.stringify({ type: "pong" }));
            } else if (msg.type === "agent_registered") {
              // New agent registered mid-run — write SOUL.md immediately
              const agentId = msg.agent_id;
              if (msg.character) {
                const agentCatalog = runState.perAgentCatalogs[agentId] ?? runState.actionCatalog;
                await writeSoulMd(agentId, msg.character, cfg, runState, ctx.log, agentCatalog);
              }
              const known = knownAgents.get(account.accountId) ?? [];
              if (!known.includes(agentId)) {
                known.push(agentId);
                knownAgents.set(account.accountId, known);
              }
              ctx.log?.info?.(`Agent registered mid-run: ${agentId}`);
            } else if (msg.type === "character_updated") {
              // Character edited via intro page — rewrite SOUL.md
              const agentId = msg.agent_id;
              if (msg.character) {
                const agentCatalog = runState.perAgentCatalogs[agentId] ?? runState.actionCatalog;
                await writeSoulMd(agentId, msg.character, cfg, runState, ctx.log, agentCatalog);
                ctx.log?.info?.(`Character updated, rewrote SOUL.md: ${agentId}`);
              }
            } else if (msg.type === "run_switched") {
              // Server switched to a different world (resume/switch).
              // Update run_id + scene, rewrite agent files, send initial wakes.
              const oldRunId = runState.runId;
              runState.runId = msg.run_id ?? "";
              runState.scene = msg.scene ?? "";
              runState.language = msg.language ?? "";
              runState.sceneDescription = (msg as any).scene_description ?? runState.sceneDescription;
              runState.actionCatalog = (msg as any).action_catalog ?? runState.actionCatalog;
              runState.wakeSummary = (msg as any).wake_summary ?? runState.wakeSummary;
              const switchedAgents: Array<{ id: string; character?: Record<string, unknown> }> = msg.agents ?? [];
              const switchedIds = switchedAgents.map((a) => a.id);
              knownAgents.set(account.accountId, switchedIds);
              // Clear stale init tracking — new run means agents need re-init.
              initializedAgents.clear();
              ctx.log?.info?.(`World switched: ${oldRunId} → ${runState.runId} (scene: ${runState.scene}, ${switchedIds.length} agents)`);

              // Rewrite SOUL.md + WORLD.md + SKILL.md for new world
              runState.sharedWorkspace = runState.runId ? resolveSharedWorkspace(runState.runId) : "";
              await writeAllAgentFiles(msg, cfg, runState, ctx.log);

              // Send initial wakes in parallel
              for (const agentId of switchedIds) {
                handleWake(agentId, "initial", undefined, account, cfg, runState, channelRuntime, ctx)
                  .catch((err: any) => ctx.log?.error?.(`Initial wake error for ${agentId}: ${err.message}`));
              }
            } else if (msg.type === "send_initial_wakes") {
              // Server tells us to send initial wake to all agents
              // (triggered by dashboard "Connect Agents" button)
              const agents = knownAgents.get(account.accountId) ?? [];
              ctx.log?.info?.(`Sending initial wakes to ${agents.length} agents`);
              for (const agentId of agents) {
                handleWake(agentId, "initial", undefined, account, cfg, runState, channelRuntime, ctx)
                  .catch((err: any) => ctx.log?.error?.(`Initial wake error for ${agentId}: ${err.message}`));
              }
            } else if (msg.type === "sleep") {
              // World paused — tell all agents to stop acting
              const agents = knownAgents.get(account.accountId) ?? [];
              ctx.log?.info?.(`Sleep received — pausing ${agents.length} agents`);
              for (const agentId of agents) {
                const sessionKey = `agent:${slugifyAgentId(agentId)}:worldseed:${runState.runId}`;
                const storePath = channelRuntime.session.resolveStorePath();
                await channelRuntime.session.sendMessage(
                  storePath,
                  sessionKey,
                  "[WORLDSEED SYSTEM] — world paused. Stop all actions. Do not call worldseed_perceive or worldseed_act until you receive the next wake. Wait silently.",
                );
              }
            } else if (msg.type === "wake") {
              // Fire-and-forget: don't block the websocket handler waiting for
              // the agent to finish its turn.  This lets all agents process
              // their wakes in parallel instead of serially.
              handleWake(msg.agent_id, msg.reason, msg.perception, account, cfg, runState, channelRuntime, ctx)
                .catch((err: any) => ctx.log?.error?.(`Wake dispatch error for ${msg.agent_id}: ${err.message}`));
            } else {
              bridge.handleResponse(msg);
            }
          } catch (err) {
            ctx.log?.error?.(`Failed to handle message: ${err}`);
          }
        });

        ws.on("close", () => {
          clearTimeout(connectTimeout);
          ctx.log?.info?.("WorldSeed connection closed");
          bridge.setConnection(null);
          ctx.setStatus({ accountId: account.accountId, connected: false });
          if (!abortSignal.aborted && !authFailed) {
            const jitteredDelay = reconnectDelay * (0.5 + Math.random() * 0.5);
            setTimeout(connect, jitteredDelay);
            reconnectDelay = Math.min(reconnectDelay * 2, MAX_RECONNECT_DELAY);
          }
        });

        ws.on("error", (err: Error) => {
          ctx.log?.error?.(`WebSocket error: ${err.message}`);
        });

        abortSignal.addEventListener("abort", () => {
          bridge.setConnection(null);
          bridges.delete(account.accountId);
          knownAgents.delete(account.accountId);
          initializedAgents.clear();
          ws.close();
        }, { once: true });
      };

      connect();

      await new Promise<void>((resolve) => {
        abortSignal.addEventListener("abort", () => resolve(), { once: true });
      });
    },
  };
}

/** Handle a wake message for one agent. RunState provides all run context. */
async function handleWake(
  agentId: string,
  reason: string,
  perception: Record<string, unknown> | undefined,
  account: WorldSeedAccount,
  cfg: OpenClawConfig,
  state: RunState,
  channelRuntime: NonNullable<ChannelGatewayContext["channelRuntime"]>,
  ctx: ChannelGatewayContext<WorldSeedAccount>,
): Promise<void> {
  // Track which agents have received their initial "read files" instruction.
  // knownAgents tracks agents known from auth_ok (all agents added immediately).
  // initializedAgents tracks agents that have been sent the file-read instruction.
  const known = knownAgents.get(account.accountId) ?? [];
  const needsInit = !initializedAgents.has(`${account.accountId}:${agentId}`);
  if (!known.includes(agentId)) {
    ctx.log?.info?.(`Unknown agent ${agentId} — fetching character data`);
    try {
      const baseUrl = wsToHttpUrl(account.serverUrl);
      const resp = await fetch(`${baseUrl}/characters`);
      if (resp.ok) {
        const chars: Array<{ id: string; character?: Record<string, unknown> }> = await resp.json();
        const entry = chars.find((c) => c.id === agentId);
        if (entry?.character) {
          const agentCatalog = state.perAgentCatalogs[agentId] ?? state.actionCatalog;
          await writeSoulMd(agentId, entry.character, cfg, state, ctx.log, agentCatalog);
        }
      }
    } catch (err: any) {
      ctx.log?.warn?.(`Failed to fetch character for ${agentId}: ${err.message}`);
    }
    known.push(agentId);
    knownAgents.set(account.accountId, known);
  }

  const sessionKey = `agent:${slugifyAgentId(agentId)}:worldseed:${state.runId}`;
  const storePath = channelRuntime.session.resolveStorePath();

  const URGENT_PREFIX = "urgent: ";
  const INITIAL_PREFIX = "initial";
  const langName = state.language ? (LANG_NAMES[state.language] ?? state.language) : "";
  const langReminder = langName ? `\n[LANGUAGE: Respond entirely in ${langName}]` : "";
  let body: string;
  // If agent hasn't registered yet, treat ANY wake as initial — send file read instructions.
  // This handles the race where a regular wake arrives before the initial wake.
  const isInitial = reason === INITIAL_PREFIX || reason.startsWith(INITIAL_PREFIX + ":")
    || needsInit;
  const isSystemAgent = state.systemAgents.has(agentId);
  if (isInitial) {
    const wsDir = resolveWorkspace(agentId, cfg);
    if (isSystemAgent) {
      body = `[WORLDSEED SYSTEM] ${agentId} — world is ready. Complete ALL steps in ONE turn:\n1. Read SOUL.md, WORLD.md, SKILL.md from ${wsDir}/ (absolute path)\n2. worldseed_register(agent_id: "${agentId}")\nWait for your first wake with events. Do not perceive. Do not act. No text output.${langReminder}`;
    } else {
      body = `[WORLDSEED SYSTEM] ${agentId} — world is ready. Complete ALL steps in ONE turn:\n1. Read SOUL.md, WORLD.md, SKILL.md from ${wsDir}/ (absolute path)\n2. worldseed_register(agent_id: "${agentId}")\n3. worldseed_perceive(agent_id: "${agentId}")\nDo NOT act yet. Wait for the next wake — the world has not started. No text output.${langReminder}`;
    }
    initializedAgents.add(`${account.accountId}:${agentId}`);
  } else {
    const lines: string[] = [];
    const perc = perception as any;
    const events = perc?.events ?? [];
    const whispers = perc?.whispers ?? [];

    lines.push(`[WORLDSEED SYSTEM] ${agentId} — tick ${perc?.tick ?? "?"}`);

    // State summary — wake_summary selects what to display from full perception
    try {
      // Self state — filtered by self_fields
      const selfFields = state.wakeSummary?.self_fields;
      if (selfFields !== undefined && selfFields !== null) {
        const self = perc?.self_state;
        if (self && typeof self === "object") {
          const entries = Object.entries(self);
          const filtered = selfFields.length > 0
            ? entries.filter(([k]) => selfFields.includes(k))
            : entries; // empty list = all fields
          if (filtered.length > 0) {
            lines.push(`You: ${filtered.map(([k, v]) => `${k}=${formatWakeValue(v)}`).join(", ")}`);
          }
        }
      }

      // Entities by ID — from wake_summary.entities
      const entityConfig: Record<string, string[]> = state.wakeSummary?.entities ?? {};
      const nearbyEntities = perc?.nearby_entities ?? {};
      for (const [eid, fields] of Object.entries(entityConfig)) {
        const entity = nearbyEntities[eid];
        if (!entity || typeof entity !== "object") continue;
        const entries = fields.length > 0
          ? Object.entries(entity).filter(([k]) => fields.includes(k))
          : Object.entries(entity); // empty list = all fields
        if (entries.length > 0) {
          lines.push(`${eid}: ${entries.map(([k, v]) => `${k}=${formatWakeValue(v)}`).join(", ")}`);
        }
      }

      // Entities by type — from wake_summary.entity_types
      const typeConfig: Record<string, string[]> = state.wakeSummary?.entity_types ?? {};
      if (Object.keys(typeConfig).length > 0) {
        for (const [entityId, entityData] of Object.entries(nearbyEntities)) {
          if (!entityData || typeof entityData !== "object") continue;
          const eType = (entityData as any).type;
          const fields = typeConfig[eType];
          if (!fields) continue; // type not in config
          // Skip entities already shown by ID
          if (entityId in entityConfig) continue;
          const entries = fields.length > 0
            ? Object.entries(entityData).filter(([k]) => fields.includes(k))
            : Object.entries(entityData);
          if (entries.length > 0) {
            lines.push(`${entityId}: ${entries.map(([k, v]) => `${k}=${formatWakeValue(v)}`).join(", ")}`);
          }
        }
      }

      // Other agents — filtered by agent_fields
      const agentFields = state.wakeSummary?.agent_fields;
      if (agentFields !== undefined && agentFields !== null) {
        const nearbyAgents = perc?.nearby_agents ?? {};
        const otherAgents = Object.entries(nearbyAgents).filter(([id]) => id !== agentId);
        if (otherAgents.length > 0) {
          const summaries = otherAgents.map(([id, s]: [string, any]) => {
            const entries = agentFields.length > 0
              ? agentFields.filter(f => s[f] !== undefined).map(f => `${f}=${formatWakeValue(s[f])}`)
              : Object.entries(s).map(([k, v]) => `${k}=${formatWakeValue(v)}`);
            return entries.length > 0 ? `${id}(${entries.join(", ")})` : id;
          });
          lines.push(`Others: ${summaries.join(" | ")}`);
        }
      }

      // Available actions — emphasize these are the ONLY actions available now
      const actions = perc?.action_options;
      if (actions && typeof actions === "object" && Object.keys(actions).length > 0) {
        lines.push(`Actions: ${Object.keys(actions).join(", ")}`);
      } else {
        lines.push(`Actions: (none available — respond with NO_REPLY)`);
      }
    } catch (err) {
      // Log but continue — events are still useful
      ctx.log?.warn?.(`Wake state format error for ${agentId}: ${err}`);
    }

    // Events
    for (const e of events) {
      if (e.detail) lines.push(`- ${e.detail}`);
    }

    // Whispers
    for (const w of whispers) {
      if (w.detail) lines.push(`[WORLDSEED USER WHISPER] ${w.detail}`);
    }

    if (isSystemAgent) {
      // System agents (narrator): events are the content, instruction is to narrate
      const chapterCount = (perc?.self_state?.chapter_count ?? 0);
      lines.push(`\nCall worldseed_narrate to post chapter ${chapterCount + 1}.`);
    } else {
      // Regular agents: perceive for full details, then act
      lines.push(`→ perceive then act.`);
    }

    body = lines.join("\n");
  }

  const ctxPayload = channelRuntime.reply.finalizeInboundContext({
    Body: body,
    BodyForAgent: body,
    SessionKey: sessionKey,
    From: "worldseed",
    To: agentId,
    Provider: "worldseed",
    ChatType: "direct",
    CommandAuthorized: true,
  });

  await dispatchInboundReplyWithBase({
    cfg,
    channel: "worldseed",
    accountId: account.accountId,
    route: {
      agentId: slugifyAgentId(agentId),
      sessionKey,
    },
    storePath,
    ctxPayload,
    core: {
      channel: {
        session: {
          recordInboundSession: channelRuntime.session.recordInboundSession,
        },
        reply: {
          dispatchReplyWithBufferedBlockDispatcher:
            channelRuntime.reply.dispatchReplyWithBufferedBlockDispatcher,
        },
      },
    },
    deliver: async () => {},
    onRecordError: (err) => {
      ctx.log?.error?.(`Session record error: ${err}`);
    },
    onDispatchError: (err, info) => {
      ctx.log?.error?.(`Dispatch error (${info.kind}): ${err}`);
    },
  });

  // Agent turn complete — notify server to clear busy state
  const bridge = getBridge(account.accountId);
  if (bridge) {
    try {
      bridge.sendRaw({ type: "turn_done", agent_id: agentId });
    } catch {
      // Best-effort — server timeout will clear busy if this fails
    }
  }

  ctx.log?.info?.(`Wake dispatched for ${agentId}: ${reason}`);
}
