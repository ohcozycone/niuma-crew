import { afterEach, describe, expect, it, vi } from "vitest";
import {
  deleteAgent,
  agentInput,
  fromAgent,
  agentPage,
  patchAgent,
  saveAgent,
  type AgentDTO,
} from "@/lib/api/agents";
import { saveSkill } from "@/lib/api/skills";
import { ApiError, request } from "@/lib/api/http";
const agent: AgentDTO = {
  id: "a9f87713-3f79-4c6d-bfc7-3dd42d3fc640",
  name: "行政管家",
  avatar_id: "admin",
  code: null,
  category: "行政",
  description: "简介",
  role_label: null,
  system_prompt: "指令",
  revision: 1,
  model_connection_id: null,
  is_active: true,
  is_favorite: false,
  example_tasks: ["任务"],
  deliverables: ["报告"],
  skill_assignments: [],
  resource_counts: { skills: 0, tools: 0, knowledge_bases: 0 },
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};
afterEach(() => vi.unstubAllGlobals());
describe("configuration API integration contracts", () => {
  it("preserves read-only tool and knowledge totals from the agent response", () => {
    const configured = fromAgent({
      ...agent,
      skill_assignments: ["first", "second"].map((skillId) => ({
        skill_id: skillId,
        enabled: true,
        parameters: {},
        revision: 1,
        ready: true,
        name: "技能",
        readiness_reason: null,
      })),
      resource_counts: { skills: 2, tools: 5, knowledge_bases: 1 },
    });
    expect(configured).toMatchObject({
      skills: ["first", "second"],
      toolCount: 5,
      knowledgeBaseCount: 1,
    });
    expect(agentInput(configured)).not.toHaveProperty("resource_counts");
  });
  it("requests only the requested page and never loads all agents", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(Response.json({ items: [], total: 101, offset: 20, limit: 20 }));
    vi.stubGlobal("fetch", fetcher);
    expect(
      (await agentPage(new URLSearchParams({ offset: "20", limit: "20", q: "员工" }))).total,
    ).toBe(101);
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher.mock.calls[0][0]).toContain("offset=20&limit=20");
  });
  it("round trips nullable and array values and canonicalizes legacy avatar IDs without submitting read-only fields", () => {
    const input = agentInput({
      ...fromAgent(agent),
      avatarId: "goofy-v5-company--cow-admin-goofy",
    });
    expect(input).toMatchObject({
      code: null,
      expected_revision: 1,
      model_connection_id: null,
      role_label: null,
      avatar_id: "admin",
      skill_assignments: [],
    });
    expect(input).not.toHaveProperty("id");
    expect(input).not.toHaveProperty("created_at");
    expect(input).not.toHaveProperty("resource_counts");
    expect(input).not.toHaveProperty("toolCount");
    expect(input).not.toHaveProperty("knowledgeBaseCount");
    expect(input.system_prompt).toBe(agent.system_prompt);
  });
  it.each(["legal", "goofy-v5-company--cow-hr-goofy", "unknown-avatar"])(
    "preserves stored avatar %s when only the display needs a fallback",
    (avatarId) => {
      expect(agentInput({ ...fromAgent(agent), avatarId }).avatar_id).toBe(avatarId);
    },
  );
  it("uses the returned agent UUID and updates only the intended status", async () => {
    const fetcher = vi.fn().mockResolvedValue(Response.json(agent));
    vi.stubGlobal("fetch", fetcher);
    const result = await saveAgent({ ...fromAgent(agent), id: "draft" }, true);
    expect(result.id).toBe(agent.id);
    expect(fetcher.mock.calls[0][0]).toBe("/api/agents");
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).not.toHaveProperty("id");
    fetcher.mockResolvedValue(Response.json({ ...agent, is_favorite: true }));
    await patchAgent(agent.id, { is_favorite: true }, 1);
    expect(JSON.parse(fetcher.mock.calls[1][1].body)).toEqual({
      is_favorite: true,
      expected_revision: 1,
    });
  });
  it("preserves skill instructions and supports empty delete responses", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      Response.json({
        id: "skill",
        name: "摘要",
        category: "其他",
        description: "",
        instructions: "保留\n换行",
        input_description: "",
        output_description: "",
        example: "",
      }),
    );
    vi.stubGlobal("fetch", fetcher);
    const result = await saveSkill(
      {
        id: "",
        name: "摘要",
        category: "其他",
        description: "",
        instructions: "保留\n换行",
        input: "",
        output: "",
        example: "",
      },
      true,
    );
    expect(result.instructions).toBe("保留\n换行");
    fetcher.mockResolvedValue(new Response(null, { status: 204 }));
    await expect(deleteAgent(agent.id)).resolves.toBeUndefined();
  });
  it.each([409, 404, 503, 502])(
    "reports %s without pretending a write succeeded",
    async (status) => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(Response.json({ detail: { message: "不能保存" } }, { status })),
      );
      await expect(saveAgent(fromAgent(agent), false)).rejects.toMatchObject({
        message: "不能保存",
        status,
      });
    },
  );
  it("shows the rejected name field and validator reason without echoing input or context", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        Response.json(
          {
            detail: [
              {
                type: "value_error",
                loc: ["body", "name"],
                msg: "Value error, 名称不能重复。",
                input: "private-input",
                ctx: { error: "private-context" },
              },
            ],
          },
          { status: 422 },
        ),
      ),
    );
    await expect(request("agents")).rejects.toMatchObject({
      status: 422,
      message: "名称：名称不能重复。",
    });
  });
  it("identifies a nested assignment parameter and a malformed skill ID", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        Response.json(
          {
            detail: [
              {
                type: "value_error",
                loc: ["body", "skill_assignments", 0, "parameters"],
                msg: "Value error, 装配参数无效。",
              },
              {
                type: "uuid_parsing",
                loc: ["body", "selected_skill_ids", 0],
                msg: "Input should be a valid UUID",
              },
            ],
          },
          { status: 422 },
        ),
      ),
    );
    await expect(request("conversations/example/runs")).rejects.toThrow(
      "技能装配：装配参数无效。\n技能选择：标识格式无效，请重新选择。",
    );
  });
  it("handles validation, non-JSON server failure and network failure", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(
        Response.json({ detail: [{ loc: ["body", "name"] }] }, { status: 422 }),
      )
      .mockResolvedValueOnce(new Response("Unavailable", { status: 500 }))
      .mockRejectedValueOnce(new TypeError("offline"));
    vi.stubGlobal("fetch", fetcher);
    await expect(request("agents")).rejects.toThrow("提交内容不符合要求");
    await expect(request("agents")).rejects.toBeInstanceOf(ApiError);
    await expect(request("agents")).rejects.toMatchObject({
      source: "network",
      code: "client_connection_failed",
      status: 0,
    });
  });
});

it("prevents a directory summary from overwriting full agent configuration", async () => {
  const fetcher = vi.fn();
  vi.stubGlobal("fetch", fetcher);
  await expect(
    saveAgent({ ...fromAgent(agent), configurationLoaded: false }, false),
  ).rejects.toThrow("详情");
  expect(fetcher).not.toHaveBeenCalled();
});
