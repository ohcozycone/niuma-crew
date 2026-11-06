// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { Link, MemoryRouter, Route, Routes, useSearchParams } from "react-router";
import { EmployeeHomePage } from "./EmployeeHomePage";
import { request } from "@/lib/api/http";
import { WorkspaceDataProvider } from "@/state/workspace/WorkspaceDataProvider";

let user = "user";
let permissions = ["runs:read", "runs:create", "conversations:read", "knowledge:use"];
const employee = {
  id: "employee",
  name: "行政老王",
  avatar_id: "admin",
  description: "负责行政支持",
  is_active: false,
  model_configured: false,
  resource_counts: { skills: 8, tools: 4, knowledge_bases: 0 },
};
const knowledge = { knowledge_base_ids: ["one", "two", "three"] };

function EditorDestination() {
  const [params] = useSearchParams();
  return (
    <>
      <h1>编辑标签：{params.get("tab")}</h1>
      <Link to={params.get("from") || "/agents"}>返回来源</Link>
    </>
  );
}

function Page({ entry = "/agents/employee/home" }: { entry?: string }) {
  return (
    <MemoryRouter initialEntries={[entry]}>
      <WorkspaceDataProvider>
        <Routes>
          <Route path="/agents/:id/home" element={<EmployeeHomePage />} />
          <Route path="/agents/:id" element={<EditorDestination />} />
        </Routes>
      </WorkspaceDataProvider>
    </MemoryRouter>
  );
}

function metric(name: string) {
  return within(screen.getByRole("group", { name }));
}

vi.mock("@/lib/api/http", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/http")>()),
  request: vi.fn(),
}));
vi.mock("@/state/auth/useIdentity", () => ({
  useIdentity: () => ({
    actor: { kind: permissions.length ? "user" : "guest", user: { id: user } },
    permissions,
  }),
}));
vi.mock("@/components/conversations/ConversationHistory", () => ({
  ConversationHistory: ({ agentId }: { agentId: string }) => <p>历史员工范围：{agentId}</p>,
}));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
beforeEach(() => {
  user = "user";
  permissions = ["runs:read", "runs:create", "conversations:read", "knowledge:use"];
  vi.mocked(request).mockImplementation(async (path) => {
    if (path.startsWith("public/agents/")) return employee as never;
    if (path.startsWith("knowledge-bases/employee-bindings/")) return knowledge as never;
    if (path.startsWith("conversations/stats?")) return { completed_rounds: 128 } as never;
    throw new Error(`Unexpected request: ${path}`);
  });
});

it("opens employee history first and keeps unfinished modules as explicit placeholders", async () => {
  render(<Page />);
  expect(await screen.findByText("历史员工范围：employee")).toBeTruthy();
  expect(metric("技能").getByText("8")).toBeTruthy();
  expect(await metric("知识库").findByText("3")).toBeTruthy();
  expect(await metric("轮对话").findByText("128")).toBeTruthy();
  expect(screen.queryByRole("link", { name: "配置技能" })).toBeNull();
  expect(screen.queryByRole("link", { name: "配置知识库" })).toBeNull();
  expect(screen.queryByText(/交付.*任务/)).toBeNull();
  expect(screen.getByText("已暂停接单")).toBeTruthy();
  fireEvent.click(screen.getByRole("tab", { name: "任务记录" }));
  expect(await screen.findByText("任务记录建设中")).toBeTruthy();
  expect(screen.queryByText("历史员工范围：employee")).toBeNull();
  fireEvent.click(screen.getByRole("tab", { name: "定时任务" }));
  expect(await screen.findByText("定时任务建设中")).toBeTruthy();
  fireEvent.click(screen.getByRole("tab", { name: "长期记忆" }));
  expect(await screen.findByText("长期记忆建设中")).toBeTruthy();
});

it("shows public skills without fetching private metrics for guests", async () => {
  permissions = [];
  render(<Page />);
  expect(await screen.findByRole("heading", { name: "行政老王" })).toBeTruthy();
  expect(metric("技能").getByText("8")).toBeTruthy();
  expect(screen.getAllByText("登录后查看")).toHaveLength(2);
  expect(request).toHaveBeenCalledTimes(1);
  expect(screen.getByText("登录后查看自己的对话记录")).toBeTruthy();
  expect(screen.queryByRole("link", { name: "配置技能" })).toBeNull();
  expect(screen.queryByRole("link", { name: "配置知识库" })).toBeNull();
});

it.each([
  ["技能", "capabilities"],
  ["知识库", "instructions"],
])(
  "opens the employee's %s editor tab and preserves the personal-page return location",
  async (label, tab) => {
    permissions.push("agents:read");
    const entry = "/agents/employee/home?section=tasks&from=%2Fagents%3Fq%3D行政";
    render(<Page entry={entry} />);
    const link = await screen.findByRole("link", { name: `配置${label}` });
    const target = new URL(link.getAttribute("href")!, "http://app.local");
    expect(target.pathname).toBe("/agents/employee");
    expect(target.searchParams.get("tab")).toBe(tab);
    expect(target.searchParams.get("from")).toBe(entry);
    fireEvent.click(link);
    expect(await screen.findByRole("heading", { name: `编辑标签：${tab}` })).toBeTruthy();
    fireEvent.click(screen.getByRole("link", { name: "返回来源" }));
    expect(await screen.findByText("任务记录建设中")).toBeTruthy();
  },
);

it("keeps zero skill and knowledge counts reachable for configuration", async () => {
  permissions.push("agents:read");
  vi.mocked(request).mockImplementation(async (path) => {
    if (path.startsWith("public/agents/"))
      return { ...employee, resource_counts: { skills: 0, tools: 0, knowledge_bases: 0 } } as never;
    if (path.startsWith("knowledge-bases/employee-bindings/"))
      return { knowledge_base_ids: [] } as never;
    return { completed_rounds: 0 } as never;
  });
  render(<Page />);
  const skills = within(await screen.findByRole("group", { name: "技能" }));
  expect(skills.getByText("0")).toBeTruthy();
  expect(await metric("知识库").findByText("0")).toBeTruthy();
  expect(metric("技能").getByRole("link", { name: "配置技能" })).toBeTruthy();
  expect(metric("知识库").getByRole("link", { name: "配置知识库" })).toBeTruthy();
  expect(metric("轮对话").queryByRole("link")).toBeNull();
});

it("keeps knowledge-count retry separate from its configuration shortcut", async () => {
  permissions.push("agents:read");
  let failed = true;
  vi.mocked(request).mockImplementation(async (path) => {
    if (path.startsWith("public/agents/")) return employee as never;
    if (path.startsWith("knowledge-bases/employee-bindings/")) {
      if (failed) throw new Error("读取失败");
      return knowledge as never;
    }
    return { completed_rounds: 0 } as never;
  });
  render(<Page />);
  const retry = await screen.findByRole("button", { name: "重新读取知识库数量" });
  expect(retry.closest("a")).toBeNull();
  failed = false;
  fireEvent.click(retry);
  expect(await metric("知识库").findByText("3")).toBeTruthy();
  expect(screen.getByRole("heading", { name: "行政老王" })).toBeTruthy();
  expect(screen.getByRole("link", { name: "配置知识库" })).toBeTruthy();
});

it("keeps a failed count distinct from zero and retries only that count", async () => {
  let failed = true;
  vi.mocked(request).mockImplementation(async (path) => {
    if (path.startsWith("public/agents/")) return employee as never;
    if (path.startsWith("knowledge-bases/employee-bindings/")) return knowledge as never;
    if (failed) throw new Error("读取失败");
    return { completed_rounds: 0 } as never;
  });
  render(<Page />);
  const retry = await screen.findByRole("button", { name: "重新读取完成对话轮数" });
  expect(metric("轮对话").queryByText("0")).toBeNull();
  expect(await metric("知识库").findByText("3")).toBeTruthy();
  failed = false;
  fireEvent.click(retry);
  expect(await metric("轮对话").findByText("0")).toBeTruthy();
  expect(vi.mocked(request).mock.calls.filter(([path]) => path.startsWith("public/"))).toHaveLength(
    1,
  );
});

it("does not fetch knowledge when a signed-in user lacks its permissions", async () => {
  permissions = ["agents:read", "conversations:read", "runs:read"];
  render(<Page />);
  expect(await screen.findByText("暂无查看权限")).toBeTruthy();
  expect(await metric("轮对话").findByText("128")).toBeTruthy();
  expect(vi.mocked(request).mock.calls.some(([path]) => path.startsWith("knowledge-bases/"))).toBe(
    false,
  );
  expect(screen.queryByRole("link", { name: "配置知识库" })).toBeNull();
});

it("discards the prior identity's late statistics", async () => {
  let finishOld: (value: { completed_rounds: number }) => void = () => {};
  const old = new Promise<{ completed_rounds: number }>((resolve) => {
    finishOld = resolve;
  });
  vi.mocked(request).mockImplementation(async (path) => {
    if (path.startsWith("public/agents/")) return employee as never;
    if (path.startsWith("knowledge-bases/employee-bindings/")) return knowledge as never;
    return (user === "user" ? old : { completed_rounds: 9 }) as never;
  });
  const view = render(<Page />);
  expect(await screen.findByLabelText("正在读取完成对话轮数")).toBeTruthy();
  user = "another-user";
  view.rerender(<Page />);
  const current = within(await screen.findByRole("group", { name: "轮对话" }));
  expect(await current.findByText("9")).toBeTruthy();
  await act(async () => finishOld({ completed_rounds: 128 }));
  expect(metric("轮对话").getByText("9")).toBeTruthy();
  expect(metric("轮对话").queryByText("128")).toBeNull();
});
