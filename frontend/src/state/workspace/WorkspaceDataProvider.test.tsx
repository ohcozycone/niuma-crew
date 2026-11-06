// @vitest-environment jsdom
import { StrictMode } from "react";
import {
  act,
  cleanup,
  fireEvent,
  render,
  renderHook,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import * as api from "@/lib/api/agents";
import type { Agent } from "@/lib/models/agent";
import { useAgentState } from "@/state/agents/useAgentData";
import { useResource } from "@/state/shared/useResource";
import { WorkspaceDataProvider } from "./WorkspaceDataProvider";
import { useWorkspaceData } from "./useWorkspaceData";

let userId = "owner";
vi.mock("@/state/auth/useIdentity", () => ({
  useIdentity: () => ({
    actor: { kind: "user", user: { id: userId, username: "admin" } },
    expires_at: "2099",
    permissions: ["agents:read"],
  }),
}));
vi.mock("@/lib/api/agents", async (original) => ({
  ...(await original<object>()),
  agentPage: vi.fn(),
  patchAgent: vi.fn(),
}));
function dto(id: string): api.AgentSummaryDTO {
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
    is_favorite: false,
    resource_counts: { skills: 0, tools: 0, knowledge_bases: 0 },
    skill_summaries: [],
    revision: 1,
    updated_at: "2026-10-30T00:00:00Z",
  };
}
function page(ids = ["A", "B"]) {
  return { items: ids.map(dto), total: ids.length, offset: 0, limit: 20 };
}
beforeEach(() => {
  userId = "owner";
  vi.mocked(api.agentPage).mockResolvedValue(page());
});
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});
const renders = new Map<string, number>();
function Employee({ id }: { id: string }) {
  const state = useAgentState(id);
  renders.set(id, (renders.get(id) ?? 0) + 1);
  return <output aria-label={id}>{String(state.agent?.favorite)}</output>;
}
function Directory() {
  const data = useWorkspaceData();
  const result = useResource(data.agents.page(new URLSearchParams("offset=0&limit=20&q=")));
  return (
    <>
      <button
        onClick={() => {
          void data.agents.setFavorite("A", true);
        }}
      >
        收藏 A
      </button>
      {result.data?.ids.map((id) => (
        <Employee key={id} id={id} />
      ))}
    </>
  );
}

it("keeps the Context instance stable and rerenders only subscribers to the changed employee", async () => {
  renders.clear();
  render(
    <WorkspaceDataProvider>
      <Directory />
    </WorkspaceDataProvider>,
  );
  await screen.findByLabelText("B");
  const beforeB = renders.get("B");
  let finish!: (value: Agent) => void;
  vi.mocked(api.patchAgent).mockReturnValueOnce(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  fireEvent.click(screen.getByRole("button", { name: "收藏 A" }));
  expect(screen.getByLabelText("A").textContent).toBe("true");
  expect(renders.get("B")).toBe(beforeB);
  await act(async () =>
    finish({
      ...api.fromAgentSummary(dto("A")),
      favorite: true,
      revision: 2,
      systemPrompt: "",
      exampleTasks: [],
      deliverables: [],
    }),
  );
  expect(renders.get("B")).toBe(beforeB);
  expect(api.agentPage).toHaveBeenCalledTimes(1);
});

it("deduplicates development StrictMode subscriptions without disposing the live Provider", async () => {
  render(
    <StrictMode>
      <WorkspaceDataProvider>
        <Directory />
      </WorkspaceDataProvider>
    </StrictMode>,
  );
  await screen.findByLabelText("A");
  expect(api.agentPage).toHaveBeenCalledTimes(1);
});

it("isolates identities and cancels old reads before late responses can populate the new store", async () => {
  let oldResolve!: (value: ReturnType<typeof page>) => void;
  vi.mocked(api.agentPage).mockReturnValueOnce(
    new Promise((resolve) => {
      oldResolve = resolve;
    }),
  );
  const view = renderHook(
    () => {
      const data = useWorkspaceData();
      return {
        data,
        result: useResource(data.agents.page(new URLSearchParams("offset=0&limit=20&q="))),
      };
    },
    { wrapper: WorkspaceDataProvider },
  );
  await waitFor(() => expect(api.agentPage).toHaveBeenCalledTimes(1));
  const oldData = view.result.current.data;
  const oldSignal = vi.mocked(api.agentPage).mock.calls[0][1];
  userId = "another-owner";
  vi.mocked(api.agentPage).mockResolvedValueOnce(page(["new"]));
  view.rerender();
  await waitFor(() => expect(view.result.current.result.data?.ids).toEqual(["new"]));
  await act(async () => oldResolve(page(["old"])));
  expect(oldSignal?.aborted).toBe(true);
  expect(view.result.current.data).not.toBe(oldData);
  expect(view.result.current.data.agents.state("old").getSnapshot().agent).toBeUndefined();
  expect(view.result.current.result.data?.ids).toEqual(["new"]);
});
