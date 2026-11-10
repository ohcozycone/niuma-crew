import type { ExecutionAction, ExecutionTrace } from "@/lib/api/execution";
import { Button } from "@/components/ui/Button";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/Table";
import { actionTitle } from "./executionPresentation";
import {
  asRecord,
  elapsedSeconds,
  formatCount,
  modelUsage,
  percentage,
  tokenCount,
} from "./executionMetrics";

export function ExecutionConsumption({
  data,
  onSelectAction,
}: {
  data: ExecutionTrace;
  onSelectAction: (id: string) => void;
}) {
  const runTime = elapsedSeconds(data.run.started_at, data.run.finished_at);
  const totalTokens = tokenCount(asRecord(data.run.usage).total_tokens);
  return (
    <section aria-label="各阶段消耗" className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold">各阶段消耗</h2>
        <span className="text-xs text-text-muted">
          {data.actions.total === data.actions.items.length
            ? "本次执行全部步骤"
            : `当前页 ${data.actions.items.length} / ${data.actions.total} 个步骤`}
        </span>
      </div>
      <div className="overflow-x-auto rounded-control border border-border">
        <Table className="min-w-[760px] table-auto">
          <TableHeader>
            <TableRow>
              {[
                "执行步骤",
                "耗时 / 整轮占比",
                "输入 Token",
                "输出 Token",
                "其中思考",
                "总 Token / 整轮占比",
              ].map((label) => (
                <TableHead key={label}>{label}</TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.actions.items.map((action) => {
              const usage = modelUsage(action);
              const duration = elapsedSeconds(action.started_at, action.finished_at);
              const failed = action.status === "failed" || !!action.error_code;
              const model = action.kind === "model_call";
              return (
                <TableRow key={action.id} className={failed ? "bg-danger-bg" : undefined}>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="xs"
                      aria-label={`查看步骤 ${action.sequence} 的证据`}
                      className={`h-auto max-w-full whitespace-normal text-left ${failed ? "text-danger" : ""}`}
                      onClick={() => onSelectAction(action.id)}
                    >
                      {action.sequence}. {actionTitle(action)}
                      {failed ? " · 失败" : ""}
                    </Button>
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {duration != null
                      ? `${duration.toFixed(1)} 秒`
                      : action.finished_at
                        ? "未记录"
                        : "尚未结束"}
                    <Share value={percentage(duration, runTime)} />
                  </TableCell>
                  {[usage.input, usage.output, usage.reasoning].map((value, index) => (
                    <TableCell key={index} className="tabular-nums">
                      {model ? formatCount(value) : "—"}
                    </TableCell>
                  ))}
                  <TableCell className="tabular-nums">
                    {model ? formatCount(usage.total) : "—"}
                    {model && <Share value={percentage(usage.total, totalTokens)} />}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
      <p className="text-xs leading-6 text-text-muted">
        Token
        按模型调用归属，思考已包含在输出中；工具返回的内容在后续模型请求中计入输入。步骤耗时可能重叠，占比不累加。未报告用量不按
        0 计算。
      </p>
    </section>
  );
}
function Share({ value }: { value?: string }) {
  return value ? <span className="ml-2 text-xs text-text-muted">{value}</span> : null;
}

export function ExecutionBudgetEvidence({
  action,
  data,
}: {
  action: ExecutionAction;
  data: ExecutionTrace;
}) {
  if (action.kind !== "model_call") return null;
  const usage = modelUsage(action);
  const limit = tokenCount(action.metrics?.output_limit);
  const exhausted =
    action.error_code === "output_limit_exceeded" &&
    limit != null &&
    limit > 0 &&
    usage.output != null &&
    usage.output >= limit;
  const remaining =
    usage.output != null && usage.reasoning != null && usage.output >= usage.reasoning
      ? usage.output - usage.reasoning
      : undefined;
  const time = elapsedSeconds(action.started_at, action.finished_at);
  return (
    <div className="space-y-2">
      {exhausted && (
        <p className="text-sm font-medium text-danger">
          输出预算已耗尽
          {usage.reasoning != null && (
            <span className="ml-3 text-xs font-normal text-text">
              优先核对本步骤的思考与输出预算配置
            </span>
          )}
        </p>
      )}
      <dl className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
        {[
          [
            "请求输出上限",
            limit != null
              ? `${formatCount(limit)} Token（${action.metrics?.output_limit_field}）`
              : "未采集",
          ],
          ["实际输出", formatCount(usage.output)],
          [
            "其中思考",
            usage.reasoning != null
              ? `${formatCount(usage.reasoning)}${percentage(usage.reasoning, usage.output) ? `（${percentage(usage.reasoning, usage.output)}）` : ""}`
              : "未报告",
          ],
          ...(remaining != null ? [["非思考输出（差值）", formatCount(remaining)]] : []),
          [
            "步骤耗时",
            time != null
              ? `${time.toFixed(1)} 秒${percentage(time, elapsedSeconds(data.run.started_at, data.run.finished_at)) ? `（整轮 ${percentage(time, elapsedSeconds(data.run.started_at, data.run.finished_at))}）` : ""}`
              : "未记录",
          ],
          [
            "步骤总 Token",
            usage.total != null
              ? `${formatCount(usage.total)}${percentage(usage.total, tokenCount(asRecord(data.run.usage).total_tokens)) ? `（整轮 ${percentage(usage.total, tokenCount(asRecord(data.run.usage).total_tokens))}）` : ""}`
              : "未报告",
          ],
        ].map(([label, value]) => (
          <div key={label}>
            <dt className="text-xs text-text-muted">{label}</dt>
            <dd className="mt-1 tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>
      <details className="text-xs leading-6 text-text-muted">
        <summary>
          计算口径与证据来源
          {action.safe_details.purpose === "summary" ? " · 摘要触发依据未采集" : ""}
        </summary>
        <p className="mt-2">
          用量来源：
          {action.metrics?.usage_source === "response" ? "已保存的模型响应" : "步骤用量记录"}
          ；输出上限来自已保存的实际请求。非思考输出为用量差值，不代表完整有效正文。预算耗尽判断仅在错误码、请求上限与实际输出相互印证时展示，不等于已确认全部根因。
        </p>
        {action.safe_details.purpose === "summary" && <p>尚不能判断此次摘要是否必要。</p>}
      </details>
    </div>
  );
}
