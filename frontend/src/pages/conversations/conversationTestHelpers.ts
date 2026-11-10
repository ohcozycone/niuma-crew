import { vi } from "vitest";
import {
  isActive,
  isPublished,
  type Conversation,
  type ConversationSnapshot,
  type Reply,
  type ChatMessage,
  type ReplyStep,
} from "@/lib/api/conversations";
import type { ConversationTransport } from "@/lib/api/conversationTransport";
export function actionFixture(overrides: Partial<ReplyStep> = {}): ReplyStep {
  return {
    id: "step",
    run_id: "a1",
    sequence: 1,
    action_key: "model:1",
    call_key: "model:1",
    parent_action_id: null,
    kind: "model_call",
    status: "running",
    skill_id: null,
    safe_details: {},
    output_text: "回答",
    reasoning_text: "",
    reasoning_truncated: false,
    result_ref: null,
    error_code: null,
    started_at: "2026-10-24T00:00:01Z",
    finished_at: null,
    ...overrides,
  };
}
/** 仅供本模块测试，字段与当前服务端响应保持一致。 */
export function runFixture(overrides: Partial<Reply> = {}): Reply {
  const value: Reply = {
    role: "assistant",
    sequence: 2,
    can_retry: ["failed", "cancelled", "interrupted"].includes(overrides.status ?? "running"),
    content_state: "draft",
    updated_at: "2026-10-24T00:00:01Z",
    conversation_id: "chat",
    reply_to_message_id: "u1",
    id: "a1",
    retry_of_response_id: null,
    status: "running",
    version: 1,
    steps: [actionFixture({ run_id: overrides.id ?? "a1" })],
    content: "回答",
    error: null,
    usage: null,
    created_at: "2026-10-24T00:00:00Z",
    started_at: "2026-10-24T00:00:01Z",
    finished_at: null,
    ...overrides,
  };
  if (overrides.content_state === undefined) {
    value.content_state = !value.content
      ? "empty"
      : isActive(value.status) || value.acceptance === "pending"
        ? "draft"
        : value.status === "succeeded"
          ? "complete"
          : "partial";
  }
  return value;
}
export function messageFixture(id: string, role: "user" | "assistant", run: Reply): ChatMessage {
  return {
    id,
    role,
    sequence: role === "user" ? 1 : run.sequence,
    conversation_id: run.conversation_id,
    content: role === "user" ? "问题" : run.content,
    run: role === "user" ? null : run,
    published: role === "user" || isPublished(run),
    created_at: run.created_at,
    updated_at: run.created_at,
  };
}
export function snapshotFixture(run: Reply): ConversationSnapshot {
  const conversation: Conversation = {
    id: run.conversation_id,
    agent_id: "agent",
    agent_name: "员工",
    owner_user_id: "owner",
    title: "测试对话",
    version: 1,
    last_response_id: run.id,
    active_response_id: isActive(run.status) ? run.id : null,
    created_at: run.created_at,
    updated_at: run.created_at,
  };
  return {
    conversation,
    agent: { id: conversation.agent_id, name: conversation.agent_name, avatar_id: "admin" },
    messages: {
      items: [{ ...messageFixture(run.reply_to_message_id, "user", run), role: "user" }, run],
      next_before_sequence: null,
      has_more: false,
    },
    question_count: 1,
    latest_question_id: run.reply_to_message_id,
  };
}
export function transportFixture(run = runFixture({ status: "succeeded", content: "已保存回答" })) {
  const listeners: Array<Parameters<ConversationTransport["subscribe"]>[2]> = [];
  let open = 0;
  const transport: ConversationTransport = {
    getSnapshot: vi.fn(async () => snapshotFixture(run)),
    getMessages: vi.fn(async () => ({
      items: [
        messageFixture(run.reply_to_message_id, "user", run),
        messageFixture(run.id, "assistant", run),
      ],
      next_before_sequence: null,
      has_more: false,
    })),
    getResponse: vi.fn(async () => run),
    send: vi.fn(async () =>
      runFixture({
        reply_to_message_id: "u2",
        id: "a2",
        status: "queued",
      }),
    ),
    retry: vi.fn(async () =>
      runFixture({
        id: "a2",
        retry_of_response_id: run.id,
        status: "queued",
      }),
    ),
    cancel: vi.fn(async () => ({
      ...run,
      version: run.version + 1,
      status: "cancelled" as const,
      can_retry: true,
    })),
    findRequest: vi.fn(async () => null),
    subscribe: vi.fn((_conversationId, _id, listener) => {
      listeners.push(listener);
      open += 1;
      let closed = false;
      return () => {
        if (!closed) {
          closed = true;
          open -= 1;
        }
      };
    }),
  };
  return { transport, listeners, openCount: () => open };
}
