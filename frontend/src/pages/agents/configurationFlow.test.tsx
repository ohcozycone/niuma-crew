// @vitest-environment jsdom
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import * as agents from "@/lib/api/agents";
import * as skills from "@/lib/api/skills";
import { ApiError, request } from "@/lib/api/http";
import type { Agent } from "@/lib/models/agent";
import { useAgentEditor } from "./useAgentEditor";
import { WorkspaceDataProvider } from "@/state/workspace/WorkspaceDataProvider";
import { useWorkspaceData } from "@/state/workspace/useWorkspaceData";
import { useAgentDirectory } from "./useAgentDirectory";
let currentId: string | undefined = "A";
const setSearchParams = vi.fn();
vi.mock("react-router", async (original) => ({
  ...(await original<object>()),
  useParams: () => ({ id: currentId }),
  useSearchParams: () => [new URLSearchParams(), setSearchParams],
}));
vi.mock("@/state/auth/useIdentity", () => ({
  useIdentity: () => ({
    actor: { kind: "user", user: { id: "owner", username: "admin" } },
    expires_at: "2099",
    permissions: ["agents:read"],
  }),
}));
vi.mock("@/lib/api/agents", async (original) => ({
  ...(await original<object>()),
  getAgent: vi.fn(),
  agentPage: vi.fn(),
  saveAgent: vi.fn(),
}));
vi.mock("@/lib/api/skills", async (original) => ({
  ...(await original<object>()),
  skillPage: vi.fn(),
}));
vi.mock("@/lib/api/http", async (original) => ({
  ...(await original<object>()),
  request: vi.fn(),
}));
const detail = (id: string): Agent => ({
  id,
  name: id,
  code: "",
  role: "",
  description: "",
  category: "研发协作",
  icon: "custom",
  avatarId: "admin",
  systemPrompt: "完整指令",
  configurationLoaded: true,
  revision: 1,
  modelConnectionId: "brain",
  skills: [],
  toolCount: 0,
  knowledgeBaseCount: 0,
  deliverables: ["报告"],
  favorite: false,
  active: true,
  exampleTasks: ["示例"],
});
beforeEach(() => {
  currentId = "A";
  vi.mocked(skills.skillPage).mockResolvedValue({ items: [], total: 0, offset: 0, limit: 20 });
  vi.mocked(request).mockResolvedValue({ agents: 1, skills: 0, favorites: 0 });
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
it("ignores a late old editor read and saves only the full current detail", async () => {
  let finishA!: (value: Agent) => void;
  vi.mocked(agents.getAgent).mockImplementation((id) =>
    id === "A"
      ? new Promise((resolve) => {
          finishA = resolve;
        })
      : Promise.resolve(detail(id)),
  );
  vi.mocked(agents.saveAgent).mockImplementation(async (value) => ({ ...value, revision: 2 }));
  const view = renderHook(useAgentEditor, { wrapper: WorkspaceDataProvider });
  currentId = "B";
  view.rerender();
  await waitFor(() => expect(view.result.current.ready).toBe(true));
  expect(view.result.current.agents[0].id).toBe("B");
  await act(async () => {
    finishA(detail("A"));
  });
  expect(view.result.current.agents[0].id).toBe("B");
  await act(async () => {
    await view.result.current.saveAgent(view.result.current.agents[0], false);
  });
  expect(agents.saveAgent).toHaveBeenCalledWith(
    expect.objectContaining({
      id: "B",
      configurationLoaded: true,
      systemPrompt: "完整指令",
      deliverables: ["报告"],
    }),
    false,
  );
  expect(agents.agentPage).not.toHaveBeenCalled();
});
it("loads a summary for the directory and never requests configuration detail", async () => {
  currentId = undefined;
  vi.mocked(agents.agentPage).mockResolvedValue({
    items: [
      {
        id: "A",
        code: null,
        name: "A",
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
        updated_at: "2026-10-27T00:00:00Z",
      },
    ],
    total: 1,
    offset: 0,
    limit: 20,
  });
  const view = renderHook(
    () => {
      const directory = useAgentDirectory();
      const data = useWorkspaceData();
      return { ...directory, agent: data.agents.state("A").getSnapshot().agent };
    },
    { wrapper: WorkspaceDataProvider },
  );
  await waitFor(() => expect(view.result.current.ready).toBe(true));
  expect(view.result.current.agent).not.toHaveProperty("systemPrompt");
  expect(agents.getAgent).not.toHaveBeenCalled();
});

it("keeps the loaded editor mounted after a transient detail refresh, but removes a missing detail", async () => {
  vi.mocked(agents.getAgent)
    .mockResolvedValueOnce(detail("A"))
    .mockRejectedValueOnce(new ApiError("暂不可用", 503, "database_busy"))
    .mockRejectedValueOnce(new ApiError("员工不存在", 404, "agent_not_found"));
  const view = renderHook(useAgentEditor, { wrapper: WorkspaceDataProvider });
  await waitFor(() => expect(view.result.current.ready).toBe(true));
  const loaded = view.result.current.agents[0];
  act(() => view.result.current.reload());
  await waitFor(() => expect(view.result.current.failure?.code).toBe("database_busy"));
  expect(view.result.current.ready).toBe(true);
  expect(view.result.current.agents[0]).toBe(loaded);
  act(() => view.result.current.reload());
  await waitFor(() => expect(view.result.current.failure?.status).toBe(404));
  expect(view.result.current.ready).toBe(false);
  expect(view.result.current.agents).toEqual([]);
});
