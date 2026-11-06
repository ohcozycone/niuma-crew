import { ResourceIcon } from "@/components/common/ResourceIcon";
import { FailureNotice } from "@/components/failure/FailureNotice";
import { FailureState } from "@/components/failure/FailureState";
import { clientFailure, toFailure, mutationOutcome } from "@/lib/failures/resolve";
import type { Failure } from "@/lib/failures/types";
import { FormField } from "@/components/common/FormField";
import { EmptyState } from "@/components/common/EmptyState";
import { SearchInput } from "@/components/common/SearchInput";
import { Card } from "@/components/ui/Card";
import { PageContainer } from "@/components/common/PageContainer";
import { useEditingRegistration } from "@/state/editing/useEditing";
import { ConfigurationConflict } from "@/components/configuration/ConfigurationConflict";
import { ApiError } from "@/lib/api/http";
import { Switch } from "@/components/ui/Switch";
import { useEffect, useRef, useState, type RefObject } from "react";
import { Link } from "react-router";
import { sourceLink } from "@/lib/navigation";
import { useQueryState } from "@/hooks/useQueryState";
import { KeyRound, Pencil, Plus, RefreshCw, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { PageHeading } from "@/components/common/PageHeading";
import { CollectionToolbar } from "@/components/common/CollectionToolbar";
import { PageActionsMenu } from "@/components/common/PageActionsMenu";
import { ButtonGroup } from "@/components/ui/ButtonGroup";
import { DropdownMenuItem } from "@/components/ui/DropdownMenu";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/Dialog";
import { SelectField } from "@/components/ui/SelectField";
import {
  deleteModelConnection,
  loadModelConnections,
  loadModelPresets,
  saveModelConnection,
  testModelConnection,
  type ModelConnection,
  type ModelPreset,
} from "@/lib/api/modelConnections";

export function ModelConnections({
  capability = "chat",
  embedded = false,
  onChanged,
}: {
  capability?: "chat" | "embedding";
  embedded?: boolean;
  onChanged?: () => void;
}) {
  const noun = capability === "embedding" ? "向量模型" : "大脑";
  const Frame = embedded ? "div" : PageContainer;
  const createButton = useRef<HTMLButtonElement>(null);
  const [connections, setConnections] = useState<ModelConnection[] | null>(null);
  const [presets, setPresets] = useState<ModelPreset[]>([]);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [query, setQuery] = useQueryState("q");
  const [revision, setRevision] = useState(0);
  const [editing, setEditing] = useState<ModelConnection | "new" | null>(null);
  const [deleting, setDeleting] = useState<ModelConnection | null>(null);
  const [busyDelete, setBusyDelete] = useState(false);
  const [deleteFailure, setDeleteFailure] = useState<Failure | null>(null);
  const deletingRef = useRef(false);
  const checks = useRef(new Set<string>());
  const [results, setResults] = useState<
    Record<string, { ok: boolean; message: string; checking?: boolean; failure?: Failure | null }>
  >({});
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([loadModelConnections(controller.signal), loadModelPresets(controller.signal)])
      .then(([rows, catalog]) => {
        if (!controller.signal.aborted) {
          setConnections(rows.filter((item) => item.capability === capability));
          setPresets(catalog.filter((item) => (item.capability ?? "chat") === capability));
          setFailure(null);
        }
      })
      .catch((failure) => {
        if (!controller.signal.aborted) {
          const value = toFailure(failure);
          setFailure(value);
          if ([401, 403, 404].includes(value?.status ?? 0)) {
            setConnections(null);
            setPresets([]);
            setEditing(null);
            setDeleting(null);
            setResults({});
          }
        }
      });
    return () => controller.abort();
  }, [revision, capability]);
  async function check(item: ModelConnection) {
    if (checks.current.has(item.id)) return;
    checks.current.add(item.id);
    setResults((previous) => ({
      ...previous,
      [item.id]: {
        ok: false,
        message:
          item.capability === "embedding" ? "正在验证真实向量调用…" : "正在检查凭证与模型目录…",
        checking: true,
      },
    }));
    try {
      const result = await testModelConnection(item.id);
      setResults((previous) => ({
        ...previous,
        [item.id]: {
          ...result,
          failure: result.ok
            ? null
            : clientFailure("model_connection_check_failed", result.message),
        },
      }));
    } catch (failure) {
      setResults((previous) => ({
        ...previous,
        [item.id]: { ok: false, message: "", failure: toFailure(failure) },
      }));
    } finally {
      checks.current.delete(item.id);
    }
  }
  async function remove() {
    if (!deleting || deletingRef.current) return;
    deletingRef.current = true;
    setBusyDelete(true);
    setDeleteFailure(null);
    try {
      await deleteModelConnection(deleting.id);
      setConnections((items) => items?.filter((item) => item.id !== deleting.id) ?? []);
      setDeleting(null);
      onChanged?.();
    } catch (failure) {
      setDeleteFailure(toFailure(failure));
    } finally {
      deletingRef.current = false;
      setBusyDelete(false);
    }
  }
  const visible =
    connections?.filter((item) =>
      `${item.name} ${item.model_id}`.toLowerCase().includes(query.trim().toLowerCase()),
    ) ?? [];
  return (
    <Frame>
      <PageHeading
        title={`${noun}配置`}
        headingLevel={embedded ? 2 : 1}
        description={
          capability === "embedding"
            ? "向量连接可供知识库复用，密钥在服务端加密保存。"
            : "配置员工使用的对话模型，再到员工页面选择装配。"
        }
        actions={
          <ButtonGroup>
            <Button ref={createButton} onClick={() => setEditing("new")} disabled={!presets.length}>
              <Plus size={16} />
              {capability === "chat" ? "新建大脑" : "添加向量模型"}
            </Button>
            <PageActionsMenu label={`${noun}更多操作`}>
              <DropdownMenuItem onClick={() => setRevision((n) => n + 1)}>
                <RefreshCw />
                重新加载列表
              </DropdownMenuItem>
            </PageActionsMenu>
          </ButtonGroup>
        }
      />
      {capability === "embedding" && (
        <p className="type-description mb-6">
          向量模型把文本转换为向量，用于语义检索。测试连接会发送一段固定短文本。
        </p>
      )}
      {failure &&
        (connections ? (
          <FailureNotice
            failure={failure}
            context={{ operation: "refresh", resource: "connection", hasUsableData: true }}
            actions={[
              { label: "重新加载", kind: "retry", onClick: () => setRevision((n) => n + 1) },
            ]}
            className="mb-5"
          />
        ) : (
          <FailureState
            failure={failure}
            context={{ operation: "initial-read", resource: "connection" }}
            actions={[
              { label: "重新加载", kind: "retry", onClick: () => setRevision((n) => n + 1) },
            ]}
          />
        ))}
      {!connections ? (
        !failure && <p role="status">正在加载{noun}配置…</p>
      ) : (
        <>
          <CollectionToolbar
            label={`筛选${noun}`}
            summary={`${query ? "找到" : "共"} ${visible.length} 个${noun}`}
          >
            <SearchInput
              label={`搜索${noun}`}
              onChange={(nextValue) => setQuery(nextValue)}
              placeholder="搜索名称或模型…"
              value={query}
              className="w-80 max-sm:w-full"
            />
          </CollectionToolbar>
          {!visible.length && (
            <EmptyState
              boxed
              text={connections.length ? `没有找到匹配的${noun}` : "先添加一个模型连接"}
              description={
                connections.length
                  ? "试试其他名称或模型标识。"
                  : "选择模型预设，填写名称和 API Key 后保存。"
              }
              icon={
                <ResourceIcon
                  kind={capability === "embedding" ? "embedding" : "brain"}
                  size={36}
                  aria-hidden="true"
                />
              }
            >
              {!connections.length && (
                <Button disabled={!presets.length} onClick={() => setEditing("new")}>
                  {capability === "chat" ? "新建大脑" : "添加向量模型"}
                </Button>
              )}
            </EmptyState>
          )}
          <div className={embedded ? "grid gap-4" : "connection-grid"}>
            {visible.map((item) => (
              <Card as="article" key={item.id} className="form-panel">
                <div className={"mb-4 flex items-start justify-between gap-3"}>
                  <div className={"min-w-0"}>
                    <div className={"mb-2 flex items-center gap-2"}>
                      <ResourceIcon
                        kind={capability === "embedding" ? "embedding" : "brain"}
                        size={20}
                        className={"shrink-0 text-action"}
                      />
                      <h2 className={"break-words text-lg font-semibold"}>{item.name}</h2>
                    </div>
                    <p className={"text-xs text-text-muted"}>
                      {presets.find((p) => p.id === item.preset_id)?.name ?? item.preset_id} ·
                      {item.capability === "embedding" ? "知识库向量" : "员工对话"}
                    </p>
                  </div>
                  <span
                    className={
                      "flex shrink-0 items-center gap-1 rounded-full bg-success-bg px-3 py-1 text-xs text-success"
                    }
                  >
                    <KeyRound size={12} />
                    {item.has_api_key ? "Key 已配置" : "Key 未配置"}
                  </span>
                </div>
                <dl className={"space-y-2 text-sm"}>
                  <div>
                    <dt className={"text-text-muted"}>Model ID</dt>
                    <dd className={"break-all font-mono"}>{item.model_id}</dd>
                  </div>
                  <div>
                    <dt className={"text-text-muted"}>Base URL</dt>
                    <dd className={"break-all text-text"}>{item.base_url}</dd>
                  </div>
                </dl>
                <div className={"my-5 border-t pt-4"}>
                  <p className={"mb-2 text-xs text-text-muted"}>
                    {item.capability === "embedding"
                      ? "用于知识库语义检索"
                      : `${item.agents.length} 位员工使用`}
                  </p>
                  <div className={"flex flex-wrap gap-2"}>
                    {item.capability === "embedding" ? (
                      <span className="text-sm text-text-muted">
                        {item.enabled ? "已启用" : "已停用"}
                      </span>
                    ) : item.agents.length ? (
                      item.agents.map((agent) => (
                        <Link
                          className={"rounded-soft bg-muted px-2 py-1 text-xs hover:underline"}
                          to={sourceLink(`/agents/${agent.id}?tab=instructions`)}
                          key={agent.id}
                        >
                          {agent.name}
                        </Link>
                      ))
                    ) : (
                      <span className={"text-sm text-text-muted"}>尚未装配给员工</span>
                    )}
                  </div>
                </div>
                {results[item.id]?.failure ? (
                  <FailureNotice
                    failure={results[item.id].failure}
                    context={{
                      operation: "mutation",
                      resource: "connection",
                    }}
                    className="mb-4"
                  />
                ) : (
                  results[item.id] && (
                    <p
                      role="status"
                      className={`mb-4 text-sm ${results[item.id].ok ? "text-success" : "text-text-muted"}`}
                    >
                      {results[item.id].message}
                    </p>
                  )
                )}
                <div className={"flex flex-wrap gap-2"}>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={results[item.id]?.checking}
                    onClick={() => void check(item)}
                  >
                    {results[item.id]?.checking ? "检查中…" : "测试连接"}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={results[item.id]?.checking}
                    onClick={() => setEditing(item)}
                  >
                    <Pencil size={14} />
                    编辑
                  </Button>
                  <Button
                    variant="destructive-ghost"
                    size="sm"
                    disabled={item.agents.length > 0 || results[item.id]?.checking}
                    title={item.agents.length ? "请先解除员工装配" : `删除${noun}`}
                    onClick={() => {
                      setDeleteFailure(null);
                      setDeleting(item);
                    }}
                  >
                    <Trash2 size={14} />
                    删除
                  </Button>
                </div>
              </Card>
            ))}
          </div>
        </>
      )}
      {editing && (
        <ConnectionEditor
          key={editing === "new" ? "new" : editing.id}
          value={editing}
          returnFocus={createButton}
          presets={presets}
          onClose={() => setEditing(null)}
          onSaved={(item) => {
            setConnections((rows) => [item, ...(rows ?? []).filter((row) => row.id !== item.id)]);
            setResults((previous) => {
              const next = { ...previous };
              delete next[item.id];
              return next;
            });
            setEditing(null);
            onChanged?.();
          }}
        />
      )}
      <Dialog
        open={Boolean(deleting)}
        onOpenChange={(open) => {
          if (!open && !busyDelete) setDeleting(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>删除「{deleting?.name}」？</DialogTitle>
            <DialogDescription>
              将删除连接配置和保存的 Key。仍有员工或知识库使用时无法删除。
            </DialogDescription>
          </DialogHeader>
          <FailureNotice
            failure={deleteFailure}
            context={{
              operation: "mutation",
              resource: "connection",
              outcome: mutationOutcome(deleteFailure),
            }}
          />
          <DialogFooter>
            <Button variant="outline" disabled={busyDelete} onClick={() => setDeleting(null)}>
              取消
            </Button>
            <Button variant="destructive" loading={busyDelete} onClick={() => void remove()}>
              {busyDelete ? "删除中…" : "确认删除"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Frame>
  );
}

function ConnectionEditor({
  value,
  presets,
  returnFocus,
  onClose,
  onSaved,
}: {
  value: ModelConnection | "new";
  presets: ModelPreset[];
  returnFocus: RefObject<HTMLElement | null>;
  onClose: () => void;
  onSaved: (item: ModelConnection) => void;
}) {
  const noun = presets[0].capability === "embedding" ? "向量模型" : "大脑";
  const editing = value === "new" ? null : value;
  const [presetId, setPresetId] = useState(editing?.preset_id || presets[0].id);
  const preset = presets.find((item) => item.id === presetId)!;
  const initialName = editing?.name ?? (noun === "向量模型" ? presets[0].name : "");
  const [name, setName] = useState(initialName);
  const [model, setModel] = useState(editing?.model_id ?? preset.default_model_id);
  const [key, setKey] = useState("");
  const [enabled, setEnabled] = useState(editing?.enabled ?? true);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [conflict, setConflict] = useState(false);
  const [expected, setExpected] = useState({
    config_revision: editing?.config_revision ?? 1,
    credential_revision: editing?.credential_revision ?? 1,
  });
  const [saving, setSaving] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);
  const savingRef = useRef(false);
  const dirty =
    name !== initialName ||
    model !== (editing?.model_id ?? presets[0].default_model_id) ||
    key !== "" ||
    enabled !== (editing?.enabled ?? true) ||
    presetId !== (editing?.preset_id ?? presets[0].id);
  useEditingRegistration({
    dirty,
    saving,
    isSaving: () => savingRef.current,
    discard: () => {
      setName(initialName);
      setModel(editing?.model_id ?? presets[0].default_model_id);
      setKey("");
      setEnabled(editing?.enabled ?? true);
      setPresetId(editing?.preset_id ?? presets[0].id);
    },
  });
  function close() {
    if (savingRef.current) return;
    if (dirty) setConfirmClose(true);
    else onClose();
  }
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) close();
      }}
    >
      <DialogContent finalFocus={returnFocus}>
        <DialogHeader>
          <DialogTitle>{editing ? `编辑${noun}` : `添加${noun}`}</DialogTitle>
          <DialogDescription>
            {editing?.agents.length
              ? `修改后将影响 ${editing.agents.length} 位员工的后续调用：${editing.agents.map((e) => e.name).join("、")}。`
              : preset.capability === "embedding"
                ? "保存后可在知识库中选择此连接，建立向量索引。"
                : "配置一套模型连接，供不同员工复用。"}
          </DialogDescription>
        </DialogHeader>
        <form
          onSubmit={async (event) => {
            event.preventDefault();
            if (savingRef.current) return;
            savingRef.current = true;
            setSaving(true);
            setFailure(null);
            setConflict(false);
            try {
              const item = await saveModelConnection(
                { name, model_id: model, api_key: key, preset_id: presetId, enabled },
                editing ? { ...editing, ...expected } : undefined,
              );
              setKey("");
              onSaved(item);
            } catch (failure) {
              setConflict(
                failure instanceof ApiError && failure.code === "configuration_revision_conflict",
              );
              setFailure(toFailure(failure));
            } finally {
              savingRef.current = false;
              setSaving(false);
            }
          }}
        >
          {conflict && editing && (
            <ConfigurationConflict
              resource={`model-connections/${editing.id}`}
              onUseRevisions={(value) => {
                setExpected({
                  config_revision: value.config_revision!,
                  credential_revision: value.credential_revision!,
                });
                setConflict(false);
                setFailure(null);
              }}
            />
          )}
          <fieldset disabled={saving} className={"space-y-4"}>
            <label className="flex items-center gap-2">
              <Switch checked={enabled} onCheckedChange={setEnabled} />
              启用此{noun}
            </label>
            <FormField htmlFor="brain-name" label={`${noun}名称`}>
              <Input
                id="brain-name"
                autoFocus
                required
                maxLength={100}
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={noun === "大脑" ? "例如：Kimi 研发大脑" : "例如：硅基流动知识库向量"}
              />
            </FormField>
            <FormField htmlFor="brain-preset" label="模型预设" description={preset.description}>
              <SelectField
                options={presets.map((item) => ({ value: item.id, label: item.name }))}
                value={presetId}
                disabled={Boolean(editing)}
                onValueChange={(id) => {
                  const next = presets.find((p) => p.id === id)!;
                  if (!name || name === preset.name) setName(next.name);
                  setPresetId(id);
                  setModel(next.default_model_id);
                }}
                id="brain-preset"
                className="w-fit"
              />
            </FormField>
            <FormField
              htmlFor="brain-key"
              label={<>API Key {editing && "（留空保持原值）"}</>}
              description="Key 在服务端加密保存，不会返回到页面。"
            >
              <Input
                id="brain-key"
                type="password"
                autoComplete="new-password"
                required={!editing}
                maxLength={4096}
                value={key}
                onChange={(e) => setKey(e.target.value)}
                placeholder={editing ? "已保存，不显示原 Key" : `输入 ${preset.name} API Key`}
              />
            </FormField>
            <div className={"rounded-control bg-canvas p-3 text-xs leading-6"}>
              <p>
                协议：
                {preset.capability === "embedding"
                  ? "OpenAI Embeddings"
                  : "OpenAI Chat Completions"}
              </p>
              <p className={"break-all"}>Base URL：{preset.base_url}</p>
            </div>
            <FormField
              htmlFor="brain-model"
              label="Model ID"
              description={
                preset.capability === "embedding"
                  ? "已固定为 BAAI/bge-m3，保存 Key 后点击“测试连接”验证。"
                  : "已按预设填写，可根据账户支持的模型调整。"
              }
            >
              <Input
                id="brain-model"
                required
                maxLength={120}
                value={model}
                readOnly={preset.capability === "embedding"}
                onChange={(e) => setModel(e.target.value)}
              />
            </FormField>
            <FailureNotice
              failure={failure}
              context={{
                operation: "mutation",
                resource: "connection",
                outcome: mutationOutcome(failure),
              }}
            />
            {confirmClose && (
              <p role="alert" className={"text-sm text-warning"}>
                {noun}配置尚未保存，是否放弃这次修改？
              </p>
            )}
            <DialogFooter>
              {confirmClose ? (
                <>
                  <Button type="button" variant="outline" onClick={() => setConfirmClose(false)}>
                    继续编辑
                  </Button>
                  <Button type="button" variant="destructive" onClick={onClose}>
                    放弃修改
                  </Button>
                </>
              ) : (
                <>
                  <Button type="button" variant="outline" onClick={close}>
                    取消
                  </Button>
                  <Button type="submit" loading={saving}>
                    {saving ? "保存中…" : `保存${noun}`}
                  </Button>
                </>
              )}
            </DialogFooter>
          </fieldset>
        </form>
      </DialogContent>
    </Dialog>
  );
}
