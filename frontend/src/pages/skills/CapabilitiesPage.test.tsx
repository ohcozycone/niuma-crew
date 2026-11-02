// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { request } from "@/lib/api/http";
import { WorkspaceDataProvider } from "@/state/workspace/WorkspaceDataProvider";
import { CapabilitiesPage } from "./CapabilitiesPage";

vi.mock("@/state/auth/useIdentity", () => ({
  useIdentity: () => ({
    actor: { kind: "user", user: { id: "owner" } },
    permissions: ["agents:read"],
  }),
}));
vi.mock("@/lib/api/http", async (original) => ({
  ...(await original<object>()),
  request: vi.fn(),
}));
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.resetAllMocks();
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
