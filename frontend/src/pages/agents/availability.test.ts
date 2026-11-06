import { describe, expect, it } from "vitest";
import { canStartConversation, agentAvailability } from "@/lib/models/agentAvailability";
import { toAgentPresentation } from "@/pages/agents/agentPresentation";
const initialAgents = [
  {
    id: "test",
    code: "",
    name: "测试员工",
    role: "",
    category: "测试",
    description: "",
    avatarId: "intern",
    icon: "custom" as const,
    systemPrompt: "",
    modelConnectionId: "test-model",
    skills: ["skill"],
    toolCount: 0,
    knowledgeBaseCount: 0,
    exampleTasks: [],
    deliverables: [],
    active: true,
    favorite: false,
  },
];

describe("conversation prerequisites", () => {
  it("allows an active agent with a model and no skills, prompts or examples", () => {
    const agent = {
      ...initialAgents[0],
      active: true,
      modelConnectionId: "test-model",
      skills: [],
      systemPrompt: "",
      exampleTasks: [],
    };
    expect(canStartConversation(agent)).toBe(true);
    expect(toAgentPresentation(agent)).toMatchObject({
      availability: "available",
      skillCount: 0,
    });
  });
  it.each([null, undefined])(
    "does not substitute equipped skills for a missing model connection (%j)",
    (modelConnectionId) => {
      const agent = { ...initialAgents[0], active: true, modelConnectionId };
      expect(agent.skills.length).toBeGreaterThan(0);
      expect(canStartConversation(agent)).toBe(false);
      expect(toAgentPresentation(agent).availability).toBe("unconfigured");
    },
  );
  it("preserves pause and resume semantics independent of skill count", () => {
    expect(agentAvailability({ active: false, modelConnectionId: "test-model" })).toBe("paused");
    expect(canStartConversation({ active: false, modelConnectionId: "test-model" })).toBe(false);
    expect(agentAvailability({ active: true, modelConnectionId: "test-model" })).toBe("available");
    expect(agentAvailability({ active: true, modelConnectionId: null })).toBe("unconfigured");
  });
});
