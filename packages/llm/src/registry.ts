import type { AgentId, LlmProvider, ProviderId } from "./types.js";

export interface AgentAssignment {
  providerId: ProviderId;
  modelId: string;
}

export interface ProviderRegistry {
  register(provider: LlmProvider): void;
  unregister(providerId: ProviderId): void;
  get(providerId: ProviderId): LlmProvider | undefined;
  list(): LlmProvider[];
  listConnected(): LlmProvider[];

  assignAgentModel(agentId: AgentId, providerId: ProviderId, modelId: string): void;
  getAgentAssignment(agentId: AgentId): AgentAssignment | undefined;
  getProviderForAgent(agentId: AgentId): { provider: LlmProvider; modelId: string } | null;
}

export function createProviderRegistry(): ProviderRegistry {
  const providers = new Map<ProviderId, LlmProvider>();
  const assignments = new Map<AgentId, AgentAssignment>();

  return {
    register(provider) {
      providers.set(provider.id, provider);
    },
    unregister(providerId) {
      providers.delete(providerId);
      for (const [agentId, assignment] of assignments.entries()) {
        if (assignment.providerId === providerId) {
          assignments.delete(agentId);
        }
      }
    },
    get(providerId) {
      return providers.get(providerId);
    },
    list() {
      return Array.from(providers.values());
    },
    listConnected() {
      return Array.from(providers.values()).filter((p) => p.isConnected());
    },
    assignAgentModel(agentId, providerId, modelId) {
      if (!providers.has(providerId)) {
        throw new Error(`registry.assignAgentModel: provider ${providerId} not registered`);
      }
      assignments.set(agentId, { providerId, modelId });
    },
    getAgentAssignment(agentId) {
      return assignments.get(agentId);
    },
    getProviderForAgent(agentId) {
      const assignment = assignments.get(agentId);
      if (!assignment) return null;
      const provider = providers.get(assignment.providerId);
      if (!provider) return null;
      return { provider, modelId: assignment.modelId };
    },
  };
}
