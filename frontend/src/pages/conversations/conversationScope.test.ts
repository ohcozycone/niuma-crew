import { expect, it } from "vitest";
import { conversationReducer, type ConversationState } from "./conversationState";
import { runFixture } from "./conversationTestHelpers";
import type { Conversation } from "@/lib/api/conversations";
it("keeps the current scope and latest reply when an older acceptance or snapshot arrives late", () => {
  const old = runFixture({ id: "old", version: 2, status: "failed", content: "旧失败" });
  const current = runFixture({ id: "current", version: 1, status: "queued", content: "" });
  const scope: Conversation = {
    id: "chat",
    agent_id: "agent",
    agent_name: "员工",
    owner_user_id: "owner",
    title: "对话",
    version: 4,
    active_response_id: "current",
    last_response_id: "current",
    created_at: old.created_at,
    updated_at: old.updated_at,
  };
  const olderScope = { ...scope, version: 2, active_response_id: null, last_response_id: "old" };
  const initial: ConversationState = {
    id: "chat",
    conversation: scope,
    run: current,
    messages: [old, current].map((reply) => ({
      id: reply.id,
      role: "assistant",
      content: reply.content,
      published: reply.status === "failed",
      run: reply,
    })),
    loading: false,
    submitting: false,
    pending: null,
    submissionError: null,
    connectionError: null,
    cursor: null,
    loadingOlder: false,
    historyError: null,
  };
  const accepted = conversationReducer(initial, {
    type: "accepted",
    command: { key: "old-key" },
    run: { ...old, scope: olderScope },
  });
  expect(accepted.conversation).toBe(scope);
  expect(accepted.run?.id).toBe("current");
  const stalePage = conversationReducer(accepted, {
    type: "loaded",
    conversation: olderScope,
    messages: [],
    cursor: null,
    run: old,
  });
  expect(stalePage.conversation?.active_response_id).toBe("current");
  expect(stalePage.run?.id).toBe("current");
});
