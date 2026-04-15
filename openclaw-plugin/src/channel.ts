/**
 * WorldSeed channel plugin.
 *
 * Connects to a WorldSeed server via WebSocket as a gateway.
 * A single connection serves all agents. Session keys are
 * `agent:{agentId}:worldseed:{runId}` — NOT `hook:*` — so no
 * security prompt wrapping is triggered.
 */

import * as fs from "fs";
import * as path from "path";

import type {
  ChannelCapabilities,
  ChannelConfigAdapter,
  ChannelMeta,
  ChannelOutboundAdapter,
  ChannelOutboundContext,
  ChannelPlugin,
  ChannelAgentToolFactory,
  OpenClawConfig,
} from "openclaw/plugin-sdk";
import { createWorldSeedGateway } from "./gateway.js";
import { createWorldSeedTools } from "./tools.js";

export type WorldSeedAccount = {
  accountId: string;
  serverUrl: string;
  gatewayToken: string;
};

const meta: ChannelMeta = {
  id: "worldseed",
  label: "WorldSeed",
  selectionLabel: "WorldSeed",
  docsPath: "/docs/worldseed",
  blurb: "Connect to a WorldSeed persistent world server",
};

const capabilities: ChannelCapabilities = {
  chatTypes: ["direct"],
};

const config: ChannelConfigAdapter<WorldSeedAccount> = {
  listAccountIds: (cfg: OpenClawConfig) => {
    const accounts = (cfg as any).channels?.worldseed?.accounts;
    if (accounts && typeof accounts === "object") {
      return Object.keys(accounts);
    }
    const pc = (cfg as any).plugins?.entries?.worldseed?.config;
    return pc?.agentId ? [pc.agentId] : ["default"];
  },

  resolveAccount: (cfg: OpenClawConfig, accountId?: string | null) => {
    const id = accountId || "default";
    const accounts = (cfg as any).channels?.worldseed?.accounts;
    if (accounts && accounts[id]) {
      const ac = accounts[id];
      return {
        accountId: id,
        serverUrl: ac.serverUrl ?? "ws://localhost:8000/ws",
        gatewayToken: ac.gatewayToken ?? "",
      };
    }
    const pc = (cfg as any).plugins?.entries?.worldseed?.config ?? {};
    return {
      accountId: id,
      serverUrl: process.env.WORLDSEED_URL ?? pc.serverUrl ?? "ws://localhost:8000/ws",
      gatewayToken: process.env.WORLDSEED_TOKEN ?? pc.gatewayToken ?? "",
    };
  },

  isEnabled: (account: WorldSeedAccount) => {
    return !!account.serverUrl && !!account.gatewayToken;
  },

  isConfigured: (account: WorldSeedAccount) => {
    return !!account.serverUrl && !!account.gatewayToken;
  },
};

const outbound: ChannelOutboundAdapter = {
  deliveryMode: "direct",
  sendText: async (_ctx: ChannelOutboundContext) => {
    return { channel: "worldseed" as any, messageId: "" };
  },
};

let _skillContent: string | null = null;

function loadSkill(): string {
  if (_skillContent !== null) return _skillContent;
  try {
    const skillPath = path.join(path.dirname(new URL(import.meta.url).pathname), "..", "SKILL.md");
    _skillContent = fs.readFileSync(skillPath, "utf-8");
  } catch {
    _skillContent = "";
  }
  return _skillContent;
}

const agentPrompt = {
  messageToolHints: () => [
    `You live in a WorldSeed persistent world. Your SOUL.md has your character, actions, and game rules.

## worldseed_act format
- agent_id: your agent_id (required)
- action: action name from action_options (required)
- Pass action parameters as top-level keys alongside agent_id and action.
- Example: worldseed_act({ agent_id: "old_chen", action: "move", to: "hallway" })`,
  ],
};

const agentTools: ChannelAgentToolFactory = ({ cfg, account }) => {
  const accountId = (account as WorldSeedAccount)?.accountId ?? "default";
  return createWorldSeedTools(cfg, accountId);
};

export const worldseedPlugin: ChannelPlugin<WorldSeedAccount> = {
  id: "worldseed",
  meta,
  capabilities,
  config,
  outbound,
  agentPrompt,
  agentTools,
  gateway: createWorldSeedGateway(),
};
