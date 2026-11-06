import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { MessageSquare, Plus, RefreshCw } from "lucide-react";
import { useFailureState } from "@/state/shared/useFailureState";
import { useIdentity } from "@/state/auth/useIdentity";
import { identityKey } from "@/lib/identity";
import { FailureNotice } from "@/components/failure/FailureNotice";
import { EmptyState } from "@/components/common/EmptyState";
import { SearchInput } from "@/components/common/SearchInput";
import { PageContainer } from "@/components/common/PageContainer";
import { PageHeading } from "@/components/common/PageHeading";
import { Button } from "@/components/ui/Button";
import { ButtonGroup } from "@/components/ui/ButtonGroup";
import { SelectField } from "@/components/ui/SelectField";
import { sourceLink } from "@/lib/navigation";
import { getConversations, type ConversationPage } from "@/lib/api/conversations";
import { ConversationTable } from "./ConversationTable";
import { ConversationStatus } from "./ConversationStatus";
import { ExecutionLogDialog } from "@/components/execution/ExecutionLogDialog";

const statusOptions = [
  { value: "", label: "全部回复状态" },
  { value: "processing", label: "处理中" },
  { value: "replied", label: "已回复" },
  { value: "attention", label: "需关注" },
  { value: "stopped", label: "已停止" },
];
type Props = {
  agentId?: string;
  activeId?: string;
  returnTo?: string;
  onSelect?: () => void;
  compact?: boolean;
  refreshKey?: string;
};

/** Identity and employee changes dispose of the previous read and its local paging state. */
export function ConversationHistory(props: Props) {
  const identity = useIdentity();
  return <History key={`${identityKey(identity)}:${props.agentId ?? "all"}`} {...props} />;
}
function useConversationList({
  agentId,
  q,
  status,
  offset,
  refreshKey,
}: {
  agentId?: string;
  q: string;
  status: string;
  offset: number;
  refreshKey?: string;
}) {
  const [data, setData] = useState<ConversationPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const { failure, error, setError } = useFailureState();
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    getConversations({ agentId, q, status, offset }, controller.signal)
      .then((page) => {
        if (!controller.signal.aborted) {
          setData(page);
          setLoading(false);
        }
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          setError(error);
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [agentId, q, status, offset, refreshKey, revision, setError]);
  return { data, loading, failure, error, refresh: () => setRevision((n) => n + 1) };
}
function History({ agentId, activeId, returnTo, onSelect, compact = false, refreshKey }: Props) {
  const embedded = !!agentId;
  const [params, setParams] = useSearchParams();
  const inspectedId = params.get("log_conversation");
  const inspectedResponse = params.get("log_response") || undefined;
  function inspect(conversationId: string, responseId: string) {
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        next.set("log_conversation", conversationId);
        next.set("log_response", responseId);
        return next;
      },
      { replace: true, preventScrollReset: true },
    );
  }
  function closeLog() {
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        next.delete("log_conversation");
        next.delete("log_response");
        return next;
      },
      { replace: true, preventScrollReset: true },
    );
  }
  const prefix = embedded ? "history_" : "";
  const [localOffset, setLocalOffset] = useState(0);
  const rawOffset = params.get(`${prefix}offset`) ?? "0";
  const offset = compact ? localOffset : /^\d+$/.test(rawOffset) ? Number(rawOffset) : 0;
  const q = compact ? "" : (params.get(`${prefix}q`) ?? "");
  const rawStatus = params.get(`${prefix}status`) ?? "";
  const status =
    !compact && statusOptions.some((item) => item.value === rawStatus) ? rawStatus : "";
  function update(key: string, value: string) {
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        if (key !== "offset") next.delete(`${prefix}offset`);
        if (value && value !== "0") next.set(`${prefix}${key}`, value);
        else next.delete(`${prefix}${key}`);
        return next;
      },
      { replace: true, preventScrollReset: true },
    );
  }
  function setOffset(value: number) {
    if (compact) setLocalOffset(value);
    else update("offset", String(value));
  }
  const { data, loading, failure, error, refresh } = useConversationList({
    agentId,
    q,
    status,
    offset,
    refreshKey,
  });
  const href = (id: string) =>
    embedded
      ? `/conversations/${id}${returnTo ? `?from=${encodeURIComponent(returnTo)}` : ""}`
      : sourceLink(`/conversations/${id}`);
  return (
    <PageContainer embedded={embedded} className={embedded ? "min-h-0" : undefined}>
      {!embedded && (
        <PageHeading title="对话记录" description="找到之前的话题，继续交流或查看执行日志。" />
      )}
      {!compact && (
        <div className="mb-4 flex flex-wrap items-center gap-2 sm:gap-3">
          <SearchInput
            label="搜索对话主题或 ID"
            placeholder="主题 / Conversation ID / Run ID"
            debounceMs={300}
            value={q}
            onChange={(value) => update("q", value)}
            className="w-full sm:w-80"
          />
          <SelectField
            aria-label="最近回复筛选"
            options={statusOptions}
            value={status}
            onValueChange={(value) => update("status", value)}
            className="w-36 sm:w-40"
          />
          <ButtonGroup className="ml-auto">
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="刷新对话列表"
              loading={loading}
              onClick={refresh}
            >
              <RefreshCw size={16} />
            </Button>
            <Button
              size="sm"
              render={
                <Link
                  to={agentId ? sourceLink(`/conversations/new?agent=${agentId}`) : "/agents"}
                />
              }
              nativeButton={false}
            >
              <Plus size={16} />
              新对话
            </Button>
          </ButtonGroup>
        </div>
      )}
      {failure && (
        <FailureNotice
          failure={failure}
          context={{
            operation: data ? "refresh" : "initial-read",
            resource: "conversation",
            hasUsableData: !!data,
          }}
          actions={[{ label: "重新加载", kind: "retry", onClick: refresh }]}
        />
      )}
      <div aria-busy={loading}>
        {loading && (
          <p role="status" className="mb-3 text-xs text-text-muted">
            {data ? "正在更新对话…" : "正在加载对话…"}
          </p>
        )}
        {data &&
          (data.items.length ? (
            compact ? (
              <ul aria-label="历史对话" className="space-y-2">
                {data.items.map((item) => (
                  <li key={item.id}>
                    <Link
                      to={href(item.id)}
                      onClick={onSelect}
                      aria-current={item.id === activeId ? "page" : undefined}
                      className="flex min-h-20 min-w-0 items-start gap-3 rounded-panel px-3 py-4 hover:bg-surface aria-[current=page]:bg-surface"
                    >
                      <MessageSquare
                        size={16}
                        className="mt-1 shrink-0 text-text-muted"
                        aria-hidden="true"
                      />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium" title={item.title}>
                          {item.title || "新对话"}
                        </span>
                        <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-text-muted">
                          <time dateTime={item.updated_at}>
                            {new Date(item.updated_at).toLocaleDateString("zh-CN")}
                          </time>
                          <ConversationStatus item={item} />
                          {item.id === activeId && <span className="sr-only">当前对话</span>}
                        </span>
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <ConversationTable
                items={data.items}
                showAgent={!embedded}
                href={href}
                onSelect={onSelect}
                onInspect={inspect}
              />
            )
          ) : (
            <EmptyState
              boxed={!compact}
              headingLevel={false}
              density="compact"
              icon={<MessageSquare size={24} aria-hidden="true" />}
              text={q || status ? "没有符合条件的对话" : "还没有历史对话"}
              description={
                q || status
                  ? "调整关键词或回复状态，再试一次。"
                  : "从新对话开始，之后可以在这里继续之前的话题。"
              }
              onReset={
                q || status
                  ? () =>
                      setParams(
                        (current) => {
                          const next = new URLSearchParams(current);
                          for (const key of ["q", "status", "offset"])
                            next.delete(`${prefix}${key}`);
                          return next;
                        },
                        { replace: true, preventScrollReset: true },
                      )
                  : undefined
              }
            />
          ))}
      </div>
      {data && !error && !loading && data.offset === offset && (
        <div
          className={`${compact ? "px-3" : ""} mt-4 flex flex-wrap items-center justify-between gap-3 text-xs text-text-muted`}
        >
          <span>共 {data.total} 段对话</span>
          {data.total > data.limit && (
            <nav aria-label="历史对话分页" className="flex items-center gap-2">
              <Button
                size="sm"
                variant="ghost"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - data.limit))}
              >
                上一页
              </Button>
              <span className="tabular-nums">
                {Math.floor(offset / data.limit) + 1} / {Math.ceil(data.total / data.limit)}
              </span>
              <Button
                size="sm"
                variant="ghost"
                disabled={offset + data.limit >= data.total}
                onClick={() => setOffset(offset + data.limit)}
              >
                下一页
              </Button>
            </nav>
          )}
        </div>
      )}
      {inspectedId && (
        <ExecutionLogDialog
          target={{ conversationId: inspectedId, responseId: inspectedResponse }}
          onClose={closeLog}
        />
      )}
    </PageContainer>
  );
}
