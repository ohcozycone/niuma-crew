// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import * as api from "@/lib/api/modelConnections";
import { ApiError } from "@/lib/api/http";
import { EditingProvider } from "@/state/editing/useEditing";
import { ModelConnections } from "@/components/configuration/ModelConnections";
import { BrainWorkspace } from "./BrainWorkspace";

vi.mock("@/lib/api/modelConnections", () => ({
  loadModelConnections: vi.fn(),
  loadModelPresets: vi.fn(),
  saveModelConnection: vi.fn(),
  testModelConnection: vi.fn(),
  deleteModelConnection: vi.fn(),
}));
beforeEach(() => vi.resetAllMocks());
afterEach(cleanup);

it("prefills the SiliconFlow model and saves only the user's new key", async () => {
  const preset = {
    id: "siliconflow-embedding",
    name: "硅基流动 · BGE-M3",
    provider: "siliconflow",
    protocol: "openai-embeddings",
    capability: "embedding" as const,
    base_url: "https://api.siliconflow.cn/v1",
    default_model_id: "BAAI/bge-m3",
    description: "知识库向量",
  };
  vi.mocked(api.loadModelPresets).mockResolvedValue([
    {
      ...preset,
      id: "kimi-code",
      name: "Kimi Code",
      capability: "chat",
      default_model_id: "kimi-for-coding",
    },
    preset,
  ]);
  vi.mocked(api.loadModelConnections).mockResolvedValue([]);
  const saved = {
    id: "embedding",
    name: preset.name,
    model_id: preset.default_model_id,
    preset_id: preset.id,
    provider: preset.provider,
    protocol: preset.protocol,
    base_url: preset.base_url,
    capability: "embedding" as const,
    has_api_key: true,
    enabled: true,
    config_revision: 1,
    credential_revision: 1,
    agents: [],
    created_at: "",
    updated_at: "",
  };
  vi.mocked(api.saveModelConnection).mockResolvedValue(saved);
  vi.mocked(api.testModelConnection).mockResolvedValue({ ok: true, message: "真实向量调用通过" });
  render(
    <MemoryRouter>
      <EditingProvider>
        <ModelConnections capability="embedding" embedded />
      </EditingProvider>
    </MemoryRouter>,
  );
  await waitFor(() =>
    expect(
      screen.getAllByRole("button", { name: "添加向量模型" })[0].hasAttribute("disabled"),
    ).toBe(false),
  );
  fireEvent.click(screen.getAllByRole("button", { name: "添加向量模型" })[0]);
  await waitFor(() =>
    expect(screen.getByRole("textbox", { name: "向量模型名称" })).toHaveProperty(
      "value",
      preset.name,
    ),
  );
  expect(screen.getByRole("textbox", { name: "Model ID" })).toHaveProperty("readOnly", true);
  for (const [control, help] of [
    [screen.getByRole("combobox", { name: "模型预设" }), preset.description],
    [screen.getByLabelText("API Key"), "Key 在服务端加密保存，不会返回到页面。"],
    [screen.getByRole("textbox", { name: "Model ID" }), "已固定为 BAAI/bge-m3"],
  ] as const) {
    const description = control.getAttribute("aria-describedby");
    expect(description).toBeTruthy();
    expect(document.getElementById(description!)?.textContent).toContain(help);
  }
  fireEvent.change(screen.getByLabelText("API Key"), { target: { value: "test-only-key" } });
  fireEvent.click(screen.getByRole("button", { name: "保存向量模型" }));
  await screen.findByRole("heading", { name: preset.name });
  expect(api.saveModelConnection).toHaveBeenCalledWith(
    {
      name: preset.name,
      model_id: "BAAI/bge-m3",
      preset_id: preset.id,
      api_key: "test-only-key",
      enabled: true,
    },
    undefined,
  );
  expect(screen.queryByDisplayValue("test-only-key")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "测试连接" }));
  await screen.findByText("真实向量调用通过");
});

const readPreset = {
  id: "kimi-code",
  name: "Kimi Code",
  provider: "moonshot",
  protocol: "openai-chat",
  capability: "chat" as const,
  base_url: "https://example.com/v1",
  default_model_id: "model",
  description: "员工对话",
};
const readConnection = {
  id: "brain",
  name: "研发大脑",
  preset_id: readPreset.id,
  provider: readPreset.provider,
  protocol: readPreset.protocol,
  capability: "chat" as const,
  base_url: readPreset.base_url,
  model_id: "model",
  enabled: true,
  has_api_key: true,
  config_revision: 1,
  credential_revision: 1,
  agents: [],
  created_at: "",
  updated_at: "",
};
function showWorkspace() {
  vi.mocked(api.loadModelPresets).mockResolvedValue([readPreset]);
  render(
    <MemoryRouter>
      <EditingProvider>
        <BrainWorkspace />
      </EditingProvider>
    </MemoryRouter>,
  );
}

it("retains loaded connections and search when a refresh fails", async () => {
  vi.mocked(api.loadModelConnections)
    .mockResolvedValueOnce([readConnection])
    .mockRejectedValueOnce(
      new ApiError("当前无法读取目录", 503, "backend_unavailable", { requestId: "brain-refresh" }),
    );
  showWorkspace();
  await screen.findByRole("heading", { name: "研发大脑" });
  fireEvent.change(screen.getByRole("textbox", { name: "搜索大脑" }), {
    target: { value: "研发" },
  });
  fireEvent.click(screen.getByRole("button", { name: "大脑更多操作" }));
  fireEvent.click(await screen.findByRole("menuitem", { name: "重新加载列表" }));
  await screen.findByText("暂时无法更新");
  expect(screen.getByRole("heading", { name: "研发大脑" })).toBeTruthy();
  expect(screen.getByRole("textbox", { name: "搜索大脑" })).toHaveProperty("value", "研发");
  expect(screen.getByText("问题编号：brain-refresh")).toBeTruthy();
});

it("shows upstream credential rejection only on the checked connection", async () => {
  vi.mocked(api.loadModelConnections).mockResolvedValue([readConnection]);
  vi.mocked(api.testModelConnection).mockRejectedValue(
    new ApiError("模型密钥不可用", 401, "upstream_auth_failed", { requestId: "brain-check" }),
  );
  showWorkspace();
  fireEvent.click(await screen.findByRole("button", { name: "测试连接" }));
  await screen.findByText("模型密钥不可用");
  expect(screen.getByText("问题编号：brain-check")).toBeTruthy();
  expect(screen.getByRole("heading", { name: "研发大脑" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "编辑" })).toBeTruthy();
});

it("retains the new key after a rejected save and hides unexpected exception values", async () => {
  vi.mocked(api.loadModelConnections).mockResolvedValue([readConnection]);
  vi.mocked(api.saveModelConnection).mockRejectedValue(
    new Error("private credential from upstream"),
  );
  showWorkspace();
  fireEvent.click(await screen.findByRole("button", { name: "编辑" }));
  fireEvent.change(screen.getByLabelText("API Key （留空保持原值）"), {
    target: { value: "retained-fixture-key" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存大脑" }));
  await screen.findByText("还无法确认是否提交成功");
  expect(screen.queryByText(/private credential/)).toBeNull();
  expect(screen.getByLabelText("API Key （留空保持原值）")).toHaveProperty(
    "value",
    "retained-fixture-key",
  );
  expect(screen.getByRole("dialog")).toBeTruthy();
});

it("keeps embedding connections and presets out of employee brains", async () => {
  vi.mocked(api.loadModelConnections).mockResolvedValue([
    readConnection,
    { ...readConnection, id: "embedding", name: "知识库专用", capability: "embedding" },
  ]);
  showWorkspace();
  await screen.findByRole("heading", { name: "研发大脑" });
  expect(screen.queryByRole("heading", { name: "知识库专用" })).toBeNull();
});

it.each([
  ["zhipu", "智谱 GLM", "https://open.bigmodel.cn/api/paas/v4", "glm-5.3"],
  ["deepseek", "DeepSeek", "https://api.deepseek.com", "deepseek-flash"],
])(
  "selects and saves the %s preset with its own defaults and key prompt",
  async (id, name, url, model) => {
    const preset = {
      ...readPreset,
      id,
      name,
      provider: id,
      base_url: url,
      default_model_id: model,
    };
    vi.mocked(api.loadModelPresets).mockResolvedValue([readPreset, preset]);
    vi.mocked(api.loadModelConnections).mockResolvedValue([]);
    vi.mocked(api.saveModelConnection).mockResolvedValue({
      ...readConnection,
      id,
      name,
      preset_id: id,
      provider: id,
      base_url: url,
      model_id: model,
    });
    render(
      <MemoryRouter>
        <EditingProvider>
          <BrainWorkspace />
        </EditingProvider>
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(screen.getAllByRole("button", { name: "新建大脑" })[0].hasAttribute("disabled")).toBe(
        false,
      ),
    );
    fireEvent.click(screen.getAllByRole("button", { name: "新建大脑" })[0]);
    fireEvent.click(screen.getByRole("combobox", { name: "模型预设" }));
    fireEvent.keyDown(await screen.findByRole("option", { name }), { key: "Enter" });
    expect(screen.getByRole("textbox", { name: "Model ID" })).toHaveProperty("value", model);
    expect(screen.getByText(`Base URL：${url}`)).toBeTruthy();
    expect(screen.getByPlaceholderText(`输入 ${name} API Key`)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("API Key"), { target: { value: "test-only-key" } });
    fireEvent.click(screen.getByRole("button", { name: "保存大脑" }));
    await screen.findByRole("heading", { name });
    expect(api.saveModelConnection).toHaveBeenCalledWith(
      {
        name,
        model_id: model,
        api_key: "test-only-key",
        preset_id: id,
        enabled: true,
      },
      undefined,
    );
    expect(screen.queryByDisplayValue("test-only-key")).toBeNull();
  },
);
