import { FailureNotice } from "@/components/failure/FailureNotice";
import { toFailure, mutationOutcome } from "@/lib/failures/resolve";
import type { Failure } from "@/lib/failures/types";
import { useRef, useState } from "react";
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
import { useResource } from "@/state/shared/useResource";
import { useEditingRegistration } from "@/state/editing/useEditing";
import { KnowledgeFeedback } from "./KnowledgeLibraries";

export const vectorStatusLabels = {
  not_built: "尚未建立向量索引",
  ready: "向量索引可用",
  partial: "部分文件向量可用，其余文件只参与关键词检索",
  outdated: "资料或模型配置已变化，请重建向量索引",
  unavailable: "向量连接已停用，请检查连接或更换模型",
};

export function KnowledgeVectors({
  id,
  onBusyChange,
}: {
  id: string;
  onBusyChange: (busy: boolean) => void;
}) {
  const [params] = useSearchParams();
  const store = useWorkspaceData().knowledge;
  const library = useResource(store.library(id));
  const documents = useResource(store.documents(id));
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
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [message, setMessage] = useState("");
  const lock = useRef(false);
  const choices = options.data ?? [];
  const preferred = selected || library.data?.vector_connection_id;
  const connectionId = choices.find((item) => item.id === preferred)?.id ?? choices[0]?.id ?? "";
  useEditingRegistration({
    dirty: false,
    saving: busy,
    isSaving: () => lock.current,
    discard: () => {},
  });
  async function run(clear: boolean) {
    if (!writable || lock.current) return;
    lock.current = true;
    setBusy(true);
    onBusyChange(true);
    setFailure(null);
    setMessage("");
    try {
      if (clear) await store.clearVectors(id);
      else await store.buildVectors(id, connectionId);
      if (clear) setClearing(false);
      setMessage(
        clear
          ? "向量索引已移除，文档和关键词索引保留。"
          : "向量索引已建立，检索测试将自动使用关键词＋语义混合检索。",
      );
    } catch (error) {
      setFailure(toFailure(error));
    } finally {
      lock.current = false;
      setBusy(false);
      onBusyChange(false);
      // A lost response does not prove the server failed to publish the index.
      store.refresh();
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
                  disabled={!writable || busy}
                  id="knowledge-embedding"
                  className="w-full"
                />
              </FormField>
              <Button
                disabled={
                  !writable || busy || !library.data?.chunk_count || !eligible || !connectionId
                }
                onClick={() => void run(false)}
              >
                {busy
                  ? "正在处理索引…"
                  : library.data?.vector_connection_id
                    ? `更新向量索引（${eligible}篇）`
                    : `建立向量索引（${eligible}篇）`}
              </Button>
            </div>
            <p className="mt-2 text-xs leading-6 text-text-muted">
              每次建立或更新会将全部现有片段发送给向量模型重新编码，包括上次已处理的片段。构建失败时保留原索引，期间请保持页面打开。
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
          {library.data?.vector_connection_id && (
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
        {busy && (
          <p className="mt-2 text-sm text-text-muted" role="status">
            正在调用向量服务，文档较多时需要等待；原索引会在全部成功后替换。
          </p>
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
          disabled={busy}
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
        description="确认后立即移除向量索引；文档原件与关键词索引继续保留，需要时可以重新建立。"
        confirmLabel="确认移除索引"
        busy={busy}
        onConfirm={() => void run(true)}
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
