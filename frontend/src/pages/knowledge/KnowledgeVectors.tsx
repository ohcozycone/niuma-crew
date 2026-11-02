import { FailureNotice } from "@/components/failure/FailureNotice";
import { toFailure, mutationOutcome } from "@/lib/failures/resolve";
import type { Failure } from "@/lib/failures/types";
import { useRef, useState } from "react";
import { Settings2 } from "lucide-react";
import { ConfirmActionDialog } from "@/components/common/ConfirmActionDialog";
import { ModelConnections } from "@/components/configuration/ModelConnections";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
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

export function KnowledgeVectors({ id }: { id: string }) {
  const store = useWorkspaceData().knowledge;
  const library = useResource(store.library(id));
  const connections = store.embeddingConnections();
  const options = useResource(connections);
  const { permissions } = useIdentity();
  const [open, setOpen] = useState(false);
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
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setFailure(null);
    setMessage("");
    try {
      if (clear) await store.clearVectors(id);
      else await store.buildVectors(id, connectionId);
      if (clear) setClearing(false);
      setMessage(
        clear
          ? "向量索引已移除，文档和关键词索引保留。"
          : "向量索引已建立，可以选择“向量检索”查找资料。",
      );
    } catch (error) {
      setFailure(toFailure(error));
    } finally {
      lock.current = false;
      setBusy(false);
      // A lost response does not prove the server failed to publish the index.
      store.refresh();
    }
  }
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!lock.current) setOpen(next);
      }}
    >
      <DialogTrigger render={<Button variant="outline" size="sm" />}>
        <Settings2 size={16} />
        检索设置
      </DialogTrigger>
      <DialogContent size={managing ? "wide" : "standard"} showCloseButton={!busy}>
        <DialogHeader>
          <DialogTitle>检索设置</DialogTitle>
          <DialogDescription>
            BM25 可直接使用。建立向量索引后可使用向量与混合检索。
          </DialogDescription>
        </DialogHeader>
        {managing ? (
          <>
            <Button variant="ghost" size="sm" onClick={() => setManaging(false)}>
              返回索引设置
            </Button>
            <ModelConnections capability="embedding" embedded onChanged={() => store.refresh()} />
          </>
        ) : (
          <section aria-label="知识库向量索引">
            <h3 className="text-sm font-medium">向量索引</h3>
            <p className="mt-2 text-sm text-text-muted" role="status">
              {vectorStatusLabels[library.data?.vector_status ?? "not_built"]}
              {library.data?.vector_connection_name && ` · ${library.data.vector_connection_name}`}
            </p>
            <KnowledgeFeedback
              loading={options.loading}
              failure={options.failure}
              hasUsableData={options.data !== undefined}
              resource="connection"
              retry={() => connections.invalidate()}
            />
            {!!choices.length && (
              <>
                <div className="mt-4 flex flex-wrap items-end gap-3">
                  <FormField
                    htmlFor="knowledge-embedding"
                    label="向量模型"
                    className="min-w-0 flex-1 basis-64"
                  >
                    <SelectField
                      options={choices.map((item) => ({
                        value: item.id,
                        label: `${item.name} · ${item.model_id}`,
                      }))}
                      displayValue={choices.find((item) => item.id === connectionId)?.name}
                      value={connectionId}
                      onValueChange={setSelected}
                      disabled={busy}
                      id="knowledge-embedding"
                      className="w-fit"
                    />
                  </FormField>
                  <Button
                    disabled={busy || !library.data?.chunk_count || !connectionId}
                    onClick={() => void run(false)}
                  >
                    {busy
                      ? "正在处理索引…"
                      : library.data?.vector_connection_id
                        ? "重建向量索引"
                        : "建立向量索引"}
                  </Button>
                </div>
                <p className="mt-2 text-xs leading-6 text-text-muted">
                  建立索引会将当前库的文档片段发送给硅基流动。上传或删除文档后需重建；构建失败时保留原索引。处理期间请保持页面打开。
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
                  "请管理员在知识库的检索设置中添加并启用向量模型。"
                )}
              </p>
            )}
            <div className="mt-3 flex flex-wrap gap-2">
              {permissions.includes("model_connections:read") && !!choices.length && (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={busy}
                  onClick={() => setManaging(true)}
                >
                  管理向量模型
                </Button>
              )}
              <Button variant="ghost" size="sm" disabled={busy} onClick={() => store.refresh()}>
                刷新连接与索引状态
              </Button>
              {library.data?.vector_connection_id && (
                <Button variant="ghost" size="sm" disabled={busy} onClick={() => setClearing(true)}>
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
          </section>
        )}
        <DialogFooter>
          <Button variant="outline" disabled={busy} onClick={() => setOpen(false)}>
            完成
          </Button>
        </DialogFooter>
      </DialogContent>
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
    </Dialog>
  );
}
