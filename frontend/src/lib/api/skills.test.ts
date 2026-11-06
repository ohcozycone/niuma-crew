import { afterEach, expect, it, vi } from "vitest";
import { fromSkillSummary, saveSkill } from "./skills";

afterEach(() => vi.unstubAllGlobals());

it("refuses to save a directory summary before full instructions are loaded", async () => {
  const fetcher = vi.fn();
  vi.stubGlobal("fetch", fetcher);
  const summary = fromSkillSummary({
    id: "method",
    name: "摘要",
    category: "其他",
    description: "目录简介",
    is_active: true,
    revision: 3,
    assignment_count: 1,
    updated_at: "2026-10-27T00:00:00Z",
  });
  await expect(
    saveSkill({ ...summary, input: "", output: "", example: "" }, false),
  ).rejects.toThrow("请先读取技能详情");
  expect(fetcher).not.toHaveBeenCalled();
});
