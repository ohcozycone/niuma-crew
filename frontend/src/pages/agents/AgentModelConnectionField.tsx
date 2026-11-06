import { useFailureState } from "@/state/shared/useFailureState";
import { FailureNotice } from "@/components/failure/FailureNotice";
import { useEffect, useState } from "react";
import { ArrowUpRight, Check, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { SelectField } from "@/components/ui/SelectField";
import { loadModelConnections, type ModelConnection } from "@/lib/api/modelConnections";
import { cn } from "@/lib/utils";

export function AgentModelConnectionField({
  value,
  onChange,
  onReadinessChange,
}: {
  value: string | null;
  onChange: (id: string | null) => void;
  onReadinessChange?: (ready: boolean) => void;
}) {
  const [connections, setConnections] = useState<ModelConnection[]>([]);
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(true);
  const { failure, error, setError } = useFailureState();
  useEffect(() => {
    const controller = new AbortController();
    loadModelConnections(controller.signal)
      .then((items) => {
        if (!controller.signal.aborted) {
          setConnections(items);
          setLoading(false);
        }
      })
      .catch((failure) => {
        if (!controller.signal.aborted) {
          setError(failure);
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [revision, setError]);

  const selected = connections.find((item) => item.id === value);
  const selectionProblem = selected
    ? !selected.enabled
      ? "大脑已停用，请更换连接或前往配置启用。"
      : selected.capability !== "chat"
        ? "此连接仅用于向量，需更换为对话模型。"
        : !selected.has_api_key
          ? "尚未配置凭证，请前往大脑配置补充。"
          : ""
    : value
      ? "当前大脑未加载，请刷新确认；已有选择会保留。"
      : "";
  const status = loading
    ? "加载中"
    : error
      ? "加载失败"
      : selected
        ? !selected.enabled
          ? "已停用"
          : selected.capability !== "chat"
            ? "不支持对话"
            : !selected.has_api_key
              ? "待配置凭证"
              : "已选择"
        : value
          ? "待确认"
          : "未装配";
  const feedback = loading
    ? "正在获取模型连接，已有选择会保留。"
    : error ||
      selectionProblem ||
      (selected
        ? "凭证已配置"
        : connections.some((item) => item.enabled && item.capability === "chat")
          ? "未装配时可保存草稿，暂不能对话。"
          : "暂无可用的对话连接，可先配置大脑，再刷新列表。");

  const ready = !loading && !error && !!selected && !selectionProblem;
  useEffect(() => onReadinessChange?.(ready), [ready, onReadinessChange]);

  function refresh() {
    setLoading(true);
    setError("");
    setRevision((current) => current + 1);
  }

  return (
    <section aria-labelledby="agent-brain-label" aria-busy={loading} className="min-w-0">
      <div className="flex min-h-5 items-center gap-3">
        <label id="agent-brain-label" htmlFor="agent-brain" className="type-caption">
          大脑
        </label>
        <span
          className={cn(
            "inline-flex shrink-0 items-center gap-1 text-[length:var(--os-text-caption)] leading-4",
            ready && "sr-only",
            !loading && !error && !value && "sr-only",
            error
              ? "text-danger"
              : !loading && selectionProblem
                ? "text-warning"
                : !loading && selected
                  ? "text-success"
                  : "text-text-muted",
          )}
        >
          {!loading && !error && selected && !selectionProblem && (
            <Check className="size-3" aria-hidden="true" />
          )}
          {status}
        </span>
      </div>
      <p id="agent-brain-description" className="sr-only">
        选择这位员工使用的模型连接
      </p>
      <SelectField
        options={[
          { value: "none", label: "暂不装配" },
          ...(value && !selected ? [{ value, label: "当前大脑（待确认）" }] : []),
          ...connections.map((item) => ({
            value: item.id,
            label: `${item.name} · ${item.model_id}${!item.enabled ? "（已停用）" : item.capability !== "chat" ? "（仅用于向量）" : ""}`,
            disabled: !item.enabled || item.capability !== "chat",
          })),
        ]}
        value={value || "none"}
        onValueChange={(id) => onChange(id === "none" ? null : id)}
        disabled={loading || Boolean(error)}
        displayValue={
          loading
            ? "正在加载大脑…"
            : selected
              ? selected.name
              : value
                ? "当前大脑（待确认）"
                : "选择一个大脑"
        }
        contentProps={{
          className: "min-w-(--anchor-width) max-w-[calc(100vw-2rem)]",
        }}
        id="agent-brain"
        aria-label="装配大脑"
        aria-describedby="agent-brain-description agent-brain-feedback"
        className="mt-1 h-auto min-h-9 w-fit max-w-full gap-3 border-transparent bg-transparent px-0 py-1 text-section font-semibold hover:text-action"
      />
      {failure ? (
        <div id="agent-brain-feedback">
          <FailureNotice
            compact
            failure={failure}
            context={{
              operation: connections.length ? "refresh" : "initial-read",
              resource: "connection",
              hasUsableData: !!connections.length,
            }}
          />
        </div>
      ) : (
        <p
          id="agent-brain-feedback"
          role="status"
          className={cn(
            "type-caption mt-1 flex min-h-4.5 items-start gap-1.5 wrap-anywhere",
            error ? "text-danger" : !loading && selectionProblem ? "text-warning" : "",
          )}
        >
          {ready && <Check className="mt-0.5 size-3.5 shrink-0 text-success" aria-hidden="true" />}
          <span>
            {selected && !selectionProblem && !loading && `${selected.model_id} · `}
            {feedback}
          </span>
          {!loading && !error && revision > 0 && <span className="sr-only">。列表已更新。</span>}
        </p>
      )}
      <div className="mt-1 flex flex-wrap items-center gap-1">
        <Button
          variant="ghost"
          size="icon-sm"
          nativeButton={false}
          render={<a href="/brains" target="_blank" rel="noopener noreferrer" />}
          title="配置大脑"
          aria-label="配置大脑（新标签页）"
        >
          <ArrowUpRight aria-hidden="true" />
        </Button>
        <Button
          type="button"
          size="icon-sm"
          variant="ghost"
          aria-label="刷新大脑列表"
          title="刷新大脑列表"
          loading={loading}
          onClick={refresh}
        >
          <RefreshCw aria-hidden="true" />
        </Button>
      </div>
    </section>
  );
}
