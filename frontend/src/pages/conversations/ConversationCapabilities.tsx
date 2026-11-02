import { Link } from "react-router";
import { ArrowUpRight } from "lucide-react";
import { ResourceIcon } from "@/components/common/ResourceIcon";
import { EmployeeKnowledge } from "@/components/knowledge/EmployeeKnowledge";
import { FailureNotice } from "@/components/failure/FailureNotice";
import { Button } from "@/components/ui/Button";
import type { AgentUsageDTO } from "@/lib/api/agents";
import { useIdentity } from "@/state/auth/useIdentity";
import { useWorkspaceData } from "@/state/workspace/useWorkspaceData";
import { useResource } from "@/state/shared/useResource";

function PersonalKnowledge({ agent }: { agent: AgentUsageDTO }) {
  const resource = useWorkspaceData().knowledge.employeeBindings(agent.id);
  const state = useResource(resource);
  const selected = state.data?.knowledge_base_ids ?? [];
  return (
    <section className="space-y-3" aria-label="我的挂载知识库">
      <div className="flex min-w-0 items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-sm font-medium">
          <ResourceIcon kind="knowledge" />
          我的知识库
          {state.data && <span className="text-xs text-text-muted">{selected.length}</span>}
        </h3>
        <EmployeeKnowledge agentId={agent.id} agentName={agent.name} compact triggerLabel="管理" />
      </div>
      {state.loading && !state.data && (
        <p role="status" className="type-caption">
          正在读取知识库…
        </p>
      )}
      {state.failure && (
        <FailureNotice
          compact
          failure={state.failure}
          context={{
            operation: "initial-read",
            resource: "knowledge",
            hasUsableData: !!state.data,
          }}
          actions={[{ label: "重新加载", kind: "retry", onClick: () => resource.refresh() }]}
        />
      )}
      {state.data && !selected.length && <p className="type-caption">暂未挂载知识库</p>}
      {state.data && selected.length > 0 && (
        <ul className="space-y-1">
          {selected.map((id) => {
            const library = state.data!.libraries.find((item) => item.id === id);
            return (
              <li key={id} className="min-w-0 text-sm [overflow-wrap:anywhere]">
                {library ? (
                  <Link
                    className="group flex min-w-0 items-center gap-3 rounded-panel px-2 py-3 transition-colors hover:bg-surface"
                    to={`/knowledge/${id}`}
                  >
                    <span className="grid size-9 shrink-0 place-items-center rounded-control bg-surface">
                      <ResourceIcon kind="knowledge" size={18} className="text-text-muted" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate">{library.name}</span>
                      <span className="mt-0.5 block text-xs text-text-muted">
                        {library.document_count} 份文档
                      </span>
                    </span>
                    <ArrowUpRight
                      size={14}
                      aria-hidden="true"
                      className="shrink-0 text-text-muted"
                    />
                  </Link>
                ) : (
                  <span className="text-text-muted">知识库已不可用</span>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

/** Display current resources only; per-reply actions remain the evidence of actual usage. */
export function ConversationCapabilities({ agent }: { agent: AgentUsageDTO }) {
  const identity = useIdentity();
  const skills = agent.skill_assignments.filter((item) => item.enabled);
  const tools =
    agent.tool_grants
      ?.filter((grant) => grant.enabled)
      .flatMap((grant) =>
        grant.tools.map((tool) => ({
          key: `${grant.connection_id}:${tool.name}`,
          name: tool.name,
        })),
      ) ?? [];
  const canUseKnowledge =
    identity.permissions.includes("knowledge:use") && identity.permissions.includes("runs:create");
  return (
    <div className="space-y-7 px-5 pt-2 pb-4">
      <section className="space-y-3" aria-label="已挂载技能">
        <h3 className="flex items-center gap-2 text-sm font-medium">
          <ResourceIcon kind="skill" />
          已挂载技能
          <span className="ml-auto text-xs text-text-muted">{skills.length} 项</span>
        </h3>
        {!skills.length ? (
          <p className="type-caption">暂未挂载技能</p>
        ) : (
          <ul className="space-y-3">
            {skills.map((skill) => (
              <li key={skill.skill_id} className="rounded-control bg-surface/60 px-3 py-3">
                <p className="text-sm [overflow-wrap:anywhere]">{skill.name}</p>
                <p className="type-caption mt-1">
                  {skill.ready ? "已就绪" : skill.readiness_reason || "暂不可用"}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="space-y-3" aria-label="员工工具操作">
        <h3 className="flex items-center gap-2 text-sm font-medium">
          <ResourceIcon kind="capabilities" />
          工具操作
          {agent.tool_grants && (
            <span className="ml-auto text-xs text-text-muted">{tools.length} 项</span>
          )}
        </h3>
        {agent.tool_grants ? (
          tools.length ? (
            <ul className="space-y-2 text-sm [overflow-wrap:anywhere]">
              {tools.map((tool) => (
                <li key={tool.key}>{tool.name}</li>
              ))}
            </ul>
          ) : (
            <p className="type-caption">暂未装配工具操作</p>
          )
        ) : (
          <p className="type-caption">工具操作由员工配置授权，可在工具连接中查看账号状态。</p>
        )}
        {identity.permissions.includes("tools:read") && (
          <Button
            variant="ghost"
            size="sm"
            render={<Link to={`/agents/${agent.id}/connections`} />}
            nativeButton={false}
          >
            我的工具连接
          </Button>
        )}
      </section>
      {canUseKnowledge && <PersonalKnowledge agent={agent} />}
      <p className="text-xs leading-relaxed text-text-muted">
        这里展示当前挂载资源，本轮实际使用情况见回复中的执行过程与引用。
      </p>
    </div>
  );
}
