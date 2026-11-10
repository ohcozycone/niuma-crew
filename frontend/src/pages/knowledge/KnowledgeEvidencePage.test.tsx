// @vitest-environment jsdom
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router";
import * as api from "@/lib/api/knowledge";
import { ApiError } from "@/lib/api/http";
import { KnowledgeStore } from "@/state/knowledge/knowledgeStore";
import { KnowledgeEvidencePage } from "./KnowledgeEvidencePage";

let knowledge: KnowledgeStore;
vi.mock("@/state/workspace/useWorkspaceData", () => ({
  useWorkspaceData: () => ({ knowledge }),
}));
vi.mock("@/lib/api/knowledge", async (original) => ({
  ...(await original<object>()),
  getKnowledgeEvidence: vi.fn(),
  getKnowledgeDocument: vi.fn(),
  listKnowledgeBases: vi.fn(),
}));
const run = "100000000101";
const evidence = "K-1234567812345678";
const href = `/knowledge/sources/${run}/${evidence}`;
const preview: api.KnowledgeEvidence = {
  evidence_id: evidence,
  title: "住宿制度",
  locator: "差旅 / 住宿",
  content: "住宿每晚最高400元。",
  document_version: "fixed-version",
  offset: 0,
  next_offset: null,
  total_chars: 12,
  source_url: href,
};
function open() {
  return render(
    <MemoryRouter initialEntries={[href]}>
      <Routes>
        <Route path="/knowledge/sources/:runId/:evidenceId" element={<KnowledgeEvidencePage />} />
      </Routes>
    </MemoryRouter>,
  );
}
beforeEach(() => {
  knowledge = new KnowledgeStore();
  vi.mocked(api.getKnowledgeDocument).mockClear();
  vi.mocked(api.listKnowledgeBases).mockClear();
  vi.mocked(api.getKnowledgeEvidence).mockReset().mockResolvedValue(preview);
});
afterEach(() => {
  cleanup();
  knowledge.dispose();
});

it("reads only the registered run evidence without requesting a library or document", async () => {
  open();
  await screen.findByText(preview.content);
  expect(screen.getByRole("heading", { name: preview.title })).toBeTruthy();
  expect(api.getKnowledgeEvidence).toHaveBeenCalledExactlyOnceWith(
    run,
    evidence,
    0,
    expect.any(AbortSignal),
  );
  expect(api.getKnowledgeDocument).not.toHaveBeenCalled();
  expect(api.listKnowledgeBases).not.toHaveBeenCalled();
  expect(screen.queryByRole("link", { name: /全文|原件|下载/ })).toBeNull();
});

it("rechecks on return and hides cached evidence while pending and after access fails", async () => {
  const view = open();
  await screen.findByText(preview.content);
  view.unmount();
  let reject!: (error: ApiError) => void;
  vi.mocked(api.getKnowledgeEvidence).mockImplementationOnce(
    () => new Promise((_, fail) => (reject = fail)),
  );
  open();
  expect(screen.queryByText(preview.content)).toBeNull();
  await waitFor(() => expect(api.getKnowledgeEvidence).toHaveBeenCalledTimes(2));
  await act(async () => {
    reject(new ApiError("无法读取该任务的来源。", 403, "permission_denied"));
  });
  await screen.findByRole("alert");
  expect(screen.queryByText(preview.content)).toBeNull();
  expect(screen.getByRole("link", { name: "返回员工" }).getAttribute("href")).toBe("/agents");
  expect(api.getKnowledgeDocument).not.toHaveBeenCalled();
});
