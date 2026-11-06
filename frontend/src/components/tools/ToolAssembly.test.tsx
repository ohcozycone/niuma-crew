// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { ApiError } from "@/lib/api/http";
import { ToolAssembly } from "./ToolAssembly";
import { listToolConnections, type ToolConnection, type ToolGrantInput } from "@/lib/api/tools";

vi.mock("@/state/auth/useIdentity", () => ({
  useIdentity: () => ({ actor: { user: { id: "owner" } } }),
}));
vi.mock("@/lib/api/tools", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/tools")>()),
  listToolConnections: vi.fn(),
}));

const connection: ToolConnection = {
  id: "search",
  name: "搜索引擎",
  kind: "mcp_http",
  service_id: "service",
  account_scope: "shared",
  created_by_user_id: "owner",
  tool_annotations: {},
  annotations_revision: 1,
  provider_key: null,
  auth_type: "bearer",
  public_config: { url: "https://mcp.tavily.com/mcp/" },
  enabled: true,
  has_credential: true,
  config_revision: 1,
  credential_revision: 1,
  catalog_revision: 1,
  approved_catalog: [],
  discovery_candidate: null,
};
const onChange = vi.fn();
const grant: ToolGrantInput = {
  connection_id: "search",
  tools: ["tavily_search"],
  expected_descriptors: { tavily_search: "hash" },
  account_mode: "shared",
  scope_policy: { mode: "provider", max_calls: 3 },
  enabled: true,
};

function show(value: ToolGrantInput[] = []) {
  return render(
    <MemoryRouter>
      <ToolAssembly value={value} onChange={onChange} onValidityChange={vi.fn()} />
    </MemoryRouter>,
  );
}

beforeEach(() => vi.resetAllMocks());
afterEach(cleanup);

it("refreshes approved tools after catalog management without replacing the employee draft", async () => {
  vi.mocked(listToolConnections)
    .mockResolvedValueOnce([connection])
    .mockResolvedValueOnce([
      {
        ...connection,
        approved_catalog: [
          { name: "tavily_search", description: "搜索网页", descriptor_hash: "hash" },
        ],
      },
    ]);
  show([grant]);
  await screen.findByText("有操作已移除或定义改变，请重新核对。");
  fireEvent.click(screen.getByRole("button", { name: "刷新连接列表" }));
  await screen.findByRole("button", { name: "配置" });
  fireEvent.click(screen.getByRole("button", { name: "配置" }));
  await screen.findByText("tavily_search");
  const manage = screen.getByRole("link", { name: "管理账号与目录（新标签页）" });
  expect(manage.getAttribute("target")).toBe("_blank");
  expect(screen.getAllByRole("checkbox")[0]).toHaveProperty("checked", true);
  expect(onChange).not.toHaveBeenCalled();
  expect(listToolConnections).toHaveBeenCalledTimes(2);
});

it("does not describe existing assignments as missing while connections are still loading", () => {
  vi.mocked(listToolConnections).mockImplementation(() => new Promise(() => {}));
  show([grant]);
  expect(screen.getByRole("status").textContent).toContain("正在读取");
  expect(screen.queryByRole("button", { name: "移除不可用装配" })).toBeNull();
});

it("keeps existing assignments when a refresh fails", async () => {
  vi.mocked(listToolConnections).mockRejectedValue(new Error("连接读取失败"));
  show([grant]);
  await screen.findByRole("heading", { name: "服务暂时无法完成处理" });
  expect(screen.queryByRole("button", { name: "移除不可用装配" })).toBeNull();
  expect(onChange).not.toHaveBeenCalled();
});

it("only applies panel changes after completion and discards cancelled selection", async () => {
  vi.mocked(listToolConnections).mockResolvedValue([
    {
      ...connection,
      approved_catalog: [
        { name: "tavily_search", description: "搜索网页", descriptor_hash: "hash" },
      ],
    },
  ]);
  show();
  await screen.findByText("尚未装配工具能力。可选择已经确认目录的 MCP 或内置工具。");
  fireEvent.click(screen.getByRole("button", { name: "添加工具能力" }));
  fireEvent.click(await screen.findByRole("button", { name: /搜索引擎/ }));
  fireEvent.click(screen.getByRole("checkbox"));
  expect(onChange).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "取消" }));
  expect(onChange).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "添加工具能力" }));
  fireEvent.click(await screen.findByRole("button", { name: /搜索引擎/ }));
  expect(screen.getByRole("checkbox")).toHaveProperty("checked", false);
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", { name: "完成，更新草稿" }));
  expect(onChange).toHaveBeenCalledTimes(1);
  expect(onChange.mock.calls[0][0][0]).toMatchObject({
    connection_id: "search",
    tools: ["tavily_search"],
    expected_descriptors: { tavily_search: "hash" },
  });
});

it("retains the loaded connection during refresh failure and hides unknown exception details", async () => {
  vi.mocked(listToolConnections)
    .mockResolvedValueOnce([connection])
    .mockRejectedValueOnce(new Error("private upstream token=hidden"));
  show([grant]);
  await screen.findByText("有操作已移除或定义改变，请重新核对。");
  fireEvent.click(screen.getByRole("button", { name: "刷新连接列表" }));
  await screen.findByText("暂时无法更新");
  expect(screen.getByText("搜索引擎")).toBeTruthy();
  expect(screen.queryByText(/private upstream/)).toBeNull();
  expect(screen.getByRole("button", { name: "配置" }).hasAttribute("disabled")).toBe(false);
  expect(onChange).not.toHaveBeenCalled();
});

it("clears restricted connection metadata when refresh is explicitly forbidden", async () => {
  vi.mocked(listToolConnections)
    .mockResolvedValueOnce([connection])
    .mockRejectedValueOnce(new ApiError("访问权限已撤回", 403, "tool_access_revoked"));
  show([grant]);
  await screen.findByText("有操作已移除或定义改变，请重新核对。");
  fireEvent.click(screen.getByRole("button", { name: "刷新连接列表" }));
  await screen.findByRole("heading", { name: "当前配置需要检查" });
  expect(screen.queryByText("搜索引擎")).toBeNull();
  expect(screen.getByRole("button", { name: "配置" }).hasAttribute("disabled")).toBe(true);
  expect(onChange).not.toHaveBeenCalled();
});

it("keeps malformed local scope input visible without losing its validation message", async () => {
  vi.mocked(listToolConnections).mockResolvedValue([
    {
      ...connection,
      approved_catalog: [
        { name: "tavily_search", description: "搜索网页", descriptor_hash: "hash" },
      ],
    },
  ]);
  show([grant]);
  fireEvent.click(await screen.findByRole("button", { name: "配置" }));
  fireEvent.click(screen.getByText("高级范围约束"));
  const input = screen.getByRole("textbox", { name: "搜索引擎范围约束" });
  fireEvent.change(input, { target: { value: "{invalid" } });
  fireEvent.click(screen.getByRole("button", { name: "完成，更新草稿" }));
  await screen.findByText("范围约束必须为 JSON 对象。");
  expect(input).toHaveProperty("value", "{invalid");
  expect(onChange).not.toHaveBeenCalled();
});

it("preserves advanced scope fields when changing limits and rejects invalid limits locally", async () => {
  vi.mocked(listToolConnections).mockResolvedValue([connection]);
  show([grant]);
  fireEvent.click(await screen.findByRole("button", { name: "配置" }));
  fireEvent.click(screen.getByText("高级范围约束"));
  const json = screen.getByRole("textbox", { name: "搜索引擎范围约束" });
  fireEvent.change(json, {
    target: { value: '{"max_calls":5,"allowed_domains":["example.com"]}' },
  });
  fireEvent.change(screen.getByRole("spinbutton", { name: "每项工具调用上限" }), {
    target: { value: "8" },
  });
  expect(JSON.parse((json as HTMLTextAreaElement).value)).toEqual({
    max_calls: 8,
    allowed_domains: ["example.com"],
  });
  fireEvent.change(screen.getByRole("spinbutton", { name: "每项工具调用上限" }), {
    target: { value: "0" },
  });
  fireEvent.click(screen.getByRole("button", { name: "完成，更新草稿" }));
  expect(await screen.findByText("每项工具调用上限需为 1—32 的整数。")).toBeTruthy();
  expect(onChange).not.toHaveBeenCalled();
});
