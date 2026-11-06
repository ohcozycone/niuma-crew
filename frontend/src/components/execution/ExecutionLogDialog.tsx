import { useEffect, useState } from "react";

import { Check, CircleAlert, LoaderCircle } from "lucide-react";
import { useIdentity } from "@/state/auth/useIdentity";
import { identityKey } from "@/lib/identity";
import { executionTrace, type ExecutionTrace, type ExecutionAction } from "@/lib/api/execution";

import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/Dialog";
import { ExecutionOverview } from "./ExecutionOverview";
import { ExecutionConsumption } from "./ExecutionConsumption";

import { ExecutionActionDetails } from "./ExecutionActionDetails";
import { ExecutionFailures, ExecutionEvents } from "./ExecutionFailures";
import { actionTitle as title, failedActions } from "./executionPresentation";
import { JsonInspector } from "@/components/ui/JsonInspector";
import { Button } from "@/components/ui/Button";
import { FailureNotice } from "@/components/failure/FailureNotice";
import { useFailureState } from "@/state/shared/useFailureState";

const states: Record<string, string> = {
  queued: "排队中",
  running: "执行中",
  cancelling: "取消中",
  succeeded: "已完成",
  failed: "失败",
  cancelled: "已取消",
  interrupted: "已中断",
  unknown: "结果未确认",
};
const active = (status: string) => ["queued", "running", "cancelling"].includes(status);
function duration(action: ExecutionAction) {
  return action.finished_at
    ? `${Math.max(0, (Date.parse(action.finished_at) - Date.parse(action.started_at)) / 1000).toFixed(1)} 秒`
    : "尚未结束";
}
const JsonText = JsonInspector;

export type ExecutionLogTarget =
  | { conversationId: string; responseId?: string }
  | { agentId: string; batchId: string; caseId: string };

export function ExecutionLogDialog({
  target,
  onClose,
}: {
  target: ExecutionLogTarget | null;
  onClose: () => void;
}) {
  const identity = useIdentity();
  return (
    <Dialog
      open={!!target}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent size="workspace" className="gap-0" aria-describedby={undefined}>
        <DialogHeader className="border-b border-border px-4 py-4 pr-12 sm:px-6 sm:pr-14">
          <DialogTitle>执行日志</DialogTitle>
        </DialogHeader>
        {target && (
          <TraceContent
            key={`${identityKey(identity)}:${JSON.stringify(target)}`}
            target={target}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function TraceContent({ target }: { target: ExecutionLogTarget }) {
  const id = "conversationId" in target ? target.conversationId : target.agentId;
  const batchId = "batchId" in target ? target.batchId : undefined;
  const caseId = "caseId" in target ? target.caseId : undefined;
  const [responseId, setResponseId] = useState(
    "responseId" in target ? target.responseId : undefined,
  );
  const [actionId, setActionId] = useState("");
  const [offset, setOffset] = useState(0);
  const base =
    batchId && caseId
      ? `evaluations/${batchId}/cases/${caseId}`
      : responseId
        ? `conversations/${id}/responses/${responseId}`
        : `conversations/${id}`;
  const [data, setData] = useState<ExecutionTrace | null>(null);
  const [revision, setRevision] = useState(0);
  const { failure, setError } = useFailureState();
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function load() {
      try {
        const value = await executionTrace(base, offset, actionId, controller.signal);
        if (controller.signal.aborted) return;
        setData(value);
        setError("");
        const failed =
          !actionId && offset === 0
            ? failedActions(value).find(
                (item) =>
                  item.id !== value.selected?.id &&
                  value.selected?.status !== "failed" &&
                  !value.selected?.error_code,
              )
            : undefined;
        if (failed && value.selected?.id !== failed.id) setActionId(failed.id);
        if (active(value.run.status)) timer = setTimeout(load, 2500);
      } catch (error) {
        if (!controller.signal.aborted) {
          setData(null);
          setError(error);
        }
      }
    }
    void load();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [base, offset, actionId, revision, setError]);
  const selected = data?.selected;
  const ready = selected && (!actionId || selected.id === actionId);
  const artifactBase =
    data?.run.origin_kind === "conversation"
      ? `conversations/${id}/responses/${data.run.id}`
      : base;
  function changePage(next: number) {
    setData(null);
    setOffset(next);
    setActionId("");
  }
  function selectAttempt(next: string) {
    setData(null);
    setResponseId(next);
    setActionId("");
    setOffset(0);
  }
  return (
    <div className="mx-2 my-2 min-h-0 min-w-0 space-y-4 overflow-y-auto overscroll-contain px-2 py-3 [scrollbar-gutter:stable] sm:px-4">
      <FailureNotice
        failure={failure}
        context={{ operation: "initial-read", resource: "conversation" }}
        actions={[{ label: "重新加载", kind: "retry", onClick: () => setRevision((n) => n + 1) }]}
      />
      {!data ? (
        !failure && (
          <p role="status" className="py-8 text-sm text-text-muted">
            正在读取执行记录…
          </p>
        )
      ) : (
        <>
          <ExecutionOverview
            data={data}
            conversationId={!batchId ? id : undefined}
            onRefresh={() => setRevision((n) => n + 1)}
          />
          <ExecutionFailures data={data} onSelectAction={setActionId} />
          {!!data.actions.items.length && (
            <ExecutionConsumption data={data} onSelectAction={setActionId} />
          )}
          {data.context && (
            <div className="space-y-2 text-sm">
              <div className="flex flex-wrap items-center gap-3 text-xs text-text-muted">
                <span>
                  对话交付：
                  {
                    (
                      { accepted: "已保存", failed: "保存失败", pending: "待处理" } as Record<
                        string,
                        string
                      >
                    )[data.context.delivery.status]
                  }
                  {data.context.delivery.error_code ? ` · ${data.context.delivery.error_code}` : ""}
                </span>
                {data.run.started_at && (
                  <time>{new Date(data.run.started_at).toLocaleString("zh-CN")}</time>
                )}
                {data.context.attempts.length > 1 && (
                  <nav aria-label="本题执行尝试" className="flex flex-wrap gap-3">
                    {data.context.attempts.map((attempt) => (
                      <button
                        type="button"
                        key={attempt.id}
                        aria-pressed={attempt.id === data.run.id}
                        className="underline aria-pressed:font-medium"
                        onClick={() => selectAttempt(attempt.id)}
                      >
                        {attempt.id === data.run.id ? "当前尝试" : `尝试 ${attempt.id}`} ·{" "}
                        {states[attempt.status] || attempt.status}
                      </button>
                    ))}
                  </nav>
                )}
              </div>
              {data.context.delivery.content && (
                <details>
                  <summary className="cursor-pointer text-text-muted">已保存的交付正文</summary>
                  <div className="mt-2">
                    <JsonText value={data.context.delivery.content} />
                  </div>
                </details>
              )}
            </div>
          )}
          <div className="grid min-w-0 gap-5 lg:grid-cols-[16rem_minmax(0,1fr)]">
            <nav
              aria-label="执行路径"
              className="min-w-0 lg:sticky lg:top-0 lg:self-start lg:border-r lg:border-border lg:pr-4"
            >
              <h2 className="mb-3 text-sm font-medium">执行路径</h2>
              {!data.actions.items.length && (
                <p className="py-6 text-sm text-text-muted">尚未产生动作记录。</p>
              )}
              <ol className="max-h-60 space-y-1 overflow-auto lg:max-h-[calc(100dvh-17rem)]">
                {data.actions.items.map((action) => (
                  <li
                    key={action.id}
                    className={action.parent_action_id ? "ml-4 border-l border-border pl-2" : ""}
                  >
                    <button
                      aria-current={selected?.id === action.id ? "step" : undefined}
                      onClick={() => setActionId(action.id)}
                      className="flex w-full min-w-0 items-start gap-2 rounded-control px-3 py-3 text-left hover:bg-muted aria-[current=step]:bg-selected"
                    >
                      <span
                        className={`mt-0.5 shrink-0 ${action.status === "failed" || action.error_code ? "text-danger" : "text-text-muted"}`}
                      >
                        {active(action.status) ? (
                          <LoaderCircle
                            size={16}
                            className="animate-spin motion-reduce:animate-none"
                          />
                        ) : action.status === "succeeded" ? (
                          <Check size={16} />
                        ) : (
                          <CircleAlert size={16} />
                        )}
                      </span>
                      <span className="min-w-0">
                        <span className="block break-all text-sm font-medium">
                          {action.sequence}. {title(action)}
                        </span>
                        <span
                          className={`mt-1 block text-xs ${action.status === "failed" || action.error_code ? "text-danger" : "text-text-muted"}`}
                        >
                          {states[action.status] || action.status} · {duration(action)}
                          {action.error_code ? ` · ${action.error_code}` : ""}
                          {action.safe_details.executed === false ? " · 未执行" : ""}
                          {action.safe_details.usage &&
                          typeof action.safe_details.usage === "object" &&
                          "total_tokens" in action.safe_details.usage &&
                          typeof action.safe_details.usage.total_tokens === "number"
                            ? ` · ${action.safe_details.usage.total_tokens.toLocaleString()} token`
                            : ""}
                        </span>
                      </span>
                    </button>
                  </li>
                ))}
              </ol>
              {selected && !data.actions.items.some((item) => item.id === selected.id) && (
                <div className="mt-3 border-t border-border pt-3">
                  <p className="mb-2 text-xs text-text-muted">已定位步骤（当前分页之外）</p>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-auto whitespace-normal text-left"
                    onClick={() => setActionId(selected.id)}
                  >
                    步骤 {selected.sequence} · {title(selected)}
                  </Button>
                </div>
              )}
              {data.actions.total > 100 && (
                <div className="mt-3 flex items-center justify-between text-xs">
                  <Button
                    variant="ghost"
                    size="xs"
                    disabled={!offset}
                    onClick={() => changePage(Math.max(0, offset - 100))}
                  >
                    上一页
                  </Button>
                  <span>
                    {Math.floor(offset / 100) + 1} / {Math.ceil(data.actions.total / 100)}
                  </span>
                  <Button
                    variant="ghost"
                    size="xs"
                    disabled={offset + 100 >= data.actions.total}
                    onClick={() => changePage(offset + 100)}
                  >
                    下一页
                  </Button>
                </div>
              )}
            </nav>
            <section aria-label="动作详情" className="min-w-0">
              {!ready ? (
                <p role="status" className="py-8 text-sm text-text-muted">
                  {data.actions.total
                    ? "正在读取动作…"
                    : active(data.run.status)
                      ? "执行开始后可在此查看详情。"
                      : "本次执行未产生步骤记录。"}
                </p>
              ) : (
                <>
                  <div className="mb-3 flex flex-wrap items-baseline gap-2">
                    <h2 className="text-base font-semibold">{title(selected)}</h2>
                    <span className="break-all text-xs text-text-muted">
                      {selected.action_key} · {states[selected.status] || selected.status}
                    </span>
                  </div>
                  <ExecutionActionDetails
                    key={selected.id}
                    action={selected}
                    base={artifactBase}
                    conversationId={!batchId ? id : undefined}
                  />
                </>
              )}
            </section>
          </div>
          {!!data.logs?.items.length && (
            <details>
              <summary className="text-sm text-text-muted">
                运行事件（{data.logs.items.length}）
              </summary>
              <p className="mt-2 text-xs text-text-muted">
                按本次执行收集的程序事件，用于核对时序、异常类型和源码位置；有关联的错误已在上方定位。最多保留最近{" "}
                {data.logs.limit} 条。
              </p>
              <ExecutionEvents items={data.logs.items} />
            </details>
          )}
        </>
      )}
    </div>
  );
}
