import { afterEach, expect, it, vi } from "vitest";
import * as skillApi from "@/lib/api/skills";
import { request } from "@/lib/api/http";
import type { Skill } from "@/lib/models/skill";
import { WorkspaceData } from "./workspaceData";

vi.mock("@/lib/api/skills", async (original) => ({
  ...(await original<object>()),
  skillPage: vi.fn(),
  saveSkill: vi.fn(),
}));
vi.mock("@/lib/api/http", async (original) => ({
  ...(await original<object>()),
  request: vi.fn(),
}));
afterEach(() => vi.resetAllMocks());
it("routes a skill save to shared skill, capability and navigation reads without global version broadcasts", async () => {
  vi.mocked(skillApi.skillPage).mockResolvedValue({ items: [], total: 0, offset: 0, limit: 20 });
  vi.mocked(request).mockImplementation(async (path) =>
    path.startsWith("capabilities")
      ? { items: [], total: 0 }
      : { agents: 1, skills: 1, favorites: 0 },
  );
  const data = new WorkspaceData(true);
  const release = data.retain();
  const skills = data.skills.page(new URLSearchParams("offset=0&limit=20&q="));
  const capabilities = data.capabilities(new URLSearchParams("offset=0&limit=20&q=&kind=all"));
  const stops = [
    skills.subscribe(vi.fn()),
    capabilities.subscribe(vi.fn()),
    data.summary.subscribe(vi.fn()),
  ];
  await Promise.all([skills.ensure(), capabilities.ensure(), data.summary.ensure()]);
  const skill: Skill = {
    id: "skill",
    name: "工作方法",
    category: "其他",
    description: "",
    instructions: "正文",
    input: "",
    output: "",
    example: "",
    configurationLoaded: true,
    revision: 1,
  };
  vi.mocked(skillApi.saveSkill).mockResolvedValueOnce({ ...skill, revision: 2 });
  await data.skills.save(skill, false);
  await Promise.all([skills.ensure(), capabilities.ensure(), data.summary.ensure()]);
  expect(skillApi.skillPage).toHaveBeenCalledTimes(2);
  expect(
    vi.mocked(request).mock.calls.filter(([path]) => path.startsWith("capabilities")),
  ).toHaveLength(2);
  expect(
    vi.mocked(request).mock.calls.filter(([path]) => path === "configuration-summary"),
  ).toHaveLength(2);
  stops.forEach((stop) => stop());
  release();
});

it("keeps the workspace summary usable after many inactive search queries", async () => {
  vi.mocked(request).mockResolvedValue({ agents: 1, skills: 1, favorites: 0 });
  const data = new WorkspaceData(true);
  const release = data.retain();
  for (let i = 0; i < 40; i += 1) data.search(`query-${i}`);
  const stop = data.summary.subscribe(vi.fn());
  await data.summary.ensure();
  expect(data.summary.getSnapshot().data?.agents).toBe(1);
  stop();
  release();
});
