import { useEffect, useState, type ReactNode } from "react";
import { Link, useLocation, useParams } from "react-router";
import { Construction, Settings2 } from "lucide-react";
import { useIdentity } from "@/state/auth/useIdentity";
import { identityKey } from "@/lib/identity";
import { request } from "@/lib/api/http";
import { type PublicAgent } from "@/lib/api/agents";
import { getConversationStats } from "@/lib/api/conversations";
import { sourceLink } from "@/lib/navigation";
import { useFailureState } from "@/state/shared/useFailureState";
import { useQueryState } from "@/hooks/useQueryState";
import { AgentAvatar } from "@/components/avatars";
import { PageContainer } from "@/components/common/PageContainer";
import { PageTabs } from "@/components/common/PageTabs";
import { TabsContent } from "@/components/ui/Tabs";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/common/EmptyState";
import { FailureNotice } from "@/components/failure/FailureNotice";
import { ConversationHistory } from "@/components/conversations/ConversationHistory";
import { PageToolbar } from "@/components/common/PageToolbar";
import { PageBreadcrumb } from "@/components/common/PageBreadcrumb";
import { EmployeeEvaluations } from "./EmployeeEvaluations";
import { ResourceIcon, type ResourceKind } from "@/components/common/ResourceIcon";
import { useWorkspaceData } from "@/state/workspace/useWorkspaceData";
import { useResource } from "@/state/shared/useResource";
import { cn } from "@/lib/utils";

const sections = [
  { value: "conversations", label: "对话记录" },
  { value: "evaluations", label: "员工考核" },
  { value: "tasks", label: "任务记录" },
  { value: "schedules", label: "定时任务" },
  { value: "memory", label: "长期记忆" },
];

export function EmployeeHomePage() {
  const { id = "" } = useParams();
  const identity = useIdentity();
  return <EmployeeHome key={`${identityKey(identity)}:${id}`} id={id} />;
}

function EmployeeHome({ id }: { id: string }) {
  const identity = useIdentity();
  const location = useLocation();
  const [section, setSection] = useQueryState("section", "conversations");
  const [agent, setAgent] = useState<PublicAgent | null>(null);
  const [revision, setRevision] = useState(0);
  const { failure, setError } = useFailureState();
  const selected = sections.some((item) => item.value === section) ? section : "conversations";
  const readable = identity.permissions.includes("runs:read");
  useEffect(() => {
    const controller = new AbortController();
    void request<PublicAgent>(`public/agents/${id}`, { signal: controller.signal })
      .then((value) => {
        if (!controller.signal.aborted) {
          setAgent(value);
          setError("");
        }
      })
      .catch((error) => {
        if (!controller.signal.aborted) setError(error);
      });
    return () => controller.abort();
  }, [id, revision, setError]);
  return (
    <PageContainer className="space-y-4 py-4">
      <PageToolbar
        title={
          <PageBreadcrumb
            parent={{ label: "数字员工", to: "/agents" }}
            current={agent?.name || "员工管理"}
          />
        }
        actions={null}
      />
      <FailureNotice
        failure={failure}
        context={{ operation: "initial-read", resource: "agent" }}
        actions={[{ label: "重新加载", kind: "retry", onClick: () => setRevision((n) => n + 1) }]}
      />
      {!agent ? (
        !failure && <p role="status">正在读取员工…</p>
      ) : (
        <>
          <header className="grid min-w-0 grid-cols-[auto_minmax(0,1fr)_auto] items-start gap-x-6 gap-y-3 py-4 max-sm:gap-x-4">
            <div className="row-span-3 flex h-27 w-24 shrink-0 self-center items-end justify-center rounded-[48px_48px_var(--os-radius-card)_var(--os-radius-card)] bg-avatar-bg max-sm:row-span-1 max-sm:h-22 max-sm:w-18">
              <div className="size-28 shrink-0 max-sm:size-22">
                <AgentAvatar avatarId={agent.avatar_id} size="100%" alt="" />
              </div>
            </div>
            <div className="col-start-2 row-start-1 min-w-0 self-center">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                <h1 className="text-[length:var(--os-text-display)] font-semibold leading-snug tracking-tight [overflow-wrap:anywhere] max-sm:text-[length:var(--os-text-page)]">
                  {agent.name}
                </h1>
                <span
                  className={`inline-flex items-center gap-1.5 whitespace-nowrap text-xs ${agent.is_active ? "text-success" : "text-text-muted"}`}
                >
                  <span className="size-1.5 rounded-full bg-current" aria-hidden="true" />
                  {agent.is_active ? "在岗" : "已暂停接单"}
                </span>
              </div>
            </div>
            <p className="col-start-2 row-start-2 min-w-0 max-w-prose text-sm leading-relaxed text-text-muted [overflow-wrap:anywhere] max-sm:col-span-3 max-sm:col-start-1">
              {agent.description || agent.role_label || "暂无职责简介"}
            </p>
            <EmployeeStats agent={agent} />
            {identity.permissions.includes("agents:read") && (
              <Button
                variant="outline"
                size="icon"
                className="col-start-3 row-start-1 self-start justify-self-end"
                aria-label="编辑员工配置"
                render={<Link to={sourceLink(`/agents/${id}`)} />}
                nativeButton={false}
              >
                <Settings2 />
              </Button>
            )}
          </header>
          <PageTabs
            label="员工栏目"
            value={selected}
            onValueChange={(value) => setSection(value)}
            items={sections}
          >
            <TabsContent value="conversations">
              {readable ? (
                <>
                  <h2 className="sr-only">与{agent.name}的历史交流</h2>
                  <ConversationHistory
                    agentId={id}
                    returnTo={location.pathname + location.search}
                  />
                </>
              ) : (
                <EmptyState
                  text="登录后查看自己的对话记录"
                  description="员工配置由多人共享，对话按用户权限展示。"
                />
              )}
            </TabsContent>
            <TabsContent value="evaluations">
              {readable ? (
                <EmployeeEvaluations
                  agentId={id}
                  ready={agent.is_active && agent.model_configured}
                />
              ) : (
                <EmptyState text="登录后使用员工考核" />
              )}
            </TabsContent>
            {sections.slice(2).map((item) => (
              <TabsContent value={item.value} key={item.value}>
                <EmptyState
                  text={`${item.label}建设中`}
                  description="功能尚未开放。"
                  icon={<Construction size={26} aria-hidden="true" />}
                />
              </TabsContent>
            ))}
          </PageTabs>
        </>
      )}
    </PageContainer>
  );
}

function Metric({
  label,
  kind,
  description,
  children,
  to,
}: {
  label: string;
  kind: ResourceKind;
  description: string;
  children: ReactNode;
  to?: string;
}) {
  return (
    <div
      className={cn(
        "group/metric relative inline-flex min-h-9 min-w-0 max-w-full items-center gap-1.5 rounded-control bg-muted px-3 py-1.5",
        to &&
          "transition-colors duration-fast hover:bg-hover [@media(pointer:_coarse)]:min-h-(--os-target-touch)",
      )}
      role="group"
      aria-label={label}
      title={description}
    >
      <dt
        className={cn(
          "order-2 shrink-0 text-xs text-text-muted",
          to &&
            "underline-offset-4 transition-colors duration-fast group-hover/metric:text-brand group-hover/metric:underline group-has-[a:focus-visible]/metric:text-brand group-has-[a:focus-visible]/metric:underline",
        )}
      >
        {label}
      </dt>
      <dd className="order-1 flex min-w-0 items-center gap-1.5" aria-live="polite">
        <ResourceIcon kind={kind} size={14} className="text-brand" />
        {children}
      </dd>
      {/* 链接覆盖整项，数量读取失败的重试按钮保留独立点击层级。 */}
      {to && (
        <Link to={to} aria-label={`配置${label}`} className="absolute inset-0 rounded-control" />
      )}
    </div>
  );
}

function Count({ value, unit }: { value: number; unit: string }) {
  const exact = new Intl.NumberFormat("zh-CN").format(value);
  const display =
    value < 10_000
      ? exact
      : new Intl.NumberFormat("zh-CN", {
          notation: "compact",
          maximumFractionDigits: 1,
        }).format(value);
  return (
    <data
      value={value}
      title={`${exact} ${unit}`}
      className="min-w-0 text-section font-medium leading-tight tabular-nums [overflow-wrap:anywhere]"
    >
      {display}
    </data>
  );
}

function KnowledgeCount({ agentId }: { agentId: string }) {
  const resource = useWorkspaceData().knowledge.employeeBindings(agentId);
  const state = useResource(resource);
  if (state.failure)
    return (
      <button
        type="button"
        className="relative z-10 text-left text-xs text-danger underline underline-offset-4"
        aria-label="重新读取知识库数量"
        title={state.failure.message}
        onClick={() => resource.refresh()}
      >
        读取失败，重试
      </button>
    );
  if (!state.data) return <span aria-label="正在读取知识库数量">…</span>;
  return <Count value={state.data.knowledge_base_ids.length} unit="知识库" />;
}

function CompletedRounds({ agentId }: { agentId: string }) {
  const [count, setCount] = useState<number | null>(null);
  const [revision, setRevision] = useState(0);
  const { failure, setError } = useFailureState();
  useEffect(() => {
    const controller = new AbortController();
    void getConversationStats(agentId, controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) setCount(value.completed_rounds);
      })
      .catch((error) => {
        if (!controller.signal.aborted) setError(error);
      });
    return () => controller.abort();
  }, [agentId, revision, setError]);
  if (failure)
    return (
      <button
        type="button"
        className="text-left text-xs text-danger underline underline-offset-4"
        aria-label="重新读取完成对话轮数"
        title={failure.message}
        onClick={() => {
          setError("");
          setRevision((value) => value + 1);
        }}
      >
        读取失败，重试
      </button>
    );
  if (count === null) return <span aria-label="正在读取完成对话轮数">…</span>;
  return <Count value={count} unit="轮对话" />;
}

function EmployeeStats({ agent }: { agent: PublicAgent }) {
  const identity = useIdentity();
  const location = useLocation();
  const configurationReadable = identity.permissions.includes("agents:read");
  function editLink(tab: string) {
    const query = new URLSearchParams({ tab, from: location.pathname + location.search });
    return `/agents/${agent.id}?${query}`;
  }
  const unavailable = identity.actor.kind === "guest" ? "登录后查看" : "暂无查看权限";
  const knowledgeReadable =
    identity.permissions.includes("knowledge:use") && identity.permissions.includes("runs:create");
  const conversationsReadable =
    identity.permissions.includes("conversations:read") &&
    identity.permissions.includes("runs:read");
  return (
    <dl
      className="col-span-2 col-start-2 row-start-3 flex min-w-0 flex-wrap gap-2 max-sm:col-span-3 max-sm:col-start-1"
      aria-label="员工能力与交流统计"
    >
      <Metric
        label="技能"
        kind="skill"
        description="这位员工当前启用的技能数量"
        to={configurationReadable ? editLink("capabilities") : undefined}
      >
        <Count value={agent.resource_counts.skills} unit="技能" />
      </Metric>
      <Metric
        label="知识库"
        kind="knowledge"
        description="当前账号为这位员工装配的知识库数量"
        to={configurationReadable && knowledgeReadable ? editLink("instructions") : undefined}
      >
        {knowledgeReadable ? (
          <KnowledgeCount agentId={agent.id} />
        ) : (
          <span className="self-center text-xs text-text-muted">{unavailable}</span>
        )}
      </Metric>
      <Metric
        label="轮对话"
        kind="conversation"
        description="当前可见对话中已成功完成的问答轮数，同一问题重试不重复计数"
      >
        {conversationsReadable ? (
          <CompletedRounds agentId={agent.id} />
        ) : (
          <span className="self-center text-xs text-text-muted">{unavailable}</span>
        )}
      </Metric>
    </dl>
  );
}
