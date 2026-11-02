// @vitest-environment jsdom
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import * as skills from "@/lib/api/skills";
import type { Skill } from "@/lib/models/skill";
import { WorkspaceDataProvider } from "@/state/workspace/WorkspaceDataProvider";
import { useSkillEditor } from "./useSkillEditor";

let currentId = "A";
vi.mock("react-router", () => ({ useParams: () => ({ id: currentId }) }));
vi.mock("@/state/auth/useIdentity", () => ({
  useIdentity: () => ({
    actor: { kind: "user", user: { id: "owner", username: "admin" } },
    expires_at: "2099",
    permissions: ["agents:read"],
  }),
}));
vi.mock("@/lib/api/skills", () => ({ getSkill: vi.fn(), saveSkill: vi.fn() }));
const detail = (id: string): Skill => ({
  id,
  name: id,
  category: "其他",
  description: "简介",
  configurationLoaded: true,
  instructions: "完整\n工作方法",
  input: "输入",
  output: "输出",
  example: "示例",
  revision: 3,
  active: true,
});
beforeEach(() => {
  currentId = "A";
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it("does not let a late detail response replace the new editor", async () => {
  let finishA!: (value: Skill) => void;
  vi.mocked(skills.getSkill).mockImplementation((id) =>
    id === "A"
      ? new Promise((resolve) => {
          finishA = resolve;
        })
      : Promise.resolve(detail(id)),
  );
  const view = renderHook(useSkillEditor, { wrapper: WorkspaceDataProvider });
  currentId = "B";
  view.rerender();
  await waitFor(() => expect(view.result.current.ready).toBe(true));
  await act(async () => {
    finishA(detail("A"));
  });
  expect(view.result.current.skills[0].id).toBe("B");
  expect(view.result.current.skills[0].instructions).toBe("完整\n工作方法");
});

it("blocks a duplicate save synchronously and releases the gate after rejection", async () => {
  vi.mocked(skills.getSkill).mockResolvedValue(detail("A"));
  let rejectSave!: (error: Error) => void;
  vi.mocked(skills.saveSkill).mockImplementation(
    () =>
      new Promise((_, reject) => {
        rejectSave = reject;
      }),
  );
  const view = renderHook(useSkillEditor, { wrapper: WorkspaceDataProvider });
  await waitFor(() => expect(view.result.current.ready).toBe(true));
  let first!: Promise<Skill>;
  await act(async () => {
    first = view.result.current.saveSkill(detail("A"), false);
    await expect(view.result.current.saveSkill(detail("A"), false)).rejects.toThrow("正在保存");
  });
  expect(skills.saveSkill).toHaveBeenCalledTimes(1);
  await act(async () => {
    rejectSave(new Error("版本已变化"));
    await expect(first).rejects.toThrow("版本已变化");
  });
  expect(view.result.current.saving).toBe(false);
  expect(view.result.current.skills[0].revision).toBe(3);
});
