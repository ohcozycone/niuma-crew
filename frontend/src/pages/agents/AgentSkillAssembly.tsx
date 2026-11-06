import { useFailureState } from "@/state/shared/useFailureState";
import { FailureNotice } from "@/components/failure/FailureNotice";
import { toFailure, clientFailure } from "@/lib/failures/resolve";
import type { Failure } from "@/lib/failures/types";
import { FormField } from "@/components/common/FormField";
import { AssemblyItem } from "@/components/configuration/AssemblyItem";
import { SearchInput } from "@/components/common/SearchInput";
import { Card } from "@/components/ui/Card";
import { useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { ResourceIcon } from "@/components/common/ResourceIcon";
import type { AssemblyEntry, AssemblyCandidate } from "@/components/configuration/assemblyEntry";
import { Button } from "@/components/ui/Button";

import { Textarea } from "@/components/ui/Textarea";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/Dialog";
import { getSkill, skillPage, fromSkillSummary } from "@/lib/api/skills";
import type { Skill, SkillListItem } from "@/lib/models/skill";
type Settings = Record<string, { enabled: boolean; parameters: string }>;
export function useSkillAssembly({
  ids,
  skills,
  settings,
  onChange,
  onSelectionChange,
}: {
  ids: string[];
  skills: SkillListItem[];
  settings: Settings;
  onChange: (settings: Settings) => void;
  onSelectionChange: (ids: string[]) => void;
}) {
  const [details, setDetails] = useState<Record<string, Skill>>({});
  const [failures, setFailures] = useState<Record<string, Failure | null>>({});
  const [revision, setRevision] = useState(0);
  const [chooser, setChooser] = useState(false);
  const [query, setQuery] = useState("");
  const [options, setOptions] = useState<SkillListItem[]>(skills);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [optionsLoading, setOptionsLoading] = useState(false);
  const [optionsRevision, setOptionsRevision] = useState(0);
  const { failure: optionsFailure, setError: setOptionsError } = useFailureState();
  const [editing, setEditing] = useState<string | null>(null);
  const [parameters, setParameters] = useState("{}");
  const { failure, setError } = useFailureState();
  const selectedKey = [...ids].sort().join(",");
  useEffect(() => {
    const controller = new AbortController();
    for (const id of selectedKey.split(",").filter(Boolean)) {
      void getSkill(id, controller.signal)
        .then((skill) => {
          if (!controller.signal.aborted) {
            setDetails((current) => ({ ...current, [id]: skill }));
            setFailures((current) => {
              const next = { ...current };
              delete next[id];
              return next;
            });
          }
        })
        .catch((e) => {
          if (!controller.signal.aborted)
            setFailures((current) => ({ ...current, [id]: toFailure(e) }));
        });
    }
    return () => controller.abort();
  }, [selectedKey, revision]); // Selected identities are independent of the candidate page.
  useEffect(() => {
    if (!chooser) return;
    const controller = new AbortController();
    skillPage(
      new URLSearchParams({ q: query, offset: String(offset), limit: "20" }),
      controller.signal,
    )
      .then((page) => {
        if (!controller.signal.aborted) {
          setOptions(page.items.map(fromSkillSummary));
          setTotal(page.total);
          setOptionsError("");
          setOptionsLoading(false);
        }
      })
      .catch((failure) => {
        if (!controller.signal.aborted) {
          setOptionsError(failure);
          setOptionsLoading(false);
        }
      });
    return () => controller.abort();
  }, [chooser, query, offset, optionsRevision, setOptionsError]);
  function configure(id: string) {
    setEditing(id);
    setParameters(settings[id]?.parameters ?? "{}");
    setError("");
  }
  const current = editing ? details[editing] : null;
  const schema = current?.configurationSchema ?? {};
  const hasParameters = Object.keys(schema).length > 0;
  function openChooser() {
    setOptionsLoading(true);
    setChooser(true);
  }
  const items: AssemblyEntry[] = ids.map((id) => {
    const skill = details[id] ?? skills.find((item) => item.id === id);
    const value = settings[id] ?? { enabled: true, parameters: "{}" };
    return {
      key: `skill:${id}`,
      kind: "skill",
      name: skill?.name ?? "正在读取已装配技能…",
      summary: skill?.description ?? "可复用工作方法",
      element: (
        <AssemblyItem
          key={id}
          name={skill?.name ?? "正在读取已装配技能…"}
          icon={<ResourceIcon kind="skill" size={18} className="text-text-muted" />}
          kind="skill"
          enabled={value.enabled}
          onEnabledChange={(enabled) => onChange({ ...settings, [id]: { ...value, enabled } })}
          enableLabel={`${skill?.name ?? "技能"}装配启用`}
          onConfigure={() => configure(id)}
          onRemove={() => onSelectionChange(ids.filter((item) => item !== id))}
          removeLabel={`移除${skill?.name ?? "技能"}`}
        >
          <p className="type-caption line-clamp-1">{skill?.description || "可复用工作指引"}</p>
          {failures[id] && (
            <FailureNotice
              compact
              failure={failures[id]}
              context={{ operation: "initial-read", resource: "skill" }}
              actions={[
                { label: "重读技能", kind: "retry", onClick: () => setRevision((n) => n + 1) },
              ]}
            />
          )}
        </AssemblyItem>
      ),
    };
  });
  const candidateItems: AssemblyCandidate[] = options.map((skill) => ({
    key: `skill:${skill.id}`,
    kind: "skill",
    name: skill.name,
    summary: skill.description,
    disabled: optionsLoading || ids.includes(skill.id),
    selected: ids.includes(skill.id),
    select: () => onSelectionChange([...ids, skill.id]),
  }));
  return {
    items,
    candidateItems,
    optionsLoading,
    total,
    offset,
    setChoosing: (open: boolean) => {
      setChooser(open);
      if (open) setOptionsLoading(true);
    },
    setQuery: (next: string) => {
      setQuery(next);
      setOffset(0);
      setOptionsLoading(true);
    },
    changeOffset: (next: number) => {
      setOffset(next);
      setOptionsLoading(true);
    },
    candidateFeedback: optionsFailure ? (
      <FailureNotice
        compact
        failure={optionsFailure}
        context={{ operation: "refresh", resource: "skill", hasUsableData: !!options.length }}
        actions={[
          {
            label: "重新读取技能",
            kind: "retry",
            onClick: () => {
              setOptionsLoading(true);
              setOptionsRevision((n) => n + 1);
            },
          },
        ]}
      />
    ) : null,
    openChooser,
    chooserDialog: (
      <>
        {" "}
        <Dialog open={chooser} onOpenChange={setChooser}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>添加技能</DialogTitle>
              <DialogDescription>选择技能后加入员工草稿，保存员工配置才生效。</DialogDescription>
            </DialogHeader>
            <SearchInput
              label="搜索技能"
              debounceMs={300}
              onChange={(nextValue) => {
                setOptionsLoading(true);
                setQuery(nextValue);
                setOffset(0);
              }}
              placeholder="搜索当前可选技能…"
              value={query}
              className="w-full"
            />
            <div className="focus-gutter max-h-96 space-y-2 overflow-auto">
              {options
                .filter(
                  (skill) =>
                    !ids.includes(skill.id) &&
                    skill.name.toLowerCase().includes(query.toLowerCase()),
                )
                .map((skill) => (
                  <button
                    type="button"
                    key={skill.id}
                    disabled={optionsLoading}
                    className="flex w-full items-center justify-between gap-3 rounded-control border border-border p-3 text-left text-sm hover:bg-muted"
                    onClick={() => {
                      onSelectionChange([...ids, skill.id]);
                      setChooser(false);
                    }}
                  >
                    <span>
                      {skill.name}
                      <span className="block type-caption line-clamp-2">{skill.description}</span>
                    </span>
                    <Plus size={16} />
                  </button>
                ))}
            </div>
            {optionsLoading && <p role="status">正在搜索技能…</p>}
            {optionsFailure && (
              <FailureNotice
                compact
                failure={optionsFailure}
                context={{
                  operation: "refresh",
                  resource: "skill",
                  hasUsableData: !!options.length,
                }}
              />
            )}
            <div className="flex items-center justify-between gap-3">
              <span className="type-caption">共 {total} 项候选</span>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={!offset || optionsLoading}
                  onClick={() => {
                    setOptionsLoading(true);
                    setOffset((current) => Math.max(0, current - 20));
                  }}
                >
                  上一页
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={offset + 20 >= total || optionsLoading}
                  onClick={() => {
                    setOptionsLoading(true);
                    setOffset((current) => current + 20);
                  }}
                >
                  下一页
                </Button>
              </div>
            </div>
            <p className="type-caption">已装配详情独立读取，不随搜索和分页丢失。</p>
          </DialogContent>
        </Dialog>
      </>
    ),
    panels: (
      <>
        {" "}
        <Dialog
          open={!!editing}
          onOpenChange={(open) => {
            if (!open) setEditing(null);
          }}
        >
          <DialogContent layout="side">
            <DialogHeader>
              <DialogTitle>{current?.name ?? "技能配置"}</DialogTitle>
              <DialogDescription>
                参数规范由该能力作者声明。取消或关闭丢弃面板修改，完成后由员工页统一保存。
              </DialogDescription>
            </DialogHeader>
            <div className="focus-gutter min-h-0 space-y-4 overflow-auto">
              {editing && failures[editing] ? (
                <FailureNotice
                  compact
                  failure={failures[editing]}
                  context={{ operation: "initial-read", resource: "skill" }}
                />
              ) : !current ? (
                <p role="status">正在读取技能详情…</p>
              ) : (
                <>
                  <p className="text-sm text-text-muted">{current.description}</p>
                  {hasParameters ? (
                    <>
                      <FormField label={<>装配参数（JSON，不含密钥）</>}>
                        <Textarea
                          rows={10}
                          className="font-mono text-xs"
                          value={parameters}
                          onChange={(e) => setParameters(e.target.value)}
                        />
                      </FormField>
                      <details>
                        <summary className="cursor-pointer text-sm">查看参数规范</summary>
                        <pre className="mt-2 overflow-auto text-xs">
                          {JSON.stringify(schema, null, 2)}
                        </pre>
                      </details>
                    </>
                  ) : (
                    <p className="type-description">此技能未声明装配参数，无需填写额外字段。</p>
                  )}
                  <a
                    href={`/skills/${current.id}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm underline underline-offset-4"
                  >
                    查看完整技能（新标签页）
                  </a>
                </>
              )}
              {failure && (
                <FailureNotice
                  compact
                  failure={failure}
                  context={{ operation: "mutation", resource: "skill", outcome: "rejected" }}
                />
              )}
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setEditing(null)}>
                取消
              </Button>
              <Button
                type="button"
                disabled={!current}
                onClick={() => {
                  try {
                    const parsed: unknown = JSON.parse(hasParameters ? parameters : "{}");
                    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed))
                      throw clientFailure("invalid_skill_parameters", "参数必须为 JSON 对象。");
                    if (editing)
                      onChange({
                        ...settings,
                        [editing]: {
                          enabled: settings[editing]?.enabled ?? true,
                          parameters: JSON.stringify(parsed, null, 2),
                        },
                      });
                    setEditing(null);
                  } catch (e) {
                    setError(
                      e instanceof SyntaxError
                        ? clientFailure("invalid_skill_parameters", "参数必须为有效的 JSON 对象。")
                        : e,
                    );
                  }
                }}
              >
                完成，更新草稿
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </>
    ),
  };
}

export function AgentSkillAssembly(props: Parameters<typeof useSkillAssembly>[0]) {
  const assembly = useSkillAssembly(props);
  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="type-title">
          技能 <span className="type-caption">{props.ids.length} 项装配</span>
        </h3>
        <Button type="button" size="sm" variant="outline" onClick={assembly.openChooser}>
          <Plus />
          添加技能
        </Button>
      </div>
      {!props.ids.length && (
        <Card as="p" variant="empty" className="p-5 text-sm text-text-muted">
          尚未装配技能。工作方法按需加载，脚本执行仍须具备相应工具权限。
        </Card>
      )}
      {assembly.items.map((item) => (
        <div key={item.key}>{item.element}</div>
      ))}
      {assembly.chooserDialog}
      {assembly.panels}
    </section>
  );
}
