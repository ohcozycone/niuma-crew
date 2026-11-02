import { useRef, useState } from "react";
import type { ChunkingRules, KnowledgeBase, KnowledgeDocument } from "@/lib/api/knowledge";
import { Button } from "@/components/ui/Button";
import { SelectField } from "@/components/ui/SelectField";
import { FormField } from "@/components/common/FormField";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/Dialog";
import { FailureNotice } from "@/components/failure/FailureNotice";
import { mutationOutcome } from "@/lib/failures/resolve";
import { useWorkspaceData } from "@/state/workspace/useWorkspaceData";
import { useResource } from "@/state/shared/useResource";
import { useSaveOperation } from "@/state/editing/useSaveOperation";
import { useEditingRegistration } from "@/state/editing/useEditing";
import {
  KnowledgeChunkRules,
  resolveChunkRules,
  type ChunkRuleInputs,
} from "./KnowledgeChunkRules";
import { KnowledgeFeedback } from "./KnowledgeLibraries";

export function KnowledgeProcessing({
  library,
  documents,
  selected,
  reprocess,
  onReprocessChange,
  onClose,
  onSubmitted,
}: {
  library: KnowledgeBase;
  documents: KnowledgeDocument[];
  selected: string[];
  reprocess: boolean;
  onReprocessChange: (value: boolean) => void;
  onClose: () => void;
  onSubmitted: (count: number) => void;
}) {
  const store = useWorkspaceData().knowledge;
  const save = useSaveOperation();
  const defaults: ChunkRuleInputs = {
    size: String(library.effective_chunk_size ?? 800),
    overlap: String(library.effective_chunk_overlap ?? 120),
    minimum: String(
      library.effective_min_section_chars ??
        Math.min(
          200,
          (library.effective_chunk_size ?? 800) - (library.effective_chunk_overlap ?? 120),
        ),
    ),
  };
  const [inputs, setInputs] = useState(defaults);
  const [preview, setPreview] = useState(false);
  const targets = documents.filter(
    (doc) =>
      !["queued", "processing"].includes(doc.processing_state ?? "") &&
      (!selected.length || selected.includes(doc.id)) &&
      (reprocess || (doc.processing_state ?? "ready") !== "ready"),
  );
  const [file, setFile] = useState(targets[0]?.id ?? "");
  const targetFile = targets.find((doc) => doc.id === file)?.id ?? targets[0]?.id ?? "";
  const request = useRef<{ id: string; signature: string } | null>(null);
  const { rules, error } = resolveChunkRules(inputs);
  useEditingRegistration({
    dirty: false,
    saving: save.saving,
    isSaving: () => save.saving,
    discard: onClose,
  });
  async function submit() {
    const ids = selected.length ? [...selected].sort() : undefined;
    const signature = JSON.stringify([ids ? [...ids].sort() : null, reprocess, rules]);
    if (request.current?.signature !== signature)
      request.current = { id: crypto.randomUUID(), signature };
    try {
      const batch = await save.run(() =>
        store.process(library.id, request.current!.id, ids, reprocess, rules),
      );
      onSubmitted(batch.items.length);
    } catch (error) {
      save.setError(error);
    }
  }
  return (
    <Dialog
      open
      onOpenChange={(next) => {
        if (!next && !save.saving) onClose();
      }}
    >
      <DialogContent size="wide" className="grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden">
        <DialogHeader>
          <DialogTitle>处理文档</DialogTitle>
          <DialogDescription>
            将解析并切分{targets.length}
            份文件，建立关键词索引。每份成功文件立即可用；提交后可离开页面。
          </DialogDescription>
        </DialogHeader>
        <div className="focus-gutter min-h-0 min-w-0 space-y-4 overflow-y-auto overscroll-contain">
          <KnowledgeChunkRules
            value={inputs}
            disabled={save.saving}
            onChange={(next) => {
              setInputs(next);
              setPreview(false);
              save.clearError();
            }}
          />
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-xs text-text-muted">
              本次调整只用于这批任务，不修改知识库默认设置。
            </p>
            <Button
              size="sm"
              variant="ghost"
              disabled={save.saving}
              onClick={() => {
                setInputs(defaults);
                setPreview(false);
              }}
            >
              恢复库规则
            </Button>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={reprocess}
              disabled={save.saving}
              onChange={(e) => {
                onReprocessChange(e.target.checked);
                setPreview(false);
              }}
            />
            重新处理已有可用内容
          </label>
          <p className="text-xs text-text-muted">
            未选择文件时处理全部待处理项；勾选后包含已有可用文件。新结果成功前保留旧内容，成功后仅该文件需重建向量。向量可稍后在检索设置中建立。
          </p>
          {!!targets.length && (
            <section
              aria-label="处理前预览"
              className="min-w-0 space-y-4 border-t border-border pt-4"
            >
              <div className="flex flex-col items-stretch gap-3 sm:flex-row sm:items-end">
                <FormField label="预览文件" className="min-w-0 flex-1">
                  <SelectField
                    value={targetFile}
                    disabled={save.saving}
                    onValueChange={(value) => {
                      setFile(value);
                      setPreview(false);
                    }}
                    options={targets.map((doc) => ({ value: doc.id, label: doc.filename }))}
                  />
                </FormField>
                <Button
                  variant="outline"
                  disabled={!!error || save.saving}
                  onClick={() => setPreview(true)}
                >
                  预览切分
                </Button>
              </div>
              <p className="text-xs text-text-muted">
                预览只读取原件，不写入索引、不调用模型；修改规则或文件后需重新预览。
              </p>
              {preview && !error && (
                <ChunkPreview
                  key={`${targetFile}:${JSON.stringify(rules)}`}
                  kb={library.id}
                  document={targetFile}
                  rules={rules}
                />
              )}
            </section>
          )}
          <FailureNotice
            failure={save.failure}
            context={{
              operation: "mutation",
              resource: "knowledge",
              outcome: mutationOutcome(save.failure),
            }}
          />
        </div>
        <DialogFooter>
          <Button
            disabled={save.saving || !!error || !targets.length}
            onClick={() => void submit()}
          >
            {save.saving ? "正在提交…" : "开始后台处理"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ChunkPreview({
  kb,
  document,
  rules,
}: {
  kb: string;
  document: string;
  rules: ChunkingRules;
}) {
  const store = useWorkspaceData().knowledge;
  const [offset, setOffset] = useState(0);
  const resource = store.preview(kb, document, rules, offset);
  const state = useResource(resource);
  const result = state.data;
  return (
    <section aria-label="切分预览结果" className="min-w-0 space-y-3">
      <KnowledgeFeedback
        failure={state.failure}
        loading={state.loading}
        retry={() => resource.invalidate()}
      />
      {result && !state.loading && !state.failure && (
        <>
          <p role="status" className="text-sm">
            共{result.chunk_count}个片段 · {result.min_length}—{result.max_length}字符 ·{" "}
            {result.merged_chunk_count}个合并片段
          </p>
          {!!result.short_chunk_count && (
            <p className="text-xs text-text-muted">
              {result.short_chunk_count}
              个片段仍短于阈值：受章节边界或可合并内容长度限制，不强行凑长。
            </p>
          )}
          <ol start={offset + 1} className="min-w-0 space-y-4" aria-label="预览片段">
            {result.chunks.map((chunk, index) => (
              <li key={chunk.id} className="min-w-0 border-b border-border pb-4">
                <p className="text-sm font-medium">
                  片段{offset + index + 1} · {Array.from(chunk.text).length}字符
                  {(chunk.spans?.length ?? 0) > 1 ? " · 合并章节" : ""}
                </p>
                <p className="mt-1 break-words text-xs text-text-muted">{chunk.locator}</p>
                <p className="mt-1 text-xs text-text-muted">
                  原文位置 {chunk.start}—{chunk.end}
                </p>
                <pre className="mt-3 whitespace-pre-wrap break-words font-sans text-sm leading-relaxed [overflow-wrap:anywhere]">
                  {chunk.text}
                </pre>
              </li>
            ))}
          </ol>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs text-text-muted">
              显示{offset + 1}—{offset + result.chunks.length} / {result.chunk_count}
            </p>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="ghost"
                disabled={!offset}
                onClick={() => setOffset(Math.max(0, offset - 20))}
              >
                上一页
              </Button>
              <Button
                size="sm"
                variant="ghost"
                disabled={!result.has_more}
                onClick={() => setOffset(offset + 20)}
              >
                下一页
              </Button>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
