import { afterEach, expect, it, vi } from "vitest";
import { loadOrganizationRules, saveOrganizationRules } from "./organizationRules";

afterEach(() => vi.unstubAllGlobals());

it("reads the shared rules and sends explicit content and expected revision, including clear", async () => {
  const fetcher = vi
    .fn()
    .mockImplementation(async () =>
      Response.json({ instructions: "", revision: 3, updated_at: "2026-10-21T00:00:00Z" }),
    );
  vi.stubGlobal("fetch", fetcher);
  await loadOrganizationRules();
  expect(fetcher.mock.calls[0][0]).toBe("/api/organization-rules");
  await saveOrganizationRules("保留原始 Markdown\n", 3);
  expect(fetcher.mock.calls[1][1].method).toBe("PUT");
  expect(JSON.parse(fetcher.mock.calls[1][1].body)).toEqual({
    instructions: "保留原始 Markdown\n",
    revision: 3,
  });
  await saveOrganizationRules("", 4);
  expect(JSON.parse(fetcher.mock.calls[2][1].body)).toEqual({ instructions: "", revision: 4 });
});

it("preserves conflict code for the editor instead of retrying or overwriting", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValue(
      Response.json(
        { detail: { code: "rules_revision_conflict", message: "规则已变化" } },
        { status: 409 },
      ),
    );
  vi.stubGlobal("fetch", fetcher);
  await expect(saveOrganizationRules("本地草稿", 1)).rejects.toMatchObject({
    status: 409,
    code: "rules_revision_conflict",
  });
  expect(fetcher).toHaveBeenCalledTimes(1);
});
