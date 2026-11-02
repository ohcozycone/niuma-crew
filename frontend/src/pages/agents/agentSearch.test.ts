import { describe, expect, it } from "vitest";
import { type Skill } from "@/lib/models/skill";
import { type Agent } from "@/lib/models/agent";
import { agentMatches } from "./agentSearch";

const agent: Agent = {
  id: "agent-1",
  code: "",
  name: "行政管家",
  role: "",
  category: "财务行政",
  description: "提供 Office 日常支持",
  avatarId: "admin",
  icon: "custom",
  systemPrompt: "",
  modelConnectionId: null,
  toolCount: 0,
  knowledgeBaseCount: 0,
  skills: ["expense"],
  deliverables: [],
  exampleTasks: [],
  active: true,
  favorite: false,
};
const expense: Skill = {
  id: "expense",
  name: "费用核算",
  category: "财务行政",
  description: "",
  input: "",
  output: "",
  example: "",
};

describe("agent search with an explicit skill catalogue", () => {
  it("matches names, categories and descriptions with whitespace and case normalization", () => {
    for (const query of ["管家", "财务", " OFFICE "])
      expect(agentMatches(agent, query, [])).toBe(true);
  });

  it("matches the names of equipped skills supplied by the caller", () => {
    expect(agentMatches(agent, "费用核算", [expense])).toBe(true);
  });

  it("does not substitute demo skills when the real catalogue is empty or changed", () => {
    expect(agentMatches(agent, "费用核算", [])).toBe(false);
    expect(agentMatches(agent, "费用核算", [{ ...expense, name: "账单复核" }])).toBe(false);
    expect(agentMatches(agent, "账单复核", [{ ...expense, name: "账单复核" }])).toBe(true);
  });

  it("does not match skills the agent has not equipped", () => {
    expect(agentMatches({ ...agent, skills: [] }, "费用核算", [expense])).toBe(false);
  });

  it("keeps every agent when the search is empty", () => {
    expect(agentMatches(agent, "  ", [])).toBe(true);
  });
});
