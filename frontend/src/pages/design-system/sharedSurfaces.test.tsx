// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { AgentCard, type AgentPresentation } from "@/pages/agents";
import { CapabilityCard } from "@/components/skills/CapabilityCard";
import { SkillCard } from "@/components/skills/SkillCard";
vi.mock("@/components/avatars/index", () => ({ AgentAvatar: () => null }));
afterEach(cleanup);
it("employee, legacy skill and capability cards share the same surface and footer while preserving their actions", () => {
  const agent: AgentPresentation = {
    id: "employee",
    name: "测试员工",
    subtitle: "研发",
    description: "工作范围",
    avatarId: "admin",
    availability: "available",
    favorite: false,
    skillCount: 1,
    toolCount: 0,
    knowledgeBaseCount: 0,
  };
  render(
    <MemoryRouter>
      <AgentCard agent={agent} onAction={vi.fn()} />
      <SkillCard
        skill={{ id: "skill", name: "旧技能", category: "其他", description: "技能说明" }}
        expanded={false}
        onExpand={vi.fn()}
      />
      <CapabilityCard
        item={{
          id: "capability",
          name: "能力条目",
          description: "能力说明",
          kind: "skill",
          enabled: true,
        }}
      />
    </MemoryRouter>,
  );
  const cards = screen.getAllByRole("article");
  expect(cards).toHaveLength(3);
  for (const card of cards) {
    expect(card.getAttribute("data-slot")).toBe("card");
    expect(card.getAttribute("data-variant")).toBe("raised");
    expect(card.classList.contains("rounded-card")).toBe(true);
    expect(card.querySelector('[data-slot="card-footer"]')).not.toBeNull();
  }
  expect(screen.getByRole("button", { name: "打开测试员工的员工主页" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "查看旧技能详情" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "查看配置" }).getAttribute("href")).toBe(
    "/skills/capability",
  );
});
