import { mutationOutcome } from "@/lib/failures/resolve";
import { FailureNotice } from "@/components/failure/FailureNotice";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { ArrowLeft, Download, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { PageContainer } from "@/components/common/PageContainer";
import { PageHeading } from "@/components/common/PageHeading";
import { ConfirmActionDialog } from "@/components/common/ConfirmActionDialog";
import { safeReturnPath } from "@/lib/navigation";
import { originalKnowledgeUrl } from "@/lib/api/knowledge";
import { useWorkspaceData } from "@/state/workspace/useWorkspaceData";
import { useResource } from "@/state/shared/useResource";
import { useSaveOperation } from "@/state/editing/useSaveOperation";
import { KnowledgeFeedback } from "./KnowledgeLibraries";

export function KnowledgeDocumentPage({ kb, id }: { kb: string; id: string }) {
  const store = useWorkspaceData().knowledge;
  const resource = store.document(kb, id);
  const state = useResource(resource);
  const [params] = useSearchParams();
  const source = safeReturnPath(params.get("from"));
  const back = source.split("?")[0] === `/knowledge/${kb}` ? source : `/knowledge/${kb}`;
  const [confirm, setConfirm] = useState(false);
  const save = useSaveOperation();
  const navigate = useNavigate();
  const selected = state.data?.chunks.find((chunk) => chunk.id === params.get("chunk"));
  async function remove() {
    try {
      await save.run(() => store.remove(kb, id));
      navigate(`/knowledge/${kb}`);
    } catch (error) {
      save.setError(error);
    }
  }
  return (
    <PageContainer>
      <KnowledgeFeedback
        failure={state.failure}
        hasUsableData={state.data !== undefined}
        resource="document"
        returnTo={back}
        loading={state.loading}
        retry={() => resource.invalidate()}
      />
      {state.data && (
        <>
          <PageHeading
            title={state.data.title}
            description={`${state.data.filename} · ${state.data.chunk_count} 个片段 · ${(state.data.size / 1024).toFixed(1)} KiB`}
            actions={
              <>
                <Button
                  variant="ghost"
                  nativeButton={false}
                  role="link"
                  render={<Link to={back} />}
                >
                  <ArrowLeft size={16} />
                  返回知识库
                </Button>
                <Button
                  variant="outline"
                  nativeButton={false}
                  role="link"
                  render={<a href={originalKnowledgeUrl(kb, id)} download />}
                >
                  <Download size={16} />
                  下载原件
                </Button>
              </>
            }
          />
          {params.get("chunk") && !selected && (
            <p role="alert" className="my-4 text-sm text-danger">
              该来源片段不存在，请核对链接。
            </p>
          )}
          {selected && (
            <section
              aria-label="本次命中片段"
              className="my-6 rounded-panel border border-border bg-muted p-5"
            >
              <h2 className="type-title [overflow-wrap:anywhere]">命中片段 · {selected.locator}</h2>
              <p className="mt-3 max-w-prose whitespace-pre-wrap break-words text-sm leading-7">
                {selected.text}
              </p>
              <p className="mt-3 text-xs text-text-muted">
                对应下方固定正文的字符区间 [{selected.start}, {selected.end})
              </p>
            </section>
          )}
          <div className="my-6 flex flex-wrap items-center gap-4 text-xs text-text-muted">
            <span>原文快照 · {state.data.version.slice(0, 12)}</span>
            <span>上传时间 · {new Date(state.data.created_at).toLocaleString("zh-CN")}</span>
          </div>
          <article
            aria-label="固定文档原文"
            className="max-w-prose whitespace-pre-wrap break-words text-sm leading-8"
          >
            {state.data.document?.text ??
              "原件已保存，尚未完成正文处理。请返回知识库，确认后点击“处理文档”；也可以下载原件核对。"}
          </article>
          <details className="mt-8 border-t border-border pt-5 text-sm">
            <summary className="cursor-pointer font-medium">
              查看全部切片（{state.data.chunks.length}）
            </summary>
            <div className="mt-4 divide-y divide-border">
              {state.data.chunks.map((chunk, index) => (
                <section key={chunk.id} className="py-4">
                  <h3 className="text-sm font-medium [overflow-wrap:anywhere]">
                    {index + 1}. {chunk.locator}
                  </h3>
                  <p className="mt-1 text-xs text-text-muted">
                    正文区间 [{chunk.start}, {chunk.end})
                  </p>
                  <p className="mt-3 whitespace-pre-wrap break-words text-sm leading-7 text-text-muted">
                    {chunk.text}
                  </p>
                </section>
              ))}
            </div>
          </details>
          <div className="mt-10 flex flex-wrap items-center gap-3 border-t border-border pt-5">
            <Button variant="ghost" onClick={() => setConfirm(true)}>
              <Trash2 size={16} />
              移除文档
            </Button>
            <FailureNotice
              failure={save.failure}
              context={{
                operation: "mutation",
                resource: "knowledge",
                outcome: mutationOutcome(save.failure),
              }}
            />
          </div>
          <ConfirmActionDialog
            open={confirm}
            onOpenChange={setConfirm}
            title={`移除「${state.data.title}」？`}
            description="从当前知识库移除文档及其检索片段，确认后立即生效。其他文档继续保留。"
            confirmLabel="确认移除"
            busy={save.saving}
            onConfirm={() => void remove()}
          >
            {save.failure && (
              <FailureNotice
                failure={save.failure}
                context={{
                  operation: "mutation",
                  resource: "knowledge",
                  outcome: mutationOutcome(save.failure),
                }}
              />
            )}
          </ConfirmActionDialog>
        </>
      )}
    </PageContainer>
  );
}
