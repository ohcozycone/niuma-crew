import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router";
import { BookOpen } from "lucide-react";
import type { EmployeeKnowledgeInput, EmployeeKnowledgeSettings } from "@/lib/api/knowledge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { SelectField } from "@/components/ui/SelectField";
import { FormField } from "@/components/common/FormField";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/Dialog";
import { FailureNotice } from "@/components/failure/FailureNotice";
import { mutationOutcome } from "@/lib/failures/resolve";
import { useIdentity } from "@/state/auth/useIdentity";
import { useWorkspaceData } from "@/state/workspace/useWorkspaceData";
import { useResource } from "@/state/shared/useResource";
import { useSaveOperation } from "@/state/editing/useSaveOperation";
import { useEditingRegistration } from "@/state/editing/useEditing";

function settingsDraft(value: EmployeeKnowledgeSettings): EmployeeKnowledgeInput {
  return {
    expected_revision: value.revision,
    knowledge_base_ids: [...value.knowledge_base_ids].sort(),
    mode: value.mode,
    strategy: value.strategy,
    top_k: value.top_k,
  };
}

/** One personal editor, shared by employee configuration and the conversation sidebar. */
export function EmployeeKnowledge({
  agentId,
  agentName,
  compact = false,
  triggerLabel,
}: {
  agentId?: string;
  agentName?: string;
  compact?: boolean;
  triggerLabel?: string;
}) {
  const identity = useIdentity();
  if (
    !identity.permissions.includes("knowledge:use") ||
    !identity.permissions.includes("runs:create")
  )
    return null;
  if (!agentId)
    return <p className="type-caption mt-3">先保存员工，再选择你希望这位员工使用的知识库。</p>;
  return (
    <EmployeeKnowledgeEditor
      key={`${agentId}:${identity.actor.user?.id ?? "guest"}`}
      agentId={agentId}
      agentName={agentName}
      compact={compact}
      triggerLabel={triggerLabel}
    />
  );
}

function EmployeeKnowledgeEditor({
  agentId,
  agentName,
  compact,
  triggerLabel,
}: {
  agentId: string;
  agentName?: string;
  compact: boolean;
  triggerLabel?: string;
}) {
  const store = useWorkspaceData().knowledge;
  const resource = store.employeeBindings(agentId);
  const state = useResource(resource);
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<EmployeeKnowledgeInput | null>(null);
  const baseline = useRef("");
  const save = useSaveOperation();
  const [saved, setSaved] = useState(false);
  const dirty = open && draft !== null && JSON.stringify(draft) !== baseline.current;
  function load(value: EmployeeKnowledgeSettings) {
    const next = settingsDraft(value);
    baseline.current = JSON.stringify(next);
    setDraft(next);
  }
  useEffect(() => {
    if (open && !draft && state.data && !state.loading && !state.failure) load(state.data);
  }, [open, draft, state.data, state.loading, state.failure]);
  useEditingRegistration({
    dirty,
    saving: save.saving,
    isSaving: () => save.saving,
    discard: () => setOpen(false),
  });
  const libraries = state.data?.libraries ?? [];
  const selected = draft?.knowledge_base_ids ?? [];
  const missing = selected.filter((id) => !libraries.some((library) => library.id === id));
  const invalid =
    !!draft &&
    (!Number.isInteger(draft.top_k) ||
      draft.top_k < 1 ||
      draft.top_k > 12 ||
      selected.length > 10 ||
      missing.length > 0);
  const unavailableVector =
    draft &&
    ["vector", "hybrid"].includes(draft.strategy) &&
    selected.some((id) => {
      const library = libraries.find((item) => item.id === id);
      return !library || !["ready", "partial"].includes(library.vector_status);
    });
  function update<K extends keyof EmployeeKnowledgeInput>(
    key: K,
    value: EmployeeKnowledgeInput[K],
  ) {
    setDraft((current) => (current ? { ...current, [key]: value } : current));
    setSaved(false);
    save.clearError();
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    event.stopPropagation(); // Portal events still bubble through the employee's shared-config form.
    if (!draft || invalid || save.saving || state.loading || state.failure) return;
    try {
      const next = await save.run(() => store.saveEmployeeBindings(agentId, draft));
      load(next);
      setSaved(true);
      setOpen(false);
    } catch (error) {
      save.setError(error);
    }
  }
  return (
    <>
      {!compact && state.data && (
        <div className="mb-3 space-y-2 text-sm" aria-label="已选择的个人知识库">
          {state.data.knowledge_base_ids.length ? (
            state.data.knowledge_base_ids.map((id) => (
              <p key={id} className="flex min-w-0 items-start gap-2">
                <BookOpen size={14} className="mt-1 shrink-0 text-text-muted" aria-hidden="true" />
                <span className="break-words">
                  {state.data?.libraries.find((library) => library.id === id)?.name ??
                    "原知识库已不可用"}
                </span>
              </p>
            ))
          ) : (
            <p className="text-xs leading-6 text-text-muted">
              尚未选择参考知识库。可以先完善指令，之后按需添加资料。
            </p>
          )}
        </div>
      )}
      <Dialog
        open={open}
        onOpenChange={(next) => {
          if (save.saving) return;
          if (!next && dirty && !window.confirm("放弃尚未保存的个人知识库设置？")) return;
          if (next) {
            setDraft(null);
            save.clearError();
            if (state.data && !state.loading && !state.failure) load(state.data);
          }
          setOpen(next);
        }}
      >
        <DialogTrigger
          render={<Button type="button" size="sm" variant={compact ? "ghost" : "outline"} />}
        >
          {!triggerLabel && <BookOpen size={16} />}
          {triggerLabel ??
            `我的知识库${state.data ? `（${state.data.knowledge_base_ids.length}）` : ""}`}
        </DialogTrigger>
        <DialogContent size="wide" className="grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden">
          <DialogHeader>
            <DialogTitle>{agentName ? `${agentName} · 我的知识库` : "我的知识库"}</DialogTitle>
            <DialogDescription>
              仅供你使用这位员工时检索，不会向其他使用者共享你的资料。这里独立保存，不修改员工的岗位指令。
            </DialogDescription>
          </DialogHeader>
          <form
            id={`employee-knowledge-${agentId}`}
            onSubmit={submit}
            className="min-h-0 min-w-0 space-y-5 overflow-y-auto overscroll-contain"
          >
            {state.loading && (
              <p role="status" className="type-description">
                正在读取知识库设置…
              </p>
            )}
            <FailureNotice
              failure={state.failure}
              context={{
                operation: state.data ? "refresh" : "initial-read",
                resource: "knowledge",
                hasUsableData: !!state.data,
              }}
              actions={[{ label: "重新加载", kind: "retry", onClick: () => resource.invalidate() }]}
            />
            {draft && (
              <fieldset
                disabled={save.saving || state.loading || !!state.failure}
                className="min-w-0 space-y-5"
              >
                <section aria-label="选择个人知识库" className="space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <h3 className="type-title">选择知识库 · {selected.length}/10</h3>
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      nativeButton={false}
                      role="link"
                      render={<Link to="/knowledge" target="_blank" rel="noopener noreferrer" />}
                    >
                      管理知识库<span className="sr-only">（新标签页）</span>
                    </Button>
                  </div>
                  {!libraries.length && (
                    <p className="type-description">
                      你还没有知识库。先创建并上传资料，处理完成后即可检索；也可以先保存空装配。
                    </p>
                  )}
                  <div className="max-h-60 min-w-0 divide-y divide-border overflow-y-auto border-y border-border">
                    {libraries.map((library) => {
                      const ready =
                        library.keyword_document_count ??
                        (library.chunk_count ? library.document_count : 0);
                      return (
                        <label
                          key={library.id}
                          className="flex min-w-0 cursor-pointer items-start gap-3 py-3"
                        >
                          <input
                            type="checkbox"
                            className="mt-1 size-4 shrink-0 accent-action"
                            checked={selected.includes(library.id)}
                            disabled={!selected.includes(library.id) && selected.length >= 10}
                            onChange={(event) =>
                              update(
                                "knowledge_base_ids",
                                (event.target.checked
                                  ? [...selected, library.id]
                                  : selected.filter((id) => id !== library.id)
                                ).sort(),
                              )
                            }
                          />
                          <span className="min-w-0 flex-1">
                            <span className="block break-words text-sm font-medium">
                              {library.name}
                            </span>
                            {library.description && (
                              <span className="mt-1 block break-words text-xs text-text-muted">
                                {library.description}
                              </span>
                            )}
                            <span className="mt-1 block text-xs text-text-muted">
                              {ready}/{library.document_count}份关键词可用 ·{" "}
                              {ready
                                ? ["ready", "partial"].includes(library.vector_status)
                                  ? `${library.vector_chunk_count}个向量片段可用`
                                  : "未建立可用向量，自动模式使用关键词"
                                : "尚无可检索内容，原件不会直接发送给模型"}
                            </span>
                          </span>
                        </label>
                      );
                    })}
                    {missing.map((id) => (
                      <label key={id} className="flex items-start gap-3 py-3 text-sm text-danger">
                        <input
                          type="checkbox"
                          className="mt-1 size-4"
                          checked
                          onChange={() =>
                            update(
                              "knowledge_base_ids",
                              selected.filter((item) => item !== id),
                            )
                          }
                        />
                        原知识库已不可用，请取消选择后保存。
                      </label>
                    ))}
                  </div>
                </section>
                <div className="grid min-w-0 gap-4 sm:grid-cols-2">
                  <FormField label="何时检索资料">
                    <SelectField
                      value={draft.mode}
                      onValueChange={(value) =>
                        update("mode", value as EmployeeKnowledgeInput["mode"])
                      }
                      options={[
                        { value: "on_demand", label: "由员工按问题需要查询" },
                        { value: "always", label: "每次回答前先检索" },
                      ]}
                    />
                    <p className="type-caption">
                      按需模式根据岗位、资料范围和问题决定是否查询；每次先检索适合专门的资料问答。
                    </p>
                  </FormField>
                  <FormField label="检索方式">
                    <SelectField
                      value={draft.strategy}
                      onValueChange={(value) =>
                        update("strategy", value as EmployeeKnowledgeInput["strategy"])
                      }
                      options={[
                        { value: "auto", label: "自动：有向量用混合，否则关键词" },
                        { value: "bm25", label: "仅关键词（BM25）" },
                        { value: "vector", label: "仅向量" },
                        { value: "hybrid", label: "关键词与向量混合" },
                      ]}
                    />
                    <p className="type-caption">
                      自动模式按每个库的实际能力选择；指定向量或混合时，不可用会明确报错。
                    </p>
                  </FormField>
                </div>
                <FormField
                  label="最多召回片段数"
                  description="所有已选知识库合计的上限，不是每个库分别返回这么多。"
                >
                  <Input
                    type="number"
                    min={1}
                    max={12}
                    value={draft.top_k}
                    onChange={(event) => update("top_k", Number(event.target.value))}
                    className="max-w-32"
                  />
                </FormField>
                {invalid && (
                  <p role="alert" className="text-sm text-danger">
                    最多选择10个可用知识库，召回片段数需为1—12的整数。
                  </p>
                )}
                {unavailableVector && (
                  <p role="status" className="text-sm text-danger">
                    所选库尚未全部具有可用向量。当前策略仍会保存，检索时会明确报错；可改选自动或关键词模式。
                  </p>
                )}
                <p className="type-caption">
                  保存后用于新任务；使用旧装配的在途任务会停止，需要重新发送。未处理文件不参与检索，资料不足时员工应说明缺少依据。
                </p>
              </fieldset>
            )}
            <FailureNotice
              failure={save.failure}
              context={{
                operation: "mutation",
                resource: "knowledge",
                outcome: mutationOutcome(save.failure),
              }}
            />
            {save.failure?.status === 409 && (
              <Button
                type="button"
                variant="outline"
                onClick={async () => {
                  resource.invalidate();
                  await resource.ensure();
                  const next = resource.getSnapshot();
                  if (next.data && !next.failure) {
                    load(next.data);
                    save.clearError();
                  }
                }}
              >
                载入最新设置
              </Button>
            )}
          </form>
          <DialogFooter>
            <Button
              type="submit"
              form={`employee-knowledge-${agentId}`}
              disabled={!draft || invalid || state.loading || !!state.failure}
              loading={save.saving}
            >
              {save.saving ? "正在保存…" : "保存我的知识库"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      {saved && !open && !compact && (
        <p role="status" className="type-caption mt-2">
          个人知识库设置已保存。
        </p>
      )}
    </>
  );
}
