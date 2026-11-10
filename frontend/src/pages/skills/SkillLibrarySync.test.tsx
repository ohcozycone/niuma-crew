// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useState } from "react";
import { skillLibrary, syncSkillLibrary } from "@/lib/api/skills";
import { WorkspaceDataProvider } from "@/state/workspace/WorkspaceDataProvider";
import { SkillLibrarySync } from "./SkillLibrarySync";

vi.mock("@/state/auth/useIdentity", () => ({
  useIdentity: () => ({
    actor: { kind: "user", user: { id: "owner", username: "admin" } },
    expires_at: "2099",
    permissions: ["agents:read"],
  }),
}));
vi.mock("@/lib/api/skills", () => ({ skillLibrary: vi.fn(), syncSkillLibrary: vi.fn() }));
afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(skillLibrary).mockResolvedValue({ directory: "/data/.agents/skills" });
});

function SyncHarness() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)}>同步目录技能</button>
      <SkillLibrarySync open={open} onClose={() => setOpen(false)} />
    </>
  );
}

it("shows the actual backend directory and a per-package result without auto-assembly", async () => {
  vi.mocked(syncSkillLibrary).mockResolvedValue({
    directory: "/data/.agents/skills",
    items: [
      { name: "code-review", status: "added", skill_id: "skill", message: "" },
      { name: "invalid", status: "error", message: "目录名与标准名称不一致" },
    ],
  });
  render(<SyncHarness />, { wrapper: WorkspaceDataProvider });
  fireEvent.click(screen.getByRole("button", { name: "同步目录技能" }));
  await screen.findByText("/data/.agents/skills");
  expect(syncSkillLibrary).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "同步到能力库" }));
  await screen.findByText("code-review");
  expect(screen.getByText("目录名与标准名称不一致")).toBeTruthy();
  expect(syncSkillLibrary).toHaveBeenCalledTimes(1);
});

it("keeps failures actionable and allows a retry", async () => {
  vi.mocked(syncSkillLibrary).mockRejectedValueOnce(new Error("技能目录不可读"));
  render(<SyncHarness />, { wrapper: WorkspaceDataProvider });
  fireEvent.click(screen.getByRole("button", { name: "同步目录技能" }));
  await screen.findByText("/data/.agents/skills");
  fireEvent.click(screen.getByRole("button", { name: "同步到能力库" }));
  await screen.findByRole("alert");
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "同步到能力库" }).hasAttribute("disabled")).toBe(
      false,
    ),
  );
});
