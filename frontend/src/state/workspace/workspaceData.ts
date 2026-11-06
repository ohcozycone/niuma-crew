import { request } from "@/lib/api/http";
import { searchResources, type NavigationSummary } from "@/lib/api/navigation";
import { KnowledgeStore } from "@/state/knowledge/knowledgeStore";
import { AgentStore } from "@/state/agents/agentStore";
import { SkillStore } from "@/state/skills/skillStore";
import { Resource, ResourceCache, queryKey } from "@/state/shared/resource";

export type Capability = {
  id: string;
  name: string;
  protocol_name?: string | null;
  description: string;
  kind: "skill" | "mcp_http" | "mcp_stdio";
  enabled: boolean;
};

/** 每个身份的工作台拥有一份实例；只在此处声明不同业务数据之间的刷新关系。 */
export class WorkspaceData {
  private queries = new ResourceCache();
  readonly agents: AgentStore;
  readonly skills: SkillStore;
  readonly knowledge = new KnowledgeStore();
  readonly summary;
  private mounts = 0;
  constructor(readonly admin: boolean) {
    // 固定入口随工作台存活，不能被搜索条件的缓存淘汰。
    this.summary = new Resource((signal) =>
      request<NavigationSummary>(`${admin ? "" : "public/"}configuration-summary`, { signal }),
    );
    this.agents = new AgentStore(admin, (structural) => {
      if (structural) this.summary.invalidate();
      this.queries.invalidate("search");
    });
    this.skills = new SkillStore(admin, () => {
      this.summary.invalidate();
      this.agents.invalidate();
      this.queries.invalidate("capabilities", "search");
    });
  }
  capabilities(query: URLSearchParams) {
    const key = queryKey(query);
    return this.queries.get<{ items: Capability[]; total: number }>(
      `capabilities:${key}`,
      (signal) => request(`capabilities?${key}`, { signal }),
      ["capabilities"],
    );
  }
  search(query: string) {
    return this.queries.get(
      `search:${query}`,
      (signal) => searchResources(this.admin, query, signal),
      ["search"],
    );
  }
  capabilitiesChanged = () => {
    this.queries.invalidate("capabilities", "search");
  };
  retain = () => {
    this.mounts += 1;
    return () => {
      this.mounts -= 1;
      queueMicrotask(() => {
        if (!this.mounts) {
          this.agents.dispose();
          this.skills.dispose();
          this.knowledge.dispose();
          this.summary.dispose();
          this.queries.dispose();
        }
      });
    };
  };
}
