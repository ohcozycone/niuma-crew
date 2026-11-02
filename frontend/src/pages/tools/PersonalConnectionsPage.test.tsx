// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router";
import { ApiError } from "@/lib/api/http";
import {
  myToolBindings,
  listToolConnections,
  bindMyTool,
  type PersonalToolBinding,
} from "@/lib/api/tools";
import { PersonalConnectionsPage } from "./PersonalConnectionsPage";

vi.mock("@/state/auth/useIdentity", () => ({
  useIdentity: () => ({ actor: { user: { id: "owner" } } }),
}));
vi.mock("@/lib/api/tools", () => ({
  myToolBindings: vi.fn(),
  listToolConnections: vi.fn(),
  bindMyTool: vi.fn(),
}));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it("keeps the bound account on cancellation and retains a rejected unbind for review", async () => {
  const binding: PersonalToolBinding = {
    grant_id: "grant",
    service_id: "service",
    service_name: "搜索服务",
    account_mode: "personal",
    tools: [],
    connection_id: "account",
    connected: true,
    revision: 2,
  };
  vi.mocked(myToolBindings).mockResolvedValue({ items: [binding] });
  vi.mocked(listToolConnections).mockResolvedValue([
    {
      id: "account",
      name: "本人账号",
      service_id: "service",
      kind: "mcp_http",
      account_scope: "personal",
      created_by_user_id: "owner",
      enabled: true,
      provider_key: null,
      auth_type: "none",
      public_config: {},
      has_credential: false,
      config_revision: 1,
      credential_revision: 1,
      catalog_revision: 1,
      annotations_revision: 1,
      tool_annotations: {},
      approved_catalog: [],
      discovery_candidate: null,
    },
  ]);
  vi.mocked(bindMyTool).mockRejectedValue(
    new ApiError("绑定已变更，请重新核对。", 409, "binding_revision_conflict"),
  );
  render(
    <MemoryRouter initialEntries={["/agents/employee/connections"]}>
      <Routes>
        <Route path="/agents/:id/connections" element={<PersonalConnectionsPage />} />
      </Routes>
    </MemoryRouter>,
  );
  const select = await screen.findByRole("combobox", { name: "选择我的账号" });
  fireEvent.click(select);
  fireEvent.keyDown(await screen.findByRole("option", { name: "未绑定" }), { key: "Enter" });
  await screen.findByRole("dialog");
  expect(bindMyTool).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "取消" }));
  expect(select.textContent).toBe("本人账号");
  expect(bindMyTool).not.toHaveBeenCalled();
  fireEvent.click(select);
  fireEvent.keyDown(await screen.findByRole("option", { name: "未绑定" }), { key: "Enter" });
  fireEvent.click(await screen.findByRole("button", { name: "确认解除绑定" }));
  await screen.findAllByText("绑定已变更，请重新核对。");
  await waitFor(() =>
    expect(bindMyTool).toHaveBeenCalledExactlyOnceWith("employee", binding, null),
  );
  expect(screen.getByRole("dialog")).toBeTruthy();
});
