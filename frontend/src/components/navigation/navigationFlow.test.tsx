import { ApiError } from "@/lib/api/http";
// @vitest-environment jsdom
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { agentPage, type AgentSummaryDTO } from "@/lib/api/agents";
import { request } from "@/lib/api/http";
import { WorkspaceDataProvider } from "@/state/workspace/WorkspaceDataProvider";
import { useWorkspaceData } from "@/state/workspace/useWorkspaceData";
import { favoriteQuery } from "@/state/agents/agentStore";
import { useResource } from "@/state/shared/useResource";
import { useNavigationSummary } from "./useNavigationSummary";

vi.mock("@/state/auth/useIdentity", () => ({
  useIdentity: () => ({
    actor: { kind: "user", user: { id: "owner", username: "admin" } },
    expires_at: "2099",
    permissions: ["agents:read"],
  }),
}));
vi.mock("@/lib/api/agents", async (original) => ({
  ...(await original<object>()),
  agentPage: vi.fn(),
}));
vi.mock("@/lib/api/http", async (original) => ({
  ...(await original<object>()),
  request: vi.fn(),
}));
function employee(id: string): AgentSummaryDTO {
  return {
    id,
    code: null,
    name: id,
    avatar_id: "admin",
    category: "研发协作",
    description: "摘要",
    role_label: null,
    model_connection_id: "brain",
    is_active: true,
    is_favorite: true,
    resource_counts: { skills: 0, tools: 0, knowledge_bases: 0 },
    skill_summaries: [],
    revision: 1,
    updated_at: "2026-10-30T00:00:00Z",
  };
}
function page(id: string, total = 21) {
  return { items: [employee(id)], total, offset: 0, limit: 20 };
}
beforeEach(() => {
  vi.mocked(request).mockResolvedValue({ agents: 45, skills: 2, favorites: 999 });
  vi.mocked(agentPage).mockResolvedValue(page("已收藏员工"));
});
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});
function useNavigation() {
  return { summary: useNavigationSummary(), shared: useWorkspaceData() };
}

it("shares a single favorites query and derives its count from the same response", async () => {
  const view = renderHook(
    () => {
      const current = useNavigation();
      const samePage = useResource(current.shared.agents.page(favoriteQuery()));
      return { ...current, samePage };
    },
    { wrapper: WorkspaceDataProvider },
  );
  await waitFor(() => expect(view.result.current.summary.ready).toBe(true));
  expect(view.result.current.summary.globalTotals).toEqual({
    agents: 45,
    skills: 2,
    favorites: 21,
  });
  expect(view.result.current.summary.favorites[0]?.name).toBe("已收藏员工");
  expect(agentPage).toHaveBeenCalledTimes(1);
  expect(request).toHaveBeenCalledTimes(1);
});

it("updates favorite names from another shared query without rereading the favorites page", async () => {
  const view = renderHook(useNavigation, { wrapper: WorkspaceDataProvider });
  await waitFor(() => expect(view.result.current.summary.ready).toBe(true));
  const renamed = { ...employee("已收藏员工"), name: "最新姓名", revision: 2 };
  vi.mocked(agentPage).mockResolvedValueOnce({ items: [renamed], total: 1, offset: 0, limit: 20 });
  const directory = view.result.current.shared.agents.page(new URLSearchParams("q=最新姓名"));
  let stop!: () => void;
  await act(async () => {
    stop = directory.subscribe(vi.fn());
    await directory.ensure();
  });
  expect(view.result.current.summary.favorites[0]?.name).toBe("最新姓名");
  expect(agentPage).toHaveBeenCalledTimes(2);
  expect(view.result.current.summary.globalTotals?.favorites).toBe(21);
  stop();
});

it("retains confirmed favorites and counts when synchronization fails, then retries only the read", async () => {
  const view = renderHook(useNavigation, { wrapper: WorkspaceDataProvider });
  await waitFor(() => expect(view.result.current.summary.ready).toBe(true));
  vi.mocked(agentPage).mockRejectedValueOnce(new ApiError("网络异常", 0));
  act(() => view.result.current.shared.agents.page(favoriteQuery()).refresh());
  await waitFor(() => expect(view.result.current.summary.summaryError).toBe("网络异常"));
  expect(view.result.current.summary.favorites[0]?.name).toBe("已收藏员工");
  expect(view.result.current.summary.globalTotals?.favorites).toBe(21);
  expect(request).toHaveBeenCalledTimes(1);
  vi.mocked(agentPage).mockResolvedValueOnce(page("补位员工", 20));
  act(() => view.result.current.summary.reload());
  await waitFor(() => expect(view.result.current.summary.favorites[0]?.name).toBe("补位员工"));
  expect(view.result.current.summary.summaryError).toBe("");
});

it("ignores an old navigation response after a newer refresh", async () => {
  const view = renderHook(useNavigation, { wrapper: WorkspaceDataProvider });
  await waitFor(() => expect(view.result.current.summary.ready).toBe(true));
  let resolveOld!: (value: Awaited<ReturnType<typeof agentPage>>) => void;
  vi.mocked(agentPage).mockReturnValueOnce(
    new Promise((resolve) => {
      resolveOld = resolve;
    }),
  );
  act(() => view.result.current.summary.reload());
  await waitFor(() => expect(agentPage).toHaveBeenCalledTimes(2));
  const signal = vi.mocked(agentPage).mock.lastCall?.[1];
  vi.mocked(agentPage).mockResolvedValueOnce(page("最新收藏", 22));
  act(() => view.result.current.summary.reload());
  await waitFor(() => expect(view.result.current.summary.favorites[0]?.name).toBe("最新收藏"));
  expect(signal?.aborted).toBe(true);
  await act(async () => resolveOld(page("旧收藏")));
  expect(view.result.current.summary.favorites[0]?.name).toBe("最新收藏");
});
