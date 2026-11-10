// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { RunProgress } from "./RunProgress";
import { RunActions } from "./RunActions";
import { actionFixture, runFixture } from "./conversationTestHelpers";

const animateDescriptor = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "animate");
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  if (animateDescriptor) Object.defineProperty(HTMLElement.prototype, "animate", animateDescriptor);
  else Reflect.deleteProperty(HTMLElement.prototype, "animate");
});

function advance(ms = 120) {
  act(() => vi.advanceTimersByTime(ms));
}

it("follows model, parallel tools, model output and completion without remounting the process", () => {
  vi.useFakeTimers();
  const model = actionFixture({ output_text: "", reasoning_text: "已保存的思考" });
  const run = runFixture({ steps: [model] });
  const { rerender, container } = render(<RunActions run={run} finalText="" />);
  fireEvent.click(screen.getByRole("button", { name: "执行过程" }));
  fireEvent.click(screen.getByRole("button", { name: "模型思考" }));
  expect(screen.getByText("思考中")).toBeTruthy();
  const tool = actionFixture({ id: "tool", kind: "tool_call" });
  // 即使模型排在工具后面且仍在 running，在途工具也优先。
  rerender(<RunActions run={{ ...run, steps: [tool, model] }} finalText="" />);
  advance();
  expect(screen.getByText("调用工具中")).toBeTruthy();
  rerender(
    <RunActions
      run={{
        ...run,
        steps: [
          { ...tool, status: "succeeded" },
          { ...model, output_text: "回复" },
        ],
      }}
      finalText="回复"
    />,
  );
  advance();
  expect(screen.getByText("生成回复中")).toBeTruthy();
  rerender(<RunActions run={{ ...run, status: "succeeded" }} finalText="" />);
  expect(screen.getByText("已完成")).toBeTruthy();
  expect(
    container.querySelector('[data-current="true"] .lucide-message-circle-check'),
  ).toBeTruthy();
  expect(screen.getByRole("button", { name: "模型思考" }).getAttribute("aria-expanded")).toBe(
    "true",
  );
});

it("ignores fleeting stages and applies cancellation immediately", () => {
  vi.useFakeTimers();
  const run = runFixture({ steps: [actionFixture({ output_text: "" })] });
  const { rerender } = render(<RunProgress run={run} total={1} />);
  rerender(
    <RunProgress run={{ ...run, steps: [actionFixture({ kind: "tool_call" })] }} total={1} />,
  );
  advance(80);
  rerender(<RunProgress run={run} total={1} />);
  advance();
  expect(screen.getByText("思考中")).toBeTruthy();
  expect(screen.queryByText("调用工具中")).toBeNull();
  rerender(<RunProgress run={{ ...run, status: "cancelling" }} total={1} />);
  expect(screen.getByText("正在停止")).toBeTruthy();
  advance(1000);
  expect(screen.queryByText("思考中")).toBeNull();
});

it("distinguishes pending or failed reply saving from a completed reply", () => {
  const run = runFixture({ status: "succeeded", acceptance: "pending" });
  const { rerender, container } = render(<RunProgress run={run} total={1} />);
  expect(screen.getByText("正在保存回复")).toBeTruthy();
  expect(container.querySelector('[data-current="true"] .lucide-message-circle-check')).toBeNull();
  rerender(<RunProgress run={{ ...run, acceptance: "failed" }} total={1} />);
  expect(screen.getByText("回复未保存")).toBeTruthy();
  rerender(<RunProgress run={{ ...run, acceptance: "accepted" }} total={1} />);
  expect(screen.getByText("已完成")).toBeTruthy();
});

it("uses all steps for the header while an older local page is selected", () => {
  vi.useFakeTimers();
  const steps = Array.from({ length: 101 }, (_, index) =>
    actionFixture({ id: `${index}`, status: "succeeded", output_text: "" }),
  );
  steps.push(actionFixture({ id: "active-tool", kind: "tool_call" }));
  render(<RunActions run={runFixture({ steps })} finalText="" />);
  fireEvent.click(screen.getByRole("button", { name: "执行过程" }));
  expect(screen.getByText("1 / 2")).toBeTruthy();
  expect(screen.getByText("调用工具中")).toBeTruthy();
});

it("animates only icon changes, cancels in-flight animations and skips initial entry", () => {
  vi.useFakeTimers();
  vi.stubGlobal("getComputedStyle", () => ({ getPropertyValue: () => "280ms" }));
  const cancel = vi.fn();
  const animate = vi.fn(() => ({ cancel }));
  Object.defineProperty(HTMLElement.prototype, "animate", { configurable: true, value: animate });
  const run = runFixture({ steps: [actionFixture({ output_text: "" })] });
  const { rerender, unmount } = render(<RunProgress run={run} total={1} />);
  expect(animate).not.toHaveBeenCalled();
  rerender(
    <RunProgress run={{ ...run, steps: [actionFixture({ kind: "tool_call" })] }} total={1} />,
  );
  advance();
  expect(animate).toHaveBeenCalledTimes(2);
  expect(animate).toHaveBeenNthCalledWith(
    2,
    expect.any(Array),
    expect.objectContaining({ duration: 280, delay: expect.closeTo(44.8) }),
  );
  rerender(<RunProgress run={{ ...run, status: "succeeded" }} total={1} />);
  expect(cancel).toHaveBeenCalledTimes(2);
  unmount();
  expect(cancel).toHaveBeenCalledTimes(4);
});

it("switches directly when reduced motion is enabled", () => {
  vi.stubGlobal("matchMedia", () => ({ matches: true }));
  const animate = vi.fn();
  Object.defineProperty(HTMLElement.prototype, "animate", { configurable: true, value: animate });
  const run = runFixture();
  const { rerender, container } = render(<RunProgress run={run} total={1} />);
  rerender(<RunProgress run={{ ...run, status: "failed" }} total={1} />);
  expect(screen.getByText("执行失败")).toBeTruthy();
  expect(container.querySelector('[data-current="true"] .lucide-circle-alert')).toBeTruthy();
  expect(animate).not.toHaveBeenCalled();
});
