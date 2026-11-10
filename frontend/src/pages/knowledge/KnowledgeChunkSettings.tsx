import { useState } from "react";
import type { ChunkingRules } from "@/lib/api/knowledge";
import { Button } from "@/components/ui/Button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/Dialog";
import { useWorkspaceData } from "@/state/workspace/useWorkspaceData";
import { useResource } from "@/state/shared/useResource";
import { KnowledgeChunkRules, resolveChunkRules } from "./KnowledgeChunkRules";
import { KnowledgeFeedback } from "./KnowledgeLibraries";

export function KnowledgeChunkSettings({
  kb,
  rules,
  document,
  onClose,
  onConfirm,
}: {
  kb: string;
  rules: ChunkingRules;
  document?: { id: string; filename: string };
  onClose: () => void;
  onConfirm: (rules: ChunkingRules) => void;
}) {
  const [inputs, setInputs] = useState({
    size: String(rules.chunk_size),
    overlap: String(rules.chunk_overlap),
    minimum: String(rules.min_section_chars),
  });
  const [preview, setPreview] = useState(false);
  const draft = resolveChunkRules(inputs);
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent size="wide" className="grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden">
        <DialogHeader>
          <DialogTitle>分片规则</DialogTitle>
        </DialogHeader>
        <div className="focus-gutter min-h-0 min-w-0 space-y-5 overflow-y-auto overscroll-contain">
          <DialogDescription>
            确认后更新本页的分片规则。返回文档列表后，点击“分片并建关键词索引”才会处理所选文件。
          </DialogDescription>
          <KnowledgeChunkRules
            value={inputs}
            onChange={(next) => {
              setInputs(next);
              setPreview(false);
            }}
          />
          <section aria-label="处理前预览" className="space-y-3 border-t border-border pt-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="min-w-0 break-words text-sm">
                {document
                  ? `预览文件：${document.filename}`
                  : "在列表中选择文件后，可预览首份文件。"}
              </p>
              <Button
                variant="outline"
                disabled={!document || !!draft.error}
                onClick={() => setPreview(true)}
              >
                预览切分
              </Button>
            </div>
            <p className="text-xs text-text-muted">
              只读取原件，不修改文档或索引，不调用模型。修改规则后需重新预览。
            </p>
            {preview && document && !draft.error && (
              <ChunkPreview
                key={`${document.id}:${JSON.stringify(draft.rules)}`}
                kb={kb}
                document={document.id}
                rules={draft.rules}
              />
            )}
          </section>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            取消
          </Button>
          <Button disabled={!!draft.error} onClick={() => onConfirm(draft.rules)}>
            确认设置
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
