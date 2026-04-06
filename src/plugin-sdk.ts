/**
 * Inline OpenClaw plugin SDK.
 *
 * This file provides the minimal types and helper to define an OpenClaw plugin
 * without taking a runtime dependency on @rivonclaw/plugin-sdk or
 * @mariozechner/openclaw. The plugin built from these types is loadable into
 * any OpenClaw-compatible runtime, including RivonClaw.
 *
 * Source of truth for the API shape: OpenClaw plugin contract documented at
 * https://github.com/mariozechner/openclaw (vendored types reproduced below).
 */

export type ToolVisibility = "managed" | "always";

/** Minimal OpenClaw plugin API surface — what plugins receive at activation. */
export interface PluginApi {
  id: string;
  logger: {
    info: (msg: string) => void;
    warn: (msg: string) => void;
    error: (msg: string) => void;
  };
  pluginConfig?: Record<string, unknown>;
  on(
    event: string,
    handler: (...args: any[]) => any,
    opts?: { priority?: number }
  ): void;
  registerTool?(
    factory: (ctx: { config?: Record<string, unknown> }) => unknown,
    opts?: { optional?: boolean }
  ): void;
  registerGatewayMethod?(
    name: string,
    handler: (args: {
      params: Record<string, unknown>;
      respond: (
        ok: boolean,
        payload?: unknown,
        error?: { code: string; message: string }
      ) => void;
      context?: { broadcast: (event: string, payload: unknown) => void };
    }) => void
  ): void;
}

/** Tool definition — what plugins provide. */
export interface ToolDefinition {
  name: string;
  label?: string;
  description: string;
  parameters: Record<string, unknown>;
  run?: (...args: any[]) => any;
  [key: string]: unknown;
}

/** Plugin definition — what plugin authors write. */
export interface PluginOptions {
  id: string;
  name: string;
  tools?: ToolDefinition[];
  toolVisibility?: ToolVisibility;
  setup?: (api: PluginApi) => void;
}

/** OpenClaw plugin shape — what OpenClaw expects. */
export interface OpenClawPlugin {
  id: string;
  name: string;
  activate(api: PluginApi): void;
  /** Channel plugins require register() — aliased to activate(). */
  register(api: PluginApi): void;
}

/**
 * Define an OpenClaw plugin with declarative tool registration and automatic
 * framework wiring. Returns an object with both `activate` and `register`
 * methods so the same plugin works whether OpenClaw calls activate() or
 * register() at startup.
 */
export function definePlugin(options: PluginOptions): OpenClawPlugin {
  const visibility: ToolVisibility = options.toolVisibility ?? "managed";

  const plugin: OpenClawPlugin = {
    id: options.id,
    name: options.name,
    activate(api: PluginApi) {
      if (options.tools) {
        const toolOpts = visibility === "managed" ? { optional: true } : undefined;
        for (const toolDef of options.tools) {
          if (typeof api.registerTool === "function") {
            api.registerTool(() => toolDef, toolOpts);
          }
        }
      }
      if (options.setup) {
        options.setup(api);
      }
      api.logger.info(`${options.name} plugin activated`);
    },
    register(api: PluginApi) {
      plugin.activate(api);
    },
  };

  return plugin;
}
