// @vitest-environment jsdom
import { StrictMode, type ReactNode } from "react";
import { act, cleanup, render, renderHook, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/http";
import type { ConversationTransport } from "@/lib/api/conversationTransport";
import { ConversationProvider } from "./ConversationProvider";
import { useConversation } from "./useConversation";
import { useMessage } from "./useMessage";
import {
  messageFixture,
  runFixture,
  actionFixture,
  transportFixture,
} from "./conversationTestHelpers";
afterEach(() => {
  cleanup();
  sessionStorage.clear();
  vi.restoreAllMocks();
});

it("keeps observing completed execution until the reply is accepted", async () => {
  const pending = runFixture({
    status: "succeeded",
    acceptance: "pending",
    content: "已保存的执行成果",
    content_state: "draft",
  });
  const { transport, listeners, openCount } = transportFixture(pending);
  const { result } = renderHook(
    () => ({ conversation: useConversation(), answer: useMessage("a1") }),
    { wrapper: wrapper(transport) },
  );
  await waitFor(() => expect(openCount()).toBe(1));
  expect(result.current.answer.message?.published).toBe(false);
  expect(result.current.answer.message?.run?.content_state).toBe("draft");
  expect(result.current.answer.canStop).toBe(false);
  expect(result.current.conversation.phase).toBe("submitted");
  act(() =>
    listeners[0].snapshot({
      ...pending,
      version: pending.version + 1,
      acceptance: "accepted",
      content_state: "complete",
    }),
  );
  await waitFor(() => expect(openCount()).toBe(0));
  expect(result.current.answer.message?.published).toBe(true);
  expect(result.current.answer.message?.run?.content_state).toBe("complete");
  expect(result.current.conversation.phase).toBe("ready");
});
function wrapper(transport: ConversationTransport) {
  return function Scope({ children }: { children: ReactNode }) {
    return (
      <ConversationProvider id="chat" transport={transport}>
        {children}
      </ConversationProvider>
    );
  };
}
it("shares loading and one subscription across conversation and message consumers", async () => {
  const { transport, listeners, openCount } = transportFixture(runFixture());
  const renders: Record<string, number> = {};
  function Summary() {
    const conversation = useConversation();
    renders.summary = (renders.summary ?? 0) + 1;
    return <span>{conversation.messageIds.join(",")}</span>;
  }
  function Item({ id, label }: { id: string; label: string }) {
    const { message } = useMessage(id);
    renders[label] = (renders[label] ?? 0) + 1;
    return <span data-testid={label}>{message?.content}</span>;
  }
  render(
    <ConversationProvider id="chat" transport={transport}>
      <Summary />
      <Summary />
      <Item id="u1" label="user" />
      <Item id="a1" label="answer" />
      <Item id="a1" label="actions" />
    </ConversationProvider>,
  );
  await waitFor(() => expect(screen.getByTestId("answer").textContent).toBe("回答"));
  expect(transport.getMessages).not.toHaveBeenCalled();
  expect(transport.getSnapshot).toHaveBeenCalledOnce();
  expect(transport.getResponse).not.toHaveBeenCalled();
  expect(openCount()).toBe(1);
  const before = { ...renders };
  act(() =>
    listeners[0].snapshot(
      runFixture({
        version: 2,
        content: "新正文",
        steps: [actionFixture({ output_text: "新正文" })],
      }),
    ),
  );
  expect(screen.getByTestId("answer").textContent).toBe("新正文");
  expect(screen.getByTestId("actions").textContent).toBe("新正文");
  expect(renders.summary).toBe(before.summary);
  expect(renders.user).toBe(before.user);
  expect(transport.subscribe).toHaveBeenCalledOnce();
});
it("returns no message for explicit null or an unloaded ID without fetching or selecting latest", async () => {
  const { transport } = transportFixture();
  const { result } = renderHook(
    () => ({
      conversation: useConversation(),
      none: useMessage(null),
      missing: useMessage("unknown"),
      answer: useMessage("a1"),
    }),
    { wrapper: wrapper(transport) },
  );
  await waitFor(() => expect(result.current.conversation.phase).toBe("ready"));
  expect(result.current.conversation.lastMessageId).toBe("a1");
  expect(result.current.answer.status).toBe("succeeded");
  expect(result.current.answer.message?.id).toBe("a1");
  expect(result.current.none.message).toBeNull();
  expect(result.current.missing.message).toBeNull();
  expect(result.current.missing.executionActions).toEqual([]);
  await expect(result.current.missing.actions.stop()).rejects.toThrow("不能停止");
  expect(transport.getMessages).not.toHaveBeenCalled();
  expect(transport.cancel).not.toHaveBeenCalled();
});
it("keeps the message ID list and unchanged message snapshots stable on streaming updates", async () => {
  const { transport, listeners } = transportFixture(runFixture());
  const { result } = renderHook(
    () => ({ conversation: useConversation(), user: useMessage("u1"), answer: useMessage("a1") }),
    { wrapper: wrapper(transport) },
  );
  await waitFor(() => expect(result.current.conversation.phase).toBe("streaming"));
  const before = result.current;
  act(() =>
    listeners[0].snapshot(
      runFixture({ version: 2, steps: [actionFixture({ reasoning_text: "新增步骤摘要" })] }),
    ),
  );
  expect(result.current.conversation).toBe(before.conversation);
  expect(result.current.conversation.messageIds).toBe(before.conversation.messageIds);
  expect(result.current.user).toBe(before.user);
  expect(result.current.answer.executionActions[0].reasoning_text).toBe("新增步骤摘要");
  expect(result.current.answer.actions).toBe(before.answer.actions);
});
it("loads historical messages through the conversation window and exposes them by ID", async () => {
  const { transport, listeners } = transportFixture(runFixture());
  const { result } = renderHook(
    () => ({
      conversation: useConversation(),
      old: useMessage("old-answer"),
      current: useMessage("a1"),
    }),
    { wrapper: wrapper(transport) },
  );
  await waitFor(() => expect(result.current.conversation.phase).toBe("streaming"));
  const saved = runFixture({
    reply_to_message_id: "old-question",
    id: "old-answer",
    status: "succeeded",
    content: "历史回答",
    steps: [actionFixture({ id: "old-step", run_id: "old-run", reasoning_text: "历史步骤" })],
  });
  vi.mocked(transport.getMessages).mockResolvedValueOnce({
    items: [
      messageFixture("old-question", "user", saved),
      messageFixture("old-answer", "assistant", saved),
    ],
    next_before_sequence: null,
    has_more: false,
    next_after_sequence: 2,
  });
  await act(async () => {
    await result.current.conversation.history.jump("old-question");
  });
  expect(result.current.conversation.messageIds).toEqual(["old-question", "old-answer"]);
  expect(result.current.conversation.lastMessageId).toBe("a1");
  expect(result.current.current.canStop).toBe(true);
  expect(result.current.old.canStop).toBe(false);
  expect(result.current.old.message?.content).toBe("历史回答");
  expect(result.current.old.executionActions[0].reasoning_text).toBe("历史步骤");
  act(() =>
    listeners[0].snapshot(
      runFixture({
        version: 2,
        content: "历史阅读期间继续生成",
      }),
    ),
  );
  expect(result.current.current.message?.content).toBe("历史阅读期间继续生成");
  expect(result.current.conversation.messageIds).toEqual(["old-question", "old-answer"]);
  expect(transport.getMessages).toHaveBeenCalledTimes(1);
});
it("binds retry to the selected message and rejects a stale action after a new message arrives", async () => {
  const failed = runFixture({ status: "failed" });
  const { transport } = transportFixture(failed);
  const { result } = renderHook(
    () => ({ conversation: useConversation(), answer: useMessage("a1") }),
    { wrapper: wrapper(transport) },
  );
  await waitFor(() => expect(result.current.answer.canRetry).toBe(true));
  const retryOld = result.current.answer.actions.retry;
  await act(async () => {
    await result.current.conversation.sendMessage({ content: "后续问题" });
  });
  await expect(retryOld()).rejects.toThrow("不能重试");
  expect(transport.retry).not.toHaveBeenCalled();
  expect(result.current.answer.message?.run?.status).toBe("failed");
});
it("retries a failed assistant message into a new answer while preserving its original steps", async () => {
  const { transport } = transportFixture(
    runFixture({
      status: "failed",
      steps: [actionFixture({ status: "failed", output_text: "原过程" })],
    }),
  );
  const { result } = renderHook(
    () => ({ conversation: useConversation(), original: useMessage("a1"), next: useMessage("a2") }),
    { wrapper: wrapper(transport) },
  );
  await waitFor(() => expect(result.current.original.canRetry).toBe(true));
  await act(async () => {
    await result.current.original.actions.retry();
  });
  expect(transport.retry).toHaveBeenCalledWith("chat", "a1", expect.any(String));
  expect(result.current.conversation.messageIds).toEqual(["u1", "a1", "a2"]);
  expect(result.current.conversation.lastMessageId).toBe("a2");
  expect(result.current.next.canStop).toBe(true);
  expect(result.current.original.executionActions[0].output_text).toBe("原过程");
  expect(result.current.next.message?.run?.retry_of_response_id).toBe("a1");
  expect(result.current.original.canRetry).toBe(false);
});
it("keeps stop failures on the selected message when connection snapshots continue", async () => {
  const { transport, listeners } = transportFixture(runFixture());
  vi.mocked(transport.cancel).mockRejectedValue(new ApiError("取消确认失败", 0));
  const { result } = renderHook(
    () => ({ conversation: useConversation(), answer: useMessage("a1"), user: useMessage("u1") }),
    { wrapper: wrapper(transport) },
  );
  await waitFor(() => expect(result.current.answer.canStop).toBe(true));
  await act(async () => {
    await result.current.answer.actions.stop();
  });
  expect(result.current.answer.operationError).toBe("取消确认失败");
  expect(result.current.answer.status).toBe("running");
  act(() => listeners[0].snapshot(runFixture({ version: 2 })));
  expect(result.current.answer.operationError).toBe("取消确认失败");
  expect(result.current.user.operationError).toBeNull();
  expect(result.current.conversation.connectionError).toBeNull();
  expect(result.current.conversation.submissionError).toBeNull();
});
it("keeps unknown submission recovery on the conversation and resends the same command", async () => {
  const { transport } = transportFixture();
  transport.create = { agentId: "agent" };
  vi.mocked(transport.send).mockRejectedValueOnce(new ApiError("提交结果未知", 0));
  const { result } = renderHook(
    () => ({ conversation: useConversation(), none: useMessage(null) }),
    { wrapper: wrapper(transport) },
  );
  await act(async () => {
    await expect(result.current.conversation.sendMessage({ content: "问题" })).rejects.toThrow();
  });
  expect(result.current.conversation.hasPendingSubmission).toBe(true);
  expect(result.current.conversation.submissionError?.message).toBe("提交结果未知");
  expect(result.current.none.canRetry).toBe(false);
  const original = vi.mocked(transport.send).mock.calls[0];
  await act(async () => {
    await result.current.conversation.resendPending();
  });
  expect(vi.mocked(transport.send).mock.calls[1]).toEqual(original);
});
it("retains one live subscription in StrictMode and does not close it when a message consumer unmounts", async () => {
  const { transport, openCount } = transportFixture(runFixture());
  function Item() {
    return <span>{useMessage("a1").message?.content}</span>;
  }
  const view = render(
    <StrictMode>
      <ConversationProvider id="chat" transport={transport}>
        <Item />
      </ConversationProvider>
    </StrictMode>,
  );
  await screen.findByText("回答");
  expect(openCount()).toBe(1);
  view.rerender(
    <StrictMode>
      <ConversationProvider id="chat" transport={transport}>
        {null}
      </ConversationProvider>
    </StrictMode>,
  );
  expect(openCount()).toBe(1);
  view.unmount();
  expect(openCount()).toBe(0);
});
it("disables captured message actions when leaving the conversation scope", async () => {
  const { transport } = transportFixture(runFixture({ status: "failed" }));
  const view = renderHook(() => useMessage("a1"), { wrapper: wrapper(transport) });
  await waitFor(() => expect(view.result.current.canRetry).toBe(true));
  const retry = view.result.current.actions.retry;
  view.unmount();
  await expect(retry()).rejects.toThrow("已离开");
  expect(transport.retry).not.toHaveBeenCalled();
});
it("requires an explicit ID instead of silently following the latest message", () => {
  const { transport } = transportFixture();
  const useWithoutId = useMessage as (id?: string) => ReturnType<typeof useMessage>;
  expect(() => renderHook(() => useWithoutId(), { wrapper: wrapper(transport) })).toThrow(
    "显式提供消息 ID",
  );
  expect(transport.getMessages).not.toHaveBeenCalled();
});
it("uses current content for copy while keeping captured actions bound to their message ID", async () => {
  const { transport, listeners } = transportFixture(runFixture());
  const writeText = vi.fn(async () => {});
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
  const { result } = renderHook(() => useMessage("a1"), { wrapper: wrapper(transport) });
  await waitFor(() => expect(result.current.message?.content).toBe("回答"));
  const copy = result.current.actions.copy;
  act(() =>
    listeners[0].snapshot(
      runFixture({
        version: 2,
        content: "最新正文",
      }),
    ),
  );
  await copy();
  expect(writeText).toHaveBeenCalledWith("最新正文");
});
it("clears message snapshots and captured actions when the identity scope changes", async () => {
  const old = transportFixture(runFixture({ status: "failed", content: "旧身份回答" }));
  const next = transportFixture();
  vi.mocked(next.transport.getMessages).mockImplementation(() => new Promise(() => {}));
  let current!: ReturnType<typeof useMessage>;
  function Item() {
    current = useMessage("a1");
    return <span>{current.message?.content ?? "空消息"}</span>;
  }
  const view = render(
    <ConversationProvider id="chat" storageKey="owner-one" transport={old.transport}>
      <Item />
    </ConversationProvider>,
  );
  await screen.findByText("旧身份回答");
  const retryOld = current.actions.retry;
  view.rerender(
    <ConversationProvider id="chat" storageKey="owner-two" transport={next.transport}>
      <Item />
    </ConversationProvider>,
  );
  expect(screen.queryByText("旧身份回答")).toBeNull();
  expect(screen.getByText("空消息")).toBeTruthy();
  await expect(retryOld()).rejects.toThrow("已离开");
  expect(old.transport.retry).not.toHaveBeenCalled();
  expect(next.transport.retry).not.toHaveBeenCalled();
});
it("keeps stopping state separate until the server confirms cancellation of that message", async () => {
  const initial = runFixture();
  const { transport, listeners } = transportFixture(initial);
  let confirm!: (run: typeof initial) => void;
  vi.mocked(transport.cancel).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        confirm = resolve;
      }),
  );
  const { result } = renderHook(
    () => {
      const conversation = useConversation();
      return { conversation, answer: useMessage(conversation.lastMessageId) };
    },
    { wrapper: wrapper(transport) },
  );
  await waitFor(() => expect(result.current.answer.canStop).toBe(true));
  let stopping!: Promise<void>;
  act(() => {
    stopping = result.current.answer.actions.stop();
  });
  expect(result.current.answer.pending.stop).toBe(true);
  expect(result.current.answer.status).toBe("running");
  expect(transport.cancel).toHaveBeenCalledWith("chat", "a1");
  await act(async () => {
    confirm({ ...initial, version: 2, status: "cancelling" });
    await stopping;
  });
  expect(result.current.answer.status).toBe("cancelling");
  expect(result.current.answer.pending.stop).toBe(false);
  expect(result.current.answer.canStop).toBe(false);
  act(() =>
    listeners[0].snapshot({ ...initial, version: 3, status: "cancelled", can_retry: true }),
  );
  expect(result.current.answer.status).toBe("cancelled");
  expect(result.current.conversation.phase).toBe("ready");
  expect(result.current.conversation.lastMessageId).toBe("a1");
  expect(result.current.answer.canStop).toBe(false);
  expect(result.current.answer.canRetry).toBe(true);
});
it("loads the latest reply and scope from one snapshot", async () => {
  const { transport } = transportFixture();
  const active = runFixture({ reply_to_message_id: "u2", id: "a2" });
  const original = await transport.getSnapshot("chat");
  vi.mocked(transport.getSnapshot).mockResolvedValue({
    ...original,
    conversation: {
      ...original.conversation,
      version: 2,
      active_response_id: active.id,
      last_response_id: active.id,
    },
    messages: {
      ...original.messages,
      items: [
        ...original.messages.items,
        {
          id: "u2",
          conversation_id: "chat",
          role: "user",
          sequence: 3,
          content: "新问题",
          created_at: active.created_at,
          updated_at: active.updated_at,
        },
        active,
      ],
    },
  });
  vi.mocked(transport.getMessages).mockClear();
  const { result } = renderHook(
    () => {
      const conversation = useConversation();
      return { conversation, last: useMessage(conversation.lastMessageId) };
    },
    { wrapper: wrapper(transport) },
  );
  await waitFor(() => expect(result.current.last.canStop).toBe(true));
  expect(result.current.conversation.lastMessageId).toBe("a2");
  expect(transport.getMessages).not.toHaveBeenCalled();
});

it("hides retry actions for a read-only historical reply without hiding its content", async () => {
  const { transport } = transportFixture(
    runFixture({ status: "failed", can_retry: false, content: "历史内容" }),
  );
  const { result } = renderHook(
    () => ({ conversation: useConversation(), answer: useMessage("a1") }),
    { wrapper: wrapper(transport) },
  );
  await waitFor(() => expect(result.current.conversation.phase).toBe("ready"));
  expect(result.current.answer.message?.content).toBe("历史内容");
  expect(result.current.answer.canRetry).toBe(false);
  await expect(result.current.answer.actions.retry()).rejects.toThrow("不能重试");
  expect(transport.retry).not.toHaveBeenCalled();
});
