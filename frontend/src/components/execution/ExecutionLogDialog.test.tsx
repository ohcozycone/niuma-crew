// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { ExecutionLogDialog } from "./ExecutionLogDialog";
import { executionTrace, type ExecutionAction, type ExecutionTrace } from "@/lib/api/execution";

const session = vi.hoisted(() => ({ id: "admin" }));
vi.mock("@/state/auth/useIdentity", () => ({
  useIdentity: () => ({
    actor: { kind: "user", user: { id: session.id, username: session.id } },
    expires_at: "later",
    permissions: ["runs:read"],
  }),
}));
vi.mock("@/lib/api/execution", async (original) => ({
  ...(await original<typeof import("@/lib/api/execution")>()),
  executionTrace: vi.fn(),
}));
const actions: ExecutionAction[] = [
  {
    id: "model",
    sequence: 1,
    action_key: "model:1",
    parent_action_id: null,
    kind: "model_call",
    status: "succeeded",
    safe_details: { round: 1 },
    output_text: "",
    reasoning_text: "",
    reasoning_truncated: false,
    error_code: null,
    started_at: "2026-11-05T00:00:00Z",
    finished_at: "2026-11-05T00:00:02Z",
  },
  {
    id: "tool",
    sequence: 2,
    action_key: "tool:read",
    parent_action_id: "model",
    kind: "tool_call",
    status: "succeeded",
    safe_details: { tool: "read_file" },
    output_text: "",
    reasoning_text: "",
    reasoning_truncated: false,
    error_code: null,
    started_at: "2026-11-05T00:00:02Z",
    finished_at: "2026-11-05T00:00:03Z",
  },
];
function fixture(action = "model"): ExecutionTrace {
  return {
    run: {
      id: "100000000002",
      agent_id: "employee",
      origin_kind: "conversation",
      status: "succeeded",
      revision: 3,
      error_code: null,
      started_at: null,
      finished_at: null,
      usage: null,
    },
    configuration: { agent_revision: 9, model_id: "glm-test", schema_version: 1 },
    can_inspect_inputs: true,
    actions: { items: actions, offset: 0, limit: 100, total: 2 },
    selected: {
      ...actions.find((item) => item.id === action)!,
      request: {
        status: "available",
        size: 100,
        content_hash: "hash",
        document: {
          schema_version: 1,
          capture_stage: action === "model" ? "wire_request" : "tool_request",
          payload:
            action === "model"
              ? {
                  messages: [
                    { role: "system", content: "任何问题都只回答我不知道" },
                    { role: "user", content: "如何报销？" },
                  ],
                }
              : {
                  requested_arguments: { file_path: "/inputs/rules.txt" },
                  authorization_status: "allowed",
                },
        },
      },
      response: {
        status: "available",
        size: 30,
        content_hash: "hash",
        document: {
          schema_version: 1,
          capture_stage: action === "model" ? "sdk_response" : "tool_response",
          payload: { content: "工具已返回制度正文" },
        },
      },
      saved_tool_feedback: null,
    },
    logs: { items: [], limit: 200, status: "not_collected" },
  };
}
function view() {
  return (
    <MemoryRouter>
      <ExecutionLogDialog
        target={{ conversationId: "100000000000", responseId: "100000000002" }}
        onClose={() => {}}
      />
    </MemoryRouter>
  );
}
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  session.id = "admin";
});

it("shows actual input, follows tools and keeps evidence associated with the response", async () => {
  vi.mocked(executionTrace).mockImplementation(async (_base, _offset, action) =>
    fixture(action || "model"),
  );
  render(view());
  expect(await screen.findByRole("region", { name: "执行概况" })).toBeTruthy();
  fireEvent.click(screen.getByRole("tab", { name: "模型请求" }));
  fireEvent.click(screen.getByText(/1. 系统指令/));
  expect(await screen.findByText("任何问题都只回答我不知道")).toBeTruthy();
  expect(screen.getByText(/1. 系统指令/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: /2. read_file/ }));
  await screen.findByRole("tab", { name: "调用参数" });
  fireEvent.click(screen.getByRole("tab", { name: "调用参数" }));
  expect(await screen.findByText("模型申请的参数")).toBeTruthy();
  expect(screen.queryByText("任何问题都只回答我不知道")).toBeNull();
  expect(screen.getByRole("link", { name: /下载完整 JSON/ }).getAttribute("href")).toBe(
    "/api/conversations/100000000000/responses/100000000002/trace/actions/tool/evidence/request",
  );
  fireEvent.click(screen.getByRole("tab", { name: /返回/ }));
  expect(
    (await screen.findAllByText("工具已返回制度正文", { exact: true })).length,
  ).toBeGreaterThan(0);
  expect(screen.queryByText("未收到可展示的思考内容。")).toBeNull();
});

it("labels missing historical evidence and restricted inputs", async () => {
  const value = fixture();
  value.selected!.request = { status: "not_collected" };
  value.selected!.response = { status: "restricted" };
  vi.mocked(executionTrace).mockResolvedValue(value);
  render(view());
  await screen.findByRole("region", { name: "执行概况" });
  expect(await screen.findByText(/历史执行不会补造输入或响应/)).toBeTruthy();
  expect(await screen.findByText(/完整输入与工具证据需要/)).toBeTruthy();
  expect(screen.queryByRole("tab")).toBeNull();
  expect(screen.queryByRole("link", { name: /下载完整 JSON/ })).toBeNull();
});

it("drops old identity data and ignores its delayed response", async () => {
  let finish: (value: ExecutionTrace) => void = () => {};
  vi.mocked(executionTrace)
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    )
    .mockResolvedValue({
      ...fixture(),
      selected: { ...fixture().selected!, request: { status: "restricted" } },
    });
  const mounted = render(view());
  await waitFor(() => expect(executionTrace).toHaveBeenCalledTimes(1));
  session.id = "member";
  mounted.rerender(view());
  await screen.findByRole("region", { name: "执行概况" });
  expect(await screen.findByText(/完整输入与工具证据需要/)).toBeTruthy();
  finish(fixture());
  await waitFor(() => expect(screen.queryByText("任何问题都只回答我不知道")).toBeNull());
});

it("uses the assessment association without creating a conversation", async () => {
  const value = fixture();
  value.run.origin_kind = "evaluation";
  vi.mocked(executionTrace).mockResolvedValue(value);
  render(
    <MemoryRouter>
      <ExecutionLogDialog
        target={{ agentId: "employee", batchId: "batch", caseId: "case" }}
        onClose={() => {}}
      />
    </MemoryRouter>,
  );
  expect(await screen.findByText("考题执行")).toBeTruthy();
  expect(executionTrace).toHaveBeenCalledWith(
    "evaluations/batch/cases/case",
    0,
    "",
    expect.any(AbortSignal),
  );
  expect(screen.queryByText(/对话交付/)).toBeNull();
});

it("focuses a failed action and keeps recorded token totals visible", async () => {
  vi.mocked(executionTrace).mockImplementation(async (_base, _offset, action) => {
    const value = fixture(action || "model");
    value.run.usage = { input_tokens: 9128, output_tokens: 599, total_tokens: 9727 };
    value.actions.items = actions.map((item) =>
      item.id === "tool" ? { ...item, status: "failed", error_code: "tool_result_unknown" } : item,
    );
    return value;
  });
  render(view());
  await waitFor(() =>
    expect(executionTrace).toHaveBeenCalledWith(
      expect.any(String),
      0,
      "tool",
      expect.any(AbortSignal),
    ),
  );
  expect(screen.getByText("9,727")).toBeTruthy();
  expect(screen.getByRole("button", { name: /定位步骤 2/ })).toBeTruthy();
});

it("aborts reads when the dialog closes and does not restore delayed content", async () => {
  let finish: (value: ExecutionTrace) => void = () => {};
  vi.mocked(executionTrace).mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const onClose = vi.fn();
  const mounted = render(
    <MemoryRouter>
      <ExecutionLogDialog target={{ conversationId: "100000000000" }} onClose={onClose} />
    </MemoryRouter>,
  );
  await waitFor(() => expect(executionTrace).toHaveBeenCalledTimes(1));
  const signal = vi.mocked(executionTrace).mock.calls[0][3];
  fireEvent.click(screen.getByRole("button", { name: "关闭" }));
  expect(onClose).toHaveBeenCalledTimes(1);
  mounted.rerender(
    <MemoryRouter>
      <ExecutionLogDialog target={null} onClose={onClose} />
    </MemoryRouter>,
  );
  expect(signal.aborted).toBe(true);
  await act(async () => finish(fixture()));
  expect(screen.queryByRole("dialog")).toBeNull();
});

it("shows complete model response first and keeps the thinking text collapsed", async () => {
  const value = fixture();
  value.selected!.reasoning_text = "THINKING_TEXT";
  value.selected!.response.document!.payload = {
    content: "COMPLETE_RESULT",
    usage: { input_tokens: 10 },
  };
  vi.mocked(executionTrace).mockResolvedValue(value);
  render(view());
  await screen.findByText("COMPLETE_RESULT");
  expect(screen.getByRole("tab", { name: "完整响应" }).getAttribute("aria-selected")).toBe("true");
  const disclosure = screen.getByText("模型思考文本").closest("details")!;
  expect(disclosure.open).toBe(false);
  expect(within(disclosure).getByText("THINKING_TEXT")).toBeTruthy();
  expect(screen.queryByText("动作元数据")).toBeNull();
  expect(screen.queryByRole("tab", { name: "技术日志" })).toBeNull();
});

it("renders knowledge records without empty request, response or metadata tabs", async () => {
  const value = fixture();
  const knowledge = {
    ...actions[0],
    kind: "knowledge",
    safe_details: { query: "报销制度", sources: [] },
  };
  value.actions.items = [knowledge];
  value.selected = {
    ...knowledge,
    request: { status: "not_collected" },
    response: { status: "not_collected" },
    saved_tool_feedback: null,
  };
  vi.mocked(executionTrace).mockResolvedValue(value);
  render(view());
  expect(await screen.findByRole("heading", { name: "知识检索记录" })).toBeTruthy();
  expect(screen.getByText("报销制度")).toBeTruthy();
  expect(screen.queryByRole("tab")).toBeNull();
  expect(screen.queryByText("动作元数据")).toBeNull();
  expect(within(screen.getByRole("region", { name: "动作详情" })).queryByText("未提供")).toBeNull();
});

it("locates failures beyond the visible action page and connects the exact runtime event", async () => {
  const value = fixture("tool");
  const failed = {
    ...actions[1],
    sequence: 102,
    status: "failed",
    error_code: "tool_upstream_failed",
  };
  value.run.status = "failed";
  value.run.error_code = "tool_upstream_failed";
  value.actions = { items: [actions[0]], total: 102, offset: 0, limit: 100 };
  value.failures = { items: [failed], total: 1 };
  value.selected = { ...value.selected!, ...failed };
  value.logs = {
    status: "available",
    limit: 200,
    items: [
      {
        time: actions[1].finished_at!,
        level: "ERROR",
        event: "tool.finished",
        action_key: failed.action_key,
        error_code: failed.error_code,
        source: "tool_calls.py:123:invoke",
      },
    ],
  };
  vi.mocked(executionTrace).mockResolvedValue(value);
  render(view());
  const error = within(await screen.findByRole("region", { name: "错误定位" }));
  expect(error.getByRole("button", { name: /定位步骤 102.*read_file/ })).toBeTruthy();
  expect(error.getByText(/事件记录位置：tool_calls.py:123:invoke/)).toBeTruthy();
  expect(await screen.findByText("已定位步骤（当前分页之外）")).toBeTruthy();
  expect(screen.queryByRole("tab", { name: "技术日志" })).toBeNull();
});

it("labels run-level errors without inventing a failed model or tool location", async () => {
  const value = fixture();
  value.run.status = "failed";
  value.run.error_code = "execution_failed";
  value.logs = {
    status: "available",
    limit: 200,
    items: [
      {
        time: actions[1].finished_at!,
        level: "ERROR",
        event: "execution.failed",
        action_key: null,
        error_code: "execution_failed",
        source: "task.py:193:execute",
        frames: "task.py:125:execute <- factory.py:21:create",
      },
    ],
  };
  vi.mocked(executionTrace).mockResolvedValue(value);
  render(view());
  const error = within(await screen.findByRole("region", { name: "错误定位" }));
  expect(error.getByText("执行级事件（未关联具体步骤）")).toBeTruthy();
  expect(error.getByText(/task.py:193:execute/)).toBeTruthy();
  expect(error.queryByRole("button", { name: /定位步骤/ })).toBeNull();
});
