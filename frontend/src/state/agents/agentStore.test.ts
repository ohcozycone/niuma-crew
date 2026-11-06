import { afterEach, beforeEach, expect, it, vi } from "vitest";
import * as api from "@/lib/api/agents";
import { ApiError } from "@/lib/api/http";
import type { Agent } from "@/lib/models/agent";
import { AgentStore, favoriteQuery } from "./agentStore";

vi.mock("@/lib/api/agents", async (original) => ({
  ...(await original<object>()),
  agentPage: vi.fn(),
  patchAgent: vi.fn(),
  getAgent: vi.fn(),
}));
const store = () => new AgentStore(true, vi.fn());
function dto(id: string, favorite = false, revision = 1): api.AgentSummaryDTO {
  return {
    id,
    name: id,
    code: null,
    avatar_id: "admin",
    category: "研发协作",
    description: "摘要",
    role_label: null,
    model_connection_id: "brain",
    is_active: true,
    is_favorite: favorite,
    resource_counts: { skills: 0, tools: 0, knowledge_bases: 0 },
    skill_summaries: [],
    revision,
    updated_at: "2026-10-30T00:00:00Z",
  };
}
function agent(id: string, favorite: boolean, revision = 2): Agent {
  return {
    ...api.fromAgentSummary(dto(id, favorite, revision)),
    systemPrompt: "秘密指令",
    deliverables: [],
    exampleTasks: [],
    configurationLoaded: true,
  };
}
function page(items: api.AgentSummaryDTO[], total = items.length) {
  return { items, total, offset: 0, limit: 20 };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((yes) => {
    resolve = yes;
  });
  return { promise, resolve };
}
beforeEach(() => {
  vi.mocked(api.agentPage).mockResolvedValue(page([dto("A"), dto("B")]));
});
afterEach(() => vi.resetAllMocks());

it("updates only the selected employee subscription and shares its optimistic state across readers", async () => {
  const data = store();
  const resource = data.page(new URLSearchParams({ offset: "0", limit: "20", q: "" }));
  const stop = resource.subscribe(vi.fn());
  await resource.ensure();
  const a = vi.fn();
  const otherA = vi.fn();
  const b = vi.fn();
  data.state("A").subscribe(a);
  data.state("A").subscribe(otherA);
  data.state("B").subscribe(b);
  const write = deferred<Agent>();
  vi.mocked(api.patchAgent).mockReturnValueOnce(write.promise);
  const pending = data.setFavorite("A", true);
  expect(data.state("A").getSnapshot().agent?.favorite).toBe(true);
  expect(a).toHaveBeenCalledTimes(1);
  expect(otherA).toHaveBeenCalledTimes(1);
  expect(b).not.toHaveBeenCalled();
  await data.setFavorite("A", false);
  expect(api.patchAgent).toHaveBeenCalledTimes(1);
  write.resolve(agent("A", true));
  await pending;
  expect(data.state("A").getSnapshot().agent).not.toHaveProperty("systemPrompt");
  expect(data.state("A").getSnapshot().agent).not.toHaveProperty("configurationLoaded");
  expect(api.agentPage).toHaveBeenCalledTimes(1);
  expect(b).not.toHaveBeenCalled();
  stop();
  data.dispose();
});

it("does not count a completed favorite twice when an overlapping read contains that write", async () => {
  const data = store();
  const query = data.page(favoriteQuery());
  vi.mocked(api.agentPage).mockResolvedValueOnce(page([dto("A", true), dto("B", true)], 8));
  const stop = query.subscribe(vi.fn());
  await query.ensure();
  const oldRead = deferred<Awaited<ReturnType<typeof api.agentPage>>>();
  vi.mocked(api.agentPage)
    .mockReturnValueOnce(oldRead.promise)
    .mockResolvedValueOnce(page([dto("B", true)], 7));
  query.refresh();
  await Promise.resolve();
  vi.mocked(api.patchAgent).mockResolvedValueOnce(agent("A", false));
  await data.setFavorite("A", false);
  expect(query.getSnapshot().data?.total).toBe(7);
  oldRead.resolve(page([dto("B", true)], 7));
  await oldRead.promise;
  await query.ensure();
  expect(query.getSnapshot().data?.total).toBe(7);
  expect(query.getSnapshot().data?.ids).toEqual(["B"]);
  stop();
  data.dispose();
});

it("keeps an uncertain write locked and retries only verification, without blocking other employee reads", async () => {
  const data = store();
  const resource = data.page(new URLSearchParams("offset=0&limit=20&q="));
  const stop = resource.subscribe(vi.fn());
  await resource.ensure();
  vi.mocked(api.patchAgent).mockRejectedValueOnce(new ApiError("offline", 0));
  vi.mocked(api.getAgent).mockRejectedValueOnce(new Error("still offline"));
  await data.setFavorite("A", true);
  expect(data.state("A").getSnapshot()).toMatchObject({ saving: true, retryable: true });
  await data.setFavorite("A", true);
  expect(api.patchAgent).toHaveBeenCalledTimes(1);
  resource.refresh();
  await resource.ensure();
  expect(resource.getSnapshot().loading).toBe(false);
  vi.mocked(api.getAgent).mockResolvedValueOnce(agent("A", true));
  await data.retryStatus("A");
  expect(data.state("A").getSnapshot()).toMatchObject({
    saving: false,
    retryable: false,
    error: "",
  });
  expect(data.state("A").getSnapshot().agent?.favorite).toBe(true);
  expect(api.patchAgent).toHaveBeenCalledTimes(1);
  stop();
  data.dispose();
});

it("retains a newer employee revision when an older page arrives", async () => {
  const data = store();
  const resource = data.page(new URLSearchParams("offset=0&limit=20&q="));
  const stop = resource.subscribe(vi.fn());
  await resource.ensure();
  vi.mocked(api.patchAgent).mockResolvedValueOnce(agent("A", true, 3));
  await data.setFavorite("A", true);
  vi.mocked(api.agentPage).mockResolvedValueOnce(page([dto("A", false, 1)]));
  resource.refresh();
  await resource.ensure();
  expect(data.state("A").getSnapshot().agent).toMatchObject({ favorite: true, revision: 3 });
  stop();
  data.dispose();
});
