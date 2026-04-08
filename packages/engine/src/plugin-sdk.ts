/**
 * OpenClaw Plugin SDK - Minimal implementation for Polymarket Trader
 */

export interface PluginContext {
  /** Plugin configuration from openclaw.json */
  config: Record<string, unknown>;
  /** Plugin workspace directory */
  workspaceDir: string;
  /** Logger instance */
  logger: {
    info: (message: string) => void;
    warn: (message: string) => void;
    error: (message: string) => void;
  };
  /** Event bus for inter-plugin communication */
  events: {
    on: (event: string, handler: (data: unknown) => void) => void;
    emit: (event: string, data: unknown) => void;
  };
  /** Cron job registration */
  cron: {
    register: (name: string, schedule: string, handler: () => Promise<void>) => void;
  };
}

export interface PluginDefinition {
  id: string;
  name: string;
  version: string;
  activate: (context: PluginContext) => Promise<void> | void;
  deactivate?: () => Promise<void> | void;
}

export function definePlugin(definition: PluginDefinition): PluginDefinition {
  return definition;
}
