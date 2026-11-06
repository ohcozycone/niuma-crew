import { afterEach, expect, it, vi } from "vitest";
import {
  connectionInput,
  saveModelConnection,
  testModelConnection,
  type ModelConnection,
} from "./modelConnections";
import { agentInput, fromAgent, type AgentDTO } from "@/lib/api/agents";
import { canStartConversation } from "@/lib/models/agentAvailability";
import { safeReturnPath } from "@/lib/navigation";

afterEach(() => vi.unstubAllGlobals());
it("omits an unchanged key on edit and sends a replacement only when entered", () => {
  const input = {
    name: " Kimi ",
    model_id: " kimi-for-coding ",
    preset_id: "kimi-code",
    api_key: "",
  };
  expect(connectionInput(input, true)).toEqual({
    name: "Kimi",
    model_id: "kimi-for-coding",
    enabled: true,
  });
  expect(connectionInput({ ...input, api_key: " new-key " }, true)).toEqual({
    name: "Kimi",
    model_id: "kimi-for-coding",
    api_key: "new-key",
    enabled: true,
  });
  expect(connectionInput(input, false)).toHaveProperty("preset_id", "kimi-code");
});
it("saves connections and explicitly tests the saved record", async () => {
  const fetcher = vi.fn().mockImplementation(async () => Response.json({ id: "connection" }));
  vi.stubGlobal("fetch", fetcher);
  await saveModelConnection({
    name: "Kimi",
    model_id: "kimi-for-coding",
    preset_id: "kimi-code",
    api_key: "key",
  });
  expect(fetcher.mock.calls[0][0]).toBe("/api/model-connections");
  expect(fetcher.mock.calls[0][1].method).toBe("POST");
  await saveModelConnection({ name: "Kimi", model_id: "k3", preset_id: "kimi-code", api_key: "" }, {
    id: "connection",
    config_revision: 3,
    credential_revision: 2,
  } as ModelConnection);
  expect(JSON.parse(fetcher.mock.calls[1][1].body)).not.toHaveProperty("api_key");
  await testModelConnection("connection");
  expect(fetcher.mock.calls[2][0]).toBe("/api/model-connections/connection/test");
  expect(fetcher.mock.calls[2][1].body).toBe("{}");
});
it("round trips bindings and requires an explicit model connection", () => {
  const dto = {
    id: "agent",
    name: "员工",
    avatar_id: "admin",
    revision: 1,
    model_connection_id: null,
    is_active: true,
    skill_assignments: [],
    resource_counts: { skills: 0, tools: 0, knowledge_bases: 0 },
    example_tasks: [],
    deliverables: [],
  } as unknown as AgentDTO;
  const agent = fromAgent(dto);
  expect(canStartConversation(agent)).toBe(false);
  expect(agentInput(agent).model_connection_id).toBeNull();
  const bound = { ...agent, modelConnectionId: "brain" };
  expect(canStartConversation(bound)).toBe(true);
  expect(canStartConversation({ ...bound, active: false })).toBe(false);
  expect(agentInput(bound).model_connection_id).toBe("brain");
  expect(safeReturnPath("/brains")).toBe("/brains");
});
