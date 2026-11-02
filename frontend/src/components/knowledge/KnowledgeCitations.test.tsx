// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { Markdown } from "@/components/common/Markdown";
import * as api from "@/lib/api/knowledge";
import { ApiError } from "@/lib/api/http";
import { KnowledgeStore } from "@/state/knowledge/knowledgeStore";

let knowledge: KnowledgeStore;
vi.mock("@/state/workspace/useWorkspaceData", () => ({
  useWorkspaceData: () => ({ knowledge }),
}));
vi.mock("@/lib/api/knowledge", async (original) => ({
  ...(await original<object>()),
  getKnowledgeCitation: vi.fn(),
}));
const library = "12345678-1234-1234-1234-123456789abc";
const document = "22345678-1234-1234-1234-123456789abc";
const chunk = "a".repeat(64);
const href = `/knowledge/${library}/documents/${document}?chunk=${chunk}`;
const preview: api.CitationPreview = {
  title: "报销材料与提交流程",
  locator: "报销制度 / 发票遗失",
  excerpt: "先联系开票方补发发票；无法取得时向财务提交缺票说明。",
  has_more: false,
  source_url: href,
};
function Answer() {
  return (
    <Markdown
      text={`发票遗失的处理步骤。[K-1234567812345678](${href})`}
      sourceTitles={new Map([[href, preview.title]])}
    />
  );
}
beforeEach(() => {
  knowledge = new KnowledgeStore();
  vi.mocked(api.getKnowledgeCitation).mockReset().mockResolvedValue(preview);
});
afterEach(() => {
  cleanup();
  knowledge.dispose();
  vi.restoreAllMocks();
});

it("loads a bounded source only when the citation preview opens", async () => {
  render(<Answer />);
  expect(api.getKnowledgeCitation).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "引用了 1 个来源" }));
  expect(api.getKnowledgeCitation).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: /^预览来源 1/ }));
  expect(await screen.findByText(preview.excerpt)).toBeTruthy();
  expect(screen.getByText(preview.locator)).toBeTruthy();
  expect(api.getKnowledgeCitation).toHaveBeenCalledExactlyOnceWith(
    library,
    document,
    chunk,
    expect.any(AbortSignal),
  );
  const link = screen.getByRole("link", { name: /^查看原文/ });
  expect(link.getAttribute("href")).toBe(href);
  expect(link.getAttribute("target")).toBe("_blank");
});

it("opens on keyboard focus and closes with Escape", async () => {
  render(<Answer />);
  const trigger = screen.getByRole("button", { name: /^预览来源 1/ });
  act(() => trigger.focus());
  await screen.findByText(preview.excerpt);
  fireEvent.keyDown(trigger, { key: "Escape" });
  await waitFor(() => expect(screen.queryByRole("region", { name: /^来源预览/ })).toBeNull());
});

it("rechecks on reopening and hides cached text while the new check is pending", async () => {
  render(<Answer />);
  const trigger = screen.getByRole("button", { name: /^预览来源 1/ });
  fireEvent.click(trigger);
  await screen.findByText(preview.excerpt);
  fireEvent.keyDown(trigger, { key: "Escape" });
  await waitFor(() => expect(screen.queryByRole("region", { name: /^来源预览/ })).toBeNull());
  let finish!: (value: api.CitationPreview) => void;
  vi.mocked(api.getKnowledgeCitation).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  fireEvent.click(trigger);
  await screen.findByText("正在读取来源片段…");
  expect(screen.queryByText(preview.excerpt)).toBeNull();
  await act(async () => finish({ ...preview, excerpt: "本次重新核对后的片段" }));
  await screen.findByText("本次重新核对后的片段");
  expect(api.getKnowledgeCitation).toHaveBeenCalledTimes(2);
});

it("shows inaccessible sources and lets a failed read be retried", async () => {
  vi.mocked(api.getKnowledgeCitation).mockRejectedValueOnce(
    new ApiError("引用片段已不存在。", 404, "knowledge_chunk_not_found"),
  );
  render(<Answer />);
  fireEvent.click(screen.getByRole("button", { name: /^预览来源 1/ }));
  expect(await screen.findByRole("alert")).toBeTruthy();
  expect(screen.queryByText(preview.excerpt)).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "重新读取" }));
  await screen.findByText(preview.excerpt);
});

it("cancels a pending preview when its message leaves the page", async () => {
  let signal!: AbortSignal;
  vi.mocked(api.getKnowledgeCitation).mockImplementation(
    (_library, _document, _chunk, currentSignal) => {
      signal = currentSignal!;
      return new Promise(() => {});
    },
  );
  const view = render(<Answer />);
  fireEvent.click(screen.getByRole("button", { name: /^预览来源 1/ }));
  await waitFor(() => expect(signal).toBeTruthy());
  view.unmount();
  await waitFor(() => expect(signal.aborted).toBe(true));
});
