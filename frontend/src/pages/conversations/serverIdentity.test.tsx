// @vitest-environment jsdom
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useConversationController } from "./useConversationController";
import { readConversationSession } from "./pendingSubmissionStorage";
import { runFixture, snapshotFixture, transportFixture } from "./conversationTestHelpers";
import type { Reply } from "@/lib/api/conversations";
import { ApiError } from "@/lib/api/http";

afterEach(() => {
  cleanup();
  sessionStorage.clear();
});

function serverFixture() {
  const conversationId = "100000000000";
  const reply = runFixture({
    conversation_id: conversationId,
    id: "100000000002",
    reply_to_message_id: "100000000001",
    status: "running",
  });
  const snapshot = snapshotFixture(reply);
  reply.scope = snapshot.conversation;
  const { transport } = transportFixture(reply);
  transport.create = { agentId: "agent" };
  vi.mocked(transport.send).mockResolvedValue(reply);
  vi.mocked(transport.getSnapshot).mockResolvedValue(snapshot);
  return { transport, reply, conversationId };
}

it("sends null and adopts the server identity before notifying navigation", async () => {
  const { transport, reply, conversationId } = serverFixture();
  const snapshot = snapshotFixture(reply);
  expect(snapshot.conversation.id).toBe(reply.conversation_id);
  expect(snapshot.messages.items[0].id).toBe(reply.reply_to_message_id);
  expect(
    snapshot.messages.items.every((message) => message.conversation_id === conversationId),
  ).toBe(true);
  expect(reply.steps.every((step) => step.run_id === reply.id)).toBe(true);
  const accepted = vi.fn(() => {
    expect(readConversationSession("draft-session").conversationId).toBe(conversationId);
  });
  const { result } = renderHook(() =>
    useConversationController({
      id: "draft:entry",
      transport,
      storageKey: "draft-session",
      onAccepted: accepted,
    }),
  );
  expect(transport.getSnapshot).not.toHaveBeenCalled();
  await act(() => result.current.sendMessage({ content: "第一问" }));
  expect(transport.send).toHaveBeenCalledWith(null, expect.any(Object), expect.any(String));
  expect(result.current.id).toBe(conversationId);
  expect(result.current.messages.map((message) => message.id)).toEqual([
    reply.reply_to_message_id,
    reply.id,
  ]);
  expect(accepted).toHaveBeenCalledWith(expect.objectContaining({ content: "第一问" }), reply);
  await waitFor(() =>
    expect(transport.subscribe).toHaveBeenCalledWith(conversationId, reply.id, expect.any(Object)),
  );
});

it("recovers a lost first receipt by request key without sending another command", async () => {
  const { transport, reply, conversationId } = serverFixture();
  sessionStorage.setItem(
    "lost",
    JSON.stringify({
      persisted: false,
      pending: { key: "original-request", input: { content: "第一问" } },
    }),
  );
  vi.mocked(transport.findRequest).mockResolvedValue(reply);
  const { result } = renderHook(() =>
    useConversationController({ id: "draft:entry", transport, storageKey: "lost" }),
  );
  await waitFor(() => expect(result.current.phase).toBe("streaming"));
  expect(transport.findRequest).toHaveBeenCalledWith(
    null,
    "original-request",
    expect.any(AbortSignal),
  );
  expect(transport.getSnapshot).toHaveBeenCalledWith(conversationId, expect.any(AbortSignal));
  expect(transport.send).not.toHaveBeenCalled();
  expect(readConversationSession("lost")).toMatchObject({ conversationId, pending: null });
});

it("applies a pending stop to the real conversation before notifying navigation", async () => {
  const { transport, reply, conversationId } = serverFixture();
  let accept!: (value: Reply) => void;
  vi.mocked(transport.send).mockImplementation(
    () =>
      new Promise((resolve) => {
        accept = resolve;
      }),
  );
  vi.mocked(transport.cancel).mockResolvedValue({ ...reply, version: 2, status: "cancelled" });
  const accepted = vi.fn();
  const { result } = renderHook(() =>
    useConversationController({
      id: "draft:entry",
      transport,
      storageKey: "stopping",
      onAccepted: accepted,
    }),
  );
  let sending!: Promise<void>;
  act(() => {
    sending = result.current.sendMessage({ content: "第一问" });
  });
  await act(() => result.current.cancelPending());
  await act(async () => {
    accept(reply);
    await sending;
  });
  expect(transport.cancel).toHaveBeenCalledWith(conversationId, reply.id);
  expect(vi.mocked(transport.cancel).mock.invocationCallOrder[0]).toBeLessThan(
    accepted.mock.invocationCallOrder[0],
  );
  expect(readConversationSession("stopping")).toMatchObject({ conversationId, pending: null });
});

it("retains a received server identity across a reload before route replacement", async () => {
  const { transport, conversationId } = serverFixture();
  sessionStorage.setItem(
    "received",
    JSON.stringify({ persisted: true, conversationId, pending: null }),
  );
  const { result } = renderHook(() =>
    useConversationController({ id: "draft:entry", transport, storageKey: "received" }),
  );
  await waitFor(() => expect(result.current.phase).toBe("streaming"));
  expect(transport.getSnapshot).toHaveBeenCalledWith(conversationId, expect.any(AbortSignal));
  expect(result.current.id).toBe(conversationId);
  expect(transport.send).not.toHaveBeenCalled();
});

it("keeps an unconfirmed first request without querying a local draft as a backend ID", async () => {
  const { transport } = serverFixture();
  sessionStorage.setItem(
    "unconfirmed",
    JSON.stringify({
      persisted: false,
      pending: { key: "original-request", input: { content: "第一问" } },
    }),
  );
  vi.mocked(transport.findRequest).mockResolvedValue(null);
  const { result } = renderHook(() =>
    useConversationController({
      id: "draft:entry",
      transport,
      storageKey: "unconfirmed",
    }),
  );
  await waitFor(() => expect(result.current.submissionError).toBeTruthy());
  expect(transport.getSnapshot).not.toHaveBeenCalled();
  expect(transport.send).not.toHaveBeenCalled();
  expect(readConversationSession("unconfirmed").pending?.key).toBe("original-request");
});

it("retries a persisted stop after receipt recovery and a failed cancellation", async () => {
  const { transport, reply, conversationId } = serverFixture();
  sessionStorage.setItem(
    "stop-recovery",
    JSON.stringify({
      persisted: false,
      pending: { key: "original-request", input: { content: "第一问" }, stopRequested: true },
    }),
  );
  vi.mocked(transport.findRequest).mockResolvedValue(reply);
  vi.mocked(transport.cancel).mockRejectedValueOnce(new TypeError("network"));
  const first = renderHook(() =>
    useConversationController({
      id: "draft:entry",
      transport,
      storageKey: "stop-recovery",
    }),
  );
  await waitFor(() => expect(transport.cancel).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(first.result.current.phase).toBe("streaming"));
  expect(readConversationSession("stop-recovery")).toMatchObject({
    conversationId,
    pending: { key: "original-request", stopRequested: true },
  });
  first.unmount();
  vi.mocked(transport.cancel).mockResolvedValueOnce({ ...reply, status: "cancelled", version: 2 });
  renderHook(() =>
    useConversationController({
      id: "draft:entry",
      transport,
      storageKey: "stop-recovery",
    }),
  );
  await waitFor(() => expect(transport.cancel).toHaveBeenCalledTimes(2));
  await waitFor(() => expect(readConversationSession("stop-recovery").pending).toBeNull());
  expect(transport.cancel).toHaveBeenLastCalledWith(conversationId, reply.id);
});

it("reports a missing conversation during request reconciliation instead of offering a resend", async () => {
  const { transport } = serverFixture();
  sessionStorage.setItem(
    "missing-request",
    JSON.stringify({
      persisted: false,
      pending: { key: "original-request", input: { content: "第一问" } },
    }),
  );
  vi.mocked(transport.findRequest).mockRejectedValue(
    new ApiError("对话不存在", 404, "conversation_not_found"),
  );
  const { result } = renderHook(() =>
    useConversationController({
      id: "draft:entry",
      transport,
      storageKey: "missing-request",
    }),
  );
  await waitFor(() =>
    expect(result.current.connectionError?.failure?.code).toBe("conversation_not_found"),
  );
  expect(result.current.connectionError?.recovery).toBeNull();
  expect(result.current.submissionError).toBeNull();
  expect(transport.send).not.toHaveBeenCalled();
  expect(transport.getSnapshot).not.toHaveBeenCalled();
});
