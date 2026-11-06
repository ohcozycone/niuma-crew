// @vitest-environment jsdom
import type { ReactNode } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router";
// eslint-disable-next-line boundaries/dependencies -- 路由集成回归装配真实外壳，覆盖页面保存与全局离页保护的协作。
import { Layout } from "@/Layout";
import * as api from "@/lib/api/agents";
import * as skills from "@/lib/api/skills";
import { ApiError, request } from "@/lib/api/http";
import type { Agent } from "@/lib/models/agent";
import { agentAvatars, defaultAvatarId } from "@/lib/avatars/registry";
import { draftKey } from "@/lib/draft";
import { identityKey } from "@/lib/identity";
import { AgentEditorPage, AgentsPage } from "./AgentsPage";

const identity = {
  actor: { kind: "user" as const, user: { id: "owner", username: "admin" } },
  expires_at: "2099",
  permissions: ["agents:read", "agents:create", "agents:update", "skills:read"],
};
vi.mock("@/state/auth/useIdentity", () => ({ useIdentity: () => identity }));
vi.mock("@/components/auth/AuthBoundary", () => ({
  AuthBoundary: ({ children }: { children: ReactNode }) => children,
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
vi.mock("@/lib/api/modelConnections", () => ({
  loadModelConnections: async () => [],
}));
vi.mock("@/lib/api/http", async (original) => ({
  ...(await original<object>()),
  request: vi.fn(),
}));

let persisted: Agent;
function employee(): Agent {
  return {
    id: "employee-a",
    createdByUserId: "owner",
    name: "原始员工",
    code: "",
    role: "",
    description: "已保存的介绍",
    category: "研发协作",
    icon: "custom",
    avatarId: defaultAvatarId,
    systemPrompt: "现有岗位指令",
    revision: 1,
    configurationLoaded: true,
    toolGrants: [],
    modelConnectionId: null,
    skillAssignments: [],
    skills: [],
    toolCount: 0,
    knowledgeBaseCount: 0,
    deliverables: ["报告"],
    exampleTasks: ["示例"],
    active: true,
    favorite: false,
  };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
function editor(entry: string) {
  const router = createMemoryRouter(
    [
      {
        element: <Layout />,
        children: [
          { path: "/agents/new", Component: AgentEditorPage },
          { path: "/agents/:id", Component: AgentEditorPage },
          { path: "/agents", Component: AgentsPage },
          { path: "/skills", element: <h1>能力目录</h1> },
          { path: "/brains", element: <h1>模型目录</h1> },
        ],
      },
    ],
    { initialEntries: [entry] },
  );
  render(<RouterProvider router={router} />);
  return router;
}
beforeEach(() => {
  sessionStorage.clear();
  persisted = employee();
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
  vi.mocked(skills.skillPage).mockResolvedValue({ items: [], total: 0, offset: 0, limit: 20 });
  vi.mocked(request).mockImplementation(async (path) => {
    if (path === "configuration-summary") return { agents: 1, skills: 0, favorites: 0 };
    if (path === "agents/employee-a") return { name: persisted.name, revision: persisted.revision };
    throw new Error(`Unexpected request: ${path}`);
  });
  vi.mocked(api.getAgent).mockImplementation(async () => ({ ...persisted }));
  vi.mocked(api.agentPage).mockImplementation(async () => ({
    items: [
      {
        id: persisted.id,
        created_by_user_id: "owner",
        name: persisted.name,
        code: null,
        role_label: null,
        description: persisted.description,
        category: persisted.category,
        avatar_id: persisted.avatarId,
        model_connection_id: null,
        is_active: true,
        is_favorite: false,
        revision: persisted.revision!,
        resource_counts: { skills: 0, tools: 0, knowledge_bases: 0 },
        skill_summaries: [],
        updated_at: "",
      },
    ],
    total: 1,
    offset: 0,
    limit: 20,
  }));
  vi.mocked(api.saveAgent).mockImplementation(async (value, create) => {
    if (!create && value.revision !== persisted.revision)
      throw new ApiError(
        "员工配置已被修改，当前草稿已保留。",
        409,
        "configuration_revision_conflict",
      );
    persisted = {
      ...value,
      id: "employee-a",
      revision: create ? 1 : persisted.revision! + 1,
      configurationLoaded: true,
    };
    return { ...persisted };
  });
});
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
  vi.unstubAllGlobals();
});

it.each([
  ["/agents/new?from=%2Fbrains", true, "/agents"],
  [
    "/agents/employee-a?from=%2Fagents%3Ffilter%3Dall%26q%3D保存",
    false,
    "/agents?filter=all&q=保存",
  ],
] as const)(
  "commits the save before leaving %s and keeps the confirmed result on reopening",
  async (entry, create, target) => {
    const router = editor(entry as string);
    const blockedNavigation = vi.fn();
    const stopObserving = router.subscribe((state) => {
      if ([...state.blockers.values()].some((blocker) => blocker.state === "blocked"))
        blockedNavigation();
    });
    const name = await screen.findByRole("textbox", { name: "员工名称" });
    fireEvent.change(name, { target: { value: "保存后的员工" } });
    fireEvent.click(screen.getByRole("button", { name: "保存配置" }));
    const destination = new URL(target, "http://app.local");
    await waitFor(() =>
      expect(router.state.location.pathname + router.state.location.search).toBe(
        destination.pathname + destination.search,
      ),
    );
    expect(api.saveAgent).toHaveBeenCalledTimes(1);
    expect(api.saveAgent).toHaveBeenCalledWith(
      expect.objectContaining({ name: "保存后的员工" }),
      create,
    );
    await screen.findByText("员工配置已保存。");
    expect(blockedNavigation).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(
      sessionStorage.getItem(
        draftKey(identityKey(identity), `agent:${create ? "new" : "employee-a"}`),
      ),
    ).toBeNull();
    expect(router.state.historyAction).toBe("REPLACE");
    await act(async () => {
      await router.navigate("/agents/employee-a");
    });
    expect(
      ((await screen.findByRole("textbox", { name: "员工名称" })) as HTMLInputElement).value,
    ).toBe("保存后的员工");
    expect(screen.queryByText(/服务器配置已更新，旧修订草稿/)).toBeNull();
    await act(async () => {
      await router.navigate("/skills");
    });
    await screen.findByRole("heading", { name: "能力目录" });
    expect(screen.queryByRole("dialog")).toBeNull();
    stopObserving();
  },
);

it("shows saved until changes require saving, including reverting across tabs", async () => {
  editor("/agents/employee-a");
  const name = await screen.findByRole("textbox", { name: "员工名称" });
  expect(screen.getByRole("button", { name: "删除员工" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "返回" })).toBeTruthy();
  expect((screen.getByRole("button", { name: "已保存" }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.submit(name.closest("form")!);
  expect(api.saveAgent).not.toHaveBeenCalled();
  fireEvent.change(name, { target: { value: "编辑中的员工" } });
  expect((screen.getByRole("button", { name: "保存配置" }) as HTMLButtonElement).disabled).toBe(
    false,
  );
  fireEvent.click(screen.getByRole("tab", { name: "指令与知识" }));
  await screen.findByRole("textbox", { name: "工作指令" });
  expect(screen.getByRole("button", { name: "保存配置" })).toBeTruthy();
  fireEvent.click(screen.getByRole("tab", { name: "基础配置" }));
  fireEvent.change(await screen.findByRole("textbox", { name: "员工名称" }), {
    target: { value: persisted.name },
  });
  expect((screen.getByRole("button", { name: "已保存" }) as HTMLButtonElement).disabled).toBe(true);
});

it("returns directly when unchanged and protects unsaved changes on return", async () => {
  const router = editor("/agents/employee-a?from=%2Fbrains");
  await screen.findByRole("textbox", { name: "员工名称" });
  fireEvent.click(screen.getByRole("button", { name: "返回" }));
  await waitFor(() => expect(router.state.location.pathname).toBe("/brains"));
  expect(screen.queryByRole("dialog")).toBeNull();
  await act(async () => {
    await router.navigate("/agents/employee-a?from=%2Fbrains");
  });
  fireEvent.change(await screen.findByRole("textbox", { name: "员工名称" }), {
    target: { value: "暂存的修改" },
  });
  fireEvent.click(screen.getByRole("button", { name: "返回" }));
  await screen.findByRole("dialog", { name: "放弃未保存的修改？" });
  expect(router.state.location.pathname).toBe("/agents/employee-a");
  fireEvent.click(screen.getByRole("button", { name: "继续编辑" }));
  expect((screen.getByRole("textbox", { name: "员工名称" }) as HTMLInputElement).value).toBe(
    "暂存的修改",
  );
  expect(api.saveAgent).not.toHaveBeenCalled();
});

it("changes the portrait through the integrated avatar button and only persists on save", async () => {
  const router = editor("/agents/employee-a");
  const changeAvatar = await screen.findByRole("button", { name: "更换头像" });
  expect(screen.getAllByRole("button", { name: "更换头像" })).toHaveLength(1);
  fireEvent.click(changeAvatar);
  await screen.findByRole("dialog", { name: "选择头像" });
  const index = agentAvatars.findIndex((avatar) => avatar.id !== defaultAvatarId);
  fireEvent.click(screen.getByRole("button", { name: `头像 ${index + 1}` }));
  await waitFor(() => expect(screen.queryByRole("dialog", { name: "选择头像" })).toBeNull());
  expect(screen.getByRole("complementary", { name: "员工配置预览" })).toBeTruthy();
  expect(api.saveAgent).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "保存配置" }));
  await waitFor(() => expect(router.state.location.pathname).toBe("/agents"));
  expect(api.saveAgent).toHaveBeenCalledWith(
    expect.objectContaining({ avatarId: agentAvatars[index].id }),
    false,
  );
});

it("offers save and return but no deletion for a blank new employee", async () => {
  editor("/agents/new");
  await screen.findByRole("textbox", { name: "员工名称" });
  expect(screen.getByRole("button", { name: "保存配置" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "返回" })).toBeTruthy();
  expect(screen.queryByRole("button", { name: "删除员工" })).toBeNull();
});

it("keeps an actual rejected draft, requires explicit revision adoption, then saves once", async () => {
  const router = editor("/agents/employee-a");
  const input = await screen.findByRole("textbox", { name: "员工简介" });
  fireEvent.change(input, { target: { value: "需要保留的草稿" } });
  persisted = { ...persisted, description: "其他页面的更新", revision: 3 };
  fireEvent.click(screen.getByRole("button", { name: "保存配置" }));
  await screen.findByText("员工配置已被修改，当前草稿已保留。");
  expect(router.state.location.pathname).toBe("/agents/employee-a");
  expect((input as HTMLTextAreaElement).value).toBe("需要保留的草稿");
  expect(screen.queryByText("员工配置已保存。")).toBeNull();
  fireEvent.click(screen.getByRole("link", { name: "能力库" }));
  await screen.findByRole("dialog", { name: "放弃未保存的修改？" });
  fireEvent.click(screen.getByRole("button", { name: "继续编辑" }));
  fireEvent.click(screen.getByRole("button", { name: "查看服务器最新配置" }));
  await screen.findByRole("button", { name: "采用最新修订并保留草稿" });
  expect(api.saveAgent).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: "采用最新修订并保留草稿" }));
  fireEvent.click(screen.getByRole("button", { name: "保存配置" }));
  await waitFor(() => expect(router.state.location.pathname).toBe("/agents"));
  expect(api.saveAgent).toHaveBeenLastCalledWith(
    expect.objectContaining({ revision: 3, description: "需要保留的草稿" }),
    false,
  );
  expect(persisted.revision).toBe(4);
  expect(screen.queryByRole("dialog")).toBeNull();
});

it("locks repeated submissions and keeps navigation protected only until confirmation", async () => {
  const router = editor("/agents/employee-a");
  const name = await screen.findByRole("textbox", { name: "员工名称" });
  fireEvent.change(name, { target: { value: "慢速保存" } });
  const write = deferred<Agent>();
  vi.mocked(api.saveAgent).mockReturnValueOnce(write.promise);
  const form = name.closest("form")!;
  fireEvent.submit(form);
  fireEvent.submit(form);
  expect(api.saveAgent).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole("alert")).toBeNull();
  fireEvent.click(screen.getByRole("link", { name: "能力库" }));
  await screen.findByRole("dialog", { name: "正在保存" });
  expect(
    (screen.getByRole("button", { name: "放弃修改并离开" }) as HTMLButtonElement).disabled,
  ).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "继续编辑" }));
  await act(async () => {
    persisted = { ...persisted, name: "慢速保存", revision: 2 };
    write.resolve(persisted);
  });
  await waitFor(() => expect(router.state.location.pathname).toBe("/agents"));
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(api.saveAgent).toHaveBeenCalledTimes(1);
});
