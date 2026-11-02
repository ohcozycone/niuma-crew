import type { ToolGrant } from "./tools";
import { request } from "./http";
import type { Agent, AgentSummary } from "@/lib/models/agent";
import { findAvatar } from "@/lib/avatars/registry";

export type AgentResourceCountsDTO = {
  skills: number;
  tools: number;
  knowledge_bases: number;
};

export type AgentDTO = {
  id: string;
  created_by_user_id?: string | null;
  tool_grants?: ToolGrant[];
  code: string | null;
  name: string;
  avatar_id: string;
  category: string;
  description: string;
  role_label: string | null;
  system_prompt: string;
  revision: number;
  model_connection_id: string | null;
  is_active: boolean;
  is_favorite: boolean;
  example_tasks: string[];
  deliverables: string[];
  skill_assignments: {
    skill_id: string;
    enabled: boolean;
    parameters: Record<string, unknown>;
    revision: number;
    ready: boolean;
    name: string;
    readiness_reason: string | null;
  }[];
  resource_counts: AgentResourceCountsDTO;
  created_at: string;
  updated_at: string;
};
type Page<T> = { items: T[]; total: number; offset: number; limit: number };

export function fromAgent(data: AgentDTO): Agent {
  return {
    configurationLoaded: true,
    createdByUserId: data.created_by_user_id,
    toolGrants: (data.tool_grants ?? []).map((grant) => ({
      connection_id: grant.connection_id,
      tools: grant.tools.map((tool) => tool.name),
      expected_descriptors: Object.fromEntries(
        grant.tools.map((tool) => [tool.name, tool.descriptor_hash]),
      ),
      scope_policy: grant.scope_policy,
      account_mode: grant.account_mode ?? "personal",
      enabled: grant.enabled,
    })),
    id: data.id,
    code: data.code ?? "",
    name: data.name,
    avatarId: data.avatar_id,
    category: data.category,
    description: data.description,
    role: data.role_label ?? "",
    systemPrompt: data.system_prompt,
    revision: data.revision,
    skillAssignments: data.skill_assignments.map((a) => ({
      skillId: a.skill_id,
      enabled: a.enabled,
      parameters: a.parameters,
      revision: a.revision,
      ready: a.ready,
      name: a.name,
      readinessReason: a.readiness_reason,
    })),
    modelConnectionId: data.model_connection_id,
    active: data.is_active,
    favorite: data.is_favorite,
    exampleTasks: data.example_tasks,
    deliverables: data.deliverables,
    skills: data.skill_assignments.map((a) => a.skill_id),
    toolCount: data.resource_counts.tools,
    knowledgeBaseCount: data.resource_counts.knowledge_bases,
    icon: "custom",
  };
}
export function agentInput(data: Agent, create = false) {
  return {
    ...(data.toolGrants !== undefined ? { tool_grants: data.toolGrants } : {}),
    name: data.name,
    avatar_id: findAvatar(data.avatarId)?.id ?? data.avatarId,
    code: data.code || null,
    category: data.category,
    description: data.description,
    role_label: data.role || null,
    system_prompt: data.systemPrompt,
    ...(!create ? { expected_revision: data.revision } : {}),
    model_connection_id: data.modelConnectionId ?? null,
    is_active: data.active,
    is_favorite: data.favorite,
    example_tasks: data.exampleTasks,
    deliverables: data.deliverables,
    skill_assignments: data.skills.map((skillId) => {
      const prior = data.skillAssignments?.find((a) => a.skillId === skillId);
      return {
        skill_id: skillId,
        enabled: prior?.enabled ?? true,
        parameters: prior?.parameters ?? {},
      };
    }),
  };
}
export async function saveAgent(agent: Agent, create: boolean) {
  if (!create && !agent.configurationLoaded) throw new Error("请先读取员工详情，再保存配置。");
  return fromAgent(
    await request<AgentDTO>(create ? "agents" : `agents/${agent.id}`, {
      method: create ? "POST" : "PATCH",
      body: JSON.stringify(agentInput(agent, create)),
    }),
  );
}
export async function patchAgent(
  id: string,
  patch: { is_active?: boolean; is_favorite?: boolean },
  revision: number,
) {
  return fromAgent(
    await request<AgentDTO>(`agents/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ ...patch, expected_revision: revision }),
    }),
  );
}
export const deleteAgent = (id: string) => request<void>(`agents/${id}`, { method: "DELETE" });

export type AgentSummaryDTO = Pick<
  AgentDTO,
  | "id"
  | "created_by_user_id"
  | "code"
  | "name"
  | "avatar_id"
  | "category"
  | "description"
  | "role_label"
  | "model_connection_id"
  | "is_active"
  | "is_favorite"
  | "resource_counts"
  | "revision"
  | "updated_at"
> & {
  skill_summaries: { skill_id: string; name: string; enabled: boolean }[];
};
export function fromAgentSummary(data: AgentSummaryDTO): AgentSummary {
  return {
    id: data.id,
    createdByUserId: data.created_by_user_id,
    code: data.code ?? "",
    name: data.name,
    avatarId: data.avatar_id,
    category: data.category,
    description: data.description,
    role: data.role_label ?? "",
    modelConnectionId: data.model_connection_id,
    active: data.is_active,
    favorite: data.is_favorite,
    skills: data.skill_summaries.filter((a) => a.enabled).map((a) => a.skill_id),
    toolCount: data.resource_counts.tools,
    knowledgeBaseCount: data.resource_counts.knowledge_bases,
    revision: data.revision,
    icon: "custom",
  };
}
export const agentPage = (query: URLSearchParams, signal?: AbortSignal) =>
  request<Page<AgentSummaryDTO>>(`agents?${query}`, { signal });
export const getAgent = async (id: string, signal?: AbortSignal) =>
  fromAgent(await request<AgentDTO>(`agents/${id}`, { signal }));

export type PublicAgent = {
  id: string;
  code: string | null;
  name: string;
  avatar_id: string;
  category: string;
  description: string;
  role_label: string | null;
  is_active: boolean;
  is_favorite: boolean;
  example_tasks: string[];
  deliverables: string[];
  skill_ids: string[];
  resource_counts: AgentResourceCountsDTO;
  model_configured: boolean;
};

export type AgentUsageDTO = Pick<
  AgentDTO,
  "id" | "name" | "description" | "avatar_id" | "is_active" | "example_tasks"
> & {
  tool_grants?: ToolGrant[];
  model_configured?: boolean;
  model_connection_id?: string | null;
  skill_assignments: Pick<
    AgentDTO["skill_assignments"][number],
    "skill_id" | "name" | "enabled" | "ready" | "readiness_reason"
  >[];
};
