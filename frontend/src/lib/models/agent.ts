import type { ToolGrantInput } from "@/lib/api/tools";
export type Agent = {
  id: string;
  createdByUserId?: string | null;
  toolGrants?: ToolGrantInput[];
  code: string;
  name: string;
  role: string;
  description: string;
  category: string;
  icon: "travel" | "knowledge" | "writing" | "analysis" | "support" | "engineering" | "custom";
  avatarId: string;
  systemPrompt: string;
  configurationLoaded?: boolean;
  revision?: number;
  skillAssignments?: {
    skillId: string;
    enabled: boolean;
    parameters: Record<string, unknown>;
    revision?: number;
    ready?: boolean;
    name?: string;
    readinessReason?: string | null;
  }[];
  modelConnectionId?: string | null;
  skills: string[];
  toolCount: number;
  knowledgeBaseCount: number;
  deliverables: string[];
  favorite: boolean;
  active: boolean;
  exampleTasks: string[];
};

export type AgentAvailability = "available" | "paused" | "unconfigured";

/** 目录只提供展示和切换所需字段，不能作为完整配置保存。 */
export type AgentSummary = Omit<Agent, "systemPrompt" | "exampleTasks" | "deliverables">;
