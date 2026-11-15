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
let readOnly = false;
let member = false;
vi.mock("@/state/auth/useIdentity", () => ({
  useIdentity: () => ({
    actor: {
      kind: guest ? "guest" : "user",
      user: guest ? null : { id: "owner", username: "member" },
    },
    expires_at: "2099",
    permissions: guest
      ? []
      : member
        ? ["knowledge:use"]
        : readOnly
          ? ["knowledge:read"]
          : ["knowledge:manage", ...(canReadRules ? ["organization_rules:read"] : [])],
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
  listKnowledgeVectorJobs: vi.fn(),
  cancelKnowledgeVectorJob: vi.fn(),
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
const vectorJob: api.VectorJob = {
  id: "vector-job",
  status: "queued",
  connection_id: "embedding",
  chunk_count: 1,
  completed_count: 0,
  reused_count: 0,
  error: null,
  created_at: kb.updated_at,
  updated_at: kb.updated_at,
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

it("requires a separate confirmation before clearing vectors and preserves the index page on cancel", async () => {
  vi.mocked(api.getKnowledgeBase).mockResolvedValue({
    ...kb,
    vector_connection_id: "embedding",
    vector_status: "ready",
  });
  vi.mocked(api.clearKnowledgeVectors).mockResolvedValue(undefined);
  open("/knowledge/kb?view=search");
  fireEvent.click(await screen.findByRole("tab", { name: "检索设置" }));
  fireEvent.click(await screen.findByRole("button", { name: "移除向量索引" }));
  expect(api.clearKnowledgeVectors).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "取消" }));
  expect(screen.getByRole("region", { name: "知识库向量索引" })).toBeTruthy();
  expect(api.clearKnowledgeVectors).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "移除向量索引" }));
  fireEvent.click(screen.getByRole("button", { name: "确认移除索引" }));
  await screen.findByText("向量索引已移除，文档和关键词索引保留。");
  expect(api.clearKnowledgeVectors).toHaveBeenCalledExactlyOnceWith("kb");
});
beforeEach(() => {
  vi.clearAllMocks();
  guest = false;
  readOnly = false;
  member = false;
  vi.mocked(api.listKnowledgeBases).mockResolvedValue([kb]);
  vi.mocked(api.getKnowledgeBase).mockResolvedValue(kb);
  vi.mocked(api.listKnowledgeDocuments).mockResolvedValue([]);
  vi.mocked(api.listEmbeddingConnections).mockResolvedValue([]);
  vi.mocked(api.listKnowledgeProcessing).mockResolvedValue([]);
  vi.mocked(api.listKnowledgeVectorJobs).mockResolvedValue([]);
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
  await screen.findByRole("button", { name: "上传文件" });
  expect(api.createKnowledgeBase).toHaveBeenCalledWith("研发资料", "", expect.any(String));
});
it("retains the same upload request identifier when a failed file is retried", async () => {
  vi.mocked(api.uploadKnowledgeDocument)
    .mockRejectedValueOnce(new ApiError("网络中断，请重试。", 0, "client_connection_failed"))
    .mockResolvedValueOnce(doc);
  open("/knowledge/kb");
  fireEvent.click(await screen.findByRole("button", { name: "上传文件" }));
  const input = await screen.findByLabelText("选择文件（可多选）");
  const file = new File(["# 发布"], "release.md", { type: "text/markdown" });
  fireEvent.change(input, { target: { files: [file] } });
  fireEvent.click(screen.getByRole("button", { name: "上传文件" }));
  await screen.findByText("网络中断，请重试。");
  fireEvent.click(screen.getByRole("button", { name: "收起上传" }));
  fireEvent.click(screen.getByRole("button", { name: "上传文件（1）" }));
  expect(await screen.findByText("网络中断，请重试。")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "重试上传" }));
  await screen.findByText("已上传 · 待分片");
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
  fireEvent.click(screen.getByRole("button", { name: "上传文件" }));
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
  fireEvent.click(screen.getByRole("button", { name: "重试分片" }));
  expect(screen.queryByRole("dialog")).toBeNull();
  await screen.findByText("已提交 1 份文档。后台处理会继续，可离开页面。");
  expect(api.processKnowledgeDocuments).toHaveBeenCalledWith("kb", expect.any(String), ["doc"], {
    chunk_size: 800,
    chunk_overlap: 120,
    min_section_chars: 200,
  });
  expect(api.buildKnowledgeVectors).not.toHaveBeenCalled();
});

it("saves library metadata without offering a second rules editor", async () => {
  vi.mocked(api.getKnowledgeBase).mockResolvedValue({ ...kb, revision: 3, chunk_size: 600 });
  vi.mocked(api.updateKnowledgeBase).mockResolvedValue({ ...kb, revision: 4 });
  open("/knowledge/kb");
  fireEvent.click(await screen.findByRole("button", { name: "知识库设置" }));
  expect(screen.queryByRole("spinbutton")).toBeNull();
  fireEvent.change(screen.getByRole("textbox", { name: "知识库名称" }), {
    target: { value: "研发资料" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存设置" }));
  await waitFor(() =>
    expect(api.updateKnowledgeBase).toHaveBeenCalledWith("kb", {
      expected_revision: 3,
      name: "研发资料",
      description: kb.description,
      chunk_size: 600,
      chunk_overlap: null,
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
  fireEvent.click(await screen.findByRole("checkbox", { name: "选择release.md" }));
  fireEvent.click(screen.getByRole("button", { name: "调整" }));
  expect(api.previewKnowledgeDocument).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "预览切分" }));
  await screen.findByText("共2个片段 · 10—60字符 · 1个合并片段");
  expect(screen.getByText(/合并章节/)).toBeTruthy();
  fireEvent.change(screen.getByRole("spinbutton", { name: "切分字符数" }), {
    target: { value: "100" },
  });
  expect(screen.queryByRole("region", { name: "切分预览结果" })).toBeNull();
  expect(screen.getByRole("button", { name: "确认设置" })).toHaveProperty("disabled", true);
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
  fireEvent.click(screen.getByRole("button", { name: "确认设置" }));
  expect(api.processKnowledgeDocuments).not.toHaveBeenCalled();
  expect(screen.queryByRole("dialog")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "分片并建关键词索引" }));
  await screen.findByText("已提交 1 份文档。后台处理会继续，可离开页面。");
  expect(api.processKnowledgeDocuments).toHaveBeenLastCalledWith(
    "kb",
    expect.any(String),
    ["doc"],
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
  fireEvent.click(await screen.findByRole("checkbox", { name: "选择release.md" }));
  fireEvent.click(screen.getByRole("button", { name: "调整" }));
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
  fireEvent.click(await screen.findByRole("checkbox", { name: "选择release.md" }));
  fireEvent.click(screen.getByRole("button", { name: "调整" }));
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
  vi.mocked(api.getKnowledgeBase).mockResolvedValue({ ...kb, chunk_count: 1 });
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
  expect(api.searchKnowledge).toHaveBeenCalledWith("kb", "回滚", expect.any(AbortSignal), "auto");
  fireEvent.click(screen.getByRole("link", { name: "查看来源" }));
  await screen.findByRole("region", { name: "本次命中片段" });
  expect(screen.getByRole("article", { name: "固定文档原文" }).textContent).toContain(
    "发布失败后切回上一版本。",
  );
});
it("does not request the library list without read permission", async () => {
  guest = true;
  open("/knowledge");
  expect(screen.getByRole("link", { name: "登录" })).toBeTruthy();
  await waitFor(() => expect(api.listKnowledgeBases).not.toHaveBeenCalled());
});

it("directs members to employees without requesting organization library management", async () => {
  member = true;
  open("/knowledge");
  expect(screen.getByText("知识库由管理员统一维护，请通过员工使用已配置的知识资料。")).toBeTruthy();
  expect(screen.getByRole("link", { name: "返回员工" })).toBeTruthy();
  expect(screen.queryByRole("link", { name: "登录" })).toBeNull();
  await waitFor(() => expect(api.listKnowledgeBases).not.toHaveBeenCalled());
});

it("builds vectors with the selected shared connection and retains an error for retry", async () => {
  vi.mocked(api.getKnowledgeBase).mockResolvedValue({ ...kb, chunk_count: 1 });
  vi.mocked(api.listKnowledgeDocuments).mockResolvedValue([doc]);
  vi.mocked(api.listEmbeddingConnections).mockResolvedValue([
    { id: "embedding", name: "硅基流动向量", model_id: "BAAI/bge-m3" },
  ]);
  vi.mocked(api.buildKnowledgeVectors)
    .mockRejectedValueOnce(
      new ApiError("硅基流动请求限流，请稍后重试。", 429, "embedding_rate_limited"),
    )
    .mockImplementationOnce(async () => {
      vi.mocked(api.listKnowledgeVectorJobs).mockResolvedValue([vectorJob]);
      return vectorJob;
    });
  open("/knowledge/kb?view=search");
  expect(screen.queryByRole("button", { name: /建立向量索引/ })).toBeNull();
  fireEvent.click(await screen.findByRole("tab", { name: "检索设置" }));
  fireEvent.click(await screen.findByRole("button", { name: /建立向量索引/ }));
  expect((await screen.findByRole("alert")).textContent).toContain(
    "硅基流动请求限流，请稍后重试。",
  );
  fireEvent.click(screen.getByRole("button", { name: /建立向量索引/ }));
  await screen.findByText("向量任务：排队中");
  expect(api.buildKnowledgeVectors).toHaveBeenCalledWith("kb", "embedding", expect.any(String));
});

it.each(["ready", "partial"] as const)(
  "automatically searches %s vectors without a strategy selector",
  async (vectorStatus) => {
    vi.mocked(api.getKnowledgeBase).mockResolvedValue({
      ...kb,
      chunk_count: 1,
      vector_status: vectorStatus,
    });
    vi.mocked(api.searchKnowledge).mockResolvedValue({
      knowledge_base_id: "kb",
      strategy: "hybrid",
      hits: [{ rank: 1, score: null, score_kind: "rank_only", chunk }],
    });
    open("/knowledge/kb?view=search&question=回滚");
    await screen.findByText("发布失败后切回上一版本。");
    expect(api.searchKnowledge).toHaveBeenCalledWith("kb", "回滚", expect.any(AbortSignal), "auto");
    expect(screen.queryByRole("combobox")).toBeNull();
    expect(screen.getByText("当前使用：关键词＋语义混合检索")).toBeTruthy();
    expect(screen.getByText(/融合排序第 1 项/)).toBeTruthy();
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
  fireEvent.click(screen.getByRole("button", { name: "刷新知识库列表" }));
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
  fireEvent.click(screen.getByRole("tab", { name: "检索设置" }));
  fireEvent.click(await screen.findByRole("button", { name: "刷新连接与索引状态" }));
  await screen.findByRole("heading", { name: "没找到这个知识库" });
  expect(screen.queryByRole("heading", { name: "项目资料" })).toBeNull();
  expect(screen.queryByRole("button", { name: "上传文件" })).toBeNull();
});

it("disables an empty library query and links to document processing", async () => {
  open("/knowledge/kb?view=search&question=回滚");
  await screen.findByRole("heading", { name: "项目资料" });
  expect(screen.getByRole("textbox", { name: "检索问题" })).toHaveProperty("value", "回滚");
  expect(screen.getByRole("button", { name: "检索" })).toHaveProperty("disabled", true);
  expect(api.searchKnowledge).not.toHaveBeenCalled();
  expect(screen.queryByRole("combobox")).toBeNull();
  fireEvent.click(screen.getByRole("link", { name: "文档页" }));
  expect(await screen.findByRole("button", { name: "分片并建关键词索引" })).toHaveProperty(
    "disabled",
    true,
  );
});

it("allows navigation during submission and reloads a background job when returning", async () => {
  vi.mocked(api.getKnowledgeBase).mockResolvedValue({ ...kb, chunk_count: 1 });
  vi.mocked(api.listKnowledgeDocuments).mockResolvedValue([doc]);
  vi.mocked(api.listEmbeddingConnections).mockResolvedValue([
    { id: "embedding", name: "向量模型", model_id: "BAAI/bge-m3" },
  ]);
  let finish!: (value: api.VectorJob) => void;
  vi.mocked(api.buildKnowledgeVectors).mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  open("/knowledge/kb?view=settings");
  const build = await screen.findByRole("button", { name: /建立向量索引/ });
  await waitFor(() => expect(build).toHaveProperty("disabled", false));
  fireEvent.click(build);
  fireEvent.click(build);
  expect(api.buildKnowledgeVectors).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("tab", { name: "文档" }).getAttribute("aria-disabled")).not.toBe("true");
  expect(screen.getByRole("tab", { name: "检索测试" }).getAttribute("aria-disabled")).not.toBe(
    "true",
  );
  expect(screen.getByRole("button", { name: "上传文件" })).toHaveProperty("disabled", false);
  fireEvent.click(screen.getByRole("tab", { name: "检索测试" }));
  expect(await screen.findByRole("textbox", { name: "检索问题" })).toBeTruthy();
  vi.mocked(api.listKnowledgeVectorJobs).mockResolvedValue([vectorJob]);
  await act(async () => finish(vectorJob));
  fireEvent.click(screen.getByRole("tab", { name: "检索设置" }));
  await screen.findByText("向量任务：排队中");
  expect(screen.getByRole("button", { name: "向量任务进行中" })).toHaveProperty("disabled", true);
  expect(screen.getByRole("button", { name: "取消向量任务" })).toHaveProperty("disabled", false);
  fireEvent.click(screen.getByRole("link", { name: "全部知识库" }));
  await screen.findByRole("heading", { name: "知识库" });
  vi.mocked(api.listKnowledgeVectorJobs).mockResolvedValue([
    { ...vectorJob, status: "succeeded", completed_count: 1, reused_count: 1 },
  ]);
  fireEvent.click(screen.getByRole("link", { name: /项目资料/ }));
  fireEvent.click(await screen.findByRole("tab", { name: "检索设置" }));
  await screen.findByText("向量任务：已完成");
  expect(screen.getByRole("progressbar").getAttribute("aria-valuetext")).toContain("其中复用 1 个");
});

it("selects only available filtered documents and preserves selections outside the search", async () => {
  vi.mocked(api.listKnowledgeDocuments).mockResolvedValue([
    doc,
    { ...doc, id: "second", title: "发布检查", filename: "check.md" },
    { ...doc, id: "other", title: "费用报销", filename: "expense.md" },
    { ...doc, id: "busy", title: "发布中", filename: "busy.md", processing_state: "processing" },
  ]);
  open("/knowledge/kb");
  const all = await screen.findByRole("checkbox", { name: "全选当前结果" });
  fireEvent.click(screen.getByRole("checkbox", { name: "选择release.md" }));
  expect(all).toHaveProperty("indeterminate", true);
  fireEvent.change(screen.getByRole("textbox", { name: "查找库内文档" }), {
    target: { value: "费用" },
  });
  fireEvent.click(all);
  expect(screen.getByRole("status").textContent).toContain("已选 2 份");
  fireEvent.click(all);
  expect(screen.getByRole("status").textContent).toContain("已选 1 份");
  fireEvent.change(screen.getByRole("textbox", { name: "查找库内文档" }), {
    target: { value: "发布" },
  });
  expect(all).toHaveProperty("indeterminate", true);
  fireEvent.click(all);
  expect(screen.getByRole("checkbox", { name: "选择busy.md" })).toHaveProperty("disabled", true);
  expect(screen.getByRole("checkbox", { name: "选择busy.md" })).toHaveProperty("checked", false);
  expect(screen.getByRole("status").textContent).toContain("已选 2 份");
  expect(screen.queryByRole("button", { name: "清空选择" })).toBeNull();
  expect(screen.queryByRole("button", { name: "全选" })).toBeNull();
  expect(screen.queryByRole("button", { name: "反选" })).toBeNull();
  fireEvent.click(all);
  expect(all).toHaveProperty("checked", false);
  expect(all).toHaveProperty("indeterminate", false);
});

it("includes selected ready documents in rechunking and submits only their identifiers", async () => {
  vi.mocked(api.listKnowledgeDocuments).mockResolvedValue([doc]);
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
  fireEvent.click(await screen.findByRole("checkbox", { name: "选择release.md" }));
  fireEvent.click(screen.getByRole("button", { name: "分片并建关键词索引" }));
  expect(screen.queryByRole("dialog")).toBeNull();
  await waitFor(() =>
    expect(api.processKnowledgeDocuments).toHaveBeenCalledWith(
      "kb",
      expect.any(String),
      ["doc"],
      previewResult.rules,
    ),
  );
  expect(api.buildKnowledgeVectors).not.toHaveBeenCalled();
});

it("switches tabs without losing the test question", async () => {
  open("/knowledge/kb?view=search&question=回滚");
  fireEvent.click(await screen.findByRole("tab", { name: "检索设置" }));
  expect(await screen.findByRole("region", { name: "知识库向量索引" })).toBeTruthy();
  expect(screen.queryByRole("textbox", { name: "检索问题" })).toBeNull();
  fireEvent.click(screen.getByRole("tab", { name: "检索测试" }));
  expect(await screen.findByRole("textbox", { name: "检索问题" })).toHaveProperty("value", "回滚");
  expect(api.buildKnowledgeVectors).not.toHaveBeenCalled();
});

it("keeps document selection and processing disabled for read-only visitors", async () => {
  readOnly = true;
  vi.mocked(api.listKnowledgeDocuments).mockResolvedValue([
    { ...doc, processing_state: "pending" },
  ]);
  open("/knowledge/kb");
  expect(await screen.findByRole("checkbox", { name: "全选当前结果" })).toHaveProperty(
    "disabled",
    true,
  );
  expect(screen.getByRole("checkbox", { name: "选择release.md" })).toHaveProperty("disabled", true);
  expect(screen.getByRole("button", { name: "分片并建关键词索引" })).toHaveProperty(
    "disabled",
    true,
  );
  expect(api.processKnowledgeDocuments).not.toHaveBeenCalled();
});

it("keeps the question when entering automatic search from settings", async () => {
  vi.mocked(api.getKnowledgeBase).mockResolvedValue({
    ...kb,
    chunk_count: 1,
    vector_status: "ready",
  });
  open("/knowledge/kb?view=settings&question=回滚");
  fireEvent.click(await screen.findByRole("link", { name: "前往检索测试" }));
  expect(await screen.findByRole("textbox", { name: "检索问题" })).toHaveProperty("value", "回滚");
  await waitFor(() =>
    expect(api.searchKnowledge).toHaveBeenCalledWith("kb", "回滚", expect.any(AbortSignal), "auto"),
  );
});

it("keeps rules and the process action stable until the user confirms, and discards cancelled drafts", async () => {
  vi.mocked(api.listKnowledgeDocuments).mockResolvedValue([doc]);
  open("/knowledge/kb");
  const action = await screen.findByRole("button", { name: "分片并建关键词索引" });
  expect(action).toHaveProperty("disabled", true);
  fireEvent.click(screen.getByRole("button", { name: "调整" }));
  expect(screen.getByRole("button", { name: "预览切分" })).toHaveProperty("disabled", true);
  fireEvent.change(screen.getByRole("spinbutton", { name: "切分字符数" }), {
    target: { value: "900" },
  });
  fireEvent.click(screen.getByRole("button", { name: "取消" }));
  expect(screen.queryByRole("dialog")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "调整" }));
  expect(screen.getByRole("spinbutton", { name: "切分字符数" })).toHaveProperty("value", "800");
  fireEvent.change(screen.getByRole("spinbutton", { name: "切分字符数" }), {
    target: { value: "900" },
  });
  fireEvent.keyDown(document.activeElement || document.body, { key: "Escape" });
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  fireEvent.click(screen.getByRole("button", { name: "调整" }));
  expect(screen.getByRole("spinbutton", { name: "切分字符数" })).toHaveProperty("value", "800");
  fireEvent.click(screen.getByRole("button", { name: "确认设置" }));
  fireEvent.click(screen.getByRole("checkbox", { name: "选择release.md" }));
  expect(screen.getByRole("button", { name: "分片并建关键词索引" })).toBe(action);
  expect(action).toHaveProperty("disabled", false);
  expect(api.processKnowledgeDocuments).not.toHaveBeenCalled();
  expect(api.updateKnowledgeBase).not.toHaveBeenCalled();
});

it("shows new, reused and changed counts and retains the submission id after an unknown outcome", async () => {
  vi.mocked(api.listKnowledgeDocuments).mockResolvedValue([
    { ...doc, processing_reusable: true, processing_rules: previewResult.rules },
    {
      ...doc,
      id: "new",
      filename: "new.md",
      version: "",
      chunk_count: 0,
      keyword_ready: false,
      processing_state: "pending",
    },
    {
      ...doc,
      id: "changed",
      filename: "changed.md",
      processing_reusable: true,
      processing_rules: { ...previewResult.rules, chunk_size: 900 },
    },
  ]);
  vi.mocked(api.processKnowledgeDocuments)
    .mockRejectedValueOnce(new ApiError("网络中断，请重试。", 0, "client_connection_failed"))
    .mockResolvedValueOnce({
      id: "batch",
      status: "succeeded",
      rules: previewResult.rules,
      created_at: "",
      items: [
        { id: "item", document_id: "doc", filename: "release.md", status: "reused", error: null },
      ],
    });
  open("/knowledge/kb");
  fireEvent.click(await screen.findByRole("checkbox", { name: "全选当前结果" }));
  expect(screen.getByText("新建 1 份 · 复用 1 份 · 重新分片 1 份")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "分片并建关键词索引" }));
  await screen.findByRole("alert");
  fireEvent.click(screen.getByRole("button", { name: "分片并建关键词索引" }));
  await screen.findByText("已复用 1 份文档的分片和关键词索引，无需重新处理。");
  const calls = vi.mocked(api.processKnowledgeDocuments).mock.calls;
  expect(calls).toHaveLength(2);
  expect(calls[0][1]).toBe(calls[1][1]);
  expect(calls[0][2]).toEqual(["doc", "new", "changed"]);
});

it("keeps an unuploaded local file independent from old-document processing", async () => {
  vi.mocked(api.listKnowledgeDocuments).mockResolvedValue([doc]);
  vi.mocked(api.processKnowledgeDocuments).mockResolvedValue({
    id: "batch",
    status: "queued",
    rules: previewResult.rules,
    created_at: "",
    items: [],
  });
  open("/knowledge/kb");
  fireEvent.click(await screen.findByRole("button", { name: "上传文件" }));
  fireEvent.change(screen.getByLabelText("选择文件（可多选）"), {
    target: { files: [new File(["新资料"], "new.md")] },
  });
  fireEvent.click(screen.getByRole("checkbox", { name: "选择release.md" }));
  fireEvent.click(screen.getByRole("button", { name: "分片并建关键词索引" }));
  await waitFor(() =>
    expect(api.processKnowledgeDocuments).toHaveBeenCalledWith(
      "kb",
      expect.any(String),
      ["doc"],
      previewResult.rules,
    ),
  );
  expect(api.uploadKnowledgeDocument).not.toHaveBeenCalled();
});

it("builds all existing chunks even when some uploaded documents are pending, independently of selection", async () => {
  vi.mocked(api.getKnowledgeBase).mockResolvedValue({ ...kb, document_count: 2, chunk_count: 1 });
  vi.mocked(api.listKnowledgeDocuments).mockResolvedValue([
    doc,
    {
      ...doc,
      id: "pending",
      filename: "new.md",
      version: "",
      chunk_count: 0,
      keyword_ready: false,
      processing_state: "pending",
    },
  ]);
  vi.mocked(api.listEmbeddingConnections).mockResolvedValue([
    { id: "embedding", name: "向量模型", model_id: "BAAI/bge-m3" },
  ]);
  vi.mocked(api.buildKnowledgeVectors).mockResolvedValue(vectorJob);
  open("/knowledge/kb");
  fireEvent.click(await screen.findByRole("checkbox", { name: "全选当前结果" }));
  fireEvent.click(screen.getByRole("tab", { name: "检索设置" }));
  expect(
    await screen.findByText("本次处理 1 篇已分片文档；另有 1 篇待分片，暂不参与。"),
  ).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "建立向量索引（1篇）" }));
  await waitFor(() =>
    expect(api.buildKnowledgeVectors).toHaveBeenCalledWith("kb", "embedding", expect.any(String)),
  );
  expect(api.processKnowledgeDocuments).not.toHaveBeenCalled();
});

it("keeps an uncertain vector submission key and original model across navigation", async () => {
  vi.mocked(api.getKnowledgeBase).mockResolvedValue({ ...kb, chunk_count: 1 });
  vi.mocked(api.listKnowledgeDocuments).mockResolvedValue([doc]);
  vi.mocked(api.listEmbeddingConnections).mockResolvedValue([
    { id: "embedding", name: "向量模型", model_id: "BAAI/bge-m3" },
  ]);
  vi.mocked(api.buildKnowledgeVectors)
    .mockRejectedValueOnce(new ApiError("网络中断，请重试。", 0, "client_connection_failed"))
    .mockImplementationOnce(async () => {
      vi.mocked(api.listKnowledgeVectorJobs).mockResolvedValue([vectorJob]);
      return vectorJob;
    });
  open("/knowledge/kb?view=settings");
  const build = await screen.findByRole("button", { name: /建立向量索引/ });
  await waitFor(() => expect(build).toHaveProperty("disabled", false));
  fireEvent.click(build);
  await screen.findByText("提交结果尚未确认，再次提交会沿用原标识与模型，不会重复创建同一任务。");
  fireEvent.click(screen.getByRole("tab", { name: "文档" }));
  vi.mocked(api.listEmbeddingConnections).mockResolvedValue([]);
  fireEvent.click(screen.getByRole("tab", { name: "检索设置" }));
  fireEvent.click(await screen.findByRole("button", { name: "刷新连接与索引状态" }));
  await screen.findByText(/还没有可用的向量连接/);
  const confirm = await screen.findByRole("button", { name: "确认上次提交" });
  await waitFor(() => expect(confirm).toHaveProperty("disabled", false));
  fireEvent.click(confirm);
  await screen.findByText("向量任务：排队中");
  const calls = vi.mocked(api.buildKnowledgeVectors).mock.calls;
  expect(calls).toHaveLength(2);
  expect(calls[0]).toEqual(calls[1]);
});

it("cancels an active vector job and retries interrupted work with a new submission", async () => {
  vi.mocked(api.getKnowledgeBase).mockResolvedValue({
    ...kb,
    chunk_count: 1,
    vector_status: "ready",
    vector_connection_id: "embedding",
  });
  vi.mocked(api.listKnowledgeDocuments).mockResolvedValue([doc]);
  vi.mocked(api.listEmbeddingConnections).mockResolvedValue([
    { id: "embedding", name: "向量模型", model_id: "BAAI/bge-m3" },
  ]);
  vi.mocked(api.listKnowledgeVectorJobs).mockResolvedValue([{ ...vectorJob, status: "running" }]);
  vi.mocked(api.cancelKnowledgeVectorJob).mockImplementationOnce(async () => {
    const cancelled = { ...vectorJob, status: "cancelled" as const };
    vi.mocked(api.listKnowledgeVectorJobs).mockResolvedValue([cancelled]);
    return cancelled;
  });
  vi.mocked(api.buildKnowledgeVectors).mockImplementationOnce(async () => {
    const retried = { ...vectorJob, id: "second" };
    vi.mocked(api.listKnowledgeVectorJobs).mockResolvedValue([retried]);
    return retried;
  });
  open("/knowledge/kb?view=settings");
  fireEvent.click(await screen.findByRole("button", { name: "取消向量任务" }));
  await screen.findByText("向量任务：已取消");
  expect(api.cancelKnowledgeVectorJob).toHaveBeenCalledExactlyOnceWith("kb", "vector-job");
  expect(screen.getByRole("link", { name: "前往检索测试" })).toBeTruthy();
  vi.mocked(api.listKnowledgeVectorJobs).mockResolvedValue([
    { ...vectorJob, status: "interrupted", error: "服务重启，任务已中断。" },
  ]);
  fireEvent.click(screen.getByRole("button", { name: "刷新连接与索引状态" }));
  await screen.findByText("向量任务：已中断");
  expect(screen.getByText("服务重启，任务已中断。")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "重试向量构建（1篇）" }));
  await screen.findByText("向量任务：排队中");
  expect(api.buildKnowledgeVectors).toHaveBeenCalledExactlyOnceWith(
    "kb",
    "embedding",
    expect.any(String),
  );
});

it("polls vector progress and stops after the job finishes", async () => {
  vi.mocked(api.listKnowledgeVectorJobs).mockResolvedValue([{ ...vectorJob, status: "running" }]);
  open("/knowledge/kb?view=settings");
  await screen.findByText("向量任务：构建中");
  vi.mocked(api.listKnowledgeVectorJobs).mockResolvedValue([
    { ...vectorJob, status: "succeeded", completed_count: 1, reused_count: 1 },
  ]);
  await screen.findByText("向量任务：已完成", {}, { timeout: 2500 });
  expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("1");
  const calls = vi.mocked(api.listKnowledgeVectorJobs).mock.calls.length;
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 1600));
  });
  expect(api.listKnowledgeVectorJobs).toHaveBeenCalledTimes(calls);
});

it("keeps vector cancellation and build disabled for read-only visitors", async () => {
  readOnly = true;
  vi.mocked(api.getKnowledgeBase).mockResolvedValue({ ...kb, chunk_count: 1 });
  vi.mocked(api.listKnowledgeVectorJobs).mockResolvedValue([vectorJob]);
  vi.mocked(api.listKnowledgeDocuments).mockResolvedValue([doc]);
  vi.mocked(api.listEmbeddingConnections).mockResolvedValue([
    { id: "embedding", name: "向量模型", model_id: "model" },
  ]);
  open("/knowledge/kb?view=settings");
  expect(await screen.findByRole("button", { name: "取消向量任务" })).toHaveProperty(
    "disabled",
    true,
  );
  expect(screen.getByRole("button", { name: "向量任务进行中" })).toHaveProperty("disabled", true);
  expect(api.cancelKnowledgeVectorJob).not.toHaveBeenCalled();
  expect(api.buildKnowledgeVectors).not.toHaveBeenCalled();
});
