// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/http";
import { toFailure } from "@/lib/failures/resolve";
import { FailureState } from "./FailureState";
import { FailureNotice } from "./FailureNotice";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});
describe("shared failure presentation", () => {
  it("renders optional content without empty recovery placeholders", () => {
    const { container } = render(
      <FailureState error={new ApiError("不存在", 404)} description="" />,
    );
    expect(screen.getByRole("alert").textContent).toContain("这个页面没有找到");
    expect(container.querySelector(".failure-recovery")).toBeNull();
    expect(container.querySelector(".failure-description")).toBeNull();
  });
  it("keeps a working navigation link and textual fallback when art fails", () => {
    const { container } = render(
      <FailureState
        error={new ApiError("不存在", 404)}
        actions={[{ kind: "return", label: "返回列表", href: "/agents" }]}
      />,
    );
    expect(screen.getByRole("link", { name: "返回列表" }).getAttribute("href")).toBe("/agents");
    fireEvent.error(container.querySelector("img")!);
    expect(container.querySelector("figure")).toBeNull();
    expect(screen.getByRole("heading", { name: "这个页面没有找到" })).toBeTruthy();
  });
  it("never exposes raw exceptions or renders invalid metadata as a React child", () => {
    const fact = toFailure({
      source: "http",
      status: 503,
      code: "internal_error",
      message: "请稍后重试",
      requestId: {},
    })!;
    const { rerender } = render(<FailureState failure={fact} />);
    expect(screen.queryByText(/问题编号/)).toBeNull();
    rerender(<FailureState error={new Error("private password")} />);
    expect(screen.queryByText(/private password/)).toBeNull();
    expect(screen.queryByText("500")).toBeNull();
  });
  it("honors the deadline across remounts and never retries automatically", async () => {
    vi.useFakeTimers();
    const retry = vi.fn();
    const failure = toFailure(
      new ApiError("请稍后", 429, "rate_limited", { retryAt: Date.now() + 2000 }),
    )!;
    const props = {
      failure,
      actions: [{ kind: "retry" as const, label: "重新检查", onClick: retry }],
    };
    const first = render(<FailureState {...props} />);
    expect((screen.getByRole("button", { name: "重新检查" }) as HTMLButtonElement).disabled).toBe(
      true,
    );
    act(() => vi.advanceTimersByTime(1000));
    first.unmount();
    render(<FailureState {...props} />);
    act(() => vi.advanceTimersByTime(1000));
    expect((screen.getByRole("button", { name: "重新检查" }) as HTMLButtonElement).disabled).toBe(
      false,
    );
    expect(retry).not.toHaveBeenCalled();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "重新检查" }));
    });
    expect(retry).toHaveBeenCalledTimes(1);
  });
  it("keeps compact login feedback to its safe description", () => {
    render(
      <FailureNotice
        compact
        error={new ApiError("账号或密码不正确", 401, "invalid_credentials")}
      />,
    );
    expect(screen.getByRole("alert").textContent).toBe("账号或密码不正确");
    expect(screen.queryByText("当前账号无法访问")).toBeNull();
  });
  it("announces a local failure without announcing every countdown tick", () => {
    vi.useFakeTimers();
    render(
      <FailureNotice
        failure={toFailure(
          new ApiError("请稍后", 429, "rate_limited", { retryAt: Date.now() + 2000 }),
        )}
        actions={[{ kind: "retry", label: "重新检查", onClick: vi.fn() }]}
      />,
    );
    expect(screen.getByText(/2 秒/).closest('[role="alert"]')).toBeNull();
    const announcement = screen.getByRole("alert").textContent;
    act(() => vi.advanceTimersByTime(1000));
    expect(screen.getByRole("alert").textContent).toBe(announcement);
    expect(screen.getByText(/1 秒/).closest('[role="alert"]')).toBeNull();
  });
});
