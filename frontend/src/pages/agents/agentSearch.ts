import { type AgentSummary } from "@/lib/models/agent";
import { type SkillListItem } from "@/lib/models/skill";

export function agentMatches(agent: AgentSummary, query: string, catalog: SkillListItem[]) {
  return [
    agent.name,
    agent.description,
    agent.category,
    ...agent.skills.map((id) => catalog.find((skill) => skill.id === id)?.name || ""),
  ]
    .join(" ")
    .toLowerCase()
    .includes(query.trim().toLowerCase());
}
