// @vitest-environment jsdom
import { useState } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { listToolConnections, type ToolConnection, type ToolGrantInput } from "@/lib/api/tools";
import { getSkill, skillPage } from "@/lib/api/skills";
import { AgentCapabilityAssembly } from "./AgentCapabilityAssembly";

vi.mock("@/state/auth/useIdentity", () => ({
  useIdentity: () => ({ actor: { user: { id: "owner" } } }),
}));
vi.mock("@/lib/api/tools", async (original) => ({
  ...(await original<object>()),
  listToolConnections: vi.fn(),
}));
vi.mock("@/lib/api/skills", async (original) => ({
  ...(await original<object>()),
  getSkill: vi.fn(),
  skillPage: vi.fn(),
}));

const connections: ToolConnection[] = Array.from({ length: 11 }, (_, index) => ({
  id: `tool-${index}`,
  name: `工具 ${index}`,
  kind: "mcp_http",
  service_id: "service",
  account_scope: "shared",
  created_by_user_id: "owner",
  tool_annotations: {},
  annotations_revision: 1,
  provider_key: null,
  auth_type: "none",
  public_config: {},
  enabled: true,
  has_credential: false,
  config_revision: 1,
  credential_revision: 1,
  catalog_revision: 1,
  discovery_candidate: null,
  approved_catalog: [{ name: "search", description: "搜索网页", descriptor_hash: "hash" }],
}));
const initial: ToolGrantInput[] = connections.slice(0, 10).map((item) => ({
  connection_id: item.id,
  tools: ["search"],
  expected_descriptors: { search: "hash" },
  scope_policy: {},
  account_mode: "shared",
  enabled: true,
}));
const changed = vi.fn();
function Harness() {
  const [tools, setTools] = useState(initial);
  const [ids, setIds] = useState(["research"]);
  const [settings, setSettings] = useState<
    Record<string, { enabled: boolean; parameters: string }>
  >({ research: { enabled: true, parameters: '{"topic":"原值"}' } });
  return (
    <MemoryRouter>
      <AgentCapabilityAssembly
        tools={{
          value: tools,
          onChange: (next) => {
            setTools(next);
            changed(next);
          },
          onValidityChange: vi.fn(),
        }}
        skills={{
          ids,
          skills: [],
          settings,
          onChange: setSettings,
          onSelectionChange: (next) => {
            setIds(next);
            changed(next);
          },
        }}
      />
    </MemoryRouter>
  );
}
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listToolConnections).mockResolvedValue(connections);
  vi.mocked(skillPage).mockResolvedValue({ items: [], total: 0, offset: 0, limit: 20 });
  vi.mocked(getSkill).mockResolvedValue({
    id: "research",
    name: "资料研究",
    category: "研究",
    description: "核对来源",
    input: "",
    output: "",
    example: "",
    configurationSchema: { type: "object", properties: { topic: { type: "string" } } },
  });
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

it("debounces remote skill candidates while the installed ability search remains local", async () => {
  render(<Harness />);
  await screen.findByText("工具 0");
  fireEvent.change(screen.getByRole("textbox", { name: "搜索已装配能力" }), {
    target: { value: "资料" },
  });
  expect(skillPage).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "添加能力" }));
  await act(async () => {});
  expect(skillPage).toHaveBeenCalledTimes(1);
  vi.useFakeTimers();
  const input = screen.getByRole("textbox", { name: "搜索候选能力" });
  fireEvent.change(input, { target: { value: "资" } });
  await act(async () => vi.advanceTimersByTimeAsync(200));
  fireEvent.change(input, { target: { value: "资料" } });
  await act(async () => vi.advanceTimersByTimeAsync(299));
  expect(skillPage).toHaveBeenCalledTimes(1);
  await act(async () => vi.advanceTimersByTimeAsync(1));
  expect(skillPage).toHaveBeenCalledTimes(2);
  expect(vi.mocked(skillPage).mock.lastCall?.[0].get("q")).toBe("资料");
  expect(vi.mocked(skillPage).mock.lastCall?.[0].get("offset")).toBe("0");
});

it("adds a tool through the shared chooser only after the operation panel is completed", async () => {
  render(<Harness />);
  await screen.findByText("工具 0");
  fireEvent.click(screen.getByRole("button", { name: "添加能力" }));
  fireEvent.click(await screen.findByRole("button", { name: /工具 10/ }));
  expect(changed).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("checkbox", { name: /search/ }));
  expect(changed).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "完成，更新草稿" }));
  expect(changed).toHaveBeenCalledTimes(1);
  expect(changed.mock.calls[0][0]).toHaveLength(11);
  expect(changed.mock.calls[0][0].at(-1)).toMatchObject({
    connection_id: "tool-10",
    tools: ["search"],
  });
});

it("keeps skills directly reachable among many tools and confirms removal before touching the draft", async () => {
  render(<Harness />);
  await screen.findByText("工具 0");
  expect(screen.getAllByRole("button", { name: "配置" })).toHaveLength(6);
  fireEvent.click(screen.getByRole("button", { name: "下一页" }));
  expect(screen.getAllByRole("button", { name: "配置" })).toHaveLength(5);
  fireEvent.click(
    within(screen.getByRole("group", { name: "筛选已装配能力" })).getByRole("button", {
      name: /技能/,
    }),
  );
  await screen.findByText("资料研究");
  expect(screen.getAllByRole("button", { name: "配置" })).toHaveLength(1);
  fireEvent.click(screen.getByRole("button", { name: "移除资料研究" }));
  expect(changed).not.toHaveBeenCalled();
  expect(screen.getByRole("dialog").textContent).toContain("保存员工配置后生效");
  fireEvent.click(screen.getByRole("button", { name: "取消" }));
  expect(changed).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "移除资料研究" }));
  fireEvent.click(screen.getByRole("button", { name: "确认移除" }));
  expect(changed).toHaveBeenCalledExactlyOnceWith([]);
  expect(screen.queryByText("资料研究")).toBeNull();
});

it("discards cancelled panel inputs and retains completed settings across filtering and search", async () => {
  render(<Harness />);
  fireEvent.click(
    within(screen.getByRole("group", { name: "筛选已装配能力" })).getByRole("button", {
      name: /技能/,
    }),
  );
  await screen.findByText("资料研究");
  fireEvent.click(screen.getByRole("button", { name: "配置" }));
  const field = await screen.findByRole("textbox", { name: /装配参数/ });
  fireEvent.change(field, { target: { value: '{"topic":"取消输入"}' } });
  fireEvent.click(screen.getByRole("button", { name: "取消" }));
  fireEvent.click(screen.getByRole("button", { name: "配置" }));
  expect(await screen.findByRole("textbox", { name: /装配参数/ })).toHaveProperty(
    "value",
    '{"topic":"原值"}',
  );
  fireEvent.change(screen.getByRole("textbox", { name: /装配参数/ }), {
    target: { value: '{"topic":"已完成"}' },
  });
  fireEvent.click(screen.getByRole("button", { name: "完成，更新草稿" }));
  fireEvent.click(
    within(screen.getByRole("group", { name: "筛选已装配能力" })).getByRole("button", {
      name: /工具/,
    }),
  );
  fireEvent.change(screen.getByRole("textbox", { name: "搜索已装配能力" }), {
    target: { value: "工具 9" },
  });
  expect(screen.getAllByRole("button", { name: "配置" })).toHaveLength(1);
  fireEvent.change(screen.getByRole("textbox", { name: "搜索已装配能力" }), {
    target: { value: "" },
  });
  fireEvent.click(
    within(screen.getByRole("group", { name: "筛选已装配能力" })).getByRole("button", {
      name: /技能/,
    }),
  );
  fireEvent.click(screen.getByRole("button", { name: "配置" }));
  const saved = await screen.findByRole("textbox", { name: /装配参数/ });
  expect(JSON.parse((saved as HTMLTextAreaElement).value)).toEqual({ topic: "已完成" });
});

it("keeps the catalog open for consecutive skill additions and marks selected entries", async () => {
  vi.mocked(skillPage).mockResolvedValue({
    items: [
      { id: "first", name: "技能甲", description: "整理资料" },
      { id: "second", name: "技能乙", description: "核对资料" },
    ].map((item) => ({
      ...item,
      category: "研究",
      is_active: true,
      revision: 1,
      assignment_count: 0,
      updated_at: "2026-11-06T00:00:00Z",
    })),
    total: 2,
    offset: 0,
    limit: 20,
  });
  render(<Harness />);
  fireEvent.click(screen.getByRole("button", { name: "添加能力" }));
  fireEvent.click(await screen.findByRole("button", { name: /技能甲/ }));
  expect(screen.getByRole("dialog")).toBeTruthy();
  expect((screen.getByRole("button", { name: /技能甲/ }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByRole("status").textContent).toContain("技能甲");
  fireEvent.click(screen.getByRole("button", { name: /技能乙/ }));
  expect(changed).toHaveBeenLastCalledWith(["research", "first", "second"]);
  fireEvent.click(screen.getByRole("button", { name: "完成选择" }));
  expect(screen.queryByRole("dialog")).toBeNull();
});
