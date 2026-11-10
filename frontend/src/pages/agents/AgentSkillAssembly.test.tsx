// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { AgentSkillAssembly } from "./AgentSkillAssembly";
import { getSkill } from "@/lib/api/skills";
vi.mock("@/lib/api/skills", () => ({
  getSkill: vi.fn(),
  skillPage: vi.fn(),
  fromSkillSummary: vi.fn(),
}));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
it("loads an assigned skill outside the candidate page and does not invent parameters for an empty schema", async () => {
  vi.mocked(getSkill).mockResolvedValue({
    id: "outside",
    name: "不在当前候选页",
    category: "其他",
    description: "说明",
    input: "",
    output: "",
    example: "",
    configurationSchema: {},
  });
  render(
    <AgentSkillAssembly
      ids={["outside"]}
      skills={[]}
      settings={{}}
      onChange={vi.fn()}
      onSelectionChange={vi.fn()}
    />,
  );
  await screen.findByText("不在当前候选页");
  fireEvent.click(screen.getByRole("button", { name: "配置" }));
  await screen.findByText("此技能未声明装配参数，无需填写额外字段。");
  expect(screen.queryByRole("textbox")).toBeNull();
});
