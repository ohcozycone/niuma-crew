// @vitest-environment jsdom
import { StrictMode, type ReactNode } from "react";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/http";
import { useConversationController } from "@/pages/conversations/useConversationController";
import {
  runFixture,
  actionFixture,
  transportFixture,
  snapshotFixture,
} from "./conversationTestHelpers";
afterEach(() => {
  cleanup();
  sessionStorage.clear();
  vi.restoreAllMocks();
  vi.useRealTimers();
});
it("opens a local draft without requests and accepts a first send with stable message IDs", async () => {
  const { transport } = transportFixture();
  transport.create = { agentId: "agent" };
  const { result } = renderHook(() => useConversationController({ id: "chat", transport }));
  expect(result.current.phase).toBe("ready");
  expect(transport.getSnapshot).not.toHaveBeenCalled();
  await act(async () => {
    await result.current.sendMessage({ content: " 新问题 " });
  });
  expect(transport.send).toHaveBeenCalledWith(
    null,
    expect.objectContaining({ content: "新问题" }),
    expect.any(String),
  );
  expect(result.current.messages.map((message) => message.id)).toEqual(["u2", "a2"]);
  expect(result.current.phase).toBe("submitted");
});
it("replaces snapshots, rejects duplicate revisions and keeps history references and the subscription", async () => {
  const { transport, listeners } = transportFixture(runFixture());
  const { result } = renderHook(() => useConversationController({ id: "chat", transport }));
  await waitFor(() => expect(result.current.phase).toBe("streaming"));
  const user = result.current.messages[0];
  const before = result.current.messages;
  act(() => listeners[0].snapshot(runFixture()));
  expect(result.current.messages).toBe(before);
  act(() =>
    listeners[0].snapshot(
      runFixture({
        version: 2,
        content: "回答更新",
      }),
    ),
  );
  expect(result.current.messages[0]).toBe(user);
  expect(result.current.messages[1].content).toBe("回答更新");
  expect(transport.subscribe).toHaveBeenCalledTimes(1);
  expect(transport.getSnapshot).toHaveBeenCalledTimes(1);
});
it("keeps unknown submission busy and retries exactly the same immutable request", async () => {
  const { transport } = transportFixture();
  transport.create = { agentId: "agent" };
  vi.mocked(transport.send).mockRejectedValueOnce(new ApiError("网络中断", 0));
  const { result } = renderHook(() =>
    useConversationController({ id: "chat", transport, storageKey: "request" }),
  );
  await act(async () => {
    await expect(
      result.current.sendMessage({ content: "问题二", selectedSkillIds: ["skill"] }),
    ).rejects.toThrow();
  });
  expect(result.current.phase).toBe("submitted");
  expect(result.current.submissionError?.recovery).toBe("retry");
  const original = vi.mocked(transport.send).mock.calls[0];
  await act(async () => {
    await result.current.resendPending();
  });
  expect(vi.mocked(transport.send).mock.calls[1]).toEqual(original);
  expect(result.current.messages.filter((message) => message.role === "user")).toHaveLength(1);
});
it("records stop during a pending POST and cancels only after the Reply is known", async () => {
  const { transport } = transportFixture();
  transport.create = { agentId: "agent" };
  let accept!: (value: ReturnType<typeof runFixture>) => void;
  vi.mocked(transport.send).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        accept = resolve;
      }),
  );
  vi.mocked(transport.cancel).mockResolvedValue(
    runFixture({
      reply_to_message_id: "u2",
      id: "a2",
      status: "cancelled",
      version: 2,
    }),
  );
  const { result } = renderHook(() => useConversationController({ id: "chat", transport }));
  let sending!: Promise<void>;
  act(() => {
    sending = result.current.sendMessage({ content: "待停止" });
  });
  await act(async () => {
    await result.current.cancelPending();
  });
  expect(transport.cancel).not.toHaveBeenCalled();
  await act(async () => {
    accept(
      runFixture({
        reply_to_message_id: "u2",
        id: "a2",
        status: "queued",
      }),
    );
    await sending;
  });
  expect(transport.cancel).toHaveBeenCalledWith("chat", "a2");
  expect(result.current.phase).toBe("ready");
  expect(result.current.messages[1].run?.status).toBe("cancelled");
});
it("creates a new attempt for a failed answer and reuses the original user message", async () => {
  const { transport } = transportFixture(
    runFixture({
      status: "failed",
      error: { code: "upstream_unavailable", message: "上游失败" },
    }),
  );
  const { result } = renderHook(() => useConversationController({ id: "chat", transport }));
  await waitFor(() => expect(result.current.messages[1]?.run?.status).toBe("failed"));
  await act(async () => {
    await result.current.retryMessage("a1");
  });
  expect(transport.retry).toHaveBeenCalledWith("chat", "a1", expect.any(String));
  expect(result.current.messages.filter((message) => message.role === "user")).toHaveLength(1);
  expect(result.current.messages.filter((message) => message.role === "assistant")).toHaveLength(2);
  expect(result.current.messages[1].run?.status).toBe("failed");
});
it("reconnects by reading saved state and never resubmits or cancels work", async () => {
  const { transport } = transportFixture(runFixture());
  const { result } = renderHook(() => useConversationController({ id: "chat", transport }));
  await waitFor(() => expect(result.current.phase).toBe("streaming"));
  const completed = runFixture({
    status: "succeeded",
    version: 3,
    content: "完成",
  });
  vi.mocked(transport.getSnapshot).mockResolvedValue(snapshotFixture(completed));
  act(() => result.current.reconnect());
  await waitFor(() => expect(result.current.phase).toBe("ready"));
  expect(result.current.messages[1].content).toBe("完成");
  expect(transport.send).not.toHaveBeenCalled();
  expect(transport.retry).not.toHaveBeenCalled();
  expect(transport.cancel).not.toHaveBeenCalled();
});
it("recovers an unknown request on mount using GET only", async () => {
  const { transport } = transportFixture(runFixture());
  const input = { content: "问题" };
  sessionStorage.setItem(
    "request",
    JSON.stringify({ persisted: false, pending: { key: "original-key", input } }),
  );
  transport.create = { agentId: "agent" };
  vi.mocked(transport.findRequest).mockResolvedValue(runFixture());
  const accepted = vi.fn();
  const { result } = renderHook(() =>
    useConversationController({
      id: "chat",
      transport,
      storageKey: "request",
      onAccepted: accepted,
    }),
  );
  await waitFor(() => expect(result.current.phase).toBe("streaming"));
  expect(transport.findRequest).toHaveBeenCalledWith(null, "original-key", expect.any(AbortSignal));
  expect(accepted).toHaveBeenCalledWith(
    input,
    expect.objectContaining({ conversation_id: "chat" }),
  );
  expect(transport.send).not.toHaveBeenCalled();
});
it("keeps one live subscription in StrictMode and closes resources on unmount", async () => {
  const { transport, openCount } = transportFixture(runFixture());
  const wrapper = ({ children }: { children: ReactNode }) => <StrictMode>{children}</StrictMode>;
  const view = renderHook(() => useConversationController({ id: "chat", transport }), { wrapper });
  await waitFor(() => expect(view.result.current.phase).toBe("streaming"));
  expect(openCount()).toBe(1);
  view.unmount();
  expect(openCount()).toBe(0);
});
it("does not leak a late accepted result into another conversation", async () => {
  const { transport } = transportFixture();
  transport.create = { agentId: "agent" };
  let accept!: (value: ReturnType<typeof runFixture>) => void;
  vi.mocked(transport.send).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        accept = resolve;
      }),
  );
  const view = renderHook(({ id }) => useConversationController({ id, transport }), {
    initialProps: { id: "chat" },
  });
  let sending!: Promise<void>;
  act(() => {
    sending = view.result.current.sendMessage({ content: "旧会话输入" });
  });
  view.rerender({ id: "another" });
  await act(async () => {
    accept(runFixture({ status: "queued" }));
    await sending;
  });
  expect(view.result.current.messages).toEqual([]);
});
it("keeps execution busy through bounded automatic reconnects and then offers manual recovery", async () => {
  const { transport, listeners } = transportFixture(runFixture());
  const { result } = renderHook(() => useConversationController({ id: "chat", transport }));
  await waitFor(() => expect(result.current.phase).toBe("streaming"));
  vi.useFakeTimers();
  for (const delay of [1000, 2000, 5000]) {
    await act(async () => {
      listeners.at(-1)!.disconnected();
    });
    expect(result.current.phase).toBe("streaming");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(delay);
    });
  }
  await act(async () => {
    listeners.at(-1)!.disconnected();
  });
  expect(result.current.connectionError?.recovery).toBe("reconnect");
  expect(transport.subscribe).toHaveBeenCalledTimes(4);
  expect(transport.send).not.toHaveBeenCalled();
});
it("does not claim that stopping succeeded when the cancellation request failed", async () => {
  const { transport } = transportFixture(runFixture());
  vi.mocked(transport.cancel).mockRejectedValue(new ApiError("取消确认失败", 0));
  const { result } = renderHook(() => useConversationController({ id: "chat", transport }));
  await waitFor(() => expect(result.current.phase).toBe("streaming"));
  await act(async () => {
    await result.current.stopMessage("a1");
  });
  expect(result.current.phase).toBe("streaming");
  expect(result.current.messages[1].run?.status).toBe("running");
  expect(result.current.messageOperations.a1.error).toBe("取消确认失败");
});
it("keeps a pending command confirmation across an observation reconnect", async () => {
  const { transport } = transportFixture();
  transport.create = { agentId: "agent" };
  let accept!: (value: ReturnType<typeof runFixture>) => void;
  vi.mocked(transport.send).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        accept = resolve;
      }),
  );
  const { result } = renderHook(() => useConversationController({ id: "chat", transport }));
  let sending!: Promise<void>;
  act(() => {
    sending = result.current.sendMessage({ content: "等待确认" });
  });
  act(() => result.current.reconnect());
  await waitFor(() => expect(transport.findRequest).toHaveBeenCalledTimes(1));
  await act(async () => {
    accept(
      runFixture({
        reply_to_message_id: "u2",
        id: "a2",
        status: "queued",
      }),
    );
    await sending;
  });
  expect(result.current.messages.at(-1)?.run?.id).toBe("a2");
  expect(result.current.phase).toBe("submitted");
  expect(transport.send).toHaveBeenCalledTimes(1);
});
it("releases a failed stop command after reconnect so stopping can be attempted again", async () => {
  const { transport } = transportFixture(runFixture());
  let reject!: (reason: Error) => void;
  vi.mocked(transport.cancel).mockImplementationOnce(
    () =>
      new Promise((_resolve, failure) => {
        reject = failure;
      }),
  );
  const { result } = renderHook(() => useConversationController({ id: "chat", transport }));
  await waitFor(() => expect(result.current.phase).toBe("streaming"));
  let stopping!: Promise<void>;
  act(() => {
    stopping = result.current.stopMessage("a1");
  });
  act(() => result.current.reconnect());
  await act(async () => {
    reject(new ApiError("取消确认失败", 0));
    await stopping;
  });
  await act(async () => {
    await result.current.stopMessage("a1");
  });
  expect(transport.cancel).toHaveBeenCalledTimes(2);
  expect(result.current.phase).toBe("ready");
});
it("hydrates body and steps from history without a separate run read", async () => {
  const saved = actionFixture({
    status: "succeeded",
    output_text: "中间过程",
    reasoning_text: "历史摘要",
  });
  const run = runFixture({
    status: "succeeded",
    content: "历史正文",
    steps: [saved],
  });
  const { transport } = transportFixture(run);
  const { result } = renderHook(() => useConversationController({ id: "chat", transport }));
  await waitFor(() => expect(result.current.phase).toBe("ready"));
  expect(result.current.messages[1].content).toBe("历史正文");
  expect(result.current.messages[1].run?.steps).toEqual([saved]);
  expect(transport.getSnapshot).toHaveBeenCalledOnce();
  expect(transport.getResponse).not.toHaveBeenCalled();
});
it("updates body and steps together, reuses old rows and rejects stale/terminal regressions", async () => {
  const completedStep = actionFixture({ id: "old", status: "succeeded", output_text: "旧轮次" });
  const currentStep = actionFixture({ sequence: 2 });
  const initial = runFixture({ steps: [completedStep, currentStep] });
  const { transport, listeners } = transportFixture(initial);
  const { result } = renderHook(() => useConversationController({ id: "chat", transport }));
  await waitFor(() => expect(result.current.phase).toBe("streaming"));
  const oldRow = result.current.messages[1].run!.steps[0];
  const update = runFixture({
    version: 2,
    content: "正文更新",
    steps: [
      { ...completedStep, safe_details: {} },
      { ...currentStep, output_text: "正文更新", reasoning_text: "步骤更新" },
    ],
  });
  act(() => listeners[0].snapshot(update));
  const message = result.current.messages[1];
  expect(message.content).toBe("正文更新");
  expect(message.run?.steps[1].reasoning_text).toBe("步骤更新");
  expect(message.run?.steps[0]).toBe(oldRow);
  act(() => {
    listeners[0].snapshot(initial);
    listeners[0].snapshot({ ...update });
  });
  expect(result.current.messages[1]).toBe(message);
  const finished = {
    ...update,
    version: 3,
    status: "cancelled" as const,
    steps: update.steps.map((step) => ({ ...step, status: "cancelled" })),
  };
  act(() => listeners[0].snapshot(finished));
  expect(result.current.messages[1].run?.steps[1].status).toBe("cancelled");
  act(() => listeners[0].snapshot({ ...update, version: 4 }));
  expect(result.current.messages[1].run?.status).toBe("cancelled");
});
it("does not let a late history response overwrite newer SSE text or steps", async () => {
  const initial = runFixture();
  const { transport, listeners } = transportFixture(initial);
  const { result } = renderHook(() => useConversationController({ id: "chat", transport }));
  await waitFor(() => expect(result.current.phase).toBe("streaming"));
  let resolve!: (snapshot: Awaited<ReturnType<typeof transport.getSnapshot>>) => void;
  vi.mocked(transport.getSnapshot).mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  act(() => result.current.reconnect());
  const newer = runFixture({
    version: 5,
    content: "更晚的正文",
    steps: [actionFixture({ output_text: "更晚的正文", reasoning_text: "更晚的步骤" })],
  });
  await waitFor(() => expect(transport.getSnapshot).toHaveBeenCalledTimes(2));
  act(() => listeners.at(-1)!.snapshot(newer));
  await act(async () => resolve(snapshotFixture(initial)));
  expect(result.current.messages[1].content).toBe("更晚的正文");
  expect(result.current.messages[1].run?.steps[0].reasoning_text).toBe("更晚的步骤");
});
it("recovers all final steps with the same snapshot when the SSE connection drops", async () => {
  const { transport, listeners } = transportFixture(runFixture());
  const { result } = renderHook(() => useConversationController({ id: "chat", transport }));
  await waitFor(() => expect(result.current.phase).toBe("streaming"));
  const final = runFixture({
    version: 3,
    status: "succeeded",
    content: "恢复的答案",
    steps: [actionFixture({ status: "succeeded", reasoning_text: "恢复的步骤" })],
  });
  vi.mocked(transport.getResponse).mockResolvedValue(final);
  await act(async () => listeners[0].disconnected());
  expect(result.current.messages[1].content).toBe("恢复的答案");
  expect(result.current.messages[1].run?.steps).toEqual(final.steps);
  expect(result.current.phase).toBe("ready");
  expect(transport.getSnapshot).toHaveBeenCalledOnce();
  expect(transport.send).not.toHaveBeenCalled();
});

it("rejects retrying a historical reply that the server marks read-only", async () => {
  const { transport } = transportFixture(runFixture({ status: "interrupted", can_retry: false }));
  const { result } = renderHook(() => useConversationController({ id: "chat", transport }));
  await waitFor(() => expect(result.current.phase).toBe("ready"));
  await expect(result.current.retryMessage("a1")).rejects.toThrow("不能重试");
  expect(transport.retry).not.toHaveBeenCalled();
});

it("can stop active work even when retry is unavailable", async () => {
  const { transport } = transportFixture(runFixture({ status: "running", can_retry: false }));
  const { result } = renderHook(() => useConversationController({ id: "chat", transport }));
  await waitFor(() => expect(result.current.phase).toBe("streaming"));
  await act(async () => {
    await result.current.stopMessage("a1");
  });
  expect(transport.cancel).toHaveBeenCalledWith("chat", "a1");
});
