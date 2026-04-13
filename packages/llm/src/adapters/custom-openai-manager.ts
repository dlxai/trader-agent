import { createOpenAICompatProvider } from "./openai-compat.js";
import type { LlmProvider, ProviderId } from "../types.js";

export interface CustomEndpointConfig {
  id: string;
  displayName: string;
  baseUrl: string;
  apiKey?: string;
  modelName: string;
  extraHeaders?: Record<string, string>;
}

export interface AddEndpointInput {
  displayName: string;
  baseUrl: string;
  apiKey?: string;
  modelName: string;
  extraHeaders?: Record<string, string>;
}

export class CustomOpenAIManager {
  private endpoints = new Map<string, CustomEndpointConfig>();

  add(input: AddEndpointInput): CustomEndpointConfig {
    for (const existing of this.endpoints.values()) {
      if (existing.displayName === input.displayName) {
        throw new Error(`Custom endpoint "${input.displayName}" already exists`);
      }
    }
    const sanitized = input.displayName.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/_+$/, "");
    const id = `custom_${sanitized}_${Date.now()}`;
    const config: CustomEndpointConfig = { id, ...input };
    this.endpoints.set(id, config);
    return config;
  }

  remove(id: string): void {
    this.endpoints.delete(id);
  }

  get(id: string): CustomEndpointConfig | undefined {
    return this.endpoints.get(id);
  }

  list(): CustomEndpointConfig[] {
    return Array.from(this.endpoints.values());
  }

  createProvider(id: string): LlmProvider | null {
    const config = this.endpoints.get(id);
    if (!config) return null;
    return createOpenAICompatProvider({
      providerId: config.id as ProviderId,
      displayName: config.displayName,
      apiKey: config.apiKey ?? "",
      baseUrl: config.baseUrl,
      defaultModels: [{ id: config.modelName, contextWindow: 0 }],
      extraHeaders: config.extraHeaders,
    });
  }

  loadAll(configs: CustomEndpointConfig[]): void {
    for (const c of configs) {
      this.endpoints.set(c.id, c);
    }
  }
}
