import { useIdentity } from "@/state/auth/useIdentity";
import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { ArrowLeft, Plus, Scissors, Upload } from "lucide-react";
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
import { KnowledgeFeedback } from "./KnowledgeLibraries";
import { KnowledgeSearch } from "./KnowledgeSearch";
import { KnowledgeSettings } from "./KnowledgeSettings";
import { KnowledgeChunkSettings } from "./KnowledgeChunkSettings";
import type { ChunkingRules } from "@/lib/api/knowledge";
import { KnowledgeVectors } from "./KnowledgeVectors";
import { KnowledgeDocumentList, isDocumentProcessing as active } from "./KnowledgeDocumentList";

export function KnowledgeLibrary({ id }: { id: string }) {
  const writable = useIdentity().permissions.includes("knowledge:manage");
  const store = useWorkspaceData().knowledge;
  const resource = store.library(id);
  const state = useResource(resource);
  const documents = useResource(store.documents(id));
  const jobs = useResource(store.processing(id));
  const uploads = useAtom(store.uploads.state);
  const [adding, setAdding] = useState(false);
  const [buildingVectors, setBuildingVectors] = useState(false);
  const [params, setParams] = useSearchParams();
  const requestedView = params.get("view");
  const view =
    requestedView === "search" || requestedView === "settings" ? requestedView : "documents";
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
            description={state.data.description || "上传资料，按需分片，再为已有片段增加语义检索。"}
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
                {writable && <KnowledgeSettings library={state.data} />}
                <Button
                  disabled={!writable || buildingVectors}
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
                    ? "收起上传"
                    : `上传文件${pendingUploads ? `（${pendingUploads}）` : ""}`}
                </Button>
              </>
            }
          />
          <PageTabs
            label="库内功能"
            items={[
              { value: "documents", label: "文档", disabled: buildingVectors },
              { value: "settings", label: "检索设置" },
              { value: "search", label: "检索测试", disabled: buildingVectors },
            ]}
            value={view}
            onValueChange={(next) => {
              if (buildingVectors) return;
              setParams((current) => {
                const copy = new URLSearchParams(current);
                copy.set("view", next);
                return copy;
              });
            }}
          >
            <TabsContent value="documents" keepMounted>
              <LibraryDocuments id={id} name={state.data.name} adding={adding} />
            </TabsContent>
            <TabsContent value="settings">
              <KnowledgeVectors id={id} onBusyChange={setBuildingVectors} />
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
  const writable = useIdentity().permissions.includes("knowledge:manage");
  const store = useWorkspaceData().knowledge;
  const resource = store.documents(id);
  const state = useResource(resource);
  const library = useResource(store.library(id));
  const jobs = useResource(store.processing(id));
  const uploads = useAtom(store.uploads.state);
  const [query, setQuery] = useQueryState("q");
  const [selection, setSelected] = useState<string[]>([]);
  const [adjusting, setAdjusting] = useState(false);
  const [confirmedRules, setConfirmedRules] = useState<ChunkingRules>();
  const request = useRef<{ id: string; signature: string } | null>(null);
  const processingLock = useRef(false);
  const [message, setMessage] = useState("");
  const save = useSaveOperation();
  const docs = state.data ?? [];
  const selected = selection.filter((item) => docs.some((doc) => doc.id === item && !active(doc)));
  const shown = docs.filter((doc) =>
    `${doc.title} ${doc.filename}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()),
  );
  const rules = confirmedRules ?? {
    chunk_size: library.data?.effective_chunk_size ?? 800,
    chunk_overlap: library.data?.effective_chunk_overlap ?? 120,
    min_section_chars: library.data?.effective_min_section_chars ?? 200,
  };
  const targets = docs.filter((doc) => selected.includes(doc.id));
  const reuse = targets.filter(
    (doc) =>
      doc.processing_reusable &&
      doc.processing_rules?.chunk_size === rules.chunk_size &&
      doc.processing_rules?.chunk_overlap === rules.chunk_overlap &&
      doc.processing_rules?.min_section_chars === rules.min_section_chars,
  ).length;
  const fresh = targets.filter((doc) => !doc.version).length;
  async function processDocuments(ids: string[]) {
    if (!ids.length || processingLock.current) return;
    processingLock.current = true;
    setMessage("");
    const signature = JSON.stringify([[...ids].sort(), rules]);
    if (request.current?.signature !== signature)
      request.current = { id: crypto.randomUUID(), signature };
    try {
      const batch = await save.run(() => store.process(id, request.current!.id, ids, rules));
      const reused = batch.items.filter((item) => item.status === "reused").length;
      setMessage(
        reused === batch.items.length && reused > 0
          ? `已复用 ${reused} 份文档的分片和关键词索引，无需重新处理。`
          : `已提交 ${batch.items.length} 份文档${reused ? `，其中 ${reused} 份已复用现有索引` : ""}。后台处理会继续，可离开页面。`,
      );

      setSelected([]);
      request.current = null;
    } catch (error) {
      save.setError(error);
    } finally {
      processingLock.current = false;
    }
  }
  async function importDemo(preset: "travel" | "technical") {
    try {
      const result = await save.run(() => store.importDemo(id, preset, crypto.randomUUID()));
      setMessage(`已添加 ${result.length} 份演示文档，选择后可分片并建立关键词索引。`);
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
            KiB。上传成功即加入列表；选择文件后可分片并建立关键词索引。上传列表可在全局浮层中查看。
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
      </div>
      <div className="mb-3 space-y-3">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-text-muted">
          <span>
            分片规则：{rules.chunk_size} 字符 · 重叠 {rules.chunk_overlap} · 合并阈值{" "}
            {rules.min_section_chars}
          </span>
          {writable && (
            <Button
              variant="ghost"
              size="sm"
              disabled={save.saving}
              onClick={() => setAdjusting(true)}
            >
              调整
            </Button>
          )}
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="space-y-1 text-xs text-text-muted">
            <p role="status" className="min-h-5 tabular-nums">
              <span className="font-medium text-text">已选 {selected.length} 份</span> ·{" "}
              {query ? `找到 ${shown.length} / ${docs.length} 份文档` : `共 ${docs.length} 份文档`}
              {selected.some((item) => !shown.some((doc) => doc.id === item)) &&
                "（含搜索外的选择）"}
            </p>
            <p className="tabular-nums">
              新建 {fresh} 份 · 复用 {reuse} 份 · 重新分片 {targets.length - fresh - reuse} 份
            </p>
          </div>
          <Button
            variant="outline"
            disabled={!writable || save.saving || !selected.length}
            onClick={() => void processDocuments(selected)}
          >
            <Scissors size={16} />
            {save.saving ? "正在提交…" : "分片并建关键词索引"}
          </Button>
        </div>
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
        <KnowledgeDocumentList
          id={id}
          documents={shown}
          selected={selected}
          writable={writable && !save.saving}
          onSelectionChange={setSelected}
          onRetry={(doc) => {
            setSelected([doc.id]);
            void processDocuments([doc.id]);
          }}
        />
      )}
      {shown.length === 0 && !state.loading && !state.error && (
        <EmptyState
          icon={<ResourceIcon kind="document" size={28} />}
          text={query ? "没有匹配的文档" : "这个知识库还没有文档"}
          description={
            query ? "更换名称，或清除搜索。" : "点击右上角“上传文件”，上传成功后会出现在这里。"
          }
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
            分片记录（最近{jobs.data.length}批）
          </summary>
          <div className="mt-3 space-y-4">
            {jobs.data.map((batch) => (
              <section key={batch.id} className="border-b border-border pb-3">
                <p>
                  {new Date(batch.created_at).toLocaleString("zh-CN")} · 已完成
                  {batch.items.filter((i) => ["succeeded", "reused"].includes(i.status)).length}/
                  {batch.items.length}
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
                          reused: "已复用",
                          failed: "失败",
                          cancelled: "取消",
                          interrupted: "中断",
                        } as Record<string, string>
                      )[item.status] ?? item.status}
                      {item.error && ` · ${item.error}`}
                    </li>
                  ))}
                </ul>
                {writable && ["queued", "running"].includes(batch.status) && (
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
      {adjusting && (
        <KnowledgeChunkSettings
          kb={id}
          rules={rules}
          document={targets[0]}
          onClose={() => setAdjusting(false)}
          onConfirm={(next) => {
            setConfirmedRules(next);
            setAdjusting(false);
            save.clearError();
          }}
        />
      )}
    </section>
  );
}
