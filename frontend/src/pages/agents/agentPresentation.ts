import type { PublicAgent } from "@/lib/api/agents";
import { agentAvailability } from "@/lib/models/agentAvailability";
import type { AgentPresentation } from "@/pages/agents/types";
import { type AgentSummary as AgentSummary } from "@/lib/models/agent";

/** Map the agent configuration to the shared card contract. */
export function toAgentPresentation(agent: AgentSummary): AgentPresentation {
  return {
    id: agent.id,
    name: agent.name,
    subtitle: agent.category,
    description: agent.description,
    avatarId: agent.avatarId,
    favorite: agent.favorite,
    skillCount: agent.skillAssignments?.filter((a) => a.enabled).length ?? agent.skills.length,
    toolCount: agent.toolCount,
    knowledgeBaseCount: agent.knowledgeBaseCount,
    availability: agentAvailability(agent),
  };
}

export function presentPublicAgent(agent: PublicAgent): AgentPresentation {
  return {
    id: agent.id,
    name: agent.name,
    avatarId: agent.avatar_id,
    subtitle: agent.category,
    description: agent.description,
    favorite: agent.is_favorite,
    skillCount: agent.resource_counts.skills,
    toolCount: agent.resource_counts.tools,
    knowledgeBaseCount: agent.resource_counts.knowledge_bases,
    availability: !agent.is_active
      ? "paused"
      : agent.model_configured
        ? "available"
        : "unconfigured",
  };
}
