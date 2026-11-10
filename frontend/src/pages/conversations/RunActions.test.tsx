// @vitest-environment jsdom
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router";
import { fireEvent, render as renderView, screen, cleanup, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { RunActions } from "./RunActions";
import { runFixture, actionFixture } from "./conversationTestHelpers";
const render = (view: ReactElement) => renderView(view, { wrapper: MemoryRouter });
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it("shows revalidated history as its own operation with clickable original sources", () => {
  const source = `/knowledge/12345678-1234-1234-1234-123456789abc/documents/22345678-1234-1234-1234-123456789abc?chunk=${"a".repeat(64)}`;
  render(
    <RunActions
      run={runFixture({
        steps: [
          actionFixture({
            kind: "knowledge",
            safe_details: {
              operation: "history_reuse",
              source_count: 1,
              sources: [{ title: "上轮差旅制度依据", url: source, status: "succeeded" }],
            },
          }),
        ],
      })}
      finalText=""
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "执行过程" }));
  fireEvent.click(screen.getByRole("button", { name: /^核对历史知识来源/ }));
  expect(screen.getByRole("link", { name: "上轮差旅制度依据" }).getAttribute("href")).toBe(source);
  expect(screen.getByText(/平台接受本轮任务时已核对/)).toBeTruthy();
  expect(screen.queryByText("工具：未提供名称")).toBeNull();
  expect(screen.queryByText("检索知识库")).toBeNull();
});
it("opens exact internal knowledge sources but leaves unrelated relative links inert", () => {
  const source = `/knowledge/12345678-1234-1234-1234-123456789abc/documents/22345678-1234-1234-1234-123456789abc?chunk=${"a".repeat(64)}`;
  render(
    <RunActions
      run={runFixture({
        steps: [
          actionFixture({
            kind: "tool_call",
            safe_details: {
              tool: "search_knowledge",
              sources: [
                { title: "差旅制度依据", url: source, text_obtained: true },
                { title: "非法相对来源", url: "/brains" },
              ],
            },
          }),
        ],
      })}
      finalText=""
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "执行过程" }));
  fireEvent.click(screen.getByRole("button", { name: /^检索知识库/ }));
  expect(screen.getByRole("link", { name: "差旅制度依据" }).getAttribute("href")).toBe(source);
  expect(screen.queryByRole("link", { name: "非法相对来源" })).toBeNull();
});
it("reads saved steps, reflects streaming and terminal snapshots without any requests", () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  const step = actionFixture({ reasoning_text: "已有摘要" });
  const run = runFixture({ steps: [step] });
  const { rerender } = render(<RunActions run={run} finalText="" />);
  fireEvent.click(screen.getByRole("button", { name: "执行过程" }));
  fireEvent.click(screen.getByRole("button", { name: "模型思考" }));
  expect(screen.getByText("已有摘要")).toBeTruthy();
  rerender(
    <RunActions
      run={{ ...run, steps: [{ ...step, reasoning_text: "追加后的摘要" }] }}
      finalText=""
    />,
  );
  expect(screen.getByText("追加后的摘要")).toBeTruthy();
  rerender(
    <RunActions
      run={{
        ...run,
        status: "cancelled",
        steps: [{ ...step, status: "cancelled", reasoning_text: "最后保存的摘要" }],
      }}
      finalText=""
    />,
  );
  expect(screen.getByText("最后保存的摘要")).toBeTruthy();
  expect(within(screen.getByRole("button", { name: "执行过程" })).getByText("已取消")).toBeTruthy();
  expect(fetch).not.toHaveBeenCalled();
});
it("renders process text safely and preserves nested open state across collapse", () => {
  const { container } = render(
    <RunActions
      run={runFixture({
        steps: [
          actionFixture({
            safe_details: { has_tool_calls: true },
            output_text: "我先读取技能",
            reasoning_text: '<img src="https://example.test/tracker">',
          }),
        ],
      })}
      finalText=""
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "执行过程" }));
  expect(screen.getByText("本轮过程文字")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "模型思考" }));
  expect(container.querySelector("img")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "执行过程" }));
  fireEvent.click(screen.getByRole("button", { name: "执行过程" }));
  expect(screen.getByRole("button", { name: "模型思考" }).getAttribute("aria-expanded")).toBe(
    "true",
  );
});
it("paginates all loaded steps locally and retains the current page when new snapshots arrive", () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  const steps = Array.from({ length: 101 }, (_, i) =>
    actionFixture({
      id: `step-${i}`,
      sequence: i + 1,
      safe_details: { round: i + 1 },
    }),
  );
  const run = runFixture({ steps: steps });
  const { rerender } = render(<RunActions run={run} finalText="" />);
  fireEvent.click(screen.getByRole("button", { name: "执行过程" }));
  expect(screen.getByText("1 / 2")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "下一页" }));
  expect(screen.getByText("2 / 2")).toBeTruthy();
  expect(screen.getByText("模型调用 · 第 101 轮")).toBeTruthy();
  rerender(
    <RunActions
      run={{
        ...run,
        version: 2,
        steps: [...steps, actionFixture({ id: "new", safe_details: { round: 102 } })],
      }}
      finalText=""
    />,
  );
  expect(screen.getByText("2 / 2")).toBeTruthy();
  expect(screen.getByText("模型调用 · 第 102 轮")).toBeTruthy();
  expect(fetch).not.toHaveBeenCalled();
});
it("does not show an empty process", () => {
  const { container } = render(<RunActions run={runFixture({ steps: [] })} finalText="" />);
  expect(container.textContent).toBe("");
});
