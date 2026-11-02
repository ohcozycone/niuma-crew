import { useFailureState } from "@/state/shared/useFailureState";
import { FailureNotice } from "@/components/failure/FailureNotice";
import { EmptyState } from "@/components/common/EmptyState";
import { Card } from "@/components/ui/Card";
import { PageContainer } from "@/components/common/PageContainer";
import { sourceLink } from "@/lib/navigation";
import { useQueryState } from "@/hooks/useQueryState";
import { Link } from "react-router";
import { useEffect, useState } from "react";
import { MessageSquare, ArrowUpRight, Check, Plus } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { PageHeading } from "@/components/common/PageHeading";
import { getConversations, type ConversationPage } from "@/lib/api/conversations";

/** 全局记录页与当前员工的历史切换共用列表及服务端分页。 */
export function ConversationHistory({
  agentId,
  activeId,
  returnTo,
  onSelect,
  compact = false,
  refreshKey,
}: {
  agentId?: string;
  activeId?: string;
  returnTo?: string;
  onSelect?: () => void;
  compact?: boolean;
  refreshKey?: string;
}) {
  const embedded = !!agentId;
  const [rawOffset, updateOffset] = useQueryState("offset", "0");
  const [localOffset, setLocalOffset] = useState(0);
  const offset = embedded ? localOffset : /^\d+$/.test(rawOffset) ? Number(rawOffset) : 0;
  const setOffset = (value: number) =>
    embedded ? setLocalOffset(value) : updateOffset(String(value));
  const [data, setData] = useState<ConversationPage | null>(null);
  const { failure, error, setError } = useFailureState();
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    getConversations({ agentId, offset }, controller.signal)
      .then((page) => {
        if (!controller.signal.aborted) {
          setData(page);
          setError("");
        }
      })
      .catch((failure: Error) => {
        if (!controller.signal.aborted) setError(failure);
      });
    return () => controller.abort();
  }, [agentId, offset, revision, refreshKey, setError]);
  return (
    <PageContainer embedded={embedded} className={embedded ? "min-h-0" : undefined}>
      {!embedded && (
        <PageHeading
          title="对话记录"
          description="接着上次的话题聊，或选择一位员工开始新对话。"
          actions={
            <Button render={<Link to="/agents" />} nativeButton={false}>
              <Plus size={16} /> 开始对话
            </Button>
          }
        />
      )}
      {failure && (
        <FailureNotice
          failure={failure}
          context={{
            operation: data ? "refresh" : "initial-read",
            resource: "conversation",
            hasUsableData: !!data,
          }}
          actions={[
            {
              label: "重新加载",
              kind: "retry",
              onClick: () => {
                setError("");
                setRevision((v) => v + 1);
              },
            },
          ]}
        />
      )}
      {!data ? (
        !failure && (
          <p role="status" className="py-6 text-sm text-text-muted">
            正在加载对话…
          </p>
        )
      ) : !data.items.length ? (
        <EmptyState
          boxed={!compact}
          headingLevel={false}
          text={
            embedded
              ? "还没有历史对话，发一条消息开始吧。"
              : "还没有对话。选择一位已装配大脑的员工开始。"
          }
          icon={<MessageSquare size={24} aria-hidden="true" />}
          density="compact"
        />
      ) : (
        <HistoryList
          compact={compact}
          as="ul"
          variant={embedded ? "plain" : "outline"}
          radius={embedded ? "none" : "panel"}
          aria-label="历史对话"
          className={
            compact
              ? "space-y-2"
              : `divide-y divide-border ${embedded ? "focus-gutter max-h-[50dvh] overflow-y-auto" : ""}`
          }
        >
          {data.items.map((item) => (
            <li key={item.id}>
              <Link
                to={
                  embedded
                    ? `/conversations/${item.id}${returnTo ? `?from=${encodeURIComponent(returnTo)}` : ""}`
                    : sourceLink(`/conversations/${item.id}`)
                }
                aria-current={item.id === activeId ? "page" : undefined}
                onClick={onSelect}
                className={
                  compact
                    ? "group flex min-h-20 min-w-0 items-start gap-3 rounded-panel px-3 py-4 transition-colors hover:bg-surface/60 aria-[current=page]:bg-surface"
                    : "group flex min-h-16 min-w-0 items-center gap-3 px-4 py-3 hover:bg-muted aria-[current=page]:bg-selected"
                }
              >
                {compact && (
                  <MessageSquare
                    size={16}
                    strokeWidth={1.5}
                    aria-hidden="true"
                    className="mt-0.5 shrink-0 text-text-muted"
                  />
                )}
                {!compact && (
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-control bg-muted text-text-muted">
                    {item.id === activeId ? <Check size={16} /> : <MessageSquare size={16} />}
                  </span>
                )}
                <span className="min-w-0 flex-1">
                  <span className="flex min-w-0 items-center gap-2">
                    <span
                      className="block min-w-0 flex-1 truncate text-sm font-medium text-text"
                      title={item.title}
                    >
                      {item.title || "新对话"}
                    </span>
                    {compact && item.id === activeId && (
                      <span
                        className="size-1.5 shrink-0 rounded-full bg-text/65"
                        aria-hidden="true"
                      />
                    )}
                  </span>
                  <span className="mt-1 flex flex-wrap gap-x-2 text-xs text-text-muted">
                    {!embedded && <span>{item.agent_name}</span>}
                    <time dateTime={item.updated_at}>
                      {new Date(item.updated_at).toLocaleString("zh-CN", {
                        month: "numeric",
                        day: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </time>
                    {item.active_response_id && <span className="text-success">执行中</span>}
                    {item.id === activeId && (
                      <span className={compact ? "sr-only" : undefined}>当前对话</span>
                    )}
                  </span>
                </span>
                {!compact && <ArrowUpRight size={16} className="shrink-0 text-text-muted" />}
              </Link>
            </li>
          ))}
        </HistoryList>
      )}
      {data && !error && data.offset === offset && (
        <div
          className={`${compact ? "mt-5 gap-2 px-3" : "mt-6 gap-4"} flex flex-wrap items-center justify-between`}
        >
          <span className="text-xs text-text-muted">共 {data.total} 段对话</span>
          {data.total > 20 && (
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="ghost"
                disabled={!offset}
                onClick={() => setOffset(Math.max(0, offset - 20))}
              >
                上一页
              </Button>
              <span className="text-xs tabular-nums text-text-muted">
                {Math.floor(offset / 20) + 1} / {Math.ceil(data.total / 20)}
              </span>
              <Button
                size="sm"
                variant="ghost"
                disabled={offset + 20 >= data.total}
                onClick={() => setOffset(offset + 20)}
              >
                下一页
              </Button>
            </div>
          )}
        </div>
      )}
    </PageContainer>
  );
}

function HistoryList({
  compact,
  children,
  ...props
}: React.ComponentProps<typeof Card> & { compact: boolean }) {
  return compact ? (
    <ul aria-label="历史对话" className="space-y-2">
      {children}
    </ul>
  ) : (
    <Card {...props}>{children}</Card>
  );
}
