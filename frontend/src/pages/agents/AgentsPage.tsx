import { FailureState } from "@/components/failure/FailureState";
import { PageContainer } from "@/components/common/PageContainer";
import { AgentDirectoryPagination } from "./AgentDirectoryPagination";
import { useCallback, useState } from "react";
import { Navigate, Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router";
import { useIdentity } from "@/state/auth/useIdentity";
import { identityKey } from "@/lib/identity";
import { Button } from "@/components/ui/Button";

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
    <ResourceStatus data={data} resource="agent" shape="employees">
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
      onRefresh={data.reload}
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
      canEdit={() => identity.permissions.includes("agents:update")}
      onCreate={
        identity.permissions.includes("agents:create")
          ? () => navigate(sourceLink("/agents/new"))
          : undefined
      }
      onAction={action}
    />
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
  if (!id && !identity.permissions.includes("agents:create"))
    return <Navigate replace to="/agents" />;
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
        readOnly={!identity.permissions.includes("agents:update")}
        initialTab={tab}
        onTabChange={setTab}
        onClose={() => navigate(target)}
        onSave={(value) => data.saveAgent(value, !id)}
        onSaved={() => navigate(listTarget, { replace: true, state: { agentSaved: true } })}
        onDelete={
          agent && identity.permissions.includes("agents:delete")
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
