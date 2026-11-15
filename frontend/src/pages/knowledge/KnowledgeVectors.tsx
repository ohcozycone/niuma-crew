import { FailureNotice } from "@/components/failure/FailureNotice";
import { mutationOutcome } from "@/lib/failures/resolve";
import { useState } from "react";
import { Database, Settings2 } from "lucide-react";
import { Link, useSearchParams } from "react-router";
import { ConfirmActionDialog } from "@/components/common/ConfirmActionDialog";
import { ModelConnections } from "@/components/configuration/ModelConnections";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { FormField } from "@/components/common/FormField";
import { SelectField } from "@/components/ui/SelectField";
import { useIdentity } from "@/state/auth/useIdentity";
import { useWorkspaceData } from "@/state/workspace/useWorkspaceData";
import { useAtom, useResource } from "@/state/shared/useResource";
import { KnowledgeFeedback } from "./KnowledgeLibraries";

export const vectorStatusLabels = {
  not_built: "尚未建立向量索引",
  ready: "向量索引可用",
  partial: "部分文件向量可用，其余文件只参与关键词检索",
  outdated: "资料或模型配置已变化，请重建向量索引",
  unavailable: "向量连接已停用，请检查连接或更换模型",
};

const vectorJobLabels = {
  queued: "排队中",
  running: "构建中",
  succeeded: "已完成",
  failed: "失败",
  cancelled: "已取消",
  interrupted: "已中断",
};

export function KnowledgeVectors({ id }: { id: string }) {
  const [params] = useSearchParams();
  const store = useWorkspaceData().knowledge;
  const library = useResource(store.library(id));
  const documents = useResource(store.documents(id));
  const jobsResource = store.vectorJobs(id);
  const jobs = useResource(jobsResource);
  const operation = useAtom(store.vectorOperations)[id];
  const busy = operation?.busy ?? false;
  const failure = operation?.failure ?? null;
  const activeJob = jobs.data?.find((job) => job.status === "queued" || job.status === "running");
  const latest = activeJob ?? jobs.data?.[0];
  const retryable = latest && ["failed", "cancelled", "interrupted"].includes(latest.status);
  const eligible = (documents.data ?? []).filter(
    (doc) => doc.chunk_count > 0 && doc.keyword_ready !== false,
  ).length;
  const pending = (documents.data ?? []).length - eligible;
  const connections = store.embeddingConnections();
  const options = useResource(connections);
  const { permissions } = useIdentity();
  const writable = permissions.includes("knowledge:manage");
  const [managing, setManaging] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [selected, setSelected] = useState("");
  const [message, setMessage] = useState("");
  const choices = options.data ?? [];
  const preferred =
    operation?.request?.connectionId ||
    selected ||
    latest?.connection_id ||
    library.data?.vector_connection_id;
  const connectionId = choices.find((item) => item.id === preferred)?.id ?? choices[0]?.id ?? "";
  async function run(action: "build" | "clear" | "cancel") {
    if (!writable || busy) return;
    setMessage("");
    try {
      if (action === "clear") {
        await store.clearVectors(id);
        setClearing(false);
        setMessage("向量索引已移除，文档和关键词索引保留。");
      } else if (action === "cancel" && activeJob) {
        await store.cancelVectors(id, activeJob.id);
      } else if (action === "build") {
        await store.buildVectors(id, connectionId);
      }
    } catch {
      // The identity-scoped store keeps submission failures and retry keys when this page unmounts.
    }
  }
  return (
    <section aria-label="知识库向量索引" className="py-4">
      <h2 className="type-title">增加语义检索</h2>
      <p className="mt-2 mb-6 max-w-3xl text-sm leading-6 text-text-muted">
        为本库全部已分片文档建立向量索引，与文档页的勾选无关。保留已有分片和关键词索引，不会重复分片。
      </p>
      <div className="mb-6 flex flex-wrap items-start gap-3 border-y border-border py-4">
        <Database size={20} className="mt-0.5 shrink-0 text-text-muted" />
        <div className="min-w-0 space-y-1">
          <p className="text-sm font-medium" role="status">
            {vectorStatusLabels[library.data?.vector_status ?? "not_built"]}
          </p>
          <p className="text-xs text-text-muted tabular-nums">
            有效向量 {library.data?.vector_chunk_count ?? 0} / {library.data?.chunk_count ?? 0}{" "}
            个片段
            {library.data?.vector_connection_name && ` · ${library.data.vector_connection_name}`}
          </p>
        </div>
      </div>
      {!library.data?.chunk_count && (
        <p className="mb-4 text-sm text-text-muted">
          请先在“文档”页选择文件，分片并建立关键词索引。
        </p>
      )}
      <div className="max-w-3xl">
        <KnowledgeFeedback
          loading={documents.loading}
          failure={documents.failure}
          hasUsableData={documents.data !== undefined}
          retry={() => store.documents(id).invalidate()}
        />
        <KnowledgeFeedback
          loading={jobs.loading}
          failure={jobs.failure}
          hasUsableData={jobs.data !== undefined}
          retry={() => jobsResource.invalidate()}
        />
        <KnowledgeFeedback
          loading={options.loading}
          failure={options.failure}
          hasUsableData={options.data !== undefined}
          resource="connection"
          retry={() => connections.invalidate()}
        />
        <p className="my-4 text-sm text-text-muted" role="status">
          本次处理 {eligible} 篇已分片文档
          {pending > 0 ? `；另有 ${pending} 篇待分片，暂不参与` : ""}。
        </p>
        {!!choices.length && (
          <>
            <div className="mt-4 flex flex-wrap items-end gap-3">
              <FormField
                htmlFor="knowledge-embedding"
                label="向量模型"
                className="min-w-0 max-w-sm flex-1 basis-64"
              >
                <SelectField
                  options={choices.map((item) => ({
                    value: item.id,
                    label: `${item.name} · ${item.model_id}`,
                  }))}
                  displayValue={choices.find((item) => item.id === connectionId)?.name}
                  value={connectionId}
                  onValueChange={setSelected}
                  disabled={!writable || busy || !!activeJob || !!operation?.request}
                  id="knowledge-embedding"
                  className="w-full"
                />
              </FormField>
              <Button
                disabled={
                  !writable ||
                  busy ||
                  !!activeJob ||
                  !!operation?.request ||
                  jobs.loading ||
                  jobs.data === undefined ||
                  !!jobs.failure ||
                  !library.data?.chunk_count ||
                  !eligible ||
                  !connectionId
                }
                onClick={() => void run("build")}
              >
                {busy
                  ? "正在提交…"
                  : activeJob
                    ? "向量任务进行中"
                    : operation?.request
                      ? "等待确认上次提交"
                      : retryable
                        ? `重试向量构建（${eligible}篇）`
                        : library.data?.vector_connection_id
                          ? `更新向量索引（${eligible}篇）`
                          : `建立向量索引（${eligible}篇）`}
              </Button>
            </div>
            <p className="mt-2 text-xs leading-6 text-text-muted">
              任务在后台执行，可离开页面。相同模型配置与内容的已完成片段会复用缓存，只为未缓存片段调用向量服务；新索引全部成功后替换原索引。失败或中断后可手动重试。
            </p>
          </>
        )}
        {!options.loading && !options.error && !choices.length && (
          <p className="mt-3 text-sm text-text-muted">
            还没有可用的向量连接。
            {permissions.includes("model_connections:read") ? (
              <Button variant="ghost" size="sm" onClick={() => setManaging(true)}>
                添加向量模型
              </Button>
            ) : (
              "请管理员在“检索设置”页添加并启用向量模型。"
            )}
          </p>
        )}
        <div className="mt-3 flex flex-wrap gap-2">
          {permissions.includes("model_connections:read") && !!choices.length && (
            <Button variant="outline" size="sm" disabled={busy} onClick={() => setManaging(true)}>
              <Settings2 size={16} />
              管理向量模型
            </Button>
          )}
          <Button variant="ghost" size="sm" disabled={busy} onClick={() => store.refresh()}>
            刷新连接与索引状态
          </Button>
          {(library.data?.vector_connection_id || latest) && (
            <Button
              variant="ghost"
              size="sm"
              disabled={!writable || busy}
              onClick={() => setClearing(true)}
            >
              移除向量索引
            </Button>
          )}
        </div>
        {operation?.request && !busy && (
          <div className="mt-3 space-y-2">
            <p className="text-sm text-text-muted" role="status">
              提交结果尚未确认，再次提交会沿用原标识与模型，不会重复创建同一任务。
            </p>
            <Button
              variant="outline"
              size="sm"
              disabled={!writable}
              onClick={() => void run("build")}
            >
              确认上次提交
            </Button>
          </div>
        )}
        {latest && (
          <section aria-label="最近向量任务" className="mt-6 space-y-3 border-t border-border pt-4">
            <p className="text-sm font-medium" role="status">
              向量任务：{vectorJobLabels[latest.status]}
            </p>
            <div
              role="progressbar"
              aria-label="向量构建进度"
              aria-valuemin={0}
              aria-valuemax={Math.max(latest.chunk_count, 1)}
              aria-valuenow={latest.completed_count}
              aria-valuetext={`已完成 ${latest.completed_count} / ${latest.chunk_count} 个片段，其中复用 ${latest.reused_count} 个`}
              className="h-2 overflow-hidden rounded-full bg-border"
            >
              <div
                className="h-full bg-text-muted"
                style={{
                  width: `${Math.min(100, (latest.completed_count / Math.max(latest.chunk_count, 1)) * 100)}%`,
                }}
              />
            </div>
            <p className="text-xs text-text-muted tabular-nums">
              已完成 {latest.completed_count} / {latest.chunk_count} 个片段，其中复用{" "}
              {latest.reused_count} 个
            </p>
            {latest.error && <p className="break-words text-sm text-text-muted">{latest.error}</p>}
            {activeJob ? (
              <>
                <p className="text-xs text-text-muted">
                  后台处理会继续，可切换页面；现有有效索引仍可检索。
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!writable || busy}
                  onClick={() => void run("cancel")}
                >
                  取消向量任务
                </Button>
              </>
            ) : retryable ? (
              <p className="text-xs text-text-muted">
                原索引不受影响。重试会提交新任务，并复用已完成且仍有效的缓存。
              </p>
            ) : (
              <p className="text-xs text-text-muted">
                任务已完成，当前索引可用情况以上方索引状态为准。
              </p>
            )}
          </section>
        )}
        {(jobs.data?.length ?? 0) > 1 && (
          <details className="mt-4 text-sm">
            <summary className="cursor-pointer">
              向量任务记录（最近 {jobs.data!.length} 次）
            </summary>
            <ul className="mt-3 space-y-2 text-xs text-text-muted">
              {jobs.data!.map((job) => (
                <li key={job.id} className="break-words">
                  {new Date(job.created_at).toLocaleString("zh-CN")} · {vectorJobLabels[job.status]}{" "}
                  · 已完成 {job.completed_count}/{job.chunk_count}，复用 {job.reused_count}
                  {job.error && ` · ${job.error}`}
                </li>
              ))}
            </ul>
          </details>
        )}
        <FailureNotice
          failure={failure}
          context={{
            operation: "mutation",
            resource: "knowledge",
            outcome: mutationOutcome(failure),
          }}
        />
        {message && (
          <p className="mt-2 text-sm text-success" role="status">
            {message}
          </p>
        )}
      </div>
      {(library.data?.vector_status === "ready" || library.data?.vector_status === "partial") && (
        <Button
          className="mt-6"
          variant="outline"
          nativeButton={false}
          role="link"
          render={
            <Link
              to={`/knowledge/${id}?${new URLSearchParams({ ...Object.fromEntries(params), view: "search" })}`}
            />
          }
        >
          前往检索测试
        </Button>
      )}
      <Dialog open={managing} onOpenChange={setManaging}>
        <DialogContent size="wide">
          <DialogHeader>
            <DialogTitle>管理向量模型</DialogTitle>
          </DialogHeader>
          <ModelConnections capability="embedding" embedded onChanged={() => store.refresh()} />
          <DialogFooter>
            <Button variant="outline" onClick={() => setManaging(false)}>
              完成
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <ConfirmActionDialog
        open={clearing}
        onOpenChange={setClearing}
        title="移除当前知识库的向量索引？"
        description="确认后取消未完成的向量任务，并移除向量索引与片段向量缓存；文档原件与关键词索引继续保留，需要时可以重新建立。"
        confirmLabel="确认移除索引"
        busy={busy}
        onConfirm={() => void run("clear")}
      >
        <FailureNotice
          failure={failure}
          context={{
            operation: "mutation",
            resource: "knowledge",
            outcome: mutationOutcome(failure),
          }}
        />
      </ConfirmActionDialog>
    </section>
  );
}
