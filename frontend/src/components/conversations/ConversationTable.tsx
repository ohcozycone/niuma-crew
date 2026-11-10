import { Link } from "react-router";
import type { Conversation } from "@/lib/api/conversations";
import { Button } from "@/components/ui/Button";
import { ButtonGroup } from "@/components/ui/ButtonGroup";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/Table";
import { ConversationStatus } from "./ConversationStatus";

function formatTime(value: string, dateOnly = false) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("zh-CN", {
    ...(date.getFullYear() !== new Date().getFullYear() ? { year: "numeric" as const } : {}),
    month: "2-digit",
    day: "2-digit",
    ...(!dateOnly ? { hour: "2-digit" as const, minute: "2-digit" as const } : {}),
  });
}
export function ConversationTable({
  items,
  showAgent,
  href,
  onSelect,
  onInspect,
}: {
  items: Conversation[];
  showAgent: boolean;
  href: (id: string) => string;
  onSelect?: () => void;
  onInspect: (conversationId: string, responseId: string) => void;
}) {
  return (
    <div className="overflow-hidden rounded-panel border border-border bg-raised @container/history">
      <Table aria-label="历史对话" className="@max-[599px]/history:block">
        <TableHeader className="@max-[599px]/history:sr-only">
          <TableRow>
            <TableHead>对话主题</TableHead>
            <TableHead className="w-26 @max-[799px]/history:hidden">最近回复</TableHead>
            <TableHead className="w-40">最近活动</TableHead>
            <TableHead className="w-44 text-right">操作</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody className="@max-[599px]/history:block">
          {items.map((item) => (
            <TableRow
              key={item.id}
              className="@max-[599px]/history:grid @max-[599px]/history:grid-cols-[minmax(0,1fr)_auto]"
            >
              <TableCell className="@max-[599px]/history:col-span-2 @max-[599px]/history:pb-0">
                <Link
                  to={href(item.id)}
                  onClick={onSelect}
                  title={item.title}
                  className="line-clamp-2 rounded-small font-medium leading-6 hover:underline underline-offset-4 [overflow-wrap:anywhere]"
                >
                  {item.title || "新对话"}
                </Link>
                {showAgent && (
                  <span className="mt-1 block text-xs text-text-muted">{item.agent_name}</span>
                )}
                <p className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-text-muted">
                  <span>
                    Conversation ID <code className="select-all">{item.id}</code>
                  </span>
                  {item.last_response_id && (
                    <span>
                      {item.matched_response_id ? "命中 Run" : "最近 Run"}{" "}
                      <code className="select-all">
                        {item.matched_response_id || item.last_response_id}
                      </code>
                    </span>
                  )}
                </p>
                <span className="mt-1 hidden @min-[600px]/history:@max-[799px]/history:block">
                  <ConversationStatus item={item} />
                </span>
              </TableCell>
              <TableCell className="hidden @min-[800px]/history:table-cell @max-[599px]/history:block">
                <ConversationStatus item={item} />
              </TableCell>
              <TableCell className="text-xs text-text-muted tabular-nums @max-[599px]/history:text-right">
                <time
                  dateTime={item.updated_at}
                  title={new Date(item.updated_at).toLocaleString("zh-CN")}
                >
                  <span className="sr-only">最近活动：</span>
                  {formatTime(item.updated_at)}
                </time>
                <span className="mt-1 block">
                  创建于{" "}
                  <time
                    dateTime={item.created_at}
                    title={new Date(item.created_at).toLocaleString("zh-CN")}
                  >
                    {formatTime(item.created_at, true)}
                  </time>
                </span>
              </TableCell>
              <TableCell className="@max-[599px]/history:col-span-2 @max-[599px]/history:pt-0">
                <ButtonGroup className="flex-nowrap gap-1">
                  {item.last_response_id && (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() =>
                        onInspect(item.id, item.matched_response_id || item.last_response_id!)
                      }
                      aria-label={`查看${item.title || "对话"}的执行日志`}
                    >
                      执行日志
                    </Button>
                  )}
                  <Button
                    size="sm"
                    variant="secondary"
                    render={<Link to={href(item.id)} onClick={onSelect} />}
                    nativeButton={false}
                  >
                    去对话
                  </Button>
                </ButtonGroup>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
