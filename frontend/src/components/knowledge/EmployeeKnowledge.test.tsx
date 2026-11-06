// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { EmployeeKnowledge } from "./EmployeeKnowledge";
import { WorkspaceDataProvider } from "@/state/workspace/WorkspaceDataProvider";
import { EditingProvider } from "@/state/editing/useEditing";
import * as api from "@/lib/api/knowledge";
import { ApiError } from "@/lib/api/http";

let user = "owner";
let permissions = ["knowledge:use", "runs:create"];
vi.mock("@/state/auth/useIdentity", () => ({
  useIdentity: () => ({
    actor: { kind: "user", user: { id: user, username: user } },
    permissions,
    expires_at: "2099",
  }),
}));
vi.mock("@/lib/api/knowledge", () => ({
  getEmployeeKnowledge: vi.fn(),
  saveEmployeeKnowledge: vi.fn(),
}));
const library: api.KnowledgeBase = {
  id: "library",
  name: "差旅制度",
  description: "住宿和交通标准",
  document_count: 2,
  chunk_count: 3,
  keyword_document_count: 1,
  updated_at: "2026-11-01T00:00:00Z",
  search_mode: "bm25",
  vector_status: "not_built",
  vector_connection_id: null,
  vector_connection_name: null,
  vector_chunk_count: 0,
};
const settings: api.EmployeeKnowledgeSettings = {
  agent_id: "employee",
  revision: 0,
  knowledge_base_ids: [],
  mode: "on_demand",
  strategy: "auto",
  top_k: 6,
  libraries: [library],
};
function App({ parentSubmit = () => {} }: { parentSubmit?: () => void }) {
  return (
    <MemoryRouter>
      <EditingProvider>
        <WorkspaceDataProvider>
          <form onSubmit={parentSubmit}>
            <EmployeeKnowledge agentId="employee" agentName="行政助理" />
          </form>
        </WorkspaceDataProvider>
      </EditingProvider>
    </MemoryRouter>
  );
}
beforeEach(() => {
  vi.resetAllMocks();
  user = "owner";
  permissions = ["knowledge:use", "runs:create"];
  vi.mocked(api.getEmployeeKnowledge).mockResolvedValue(settings);
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

it("saves the personal selection independently without submitting the employee form", async () => {
  const parentSubmit = vi.fn();
  vi.mocked(api.saveEmployeeKnowledge).mockResolvedValue({
    ...settings,
    revision: 1,
    knowledge_base_ids: [library.id],
  });
  render(<App parentSubmit={parentSubmit} />);
  fireEvent.click(await screen.findByRole("button", { name: "我的知识库（0）" }));
  expect(await screen.findByText(/仅供你使用这位员工时检索/)).toBeTruthy();
  fireEvent.click(await screen.findByRole("checkbox", { name: /差旅制度/ }));
  fireEvent.click(screen.getByRole("button", { name: "保存我的知识库" }));
  await screen.findByText("个人知识库设置已保存。");
  expect(api.saveEmployeeKnowledge).toHaveBeenCalledExactlyOnceWith("employee", {
    expected_revision: 0,
    knowledge_base_ids: [library.id],
    mode: "on_demand",
    strategy: "auto",
    top_k: 6,
  });
  expect(parentSubmit).not.toHaveBeenCalled();
});

it("retains a conflicted draft until the user explicitly loads the latest revision", async () => {
  vi.mocked(api.getEmployeeKnowledge).mockResolvedValueOnce({ ...settings, revision: 1 });
  vi.mocked(api.saveEmployeeKnowledge).mockRejectedValueOnce(
    new ApiError("个人设置已变化。", 409, "configuration_revision_conflict"),
  );
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "我的知识库（0）" }));
  fireEvent.click(await screen.findByRole("checkbox", { name: /差旅制度/ }));
  fireEvent.click(screen.getByRole("button", { name: "保存我的知识库" }));
  await screen.findByText("个人设置已变化。");
  expect(screen.getByRole("checkbox", { name: /差旅制度/ })).toHaveProperty("checked", true);
  vi.mocked(api.getEmployeeKnowledge).mockResolvedValue({ ...settings, revision: 2, top_k: 4 });
  fireEvent.click(screen.getByRole("button", { name: "载入最新设置" }));
  await waitFor(() =>
    expect(screen.getByRole("spinbutton", { name: "最多召回片段数" })).toHaveProperty("value", "4"),
  );
  expect(screen.getByRole("checkbox", { name: /差旅制度/ })).toHaveProperty("checked", false);
  vi.mocked(api.saveEmployeeKnowledge).mockResolvedValue({ ...settings, revision: 3, top_k: 4 });
  fireEvent.click(screen.getByRole("button", { name: "保存我的知识库" }));
  await screen.findByText("个人知识库设置已保存。");
  expect(api.saveEmployeeKnowledge).toHaveBeenLastCalledWith(
    "employee",
    expect.objectContaining({ expected_revision: 2, top_k: 4 }),
  );
});

it("shows an empty-library recovery path and blocks invalid top-k", async () => {
  vi.mocked(api.getEmployeeKnowledge).mockResolvedValue({ ...settings, libraries: [] });
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "我的知识库（0）" }));
  expect(await screen.findByText(/你还没有知识库/)).toBeTruthy();
  expect(screen.getByRole("link", { name: /管理知识库/ }).getAttribute("href")).toBe("/knowledge");
  fireEvent.change(screen.getByRole("spinbutton", { name: "最多召回片段数" }), {
    target: { value: "13" },
  });
  expect(screen.getByRole("button", { name: "保存我的知识库" })).toHaveProperty("disabled", true);
});

it("preserves an explicitly configured unavailable vector strategy", async () => {
  vi.mocked(api.getEmployeeKnowledge).mockResolvedValue({
    ...settings,
    knowledge_base_ids: [library.id],
    strategy: "vector",
  });
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "我的知识库（1）" }));
  expect(await screen.findByText(/当前策略仍会保存/)).toBeTruthy();
  expect(screen.getByRole("combobox", { name: "检索方式" }).textContent).toContain("仅向量");
});

it("protects dirty closing and blocks dismissal during save", async () => {
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  let finish!: (result: api.EmployeeKnowledgeSettings) => void;
  vi.mocked(api.saveEmployeeKnowledge).mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "我的知识库（0）" }));
  fireEvent.click(await screen.findByRole("checkbox", { name: /差旅制度/ }));
  fireEvent.click(screen.getByRole("button", { name: "关闭" }));
  expect(confirm).toHaveBeenCalled();
  expect(screen.getByRole("dialog")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "保存我的知识库" }));
  fireEvent.click(screen.getByRole("button", { name: "关闭" }));
  expect(screen.getByRole("dialog")).toBeTruthy();
  await act(async () => finish({ ...settings, revision: 1, knowledge_base_ids: [library.id] }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
});

it("does not show or read personal data for an unauthorized visitor", () => {
  permissions = [];
  render(<App />);
  expect(screen.queryByRole("button", { name: /我的知识库/ })).toBeNull();
  expect(api.getEmployeeKnowledge).not.toHaveBeenCalled();
});

it("clears the previous user's editor and ignores an obsolete response", async () => {
  let finish!: (value: api.EmployeeKnowledgeSettings) => void;
  vi.mocked(api.getEmployeeKnowledge).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const view = render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "我的知识库" }));
  await waitFor(() => expect(api.getEmployeeKnowledge).toHaveBeenCalledTimes(1));
  const signal = vi.mocked(api.getEmployeeKnowledge).mock.calls[0][1]!;
  user = "second";
  vi.mocked(api.getEmployeeKnowledge).mockResolvedValue({ ...settings, libraries: [] });
  view.rerender(<App />);
  await waitFor(() => expect(signal.aborted).toBe(true));
  await act(async () => finish({ ...settings, knowledge_base_ids: [library.id] }));
  expect(screen.queryByRole("dialog")).toBeNull();
  fireEvent.click(await screen.findByRole("button", { name: "我的知识库（0）" }));
  expect(await screen.findByText(/你还没有知识库/)).toBeTruthy();
  expect(screen.queryByText(library.name)).toBeNull();
});
