// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import {
  agentPage,
  patchAgent,
  fromAgentSummary,
  getAgent,
  type AgentSummaryDTO,
} from "@/lib/api/agents";
import { ApiError, request } from "@/lib/api/http";
import { useWorkspaceData } from "@/state/workspace/useWorkspaceData";
import { WorkspaceDataProvider } from "@/state/workspace/WorkspaceDataProvider";
import { useNavigationSummary } from "@/components/navigation/useNavigationSummary";
import { useEditing } from "@/state/editing/useEditing";
import type { Agent } from "@/lib/models/agent";
import { AgentsPage } from "./AgentsPage";

let userId = "owner";
vi.mock("@/state/auth/useIdentity", () => ({
  useIdentity: () => ({
    actor: { kind: "user", user: { id: userId, username: "admin" } },
    expires_at: "2099",
    permissions: ["agents:read", "skills:read"],
  }),
}));
vi.mock("@/lib/api/agents", async (original) => ({
  ...(await original<object>()),
  agentPage: vi.fn(),
  patchAgent: vi.fn(),
  getAgent: vi.fn(),
}));
vi.mock("@/lib/api/http", async (original) => ({
  ...(await original<object>()),
  request: vi.fn(),
}));

function employee(id: string, configured = true): AgentSummaryDTO {
  return {
    id,
    code: null,
    name: id,
    avatar_id: "admin",
    category: "研发协作",
    description: "员工摘要",
    role_label: null,
    model_connection_id: configured ? "brain" : null,
    is_active: true,
    is_favorite: true,
    resource_counts: { skills: 0, tools: 0, knowledge_bases: 0 },
    skill_summaries: [],
    revision: 1,
    updated_at: "2026-10-29T00:00:00Z",
  };
}
function page(items: AgentSummaryDTO[], total = items.length) {
  return { items, total, offset: 0, limit: 20 };
}
function saved(id: string, favorite: boolean, revision = 2): Agent {
  return {
    ...fromAgentSummary(employee(id)),
    favorite,
    revision,
    systemPrompt: "",
    configurationLoaded: true,
    exampleTasks: [],
    deliverables: [],
  };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
function NavigationProbe() {
  const summary = useNavigationSummary();
  return (
    <output aria-label="侧栏收藏">{summary.favorites.map((item) => item.name).join("、")}</output>
  );
}
function RefreshProbe() {
  const data = useWorkspaceData();
  return (
    <button
      onClick={() =>
        data.agents.page(new URLSearchParams({ offset: "0", limit: "20", q: "" })).refresh()
      }
    >
      测试重新读取
    </button>
  );
}
function SavingProbe() {
  const editing = useEditing();
  return <output aria-label="全局保存">{String(editing.saving)}</output>;
}
function directoryTree(entry = "/agents", navigation = false) {
  return (
    <MemoryRouter initialEntries={[entry]}>
      <WorkspaceDataProvider>
        {navigation && <NavigationProbe />}
        <SavingProbe />
        <RefreshProbe />
        <AgentsPage />
      </WorkspaceDataProvider>
    </MemoryRouter>
  );
}
function directory(entry = "/agents", navigation = false) {
  return render(directoryTree(entry, navigation));
}
beforeEach(() => {
  userId = "owner";
  vi.mocked(request).mockResolvedValue({ agents: 45, skills: 0, favorites: 8 });
  vi.mocked(agentPage).mockResolvedValue(page([employee("原始员工")], 45));
});

it("loads the global count independently when opening a filtered URL directly", async () => {
  vi.mocked(agentPage).mockResolvedValueOnce(page([employee("收藏员工")], 8));
  directory("/agents?filter=favorites");
  await screen.findByRole("tab", { name: "全部员工 45" });
  expect(screen.getByRole("tab", { name: "已收藏" }).getAttribute("aria-selected")).toBe("true");
  expect(screen.getByText("共 8 位员工 · 本页 1 位可对话")).toBeTruthy();
});

it("keeps search focus and resets pagination while a search request is pending", async () => {
  directory("/agents?offset=20");
  await screen.findByRole("tab", { name: "全部员工 45" });
  const search = screen.getByRole("textbox", { name: "筛选员工" });
  const next = deferred<Awaited<ReturnType<typeof agentPage>>>();
  vi.mocked(agentPage).mockReturnValueOnce(next.promise);
  vi.useFakeTimers();
  act(() => search.focus());
  fireEvent.change(search, { target: { value: "财" } });
  await act(async () => vi.advanceTimersByTimeAsync(200));
  fireEvent.change(search, { target: { value: "财务" } });
  await act(async () => vi.advanceTimersByTimeAsync(299));
  expect(agentPage).toHaveBeenCalledTimes(1);
  await act(async () => vi.advanceTimersByTimeAsync(1));
  expect(agentPage).toHaveBeenCalledTimes(2);
  expect(screen.getByLabelText("员工列表").getAttribute("aria-busy")).toBe("true");
  expect(screen.getByRole("textbox", { name: "筛选员工" })).toBe(search);
  expect(document.activeElement).toBe(search);
  const query = vi.mocked(agentPage).mock.lastCall?.[0];
  expect(query?.get("q")).toBe("财务");
  expect(query?.get("offset")).toBe("0");
  await act(async () => next.resolve(page([employee("财务员工")], 1)));
  expect(screen.getByText("共 1 位员工 · 本页 1 位可对话")).toBeTruthy();
  expect(screen.getByRole("tab", { name: "全部员工 45" })).toBeTruthy();
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.resetAllMocks();
});

it("keeps tabs and search mounted and separates global, filtered and page counts", async () => {
  vi.mocked(agentPage).mockResolvedValueOnce(
    page(
      Array.from({ length: 20 }, (_, i) => employee(`员工${i}`, i < 15)),
      45,
    ),
  );
  directory();
  const all = await screen.findByRole("tab", { name: "全部员工 45" });
  const search = screen.getByRole("textbox", { name: "筛选员工" });
  const favorites = screen.getByRole("tab", { name: "已收藏" });
  expect(screen.getByText("共 45 位员工 · 本页 15 位可对话")).toBeTruthy();
  const next = deferred<Awaited<ReturnType<typeof agentPage>>>();
  vi.mocked(agentPage).mockReturnValueOnce(next.promise);
  fireEvent.click(favorites);
  act(() => favorites.focus());
  await waitFor(() =>
    expect(screen.getByLabelText("员工列表").getAttribute("aria-busy")).toBe("true"),
  );
  expect(screen.getByText(/正在更新…/)).toBeTruthy();
  const retainedCard = screen.getByRole("article", { name: "员工0" });
  expect(retainedCard.closest("[inert], [aria-hidden='true'], .opacity-0")).toBeNull();
  expect(screen.getByRole("tab", { name: "全部员工 45" })).toBe(all);
  expect(screen.getByRole("textbox", { name: "筛选员工" })).toBe(search);
  expect(document.activeElement).toBe(favorites);
  expect(screen.getByRole("heading", { name: "员工0" })).toBeTruthy();
  expect((screen.getByRole("button", { name: "下一页" }) as HTMLButtonElement).disabled).toBe(true);
  await act(async () => next.resolve(page([employee("收藏员工")], 8)));
  expect(screen.getByText("共 8 位员工 · 本页 1 位可对话")).toBeTruthy();
  expect(screen.getByRole("tab", { name: "全部员工 45" })).toBe(all);
  expect(document.activeElement).toBe(favorites);
  expect(request).toHaveBeenCalledTimes(1);
  expect(agentPage).toHaveBeenLastCalledWith(expect.any(URLSearchParams), expect.any(AbortSignal));
  expect(vi.mocked(agentPage).mock.lastCall?.[0].get("is_favorite")).toBe("true");
});

it("ignores late results after rapid tab changes and preserves the global count", async () => {
  directory();
  await screen.findByRole("tab", { name: "全部员工 45" });
  const older = deferred<Awaited<ReturnType<typeof agentPage>>>();
  const latest = deferred<Awaited<ReturnType<typeof agentPage>>>();
  vi.mocked(agentPage).mockReturnValueOnce(older.promise).mockReturnValueOnce(latest.promise);
  fireEvent.click(screen.getByRole("tab", { name: "已收藏" }));
  await waitFor(() => expect(agentPage).toHaveBeenCalledTimes(2));
  const olderSignal = vi.mocked(agentPage).mock.calls[1][1];
  fireEvent.click(screen.getByRole("tab", { name: "已暂停" }));
  await waitFor(() => expect(agentPage).toHaveBeenCalledTimes(3));
  expect(olderSignal?.aborted).toBe(true);
  await act(async () => latest.resolve(page([], 0)));
  await act(async () => older.resolve(page([employee("迟到员工")], 8)));
  expect(screen.queryByRole("heading", { name: "迟到员工" })).toBeNull();
  expect(screen.getByRole("tab", { name: "已暂停" }).getAttribute("aria-selected")).toBe("true");
  expect(screen.getByRole("tab", { name: "全部员工 45" })).toBeTruthy();
  expect(screen.getByText("没有找到符合条件的员工")).toBeTruthy();
  expect(screen.getByText("共 0 位员工 · 本页 0 位可对话")).toBeTruthy();
});

it("keeps controls after failure and clears the error when a new filter succeeds", async () => {
  directory();
  const all = await screen.findByRole("tab", { name: "全部员工 45" });
  vi.mocked(agentPage).mockRejectedValueOnce(new Error("筛选读取失败"));
  fireEvent.click(screen.getByRole("tab", { name: "已收藏" }));
  await screen.findByRole("alert");
  expect(screen.getByRole("tab", { name: "全部员工 45" })).toBe(all);
  expect(screen.getByRole("heading", { name: "原始员工" })).toBeTruthy();
  expect(screen.getByText(/更新失败，仍显示上次结果/)).toBeTruthy();
  vi.mocked(agentPage).mockResolvedValueOnce(page([employee("可用员工")], 2));
  fireEvent.click(screen.getByRole("tab", { name: "可对话" }));
  await screen.findByRole("heading", { name: "可用员工" });
  expect(screen.queryByRole("alert")).toBeNull();
  vi.mocked(agentPage).mockResolvedValueOnce(page([employee("恢复的收藏员工")], 8));
  fireEvent.click(screen.getByRole("tab", { name: "已收藏" }));
  await screen.findByRole("heading", { name: "恢复的收藏员工" });
  expect(screen.queryByRole("alert")).toBeNull();
});

it("hides the previous identity's data until the next identity has loaded", async () => {
  const view = directory();
  await screen.findByRole("heading", { name: "原始员工" });
  const next = deferred<Awaited<ReturnType<typeof agentPage>>>();
  vi.mocked(agentPage).mockReturnValueOnce(next.promise);
  userId = "another-owner";
  view.rerender(directoryTree());
  expect(screen.queryByRole("heading", { name: "原始员工" })).toBeNull();
  expect(screen.queryByRole("tab")).toBeNull();
  await act(async () => next.resolve(page([employee("新身份员工")], 1)));
  await screen.findByRole("heading", { name: "新身份员工" });
});

it("does not substitute the filtered page length when the global count fails", async () => {
  vi.mocked(request).mockRejectedValueOnce(new ApiError("总数读取失败", 503, "database_busy"));
  directory();
  await screen.findByRole("heading", { name: "原始员工" });
  expect(screen.getByRole("tab", { name: "全部员工 —" })).toBeTruthy();
  expect(screen.getByRole("alert").textContent).toContain("总数读取失败");
  vi.mocked(request).mockResolvedValueOnce({ agents: 45, skills: 0, favorites: 8 });
  fireEvent.click(screen.getByRole("button", { name: "重新加载" }));
  await screen.findByRole("tab", { name: "全部员工 45" });
  expect(screen.queryByRole("alert")).toBeNull();
});

it("updates one card immediately and synchronizes the shared favorites page without reloading the directory", async () => {
  let favoriteConfirmed = false;
  vi.mocked(agentPage).mockImplementation(async (query) =>
    query.get("is_favorite") === "true"
      ? page(
          favoriteConfirmed ? [{ ...employee("员工A"), revision: 2 }] : [],
          favoriteConfirmed ? 9 : 8,
        )
      : page([{ ...employee("员工A"), is_favorite: false }, employee("员工B")], 45),
  );
  directory("/agents", true);
  const favorite = await screen.findByRole("button", { name: "收藏员工A" });
  const otherCard = screen.getByRole("article", { name: "员工B" });
  const write = deferred<Agent>();
  vi.mocked(patchAgent).mockReturnValueOnce(write.promise);
  fireEvent.click(favorite);
  fireEvent.click(favorite);
  expect(favorite.getAttribute("aria-pressed")).toBe("true");
  expect((favorite as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "员工A的更多操作" }));
  expect(
    (await screen.findByRole("menuitem", { name: "暂停接单" })).getAttribute("aria-disabled"),
  ).toBe("true");
  expect((screen.getByRole("button", { name: "收藏员工B" }) as HTMLButtonElement).disabled).toBe(
    false,
  );
  expect(screen.getByRole("menuitem", { name: "编辑配置" }).hasAttribute("aria-disabled")).toBe(
    false,
  );
  fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });
  await waitFor(() => expect(screen.queryByRole("menu")).toBeNull());
  expect(screen.getByLabelText("全局保存").textContent).toBe("false");
  expect(patchAgent).toHaveBeenCalledTimes(1);
  favoriteConfirmed = true;
  await act(async () => write.resolve(saved("员工A", true)));
  await waitFor(() => expect(screen.getByLabelText("侧栏收藏").textContent).toBe("员工A"));
  expect(screen.getByRole("article", { name: "员工B" })).toBe(otherCard);
  expect(
    vi.mocked(agentPage).mock.calls.filter(([query]) => query.get("is_favorite") !== "true"),
  ).toHaveLength(1);
  expect(request).toHaveBeenCalledTimes(1);
  vi.mocked(patchAgent).mockResolvedValueOnce(saved("员工A", false, 3));
  fireEvent.click(favorite);
  await waitFor(() => expect(patchAgent).toHaveBeenCalledTimes(2));
  expect(patchAgent).toHaveBeenLastCalledWith("员工A", { is_favorite: false }, 2);
});

it("allows independent writes to different employees and handles reverse completion", async () => {
  vi.mocked(agentPage).mockResolvedValueOnce(page([employee("员工A"), employee("员工B")]));
  directory();
  const a = await screen.findByRole("button", { name: "收藏员工A" });
  const first = deferred<Agent>();
  const second = deferred<Agent>();
  vi.mocked(patchAgent).mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
  fireEvent.click(a);
  fireEvent.click(screen.getByRole("button", { name: "收藏员工B" }));
  expect(patchAgent).toHaveBeenCalledTimes(2);
  await act(async () => second.resolve(saved("员工B", false)));
  expect((a as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByRole("button", { name: "收藏员工B" }) as HTMLButtonElement).disabled).toBe(
    false,
  );
  await act(async () => first.resolve(saved("员工A", false)));
  expect(a.getAttribute("aria-pressed")).toBe("false");
  expect(screen.getByRole("button", { name: "收藏员工B" }).getAttribute("aria-pressed")).toBe(
    "false",
  );
  expect(agentPage).toHaveBeenCalledTimes(1);
});

it("rolls back a rejected favorite and keeps the card available for retry", async () => {
  directory();
  const favorite = await screen.findByRole("button", { name: "收藏原始员工" });
  const write = deferred<Agent>();
  vi.mocked(patchAgent).mockReturnValueOnce(write.promise);
  fireEvent.click(favorite);
  expect(favorite.getAttribute("aria-pressed")).toBe("false");
  await act(async () => write.reject(new ApiError("服务暂不可用", 422, "invalid_input")));
  expect(favorite.getAttribute("aria-pressed")).toBe("true");
  expect((favorite as HTMLButtonElement).disabled).toBe(false);
  expect(screen.getByRole("article", { name: "原始员工" }).textContent).toContain("服务暂不可用");
  expect(agentPage).toHaveBeenCalledTimes(1);
  vi.mocked(patchAgent).mockResolvedValueOnce(saved("原始员工", false));
  fireEvent.click(favorite);
  await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  expect(favorite.getAttribute("aria-pressed")).toBe("false");
});

it("reconciles a revision conflict without automatically repeating the write", async () => {
  directory();
  const favorite = await screen.findByRole("button", { name: "收藏原始员工" });
  vi.mocked(patchAgent).mockRejectedValueOnce(new ApiError("配置已变更", 409));
  vi.mocked(getAgent).mockResolvedValueOnce(saved("原始员工", true, 3));
  fireEvent.click(favorite);
  await waitFor(() => expect(getAgent).toHaveBeenCalledTimes(1));
  await waitFor(() =>
    expect(screen.getByLabelText("员工列表").getAttribute("aria-busy")).toBe("false"),
  );
  expect(patchAgent).toHaveBeenCalledTimes(1);
  expect(favorite.getAttribute("aria-pressed")).toBe("true");
  vi.mocked(patchAgent).mockResolvedValueOnce(saved("原始员工", false, 4));
  fireEvent.click(favorite);
  await waitFor(() => expect(patchAgent).toHaveBeenCalledTimes(2));
  expect(patchAgent).toHaveBeenLastCalledWith("原始员工", { is_favorite: false }, 3);
});

it("removes a confirmed unfavorite and fills the filtered page without hiding remaining cards", async () => {
  vi.mocked(agentPage).mockResolvedValueOnce(page([employee("员工A"), employee("员工B")], 8));
  directory("/agents?filter=favorites");
  const favorite = await screen.findByRole("button", { name: "收藏员工A" });
  const retained = screen.getByRole("article", { name: "员工B" });
  const write = deferred<Agent>();
  const refill = deferred<Awaited<ReturnType<typeof agentPage>>>();
  vi.mocked(patchAgent).mockReturnValueOnce(write.promise);
  vi.mocked(agentPage).mockReturnValueOnce(refill.promise);
  fireEvent.click(favorite);
  expect(screen.getByRole("article", { name: "员工A" })).toBeTruthy();
  await act(async () => write.resolve(saved("员工A", false)));
  expect(screen.queryByRole("article", { name: "员工A" })).toBeNull();
  expect(screen.getByRole("article", { name: "员工B" })).toBe(retained);
  expect(retained.closest("[inert], [aria-hidden='true'], .opacity-0")).toBeNull();
  expect(screen.getByText(/共 7 位员工/)).toBeTruthy();
  expect(screen.getByRole("tab", { name: "全部员工 45" })).toBeTruthy();
  await act(async () => refill.resolve(page([employee("员工B"), employee("补位员工")], 7)));
  expect(screen.getByRole("article", { name: "补位员工" })).toBeTruthy();
  expect(screen.getByRole("article", { name: "员工B" })).toBe(retained);
  expect(request).toHaveBeenCalledTimes(1);
});

it("moves to the last valid page after removing the last favorite on a final page", async () => {
  vi.mocked(agentPage).mockResolvedValueOnce(page([employee("末页员工")], 21));
  directory("/agents?filter=favorites&offset=20");
  const favorite = await screen.findByRole("button", { name: "收藏末页员工" });
  vi.mocked(patchAgent).mockResolvedValueOnce(saved("末页员工", false));
  vi.mocked(agentPage).mockImplementation(async (query) =>
    query.get("offset") === "20" ? page([], 20) : page([employee("上一页员工")], 20),
  );
  fireEvent.click(favorite);
  await screen.findByRole("heading", { name: "上一页员工" });
  expect(vi.mocked(agentPage).mock.lastCall?.[0].get("offset")).toBe("0");
  expect(screen.queryByRole("navigation", { name: "员工分页" })).toBeNull();
});

it("discards a stale refresh that overlaps a completed write", async () => {
  directory();
  const favorite = await screen.findByRole("button", { name: "收藏原始员工" });
  const oldRead = deferred<Awaited<ReturnType<typeof agentPage>>>();
  const freshRead = deferred<Awaited<ReturnType<typeof agentPage>>>();
  vi.mocked(agentPage).mockReturnValueOnce(oldRead.promise).mockReturnValueOnce(freshRead.promise);
  fireEvent.click(screen.getByRole("button", { name: "测试重新读取" }));
  await waitFor(() => expect(agentPage).toHaveBeenCalledTimes(2));
  expect(screen.getByRole("heading", { name: "原始员工" })).toBeTruthy();
  vi.mocked(patchAgent).mockResolvedValueOnce(saved("原始员工", false));
  fireEvent.click(favorite);
  await waitFor(() => expect((favorite as HTMLButtonElement).disabled).toBe(false));
  await act(async () => oldRead.resolve(page([employee("原始员工")], 45)));
  await waitFor(() => expect(agentPage).toHaveBeenCalledTimes(3));
  expect(favorite.getAttribute("aria-pressed")).toBe("false");
  await act(async () =>
    freshRead.resolve(page([{ ...employee("原始员工"), is_favorite: false, revision: 2 }], 45)),
  );
  expect(favorite.getAttribute("aria-pressed")).toBe("false");
});

it("defers a new filtered read until the write has completed", async () => {
  directory();
  const favorite = await screen.findByRole("button", { name: "收藏原始员工" });
  const write = deferred<Agent>();
  vi.mocked(patchAgent).mockReturnValueOnce(write.promise);
  fireEvent.click(favorite);
  fireEvent.click(screen.getByRole("tab", { name: "已收藏" }));
  expect(screen.getByLabelText("员工列表").getAttribute("aria-busy")).toBe("true");
  expect(agentPage).toHaveBeenCalledTimes(1);
  vi.mocked(agentPage).mockResolvedValueOnce(page([employee("补位员工")], 7));
  await act(async () => write.resolve(saved("原始员工", false)));
  await screen.findByRole("heading", { name: "补位员工" });
  expect(screen.queryByRole("article", { name: "原始员工" })).toBeNull();
});

it("ignores a write completion from a previous identity", async () => {
  const view = directory();
  const favorite = await screen.findByRole("button", { name: "收藏原始员工" });
  const write = deferred<Agent>();
  vi.mocked(patchAgent).mockReturnValueOnce(write.promise);
  fireEvent.click(favorite);
  userId = "another-owner";
  vi.mocked(agentPage).mockResolvedValueOnce(page([employee("新身份员工")], 1));
  view.rerender(directoryTree());
  await screen.findByRole("heading", { name: "新身份员工" });
  await act(async () => write.resolve(saved("原始员工", false)));
  expect(screen.queryByRole("article", { name: "原始员工" })).toBeNull();
  expect(screen.getByRole("button", { name: "收藏新身份员工" }).getAttribute("aria-pressed")).toBe(
    "true",
  );
});

it("keeps the optimistic favorite while a refresh waits for its write", async () => {
  directory();
  const favorite = await screen.findByRole("button", { name: "收藏原始员工" });
  const write = deferred<Agent>();
  vi.mocked(patchAgent).mockReturnValueOnce(write.promise);
  fireEvent.click(favorite);
  vi.mocked(agentPage).mockResolvedValueOnce(
    page([{ ...employee("原始员工"), is_favorite: false, revision: 3 }], 45),
  );
  fireEvent.click(screen.getByRole("button", { name: "测试重新读取" }));
  expect(screen.getByLabelText("员工列表").getAttribute("aria-busy")).toBe("true");
  expect(favorite.getAttribute("aria-pressed")).toBe("false");
  await act(async () => write.resolve(saved("原始员工", false, 2)));
  await waitFor(() =>
    expect(screen.getByLabelText("员工列表").getAttribute("aria-busy")).toBe("false"),
  );
  vi.mocked(patchAgent).mockResolvedValueOnce(saved("原始员工", true, 4));
  fireEvent.click(favorite);
  await waitFor(() => expect(patchAgent).toHaveBeenCalledTimes(2));
  expect(patchAgent).toHaveBeenLastCalledWith("原始员工", { is_favorite: true }, 3);
});

it.each([0, 503])(
  "reconciles an uncertain write result (%s) without retrying the PATCH",
  async (status) => {
    directory();
    const favorite = await screen.findByRole("button", { name: "收藏原始员工" });
    vi.mocked(patchAgent).mockRejectedValueOnce(new ApiError("保存结果待核对", status));
    vi.mocked(getAgent).mockResolvedValueOnce(saved("原始员工", false, 2));
    fireEvent.click(favorite);
    await waitFor(() => expect(getAgent).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(screen.getByLabelText("员工列表").getAttribute("aria-busy")).toBe("false"),
    );
    expect(favorite.getAttribute("aria-pressed")).toBe("false");
    expect(patchAgent).toHaveBeenCalledTimes(1);
  },
);

it("confirms an active-status change and refills the active filter using the same local path", async () => {
  directory("/agents?filter=active");
  const more = await screen.findByRole("button", { name: "原始员工的更多操作" });
  const write = deferred<Agent>();
  vi.mocked(patchAgent).mockReturnValueOnce(write.promise);
  fireEvent.click(more);
  fireEvent.click(await screen.findByRole("menuitem", { name: "暂停接单" }));
  expect(patchAgent).not.toHaveBeenCalled();
  fireEvent.click(await screen.findByRole("button", { name: "取消" }));
  expect(patchAgent).not.toHaveBeenCalled();
  fireEvent.click(more);
  fireEvent.click(await screen.findByRole("menuitem", { name: "暂停接单" }));
  fireEvent.click(await screen.findByRole("button", { name: "确认暂停接单" }));
  expect(patchAgent).toHaveBeenCalledWith("原始员工", { is_active: false }, 1);
  expect(screen.getByRole("article", { name: "原始员工" })).toBeTruthy();
  vi.mocked(agentPage).mockResolvedValueOnce(page([employee("补位员工")], 44));
  await act(async () => write.resolve({ ...saved("原始员工", true), active: false }));
  await screen.findByRole("heading", { name: "补位员工" });
  expect(screen.queryByRole("article", { name: "原始员工" })).toBeNull();
  expect(request).toHaveBeenCalledTimes(1);
});

it("requests server pages from the top controls and preserves active filters", async () => {
  vi.mocked(agentPage).mockResolvedValueOnce(page([employee("第一页员工")], 45));
  directory("/agents?q=员工&category=研发协作&filter=favorites&skill=skill-a");
  await screen.findByRole("heading", { name: "第一页员工" });
  expect(screen.getAllByRole("navigation", { name: "员工分页" })).toHaveLength(1);
  expect(screen.getByRole("button", { name: "上一页" }).hasAttribute("disabled")).toBe(true);
  expect(screen.getByRole("button", { name: "下一页" }).textContent).toBe("");
  const pending = deferred<Awaited<ReturnType<typeof agentPage>>>();
  vi.mocked(agentPage).mockReturnValueOnce(pending.promise);
  fireEvent.click(screen.getByRole("button", { name: "下一页" }));
  await waitFor(() => expect(agentPage).toHaveBeenCalledTimes(2));
  const query = vi.mocked(agentPage).mock.lastCall?.[0];
  expect(Object.fromEntries(query!)).toMatchObject({
    offset: "20",
    limit: "20",
    q: "员工",
    category: "研发协作",
    is_favorite: "true",
    skill_id: "skill-a",
  });
  expect(screen.getByRole("heading", { name: "第一页员工" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "第 3 页" }).hasAttribute("disabled")).toBe(true);
  await act(async () => pending.resolve({ ...page([employee("第二页员工")], 45), offset: 20 }));
  expect(screen.getByRole("button", { name: "第 2 页" }).getAttribute("aria-current")).toBe("page");
  vi.mocked(agentPage).mockResolvedValueOnce({ ...page([employee("末页员工")], 45), offset: 40 });
  fireEvent.click(screen.getByRole("button", { name: "第 3 页" }));
  await screen.findByRole("heading", { name: "末页员工" });
  expect(vi.mocked(agentPage).mock.lastCall?.[0].get("offset")).toBe("40");
  expect(screen.getByRole("button", { name: "下一页" }).hasAttribute("disabled")).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "上一页" }));
  await screen.findByRole("heading", { name: "第二页员工" });
  expect(screen.getByRole("button", { name: "第 2 页" }).getAttribute("aria-current")).toBe("page");
});

it("keeps long pagination bounded while providing direct access to both ends", async () => {
  vi.mocked(agentPage).mockResolvedValueOnce(page([employee("中间页员工")], 200));
  directory("/agents?offset=80");
  await screen.findByRole("heading", { name: "中间页员工" });
  const navigation = screen.getByRole("navigation", { name: "员工分页" });
  expect(navigation.querySelectorAll("button")).toHaveLength(5);
  expect(screen.getByRole("button", { name: "第 5 页" }).getAttribute("aria-current")).toBe("page");
  expect(screen.getByRole("button", { name: "第 1 页" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "第 10 页" })).toBeTruthy();
  vi.mocked(agentPage).mockResolvedValueOnce(page([], 0));
  fireEvent.click(screen.getByRole("tab", { name: "已暂停" }));
  await screen.findByText("没有找到符合条件的员工");
  expect(vi.mocked(agentPage).mock.lastCall?.[0].get("offset")).toBe("0");
  expect(screen.queryByRole("navigation", { name: "员工分页" })).toBeNull();
  expect(screen.queryByRole("button", { name: "第 0 页" })).toBeNull();
});
