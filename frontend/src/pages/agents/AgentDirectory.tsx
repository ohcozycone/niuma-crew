import type { ReactNode } from "react";
import { PageContainer } from "@/components/common/PageContainer";
import { Plus, SlidersHorizontal, X } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { PageHeading } from "@/components/common/PageHeading";
import { SearchInput } from "@/components/common/SearchInput";
import { EmptyState } from "@/components/common/EmptyState";
import { SelectField } from "@/components/ui/SelectField";
import { PageTabs } from "@/components/common/PageTabs";
import { type AgentSummary } from "@/lib/models/agent";
import { type AgentAction } from "./types";
import { AgentCard } from "./AgentCard";
import { useAgentState } from "@/state/agents/useAgentData";
import { useWorkspaceData } from "@/state/workspace/useWorkspaceData";
import { toAgentPresentation } from "./agentPresentation";
type Props = {
  ids: string[];
  pagination?: ReactNode;
  categories: string[];
  availableCount: number;
  totalAgents?: number | null;
  matchedTotal?: number;
  loading?: boolean;
  loadError?: string;
  saveMessage?: string;
  query: string;
  setQuery: (value: string) => void;
  filter: string;
  setFilter: (value: string) => void;
  category: string;
  setCategory: (value: string) => void;
  agentSkillId: string | null;
  setAgentSkillId: (value: string | null) => void;
  canEdit?: (agent: AgentSummary) => boolean;
  onCreate: () => void;
  onAction: (agent: AgentSummary, action: AgentAction) => void;
};
export function AgentDirectory({
  ids,
  pagination,
  categories: pageCategories,
  availableCount,
  totalAgents,
  matchedTotal,
  loading = false,
  loadError = "",
  saveMessage = "",
  query,
  setQuery,
  filter,
  setFilter,
  category,
  setCategory,
  agentSkillId,
  setAgentSkillId,
  onCreate,
  canEdit,
  onAction,
}: Props) {
  const categories = [
    ...new Set([
      "财务行政",
      "知识管理",
      "内容创作",
      "研究分析",
      "客户服务",
      "研发协作",
      "其他",
      ...(category === "all" ? [] : [category]),
      ...pageCategories,
    ]),
  ].filter(Boolean);
  const resultTotal = matchedTotal ?? ids.length;
  return (
    <PageContainer>
      <PageHeading
        title="数字员工"
        description={agentSkillId ? "已装配所选技能的员工。" : "为合适的员工配齐能力，交办工作。"}
        actions={
          <Button onClick={onCreate}>
            <Plus />
            创建员工
          </Button>
        }
      />
      {saveMessage && (
        <p role="status" className="type-caption mb-4 text-success">
          {saveMessage}
        </p>
      )}
      <PageTabs
        value={filter}
        onValueChange={setFilter}
        label="员工状态筛选"
        items={[
          { value: "all", label: "全部员工", count: totalAgents ?? "—" },
          { value: "favorites", label: "已收藏" },
          { value: "active", label: "可对话" },
          { value: "paused", label: "已暂停" },
        ]}
        trailing={
          <span role="status" aria-atomic="true" aria-busy={loading && !loadError}>
            {`共 ${resultTotal} 位员工 · 本页 ${availableCount} 位可对话`}
            {loadError && " · 更新失败，仍显示上次结果"}
            {loading && !loadError && " · 正在更新…"}
          </span>
        }
      />
      <div className="my-4 flex flex-wrap items-center gap-3" role="group" aria-label="员工筛选">
        <SearchInput
          label="筛选员工"
          debounceMs={300}
          placeholder="筛选员工：名称、职责或技能"
          className="max-sm:w-full"
          value={query}
          onChange={setQuery}
        />
        <div className="flex flex-wrap items-center gap-2.5">
          <SelectField
            options={[
              { value: "all", label: "全部岗位" },
              ...categories.map((value) => ({ value, label: value })),
            ]}
            value={category}
            onValueChange={setCategory}
            icon={<SlidersHorizontal size={14} />}
            aria-label="按岗位分类"
            className="w-fit text-text-muted"
          />
          {agentSkillId && (
            <Button variant="ghost" onClick={() => setAgentSkillId(null)}>
              清除技能筛选
              <X size={14} />
            </Button>
          )}
        </div>
        {pagination}
      </div>
      <div aria-label="员工列表" aria-busy={loading && !loadError}>
        <div>
          <div className={"employee-grid"}>
            {ids.map((id) => (
              <DirectoryCard key={id} id={id} canEdit={canEdit} onAction={onAction} />
            ))}
          </div>
          {!ids.length && !loading && (
            <EmptyState
              onReset={() => {
                setQuery("");
                setFilter("all");
                setCategory("all");
                setAgentSkillId(null);
              }}
              text={
                totalAgents === 0
                  ? "还没有员工，点击「创建员工」开始配置"
                  : "没有找到符合条件的员工"
              }
            />
          )}
          {!ids.length && loading && (
            <p role="status" className="type-caption py-12">
              正在读取员工…
            </p>
          )}
        </div>
      </div>
    </PageContainer>
  );
}

function DirectoryCard({
  id,
  canEdit,
  onAction,
}: Pick<Props, "canEdit" | "onAction"> & { id: string }) {
  const state = useAgentState(id);
  const data = useWorkspaceData();
  const agent = state.agent;
  if (!agent) return null;
  return (
    <AgentCard
      agent={toAgentPresentation(agent)}
      readOnly={canEdit ? !canEdit(agent) : false}
      usable
      statusPending={state.saving}
      statusError={state.error}
      statusFailure={state.failure}
      statusRetry={
        state.retryable
          ? () => {
              void data.agents.retryStatus(id);
            }
          : undefined
      }
      onAction={(_id, action) => onAction(agent, action)}
    />
  );
}
