import { ApiError, request } from "@/lib/api/http";
// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, act } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MemoryRouter, Routes, Route } from "react-router";
import { ConversationPanel } from "./ConversationPanel";
import * as api from "@/lib/api/conversations";
import { runFixture, snapshotFixture } from "./conversationTestHelpers";
vi.mock("@/state/auth/useIdentity", () => ({
  useIdentity: () => ({
    actor: { kind: "user", user: { id: "u", username: "tester" } },
    permissions: ["agents:read"],
    expires_at: "2099",
  }),
}));
vi.mock("@/lib/api/http", async (original) => ({
  ...(await original<object>()),
  request: vi.fn(async (path: string) => {
    if (path === "agents/agent")
      return {
        id: "agent",
        name: "老赵",
        description: "",
        example_tasks: "",
        avatar_id: "programmer-horse",
        is_active: true,
        model_connection_id: "brain",
        skill_assignments: [],
      };
    if (path === "conversations/chat/files" || path === "conversations/100000000000/files")
      return [];
    throw new Error(`Unexpected request: ${path}`);
  }),
}));
const observedReply = vi.hoisted(() => ({ receive: null as ((reply: api.Reply) => void) | null }));
vi.mock("@/pages/conversations/useResponseSubscription", () => ({
  useResponseSubscription: (
    _id: string,
    _reply: string | null,
    _transport: unknown,
    receive: (reply: api.Reply) => void,
  ) => {
    observedReply.receive = receive;
  },
}));
vi.mock("@/components/avatars/index", () => ({ AgentAvatar: () => null }));
vi.mock("@/components/common/Markdown", () => ({
  Markdown: ({ text }: { text: string }) => <div>{text}</div>,
}));
vi.mock("@/lib/api/conversations", async (original) => ({
  ...(await original<object>()),
  getSnapshot: vi.fn(),
  getMessages: vi.fn(),
  getQuestions: vi.fn(async () => ({ items: [], total: 0, next_after_sequence: null })),
  getConversations: vi.fn(async () => ({ items: [], total: 0, offset: 0, limit: 20 })),
  sendMessage: vi.fn(),
}));
const inputMessage = (sequence: number, content = `消息 ${sequence}`): api.UserMessage => ({
  id: String(sequence),
  sequence,
  role: "user",
  content,
  conversation_id: "chat",
  created_at: "2026-11-04T00:00:00Z",
  updated_at: "2026-11-04T00:00:00Z",
});
const message = (sequence: number, content = `消息 ${sequence}`): api.ChatMessage => ({
  ...inputMessage(sequence, content),
  run: null,
  published: true,
});
const latest = { items: [message(51), message(52)], next_before_sequence: 51, has_more: true };
beforeEach(() => {
  vi.mocked(api.getSnapshot).mockResolvedValue({
    conversation: {
      ...snapshotFixture(runFixture()).conversation,
      title: "已有对话",
      last_response_id: null,
      active_response_id: null,
    },
    agent: { id: "agent", name: "老赵", avatar_id: "admin" },
    messages: {
      ...latest,
      items: latest.items.map((item) => inputMessage(item.sequence, item.content)),
    },
    question_count: 2,
    latest_question_id: "52",
  });
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
it("keeps the draft identity local and loads files only after the first message creates a conversation", async () => {
  const id = "100000000000";
  const uploaded = {
    id: "00000000-0000-4000-8000-000000000001",
    name: "input.csv",
    size: 3,
    media_type: "text/csv",
    content_hash: "hash",
    purpose: "input",
  };
  const run = runFixture({ conversation_id: id });
  const snapshot = snapshotFixture(run);
  vi.mocked(api.sendMessage).mockResolvedValue({ ...run, scope: snapshot.conversation });
  vi.mocked(api.getSnapshot).mockResolvedValue(snapshot);
  render(
    <MemoryRouter initialEntries={["/conversations/new?agent=agent"]}>
      <Routes>
        <Route
          path="/conversations/new"
          element={<ConversationPanel key="draft" id="draft:entry:agent" agentId="agent" />}
        />
        <Route path="/conversations/:id" element={<ConversationPanel key={id} id={id} />} />
      </Routes>
    </MemoryRouter>,
  );
  await screen.findByRole("textbox", { name: "消息" });
  expect(vi.mocked(request).mock.calls.filter(([path]) => path.endsWith("/files"))).toEqual([]);
  expect(api.getSnapshot).not.toHaveBeenCalled();
  expect(screen.queryByRole("alert")).toBeNull();

  vi.mocked(request).mockResolvedValueOnce(uploaded);
  fireEvent.change(screen.getByLabelText("上传输入文件"), {
    target: { files: [new File(["a,b"], uploaded.name, { type: "text/csv" })] },
  });
  await screen.findByText(uploaded.name);
  expect(request).toHaveBeenCalledWith("files?name=input.csv", {
    method: "POST",
    headers: { "Content-Type": "text/csv" },
    body: expect.any(File),
    signal: expect.any(AbortSignal),
  });
  fireEvent.change(screen.getByRole("textbox", { name: "消息" }), {
    target: { value: "检查附件" },
  });
  fireEvent.click(screen.getByRole("button", { name: "发送" }));
  await waitFor(() =>
    expect(api.sendMessage).toHaveBeenCalledWith(
      null,
      "检查附件",
      expect.any(String),
      [],
      "agent",
      [uploaded.id],
    ),
  );
  await waitFor(() =>
    expect(request).toHaveBeenCalledWith(`conversations/${id}/files`, {
      signal: expect.any(AbortSignal),
    }),
  );
  await waitFor(() => expect(api.getSnapshot).toHaveBeenCalledWith(id, expect.any(AbortSignal)));
  expect(vi.mocked(request).mock.calls.some(([path]) => path.includes("draft:"))).toBe(false);
  expect(screen.queryByRole("alert")).toBeNull();
});
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
  expect(api.getMessages).toHaveBeenCalledTimes(1);
  expect(vi.mocked(api.getMessages).mock.calls[0][1]).toBe(51);
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
  expect(vi.mocked(api.getMessages).mock.calls.map((call) => call[1])).toEqual([51, 51]);
});
it("aborts an older-page request when leaving the conversation", async () => {
  vi.mocked(api.getMessages).mockImplementationOnce(() => new Promise(() => {}));
  const view = open();
  fireEvent.click(await screen.findByRole("button", { name: "加载更早消息" }));
  const signal = vi.mocked(api.getMessages).mock.calls[0][2];
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
  const signal = vi.mocked(api.getMessages).mock.calls[0][2];
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

it("clears the sidebar running badge when the same reply is accepted", async () => {
  const running: api.Conversation = {
    id: "chat",
    agent_id: "agent",
    agent_name: "老赵",
    owner_user_id: "u",
    title: "部署验证话题",
    version: 7,
    active_response_id: "a1",
    last_response_id: "a1",
    created_at: "2026-11-04T00:00:00Z",
    updated_at: "2026-11-04T00:00:00Z",
  };
  const completed = { ...running, version: 8, active_response_id: null };
  let saved = running;
  vi.mocked(api.getConversations).mockImplementation(async () => ({
    items: [saved],
    total: 1,
    offset: 0,
    limit: 20,
  }));
  vi.mocked(api.getSnapshot).mockResolvedValueOnce({
    conversation: running,
    agent: { id: "agent", name: "老赵", avatar_id: "admin" },
    messages: {
      items: [
        {
          id: "u1",
          conversation_id: "chat",
          sequence: 1,
          role: "user",
          content: "测试问题",
          created_at: running.created_at,
          updated_at: running.updated_at,
        },
        runFixture({ scope: running, content: "", status: "running" }),
      ],
      next_before_sequence: null,
      has_more: false,
    },
    question_count: 1,
    latest_question_id: "u1",
  });
  open();
  const history = await screen.findByRole("link", { name: /部署验证话题/ });
  expect(history.textContent).toContain("执行中");
  saved = completed;
  act(() =>
    observedReply.receive?.(
      runFixture({
        scope: completed,
        version: 2,
        status: "succeeded",
        acceptance: "accepted",
        content: "正式回答",
      }),
    ),
  );
  await screen.findByText("正式回答");
  await waitFor(() =>
    expect(screen.getByRole("link", { name: /部署验证话题/ }).textContent).not.toContain("执行中"),
  );
});

it("moves a saved server identity and pending stop together before replacing the draft route", async () => {
  const { identityKey } = await import("@/lib/identity");
  const { conversationSessionKey } = await import("./conversationDraft");
  const { readConversationSession, saveConversationSession } =
    await import("./pendingSubmissionStorage");
  const owner = identityKey({
    actor: { kind: "user", user: { id: "u", username: "tester" } },
    permissions: ["agents:read"],
    expires_at: "2099",
  });
  const id = "100000000000";
  const session = {
    persisted: true,
    conversationId: id,
    pending: { key: "first-request", input: { content: "第一问" }, stopRequested: true },
  };
  saveConversationSession(conversationSessionKey(owner, "draft:entry"), session);
  render(
    <MemoryRouter initialEntries={["/new"]}>
      <Routes>
        <Route path="/new" element={<ConversationPanel id="draft:entry" agentId="agent" />} />
        <Route path="/conversations/:id" element={<p>真实对话页面</p>} />
      </Routes>
    </MemoryRouter>,
  );
  await screen.findByText("真实对话页面");
  expect(readConversationSession(conversationSessionKey(owner, id))).toEqual(session);
  expect(api.sendMessage).not.toHaveBeenCalled();
});
