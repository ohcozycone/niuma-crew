import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { ArrowLeft, ChevronRight, Plus, Upload } from "lucide-react";
import { ResourceIcon } from "@/components/common/ResourceIcon";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { TabsContent } from "@/components/ui/Tabs";
import { PageTabs } from "@/components/common/PageTabs";
import { PageContainer } from "@/components/common/PageContainer";
import { PageHeading } from "@/components/common/PageHeading";
import { EmptyState } from "@/components/common/EmptyState";
import { SearchInput } from "@/components/common/SearchInput";
import { FailureNotice } from "@/components/failure/FailureNotice";
import { mutationOutcome } from "@/lib/failures/resolve";
import { useWorkspaceData } from "@/state/workspace/useWorkspaceData";
import { useAtom, useResource } from "@/state/shared/useResource";
import { useSaveOperation } from "@/state/editing/useSaveOperation";
import { useQueryState } from "@/hooks/useQueryState";
import type { KnowledgeDocument } from "@/lib/api/knowledge";
import { KnowledgeFeedback } from "./KnowledgeLibraries";
import { KnowledgeSearch } from "./KnowledgeSearch";
import { KnowledgeSettings } from "./KnowledgeSettings";
import { KnowledgeProcessing } from "./KnowledgeProcessing";

export const processingLabels = {
  pending: "待处理",
  queued: "排队中",
  processing: "处理中",
  ready: "处理完成",
  failed: "处理失败",
  interrupted: "处理已中断",
};
const active = (doc: KnowledgeDocument) =>
  doc.processing_state === "queued" || doc.processing_state === "processing";

export function KnowledgeLibrary({ id }: { id: string }) {
  const store = useWorkspaceData().knowledge;
  const resource = store.library(id);
  const state = useResource(resource);
  const documents = useResource(store.documents(id));
  const jobs = useResource(store.processing(id));
  const uploads = useAtom(store.uploads.state);
  const [adding, setAdding] = useState(false);
  const [params, setParams] = useSearchParams();
  const view = params.get("view") === "search" ? "search" : "documents";
  const busy =
    documents.data?.some(active) ||
    jobs.data?.some((b) => ["queued", "running"].includes(b.status));
  useEffect(() => {
    if (!busy || documents.loading || jobs.loading) return;
    const timer = window.setTimeout(() => store.refresh(), 1500);
    return () => window.clearTimeout(timer);
  }, [busy, documents.loading, documents.data, jobs.loading, jobs.data, store]);
  const pendingUploads = uploads.entries.filter(
    (e) => e.kb === id && !["done", "cancelled"].includes(e.status),
  ).length;
  return (
    <PageContainer>
      <KnowledgeFeedback
        failure={state.failure}
        hasUsableData={state.data !== undefined}
        returnTo="/knowledge"
        loading={state.loading}
        retry={() => resource.invalidate()}
      />
      {state.data && (
        <>
          <PageHeading
            title={state.data.name}
            description={`${state.data.document_count} 份原件 · ${state.data.keyword_document_count ?? state.data.document_count} 份关键词可用`}
            actions={
              <>
                <Button
                  variant="ghost"
                  nativeButton={false}
                  role="link"
                  render={<Link to="/knowledge" />}
                >
                  <ArrowLeft size={16} />
                  全部知识库
                </Button>
                <KnowledgeSettings library={state.data} />
                <Button
                  aria-expanded={adding && view === "documents"}
                  aria-controls="knowledge-add-documents"
                  onClick={() => {
                    setAdding(view === "documents" ? !adding : true);
                    if (view !== "documents")
                      setParams((current) => {
                        const copy = new URLSearchParams(current);
                        copy.set("view", "documents");
                        return copy;
                      });
                  }}
                >
                  <Plus size={16} />
                  {adding && view === "documents"
                    ? "收起添加文档"
                    : `添加文档${pendingUploads ? `（${pendingUploads}）` : ""}`}
                </Button>
              </>
            }
          />
          {state.data.description && (
            <details className="mb-4 max-w-prose text-sm text-text-muted">
              <summary className="cursor-pointer">用途说明</summary>
              <p className="mt-2 break-words">{state.data.description}</p>
            </details>
          )}
          <PageTabs
            label="库内功能"
            items={[
              { value: "documents", label: "文档" },
              { value: "search", label: "检索测试" },
            ]}
            value={view}
            onValueChange={(next) =>
              setParams((current) => {
                const copy = new URLSearchParams(current);
                copy.set("view", next);
                return copy;
              })
            }
          >
            <TabsContent value="documents">
              <LibraryDocuments id={id} name={state.data.name} adding={adding} />
            </TabsContent>
            <TabsContent value="search">
              <KnowledgeSearch key={params.get("question") || ""} id={id} />
            </TabsContent>
          </PageTabs>
        </>
      )}
    </PageContainer>
  );
}

function LibraryDocuments({ id, name, adding }: { id: string; name: string; adding: boolean }) {
  const store = useWorkspaceData().knowledge;
  const resource = store.documents(id);
  const state = useResource(resource);
  const library = useResource(store.library(id));
  const jobs = useResource(store.processing(id));
  const uploads = useAtom(store.uploads.state);
  const [query, setQuery] = useQueryState("q");
  const [selected, setSelected] = useState<string[]>([]);
  const [processing, setProcessing] = useState(false);
  const [reprocess, setReprocess] = useState(false);
  const [message, setMessage] = useState("");
  const save = useSaveOperation();
  const docs = state.data ?? [];
  const shown = docs.filter((doc) => `${doc.title} ${doc.filename}`.includes(query.trim()));
  const pending = docs.filter(
    (doc) => !active(doc) && (doc.processing_state ?? "ready") !== "ready",
  );
  async function importDemo(preset: "travel" | "technical") {
    try {
      const result = await save.run(() => store.importDemo(id, preset, crypto.randomUUID()));
      setMessage(`已保存${result.length}份演示原件，请确认后手动处理。`);
    } catch (error) {
      save.setError(error);
    }
  }
  return (
    <section aria-label="库内文档">
      {adding && (
        <section
          id="knowledge-add-documents"
          aria-label="添加文档"
          className="my-4 space-y-4 rounded-panel border border-border p-4"
        >
          <p className="text-sm text-text-muted" id="knowledge-upload-help">
            支持UTF-8 Markdown、TXT，每份不超过128
            KiB。上传只保存原件，确认后再手动处理。上传列表可在全局浮层中查看。
          </p>
          <label className="block space-y-2 text-sm">
            选择文件（可多选）
            <Input
              type="file"
              accept=".md,.txt"
              multiple
              aria-describedby="knowledge-upload-help"
              onChange={(event) => {
                try {
                  const files = Array.from(event.target.files ?? []);
                  if (files.length) store.uploads.add(id, name, files);
                } catch (error) {
                  save.setError(error);
                }
                event.target.value = "";
              }}
            />
          </label>
          <Button
            disabled={!uploads.entries.some((e) => e.kb === id && e.status === "ready")}
            onClick={() => store.uploads.start(id)}
          >
            <Upload size={16} />
            上传文件
          </Button>
          <details className="text-sm text-text-muted">
            <summary className="cursor-pointer">没有现成文件？导入演示资料</summary>
            <p className="my-3">虚构样例按普通原件保存，重复导入不会新增相同内容。</p>
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                variant="outline"
                disabled={save.saving}
                onClick={() => void importDemo("travel")}
              >
                导入差旅样例（5 份）
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={save.saving}
                onClick={() => void importDemo("technical")}
              >
                导入技术样例（4 份）
              </Button>
            </div>
          </details>
        </section>
      )}
      <div className="my-4 flex flex-wrap items-center justify-between gap-3">
        <SearchInput
          label="查找库内文档"
          value={query}
          onChange={setQuery}
          placeholder="搜索文档名称…"
        />
        <Button
          variant="outline"
          disabled={save.saving || (!pending.length && !selected.length)}
          onClick={() => {
            setProcessing(true);
            save.clearError();
          }}
        >
          处理文档{selected.length ? `（已选${selected.length}）` : `（待处理${pending.length}）`}
        </Button>
      </div>
      <FailureNotice
        failure={save.failure}
        context={{
          operation: "mutation",
          resource: "knowledge",
          outcome: mutationOutcome(save.failure),
        }}
      />
      {message && (
        <p role="status" className="my-3 text-sm text-text-muted">
          {message}
        </p>
      )}
      <KnowledgeFeedback
        failure={state.failure}
        hasUsableData={state.data !== undefined}
        loading={state.loading}
        retry={() => resource.invalidate()}
      />
      {!!shown.length && (
        <div className="divide-y divide-border border-y border-border">
          {shown.map((doc) => (
            <div key={doc.id} className="flex min-w-0 items-start gap-3 py-4">
              <input
                type="checkbox"
                className="mt-1 size-4 shrink-0 accent-text"
                aria-label={`选择${doc.filename}`}
                disabled={active(doc)}
                checked={selected.includes(doc.id)}
                onChange={(e) =>
                  setSelected((old) =>
                    e.target.checked ? [...old, doc.id] : old.filter((item) => item !== doc.id),
                  )
                }
              />
              <Link
                to={`/knowledge/${id}/documents/${doc.id}`}
                className="flex min-w-0 flex-1 items-start gap-3 hover:bg-muted"
              >
                <ResourceIcon kind="document" size={20} className="text-text-muted" />
                <div className="min-w-0 flex-1">
                  <h3 className="break-words text-sm font-medium">{doc.title}</h3>
                  <p className="mt-1 break-words text-xs text-text-muted">
                    {doc.filename} · {doc.chunk_count}个片段 · {(doc.size / 1024).toFixed(1)} KiB
                  </p>
                  <p className="mt-1 text-xs text-text-muted">
                    {processingLabels[doc.processing_state ?? "ready"]} ·{" "}
                    {doc.keyword_ready !== false && doc.chunk_count ? "关键词可用" : "尚不可检索"}
                    {doc.vector_ready && " · 已建向量"}
                  </p>
                  {doc.processing_error && (
                    <p className="mt-2 break-words text-xs text-danger">{doc.processing_error}</p>
                  )}
                </div>
                <ChevronRight size={16} className="shrink-0 text-text-muted" />
              </Link>
              {["failed", "interrupted"].includes(doc.processing_state ?? "") && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setSelected([doc.id]);
                    setReprocess(false);
                    save.clearError();
                    setProcessing(true);
                  }}
                >
                  重试处理
                </Button>
              )}
            </div>
          ))}
        </div>
      )}
      {shown.length === 0 && !state.loading && !state.error && (
        <EmptyState
          icon={<ResourceIcon kind="document" size={28} />}
          text={query ? "没有匹配的文档" : "这个知识库还没有文档"}
          description={query ? "更换名称，或清除搜索。" : "添加并上传原件，确认后点击“处理文档”。"}
          onReset={query ? () => setQuery("") : undefined}
        />
      )}
      <KnowledgeFeedback
        failure={jobs.failure}
        loading={jobs.loading}
        hasUsableData={jobs.data !== undefined}
        retry={() => store.processing(id).invalidate()}
      />
      {!!jobs.data?.length && (
        <details className="mt-6 text-sm">
          <summary className="cursor-pointer font-medium">
            处理记录（最近{jobs.data.length}批）
          </summary>
          <div className="mt-3 space-y-4">
            {jobs.data.map((batch) => (
              <section key={batch.id} className="border-b border-border pb-3">
                <p>
                  {new Date(batch.created_at).toLocaleString("zh-CN")} · 已完成
                  {batch.items.filter((i) => i.status === "succeeded").length}/{batch.items.length}
                </p>
                <ul className="mt-2 space-y-1 text-xs text-text-muted">
                  {batch.items.map((item) => (
                    <li key={item.id} className="break-words">
                      {item.filename}：
                      {(
                        {
                          queued: "排队中",
                          running: "处理中",
                          succeeded: "完成",
                          failed: "失败",
                          cancelled: "取消",
                          interrupted: "中断",
                        } as Record<string, string>
                      )[item.status] ?? item.status}
                      {item.error && ` · ${item.error}`}
                    </li>
                  ))}
                </ul>
                {["queued", "running"].includes(batch.status) && (
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={save.saving}
                    onClick={async () => {
                      try {
                        await save.run(() => store.cancelProcessing(id, batch.id));
                      } catch (error) {
                        save.setError(error);
                      }
                    }}
                  >
                    取消未完成项
                  </Button>
                )}
              </section>
            ))}
          </div>
        </details>
      )}
      {processing && library.data && (
        <KnowledgeProcessing
          library={library.data}
          documents={docs}
          selected={selected}
          reprocess={reprocess}
          onReprocessChange={setReprocess}
          onClose={() => setProcessing(false)}
          onSubmitted={(count) => {
            setMessage(`已提交${count}份文档，后台处理会继续，可离开页面。`);
            setSelected([]);
            setProcessing(false);
            setReprocess(false);
          }}
        />
      )}
    </section>
  );
}
