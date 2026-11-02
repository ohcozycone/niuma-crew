import { useState } from "react";
import { Link } from "react-router";
import { Plus, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/Dialog";
import { SearchInput } from "@/components/common/SearchInput";
import { ResourceIcon, ResourceType } from "@/components/common/ResourceIcon";
import { useToolAssembly } from "@/components/tools/ToolAssembly";
import { cn } from "@/lib/utils";
import { useSkillAssembly } from "./AgentSkillAssembly";

type Filter = "all" | "tool" | "skill";
const filters: { value: Filter; label: string }[] = [
  { value: "all", label: "全部" },
  { value: "tool", label: "工具" },
  { value: "skill", label: "技能" },
];
const pageSize = 6;

function matches(kind: string, filter: Filter) {
  return filter === "all" || (filter === "skill" ? kind === "skill" : kind !== "skill");
}

function TypeFilters({
  value,
  onChange,
  counts,
  label,
}: {
  value: Filter;
  onChange: (value: Filter) => void;
  counts?: Record<Filter, number>;
  label: string;
}) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap gap-1">
      {filters.map((item) => (
        <Button
          key={item.value}
          type="button"
          size="sm"
          variant="ghost"
          aria-pressed={value === item.value}
          className={cn(value === item.value && "bg-selected text-text")}
          onClick={() => onChange(item.value)}
        >
          {item.label}
          {counts && <span className="type-caption">{counts[item.value]}</span>}
        </Button>
      ))}
    </div>
  );
}

export function AgentCapabilityAssembly({
  tools: toolProps,
  skills: skillProps,
  personalConnectionsHref,
}: {
  tools: Parameters<typeof useToolAssembly>[0];
  skills: Parameters<typeof useSkillAssembly>[0];
  personalConnectionsHref?: string;
}) {
  const tools = useToolAssembly(toolProps);
  const skills = useSkillAssembly(skillProps);
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [adding, setAdding] = useState(false);
  const [candidateFilter, setCandidateFilter] = useState<Filter>("all");
  const [candidateQuery, setCandidateQuery] = useState("");
  const all = [...tools.items, ...skills.items].sort((a, b) =>
    a.name.localeCompare(b.name, "zh-CN"),
  );
  const rows = all.filter(
    (item) =>
      matches(item.kind, filter) &&
      `${item.name} ${item.summary}`.toLocaleLowerCase().includes(query.toLocaleLowerCase()),
  );
  const page = Math.min(offset, Math.max(0, Math.ceil(rows.length / pageSize) - 1));
  const visible = rows.slice(page * pageSize, (page + 1) * pageSize);
  const counts = { all: all.length, tool: tools.items.length, skill: skills.items.length };
  const candidates = [...tools.candidateItems, ...skills.candidateItems]
    .filter((item) => matches(item.kind, candidateFilter))
    .sort((a, b) => a.name.localeCompare(b.name, "zh-CN"));

  function choose(open: boolean) {
    setAdding(open);
    skills.setChoosing(open);
  }
  return (
    <section aria-label="员工能力装配" className="min-w-0">
      <div className="sticky top-0 z-10 space-y-4 bg-canvas pb-4 pt-1">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="type-section">
              已装配能力 <span className="type-caption">{all.length} 项</span>
            </h2>
            <p className="type-description mt-1">统一管理工具与技能，按工作需要装配。</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {personalConnectionsHref && (
              <Button
                type="button"
                size="sm"
                variant="ghost"
                render={<Link to={personalConnectionsHref} />}
                nativeButton={false}
              >
                <ResourceIcon kind="connection" />
                我的工具连接
              </Button>
            )}
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={tools.loading}
              onClick={tools.refresh}
            >
              <RefreshCw />
              刷新连接列表
            </Button>
            <Button type="button" size="sm" variant="outline" onClick={() => choose(true)}>
              <Plus />
              添加能力
            </Button>
          </div>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <TypeFilters
            label="筛选已装配能力"
            value={filter}
            counts={counts}
            onChange={(next) => {
              setFilter(next);
              setOffset(0);
            }}
          />
          <SearchInput
            label="搜索已装配能力"
            value={query}
            placeholder="搜索名称或用途…"
            onChange={(next) => {
              setQuery(next);
              setOffset(0);
            }}
            className="w-full sm:w-64"
          />
        </div>
      </div>
      {tools.feedback}
      {visible.map((item) => (
        <div key={item.key}>{item.element}</div>
      ))}
      {!visible.length && (
        <Card as="p" variant="empty" className="p-6 text-sm text-text-muted">
          {all.length
            ? "没有匹配的能力，可调整搜索或类型筛选。"
            : "尚未装配能力，可从“添加能力”选择工具或技能。"}
        </Card>
      )}
      {rows.length > pageSize && (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <span className="type-caption">
            {page * pageSize + 1}–{Math.min(rows.length, (page + 1) * pageSize)} / {rows.length} 项
          </span>
          <div className="flex gap-2">
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={page === 0}
              onClick={() => setOffset(page - 1)}
            >
              上一页
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={(page + 1) * pageSize >= rows.length}
              onClick={() => setOffset(page + 1)}
            >
              下一页
            </Button>
          </div>
        </div>
      )}
      <p className="type-caption mt-5">
        启停、移除和面板修改均先更新当前员工草稿，点击“保存配置”后生效。
      </p>
      {tools.panels}
      {skills.panels}
      <Dialog open={adding} onOpenChange={choose}>
        <DialogContent size="wide">
          <DialogHeader>
            <DialogTitle>添加能力</DialogTitle>
            <DialogDescription>选择已有技能或工具连接，加入当前员工草稿。</DialogDescription>
          </DialogHeader>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <TypeFilters
              label="候选能力类型"
              value={candidateFilter}
              onChange={setCandidateFilter}
            />
            <SearchInput
              label="搜索候选能力"
              debounceMs={300}
              value={candidateQuery}
              placeholder="搜索名称或用途…"
              className="w-full sm:w-64"
              onChange={(next) => {
                setCandidateQuery(next);
                tools.setQuery(next);
                skills.setQuery(next);
              }}
            />
          </div>
          {tools.loading && candidateFilter !== "skill" && (
            <p role="status" className="type-caption">
              正在读取工具连接…
            </p>
          )}
          {skills.optionsLoading && candidateFilter !== "tool" && (
            <p role="status" className="type-caption">
              正在搜索技能…
            </p>
          )}
          {tools.feedback}
          {skills.candidateFeedback}
          <div className="focus-gutter max-h-[46dvh] space-y-2 overflow-y-auto overscroll-contain">
            {candidates.map((item) => (
              <button
                key={item.key}
                type="button"
                disabled={item.disabled}
                className="flex w-full items-center gap-3 rounded-control border border-border p-3 text-left hover:bg-muted disabled:opacity-50"
                onClick={() => {
                  choose(false);
                  item.select();
                  setFilter("all");
                  setQuery("");
                  setOffset(0);
                }}
              >
                <ResourceIcon kind={item.kind} size={20} className="text-text-muted" />
                <span className="min-w-0 flex-1">
                  <strong className="block break-words text-sm">{item.name}</strong>
                  <span className="type-caption line-clamp-2">{item.summary}</span>
                </span>
                <ResourceType kind={item.kind} showIcon={false} />
                <Plus size={16} aria-hidden="true" />
              </button>
            ))}
            {!candidates.length && !tools.loading && !skills.optionsLoading && (
              <p className="type-description py-4">没有其他匹配的可装配能力。</p>
            )}
          </div>
          {candidateFilter !== "tool" && (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <span className="type-caption">
                技能候选共 {skills.total} 项 · 工具按可管理连接显示
              </span>
              <div className="flex gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={!skills.offset || skills.optionsLoading}
                  onClick={() => skills.changeOffset(Math.max(0, skills.offset - 20))}
                >
                  上一批技能
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={skills.offset + 20 >= skills.total || skills.optionsLoading}
                  onClick={() => skills.changeOffset(skills.offset + 20)}
                >
                  下一批技能
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </section>
  );
}
