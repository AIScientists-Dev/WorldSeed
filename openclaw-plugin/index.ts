import type { ChannelPlugin, OpenClawPluginApi } from "openclaw/plugin-sdk";
import { worldseedPlugin } from "./src/channel.js";

const plugin = {
  id: "worldseed",
  name: "WorldSeed",
  description: "WorldSeed persistent world channel plugin",
  register(api: OpenClawPluginApi) {
    api.registerChannel({ plugin: worldseedPlugin as ChannelPlugin });
  },
};

export default plugin;
