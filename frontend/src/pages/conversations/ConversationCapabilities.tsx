import { ResourceIcon } from "@/components/common/ResourceIcon";
import type { AgentUsageDTO } from "@/lib/api/agents";

/** Display current resources only; per-reply actions remain the evidence of actual usage. */
export function ConversationCapabilities({ agent }: { agent: AgentUsageDTO }) {
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
      </section>
      <section className="space-y-3" aria-label="员工知识库">
        <h3 className="flex items-center gap-2 text-sm font-medium">
          <ResourceIcon kind="knowledge" />
          员工知识库
          <span className="ml-auto type-caption">{agent.knowledge?.libraries.length ?? 0} 个</span>
        </h3>
        {agent.knowledge?.libraries.length ? (
          <ul className="space-y-2 text-sm">
            {agent.knowledge.libraries.map((library) => (
              <li key={library.id} className="break-words">
                {library.name}
              </li>
            ))}
          </ul>
        ) : (
          <p className="type-caption">暂未装配知识库</p>
        )}
      </section>
      <p className="text-xs leading-relaxed text-text-muted">
        这里展示当前挂载资源，本轮实际使用情况见回复中的执行过程与引用。
      </p>
    </div>
  );
}
