import { FailureNotice } from "@/components/failure/FailureNotice";
import { memo, useCallback, useMemo, useRef } from "react";
import { Copy } from "lucide-react";
import { Message, MessageContent, MessageHeader, MessageFooter } from "@/components/ui/Message";
import { Bubble, BubbleContent } from "@/components/ui/Bubble";
import { Button } from "@/components/ui/Button";
import { Markdown } from "@/components/common/Markdown";
import { AgentAvatar } from "@/components/avatars/index";
import { activityLabel, isActive } from "@/lib/api/conversations";
import { useMessage } from "./useMessage";
import { MessageScrollerItem } from "@/components/ui/MessageScroller";
import { RunActions } from "./RunActions";
import { cn } from "@/lib/utils";
import { fileDownloadUrl } from "@/lib/api/files";
import { knowledgeCitationTitles } from "@/lib/knowledgeCitations";

export type RegisterConversationMessage = (
  element: HTMLDivElement,
  identity: { messageId: string; questionId: string },
) => () => void;

/** 一条消息的过程与正文保持固定位置，消息 ID 不随流式进度变化。 */
export const ConversationMessage = memo(function ConversationMessage({
  messageId,
  agentName,
  avatarId,
  anchorKey,
  registerMessage,
}: {
  messageId: string;
  agentName: string;
  avatarId?: string;
  anchorKey?: number;
  registerMessage: RegisterConversationMessage;
}) {
  const { message, actions } = useMessage(messageId);
  const sourceTitles = useMemo(
    () => knowledgeCitationTitles(message?.run?.steps ?? []),
    [message?.run?.steps],
  );
  const questionId = message?.role === "user" ? message.id : message?.run?.reply_to_message_id;
  const unregister = useRef<(() => void) | null>(null);
  const bindElement = useCallback(
    (element: HTMLDivElement | null) => {
      // 滚动器转发 ref 时不传递 cleanup 返回值，显式在解绑时注销。
      unregister.current?.();
      unregister.current =
        element && questionId ? registerMessage(element, { messageId, questionId }) : null;
    },
    [registerMessage, messageId, questionId],
  );
  if (!message) return null;
  const run = message.run;
  const active = isActive(run?.status);
  return (
    <MessageScrollerItem
      ref={bindElement}
      messageId={messageId}
      scrollAnchor={message.role === "user"}
      tabIndex={-1}
      className="outline-none"
    >
      <Message align={message.role === "user" ? "end" : "start"}>
        <MessageContent className={message.role === "user" ? "items-end" : "gap-3"}>
          {message.role === "user" ? (
            // 重复定位同一问题时仅重放气泡动画，消息行及滚动锚点保持稳定。
            <Bubble
              key={anchorKey}
              className={cn(
                "max-w-[min(85%,calc(var(--os-prose-chat)+32px))] rounded-card rounded-tr-small rounded-br-roomy",
                anchorKey !== undefined &&
                  "animate-[question-anchor-breathe_1.6s_ease-in-out] motion-reduce:animate-none",
              )}
              align="end"
            >
              <BubbleContent>
                <p className="whitespace-pre-wrap text-sm leading-6">{message.content}</p>
              </BubbleContent>
            </Bubble>
          ) : (
            <>
              <MessageHeader className="gap-2 text-xs text-text-muted">
                <span aria-hidden="true" className="size-7 shrink-0 overflow-hidden rounded-full">
                  <AgentAvatar avatarId={avatarId ?? "admin"} size={28} />
                </span>
                <span>{agentName}</span>
                {run && <span>{activityLabel(run)}</span>}
              </MessageHeader>
              {run && <RunActions key={run.id} run={run} finalText={message.content} />}
              {message.content ? (
                <Markdown text={message.content} streaming={active} sourceTitles={sourceTitles} />
              ) : (
                <p className="text-sm text-text-muted">
                  {active ? "等待模型响应…" : "本次没有生成文本。"}
                </p>
              )}
              {message.content && !active && !message.published && (
                <p className="text-xs text-text-muted">未完成的输出</p>
              )}
              {run?.error && (
                <FailureNotice
                  compact
                  failure={{ ...run.error, source: "run", status: null }}
                  context={{ operation: "subscription", resource: "conversation" }}
                />
              )}

              {message.content && !active && (
                <MessageFooter className="gap-2 text-xs text-text-muted">
                  <Button
                    variant="ghost"
                    size="icon-xs"
                    aria-label="复制回答"
                    onClick={() => {
                      void actions.copy().catch(() => {});
                    }}
                  >
                    <Copy />
                  </Button>
                  {run?.usage?.total_tokens != null && <span>{run.usage.total_tokens} tokens</span>}
                </MessageFooter>
              )}
            </>
          )}
          {!!message.files?.length && message.conversationId && (
            <ul className="space-y-1 text-sm">
              {message.files.map((file) => (
                <li key={file.id}>
                  <a
                    className="underline [overflow-wrap:anywhere]"
                    href={fileDownloadUrl(message.conversationId!, file.id)}
                    download
                  >
                    {file.name}
                  </a>
                  <span className="ml-2 text-xs text-text-muted">
                    {Math.ceil(file.size / 1024)} KiB
                  </span>
                </li>
              ))}
            </ul>
          )}
        </MessageContent>
      </Message>
    </MessageScrollerItem>
  );
});
