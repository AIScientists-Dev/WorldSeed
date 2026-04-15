/**
 * Agent tools — perceive and act.
 *
 * These tools let agents interact with the WorldSeed server
 * through the shared gateway WebSocket connection. Each request
 * includes agent_id so the server knows which agent is acting.
 */

import { Type } from "@sinclair/typebox";
import type { ChannelAgentTool, OpenClawConfig } from "openclaw/plugin-sdk";
import { getBridge } from "./gateway.js";

const PerceiveParams = Type.Object({
  agent_id: Type.String({ description: "Agent ID to perceive as" }),
});

const ActParams = Type.Object({
  agent_id: Type.String({ description: "Agent ID performing the action" }),
  action: Type.String({ description: "Action name from action_options in perception (e.g. move, say, observe, take, attempt)" }),
  think_interval: Type.Optional(
    Type.Number({
      description: "How often to wake (in ticks). Lower = more frequent. Default 5.",
    }),
  ),
}, {
  additionalProperties: true,
  description: "Action parameters go as top-level keys alongside agent_id and action. "
    + "Use the parameter names from the action schema returned by worldseed_perceive. "
    + "Example for say: { agent_id, action: 'say', message: 'hello' }. "
    + "Example for move: { agent_id, action: 'move', to: 'hallway' }.",
});

export function createWorldSeedTools(
  _cfg: OpenClawConfig | undefined,
  accountId: string = "default",
): ChannelAgentTool[] {

  const perceiveTool: ChannelAgentTool = {
    name: "worldseed_perceive",
    label: "WorldSeed Perceive",
    description:
      "Observe the world as a specific agent. Returns current state, nearby entities, nearby agents, events, whispers, and action options with resolved targets. Events and messages are drained on read.",
    parameters: PerceiveParams,
    execute: async (_toolCallId, params: any, _signal?, _onUpdate?) => {
      try {
        const bridge = getBridge(accountId);
        if (!bridge) {
          return {
            content: [{ type: "text" as const, text: "Not connected to WorldSeed" }],
            details: {},
          };
        }
        const data = await bridge.sendRequest({
          type: "perceive",
          agent_id: params.agent_id,
        });
        return {
          content: [{ type: "text" as const, text: JSON.stringify(data, null, 2) }],
          details: data,
        };
      } catch (err: any) {
        return {
          content: [{ type: "text" as const, text: `Perceive failed: ${err.message}` }],
          details: {},
        };
      }
    },
  };

  const actTool: ChannelAgentTool = {
    name: "worldseed_act",
    label: "WorldSeed Act",
    description:
      "Submit an action. Pass action parameters as top-level keys (not nested in 'params'). "
      + "Parameter names and types are defined in the action schema from worldseed_perceive's action_options. "
      + "The action is queued and executed on the next tick. Use worldseed_perceive afterwards to see results.",
    parameters: ActParams,
    execute: async (_toolCallId, params: any, _signal?, _onUpdate?) => {
      try {
        const bridge = getBridge(accountId);
        if (!bridge) {
          return {
            content: [{ type: "text" as const, text: "Not connected to WorldSeed" }],
            details: {},
          };
        }
        // Extract known protocol fields; everything else is action params
        const KNOWN_FIELDS = new Set(["agent_id", "action", "think_interval"]);
        const actionParams: Record<string, unknown> = {};
        for (const [key, value] of Object.entries(params)) {
          if (!KNOWN_FIELDS.has(key)) {
            actionParams[key] = value;
          }
        }
        const msg: Record<string, unknown> = {
          type: "act",
          agent_id: params.agent_id,
          action: params.action,
          params: actionParams,
        };
        if (params.think_interval != null) {
          msg.think_interval = params.think_interval;
        }
        const data = await bridge.sendRequest(msg);
        return {
          content: [{ type: "text" as const, text: JSON.stringify(data, null, 2) }],
          details: data,
        };
      } catch (err: any) {
        return {
          content: [{ type: "text" as const, text: `Act failed: ${err.message}` }],
          details: {},
        };
      }
    },
  };

  const registerTool: ChannelAgentTool = {
    name: "worldseed_register",
    label: "WorldSeed Register",
    description:
      "Register yourself in the world. Call this once at the start with your agent_id from SOUL.md. "
      + "You must call this before you can perceive or act.",
    parameters: Type.Object({
      agent_id: Type.String({ description: "Your agent ID from SOUL.md" }),
    }),
    execute: async (_toolCallId, params: any, _signal?, _onUpdate?) => {
      try {
        const bridge = getBridge(accountId);
        if (!bridge) {
          return {
            content: [{ type: "text" as const, text: "Not connected to WorldSeed" }],
            details: {},
          };
        }
        const data = await bridge.sendRequest({
          type: "register",
          agent_id: params.agent_id,
        });
        return {
          content: [{ type: "text" as const, text: JSON.stringify(data, null, 2) }],
          details: data,
        };
      } catch (err: any) {
        return {
          content: [{ type: "text" as const, text: `Register failed: ${err.message}` }],
          details: {},
        };
      }
    },
  };

  const narrateTool: ChannelAgentTool = {
    name: "worldseed_narrate",
    label: "WorldSeed Narrate",
    description:
      "Post a chapter summary. Narrator only — other agents should use worldseed_act.",
    parameters: Type.Object({
      agent_id: Type.String({ description: "Must be 'narrator'" }),
      title: Type.String({ description: "Chapter title capturing the core tension" }),
      tldr: Type.String({ description: "One sentence summary" }),
      body: Type.String({ description: "Narrative text (2-4 short paragraphs)" }),
      asides: Type.Optional(Type.String({ description: "0-3 asides to the reader, separated by blank lines" })),
      whisper_options: Type.Optional(Type.String({ description: "One whisper per aside. Format: 'agent_id: short note'. One per line." })),
    }),
    execute: async (_toolCallId, params: any, _signal?, _onUpdate?) => {
      try {
        const bridge = getBridge(accountId);
        if (!bridge) {
          return {
            content: [{ type: "text" as const, text: "Not connected to WorldSeed" }],
            details: {},
          };
        }
        const data = await bridge.sendRequest({
          type: "narrate",
          agent_id: params.agent_id,
          title: params.title,
          tldr: params.tldr,
          body: params.body,
          asides: params.asides ?? "",
          whisper_options: params.whisper_options ?? "",
        });
        return {
          content: [{ type: "text" as const, text: JSON.stringify(data, null, 2) }],
          details: data,
        };
      } catch (err: any) {
        return {
          content: [{ type: "text" as const, text: `Narrate failed: ${err.message}` }],
          details: {},
        };
      }
    },
  };

  return [perceiveTool, actTool, registerTool, narrateTool];
}
