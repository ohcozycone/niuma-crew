import { useState } from "react";
import type { DocumentDetail } from "@/lib/api/knowledge";
import { Button } from "@/components/ui/Button";
import { TabsContent } from "@/components/ui/Tabs";
import { PageTabs } from "@/components/common/PageTabs";
import { cn } from "@/lib/utils";

export type KnowledgeDocumentView = "original" | "chunks";
const chunksPerPage = 20;

export function KnowledgeDocumentContent({
  document,
  initialView = "original",
  className,
}: {
  document: DocumentDetail;
  initialView?: KnowledgeDocumentView;
  className?: string;
}) {
  const [view, setView] = useState<string>(initialView);
  const [page, setPage] = useState(0);
  const lastPage = Math.max(0, Math.ceil(document.chunks.length / chunksPerPage) - 1);
  const currentPage = Math.min(page, lastPage);
  const offset = currentPage * chunksPerPage;
  const chunks = document.chunks.slice(offset, offset + chunksPerPage);
  return (
    <PageTabs
      value={view}
      onValueChange={setView}
      label="文档内容"
      placement="panel"
      activateOnFocus
      items={[
        { value: "original", label: "原文" },
        { value: "chunks", label: `分片（${document.chunks.length}）` },
      ]}
      className={cn("min-h-0 min-w-0 gap-0 overflow-hidden", className)}
    >
      <TabsContent
        value="original"
        className="focus-gutter min-h-0 overflow-y-auto overscroll-contain p-4 sm:p-6"
      >
        {document.document ? (
          <article
            aria-label="固定文档原文"
            className="mx-auto max-w-prose whitespace-pre-wrap break-words text-sm leading-8 [overflow-wrap:anywhere]"
          >
            {document.document.text}
          </article>
        ) : (
          <p className="text-sm leading-7 text-text-muted">
            尚未生成可阅读的原文。请先在文档列表中分片并建立关键词索引，也可以下载原件查看。
          </p>
        )}
      </TabsContent>
      <TabsContent value="chunks" className="flex min-h-0 flex-col overflow-hidden">
        {chunks.length ? (
          <>
            <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-3 sm:px-6">
              <p role="status" className="text-xs tabular-nums text-text-muted">
                第 {offset + 1}—{offset + chunks.length} 片，共 {document.chunks.length} 片
              </p>
              <div className="flex gap-2" aria-label="分片翻页">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={!currentPage}
                  onClick={() => setPage(currentPage - 1)}
                >
                  上一页
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={currentPage === lastPage}
                  onClick={() => setPage(currentPage + 1)}
                >
                  下一页
                </Button>
              </div>
            </div>
            <ol
              key={currentPage}
              start={offset + 1}
              aria-label="文档分片"
              tabIndex={0}
              className="focus-inset min-h-0 flex-1 divide-y divide-border overflow-y-auto overscroll-contain px-4 sm:px-6"
            >
              {chunks.map((chunk, index) => (
                <li key={chunk.id} className="min-w-0 py-5">
                  <div className="mx-auto max-w-prose">
                    <h3 className="text-sm font-medium [overflow-wrap:anywhere]">
                      分片 {offset + index + 1} · {chunk.locator}
                    </h3>
                    <p className="mt-1 text-xs tabular-nums text-text-muted">
                      {Array.from(chunk.text).length} 字符 · 原文位置 {chunk.start}—{chunk.end}
                    </p>
                    <p className="mt-3 whitespace-pre-wrap break-words text-sm leading-7 [overflow-wrap:anywhere]">
                      {chunk.text}
                    </p>
                  </div>
                </li>
              ))}
            </ol>
          </>
        ) : (
          <p className="p-4 text-sm leading-7 text-text-muted sm:p-6">
            暂无分片。请在文档列表中选择文件，点击“分片并建关键词索引”；处理成功后可在这里查看。
          </p>
        )}
      </TabsContent>
    </PageTabs>
  );
}
