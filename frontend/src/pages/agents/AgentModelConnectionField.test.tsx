import { ApiError } from "@/lib/api/http";
// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { loadModelConnections, type ModelConnection } from "@/lib/api/modelConnections";
import { AgentModelConnectionField } from "./AgentModelConnectionField";

vi.mock("@/lib/api/modelConnections", () => ({
  loadModelConnections: vi.fn(),
}));

const connection: ModelConnection = {
  id: "brain",
  name: "共享对话模型",
  model_id: "chat-model",
  enabled: true,
  capability: "chat",
  config_revision: 1,
  credential_revision: 1,
  preset_id: "preset",
  provider: "provider",
  protocol: "openai",
  base_url: "",
  has_api_key: true,
  agents: [{ id: "employee", name: "员工" }],
  created_at: "",
  updated_at: "",
};

beforeEach(() => {
  vi.mocked(loadModelConnections).mockReset();
});
afterEach(cleanup);

it("describes loading and the selected connection without clearing the employee draft", async () => {
  let finish!: (items: ModelConnection[]) => void;
  vi.mocked(loadModelConnections).mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const onChange = vi.fn();
  render(<AgentModelConnectionField value="brain" onChange={onChange} />);
  const select = screen.getByRole("combobox", { name: "装配大脑" });
  expect(select.hasAttribute("disabled")).toBe(true);
  expect(select.textContent).toContain("正在加载大脑");
  expect(screen.queryByText(/暂无可用的对话连接/)).toBeNull();
  await act(async () => finish([connection]));
  expect(select.hasAttribute("disabled")).toBe(false);
  expect(select.textContent).toContain("共享对话模型");
  expect(screen.getByRole("status").textContent).toContain("chat-model · 凭证已配置");
  expect(select.getAttribute("aria-describedby")).toBe(
    "agent-brain-description agent-brain-feedback",
  );
  expect(onChange).not.toHaveBeenCalled();
});

it("keeps the selection through a failed refresh and allows a successful retry", async () => {
  vi.mocked(loadModelConnections)
    .mockResolvedValueOnce([connection])
    .mockRejectedValueOnce(new ApiError("连接读取失败", 503, "database_busy"))
    .mockResolvedValueOnce([{ ...connection, name: "更新后的模型连接" }]);
  const onChange = vi.fn();
  render(<AgentModelConnectionField value="brain" onChange={onChange} />);
  await waitFor(() => expect(screen.getByRole("combobox").textContent).toContain("共享对话模型"));
  fireEvent.click(screen.getByRole("button", { name: "刷新大脑列表" }));
  await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("连接读取失败"));
  expect(screen.getByRole("combobox").textContent).toContain("共享对话模型");
  fireEvent.click(screen.getByRole("button", { name: "刷新大脑列表" }));
  await waitFor(() =>
    expect(screen.getByRole("combobox").textContent).toContain("更新后的模型连接"),
  );
  expect(screen.getByRole("status").textContent).toContain("列表已更新");
  expect(onChange).not.toHaveBeenCalled();
});

it.each([
  [{ enabled: false }, "已停用", "大脑已停用"],
  [{ capability: "embedding" as const }, "不支持对话", "此连接仅用于向量"],
  [{ has_api_key: false }, "待配置凭证", "尚未配置凭证"],
])("makes an unusable saved connection explicit: %s", async (overrides, status, feedback) => {
  vi.mocked(loadModelConnections).mockResolvedValue([{ ...connection, ...overrides }]);
  render(<AgentModelConnectionField value="brain" onChange={vi.fn()} />);
  await waitFor(() => expect(screen.getByRole("status").textContent).toContain(feedback));
  expect(screen.getByText(status, { exact: true })).toBeDefined();
});

it("distinguishes an empty directory from a saved connection that could not be found", async () => {
  vi.mocked(loadModelConnections).mockResolvedValue([]);
  const onChange = vi.fn();
  const view = render(<AgentModelConnectionField value={null} onChange={onChange} />);
  await waitFor(() =>
    expect(screen.getByRole("status").textContent).toContain("暂无可用的对话连接"),
  );
  view.rerender(<AgentModelConnectionField value="unavailable" onChange={onChange} />);
  expect(screen.getByText("待确认", { exact: true })).toBeDefined();
  expect(screen.getByRole("status").textContent).toContain("已有选择会保留");
  expect(screen.getByRole("combobox").textContent).toContain("当前大脑（待确认）");
  expect(onChange).not.toHaveBeenCalled();
});
