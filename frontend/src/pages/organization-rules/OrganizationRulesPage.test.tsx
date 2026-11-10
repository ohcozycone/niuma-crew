// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router";
import { loadOrganizationRules, saveOrganizationRules } from "@/lib/api/organizationRules";
import { EditingProvider } from "@/state/editing/useEditing";
import { OrganizationRulesPage } from "./OrganizationRulesPage";

let allowed = true;
vi.mock("@/state/auth/useIdentity", () => ({
  useIdentity: () => ({
    actor: { kind: "user", user: { id: "owner" } },
    permissions: allowed
      ? ["knowledge:use", "organization_rules:read", "organization_rules:update"]
      : ["knowledge:use"],
  }),
}));
vi.mock("@/lib/api/organizationRules", () => ({
  loadOrganizationRules: vi.fn(),
  saveOrganizationRules: vi.fn(),
}));
const rules = { instructions: "如实回答", revision: 2, updated_at: "2026-11-06T01:00:00Z" };
beforeEach(() => {
  allowed = true;
  localStorage.clear();
  vi.mocked(loadOrganizationRules).mockResolvedValue(rules);
});
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});
function open(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <EditingProvider>
        <Routes>
          <Route path="/rules" element={<OrganizationRulesPage />} />
        </Routes>
      </EditingProvider>
    </MemoryRouter>,
  );
}

it("saves independent rules with their revision and updates the button state", async () => {
  vi.mocked(saveOrganizationRules).mockResolvedValue({
    ...rules,
    instructions: "核对后回答",
    revision: 3,
  });
  open("/rules");
  const input = await screen.findByRole("textbox", { name: "制度正文" });
  expect(screen.getByRole("heading", { name: "全员规范" })).toBeTruthy();
  expect(screen.queryByRole("tab")).toBeNull();
  expect(screen.getByRole("button", { name: "已保存" })).toHaveProperty("disabled", true);
  fireEvent.change(input, { target: { value: "核对后回答" } });
  fireEvent.click(screen.getByRole("button", { name: "保存规范" }));
  await waitFor(() =>
    expect(saveOrganizationRules).toHaveBeenCalledExactlyOnceWith("核对后回答", 2),
  );
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "已保存" })).toHaveProperty("disabled", true),
  );
});

it("rejects a direct rules visit without requesting restricted data", async () => {
  allowed = false;
  open("/rules");
  await screen.findByText("全员规范需要管理员权限。");
  expect(loadOrganizationRules).not.toHaveBeenCalled();
  expect(screen.queryByRole("textbox")).toBeNull();
});
