import type { Agent } from "@/lib/models/agent";
import type { Skill } from "@/lib/models/skill";
import type { ToolConnection, ToolDescriptor } from "@/lib/api/tools";
import { initialAgents } from "./agents";

// The preview uses the production shapes, with fixture-only identities and no API writes.
export type DemoCapability = {
  id: string;
  kind: "skill" | "mcp" | "native";
  name: string;
  description: string;
  skillId?: string;
  url?: string;
  tools: { name: string; label: string }[];
};
export type DemoAssignment = {
  capabilityId: string;
  enabled: boolean;
  parameters: string;
  supplement: string;
  connectionId: string;
  tools: string[];
  toolHashes: Record<string, string>;
  maxCalls: number;
};
export type DemoEmployee = { agent: Agent; assignments: DemoAssignment[] };
export type DemoAlias = { name: string; description: string };
export type DemoConnection = ToolConnection & {
  capabilityId: string;
  aliases: Record<string, DemoAlias>;
  remoteCatalog: ToolDescriptor[];
};
export const demoSearchCatalog: ToolDescriptor[] = [
  {
    name: "tavily_search",
    description: "Search the web for relevant pages.",
    descriptor_hash: "demo-search-v1",
  },
  {
    name: "tavily_extract",
    description: "Extract text from the supplied URLs.",
    descriptor_hash: "demo-extract-v1",
  },
];

export const demoSkills: Skill[] = [
  {
    id: "demo-summary",
    name: "资料要点整理",
    category: "知识管理",
    description: "沿用知识专员的工作场景，从已提供资料中整理结论与出处。",
    instructions:
      "根据已提供资料整理要点，保留来源；区分事实、推断与待确认事项。资料不足时明确说明。",
    input: "用户提供的资料或已获准读取的文件",
    output: "要点摘要、来源和待确认事项",
    example: "整理一份团队文档的核心结论。",
    configurationLoaded: true,
    configurationSchema: {},
    active: true,
  },
];
export const initialCapabilities: DemoCapability[] = [
  ...demoSkills.map((skill) => ({
    id: skill.id,
    skillId: skill.id,
    name: skill.name,
    description: skill.description,
    kind: "skill" as const,
    tools: [],
  })),
  {
    id: "demo-tavily",
    name: "网页搜索与读取",
    kind: "mcp",
    description: "沿用工具连接页的 Tavily 示例，分别批准操作，再授予员工许可。",
    url: "https://mcp.tavily.com/mcp",
    tools: [
      { name: "tavily_search", label: "搜索网页" },
      { name: "tavily_extract", label: "读取网页" },
    ],
  },
  {
    id: "demo-sandbox",
    name: "沙箱工作区",
    kind: "native",
    description: "沿用现有原生沙箱连接，按员工选择文件操作、命令执行和调用预算。",
    tools: [
      { name: "ls", label: "列出文件" },
      { name: "read_file", label: "读取文件" },
      { name: "glob", label: "查找路径" },
      { name: "grep", label: "搜索内容" },
      { name: "write_file", label: "写入文件" },
      { name: "edit_file", label: "修改文件" },
      { name: "delete", label: "删除文件" },
      { name: "execute", label: "执行命令" },
    ],
  },
];

export function assignmentFor(capabilityId: string): DemoAssignment {
  return {
    capabilityId,
    enabled: true,
    parameters: "{}",
    supplement: "",
    connectionId: "",
    tools: [],
    toolHashes: {},
    maxCalls: 5,
  };
}
export function createDemoEmployees(): DemoEmployee[] {
  return ["knowledge", "engineering"].map((id, index) => {
    const source = initialAgents.find((agent) => agent.id === id)!;
    const skillId = "demo-summary";
    return {
      agent: {
        ...source,
        skills: [skillId],
        skillAssignments: [{ skillId, enabled: true, parameters: {} }],
        active: true,
        modelConnectionId: "demo-model",
      },
      assignments: [
        assignmentFor(skillId),
        {
          ...assignmentFor("demo-tavily"),
          connectionId: index === 0 ? "demo-search-team" : "demo-search-dev",
          tools: ["tavily_search"],
          toolHashes: { tavily_search: "demo-search-v1" },
          maxCalls: index === 0 ? 5 : 3,
        },
      ],
    };
  });
}
export function createDemoConnections(): DemoConnection[] {
  return ["demo-search-team", "demo-search-dev"].map((id, index) => ({
    id,
    capabilityId: "demo-tavily",
    name: index === 0 ? "团队检索连接" : "研发检索连接",
    kind: "mcp_http",
    service_id: null,
    account_scope: "personal",
    created_by_user_id: null,
    tool_annotations: {},
    annotations_revision: 1,
    provider_key: null,
    auth_type: "bearer",
    public_config: { url: "https://mcp.tavily.com/mcp" },
    enabled: true,
    has_credential: true,
    config_revision: 1,
    credential_revision: 1,
    catalog_revision: 1,
    approved_catalog: structuredClone(demoSearchCatalog),
    remoteCatalog: structuredClone(demoSearchCatalog),
    aliases: {
      tavily_search: { name: "搜索网页", description: "搜索公开网页中的相关资料。" },
      tavily_extract: { name: "读取网页", description: "提取指定网页的正文。" },
    },
    discovery_candidate: null,
  }));
}
