import type { ExecutionTrace } from "@/lib/api/execution";
import { Button } from "@/components/ui/Button";
import { actionTitle, failedActions, isErrorEvent } from "./executionPresentation";
import { ExecutionBudgetEvidence } from "./ExecutionConsumption";

type Event = NonNullable<ExecutionTrace["logs"]>["items"][number];

export function ExecutionFailures({
  data,
  onSelectAction,
}: {
  data: ExecutionTrace;
  onSelectAction: (id: string) => void;
}) {
  const failures = failedActions(data);
  const events = (data.logs?.items ?? []).filter(
    (line) => isErrorEvent(line) && line.event !== "execution.finished",
  );
  const delivery = data.context?.delivery;
  const hasRunError = !!data.run.error_code || ["failed", "interrupted"].includes(data.run.status);
  if (!hasRunError && !failures.length && !events.length && delivery?.status !== "failed")
    return null;
  const actions = [...data.actions.items, ...failures, ...(data.selected ? [data.selected] : [])];
  const unknown = events.filter((event) => !event.action_key);
  const unloaded = events.filter(
    (event) =>
      event.action_key && !actions.some((action) => action.action_key === event.action_key),
  );
  return (
    <section
      aria-label="错误定位"
      className="space-y-3 rounded-panel border border-border bg-danger-bg p-4"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold text-danger">错误定位</h2>
        {hasRunError && (
          <code className="break-all text-xs text-danger">
            {data.run.error_code || data.run.status}
          </code>
        )}
      </div>
      {delivery?.status === "failed" && (
        <p className="break-all text-sm text-danger">
          回复保存失败：{delivery.error_code || "未提供错误码"}
          。这是交付阶段的错误，执行状态单独显示。
        </p>
      )}
      {failures.map((action) => {
        const related = events.filter((event) => event.action_key === action.action_key);
        return (
          <div key={action.id} className="space-y-2">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <Button
                variant="ghost"
                size="sm"
                className="h-auto min-h-8 max-w-full justify-start whitespace-normal text-left [overflow-wrap:anywhere]"
                onClick={() => onSelectAction(action.id)}
              >
                定位步骤 {action.sequence} · {actionTitle(action)}
              </Button>
              <p className="break-all text-xs text-danger">
                {action.action_key} · {action.error_code || "步骤失败，未记录错误码"}
              </p>
            </div>
            <ExecutionBudgetEvidence action={action} data={data} />
            {related.length > 0 && <ExecutionEvents items={related} />}
          </div>
        );
      })}
      {events
        .filter(
          (event) =>
            event.action_key &&
            !failures.some((action) => action.action_key === event.action_key) &&
            actions.some((action) => action.action_key === event.action_key),
        )
        .map((event, index) => {
          const action = actions.find((item) => item.action_key === event.action_key)!;
          return (
            <div key={index}>
              <Button
                size="sm"
                variant="ghost"
                className="h-auto min-h-8 max-w-full justify-start whitespace-normal text-left [overflow-wrap:anywhere]"
                onClick={() => onSelectAction(action.id)}
              >
                定位步骤 {action.sequence} · {actionTitle(action)}
              </Button>
              <ExecutionEvents items={[event]} />
            </div>
          );
        })}
      {unknown.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-xs font-medium">执行级事件（未关联具体步骤）</h3>
          <ExecutionEvents items={unknown} />
        </div>
      )}
      {unloaded.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-xs font-medium">步骤尚未载入的异常事件</h3>
          <ExecutionEvents items={unloaded} />
        </div>
      )}
      {hasRunError && !failures.length && !events.length && (
        <p className="text-sm text-text-muted">
          当前记录没有关联到具体失败步骤，无法确定错误发生位置。
        </p>
      )}
      {failures.length > 1 && !events.some((event) => !!event.action_key) && (
        <p className="text-xs text-text-muted">多个步骤标记为失败，当前事件未指明最初故障点。</p>
      )}
      {data.failures && data.failures.total > failures.length && (
        <p className="text-xs text-text-muted">
          共 {data.failures.total} 个失败步骤，此处展示前 {failures.length}{" "}
          个；其他步骤可从执行路径分页查看。
        </p>
      )}
    </section>
  );
}

export function ExecutionEvents({ items }: { items: Event[] }) {
  return (
    <ol className="divide-y divide-border">
      {items.map((line, index) => (
        <li key={index} className="space-y-1 py-2 text-xs [overflow-wrap:anywhere]">
          <p className={isErrorEvent(line) ? "font-medium text-danger" : "font-medium"}>
            {line.event}
            {line.error_code ? ` · ${line.error_code}` : ""}
            {line.error_type ? ` · ${line.error_type}` : ""}
          </p>
          <p className="text-text-muted">
            <time dateTime={line.time}>{new Date(line.time).toLocaleTimeString("zh-CN")}</time> ·{" "}
            {line.level}
            {line.action_key ? ` · ${line.action_key}` : " · 执行级"}
          </p>
          {line.source && <p className="font-mono">事件记录位置：{line.source}</p>}
          {line.frames && (
            <details open={isErrorEvent(line)}>
              <summary>异常调用位置</summary>
              <pre className="mt-2 whitespace-pre-wrap font-mono leading-6 [overflow-wrap:anywhere]">
                {line.frames}
              </pre>
            </details>
          )}
        </li>
      ))}
    </ol>
  );
}
