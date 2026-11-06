// @vitest-environment jsdom
import { WorkspaceDataProvider } from "@/state/workspace/WorkspaceDataProvider";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { ToolsPage } from "./ToolsPage";
import * as api from "@/lib/api/tools";
import { ApiError } from "@/lib/api/http";

vi.mock("@/state/auth/useIdentity", () => ({
  useIdentity: () => ({
    actor: { kind: "user", user: { id: "owner", username: "owner" } },
    permissions: ["tools:read", "tools:update"],
  }),
}));
vi.mock("@/lib/api/tools", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/tools")>()),
  listMcpServices: vi.fn(),
  toolCapabilities: vi.fn(),
  listToolConnections: vi.fn(),
  createToolConnection: vi.fn(),
  createMcpService: vi.fn(),
  patchMcpService: vi.fn(),
  deleteMcpService: vi.fn(),
  deleteToolConnection: vi.fn(),
  previewMcpConfig: vi.fn(),
  patchToolConnection: vi.fn(),
  discoverTools: vi.fn(),
  approveTools: vi.fn(),
}));
const connection: api.ToolConnection = {
  id: "tool",
  name: "搜索服务",
  kind: "mcp_http",
  service_id: "service",
  account_scope: "personal",
  created_by_user_id: "owner",
  tool_annotations: {},
  annotations_revision: 1,
  provider_key: null,
  auth_type: "bearer",
  public_config: { url: "https://mcp.tavily.com/mcp" },
  enabled: true,
  has_credential: true,
  config_revision: 1,
  credential_revision: 1,
  catalog_revision: 1,
  approved_catalog: [],
  discovery_candidate: null,
};
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.listToolConnections).mockResolvedValue([connection]);
  vi.mocked(api.discoverTools).mockResolvedValue(connection);
  vi.mocked(api.toolCapabilities).mockResolvedValue({
    stdio_enabled: false,
    stdio_registration_allowed: false,
    max_stdio_processes: 0,
  });
  vi.mocked(api.listMcpServices).mockResolvedValue([
    {
      id: "service",
      name: "搜索服务",
      description: "搜索",
      url: "https://mcp.tavily.com/mcp",
      transport: "http",
      command: null,
      args: [],
      env_keys: [],
      owner_user_id: "owner",
      revision: 1,
      enabled: true,
    },
  ]);
});
afterEach(cleanup);

it("does not disable a shared service or connection until its confirmation is accepted", async () => {
  vi.mocked(api.patchMcpService).mockImplementation(async (service, patch) => ({
    ...service,
    ...patch,
  }));
  vi.mocked(api.patchToolConnection).mockImplementation(async (value) => ({
    ...value,
    enabled: false,
  }));
  render(
    <MemoryRouter initialEntries={["/tools?service=service"]}>
      <WorkspaceDataProvider>
        <ToolsPage />
      </WorkspaceDataProvider>
    </MemoryRouter>,
  );
  fireEvent.click(await screen.findByRole("button", { name: "停用服务" }));
  expect(api.patchMcpService).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "取消" }));
  expect(api.patchMcpService).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "停用服务" }));
  fireEvent.click(screen.getByRole("button", { name: "确认停用服务" }));
  await screen.findByRole("button", { name: "启用服务" });
  expect(api.patchMcpService).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: "停用连接" }));
  expect(api.patchToolConnection).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "取消" }));
  expect(api.patchToolConnection).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "停用连接" }));
  fireEvent.click(screen.getByRole("button", { name: "确认停用连接" }));
  await screen.findByRole("button", { name: "启用连接" });
  expect(api.patchToolConnection).toHaveBeenCalledTimes(1);
});

it("keeps the approved catalog when a removal is cancelled and sends approval only after confirmation", async () => {
  const old = { name: "retired_search", description: "旧搜索", descriptor_hash: "old" };
  vi.mocked(api.listToolConnections).mockResolvedValue([
    { ...connection, approved_catalog: [old], discovery_candidate: { hash: "new", tools: [] } },
  ]);
  vi.mocked(api.approveTools).mockResolvedValue({ ...connection, approved_catalog: [] });
  render(
    <MemoryRouter initialEntries={["/tools?service=service"]}>
      <WorkspaceDataProvider>
        <ToolsPage />
      </WorkspaceDataProvider>
    </MemoryRouter>,
  );
  fireEvent.click(await screen.findByRole("button", { name: "应用工具更新" }));
  expect(api.approveTools).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "取消" }));
  expect(api.approveTools).not.toHaveBeenCalled();
  expect(screen.getByText("retired_search")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "应用工具更新" }));
  fireEvent.click(screen.getByRole("button", { name: "确认应用更新" }));
  await waitFor(() => expect(api.approveTools).toHaveBeenCalledTimes(1));
});

it("keeps discovery and catalog approval as distinct operations", async () => {
  vi.mocked(api.discoverTools).mockResolvedValue({
    ...connection,
    discovery_candidate: {
      hash: "candidate",
      tools: [{ name: "tavily_search", description: "互联网搜索", descriptor_hash: "tool-hash" }],
    },
  });
  vi.mocked(api.approveTools).mockResolvedValue({
    ...connection,
    approved_catalog: [
      { name: "tavily_search", description: "互联网搜索", descriptor_hash: "tool-hash" },
    ],
  });
  render(
    <MemoryRouter initialEntries={["/tools?service=service"]}>
      <WorkspaceDataProvider>
        <ToolsPage />
      </WorkspaceDataProvider>
    </MemoryRouter>,
  );
  fireEvent.click(await screen.findByRole("button", { name: "读取工具列表" }));
  await screen.findByText("tavily_search");
  expect(api.approveTools).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "确认工具列表" }));
  await waitFor(() => expect(api.approveTools).toHaveBeenCalledTimes(1));
});

it("does not offer a destructive empty grant save while connections fail to load", async () => {
  vi.mocked(api.listToolConnections).mockRejectedValue(
    new ApiError("连接读取失败", 503, "backend_unavailable"),
  );
  render(
    <MemoryRouter initialEntries={["/tools?agent=employee"]}>
      <WorkspaceDataProvider>
        <ToolsPage />
      </WorkspaceDataProvider>
    </MemoryRouter>,
  );
  await screen.findByRole("heading", { name: "暂时无法连接服务" });
  expect(screen.queryByRole("button", { name: "保存员工工具许可" })).toBeNull();
});

it("does not present a new-service form while an existing service is loading", async () => {
  vi.mocked(api.listMcpServices).mockImplementation(() => new Promise(() => {}));
  render(
    <MemoryRouter initialEntries={["/tools?service=service"]}>
      <WorkspaceDataProvider>
        <ToolsPage />
      </WorkspaceDataProvider>
    </MemoryRouter>,
  );
  await screen.findByRole("status");
  expect(screen.queryByRole("button", { name: "保存服务并配置账号" })).toBeNull();
});

it("normalizes an imported HTTP config into one editable form without executing or persisting its token", async () => {
  vi.mocked(api.listMcpServices).mockResolvedValue([]);
  vi.mocked(api.previewMcpConfig).mockResolvedValue({
    entries: [
      {
        name: "research",
        transport: "http",
        url: "https://example.com/mcp",
        command: null,
        args: [],
        env_keys: [],
        auth_type: "bearer",
        header_name: null,
        has_credential: true,
      },
    ],
  });
  render(
    <MemoryRouter initialEntries={["/tools"]}>
      <WorkspaceDataProvider>
        <ToolsPage />
      </WorkspaceDataProvider>
    </MemoryRouter>,
  );
  await screen.findByRole("button", { name: "快捷导入" });
  fireEvent.click(screen.getByRole("button", { name: "快捷导入" }));
  fireEvent.change(await screen.findByLabelText("MCP 配置 JSON"), {
    target: {
      value: JSON.stringify({
        mcpServers: {
          research: {
            url: "https://example.com/mcp",
            headers: { Authorization: "Bearer secret-test-token" },
          },
        },
      }),
    },
  });
  fireEvent.click(screen.getByRole("button", { name: "解析并填入" }));
  await waitFor(() => expect(screen.queryByLabelText("MCP 配置 JSON")).toBeNull());
  expect(screen.queryByLabelText("MCP 配置 JSON")).toBeNull();
  expect(screen.getByLabelText(/MCP 服务地址/).getAttribute("value")).toBe(
    "https://example.com/mcp",
  );
  expect(api.createMcpService).not.toHaveBeenCalled();
  expect(api.createToolConnection).not.toHaveBeenCalled();
  expect(sessionStorage.length).toBe(0);
});

it("keeps imported stdio environment templates empty until actual account credentials are entered", async () => {
  const keys = ["EMPTY", "BRACED", "MUSTACHE", "REAL"];
  const definition: api.McpService = {
    id: "stdio-service",
    name: "local",
    description: "",
    transport: "stdio",
    url: null,
    command: "npx",
    args: ["example@1.0.0"],
    env_keys: keys,
    owner_user_id: "owner",
    revision: 1,
    enabled: true,
  };
  vi.mocked(api.listMcpServices).mockResolvedValue([]);
  vi.mocked(api.listToolConnections).mockResolvedValue([]);
  vi.mocked(api.toolCapabilities).mockResolvedValue({
    stdio_enabled: true,
    stdio_registration_allowed: true,
    max_stdio_processes: 2,
  });
  vi.mocked(api.previewMcpConfig).mockResolvedValue({
    entries: [
      {
        name: "local",
        transport: "stdio",
        url: null,
        command: "npx",
        args: definition.args,
        env_keys: keys,
        auth_type: "env",
        header_name: null,
        has_credential: false,
      },
    ],
  });
  vi.mocked(api.createMcpService).mockResolvedValue(definition);
  vi.mocked(api.createToolConnection).mockResolvedValue({
    ...connection,
    id: "stdio-account",
    service_id: definition.id,
    kind: "mcp_stdio",
    auth_type: "env",
  });
  render(
    <MemoryRouter initialEntries={["/tools"]}>
      <WorkspaceDataProvider>
        <ToolsPage />
      </WorkspaceDataProvider>
    </MemoryRouter>,
  );
  fireEvent.click(await screen.findByRole("button", { name: "快捷导入" }));
  fireEvent.change(await screen.findByLabelText("MCP 配置 JSON"), {
    target: {
      value: JSON.stringify({
        mcpServers: {
          local: {
            command: "npx",
            args: definition.args,
            env: {
              EMPTY: "",
              BRACED: "${API_KEY}",
              MUSTACHE: "{{API_KEY}}",
              REAL: "real-test-token",
            },
          },
        },
      }),
    },
  });
  fireEvent.click(screen.getByRole("button", { name: "解析并填入" }));
  await waitFor(() => expect(screen.queryByLabelText("MCP 配置 JSON")).toBeNull());
  await screen.findByLabelText("EMPTY");
  for (const key of ["EMPTY", "BRACED", "MUSTACHE"])
    expect((screen.getByLabelText(key) as HTMLInputElement).value).toBe("");
  expect((screen.getByLabelText("REAL") as HTMLInputElement).value).toBe("real-test-token");
  expect(screen.getByRole("button", { name: "保存并测试" }).hasAttribute("disabled")).toBe(true);
  expect(api.createToolConnection).not.toHaveBeenCalled();
  for (const key of ["EMPTY", "BRACED", "MUSTACHE"])
    fireEvent.change(screen.getByLabelText(key), { target: { value: `actual-${key}` } });
  fireEvent.click(screen.getByRole("button", { name: "保存并测试" }));
  await waitFor(() => expect(api.createToolConnection).toHaveBeenCalledTimes(1));
  expect(api.createToolConnection).toHaveBeenCalledWith(
    expect.objectContaining({
      environment: {
        EMPTY: "actual-EMPTY",
        BRACED: "actual-BRACED",
        MUSTACHE: "actual-MUSTACHE",
        REAL: "real-test-token",
      },
    }),
  );
});

it("offers API Key configuration on an existing anonymous stdio connection", async () => {
  vi.mocked(api.listMcpServices).mockResolvedValue([
    {
      id: "service",
      name: "Context7",
      description: "文档",
      transport: "stdio",
      url: null,
      command: "npx",
      args: ["-y", "@upstash/context7-mcp@4.4.4"],
      env_keys: ["CONTEXT7_API_KEY"],
      owner_user_id: "owner",
      revision: 1,
      enabled: true,
    },
  ]);
  const anonymous: api.ToolConnection = {
    ...connection,
    kind: "mcp_stdio",
    auth_type: "none",
    has_credential: false,
    public_config: { command: "npx", args: ["-y", "@upstash/context7-mcp@4.4.4"], env_keys: [] },
  };
  vi.mocked(api.listToolConnections).mockResolvedValue([anonymous]);
  vi.mocked(api.patchToolConnection).mockResolvedValue({
    ...anonymous,
    auth_type: "env",
    has_credential: true,
    credential_revision: 2,
  });
  render(
    <MemoryRouter initialEntries={["/tools?service=service"]}>
      <WorkspaceDataProvider>
        <ToolsPage />
      </WorkspaceDataProvider>
    </MemoryRouter>,
  );
  fireEvent.click(await screen.findByRole("button", { name: "配置密钥" }));
  const key = within(screen.getByRole("form", { name: "修改访问设置" })).getByLabelText(
    "CONTEXT7_API_KEY",
  );
  expect(key.getAttribute("type")).toBe("password");
  const save = screen.getAllByRole("button", { name: "保存访问设置" }).at(-1)!;
  expect(save.hasAttribute("disabled")).toBe(true);
  fireEvent.change(key, { target: { value: "ctx7sk-personal-fixture" } });
  fireEvent.click(save);
  await waitFor(() =>
    expect(api.patchToolConnection).toHaveBeenCalledWith(
      anonymous,
      expect.objectContaining({
        auth_type: "env",
        environment: { CONTEXT7_API_KEY: "ctx7sk-personal-fixture" },
      }),
    ),
  );
  await waitFor(() => expect(screen.queryByDisplayValue("ctx7sk-personal-fixture")).toBeNull());
  expect(api.createMcpService).not.toHaveBeenCalled();
});

it("explains where to declare a credential field missing from an existing stdio service", async () => {
  vi.mocked(api.listMcpServices).mockResolvedValue([
    {
      id: "service",
      name: "Context7",
      description: "文档",
      transport: "stdio",
      url: null,
      command: "npx",
      args: [],
      env_keys: [],
      owner_user_id: "owner",
      revision: 1,
      enabled: true,
    },
  ]);
  vi.mocked(api.listToolConnections).mockResolvedValue([
    {
      ...connection,
      kind: "mcp_stdio",
      auth_type: "none",
      has_credential: false,
      public_config: { command: "npx", args: [], env_keys: [] },
    },
  ]);
  render(
    <MemoryRouter initialEntries={["/tools?service=service"]}>
      <WorkspaceDataProvider>
        <ToolsPage />
      </WorkspaceDataProvider>
    </MemoryRouter>,
  );
  fireEvent.click(await screen.findByRole("button", { name: "配置密钥" }));
  fireEvent.click(screen.getByRole("button", { name: "设置凭据字段" }));
  expect(screen.getByLabelText(/允许配置的凭据字段（环境变量名，每行一个）/)).toBeTruthy();
});

it("shows unchanged tool discovery without another approval action", async () => {
  const current = {
    ...connection,
    approved_catalog: [{ name: "search", description: "搜索", descriptor_hash: "same" }],
  };
  vi.mocked(api.listToolConnections).mockResolvedValue([current]);
  vi.mocked(api.discoverTools).mockResolvedValue(current);
  render(
    <MemoryRouter initialEntries={["/tools?service=service"]}>
      <WorkspaceDataProvider>
        <ToolsPage />
      </WorkspaceDataProvider>
    </MemoryRouter>,
  );
  fireEvent.click(await screen.findByRole("button", { name: "检查工具更新" }));
  expect(await screen.findByText("工具列表已是最新，没有变化。")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "应用工具更新" })).toBeNull();
});

it("requires explicit delete confirmation and explains employee references without leaving the page", async () => {
  vi.mocked(api.deleteMcpService).mockRejectedValue(
    new ApiError("已有员工装配此服务，请先移除。", 409, "mcp_service_in_use"),
  );
  render(
    <MemoryRouter initialEntries={["/tools?service=service"]}>
      <WorkspaceDataProvider>
        <ToolsPage />
      </WorkspaceDataProvider>
    </MemoryRouter>,
  );
  fireEvent.click(await screen.findByRole("button", { name: "删除 MCP" }));
  expect(api.deleteMcpService).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "确认删除" }));
  expect(await screen.findByText("已有员工装配此服务，请先移除。")).toBeTruthy();
  expect(screen.getByRole("dialog")).toBeTruthy();
});

it("uses declared custom header metadata when adding a key to an anonymous connection", async () => {
  const services = await api.listMcpServices();
  vi.mocked(api.listMcpServices).mockResolvedValue([
    {
      ...services[0],
      input_fields: [
        { name: "X-Docs-Key", description: "Account key", is_required: false, is_secret: true },
      ],
    },
  ]);
  vi.mocked(api.listToolConnections).mockResolvedValue([
    { ...connection, auth_type: "none", has_credential: false },
  ]);
  render(
    <MemoryRouter initialEntries={["/tools?service=service"]}>
      <WorkspaceDataProvider>
        <ToolsPage />
      </WorkspaceDataProvider>
    </MemoryRouter>,
  );
  fireEvent.click(await screen.findByRole("button", { name: "配置密钥" }));
  const form = screen.getByRole("form", { name: "修改访问设置" });
  expect(within(form).getByRole("combobox", { name: "认证方式" }).textContent).toContain(
    "自定义认证头",
  );
  expect((within(form).getByLabelText("认证头名称") as HTMLInputElement).value).toBe("X-Docs-Key");
});

it("keeps a successfully saved account and clears its key when discovery subsequently fails", async () => {
  vi.mocked(api.listMcpServices).mockResolvedValue([]);
  vi.mocked(api.listToolConnections).mockResolvedValue([]);
  vi.mocked(api.createMcpService).mockResolvedValue({
    id: "service",
    name: "新服务",
    description: "",
    transport: "http",
    url: "https://example.com/mcp",
    command: null,
    args: [],
    env_keys: [],
    owner_user_id: "owner",
    revision: 1,
    enabled: true,
  });
  vi.mocked(api.createToolConnection).mockResolvedValue(connection);
  vi.mocked(api.discoverTools).mockRejectedValue(
    new ApiError("上游认证未通过，请检查凭据。", 422, "tool_auth_required", {
      requestId: "discovery-failed",
    }),
  );
  render(
    <MemoryRouter initialEntries={["/tools"]}>
      <WorkspaceDataProvider>
        <ToolsPage />
      </WorkspaceDataProvider>
    </MemoryRouter>,
  );
  await screen.findByRole("button", { name: "快捷导入" });
  fireEvent.change(screen.getByLabelText("服务名称"), { target: { value: "新服务" } });
  fireEvent.change(screen.getByLabelText("MCP 服务地址"), {
    target: { value: "https://example.com/mcp" },
  });
  fireEvent.click(screen.getByRole("combobox", { name: "认证方式" }));
  fireEvent.keyDown(await screen.findByRole("option", { name: "Bearer Token" }), { key: "Enter" });
  fireEvent.change(screen.getByLabelText("API Key / Token"), {
    target: { value: "transient-test-key" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存并测试" }));
  await screen.findByText(
    "访问设置已保存，连接测试未通过。修改访问设置后，可点“读取工具列表”重试。",
  );
  expect(screen.getByText("上游认证未通过，请检查凭据。")).toBeTruthy();
  expect(screen.getByText("问题编号：discovery-failed")).toBeTruthy();
  expect(screen.queryByDisplayValue("transient-test-key")).toBeNull();
  expect(api.createMcpService).toHaveBeenCalledTimes(1);
  expect(api.createToolConnection).toHaveBeenCalledTimes(1);
  const configure = await screen.findByRole("link", { name: "检查访问设置" });
  expect(configure.getAttribute("href")).toBe(`#tool-connection-${connection.id}`);
  const savedAccount = await screen.findByRole("region", { name: `${connection.name}的访问设置` });
  expect(savedAccount.id).toBe(`tool-connection-${connection.id}`);
  expect(within(savedAccount).getByRole("button", { name: "修改访问设置" })).toBeTruthy();
  expect(await within(savedAccount).findByRole("button", { name: "读取工具列表" })).toBeTruthy();
});
