// @vitest-environment jsdom
import { StrictMode } from "react";
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { createMemoryRouter, Outlet, RouterProvider, useNavigation } from "react-router";
import { LoadingFeedback, NavigationProgress } from "./LoadingFeedback";
import { RefreshButton } from "./RefreshButton";

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

it("does not flash for fast work and restarts the delay for each new wait", () => {
  const view = render(
    <StrictMode>
      <LoadingFeedback pending shape="employees" />
    </StrictMode>,
  );
  act(() => vi.advanceTimersByTime(199));
  expect(screen.queryByRole("status")).toBeNull();
  view.rerender(
    <StrictMode>
      <LoadingFeedback pending={false} />
    </StrictMode>,
  );
  act(() => vi.advanceTimersByTime(500));
  expect(screen.queryByRole("status")).toBeNull();
  view.rerender(
    <StrictMode>
      <LoadingFeedback pending shape="form" />
    </StrictMode>,
  );
  act(() => vi.advanceTimersByTime(199));
  expect(screen.queryByRole("status")).toBeNull();
  act(() => vi.advanceTimersByTime(1));
  expect(screen.getByRole("status").textContent).toBe("正在加载内容…");
  expect(screen.getByText("正在加载内容…").className).toBe("sr-only");
  view.rerender(
    <StrictMode>
      <LoadingFeedback pending={false} />
    </StrictMode>,
  );
  expect(screen.queryByRole("status")).toBeNull();
});

it("cleans up feedback timers when the owning area unmounts", () => {
  const view = render(<LoadingFeedback />);
  expect(vi.getTimerCount()).toBe(1);
  view.unmount();
  expect(vi.getTimerCount()).toBe(0);
});

it("keeps a refresh action disabled immediately but delays its visual spinner", () => {
  const click = vi.fn();
  const view = render(<RefreshButton loading onClick={click} />);
  const button = screen.getByRole("button", { name: "刷新列表" });
  expect(button.getAttribute("aria-busy")).toBe("true");
  expect(button.hasAttribute("disabled")).toBe(true);
  expect(button.querySelector("[data-slot=button-spinner]")).toBeNull();
  act(() => vi.advanceTimersByTime(200));
  expect(button.querySelector("[data-slot=button-spinner]")).not.toBeNull();
  view.rerender(<RefreshButton onClick={click} />);
  expect(button.hasAttribute("disabled")).toBe(false);
  expect(button.querySelector("[data-slot=button-spinner]")).toBeNull();
});

it("leaves the initial skeleton as the only visual feedback while refresh stays unavailable", () => {
  render(<RefreshButton loading showProgress={false} onClick={vi.fn()} />);
  act(() => vi.advanceTimersByTime(1000));
  const button = screen.getByRole("button", { name: "刷新列表" });
  expect(button.hasAttribute("disabled")).toBe(true);
  expect(button.getAttribute("aria-busy")).toBe("true");
  expect(button.querySelector("[data-slot=button-spinner]")).toBeNull();
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
function Shell() {
  const navigation = useNavigation();
  return (
    <>
      <header>稳定顶栏</header>
      <NavigationProgress pending={navigation.state !== "idle"} />
      <Outlet />
    </>
  );
}

it("retains the current page through superseded lazy navigation and clears progress on completion", async () => {
  const first = deferred<{ Component: () => React.ReactNode }>();
  const second = deferred<{ Component: () => React.ReactNode }>();
  const router = createMemoryRouter([
    {
      Component: Shell,
      children: [
        { path: "/", element: <p>当前页面</p> },
        { path: "/first", lazy: () => first.promise },
        { path: "/second", lazy: () => second.promise },
      ],
    },
  ]);
  const view = render(<RouterProvider router={router} />);
  let firstNavigation!: Promise<void>;
  act(() => {
    firstNavigation = router.navigate("/first");
  });
  act(() => vi.advanceTimersByTime(199));
  expect(view.container.querySelector(".navigation-progress")).toBeNull();
  expect(screen.getByText("当前页面")).toBeTruthy();
  act(() => vi.advanceTimersByTime(1));
  expect(view.container.querySelector(".navigation-progress")).not.toBeNull();
  let secondNavigation!: Promise<void>;
  act(() => {
    secondNavigation = router.navigate("/second");
  });
  expect(screen.getByText("当前页面")).toBeTruthy();
  expect(screen.getAllByText("稳定顶栏")).toHaveLength(1);
  await act(async () => {
    second.resolve({ Component: () => <p>目标页面</p> });
    await secondNavigation;
  });
  expect(screen.getByText("目标页面")).toBeTruthy();
  expect(view.container.querySelector(".navigation-progress")).toBeNull();
  await act(async () => {
    first.resolve({ Component: () => <p>过期页面</p> });
    await firstNavigation;
  });
  expect(screen.queryByText("过期页面")).toBeNull();
  view.unmount();
  router.dispose();
  expect(vi.getTimerCount()).toBe(0);
});

it("shows only a delayed neutral fallback during direct-entry module loading", async () => {
  const module = deferred<{ Component: () => React.ReactNode }>();
  const router = createMemoryRouter([
    {
      path: "/",
      lazy: () => module.promise,
      hydrateFallbackElement: <LoadingFeedback shape="document" />,
    },
  ]);
  render(<RouterProvider router={router} />);
  expect(screen.queryByRole("status")).toBeNull();
  act(() => vi.advanceTimersByTime(200));
  expect(screen.getByRole("status")).toBeTruthy();
  await act(async () => {
    module.resolve({ Component: () => <p>已打开</p> });
    await Promise.resolve();
  });
  expect(screen.getByText("已打开")).toBeTruthy();
  expect(screen.queryByRole("status")).toBeNull();
  router.dispose();
});
