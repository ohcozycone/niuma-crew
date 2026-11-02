import { expect, it, vi, afterEach } from "vitest";
import {
  answerContent,
  activityLabel,
  sendMessage,
  type AcceptedSubmission,
} from "./conversations";
import { safeReturnPath } from "@/lib/navigation";
import type { Reply, ReplyStep } from "./conversations";
const actionFixture = (overrides: Partial<ReplyStep> = {}): ReplyStep => ({
  id: "step",
  run_id: "internal",
  sequence: 1,
  action_key: "model:1",
  call_key: "model:1",
  parent_action_id: null,
  kind: "model_call",
  status: "running",
  skill_id: null,
  safe_details: {},
  output_text: "",
  reasoning_text: "",
  reasoning_truncated: false,
  result_ref: null,
  error_code: null,
  started_at: "2026-10-27T00:00:00Z",
  finished_at: null,
  ...overrides,
});
const runFixture = (overrides: Partial<Reply> = {}): Reply => ({
  id: "reply",
  conversation_id: "chat",
  sequence: 2,
  role: "assistant",
  reply_to_message_id: "u1",
  version: 1,
  status: "running",
  content: "",
  content_state: "empty",
  steps: [],
  usage: null,
  error: null,
  context: { pair_count: 0, truncated: false },
  can_retry: true,
  created_at: "2026-10-27T00:00:00Z",
  updated_at: "2026-10-27T00:00:00Z",
  started_at: null,
  finished_at: null,
  ...overrides,
});

afterEach(() => vi.unstubAllGlobals());
it("keeps conversation deep links and rejects invented routes", () => {
  const path = "/conversations/a9f87713-3f79-4c6d-bfc7-3dd42d3fc640";
  expect(safeReturnPath(path)).toBe(path);
  expect(safeReturnPath(path + "/secret")).toBe("/");
});
it("displays the selected server content without interpreting model rounds", () => {
  const reply = runFixture({ content: "已保存草稿" });
  expect(answerContent(reply)).toBe("已保存草稿");
  expect(
    answerContent({
      ...reply,
      content: "",
      steps: [
        actionFixture({ output_text: "工具调用前的话", safe_details: { has_tool_calls: true } }),
      ],
    }),
  ).toBe("");
  expect(
    activityLabel({
      ...reply,
      steps: [
        actionFixture({
          kind: "tool_call",
          skill_id: "skill",
          safe_details: { tool: "read_file" },
        }),
      ],
    }),
  ).toBe("正在读取技能");
});
it("sends to messages and retains the scope supplied with acceptance", async () => {
  const response = runFixture({ status: "queued", content: "" });
  const conversation = {
    id: "chat",
    agent_id: "agent",
    agent_name: "员工",
    owner_user_id: "owner",
    title: "问题",
    version: 2,
    active_response_id: response.id,
    last_response_id: response.id,
    created_at: response.created_at,
    updated_at: response.updated_at,
  };
  const accepted: AcceptedSubmission = {
    conversation,
    response,
    client_request_id: "key",
    input_message: {
      id: "u1",
      conversation_id: "chat",
      sequence: 1,
      role: "user",
      content: "问题",
      created_at: response.created_at,
      updated_at: response.updated_at,
    },
  };
  const fetch = vi.fn<typeof globalThis.fetch>(async () => Response.json(accepted));
  vi.stubGlobal("fetch", fetch);
  const result = await sendMessage("chat", "问题", "key");
  expect(fetch.mock.calls[0][0]).toContain("conversations/chat/messages");
  expect(result.scope).toEqual(conversation);
  expect(result.id).toBe(response.id);
});
