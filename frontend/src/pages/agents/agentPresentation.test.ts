import { describe, expect, it } from "vitest";
import { toAgentPresentation } from "./agentPresentation";
import { type Agent } from "@/lib/models/agent";
const agent: Agent = {
  id: "00000000-0000-4000-8000-000000000001",
  code: "",
  name: "行政管家",
  role: "",
  category: "财务行政",
  description: "日常支持",
  avatarId: "admin",
  icon: "custom",
  systemPrompt: "",
  modelConnectionId: null,
  toolCount: 0,
  knowledgeBaseCount: 0,
  skills: [],
  deliverables: [],
  exampleTasks: [],
  active: true,
  favorite: false,
};
describe("agent resource summary", () => {
  it("recomputes draft skills while preserving the other resource totals", () => {
    const configured = { ...agent, skills: ["one", "two"], toolCount: 5, knowledgeBaseCount: 1 };
    expect(toAgentPresentation(configured)).toMatchObject({
      skillCount: 2,
      toolCount: 5,
      knowledgeBaseCount: 1,
    });
    expect(toAgentPresentation({ ...configured, skills: [] })).toMatchObject({
      skillCount: 0,
      toolCount: 5,
      knowledgeBaseCount: 1,
    });
  });
});
