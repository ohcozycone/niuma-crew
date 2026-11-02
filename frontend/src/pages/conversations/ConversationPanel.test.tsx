import { ApiError } from "@/lib/api/http";
// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, act } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { ConversationPanel } from "./ConversationPanel";
import * as api from "@/lib/api/conversations";
import { runFixture } from "./conversationTestHelpers";
vi.mock("@/state/auth/useIdentity", () => ({
  useIdentity: () => ({
    actor: { kind: "user", user: { id: "u", username: "tester" } },
    permissions: ["agents:read"],
    expires_at: "2099",
  }),
}));
vi.mock("@/lib/api/http", async (original) => ({
  ...(await original<object>()),
  request: vi.fn(async (path: string) =>
    path.endsWith("/messages")
      ? api.sendMessage("chat", "新问题", "key")
      : {
          id: "agent",
          name: "老赵",
          avatar_id: "programmer-horse",
          is_active: true,
          model_connection_id: "brain",
          skill_assignments: [],
        },
  ),
}));
vi.mock("@/pages/conversations/useResponseSubscription", () => ({
  useResponseSubscription: () => "",
}));
vi.mock("@/components/avatars/index", () => ({ AgentAvatar: () => null }));
vi.mock("@/components/common/Markdown", () => ({
  Markdown: ({ text }: { text: string }) => <div>{text}</div>,
}));
vi.mock("@/lib/api/conversations", async (original) => ({
  ...(await original<object>()),
  getSnapshot: vi.fn(async (id, signal) => {
    const conversation = await api.getConversation(id, signal);
    const page = await api.getMessages(id, undefined, signal);
    return {
      conversation,
      agent: { id: "agent", name: "老赵", avatar_id: "admin" },
      messages: { ...page, items: page.items.map((m) => m.run ?? { ...m, role: "user" as const }) },
      question_count: page.items.length,
      latest_question_id: null,
    };
  }),
  getConversation: vi.fn(),
  getMessages: vi.fn(),
  getQuestions: vi.fn(async () => ({ items: [], total: 0, next_after_sequence: null })),
  getConversations: vi.fn(async () => ({ items: [], total: 0, offset: 0, limit: 20 })),
  createConversation: vi.fn(),
  sendMessage: vi.fn(),
}));
const message = (sequence: number, content = `消息 ${sequence}`) =>
  ({ id: String(sequence), sequence, role: "user", content, run: null }) as api.ChatMessage;
const latest = { items: [message(51), message(52)], next_before_sequence: 51, has_more: true };
beforeEach(() => {
  vi.mocked(api.getConversation).mockResolvedValue({
    id: "chat",
    agent_id: "agent",
    title: "已有对话",
  } as api.Conversation);
  vi.mocked(api.getMessages).mockResolvedValueOnce(latest);
  Element.prototype.scrollTo = vi.fn();
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  sessionStorage.clear();
});
const open = () =>
  render(
    <MemoryRouter>
      <ConversationPanel id="chat" />
    </MemoryRouter>,
  );
it("opens the sidebar by default and preserves the conversation when switching or closing it", async () => {
  open();
  await screen.findByText("消息 52");
  expect(screen.getByRole("complementary", { name: "员工对话与能力" })).toBeTruthy();
  fireEvent.click(screen.getByRole("tab", { name: "员工能力" }));
  expect(await screen.findByText("暂未挂载技能")).toBeTruthy();
  expect(screen.getByText("消息 52")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "收起侧栏" }));
  expect(screen.queryByRole("complementary", { name: "员工对话与能力" })).toBeNull();
  const toggle = screen.getByRole("button", { name: "展开侧栏" });
  expect(document.activeElement).toBe(toggle);
  fireEvent.click(toggle);
  expect(screen.getByRole("tab", { name: "历史对话" }).getAttribute("aria-selected")).toBe("true");
  expect(screen.getByText("消息 52")).toBeTruthy();
  expect(api.getSnapshot).toHaveBeenCalledTimes(1);
});
it("locks overlapping history loads, deduplicates prepended rows and retains current text", async () => {
  let resolve!: (page: api.MessagePage) => void;
  vi.mocked(api.getMessages).mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  open();
  const load = await screen.findByRole("button", { name: "加载更早消息" });
  fireEvent.click(load);
  fireEvent.click(load);
  expect(api.getMessages).toHaveBeenCalledTimes(2);
  expect(vi.mocked(api.getMessages).mock.calls[1][1]).toBe(51);
  await act(async () =>
    resolve({
      items: [message(50), message(51, "过期的重复消息")],
      next_before_sequence: null,
      has_more: false,
    }),
  );
  expect(screen.getByText("消息 50")).toBeTruthy();
  expect(screen.getAllByText("消息 51")).toHaveLength(1);
  expect(screen.queryByText("过期的重复消息")).toBeNull();
  expect(screen.queryByRole("button", { name: "加载更早消息" })).toBeNull();
});
it("keeps the message transcript usable when the sidebar history cannot load", async () => {
  vi.mocked(api.getConversations).mockRejectedValueOnce(
    new ApiError("对话列表暂不可读", 503, "database_busy"),
  );
  open();
  expect(await screen.findByText("消息 52")).toBeTruthy();
  expect((await screen.findByRole("alert")).textContent).toContain("对话列表暂不可读");
  expect(screen.getByRole("button", { name: "加载更早消息" })).toBeTruthy();
});
it("keeps the current page on a history error and retries the same cursor", async () => {
  vi.mocked(api.getMessages).mockRejectedValueOnce(
    new ApiError("历史读取暂时失败", 503, "database_busy"),
  );
  open();
  fireEvent.click(await screen.findByRole("button", { name: "加载更早消息" }));
  expect((await screen.findByRole("alert")).textContent).toContain("历史读取暂时失败");
  expect(screen.getByText("消息 52")).toBeTruthy();
  vi.mocked(api.getMessages).mockResolvedValueOnce({
    items: [message(50)],
    next_before_sequence: null,
    has_more: false,
  });
  fireEvent.click(screen.getByRole("button", { name: "加载失败，点击重试" }));
  await screen.findByText("消息 50");
  expect(
    vi
      .mocked(api.getMessages)
      .mock.calls.slice(1)
      .map((call) => call[1]),
  ).toEqual([51, 51]);
});
it("aborts an older-page request when leaving the conversation", async () => {
  vi.mocked(api.getMessages).mockImplementationOnce(() => new Promise(() => {}));
  const view = open();
  fireEvent.click(await screen.findByRole("button", { name: "加载更早消息" }));
  const signal = vi.mocked(api.getMessages).mock.calls[1][2];
  view.unmount();
  expect(signal?.aborted).toBe(true);
});
it("requests older messages near the top without creating a conversation", async () => {
  vi.mocked(api.getMessages).mockResolvedValueOnce({
    items: [message(50)],
    next_before_sequence: null,
    has_more: false,
  });
  open();
  await screen.findByText("消息 52");
  const viewport = screen.getByRole("region", { name: "对话消息" });
  await waitFor(() => expect(viewport.hasAttribute("data-pending-scroll")).toBe(false));
  Object.defineProperties(viewport, {
    scrollTop: { configurable: true, value: 40 },
    scrollHeight: { configurable: true, value: 1500 },
    clientHeight: { configurable: true, value: 600 },
  });
  fireEvent.scroll(viewport);
  await screen.findByText("消息 50");
  expect(api.createConversation).not.toHaveBeenCalled();
});
it("cancels in-flight history when sending so a stale page cannot replace the new cursor", async () => {
  let resolve!: (page: api.MessagePage) => void;
  vi.mocked(api.getMessages).mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  vi.mocked(api.sendMessage).mockResolvedValue(
    runFixture({
      conversation_id: "chat",
      reply_to_message_id: "53",
      id: "54",
      status: "succeeded",
      content: "回答完成",
    }),
  );
  open();
  fireEvent.click(await screen.findByRole("button", { name: "加载更早消息" }));
  const signal = vi.mocked(api.getMessages).mock.calls[1][2];
  fireEvent.change(screen.getByRole("textbox", { name: "消息" }), { target: { value: "新问题" } });
  fireEvent.click(screen.getByRole("button", { name: "发送" }));
  await screen.findByText("新问题");
  expect(signal?.aborted).toBe(true);
  await act(async () =>
    resolve({ items: [message(1, "迟到的历史")], next_before_sequence: null, has_more: false }),
  );
  expect(screen.queryByText("迟到的历史")).toBeNull();
  expect(screen.getByRole("button", { name: "加载更早消息" })).toBeTruthy();
});

it("retires the old mode URL without offering a diagnostic form or submitting work", async () => {
  render(
    <MemoryRouter initialEntries={["/conversations/chat?work=ci"]}>
      <ConversationPanel id="chat" />
    </MemoryRouter>,
  );
  expect(
    await screen.findByText("CI 诊断入口已移除，旧草稿已清理。请重新输入普通消息。"),
  ).toBeTruthy();
  expect(screen.queryByRole("textbox", { name: "失败运行链接" })).toBeNull();
  expect(screen.queryByRole("combobox", { name: "工作方式" })).toBeNull();
  expect(screen.getByRole("textbox", { name: "消息" })).toHaveProperty("value", "");
  expect(api.sendMessage).not.toHaveBeenCalled();
});

it("shows an initial snapshot failure without presenting an empty new conversation", async () => {
  vi.mocked(api.getSnapshot).mockRejectedValueOnce(
    new ApiError("对话不存在", 404, "conversation_not_found"),
  );
  open();
  expect(await screen.findByRole("heading", { name: "没找到这条对话记录" })).toBeTruthy();
  expect(screen.queryByText("与老赵开始对话")).toBeNull();
  expect(screen.getByText("返回对话记录").closest("a")?.getAttribute("href")).toBe(
    "/conversations",
  );
  expect(api.sendMessage).not.toHaveBeenCalled();
});
