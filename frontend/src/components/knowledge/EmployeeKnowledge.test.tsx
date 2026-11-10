// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useState } from "react";
import type { AgentKnowledge } from "@/lib/models/agent";
import { EmployeeKnowledge } from "./EmployeeKnowledge";

const changed = vi.fn();
const library = { id: "library", name: "组织资料", document_count: 2, chunk_count: 8 };
vi.mock("@/state/workspace/useWorkspaceData", () => ({
  useWorkspaceData: () => ({ knowledge: { libraries: () => ({}) } }),
}));
vi.mock("@/state/shared/useResource", () => ({
  useRetainedResource: () => ({ data: [library], loading: false, failure: null }),
}));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
function Form({ readOnly = false }: { readOnly?: boolean }) {
  const [value, setValue] = useState<AgentKnowledge>({
    knowledge_base_ids: [],
    mode: "on_demand",
    top_k: 6,
  });
  return (
    <EmployeeKnowledge
      value={value}
      readOnly={readOnly}
      onChange={(next) => {
        changed(next);
        setValue(next);
      }}
    />
  );
}
it("only changes the employee draft and has no independent save action", () => {
  render(<Form />);
  fireEvent.click(screen.getByRole("checkbox"));
  expect(changed).toHaveBeenLastCalledWith({
    knowledge_base_ids: ["library"],
    mode: "on_demand",
    top_k: 6,
  });
  expect(screen.getByText(/已选择 1\/10/)).toBeTruthy();
  expect(screen.queryByRole("button", { name: /保存/ })).toBeNull();
  expect(screen.queryByText("BM25")).toBeNull();
  expect(screen.getByText(/随员工“保存配置”统一生效/)).toBeTruthy();
});
it("prevents editing shared resources in readonly mode", () => {
  render(<Form readOnly />);
  expect((screen.getByRole("checkbox") as HTMLInputElement).closest("fieldset")?.disabled).toBe(
    true,
  );
});
