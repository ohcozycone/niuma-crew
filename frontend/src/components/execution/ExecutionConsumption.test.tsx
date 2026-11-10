// @vitest-environment jsdom
import { cleanup, render, screen, within, fireEvent } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { ExecutionAction, ExecutionTrace } from "@/lib/api/execution";
import { ExecutionBudgetEvidence, ExecutionConsumption } from "./ExecutionConsumption";

const action: ExecutionAction = {
  id: "summary",
  sequence: 4,
  action_key: "model:2",
  kind: "model_call",
  parent_action_id: null,
  status: "failed",
  error_code: "output_limit_exceeded",
  safe_details: { purpose: "summary", round: 2 },
  started_at: "2026-11-06T00:00:12.800Z",
  finished_at: "2026-11-06T00:00:51.200Z",
  output_text: "",
  reasoning_text: "",
  reasoning_truncated: false,
  metrics: {
    usage: { input_tokens: 6722, output_tokens: 4096, reasoning_tokens: 3922, total_tokens: 10818 },
    usage_source: "response",
    output_limit: 4096,
    output_limit_field: "max_tokens",
  },
};
const data = {
  run: {
    started_at: "2026-11-06T00:00:00Z",
    finished_at: "2026-11-06T00:00:51.200Z",
    usage: { total_tokens: 29655 },
  },
  actions: {
    items: [
      action,
      {
        ...action,
        id: "tool",
        sequence: 3,
        kind: "tool_call",
        safe_details: { tool: "search_knowledge" },
        metrics: undefined,
        status: "succeeded",
        error_code: null,
      },
    ],
    total: 2,
  },
} as ExecutionTrace;
afterEach(cleanup);
it("compares captured budgets and separates reasoning without counting it twice", () => {
  render(<ExecutionBudgetEvidence action={action} data={data} />);
  expect(screen.getByText(/输出预算已耗尽/)).toBeTruthy();
  expect(screen.getByText("3,922（95.8%）")).toBeTruthy();
  expect(screen.getByText("174")).toBeTruthy();
  expect(screen.getByText("38.4 秒（整轮 75.0%）")).toBeTruthy();
  expect(screen.getByText("10,818（整轮 36.5%）")).toBeTruthy();
  expect(screen.getByText(/摘要触发依据未采集/)).toBeTruthy();
});
it("does not infer a limit or zero usage from missing evidence", () => {
  render(<ExecutionBudgetEvidence action={{ ...action, metrics: undefined }} data={data} />);
  expect(screen.queryByText(/输出预算已耗尽/)).toBeNull();
  expect(screen.queryByText("174")).toBeNull();
  expect(screen.getByText("未采集")).toBeTruthy();
});
it("shows each stage with a navigation target and distinguishes tool tokens from unreported model usage", () => {
  const select = vi.fn();
  render(<ExecutionConsumption data={data} onSelectAction={select} />);
  const rows = screen.getAllByRole("row");
  expect(within(rows[1]).getByText("6,722")).toBeTruthy();
  expect(within(rows[1]).getByText("36.5%")).toBeTruthy();
  expect(within(rows[2]).getAllByText("—")).toHaveLength(4);
  fireEvent.click(screen.getByRole("button", { name: "查看步骤 4 的证据" }));
  expect(select).toHaveBeenCalledWith("summary");
});
