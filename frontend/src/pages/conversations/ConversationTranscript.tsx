import { FailureNotice } from "@/components/failure/FailureNotice";
import { useCallback, useLayoutEffect, useMemo, useRef, useState } from "react";
import { MessageSquare } from "lucide-react";
import { Button } from "@/components/ui/Button";
import {
  MessageScroller,
  MessageScrollerViewport,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerButton,
  useMessageScroller,
} from "@/components/ui/MessageScroller";
import { ConversationMessage, type RegisterConversationMessage } from "./ConversationMessage";
import { ConversationOutline, type QuestionNavigationControl } from "./ConversationOutline";
import { useConversation } from "./useConversation";
import type { ConversationView } from "./conversationStore";

type History = ConversationView["history"];
type RegisteredMessage = { element: HTMLDivElement; questionId: string };

/** 当前正文作用域内统一管理节点、可见组和定位；不拥有目录请求。 */
function useConversationReading(history: History) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const rows = useRef(new Map<string, RegisteredMessage>());
  const observer = useRef<ResizeObserver | null>(null);
  const frame = useRef<number | null>(null);
  const active = useRef(false);
  const [visibleQuestionIds, setVisibleQuestionIds] = useState<string[]>([]);
  const [feedback, setFeedback] = useState<{ messageId: string; key: number } | null>(null);
  const { scrollToEnd, scrollToMessage } = useMessageScroller();
  const measure = useCallback(() => {
    frame.current = null;
    const root = viewportRef.current;
    if (!root) return;
    const bounds = root.getBoundingClientRect();
    const visible: RegisteredMessage[] = [];
    if (bounds.height > 0 && bounds.width > 0) {
      for (const row of rows.current.values()) {
        if (!root.contains(row.element)) continue;
        const rect = row.element.getBoundingClientRect();
        if (
          rect.bottom > bounds.top &&
          rect.top < bounds.bottom &&
          rect.right > bounds.left &&
          rect.left < bounds.right &&
          rect.height > 0 &&
          rect.width > 0
        )
          visible.push(row);
      }
    }
    // 前插历史的登记时间晚于原窗口，阅读顺序必须按 DOM 而非 Map 插入顺序。
    visible.sort((a, b) =>
      a.element.compareDocumentPosition(b.element) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1,
    );
    const next = [...new Set(visible.map((row) => row.questionId))];
    setVisibleQuestionIds((previous) =>
      previous.length === next.length && previous.every((id, index) => id === next[index])
        ? previous
        : next,
    );
  }, []);
  const schedule = useCallback(() => {
    if (active.current && frame.current === null) frame.current = requestAnimationFrame(measure);
  }, [measure]);
  const registerMessage = useCallback<RegisterConversationMessage>(
    (element, identity) => {
      const previous = rows.current.get(identity.messageId);
      if (previous) observer.current?.unobserve(previous.element);
      const entry = { element, questionId: identity.questionId };
      rows.current.set(identity.messageId, entry);
      observer.current?.observe(element);
      schedule();
      return () => {
        // 旧 ref 的迟到清理不能删除同 ID 已登记的新节点。
        if (rows.current.get(identity.messageId) !== entry) return;
        rows.current.delete(identity.messageId);
        observer.current?.unobserve(element);
        schedule();
      };
    },
    [schedule],
  );
  useLayoutEffect(() => {
    const root = viewportRef.current;
    if (!root) return;
    active.current = true;
    observer.current = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(schedule);
    observer.current?.observe(root);
    for (const row of rows.current.values()) observer.current?.observe(row.element);
    root.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    measure();
    return () => {
      active.current = false;
      root.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
      observer.current?.disconnect();
      observer.current = null;
      if (frame.current !== null) cancelAnimationFrame(frame.current);
      frame.current = null;
    };
  }, [measure, schedule]);
  // 分页控件出现或换行也可能改变行的位置，而不改变消息行自身尺寸。
  useLayoutEffect(schedule, [history, schedule]);
  useLayoutEffect(() => {
    const intent = history.position;
    if (!intent) return;
    const positionFrame = requestAnimationFrame(() => {
      if (intent.target === "end") {
        setFeedback(null);
        scrollToEnd({ behavior: "auto" });
      } else {
        scrollToMessage(intent.target, { align: "start", scrollMargin: 16, behavior: "auto" });
        rows.current.get(intent.target)?.element.focus({ preventScroll: true });
        setFeedback({ messageId: intent.target, key: intent.key });
      }
      schedule();
    });
    return () => cancelAnimationFrame(positionFrame);
  }, [history.position, scrollToEnd, scrollToMessage, schedule]);
  const jump = history.jump;
  const navigate = useCallback(
    (questionId: string) => {
      // 读取错误由历史层记录；离开正文后旧命令不再访问会话。
      if (active.current) void jump(questionId);
    },
    [jump],
  );
  const pending = history.loading === "jump";
  const error = history.errorOrigin === "jump" ? history.error : null;
  const navigation = useMemo<QuestionNavigationControl>(
    () => ({ pending, error, failure: history.failure, navigate }),
    [pending, error, history.failure, navigate],
  );
  return { viewportRef, registerMessage, visibleQuestionIds, feedback, navigation };
}

/** 正文与导航的唯一装配处；工具栏和输入区由页面组合。 */
export function ConversationTranscript({
  agentName,
  avatarId,
  description,
}: {
  agentName: string;
  avatarId: string;
  description?: string;
}) {
  const chat = useConversation();
  const reading = useConversationReading(chat.history);
  const active = chat.phase === "submitted" || chat.phase === "streaming";
  return (
    <>
      <MessageScroller>
        <MessageScrollerViewport
          ref={reading.viewportRef}
          aria-label="对话消息"
          onScroll={(event) => {
            const el = event.currentTarget;
            if (
              el.scrollTop < 80 &&
              el.scrollHeight > el.clientHeight &&
              !el.hasAttribute("data-pending-scroll") &&
              !chat.history.error &&
              !chat.history.isLoading
            )
              void chat.history.loadMore();
            if (
              el.scrollHeight - el.scrollTop - el.clientHeight < 80 &&
              el.scrollHeight > el.clientHeight &&
              !el.hasAttribute("data-pending-scroll") &&
              !chat.history.error &&
              !chat.history.isLoading
            )
              void chat.history.loadNewer();
          }}
        >
          {/* 分页控件不进入测量行，保证前插历史时以原消息为滚动锚点。 */}
          {chat.history.hasMore && (
            <div className="pt-3 text-center">
              <Button
                variant="ghost"
                size="sm"
                disabled={chat.history.isLoading}
                onClick={() => {
                  void chat.history.loadMore();
                }}
              >
                {chat.history.isLoading &&
                (chat.history.loading === null || chat.history.loading === "older")
                  ? "正在加载更早消息…"
                  : chat.history.errorOrigin === "older"
                    ? "加载失败，点击重试"
                    : "加载更早消息"}
              </Button>
            </div>
          )}
          <MessageScrollerContent aria-busy={active} className="conversation-frame pt-6 pb-14">
            {chat.messageIds.length === 0 && (
              <MessageScrollerItem
                messageId="empty"
                className="my-10 mx-auto max-w-120 text-center text-text-muted"
              >
                <MessageSquare className="mx-auto mb-5" size={32} strokeWidth={1.5} />
                <h2 className="mb-3 text-xl font-semibold text-text">与{agentName}开始对话</h2>
                <p className="text-sm leading-7">
                  {description || "描述你的问题，员工将根据工作指令回答。"}
                </p>
              </MessageScrollerItem>
            )}
            {chat.messageIds.map((messageId) => (
              <ConversationMessage
                key={messageId}
                messageId={messageId}
                registerMessage={reading.registerMessage}
                agentName={agentName}
                avatarId={avatarId}
                anchorKey={
                  reading.feedback?.messageId === messageId ? reading.feedback.key : undefined
                }
              />
            ))}
          </MessageScrollerContent>
          {chat.history.hasNewer && (
            <div className="pb-12 text-center">
              <Button
                variant="ghost"
                size="sm"
                disabled={chat.history.isLoading}
                onClick={() => {
                  void chat.history.loadNewer();
                }}
              >
                {chat.history.loading === "newer"
                  ? "正在加载较新消息…"
                  : chat.history.errorOrigin === "newer"
                    ? "加载失败，点击重试较新消息"
                    : "加载较新消息"}
              </Button>
            </div>
          )}
        </MessageScrollerViewport>
        <ConversationOutline
          conversationId={chat.conversation?.id ?? null}
          latestQuestionId={chat.latestQuestionId}
          visibleQuestionIds={reading.visibleQuestionIds}
          navigation={reading.navigation}
        />
        <MessageScrollerButton
          forceVisible={chat.history.isHistorical}
          onClick={() => {
            void chat.history.showLatest();
          }}
        />
      </MessageScroller>
      {chat.history.loading === "latest" && (
        <p role="status" className="sr-only">
          正在读取最新消息…
        </p>
      )}
      {chat.history.error && (
        <FailureNotice
          failure={chat.history.failure}
          error={chat.history.error}
          className="conversation-page-frame"
          context={{ operation: "refresh", resource: "conversation", hasUsableData: true }}
        />
      )}
    </>
  );
}
