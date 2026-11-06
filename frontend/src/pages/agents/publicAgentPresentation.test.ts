import { afterEach, expect, it, vi } from "vitest";
import { type PublicAgent } from "@/lib/api/agents";
import { fromPublicSkill } from "@/lib/api/skills";
import { presentPublicAgent } from "@/pages/agents/agentPresentation";

afterEach(() => vi.unstubAllGlobals());

it("uses display endpoints without fabricating editable configuration fields", async () => {
  const agent: PublicAgent = {
    id: "one",
    code: null,
    name: "员工",
    avatar_id: "admin",
    category: "行政",
    description: "简介",
    role_label: null,
    is_active: true,
    is_favorite: false,
    model_configured: true,
    example_tasks: [],
    deliverables: [],
    skill_ids: [],
    resource_counts: { skills: 0, tools: 0, knowledge_bases: 0 },
  };
  const data = {
    agents: [agent],
    skills: [
      fromPublicSkill({
        id: "skill",
        name: "技能",
        category: "其他",
        description: "",
        input_description: "",
        output_description: "",
        example: "",
      }),
    ],
  };
  expect(presentPublicAgent(data.agents[0]).availability).toBe("available");
  expect(
    presentPublicAgent({
      ...agent,
      resource_counts: { skills: 2, tools: 3, knowledge_bases: 1 },
    }),
  ).toMatchObject({
    skillCount: 2,
    toolCount: 3,
    knowledgeBaseCount: 1,
  });
  expect(data.agents[0]).not.toHaveProperty("modelName");
  expect(data.agents[0]).not.toHaveProperty("systemPrompt");
  expect(data.skills[0]).not.toHaveProperty("instructions");
  expect(presentPublicAgent({ ...agent, is_active: false }).availability).toBe("paused");
});
