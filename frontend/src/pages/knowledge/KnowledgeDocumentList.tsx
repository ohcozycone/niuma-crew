import {
  Check,
  ChevronRight,
  CircleCheck,
  CircleDashed,
  Clock3,
  Minus,
  Scissors,
  TriangleAlert,
} from "lucide-react";
import { Link } from "react-router";
import type { KnowledgeDocument } from "@/lib/api/knowledge";
import { ResourceIcon } from "@/components/common/ResourceIcon";
import { Button } from "@/components/ui/Button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/Table";
import { cn } from "@/lib/utils";

export const processingLabels = {
  pending: "待分片",
  queued: "排队中",
  processing: "分片中",
  ready: "关键词可用",
  failed: "分片失败",
  interrupted: "分片已中断",
};

export const isDocumentProcessing = (doc: KnowledgeDocument) =>
  doc.processing_state === "queued" || doc.processing_state === "processing";

export function KnowledgeDocumentList({
  id,
  documents,
  selected,
  writable,
  onSelectionChange,
  onRetry,
}: {
  id: string;
  documents: KnowledgeDocument[];
  selected: string[];
  writable: boolean;
  onSelectionChange: (ids: string[]) => void;
  onRetry: (doc: KnowledgeDocument) => void;
}) {
  const selectable = documents.filter((doc) => !isDocumentProcessing(doc));
  const selectedShown = selectable.filter((doc) => selected.includes(doc.id)).length;
  const all = selectable.length > 0 && selectedShown === selectable.length;
  return (
    <div className="@container overflow-hidden rounded-panel border border-border bg-raised">
      <Table aria-label="知识库文档">
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="w-12 px-2 [@media(pointer:coarse)]:w-16">
              <DocumentCheckbox
                label="全选当前结果"
                checked={all}
                mixed={selectedShown > 0 && !all}
                disabled={!writable || !selectable.length}
                onChange={(checked) => {
                  const shownIds = new Set(selectable.map((doc) => doc.id));
                  onSelectionChange(
                    checked
                      ? [...new Set([...selected, ...shownIds])]
                      : selected.filter((item) => !shownIds.has(item)),
                  );
                }}
              />
            </TableHead>
            <TableHead className="pl-0">文档名称</TableHead>
            <TableHead className="hidden w-36 @min-[760px]:table-cell">关键词状态</TableHead>
            <TableHead className="hidden w-20 text-right @min-[760px]:table-cell">片段数</TableHead>
            <TableHead className="hidden w-36 @min-[760px]:table-cell">向量状态</TableHead>
            <TableHead className="w-10 px-2">
              <span className="sr-only">查看文档</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {documents.map((doc) => {
            const status = doc.processing_state ?? "ready";
            const failed = status === "failed" || status === "interrupted";
            const keywordReady = doc.keyword_ready !== false && doc.chunk_count > 0;
            const StatusIcon = failed
              ? TriangleAlert
              : isDocumentProcessing(doc)
                ? Clock3
                : status === "ready"
                  ? CircleCheck
                  : CircleDashed;
            const vectorLabel = doc.vector_ready
              ? "向量可用"
              : keywordReady
                ? "待向量化"
                : "待分片后建立";
            return (
              <TableRow
                key={doc.id}
                className={cn(
                  "group relative focus-within:bg-muted/50",
                  selected.includes(doc.id) &&
                    "bg-selected hover:bg-selected focus-within:bg-selected",
                )}
              >
                <TableCell className="px-2 align-top pt-4">
                  <DocumentCheckbox
                    label={`选择${doc.filename}`}
                    checked={selected.includes(doc.id)}
                    disabled={!writable || isDocumentProcessing(doc)}
                    onChange={(checked) =>
                      onSelectionChange(
                        checked
                          ? [...selected, doc.id]
                          : selected.filter((item) => item !== doc.id),
                      )
                    }
                  />
                </TableCell>
                <TableCell className="py-4 pl-0">
                  <Link
                    to={`/knowledge/${id}/documents/${doc.id}`}
                    className="flex min-w-0 items-start gap-3 outline-none after:absolute after:inset-0 after:rounded-small focus-visible:after:outline-2 focus-visible:after:-outline-offset-2 focus-visible:after:outline-focus"
                  >
                    <ResourceIcon
                      kind="document"
                      size={20}
                      className="mt-0.5 shrink-0 text-text-muted"
                    />
                    <div className="min-w-0">
                      <h3 className="break-words text-sm font-medium [overflow-wrap:anywhere]">
                        {doc.title}
                      </h3>
                      <p className="mt-1 break-words text-xs text-text-muted [overflow-wrap:anywhere]">
                        {doc.filename} · {(doc.size / 1024).toFixed(1)} KiB
                      </p>
                    </div>
                  </Link>
                  <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-text-muted @min-[760px]:hidden">
                    <span className={cn("inline-flex items-center gap-1", failed && "text-danger")}>
                      <StatusIcon size={14} />
                      {processingLabels[status]}
                    </span>
                    <span className="tabular-nums">{doc.chunk_count} 个片段</span>
                    <span>{vectorLabel}</span>
                  </div>
                  {doc.processing_error && (
                    <p className="mt-2 break-words text-xs text-danger">{doc.processing_error}</p>
                  )}
                  {writable && failed && (
                    <Button
                      className="relative z-10 mt-2"
                      size="sm"
                      variant="outline"
                      onClick={() => onRetry(doc)}
                    >
                      <Scissors size={14} />
                      重试分片
                    </Button>
                  )}
                </TableCell>
                <TableCell className="hidden @min-[760px]:table-cell">
                  <span
                    className={cn(
                      "inline-flex items-center gap-1.5 text-xs",
                      failed ? "text-danger" : "text-text-muted",
                    )}
                  >
                    <StatusIcon size={14} className="shrink-0" />
                    {processingLabels[status]}
                  </span>
                  {keywordReady && status !== "ready" && (
                    <p className="mt-1 text-xs text-text-muted">原关键词索引仍可用</p>
                  )}
                </TableCell>
                <TableCell className="hidden text-right text-xs tabular-nums text-text-muted @min-[760px]:table-cell">
                  {doc.chunk_count}
                </TableCell>
                <TableCell className="hidden text-xs text-text-muted @min-[760px]:table-cell">
                  {vectorLabel}
                </TableCell>
                <TableCell className="px-2">
                  <ChevronRight size={16} className="text-text-muted" />
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}

function DocumentCheckbox({
  label,
  checked,
  mixed = false,
  disabled,
  onChange,
}: {
  label: string;
  checked: boolean;
  mixed?: boolean;
  disabled: boolean;
  onChange: (checked: boolean) => void;
}) {
  const Icon = mixed ? Minus : Check;
  return (
    <label className="relative z-10 flex size-8 cursor-pointer items-center justify-center rounded-small has-disabled:cursor-not-allowed [@media(pointer:coarse)]:size-11">
      <input
        type="checkbox"
        aria-label={label}
        aria-checked={mixed ? "mixed" : checked}
        ref={(node) => {
          if (node) node.indeterminate = mixed;
        }}
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
        className="peer size-4 appearance-none rounded-tiny border border-text-muted bg-surface transition-colors checked:border-action checked:bg-action indeterminate:border-action indeterminate:bg-action focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:border-border disabled:bg-muted"
      />
      <Icon
        size={12}
        strokeWidth={3}
        className="pointer-events-none absolute hidden text-action-text peer-checked:block peer-indeterminate:block"
      />
    </label>
  );
}
