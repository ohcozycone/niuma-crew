import { ApiError } from "@/lib/api/http";
// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { ConversationHistory } from "./ConversationHistory";
import { getConversations, type Conversation } from "@/lib/api/conversations";
import { executionTrace } from "@/lib/api/execution";
vi.mock("@/lib/api/execution", async (original) => ({
  ...(await original<object>()),
  executionTrace: vi.fn(() => new Promise(() => {})),
}));
vi.mock("@/lib/api/conversations", async (original) => ({
  ...(await original<object>()),
  getConversations: vi.fn(),
}));
vi.mock("@/state/auth/useIdentity", () => ({
  useIdentity: () => ({
    actor: { kind: "user", user: { id: "owner", username: "owner" } },
    permissions: ["conversations:read"],
    expires_at: "session",
  }),
}));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
function Location() {
  return <p data-testid="location">{useLocation().search}</p>;
}
const item = (id: string) =>
  ({
    id,
    title: `话题 ${id}`,
    agent_name: "老赵",
    updated_at: "2026-10-24T08:00:00Z",
    created_at: "2026-10-20T08:00:00Z",
    active_response_id: null,
  }) as Conversation;
it("keeps employee-history paging scoped in the URL and preserves the return context when switching", async () => {
  vi.mocked(getConversations).mockImplementation(async ({ offset = 0 } = {}) => ({
    items: [item(offset === 0 ? "current" : "older")],
    total: 26,
    offset,
    limit: 20,
  }));
  render(
    <MemoryRouter initialEntries={["/conversations/current?from=%2Fagents"]}>
      <Location />
      <ConversationHistory agentId="agent" activeId="current" returnTo="/agents" />
    </MemoryRouter>,
  );
  const current = await screen.findByRole("link", { name: /话题 current/ });
  expect(current.getAttribute("href")).toContain("/conversations/current");
  fireEvent.click(screen.getByRole("button", { name: "下一页" }));
  const older = await screen.findByRole("link", { name: /话题 older/ });
  expect(older.getAttribute("href")).toBe("/conversations/older?from=%2Fagents");
  expect(screen.getByTestId("location").textContent).toBe("?from=%2Fagents&history_offset=20");
  expect(screen.getByText("2 / 2")).toBeTruthy();
  expect((screen.getByRole("button", { name: "下一页" }) as HTMLButtonElement).disabled).toBe(true);
  expect(getConversations).toHaveBeenLastCalledWith(
    { agentId: "agent", offset: 20, q: "", status: "" },
    expect.any(AbortSignal),
  );
});
it("keeps full-history paging in the URL for browser navigation", async () => {
  vi.mocked(getConversations).mockImplementation(async ({ offset = 0 } = {}) => ({
    items: [item(String(offset))],
    total: 26,
    offset,
    limit: 20,
  }));
  render(
    <MemoryRouter initialEntries={["/conversations"]}>
      <Location />
      <ConversationHistory />
    </MemoryRouter>,
  );
  await screen.findByRole("link", { name: /话题 0/ });
  fireEvent.click(screen.getByRole("button", { name: "下一页" }));
  await screen.findByRole("link", { name: /话题 20/ });
  expect(screen.getByTestId("location").textContent).toBe("?offset=20");
});

it("keeps the last loaded history page visible when another page fails", async () => {
  vi.mocked(getConversations)
    .mockResolvedValueOnce({ items: [item("loaded")], total: 26, offset: 0, limit: 20 })
    .mockRejectedValueOnce(new ApiError("历史暂不可读", 503, "database_busy"));
  render(
    <MemoryRouter>
      <ConversationHistory />
    </MemoryRouter>,
  );
  await screen.findByRole("link", { name: /话题 loaded/ });
  fireEvent.click(screen.getByRole("button", { name: "下一页" }));
  expect((await screen.findByRole("alert")).textContent).toContain("历史暂不可读");
  expect(screen.getByRole("link", { name: /话题 loaded/ })).toBeTruthy();
});

it("searches the server result set, resets scoped paging and preserves other URL context", async () => {
  vi.mocked(getConversations).mockImplementation(async ({ q = "", offset = 0 } = {}) => ({
    items: [item(q || "original")],
    total: 1,
    offset,
    limit: 20,
  }));
  render(
    <MemoryRouter initialEntries={["/agents/agent/home?section=conversations&history_offset=20"]}>
      <Location />
      <ConversationHistory agentId="agent" />
    </MemoryRouter>,
  );
  await screen.findByText("话题 original");
  fireEvent.change(screen.getByRole("textbox", { name: "搜索对话主题或 ID" }), {
    target: { value: "报销" },
  });
  fireEvent.keyDown(screen.getByRole("textbox", { name: "搜索对话主题或 ID" }), { key: "Enter" });
  await screen.findByText("话题 报销");
  expect(getConversations).toHaveBeenLastCalledWith(
    { agentId: "agent", q: "报销", status: "", offset: 0 },
    expect.any(AbortSignal),
  );
  expect(screen.getByTestId("location").textContent).toContain("section=conversations");
  expect(screen.getByTestId("location").textContent).not.toContain("history_offset");
  expect(screen.getByText("新对话").closest("a")?.getAttribute("href")).not.toContain("resume");
});

it("shows the latest reply adoption state, both dates and explicit log/chat actions", async () => {
  vi.mocked(getConversations).mockResolvedValue({
    items: [
      {
        ...item("topic"),
        last_response_id: "reply",
        latest_response: { id: "reply", status: "succeeded", acceptance: "pending" },
      },
    ],
    total: 1,
    offset: 0,
    limit: 20,
  });
  render(
    <MemoryRouter>
      <ConversationHistory agentId="agent" />
    </MemoryRouter>,
  );
  await screen.findByText("话题 topic");
  expect(screen.getAllByText("保存中").length).toBeGreaterThan(0);
  expect(screen.queryByText("已回复")).toBeNull();
  expect(screen.getByText("创建于", { exact: false })).toBeTruthy();
  expect(screen.getByRole("button", { name: "查看话题 topic的执行日志" })).toBeTruthy();
  expect(screen.getByText("去对话").closest("a")?.getAttribute("href")).toBe(
    "/conversations/topic",
  );
  fireEvent.click(screen.getByRole("combobox", { name: "最近回复筛选" }));
  fireEvent.keyDown(await screen.findByRole("option", { name: "需关注" }), { key: "Enter" });
  await waitFor(() =>
    expect(getConversations).toHaveBeenLastCalledWith(
      { agentId: "agent", q: "", status: "attention", offset: 0 },
      expect.any(AbortSignal),
    ),
  );
});

it("opens the exact matching run in a dialog and keeps the history URL context on close", async () => {
  vi.mocked(getConversations).mockResolvedValue({
    items: [
      {
        ...item("100000000001"),
        last_response_id: "100000000003",
        matched_response_id: "100000000002",
      },
    ],
    total: 1,
    offset: 0,
    limit: 20,
  });
  render(
    <MemoryRouter
      initialEntries={["/agents/agent/home?section=conversations&history_q=100000000002"]}
    >
      <Location />
      <ConversationHistory agentId="agent" />
    </MemoryRouter>,
  );
  await screen.findByRole("button", { name: /查看话题 100000000001的执行日志/ });
  fireEvent.click(screen.getByRole("button", { name: /查看话题 100000000001的执行日志/ }));
  expect(await screen.findByRole("dialog", { name: "执行日志" })).toBeTruthy();
  expect(executionTrace).toHaveBeenCalledWith(
    "conversations/100000000001/responses/100000000002",
    0,
    "",
    expect.any(AbortSignal),
  );
  expect(screen.getByTestId("location").textContent).toContain("log_response=100000000002");
  expect(screen.getByTestId("location").textContent).toContain("history_q=100000000002");
  fireEvent.click(screen.getByRole("button", { name: "关闭" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(screen.getByTestId("location").textContent).toBe(
    "?section=conversations&history_q=100000000002",
  );
});
