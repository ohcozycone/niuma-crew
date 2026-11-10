// @vitest-environment jsdom
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { ResourceStatus } from "./ResourceStatus";
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});
it("replaces an initial skeleton with content, retains that content during refresh failure and offers retry", () => {
  vi.useFakeTimers();
  const reload = vi.fn();
  function Page({ ready, error = "" }: { ready: boolean; error?: string }) {
    return (
      <MemoryRouter>
        <ResourceStatus data={{ ready, error, reload }} shape="form">
          <input aria-label="草稿" defaultValue="未提交内容" />
        </ResourceStatus>
      </MemoryRouter>
    );
  }
  const view = render(<Page ready={false} />);
  expect(screen.queryByRole("textbox")).toBeNull();
  act(() => vi.advanceTimersByTime(200));
  expect(screen.getByRole("status")).toBeTruthy();
  view.rerender(<Page ready />);
  const draft = screen.getByRole("textbox");
  view.rerender(<Page ready error="读取失败" />);
  expect(screen.getByRole("textbox")).toBe(draft);
  expect((draft as HTMLInputElement).value).toBe("未提交内容");
  expect(screen.queryByText("正在加载内容…")).toBeNull();
  screen.getByRole("button", { name: "重新加载" }).click();
  expect(reload).toHaveBeenCalledOnce();
});
