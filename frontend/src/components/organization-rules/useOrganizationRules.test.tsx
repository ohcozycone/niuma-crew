// @vitest-environment jsdom
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/http";
import { loadOrganizationRules } from "@/lib/api/organizationRules";
import { useOrganizationRules } from "./useOrganizationRules";

vi.mock("@/lib/api/organizationRules", () => ({ loadOrganizationRules: vi.fn() }));
afterEach(cleanup);
const rules = { instructions: "保留已确认制度", revision: 1, updated_at: "2026-10-31T00:00:00Z" };

it("preserves a confirmed rules read during an unavailable refresh and keeps its facts", async () => {
  vi.mocked(loadOrganizationRules)
    .mockResolvedValueOnce(rules)
    .mockRejectedValueOnce(
      new ApiError("稍后重读", 503, "backend_unavailable", { requestId: "rules-refresh" }),
    );
  const { result } = renderHook(useOrganizationRules);
  await waitFor(() => expect(result.current.rules).toEqual(rules));
  act(() => result.current.reload());
  await waitFor(() =>
    expect(result.current.failure).toMatchObject({
      status: 503,
      code: "backend_unavailable",
      requestId: "rules-refresh",
    }),
  );
  expect(result.current.rules).toEqual(rules);
});

it("clears previously readable rules after an explicit permission rejection", async () => {
  vi.mocked(loadOrganizationRules)
    .mockResolvedValueOnce(rules)
    .mockRejectedValueOnce(new ApiError("权限已撤回", 403, "permission_denied"));
  const { result } = renderHook(useOrganizationRules);
  await waitFor(() => expect(result.current.rules).toEqual(rules));
  act(() => result.current.reload());
  await waitFor(() => expect(result.current.failure?.status).toBe(403));
  expect(result.current.rules).toBeNull();
});
