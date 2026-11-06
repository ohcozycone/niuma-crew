// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AgentCard } from "./AgentCard";
import type { AgentPresentation } from "./types";

const employee: AgentPresentation = {
  id: "employee",
  name: "测试员工",
  subtitle: "研发协作",
  description: "",
  avatarId: "admin",
  favorite: false,
  skillCount: 0,
  toolCount: 0,
  knowledgeBaseCount: 0,
  availability: "available",
};
afterEach(cleanup);

it("keeps a configured employee usable with no extra resources or description", () => {
  const action = vi.fn();
  render(<AgentCard agent={employee} onAction={action} />);
  fireEvent.click(screen.getByRole("button", { name: "打开测试员工的员工主页" }));
  expect(action).toHaveBeenLastCalledWith("employee", "open");
  fireEvent.click(screen.getByRole("button", { name: "配置测试员工的技能，共 0 项" }));
  expect(action).toHaveBeenLastCalledWith("employee", "skills");
});

it("keeps an unconfigured employee's records reachable without starting a conversation", () => {
  const action = vi.fn();
  const agent = { ...employee, availability: "unconfigured" as const };
  const view = render(<AgentCard agent={agent} onAction={action} />);
  fireEvent.click(screen.getByRole("button", { name: "打开测试员工的员工主页" }));
  expect(action).toHaveBeenCalledExactlyOnceWith("employee", "open");
  view.rerender(<AgentCard agent={agent} onAction={action} readOnly usable />);
  expect(
    screen.getByRole("button", { name: "打开测试员工的员工主页" }).hasAttribute("disabled"),
  ).toBe(false);
});

it("labels permitted read-only conversation access correctly while retaining the guest restriction", () => {
  const action = vi.fn();
  const view = render(<AgentCard agent={employee} onAction={action} readOnly usable />);
  fireEvent.click(screen.getByRole("button", { name: "打开测试员工的员工主页" }));
  expect(screen.getByText("查看员工")).toBeTruthy();
  expect(action).toHaveBeenCalledExactlyOnceWith("employee", "open");
  view.rerender(<AgentCard agent={employee} onAction={action} readOnly />);
  expect(screen.getByRole("button", { name: "体验功能尚未开放" }).hasAttribute("disabled")).toBe(
    true,
  );
});
