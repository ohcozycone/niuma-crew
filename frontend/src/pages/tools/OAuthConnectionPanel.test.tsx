// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { OAuthConnectionPanel } from "./OAuthConnectionPanel";
import * as api from "@/lib/api/tools";

vi.mock("@/lib/api/tools", () => ({
  startToolOAuth: vi.fn(),
  readToolOAuth: vi.fn(),
  cancelToolOAuth: vi.fn(),
  disconnectToolOAuth: vi.fn(),
  listToolConnections: vi.fn(),
  discoverTools: vi.fn(),
}));
const connection: api.ToolConnection = {
  id: "connection",
  service_id: "service",
  name: "OAuth",
  kind: "mcp_http",
  auth_type: "oauth",
  account_scope: "personal",
  created_by_user_id: "owner",
  public_config: { url: "https://example.com/mcp" },
  provider_key: null,
  enabled: true,
  has_credential: true,
  oauth_status: "connected",
  config_revision: 1,
  credential_revision: 2,
  catalog_revision: 1,
  annotations_revision: 1,
  tool_annotations: {},
  approved_catalog: [],
  discovery_candidate: null,
};
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.listToolConnections).mockResolvedValue([connection]);
  vi.mocked(api.discoverTools).mockResolvedValue(connection);
});
afterEach(cleanup);
function show(query = "?oauth_connection=connection&oauth_session=session", value = connection) {
  const change = vi.fn();
  render(
    <MemoryRouter initialEntries={[`/tools${query}`]}>
      <OAuthConnectionPanel connection={value} onChange={change} />
    </MemoryRouter>,
  );
  return change;
}
it("returns from authorization and reads a candidate without approving it", async () => {
  vi.mocked(api.readToolOAuth).mockResolvedValue({
    id: "session",
    status: "succeeded",
    authorization_url: null,
    error_code: null,
    error_message: null,
  });
  const change = show();
  await screen.findByText("工具列表已读取，请确认后到员工页面装配。");
  expect(api.discoverTools).toHaveBeenCalledExactlyOnceWith("connection");
  expect(change).toHaveBeenCalledWith(connection);
  expect(api.startToolOAuth).not.toHaveBeenCalled();
});
it("keeps a failed authorization from discovering tools", async () => {
  vi.mocked(api.readToolOAuth).mockResolvedValue({
    id: "session",
    status: "cancelled",
    authorization_url: null,
    error_code: null,
    error_message: null,
  });
  show();
  await screen.findByText("授权未完成，请重新连接账号。");
  expect(api.discoverTools).not.toHaveBeenCalled();
});
it("requires confirmation before disconnecting and applies the returned account", async () => {
  const disconnected = {
    ...connection,
    oauth_status: "disconnected" as const,
    has_credential: false,
  };
  vi.mocked(api.disconnectToolOAuth).mockResolvedValue(disconnected);
  const change = show("");
  fireEvent.click(screen.getByRole("button", { name: "断开账号" }));
  expect(api.disconnectToolOAuth).not.toHaveBeenCalled();
  fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "断开账号" }));
  await waitFor(() => expect(change).toHaveBeenCalledWith(disconnected));
});
it("starts one flow and can cancel while discovery is preparing", async () => {
  vi.mocked(api.startToolOAuth).mockResolvedValue({
    id: "session",
    status: "preparing",
    authorization_url: null,
    error_code: null,
    error_message: null,
  });
  vi.mocked(api.readToolOAuth).mockResolvedValue({
    id: "session",
    status: "preparing",
    authorization_url: null,
    error_code: null,
    error_message: null,
  });
  show("", { ...connection, oauth_status: "disconnected", has_credential: false });
  fireEvent.click(screen.getByRole("button", { name: "连接账号" }));
  fireEvent.click(await screen.findByRole("button", { name: "取消授权" }));
  await screen.findByText("已取消授权。");
  expect(api.startToolOAuth).toHaveBeenCalledTimes(1);
  expect(api.cancelToolOAuth).toHaveBeenCalledWith("connection", "session");
  expect(api.discoverTools).not.toHaveBeenCalled();
});
