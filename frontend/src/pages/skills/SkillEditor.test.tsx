// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { SkillEditor } from "./SkillEditor";
import { readSkillFile } from "@/lib/api/skills";
import type { Skill } from "@/lib/models/skill";
vi.mock("@/state/auth/useIdentity", () => ({
  useIdentity: () => ({
    actor: { kind: "user", user: { id: "owner" } },
    permissions: ["skills:update"],
  }),
}));
vi.mock("@/lib/api/skills", async (original) => ({
  ...(await original<typeof import("@/lib/api/skills")>()),
  readSkillFile: vi.fn(),
}));
const skill: Skill = {
  id: "skill",
  name: "资料整理",
  category: "其他",
  description: "整理",
  instructions: "旧方法",
  input: "旧输入",
  output: "旧输出",
  example: "旧示例",
  revision: 1,
  configurationLoaded: true,
  skillMd: "---\nname: research\ndescription: Research sources.\n---\n\nRead references/notes.md",
  files: [
    { path: "SKILL.md", content_hash: "md", size: 50, media_type: "text/markdown", is_text: true },
    {
      path: "scripts/process.py",
      content_hash: "script",
      size: 9,
      media_type: "text/plain",
      is_text: true,
    },
    {
      path: "assets/logo.png",
      content_hash: "binary",
      size: 3,
      media_type: "image/png",
      is_text: false,
    },
  ],
};
beforeEach(() => {
  sessionStorage.clear();
  vi.clearAllMocks();
});
afterEach(cleanup);
it("saves edited scripts and unchanged binary assets with the canonical markdown in one request", async () => {
  vi.mocked(readSkillFile).mockImplementation(async (_id, path) =>
    path.endsWith(".py")
      ? { path, content: "print(1)", media_type: "text/plain", is_text: true }
      : { path, content_base64: "AQID", media_type: "image/png", is_text: false },
  );
  const save = vi.fn().mockResolvedValue(undefined);
  render(
    <MemoryRouter>
      <SkillEditor value={skill} onSave={save} onClose={vi.fn()} />
    </MemoryRouter>,
  );
  await screen.findByLabelText("SKILL.md 内容");
  fireEvent.click(screen.getByRole("button", { name: "scripts/process.py" }));
  fireEvent.change(screen.getByLabelText("scripts/process.py内容"), {
    target: { value: "print(2)" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存技能" }));
  await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
  const sent = save.mock.calls[0][0];
  expect(sent.packageFiles).toEqual(
    expect.arrayContaining([
      { path: "SKILL.md", content: skill.skillMd },
      { path: "scripts/process.py", content: "print(2)" },
      { path: "assets/logo.png", content_base64: "AQID" },
    ]),
  );
  expect(sent.input).toBe("旧输入");
});
it("blocks saving when supporting files fail to load instead of replacing them with an incomplete package", async () => {
  vi.mocked(readSkillFile).mockRejectedValue(new Error("读取失败"));
  const save = vi.fn();
  render(
    <MemoryRouter>
      <SkillEditor value={skill} onSave={save} onClose={vi.fn()} />
    </MemoryRouter>,
  );
  await screen.findByRole("alert");
  expect(screen.getByRole("button", { name: "保存技能" }).hasAttribute("disabled")).toBe(true);
  expect(save).not.toHaveBeenCalled();
});

it("keeps a supporting file after cancellation and removes only the confirmed path on save", async () => {
  vi.mocked(readSkillFile).mockImplementation(async (_id, path) =>
    path.endsWith(".py")
      ? { path, content: "print(1)", media_type: "text/plain", is_text: true }
      : { path, content_base64: "AQID", media_type: "image/png", is_text: false },
  );
  const save = vi.fn().mockResolvedValue(undefined);
  render(
    <MemoryRouter>
      <SkillEditor value={skill} onSave={save} onClose={vi.fn()} />
    </MemoryRouter>,
  );
  await screen.findByLabelText("SKILL.md 内容");
  fireEvent.click(screen.getByRole("button", { name: "scripts/process.py" }));
  fireEvent.click(screen.getByRole("button", { name: "删除scripts/process.py" }));
  expect(save).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "取消" }));
  expect(screen.getByRole("button", { name: "scripts/process.py" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "删除scripts/process.py" }));
  fireEvent.click(screen.getByRole("button", { name: "确认移除文件" }));
  expect(save).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", { name: "scripts/process.py" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "保存技能" }));
  await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
  expect(save.mock.calls[0][0].packageFiles.map((file: { path: string }) => file.path)).toEqual([
    "SKILL.md",
    "assets/logo.png",
  ]);
});
