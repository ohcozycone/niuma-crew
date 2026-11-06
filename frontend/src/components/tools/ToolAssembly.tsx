import { FailureNotice } from "@/components/failure/FailureNotice";
import { FailureState } from "@/components/failure/FailureState";
import { clientFailure, toFailure } from "@/lib/failures/resolve";
import type { Failure } from "@/lib/failures/types";
import { FormField } from "@/components/common/FormField";
import { AssemblyItem } from "@/components/configuration/AssemblyItem";
import { SelectField } from "@/components/ui/SelectField";
import { SearchInput } from "@/components/common/SearchInput";
import { Card } from "@/components/ui/Card";
import { useEffect, useState } from "react";
import { Link } from "react-router";
import { Plus } from "lucide-react";
import { ResourceIcon, capabilityResourceKind } from "@/components/common/ResourceIcon";
import type { AssemblyEntry, AssemblyCandidate } from "@/components/configuration/assemblyEntry";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/Dialog";
import { useIdentity } from "@/state/auth/useIdentity";
import {
  listToolConnections,
  toolLabel,
  type ToolConnection,
  type ToolGrantInput,
} from "@/lib/api/tools";

function initialGrant(connection: ToolConnection): ToolGrantInput {
  return {
    connection_id: connection.id,
    tools: [],
    expected_descriptors: {},
    account_mode: connection.kind === "native" ? "shared" : "personal",
    enabled: true,
    scope_policy:
      connection.kind === "native"
        ? {
            mode: "workspace",
            max_calls: 32,
            read_roots: ["/inputs", "/sources", "/workspace", "/outputs"],
            write_roots: ["/workspace", "/outputs"],
          }
        : { mode: "provider", max_calls: 5, arguments: {}, allowed_domains: [] },
  };
}
export function useToolAssembly({
  value,
  onChange,
  onValidityChange,
}: {
  value: ToolGrantInput[];
  onChange: (value: ToolGrantInput[]) => void;
  onValidityChange: (valid: boolean) => void;
}) {
  const identity = useIdentity();
  const [connections, setConnections] = useState<ToolConnection[]>([]);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refresh, setRefresh] = useState(0);
  const [chooser, setChooser] = useState(false);
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<ToolGrantInput | null>(null);
  const [policy, setPolicy] = useState("");
  const [panelFailure, setPanelFailure] = useState<Failure | null>(null);
  const [operationQuery, setOperationQuery] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    listToolConnections(controller.signal)
      .then((rows) => {
        if (!controller.signal.aborted) {
          setConnections(
            rows.filter(
              (row) => row.created_by_user_id === identity.actor.user?.id || row.kind === "native",
            ),
          );
          setLoading(false);
          setLoaded(true);
          setFailure(null);
        }
      })
      .catch((e) => {
        if (!controller.signal.aborted) {
          const value = toFailure(e);
          setFailure(value);
          if ([401, 403, 404].includes(value?.status ?? 0)) {
            setConnections([]);
            setLoaded(false);
          }
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [identity.actor.user?.id, refresh]);
  function configure(connection: ToolConnection) {
    const draft = structuredClone(
      value.find((item) => item.connection_id === connection.id) ?? initialGrant(connection),
    );
    setEditing(draft);
    setPolicy(JSON.stringify(draft.scope_policy, null, 2));
    setPanelFailure(null);
    setOperationQuery("");
    setChooser(false);
  }
  function finish() {
    if (!editing) return;
    try {
      let scope: unknown;
      try {
        scope = JSON.parse(policy);
      } catch {
        throw clientFailure("tool_scope_invalid", "范围约束必须为 JSON 对象。");
      }
      if (!scope || typeof scope !== "object" || Array.isArray(scope))
        throw clientFailure("tool_scope_invalid", "范围约束必须为 JSON 对象。");
      const maxCalls = (scope as Record<string, unknown>).max_calls ?? 5;
      if (!Number.isInteger(maxCalls) || Number(maxCalls) < 1 || Number(maxCalls) > 32)
        throw clientFailure("tool_scope_invalid", "每项工具调用上限需为 1—32 的整数。");
      if (!editing.tools.length)
        throw clientFailure("tool_selection_required", "至少选择一项已确认操作，或取消本次配置。");
      onChange([
        ...value.filter((item) => item.connection_id !== editing.connection_id),
        { ...editing, scope_policy: scope as Record<string, unknown> },
      ]);
      onValidityChange(true);
      setEditing(null);
    } catch (e) {
      setPanelFailure(toFailure(e));
    }
  }
  const connection = connections.find((row) => row.id === editing?.connection_id);
  const candidates = connections.filter(
    (row) =>
      !value.some((grant) => grant.connection_id === row.id) &&
      `${row.name} ${row.approved_catalog.map((tool) => `${tool.name} ${tool.description ?? ""}`).join(" ")}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  function refreshOptions() {
    setLoading(true);
    setFailure(null);
    setRefresh((current) => current + 1);
  }
  const items: AssemblyEntry[] = value.map((grant) => {
    const row = connections.find((item) => item.id === grant.connection_id);
    const unavailable = !loading && !failure && !row;
    const stale =
      row &&
      grant.tools.some(
        (name) =>
          !row.approved_catalog.some(
            (tool) =>
              tool.name === name && grant.expected_descriptors[name] === tool.descriptor_hash,
          ),
      );
    const kind = capabilityResourceKind(row?.kind ?? "unknown");
    return {
      key: `tool:${grant.connection_id}`,
      kind,
      name: row?.name ?? "原有工具装配",
      summary: `${grant.account_mode === "shared" ? "共用账号" : "使用者个人账号"} · ${grant.tools.length} 项操作`,
      element: (
        <AssemblyItem
          key={grant.connection_id}
          name={row?.name ?? "原有工具装配"}
          icon={<ResourceIcon kind={kind} size={18} className="text-text-muted" />}
          kind={kind}
          enabled={grant.enabled}
          onEnabledChange={(enabled) =>
            onChange(
              value.map((item) =>
                item.connection_id === grant.connection_id ? { ...item, enabled } : item,
              ),
            )
          }
          enableLabel={`${row?.name ?? "工具"}装配启用`}
          onConfigure={() => row && configure(row)}
          configurationDisabled={!row}
          onRemove={() =>
            onChange(value.filter((item) => item.connection_id !== grant.connection_id))
          }
          removeLabel={`移除${row?.name ?? (unavailable ? "不可用" : "原有")}装配`}
        >
          <p className="type-caption">
            {grant.account_mode === "shared" ? "共用账号" : "使用者个人账号"} · {grant.tools.length}{" "}
            项操作
          </p>
          {unavailable && <p className="text-sm text-danger">连接当前不可管理，可移除该装配。</p>}
          {stale && <p className="text-sm text-danger">有操作已移除或定义改变，请重新核对。</p>}
        </AssemblyItem>
      ),
    };
  });
  const candidateItems: AssemblyCandidate[] = candidates.map((row) => ({
    key: `tool:${row.id}`,
    kind: capabilityResourceKind(row.kind),
    name: row.name,
    summary: `${row.approved_catalog.length} 项已确认操作`,
    disabled: !row.enabled || !row.approved_catalog.length || loading,
    disabledReason: !row.enabled
      ? "连接已停用"
      : !row.approved_catalog.length
        ? "尚未确认工具目录"
        : undefined,
    select: () => configure(row),
  }));
  return {
    items,
    candidateItems,
    loading,
    refresh: refreshOptions,
    setQuery,
    openChooser: () => setChooser(true),
    feedback: (
      <>
        {" "}
        {failure &&
          (loaded ? (
            <FailureNotice
              failure={failure}
              context={{ operation: "refresh", resource: "connection", hasUsableData: true }}
              actions={[
                {
                  label: "重新加载",
                  kind: "retry",
                  onClick: () => setRefresh((value) => value + 1),
                },
              ]}
            />
          ) : (
            <FailureState
              failure={failure}
              layout="section"
              context={{ operation: "initial-read", resource: "connection" }}
              actions={[
                {
                  label: "重新加载",
                  kind: "retry",
                  onClick: () => setRefresh((value) => value + 1),
                },
              ]}
            />
          ))}
        {loading && <p role="status">正在读取可装配连接…</p>}
      </>
    ),
    chooserDialog: (
      <>
        {" "}
        <Dialog open={chooser} onOpenChange={setChooser}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>添加工具能力</DialogTitle>
              <DialogDescription>
                只列出可管理的账号连接，选择后配置本员工的操作许可。
              </DialogDescription>
            </DialogHeader>
            <SearchInput
              label="搜索工具连接"
              onChange={(nextValue) => setQuery(nextValue)}
              placeholder="搜索连接名称…"
              value={query}
              className="w-full"
            />
            <div className="focus-gutter max-h-96 space-y-2 overflow-auto">
              {candidates.map((row) => (
                <button
                  type="button"
                  key={row.id}
                  disabled={!row.enabled || !row.approved_catalog.length}
                  onClick={() => configure(row)}
                  className="flex w-full items-center justify-between gap-3 rounded-control border border-border p-3 text-left text-sm hover:bg-muted disabled:opacity-50"
                >
                  <span>
                    {row.name}
                    <span className="block type-caption">
                      {row.kind === "native" ? "内置" : "MCP"} · {row.approved_catalog.length}{" "}
                      项已确认操作
                    </span>
                  </span>
                  <Plus size={16} />
                </button>
              ))}
              {!candidates.length && <p className="type-caption">没有其他可装配连接。</p>}
            </div>
            <a
              href="/skills"
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm underline underline-offset-4"
            >
              去能力库管理账号与目录（新标签页）
            </a>
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
              <DialogTitle>{connection?.name ?? "配置工具能力"}</DialogTitle>
              <DialogDescription>
                只选择已确认操作。取消或关闭将丢弃面板修改，完成后再由员工页面统一保存。
              </DialogDescription>
            </DialogHeader>
            {editing && connection && (
              <div className="focus-gutter min-h-0 space-y-5 overflow-y-auto">
                {connection.service_id && (
                  <Link
                    className="text-sm underline underline-offset-4"
                    to={`/tools?service=${connection.service_id}`}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    管理账号与目录（新标签页）
                  </Link>
                )}
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="type-title">允许执行的操作</h3>
                  <span className="text-xs tabular-nums text-text-muted">
                    已选 {editing.tools.length} / {connection.approved_catalog.length}
                  </span>
                </div>
                {connection.approved_catalog.length > 5 && (
                  <SearchInput
                    label="筛选工具操作"
                    value={operationQuery}
                    onChange={setOperationQuery}
                    placeholder="按名称或用途筛选操作…"
                    className="w-full"
                  />
                )}
                <div className="space-y-2">
                  {connection.approved_catalog
                    .filter((tool) =>
                      `${toolLabel(connection, tool.name)} ${tool.name} ${tool.description ?? ""}`
                        .toLocaleLowerCase()
                        .includes(operationQuery.toLocaleLowerCase()),
                    )
                    .map((tool) => {
                      const checked = editing.tools.includes(tool.name);
                      const stale =
                        checked && editing.expected_descriptors[tool.name] !== tool.descriptor_hash;
                      return (
                        <label
                          key={tool.name}
                          className={`flex items-start gap-3 rounded-control border p-3 text-sm ${checked ? "border-input bg-selected" : "border-border bg-raised"}`}
                        >
                          <input
                            type="checkbox"
                            className="mt-1 size-4 shrink-0 accent-action"
                            disabled={!connection.enabled}
                            checked={checked}
                            onChange={(event) =>
                              setEditing({
                                ...editing,
                                tools: event.target.checked
                                  ? [...editing.tools, tool.name]
                                  : editing.tools.filter((name) => name !== tool.name),
                                expected_descriptors: {
                                  ...editing.expected_descriptors,
                                  [tool.name]: tool.descriptor_hash,
                                },
                              })
                            }
                          />
                          <span className="min-w-0 break-words">
                            {toolLabel(connection, tool.name)}
                            <span className="block text-xs text-text-muted">
                              {tool.description}
                            </span>
                            {stale && (
                              <span className="block text-danger">
                                定义改变，请取消后重新核对选择。
                              </span>
                            )}
                          </span>
                        </label>
                      );
                    })}
                  {editing.tools
                    .filter(
                      (name) => !connection.approved_catalog.some((tool) => tool.name === name),
                    )
                    .map((name) => (
                      <label key={name} className="flex items-center gap-3 text-sm text-danger">
                        <input
                          type="checkbox"
                          className="size-4 shrink-0 accent-action"
                          checked
                          onChange={() =>
                            setEditing({
                              ...editing,
                              tools: editing.tools.filter((tool) => tool !== name),
                            })
                          }
                        />
                        {name} · 已移除
                      </label>
                    ))}
                </div>
                <div className="space-y-4 border-t border-border pt-5">
                  <h3 className="type-title">使用方式</h3>
                  <FormField label={<>账号方式</>}>
                    <SelectField
                      value={editing.account_mode}
                      onValueChange={(nextValue) =>
                        setEditing({
                          ...editing,
                          account_mode: nextValue as "personal" | "shared",
                        })
                      }
                      options={[
                        {
                          value: "personal",
                          label: "使用者个人账号",
                          disabled: connection.kind === "native",
                        },
                        {
                          value: "shared",
                          label: "本员工共用账号",
                          disabled: connection.account_scope !== "shared",
                        },
                      ]}
                    />
                  </FormField>
                  <p className="type-caption">
                    {editing.account_mode === "shared"
                      ? "使用该员工的人可通过此共用账号执行所选操作。"
                      : "每位使用者绑定本人账号；不会借用创建者个人 Token。"}
                  </p>
                  <FormField label={<>每项工具调用上限</>}>
                    <Input
                      type="number"
                      min={1}
                      max={32}
                      className="max-w-32"
                      value={Number(editing.scope_policy.max_calls ?? 5)}
                      onChange={(e) => {
                        try {
                          const parsed: unknown = JSON.parse(policy);
                          if (!parsed || typeof parsed !== "object" || Array.isArray(parsed))
                            throw new Error();
                          const scope = { ...parsed, max_calls: Number(e.target.value) };
                          setEditing({ ...editing, scope_policy: scope });
                          setPolicy(JSON.stringify(scope, null, 2));
                          setPanelFailure(null);
                        } catch {
                          setPanelFailure(
                            clientFailure(
                              "tool_scope_invalid",
                              "请先修正高级范围约束的 JSON 格式，再修改调用上限。",
                            ),
                          );
                        }
                      }}
                    />
                  </FormField>
                </div>
                <details className="border-t border-border pt-4">
                  <summary className="cursor-pointer rounded-small text-sm text-text-muted">
                    高级范围约束
                  </summary>
                  <Textarea
                    className="mt-2 font-mono text-xs"
                    aria-label={`${connection.name}范围约束`}
                    rows={8}
                    value={policy}
                    onChange={(e) => {
                      const text = e.target.value;
                      setPolicy(text);
                      try {
                        const scope: unknown = JSON.parse(text);
                        if (scope && typeof scope === "object" && !Array.isArray(scope))
                          setEditing({
                            ...editing,
                            scope_policy: scope as Record<string, unknown>,
                          });
                      } catch {
                        // Keep incomplete JSON visible while the user is typing.
                      }
                    }}
                  />
                </details>
                <FailureNotice
                  failure={panelFailure}
                  context={{ operation: "mutation", resource: "connection" }}
                />
              </div>
            )}
            <DialogFooter className="border-t border-border pt-4">
              <Button type="button" variant="outline" onClick={() => setEditing(null)}>
                取消
              </Button>
              <Button type="button" onClick={finish}>
                完成，更新草稿
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </>
    ),
  };
}

export function ToolAssembly(props: Parameters<typeof useToolAssembly>[0]) {
  const assembly = useToolAssembly(props);
  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="type-title">
          MCP 与内置工具 <span className="type-caption">{props.value.length} 项装配</span>
        </h3>
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={assembly.loading}
            onClick={assembly.refresh}
          >
            刷新连接列表
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={assembly.openChooser}>
            <Plus />
            添加工具能力
          </Button>
        </div>
      </div>
      {assembly.feedback}
      {!props.value.length && (
        <Card as="p" variant="empty" className="p-5 text-sm text-text-muted">
          尚未装配工具能力。可选择已经确认目录的 MCP 或内置工具。
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
