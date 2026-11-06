import type { ExecutionTrace } from "@/lib/api/execution";
import { failedActions } from "./executionPresentation";
import { Button } from "@/components/ui/Button";

const record = (value: unknown): Record<string, unknown> =>
  value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
const number = (value: unknown) =>
  typeof value === "number" ? value.toLocaleString("zh-CN") : "未提供";
const status: Record<string, string> = {
  succeeded: "已完成",
  failed: "失败",
  running: "执行中",
  queued: "排队中",
  cancelled: "已取消",
  interrupted: "已中断",
  cancelling: "取消中",
};

export function ExecutionOverview({
  data,
  conversationId,
  onRefresh,
}: {
  data: ExecutionTrace;
  conversationId?: string;
  onRefresh: () => void;
}) {
  const usage = record(data.run.usage);
  const actions = data.actions.items;
  const failed = failedActions(data);
  const models = actions.filter((item) => item.kind === "model_call");
  const tools = actions.filter((item) => item.kind === "tool_call");
  const elapsed =
    data.run.started_at && data.run.finished_at
      ? `${Math.max(0, (Date.parse(data.run.finished_at) - Date.parse(data.run.started_at)) / 1000).toFixed(1)} 秒`
      : ["queued", "running", "cancelling"].includes(data.run.status)
        ? "尚未结束"
        : "未记录";
  return (
    <section aria-label="执行概况" className="space-y-3 border-b border-border pb-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="min-w-0 flex-1 text-base font-semibold [overflow-wrap:anywhere]">
          {data.context?.question || (conversationId ? "对话执行" : "考题执行")}
        </p>
        <div className="flex items-center gap-3">
          <span
            className={
              data.run.error_code || data.run.status === "failed"
                ? "text-sm text-danger"
                : "text-sm text-text-muted"
            }
          >
            {status[data.run.status] || data.run.status}
          </span>
          <Button size="sm" variant="ghost" onClick={onRefresh}>
            刷新日志
          </Button>
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
        <p className="min-w-0 text-xs text-text-muted [overflow-wrap:anywhere]">
          {data.configuration.agent_name && (
            <span className="mr-3 text-sm font-medium text-text">
              {data.configuration.agent_name}
            </span>
          )}
          {data.configuration.model_id} · 配置 v{data.configuration.agent_revision}
        </p>
        <dl aria-label="关联编号" className="flex flex-wrap gap-x-4 gap-y-2 text-xs">
          {[
            ["对话", conversationId],
            ["执行", data.run.id],
            ["提问", data.context?.input_message_id],
          ]
            .filter(([, value]) => !!value)
            .map(([label, value]) => (
              <div
                key={label}
                className="flex min-w-0 items-baseline gap-2 rounded-small bg-muted px-2 py-1"
              >
                <dt className="shrink-0 text-text-muted">{label}编号</dt>
                <dd className="min-w-0 select-all font-mono tabular-nums [overflow-wrap:anywhere]">
                  {value}
                </dd>
              </div>
            ))}
        </dl>
      </div>
      <dl className="flex flex-wrap gap-x-6 gap-y-3 text-sm">
        {[
          ["耗时", elapsed],
          ["输入 Token", number(usage.input_tokens)],
          ["输出 Token", number(usage.output_tokens)],
          ["总 Token", number(usage.total_tokens)],
          ["缓存命中", number(usage.cached_input_tokens)],
        ].map(([label, value]) => (
          <div key={label} className="flex items-baseline gap-2">
            <dt className="text-xs text-text-muted">{label}</dt>
            <dd className="tabular-nums font-medium">{value}</dd>
          </div>
        ))}
      </dl>
      <p className="text-xs text-text-muted">
        {data.actions.total === actions.length ? "本次执行" : "当前动作页"}：{models.length}{" "}
        次模型调用（含 {models.filter((item) => item.safe_details.purpose === "summary").length}{" "}
        次摘要） · {tools.length} 次工具申请 ·{" "}
        {tools.filter((item) => item.safe_details.executed === false).length} 次未执行 ·{" "}
        全部失败步骤：{data.failures?.total ?? failed.length}
      </p>
    </section>
  );
}
