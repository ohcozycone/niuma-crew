// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { request } from "@/lib/api/http";
import { skillLibrary } from "@/lib/api/skills";
import { WorkspaceDataProvider } from "@/state/workspace/WorkspaceDataProvider";
import { CapabilitiesPage } from "./CapabilitiesPage";

let management = false;
vi.mock("@/state/auth/useIdentity", () => ({
  useIdentity: () => ({
    actor: { kind: "user", user: { id: "owner" } },
    permissions: management ? ["tools:read", "skills:create", "skills:update"] : ["agents:read"],
  }),
}));
vi.mock("@/lib/api/skills", async (original) => ({
  ...(await original<object>()),
  skillLibrary: vi.fn(),
}));
vi.mock("@/lib/api/http", async (original) => ({
  ...(await original<object>()),
  request: vi.fn(),
}));
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.resetAllMocks();
  management = false;
});

it("opens directory maintenance from more without syncing or losing the dialog", async () => {
  management = true;
  vi.mocked(request).mockResolvedValue({ items: [], total: 0 });
  vi.mocked(skillLibrary).mockResolvedValue({ directory: "/data/.agents/skills" });
  render(
    <MemoryRouter>
      <WorkspaceDataProvider>
        <CapabilitiesPage />
      </WorkspaceDataProvider>
    </MemoryRouter>,
  );
  await screen.findByText("没有找到能力，可从“添加能力”新建技能或接入 MCP。");
  expect(skillLibrary).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "能力库更多操作" }));
  expect(await screen.findByRole("menuitem", { name: "内置文件与代码工具" })).toHaveProperty(
    "href",
    expect.stringContaining("/tools?native=1"),
  );
  fireEvent.click(screen.getByRole("menuitem", { name: "从服务器目录同步技能" }));
  await screen.findByRole("dialog", { name: "从服务器目录同步技能" });
  await screen.findByText("/data/.agents/skills");
  expect(request).toHaveBeenCalledTimes(1);
});

it("requests only the final search, resets its page, retains its type and flushes Enter", async () => {
  vi.mocked(request).mockResolvedValue({ items: [], total: 45 });
  render(
    <MemoryRouter initialEntries={["/skills?kind=skill&offset=20"]}>
      <WorkspaceDataProvider>
        <CapabilitiesPage />
      </WorkspaceDataProvider>
    </MemoryRouter>,
  );
  await act(async () => {});
  expect(request).toHaveBeenCalledTimes(1);
  vi.useFakeTimers();
  const input = screen.getByRole("textbox", { name: "搜索能力" });
  fireEvent.change(input, { target: { value: "工" } });
  await act(async () => vi.advanceTimersByTimeAsync(200));
  fireEvent.change(input, { target: { value: "工作流" } });
  await act(async () => vi.advanceTimersByTimeAsync(299));
  expect(request).toHaveBeenCalledTimes(1);
  await act(async () => vi.advanceTimersByTimeAsync(1));
  expect(request).toHaveBeenCalledTimes(2);
  const query = new URLSearchParams(vi.mocked(request).mock.lastCall?.[0].split("?")[1]);
  expect(query.get("q")).toBe("工作流");
  expect(query.get("offset")).toBe("0");
  expect(query.get("kind")).toBe("skill");
  fireEvent.change(input, { target: { value: "写作" } });
  fireEvent.keyDown(input, { key: "Enter" });
  await act(async () => {});
  expect(request).toHaveBeenCalledTimes(3);
  expect(vi.mocked(request).mock.lastCall?.[0]).toContain("q=%E5%86%99%E4%BD%9C");
  await act(async () => vi.advanceTimersByTimeAsync(1000));
  expect(request).toHaveBeenCalledTimes(3);
});
