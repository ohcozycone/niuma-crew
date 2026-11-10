import { ApiError } from "@/lib/api/http";
// @vitest-environment jsdom
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { ChatMessage, MessagePage } from "@/lib/api/conversations";
import { fromMessage } from "./conversationState";
import { transportFixture } from "./conversationTestHelpers";
import { useConversationHistory } from "./useConversationHistory";
afterEach(cleanup);
const dto = (sequence: number): ChatMessage =>
  ({
    id: `m${sequence}`,
    sequence,
    role: sequence % 2 ? "user" : "assistant",
    content: `内容 ${sequence}`,
    conversation_id: "chat",
    run: null,
  }) as ChatMessage;
const page = (
  start: number,
  end: number,
  before: number | null,
  after: number | null,
): MessagePage => ({
  items: Array.from({ length: end - start + 1 }, (_, i) => dto(start + i)),
  next_before_sequence: before,
  next_after_sequence: after,
  has_more: before !== null,
});
function setup() {
  const { transport } = transportFixture();
  const latestHistory = {
    hasMore: true,
    isLoading: false,
    error: null,
    loadMore: vi.fn(async () => {}),
    cancel: vi.fn(),
  };
  const live = page(91, 100, 91, null).items.map(fromMessage);
  const refreshLatest = vi.fn(async () => {});
  const view = renderHook(
    ({ messages }) =>
      useConversationHistory({ id: "chat", transport, messages, latestHistory, refreshLatest }),
    { initialProps: { messages: live } },
  );
  return { ...view, transport, latestHistory, live, refreshLatest };
}
it("loads a distant window directly, fills both directions without gaps and restores the live cache", async () => {
  const { result, transport, live } = setup();
  vi.mocked(transport.getMessages).mockResolvedValueOnce(page(41, 50, 41, 50));
  await act(async () => {
    expect(await result.current.jump("m45")).toBe(true);
  });
  expect(transport.getMessages).toHaveBeenLastCalledWith(
    "chat",
    undefined,
    expect.any(AbortSignal),
    { around: "m45" },
  );
  expect(result.current.messages.map((m) => m.id)).toEqual(
    page(41, 50, 41, 50).items.map((m) => m.id),
  );
  expect(result.current.messages.some((m) => m.id === "m91")).toBe(false);
  vi.mocked(transport.getMessages).mockResolvedValueOnce(page(31, 41, 31, 41));
  await act(async () => {
    await result.current.loadMore();
  });
  expect(result.current.messages.map((m) => m.id)).toEqual(
    page(31, 50, 31, 50).items.map((m) => m.id),
  );
  vi.mocked(transport.getMessages).mockResolvedValueOnce(page(51, 60, 51, 60));
  await act(async () => {
    await result.current.loadNewer();
  });
  expect(transport.getMessages).toHaveBeenLastCalledWith(
    "chat",
    undefined,
    expect.any(AbortSignal),
    { after: 50 },
  );
  expect(result.current.messages).toHaveLength(30);
  await act(async () => {
    await result.current.showLatest();
  });
  expect(result.current.messages).toBe(live);
  expect(result.current.position?.target).toBe("end");
});
it("keeps historical reading independent while live snapshots update and merges overlapping live messages", async () => {
  const { result, transport, live, rerender } = setup();
  vi.mocked(transport.getMessages).mockResolvedValueOnce(page(81, 94, 81, 94));
  await act(async () => {
    await result.current.jump("m85");
  });
  const latest = live.map((m) =>
    m.id === "m94" || m.id === "m100" ? { ...m, content: "新快照" } : m,
  );
  rerender({ messages: latest });
  expect(result.current.messages.at(-1)?.id).toBe("m94");
  expect(result.current.messages.at(-1)?.content).toBe("新快照");
  await act(async () => {
    await result.current.showLatest();
  });
  expect(result.current.messages.at(-1)?.content).toBe("新快照");
});
it("honors the last jump even if an aborted response arrives late", async () => {
  const { result, transport } = setup();
  let old!: (page: MessagePage) => void;
  vi.mocked(transport.getMessages).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        old = resolve;
      }),
  );
  let first!: Promise<boolean>;
  act(() => {
    first = result.current.jump("m1");
  });
  const signal = vi.mocked(transport.getMessages).mock.calls[0][2];
  vi.mocked(transport.getMessages).mockResolvedValueOnce(page(41, 50, 41, 50));
  await act(async () => {
    await result.current.jump("m45");
  });
  expect(signal?.aborted).toBe(true);
  await act(async () => {
    old(page(1, 10, null, 10));
    await first;
  });
  expect(result.current.position?.target).toBe("m45");
  expect(result.current.messages[0].id).toBe("m41");
});
it("retains the old window and cursor on failure, retries and cancels on latest/unmount", async () => {
  const { result, transport, live, unmount } = setup();
  vi.mocked(transport.getMessages).mockRejectedValueOnce(
    new ApiError("无法读取", 503, "database_busy"),
  );
  await act(async () => {
    expect(await result.current.jump("m1")).toBe(false);
  });
  expect(result.current.messages).toBe(live);
  expect(result.current.error).toBe("无法读取");
  vi.mocked(transport.getMessages).mockResolvedValueOnce(page(1, 10, null, 10));
  await act(async () => {
    await result.current.jump("m1");
  });
  vi.mocked(transport.getMessages).mockRejectedValueOnce(
    new ApiError("稍后重试", 503, "database_busy"),
  );
  await act(async () => {
    await result.current.loadNewer();
  });
  vi.mocked(transport.getMessages).mockImplementationOnce(() => new Promise(() => {}));
  act(() => {
    void result.current.loadNewer();
  });
  expect(transport.getMessages).toHaveBeenLastCalledWith(
    "chat",
    undefined,
    expect.any(AbortSignal),
    { after: 10 },
  );
  const scope = vi.mocked(transport.getMessages).mock.calls.at(-1)![2];
  await act(async () => {
    await result.current.showLatest();
  });
  expect(scope?.aborted).toBe(true);
  act(() => {
    void result.current.jump("m1");
  });
  const last = vi.mocked(transport.getMessages).mock.calls.at(-1)![2];
  unmount();
  expect(last?.aborted).toBe(true);
});
it("jumps to a loaded question without fetching and leaves pagination unlocked", async () => {
  const { result, transport, latestHistory } = setup();
  await act(async () => {
    expect(await result.current.jump("m95")).toBe(true);
  });
  expect(transport.getMessages).not.toHaveBeenCalled();
  expect(result.current.position?.target).toBe("m95");
  await act(async () => {
    await result.current.loadMore();
  });
  expect(latestHistory.loadMore).toHaveBeenCalledOnce();
});
it("keeps the reading window when refreshing latest fails and retries without sending", async () => {
  const { result, transport, refreshLatest } = setup();
  vi.mocked(transport.getMessages).mockResolvedValueOnce(page(1, 10, null, 10));
  await act(async () => {
    await result.current.jump("m1");
  });
  refreshLatest.mockRejectedValueOnce(new ApiError("最新页读取失败", 503, "database_busy"));
  await act(async () => {
    await result.current.showLatest();
  });
  expect(result.current.isHistorical).toBe(true);
  expect(result.current.messages[0].id).toBe("m1");
  expect(result.current.error).toBe("最新页读取失败");
  await act(async () => {
    await result.current.showLatest();
  });
  expect(refreshLatest).toHaveBeenCalledTimes(2);
  expect(result.current.messages[0].id).toBe("m91");
  expect(transport.send).not.toHaveBeenCalled();
});
