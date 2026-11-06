// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router";
import * as api from "@/lib/api/knowledge";
import { ApiError } from "@/lib/api/http";
import { WorkspaceDataProvider } from "@/state/workspace/WorkspaceDataProvider";
import { EditingProvider } from "@/state/editing/useEditing";
import { KnowledgePage } from "./KnowledgePage";
import { KnowledgeUploadPanel } from "@/components/knowledge/KnowledgeUploadPanel";

let guest = false;
let canReadRules = false;
vi.mock("@/state/auth/useIdentity", () => ({
  useIdentity: () => ({
    actor: {
      kind: guest ? "guest" : "user",
      user: guest ? null : { id: "owner", username: "member" },
    },
    expires_at: "2099",
    permissions: guest
      ? []
      : ["knowledge:use", ...(canReadRules ? ["organization_rules:read"] : [])],
  }),
}));
vi.mock("@/lib/api/knowledge", () => ({
  listKnowledgeBases: vi.fn(),
  getKnowledgeBase: vi.fn(),
  createKnowledgeBase: vi.fn(),
  listKnowledgeDocuments: vi.fn(),
  getKnowledgeDocument: vi.fn(),
  uploadKnowledgeDocument: vi.fn(),
  searchKnowledge: vi.fn(),
  removeKnowledgeDocument: vi.fn(),
  originalKnowledgeUrl: vi.fn(),
  importKnowledgeDemo: vi.fn(),
  listEmbeddingConnections: vi.fn(),
  buildKnowledgeVectors: vi.fn(),
  clearKnowledgeVectors: vi.fn(),
  listKnowledgeProcessing: vi.fn(),
  processKnowledgeDocuments: vi.fn(),
  cancelKnowledgeProcessing: vi.fn(),
  updateKnowledgeBase: vi.fn(),
  previewKnowledgeDocument: vi.fn(),
}));
const kb = {
  id: "kb",
  name: "项目资料",
  description: "发布与恢复",
  document_count: 0,
  chunk_count: 0,
  updated_at: "2026-10-31T00:00:00Z",
  search_mode: "bm25" as const,
  vector_status: "not_built" as const,
  vector_connection_id: null,
  vector_connection_name: null,
  vector_chunk_count: 0,
};
const doc = {
  id: "doc",
  title: "发布说明",
  filename: "release.md",
  size: 25,
  content_hash: "hash",
  version: "v1",
  chunk_count: 1,
  created_at: kb.updated_at,
};
const chunk = {
  id: "chunk",
  document_id: "doc",
  document_version: "v1",
  title: "发布说明",
  locator: "回滚",
  start: 0,
  end: 12,
  text: "发布失败后切回上一版本。",
};
function open(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <EditingProvider>
        <WorkspaceDataProvider>
          <KnowledgeUploadPanel />
          <Routes>
            <Route path="/rules" element={<h1>全员规范</h1>} />
            <Route path="/knowledge" element={<KnowledgePage />} />
            <Route path="/knowledge/:id" element={<KnowledgePage />} />
            <Route path="/knowledge/:id/documents/:documentId" element={<KnowledgePage />} />
          </Routes>
        </WorkspaceDataProvider>
      </EditingProvider>
    </MemoryRouter>,
  );
}
afterEach(() => {
  cleanup();
  canReadRules = false;
});

it("does not delete a document on cancellation and keeps the confirmation open after a rejected delete", async () => {
  vi.mocked(api.getKnowledgeDocument).mockResolvedValue({
    ...doc,
    document: { text: chunk.text, version: "v1", parser: "library-text-v1" },
    chunks: [chunk],
  });
  vi.mocked(api.removeKnowledgeDocument).mockRejectedValue(
    new ApiError("文档正在处理，请稍后再试。", 409, "document_busy"),
  );
  open("/knowledge/kb/documents/doc");
  fireEvent.click(await screen.findByRole("button", { name: "移除文档" }));
  expect(api.removeKnowledgeDocument).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "取消" }));
  expect(api.removeKnowledgeDocument).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "移除文档" }));
  fireEvent.click(screen.getByRole("button", { name: "确认移除" }));
  await screen.findByRole("dialog");
  await screen.findAllByText("文档正在处理，请稍后再试。");
  expect(api.removeKnowledgeDocument).toHaveBeenCalledExactlyOnceWith("kb", "doc");
  expect(screen.getByRole("button", { name: "取消" })).toHaveProperty("disabled", false);
});

it("requires a separate confirmation before clearing vectors and preserves the settings dialog on cancel", async () => {
  vi.mocked(api.getKnowledgeBase).mockResolvedValue({
    ...kb,
    vector_connection_id: "embedding",
    vector_status: "ready",
  });
  vi.mocked(api.clearKnowledgeVectors).mockResolvedValue(undefined);
  open("/knowledge/kb?view=search");
  fireEvent.click(await screen.findByRole("button", { name: "检索设置" }));
  fireEvent.click(await screen.findByRole("button", { name: "移除向量索引" }));
  expect(api.clearKnowledgeVectors).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "取消" }));
  expect(screen.getByRole("dialog", { name: "检索设置" })).toBeTruthy();
  expect(api.clearKnowledgeVectors).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "移除向量索引" }));
  fireEvent.click(screen.getByRole("button", { name: "确认移除索引" }));
  await screen.findByText("向量索引已移除，文档和关键词索引保留。");
  expect(api.clearKnowledgeVectors).toHaveBeenCalledExactlyOnceWith("kb");
});
beforeEach(() => {
  vi.clearAllMocks();
  guest = false;
  vi.mocked(api.listKnowledgeBases).mockResolvedValue([kb]);
  vi.mocked(api.getKnowledgeBase).mockResolvedValue(kb);
  vi.mocked(api.listKnowledgeDocuments).mockResolvedValue([]);
  vi.mocked(api.listEmbeddingConnections).mockResolvedValue([]);
  vi.mocked(api.listKnowledgeProcessing).mockResolvedValue([]);
});
it("lists actual libraries and navigates through creation into the new library", async () => {
  vi.mocked(api.createKnowledgeBase).mockResolvedValue({ ...kb, name: "研发资料" });
  open("/knowledge");
  expect(await screen.findByRole("heading", { name: "项目资料" })).toBeTruthy();
  fireEvent.click(screen.getByRole("link", { name: "新建知识库" }));
  fireEvent.change(screen.getByRole("textbox", { name: "知识库名称" }), {
    target: { value: "研发资料" },
  });
  fireEvent.click(screen.getByRole("button", { name: "创建并添加文档" }));
  await screen.findByRole("button", { name: "添加文档" });
  expect(api.createKnowledgeBase).toHaveBeenCalledWith("研发资料", "", expect.any(String));
});
it("retains the same upload request identifier when a failed file is retried", async () => {
  vi.mocked(api.uploadKnowledgeDocument)
    .mockRejectedValueOnce(new ApiError("网络中断，请重试。", 0, "client_connection_failed"))
    .mockResolvedValueOnce(doc);
  open("/knowledge/kb");
  fireEvent.click(await screen.findByRole("button", { name: "添加文档" }));
  const input = await screen.findByLabelText("选择文件（可多选）");
  const file = new File(["# 发布"], "release.md", { type: "text/markdown" });
  fireEvent.change(input, { target: { files: [file] } });
  fireEvent.click(screen.getByRole("button", { name: "上传文件" }));
  await screen.findByText("网络中断，请重试。");
  fireEvent.click(screen.getByRole("button", { name: "收起添加文档" }));
  fireEvent.click(screen.getByRole("button", { name: "添加文档（1）" }));
  expect(await screen.findByText("网络中断，请重试。")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "重试上传" }));
  await screen.findByText("原件已保存 · 待手动处理");
  expect(api.uploadKnowledgeDocument).toHaveBeenCalledTimes(2);
  expect(vi.mocked(api.uploadKnowledgeDocument).mock.calls[0][2]).toBe(
    vi.mocked(api.uploadKnowledgeDocument).mock.calls[1][2],
  );
});
it("prioritizes existing documents while upload instructions stay collapsed", async () => {
  vi.mocked(api.listKnowledgeDocuments).mockResolvedValue([doc]);
  open("/knowledge/kb");
  expect(await screen.findByRole("heading", { name: "发布说明" })).toBeTruthy();
  expect(screen.queryByLabelText("选择文件（可多选）")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "添加文档" }));
  expect(await screen.findByLabelText("选择文件（可多选）")).toBeTruthy();
});

it("requires manual processing and submits the selected failed file for retry", async () => {
  vi.mocked(api.listKnowledgeDocuments).mockResolvedValue([
    {
      ...doc,
      chunk_count: 0,
      keyword_ready: false,
      processing_state: "failed",
      processing_error: "解析失败，可重试。",
    },
  ]);
  vi.mocked(api.processKnowledgeDocuments).mockResolvedValue({
    id: "batch",
    status: "queued",
    rules: { chunk_size: 800, chunk_overlap: 120 },
    created_at: "",
    items: [
      { id: "item", document_id: doc.id, filename: doc.filename, status: "queued", error: null },
    ],
  });
  open("/knowledge/kb");
  expect(await screen.findByText("解析失败，可重试。")).toBeTruthy();
  expect(api.processKnowledgeDocuments).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "重试处理" }));
  expect(await screen.findByRole("dialog")).toBeTruthy();
  expect(screen.getByRole("spinbutton", { name: "切分字符数" })).toHaveProperty("value", "800");
  fireEvent.click(screen.getByRole("button", { name: "开始后台处理" }));
  await screen.findByText("已提交1份文档，后台处理会继续，可离开页面。");
  expect(api.processKnowledgeDocuments).toHaveBeenCalledWith(
    "kb",
    expect.any(String),
    ["doc"],
    false,
    { chunk_size: 800, chunk_overlap: 120, min_section_chars: 200 },
  );
  expect(api.buildKnowledgeVectors).not.toHaveBeenCalled();
});

it("validates merged default chunk rules and saves metadata without processing documents", async () => {
  vi.mocked(api.getKnowledgeBase).mockResolvedValue({ ...kb, revision: 3 });
  vi.mocked(api.updateKnowledgeBase).mockResolvedValue({
    ...kb,
    revision: 4,
    chunk_size: 100,
    chunk_overlap: 10,
  });
  open("/knowledge/kb");
  fireEvent.click(await screen.findByRole("button", { name: "知识库设置" }));
  fireEvent.change(screen.getByRole("spinbutton", { name: "切分字符数" }), {
    target: { value: "100" },
  });
  expect(screen.getByRole("button", { name: "保存设置" })).toHaveProperty("disabled", true);
  fireEvent.change(screen.getByRole("spinbutton", { name: "重叠字符数" }), {
    target: { value: "10" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存设置" }));
  await waitFor(() =>
    expect(api.updateKnowledgeBase).toHaveBeenCalledWith("kb", {
      expected_revision: 3,
      name: kb.name,
      description: kb.description,
      chunk_size: 100,
      chunk_overlap: 10,
      min_section_chars: null,
    }),
  );
  expect(api.processKnowledgeDocuments).not.toHaveBeenCalled();
});

const previewResult: api.ChunkPreview = {
  document_id: "doc",
  filename: "release.md",
  rules: { chunk_size: 800, chunk_overlap: 120, min_section_chars: 200 },
  chunk_count: 2,
  short_chunk_count: 1,
  merged_chunk_count: 1,
  min_length: 10,
  max_length: 60,
  offset: 0,
  has_more: false,
  chunks: [
    {
      ...chunk,
      text: "## 发布前检查\n核对配置。\n## 发布后确认\n核对健康检查。",
      spans: [
        { block_id: "before", start: 0, end: 15 },
        { block_id: "after", start: 0, end: 15 },
      ],
    },
  ],
};

it("invalidates preview after edits and freezes the displayed temporary rules on submission", async () => {
  vi.mocked(api.listKnowledgeDocuments).mockResolvedValue([
    { ...doc, processing_state: "pending", chunk_count: 0, keyword_ready: false },
  ]);
  vi.mocked(api.previewKnowledgeDocument).mockResolvedValue(previewResult);
  vi.mocked(api.processKnowledgeDocuments).mockResolvedValue({
    id: "batch",
    status: "queued",
    rules: previewResult.rules,
    created_at: "",
    items: [
      { id: "item", document_id: doc.id, filename: doc.filename, status: "queued", error: null },
    ],
  });
  open("/knowledge/kb");
  fireEvent.click(await screen.findByRole("button", { name: "处理文档（待处理1）" }));
  expect(api.previewKnowledgeDocument).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "预览切分" }));
  await screen.findByText("共2个片段 · 10—60字符 · 1个合并片段");
  expect(screen.getByText(/合并章节/)).toBeTruthy();
  fireEvent.change(screen.getByRole("spinbutton", { name: "切分字符数" }), {
    target: { value: "100" },
  });
  expect(screen.queryByRole("region", { name: "切分预览结果" })).toBeNull();
  expect(screen.getByRole("button", { name: "开始后台处理" })).toHaveProperty("disabled", true);
  fireEvent.change(screen.getByRole("spinbutton", { name: "重叠字符数" }), {
    target: { value: "10" },
  });
  fireEvent.change(screen.getByRole("spinbutton", { name: "短章节合并阈值" }), {
    target: { value: "60" },
  });
  fireEvent.click(screen.getByRole("button", { name: "预览切分" }));
  await screen.findByText("共2个片段 · 10—60字符 · 1个合并片段");
  const rules = { chunk_size: 100, chunk_overlap: 10, min_section_chars: 60 };
  expect(api.previewKnowledgeDocument).toHaveBeenLastCalledWith(
    "kb",
    "doc",
    rules,
    0,
    expect.any(AbortSignal),
  );
  fireEvent.click(screen.getByRole("button", { name: "开始后台处理" }));
  await screen.findByText("已提交1份文档，后台处理会继续，可离开页面。");
  expect(api.processKnowledgeDocuments).toHaveBeenLastCalledWith(
    "kb",
    expect.any(String),
    undefined,
    false,
    rules,
  );
  expect(api.updateKnowledgeBase).not.toHaveBeenCalled();
});

it("cancels obsolete previews and ignores late results after a rule change", async () => {
  vi.mocked(api.listKnowledgeDocuments).mockResolvedValue([
    { ...doc, processing_state: "pending" },
  ]);
  let finish!: (value: api.ChunkPreview) => void;
  vi.mocked(api.previewKnowledgeDocument).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  open("/knowledge/kb");
  fireEvent.click(await screen.findByRole("button", { name: "处理文档（待处理1）" }));
  fireEvent.click(screen.getByRole("button", { name: "预览切分" }));
  await waitFor(() => expect(api.previewKnowledgeDocument).toHaveBeenCalledTimes(1));
  const signal = vi.mocked(api.previewKnowledgeDocument).mock.calls[0][4]!;
  fireEvent.change(screen.getByRole("spinbutton", { name: "短章节合并阈值" }), {
    target: { value: "0" },
  });
  await waitFor(() => expect(signal.aborted).toBe(true));
  await act(async () => finish(previewResult));
  expect(screen.queryByText(/共2个片段/)).toBeNull();
  expect(api.processKnowledgeDocuments).not.toHaveBeenCalled();
});

it("retries preview failures and requests the next page without publishing chunks", async () => {
  vi.mocked(api.listKnowledgeDocuments).mockResolvedValue([
    { ...doc, processing_state: "pending" },
  ]);
  vi.mocked(api.previewKnowledgeDocument)
    .mockRejectedValueOnce(new ApiError("预览暂不可用，请重试。", 503, "database_busy"))
    .mockResolvedValueOnce({ ...previewResult, chunk_count: 21, has_more: true })
    .mockResolvedValueOnce({ ...previewResult, chunk_count: 21, offset: 20, has_more: false });
  open("/knowledge/kb");
  fireEvent.click(await screen.findByRole("button", { name: "处理文档（待处理1）" }));
  fireEvent.click(screen.getByRole("button", { name: "预览切分" }));
  await screen.findByText("预览暂不可用，请重试。");
  fireEvent.click(screen.getByRole("button", { name: "重新加载" }));
  await screen.findByText(/共21个片段/);
  fireEvent.click(screen.getByRole("button", { name: "下一页" }));
  await screen.findByText("显示21—21 / 21");
  expect(api.previewKnowledgeDocument).toHaveBeenLastCalledWith(
    "kb",
    "doc",
    previewResult.rules,
    20,
    expect.any(AbortSignal),
  );
  expect(api.processKnowledgeDocuments).not.toHaveBeenCalled();
});
it("searches only the selected library and opens the exact cited chunk", async () => {
  vi.mocked(api.searchKnowledge).mockResolvedValue({
    knowledge_base_id: "kb",
    strategy: "bm25",
    hits: [{ rank: 1, score: -1, score_kind: "fts5_bm25_lower_better", chunk }],
  });
  vi.mocked(api.getKnowledgeDocument).mockResolvedValue({
    ...doc,
    document: { text: chunk.text, version: "v1", parser: "library-text-v1" },
    chunks: [chunk],
  });
  open("/knowledge/kb?view=search&question=回滚");
  await screen.findByText("发布失败后切回上一版本。");
  expect(api.searchKnowledge).toHaveBeenCalledWith("kb", "回滚", expect.any(AbortSignal), "bm25");
  fireEvent.click(screen.getByRole("link", { name: "查看来源" }));
  await screen.findByRole("region", { name: "本次命中片段" });
  expect(screen.getByRole("article", { name: "固定文档原文" }).textContent).toContain(
    "发布失败后切回上一版本。",
  );
});
it("does not request a private library list for a guest", async () => {
  guest = true;
  open("/knowledge");
  expect(screen.getByRole("link", { name: "登录" })).toBeTruthy();
  await waitFor(() => expect(api.listKnowledgeBases).not.toHaveBeenCalled());
});

it("builds vectors with the selected shared connection and retains an error for retry", async () => {
  vi.mocked(api.getKnowledgeBase).mockResolvedValue({ ...kb, chunk_count: 1 });
  vi.mocked(api.listEmbeddingConnections).mockResolvedValue([
    { id: "embedding", name: "硅基流动向量", model_id: "BAAI/bge-m3" },
  ]);
  vi.mocked(api.buildKnowledgeVectors)
    .mockRejectedValueOnce(
      new ApiError("硅基流动请求限流，请稍后重试。", 429, "embedding_rate_limited"),
    )
    .mockResolvedValueOnce({
      ...kb,
      chunk_count: 1,
      vector_status: "ready",
      vector_connection_id: "embedding",
      vector_connection_name: "硅基流动向量",
      vector_chunk_count: 1,
    });
  open("/knowledge/kb?view=search");
  expect(screen.queryByRole("button", { name: "建立向量索引" })).toBeNull();
  fireEvent.click(await screen.findByRole("button", { name: "检索设置" }));
  fireEvent.click(await screen.findByRole("button", { name: "建立向量索引" }));
  expect((await screen.findByRole("alert")).textContent).toContain(
    "硅基流动请求限流，请稍后重试。",
  );
  fireEvent.click(screen.getByRole("button", { name: "建立向量索引" }));
  await screen.findByText("向量索引已建立，可以选择“向量检索”查找资料。");
  expect(api.buildKnowledgeVectors).toHaveBeenCalledWith("kb", "embedding");
});

it.each(["vector", "hybrid"] as const)(
  "keeps %s queries separate and labels scores",
  async (strategy) => {
    vi.mocked(api.getKnowledgeBase).mockResolvedValue({ ...kb, vector_status: "ready" });
    vi.mocked(api.searchKnowledge).mockResolvedValue({
      knowledge_base_id: "kb",
      strategy,
      hits: [
        {
          rank: 1,
          score: strategy === "vector" ? 0.15 : null,
          score_kind: strategy === "vector" ? "cosine_distance_lower_better" : "rank_only",
          chunk,
        },
      ],
    });
    open("/knowledge/kb?view=search&question=回滚&strategy=" + strategy);
    await screen.findByText("发布失败后切回上一版本。");
    expect(api.searchKnowledge).toHaveBeenCalledWith(
      "kb",
      "回滚",
      expect.any(AbortSignal),
      strategy,
    );
    expect(
      screen.getByText(strategy === "vector" ? /向量距离：0.1500/ : /融合排序第 1 项/),
    ).toBeTruthy();
  },
);

it("falls back to visible documents for a member opening the rules deep link", async () => {
  open("/knowledge?tab=rules");
  expect(await screen.findByRole("heading", { name: "项目资料" })).toBeTruthy();
  expect(screen.getByRole("heading", { name: "知识库" })).toBeTruthy();
  expect(screen.queryByRole("tab", { name: "知识资料" })).toBeNull();
  expect(screen.queryByText("规章制度需要管理员权限。")).toBeNull();
});

it("redirects authorized legacy rules links to the independent management page", async () => {
  canReadRules = true;
  open("/knowledge?tab=rules");
  await screen.findByRole("heading", { name: "全员规范" });
  expect(screen.queryByRole("link", { name: "新建知识库" })).toBeNull();
});

it("shows a document-specific first-read 404 with an exit to its library", async () => {
  vi.mocked(api.getKnowledgeDocument).mockRejectedValue(
    new ApiError("不可访问", 404, "knowledge_document_not_found", {
      requestId: "document-missing",
    }),
  );
  open("/knowledge/kb/documents/missing");
  await screen.findByRole("heading", { name: "没找到这份文档" });
  expect(screen.getByLabelText("错误码 404").textContent).toBe("404");
  expect(screen.getByRole("link", { name: "返回知识库" }).getAttribute("href")).toBe(
    "/knowledge/kb",
  );
  expect(screen.getByText("问题编号：document-missing")).toBeTruthy();
  expect(screen.queryByRole("article", { name: "固定文档原文" })).toBeNull();
});

it("retains library cards and search input when a refresh fails", async () => {
  vi.mocked(api.listKnowledgeBases)
    .mockResolvedValueOnce([kb])
    .mockRejectedValueOnce(
      new ApiError("请稍后再读", 503, "backend_unavailable", { requestId: "refresh-failed" }),
    );
  open("/knowledge");
  await screen.findByRole("heading", { name: "项目资料" });
  fireEvent.change(screen.getByRole("textbox", { name: "查找知识库" }), {
    target: { value: "项目" },
  });
  fireEvent.click(screen.getByRole("button", { name: "知识库更多操作" }));
  fireEvent.click(await screen.findByRole("menuitem", { name: "重新加载列表" }));
  await screen.findByText("暂时无法更新");
  expect(screen.getByRole("heading", { name: "项目资料" })).toBeTruthy();
  expect(screen.getByRole("textbox", { name: "查找知识库" })).toHaveProperty("value", "项目");
  expect(screen.getByText("问题编号：refresh-failed")).toBeTruthy();
});

it("retains create inputs and request metadata after a rejected save", async () => {
  vi.mocked(api.createKnowledgeBase).mockRejectedValue(
    new ApiError("名称已存在，请修改名称。", 409, "knowledge_name_conflict", {
      requestId: "create-conflict",
    }),
  );
  open("/knowledge/new");
  fireEvent.change(screen.getByRole("textbox", { name: "知识库名称" }), {
    target: { value: "项目资料" },
  });
  fireEvent.click(screen.getByRole("button", { name: "创建并添加文档" }));
  await screen.findByText("名称已存在，请修改名称。");
  expect(screen.getByRole("textbox", { name: "知识库名称" })).toHaveProperty("value", "项目资料");
  expect(screen.getByText("问题编号：create-conflict")).toBeTruthy();
});

it("removes a library detail after refresh confirms it no longer exists", async () => {
  vi.mocked(api.getKnowledgeBase)
    .mockResolvedValueOnce(kb)
    .mockRejectedValueOnce(new ApiError("知识库已移除", 404, "knowledge_base_not_found"));
  open("/knowledge/kb?view=search");
  await screen.findByRole("heading", { name: "项目资料" });
  fireEvent.click(screen.getByRole("button", { name: "检索设置" }));
  fireEvent.click(await screen.findByRole("button", { name: "刷新连接与索引状态" }));
  await screen.findByRole("heading", { name: "没找到这个知识库" });
  expect(screen.queryByRole("heading", { name: "项目资料" })).toBeNull();
  expect(screen.queryByRole("button", { name: "添加文档" })).toBeNull();
});

it("blocks an unconfigured hybrid deep link while retaining the question and BM25", async () => {
  open("/knowledge/kb?view=search&question=回滚&strategy=hybrid");
  await screen.findByRole("heading", { name: "项目资料" });
  expect(screen.getByRole("textbox", { name: "检索问题" })).toHaveProperty("value", "回滚");
  expect(screen.getByRole("button", { name: "检索" })).toHaveProperty("disabled", true);
  expect(api.searchKnowledge).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("combobox", { name: "检索方式" }));
  const option = await screen.findByRole("option", { name: "混合检索" });
  expect(option.getAttribute("aria-disabled")).toBe("true");
  fireEvent.keyDown(screen.getByRole("option", { name: "关键词检索（BM25）" }), { key: "Enter" });
  await waitFor(() =>
    expect(api.searchKnowledge).toHaveBeenCalledWith("kb", "回滚", expect.any(AbortSignal), "bm25"),
  );
});

it("protects the settings dialog until index construction finishes", async () => {
  vi.mocked(api.getKnowledgeBase).mockResolvedValue({ ...kb, chunk_count: 1 });
  vi.mocked(api.listEmbeddingConnections).mockResolvedValue([
    { id: "embedding", name: "向量模型", model_id: "BAAI/bge-m3" },
  ]);
  let finish!: (value: api.KnowledgeBase) => void;
  vi.mocked(api.buildKnowledgeVectors).mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  open("/knowledge/kb?view=search");
  fireEvent.click(await screen.findByRole("button", { name: "检索设置" }));
  fireEvent.click(await screen.findByRole("button", { name: "建立向量索引" }));
  expect(screen.getByRole("button", { name: "完成" })).toHaveProperty("disabled", true);
  fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
  expect(screen.getByRole("dialog")).toBeTruthy();
  finish({ ...kb, vector_status: "ready" });
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "完成" })).toHaveProperty("disabled", false),
  );
  fireEvent.click(screen.getByRole("button", { name: "完成" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
});
