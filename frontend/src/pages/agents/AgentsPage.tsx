import { FailureState } from "@/components/failure/FailureState";
import { SelectField } from "@/components/ui/SelectField";
import { SearchInput } from "@/components/common/SearchInput";
import { PageContainer } from "@/components/common/PageContainer";
import { AgentDirectoryPagination } from "./AgentDirectoryPagination";
import { useCallback, useState } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router";
import { useIdentity } from "@/state/auth/useIdentity";
import { identityKey } from "@/lib/identity";
import { Button } from "@/components/ui/Button";
import { EmployeeKnowledge } from "@/components/knowledge/EmployeeKnowledge";

import { PageHeading } from "@/components/common/PageHeading";
import { ResourceStatus } from "@/components/configuration/ResourceStatus";
import { useWorkspaceData } from "@/state/workspace/useWorkspaceData";
import { useAgentDirectory } from "./useAgentDirectory";
import { useAgentEditor } from "./useAgentEditor";
import { returnPath, sourceLink } from "@/lib/navigation";
import { useQueryState } from "@/hooks/useQueryState";
import { clearDraft, draftKey } from "@/lib/draft";
import { AgentDirectory } from "./AgentDirectory";
import { AgentConfiguration, type ConfigurationTab } from "./AgentConfiguration";
import { AgentCard } from "./AgentCard";
import { AgentDeletionDialog } from "./AgentDeletionDialog";
import { presentPublicAgent } from "@/pages/agents/agentPresentation";
import { type AgentSummary } from "@/lib/models/agent";
import { type AgentAction } from "./types";
export function AgentsPage() {
  const data = useAgentDirectory();
  return (
    <ResourceStatus data={data} resource="agent">
      <Directory data={data} />
    </ResourceStatus>
  );
}
function Directory({ data }: { data: ReturnType<typeof useAgentDirectory> }) {
  const identity = useIdentity();
  const navigate = useNavigate();
  const location = useLocation();
  const [query, setQuery] = useQueryState("q");
  const [filter, setFilter] = useQueryState("filter", "all");
  const [category, setCategory] = useQueryState("category", "all");
  const [skill, setSkill] = useQueryState("skill");
  const admin = identity.permissions.includes("agents:read");
  const shared = useWorkspaceData();
  const action = useCallback(
    (agent: AgentSummary, kind: AgentAction) => {
      if (kind === "favorite" || kind === "toggle") {
        void shared.agents.setStatus(
          agent.id,
          kind === "favorite" ? "is_favorite" : "is_active",
          kind === "favorite" ? !agent.favorite : !agent.active,
        );
        return;
      }
      if (kind === "assign" || kind === "open") {
        navigate(sourceLink(`/agents/${agent.id}/home`));
        return;
      }
      navigate(sourceLink(`/agents/${agent.id}${kind === "skills" ? "?tab=capabilities" : ""}`));
    },
    [navigate, shared],
  );
  if (admin)
    return (
      <AgentDirectory
        pagination={
          <AgentDirectoryPagination
            total={data.agentTotal}
            pageSize={data.pageSize}
            loading={data.loading}
          />
        }
        saveMessage={location.state?.agentSaved === true ? "员工配置已保存。" : ""}
        totalAgents={data.directoryTotal}
        matchedTotal={data.agentTotal}
        loading={data.loading}
        loadError={data.listError}
        ids={data.ids}
        categories={data.categories}
        availableCount={data.availableCount}
        query={query}
        setQuery={setQuery}
        filter={filter}
        setFilter={setFilter}
        category={category}
        setCategory={setCategory}
        agentSkillId={skill || null}
        setAgentSkillId={setSkill}
        canEdit={(agent) =>
          !agent.createdByUserId || agent.createdByUserId === identity.actor.user?.id
        }
        onCreate={() => navigate(sourceLink("/agents/new"))}
        onAction={action}
      />
    );
  const visible = data.publicAgents;
  return (
    <PageContainer>
      <PageHeading title="数字员工" description="浏览员工的职责与能力，了解他们能做什么。" />
      <div className={"flex flex-wrap items-center gap-3 my-5"}>
        <SearchInput
          label="搜索员工"
          debounceMs={300}
          onChange={(nextValue) => setQuery(nextValue)}
          value={query}
          placeholder="搜索员工、岗位或职责…"
          className="w-77.5"
        />
        <SelectField
          aria-label="员工状态筛选"
          value={filter}
          onValueChange={(nextValue) => setFilter(nextValue)}
          options={[
            { value: "all", label: "全部员工" },
            { value: "favorites", label: "已收藏" },
            { value: "active", label: "可对话" },
            { value: "paused", label: "已暂停" },
          ]}
        />
        <SelectField
          aria-label="按岗位分类"
          value={category}
          onValueChange={(nextValue) => setCategory(nextValue)}
          options={[
            { value: "all", label: "全部岗位" },
            ...[...new Set(data.publicAgents.map((e) => e.category))].map((c) => ({
              value: c,
              label: c,
            })),
          ]}
        />
        <AgentDirectoryPagination
          total={data.agentTotal}
          pageSize={data.pageSize}
          loading={data.loading}
        />
      </div>
      {skill && (
        <Button variant="ghost" onClick={() => setSkill(null)}>
          清除技能筛选
        </Button>
      )}
      <div aria-busy={data.loading && !data.listError}>
        <div>
          <div className={"employee-grid"}>
            {visible.map((e) => (
              <AgentCard
                key={e.id}
                agent={presentPublicAgent(e)}
                readOnly
                usable={identity.permissions.includes("runs:create")}
                onAction={(_id, kind) =>
                  navigate(
                    kind === "assign" || kind === "open"
                      ? sourceLink(`/agents/${e.id}/home`)
                      : sourceLink(`/agents/${e.id}`),
                  )
                }
              />
            ))}
          </div>
          {!visible.length && <p className={"py-12"}>没有找到符合条件的员工</p>}
        </div>
      </div>
      <div
        role="status"
        className={
          "flex items-center justify-between gap-2.5 mt-5 text-text-muted text-[length:var(--os-text-caption)] max-[760px]:text-[length:var(--os-text-caption)] max-[760px]:[&_>_span:last-child]:hidden"
        }
      >
        {`本页显示 ${visible.length} 位员工 · 只读访问`}
        {data.loading && " · 正在更新…"}
      </div>
    </PageContainer>
  );
}
export function AgentEditorPage() {
  const data = useAgentEditor();
  return (
    <ResourceStatus data={data} resource="agent" returnTo="/agents">
      <Editor data={data} />
    </ResourceStatus>
  );
}
function Editor({ data }: { data: ReturnType<typeof useAgentEditor> }) {
  const { id } = useParams();
  const [params] = useSearchParams();
  const [rawTab, setTab] = useQueryState("tab", "identity");
  const navigate = useNavigate();
  const identity = useIdentity();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const agent = data.agents.find((e) => e.id === id);
  const target = returnPath(params, "/agents");
  const listTarget = target.split("?")[0] === "/agents" ? target : "/agents";
  if (id && !agent && identity.permissions.includes("agents:read"))
    return (
      <FailureState
        failure={{ source: "http", status: 404, code: "agent_not_found", message: "员工不存在。" }}
        context={{ operation: "initial-read", resource: "agent" }}
        actions={[{ label: "返回员工目录", kind: "return", href: "/agents" }]}
      />
    );
  if (!identity.permissions.includes("agents:read")) {
    const e = data.publicAgents.find((item) => item.id === id);
    if (!e) return <PageContainer>当前账号仅可浏览已有员工。</PageContainer>;
    return (
      <PageContainer>
        <PageHeading title={e.name} description={e.description} />
        <div className={"max-w-sm"}>
          <AgentCard readOnly agent={presentPublicAgent(e)} />
        </div>
        {identity.permissions.includes("runs:create") && (
          <div className="my-4 flex flex-wrap gap-3">
            <Button
              render={<Link to={`/conversations/new?agent=${e.id}&resume=1`} />}
              nativeButton={false}
            >
              与员工对话
            </Button>
            <Button
              variant="outline"
              render={<Link to={`/agents/${e.id}/connections`} />}
              nativeButton={false}
            >
              我的工具连接
            </Button>
            <EmployeeKnowledge agentId={e.id} agentName={e.name} />
          </div>
        )}
        <h2 className={"my-4 font-semibold"}>示例任务</h2>
        <ul>
          {e.example_tasks.map((task) => (
            <li key={task}>{task}</li>
          ))}
        </ul>
        <h2 className={"my-4 font-semibold"}>预期交付</h2>
        <p>{e.deliverables.join("、") || "尚未设置"}</p>
        <h2 className={"my-4 font-semibold"}>已装配技能</h2>
        {e.skill_ids.map((key) => (
          <Button
            variant="outline"
            key={key}
            render={<Link to={`/skills?skill=${key}`} />}
            nativeButton={false}
          >
            {data.skills.find((s) => s.id === key)?.name || "技能"}
          </Button>
        ))}
      </PageContainer>
    );
  }
  if (agent && agent.createdByUserId && agent.createdByUserId !== identity.actor.user?.id)
    return (
      <PageContainer as="main" className="space-y-6">
        <PageHeading title={agent.name} description={agent.description} />
        <p className="type-description">员工配置由创建者维护，你可以直接使用并绑定自己的账号。</p>
        <Button
          render={<Link to={`/conversations/new?agent=${agent.id}&resume=1`} />}
          nativeButton={false}
        >
          与员工对话
        </Button>
        <Button
          variant="outline"
          render={<Link to={`/agents/${agent.id}/connections`} />}
          nativeButton={false}
        >
          我的工具连接
        </Button>
        <EmployeeKnowledge agentId={agent.id} agentName={agent.name} />
      </PageContainer>
    );
  const tab: ConfigurationTab = ["identity", "instructions", "capabilities"].includes(rawTab)
    ? (rawTab as ConfigurationTab)
    : "identity";
  return (
    <>
      <AgentConfiguration
        key={id || "new"}
        skillTotal={data.skillTotal}
        value={agent ?? "new"}
        skills={data.skills}
        saving={data.saving}
        initialTab={tab}
        onTabChange={setTab}
        onClose={() => navigate(target)}
        onSave={(value) => data.saveAgent(value, !id)}
        onSaved={() => navigate(listTarget, { replace: true, state: { agentSaved: true } })}
        onDelete={
          agent
            ? () => {
                data.clearMutationError();
                setDeleteOpen(true);
              }
            : undefined
        }
      />
      {agent && deleteOpen && (
        <AgentDeletionDialog
          key={agent.id}
          agentName={agent.name}
          saving={data.saving}
          error={data.mutationError}
          failure={data.mutationFailure}
          onClose={() => {
            data.clearMutationError();
            setDeleteOpen(false);
          }}
          onConfirm={() => {
            void data.deleteAgent(agent.id).then((ok) => {
              if (ok) {
                clearDraft(draftKey(identityKey(identity), `agent:${agent.id}`));
                navigate("/agents");
              }
            });
          }}
        />
      )}
    </>
  );
}
export { AgentsPage as Component };
