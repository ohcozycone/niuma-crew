import { expect, it } from "vitest";
import type { ExecutionAction } from "@/lib/api/execution";
import { actionTitle } from "./executionPresentation";

it("labels tool discovery without adding a new action kind", () => {
  const action: ExecutionAction = {
    id: "discovery",
    sequence: 1,
    action_key: "tool:discover",
    parent_action_id: "model",
    kind: "tool_call",
    status: "succeeded",
    safe_details: { category: "tool_discovery", matched_count: 3, tool: "search_tools" },
    output_text: "",
    reasoning_text: "",
    reasoning_truncated: false,
    error_code: null,
    started_at: "2026-11-09T12:00:00Z",
    finished_at: "2026-11-09T12:00:01Z",
  };
  expect(actionTitle(action)).toBe("发现工具 · 命中 3 项");
  expect(actionTitle({ ...action, safe_details: { tool: "read_file" } })).toBe("read_file");
});
