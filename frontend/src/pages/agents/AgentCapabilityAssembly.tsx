import { useState } from "react";
import { Link } from "react-router";
import { Plus, RefreshCw, Check, ArrowUpRight } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
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
          onClick={() => onChange(item.value)}
        >
          {item.label}
          {counts && <span className="text-xs tabular-nums opacity-75">{counts[item.value]}</span>}
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
  const [addedName, setAddedName] = useState("");
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
    if (open) setAddedName("");
  }
  return (
    <section aria-label="员工能力装配" className="min-w-0">
      <div className="space-y-5 pb-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="type-section">
              已装配能力 <span className="type-caption">{all.length} 项</span>
            </h2>
            <p className="type-description mt-1">为员工选择工作方法与工具操作，保存配置后生效。</p>
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
            <Button type="button" size="sm" onClick={() => choose(true)}>
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
      {visible.length > 0 && (
        <div className="divide-y divide-border rounded-panel border border-border bg-raised">
          {visible.map((item) => (
            <div key={item.key}>{item.element}</div>
          ))}
        </div>
      )}
      {!visible.length && (
        <Card
          variant="empty"
          radius="panel"
          className="flex flex-col items-center gap-3 px-5 py-12 text-center"
        >
          <ResourceIcon
            kind={filter === "skill" ? "skill" : "tool"}
            size={28}
            className="text-text-muted"
          />
          <h3 className="type-title">
            {all.length ? "没有匹配的已装配能力" : "为员工添加第一项能力"}
          </h3>
          <p className="max-w-sm text-sm leading-6 text-text-muted">
            {all.length
              ? "调整关键词或切换类型，已有装配不会丢失。"
              : "技能提供工作方法，工具提供可执行的操作。按岗位需要添加即可。"}
          </p>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => {
              if (all.length) {
                setQuery("");
                setFilter("all");
              } else choose(true);
            }}
          >
            {all.length ? "清除筛选" : "选择能力"}
          </Button>
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
        <DialogContent layout="side">
          <DialogHeader>
            <DialogTitle>添加能力</DialogTitle>
            <DialogDescription>
              技能可连续添加；工具需先选择允许执行的操作。完成后在员工页统一保存。
            </DialogDescription>
          </DialogHeader>
          <div className="focus-gutter min-h-0 space-y-4 overflow-y-auto overscroll-contain">
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
                className="w-full"
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
            {addedName && (
              <p
                role="status"
                className="flex items-start gap-2 rounded-control bg-success-bg p-3 text-xs leading-5 text-success"
              >
                <Check size={15} className="mt-0.5 shrink-0" />
                已将「{addedName}」加入员工草稿，可继续选择。
              </p>
            )}
            <div className="space-y-2">
              {candidates.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  disabled={item.disabled}
                  className={cn(
                    "flex w-full items-center gap-3 rounded-panel border border-border bg-raised p-4 text-left hover:bg-muted disabled:cursor-default",
                    item.selected ? "border-success/40 bg-success-bg" : "disabled:opacity-50",
                  )}
                  onClick={() => {
                    if (item.kind !== "skill") choose(false);
                    item.select();
                    if (item.kind === "skill") setAddedName(item.name);
                    setFilter("all");
                    setQuery("");
                    setOffset(0);
                  }}
                >
                  <ResourceIcon kind={item.kind} size={20} className="text-text-muted" />
                  <span className="min-w-0 flex-1">
                    <strong className="block break-words text-sm">{item.name}</strong>
                    <span className="type-caption line-clamp-2">{item.summary}</span>
                    {item.disabledReason && (
                      <span className="mt-1 block text-xs text-warning">{item.disabledReason}</span>
                    )}
                  </span>
                  <span className="flex shrink-0 flex-col items-end gap-2">
                    <ResourceType kind={item.kind} showIcon={false} />
                    {item.selected ? (
                      <span className="inline-flex items-center gap-1 text-xs text-success">
                        <Check size={14} />
                        已装配
                      </span>
                    ) : (
                      <Plus size={16} aria-hidden="true" />
                    )}
                  </span>
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
          </div>
          <DialogFooter className="items-center justify-between border-t border-border pt-4">
            <Button
              type="button"
              size="sm"
              variant="ghost"
              render={<Link to="/skills" target="_blank" rel="noopener noreferrer" />}
              nativeButton={false}
            >
              管理能力库
              <ArrowUpRight size={14} />
              <span className="sr-only">（新标签页）</span>
            </Button>
            <Button type="button" onClick={() => choose(false)}>
              完成选择
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
