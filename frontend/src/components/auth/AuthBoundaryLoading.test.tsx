// @vitest-environment jsdom
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { request } from "@/lib/api/http";
import { AuthBoundary } from "./AuthBoundary";
vi.mock("@/lib/api/http", async (original) => ({
  ...(await original<object>()),
  request: vi.fn(),
}));
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.resetAllMocks();
});
it("never mounts protected content before identity and permissions are confirmed", async () => {
  vi.useFakeTimers();
  let resolve!: (value: unknown) => void;
  vi.mocked(request).mockImplementation(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  const protectedMount = vi.fn();
  function Protected() {
    protectedMount();
    return <p>受保护数据</p>;
  }
  render(
    <MemoryRouter>
      <AuthBoundary permission="agents:read">
        <Protected />
      </AuthBoundary>
    </MemoryRouter>,
  );
  act(() => vi.advanceTimersByTime(200));
  expect(protectedMount).not.toHaveBeenCalled();
  expect(screen.getByText("正在确认登录状态…").className).toBe("sr-only");
  await act(async () => resolve({ actor: { kind: "guest" }, permissions: [] }));
  expect(screen.getByText("无权访问此页面")).toBeTruthy();
  expect(screen.queryByText("受保护数据")).toBeNull();
  expect(protectedMount).not.toHaveBeenCalled();
});
