import type { Agent, AgentAvailability } from "./agent";

type ConversationConfig = Pick<Agent, "active" | "modelConnectionId">;

// Configuration readiness only; model credentials/connectivity are checked by the runtime.
export function agentAvailability(agent: ConversationConfig): AgentAvailability {
  if (!agent.active) return "paused";
  const configured = Boolean(agent.modelConnectionId);
  return configured ? "available" : "unconfigured";
}
export function canStartConversation(agent: ConversationConfig): boolean {
  return agentAvailability(agent) === "available";
}
