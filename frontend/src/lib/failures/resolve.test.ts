import { describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/http";
import { clientFailure, mutationOutcome, resolveFailure, toFailure } from "./resolve";

describe("failure facts and presentation policy", () => {
  it("preserves structured API metadata without inventing an HTTP status", () => {
    expect(
      toFailure(new ApiError("稍后再试", 503, "database_busy", { requestId: "r-1", retryAt: 123 })),
    ).toMatchObject({
      source: "http",
      status: 503,
      code: "database_busy",
      requestId: "r-1",
      retryAt: 123,
    });
    expect(toFailure(clientFailure("permission_denied", "无权访问"))?.status).toBeNull();
  });
  it("keeps cancellations silent and unknown exception values private", () => {
    expect(toFailure(new DOMException("cancelled", "AbortError"))).toBeNull();
    expect(toFailure(new Error("secret SQL/password"))?.message).not.toContain("secret");
  });
  it("shows a logical SPA 404 without fabricating an HTTP response", () => {
    const fact = clientFailure("page_not_found", "请核对地址");
    const view = resolveFailure(fact, { operation: "initial-read", resource: "page" });
    expect(fact).toMatchObject({ source: "client", status: null });
    expect(view).toMatchObject({ family: "not-found", status: null, displayCode: "404" });
    expect(
      resolveFailure(clientFailure("client_unknown", "稍后再试"), { operation: "render" }),
    ).toMatchObject({ status: null, displayCode: null });
  });
  it("treats the same missing reference differently during detail reads and writes", () => {
    const fact = toFailure(new ApiError("技能不存在", 404, "skill_not_found"))!;
    expect(resolveFailure(fact, { operation: "initial-read", resource: "skill" }).title).toBe(
      "没找到这个技能",
    );
    expect(resolveFailure(fact, { operation: "mutation" }).title).toBe("操作关联的内容已无法访问");
  });
  it("puts return first for a missing resource, and filters blind configuration retries", () => {
    const actions = [
      { kind: "retry" as const, label: "重新加载", onClick: vi.fn() },
      { kind: "return" as const, label: "返回列表", href: "/skills" },
    ];
    expect(
      resolveFailure(
        toFailure(new ApiError("不存在", 404))!,
        { operation: "initial-read" },
        actions,
      ).actions[0].kind,
    ).toBe("return");
    const config = toFailure(new ApiError("检查凭证", 503, "model_credentials_unavailable"))!;
    expect(resolveFailure(config, { operation: "initial-read" }, actions)).toMatchObject({
      family: "configuration",
      actions: [actions[1]],
    });
  });
  it("does not turn a Run provider authentication failure into website access loss", () => {
    const view = resolveFailure(
      { source: "run", status: null, code: "upstream_auth_failed", message: "检查大脑配置" },
      { operation: "subscription" },
    );
    expect(view.family).toBe("configuration");
    expect(view.status).toBeNull();
  });
  it("requires reconciliation for an unknown write instead of replaying it", () => {
    const fact = toFailure(new ApiError("连接未建立", 0, "client_connection_failed"))!;
    expect(mutationOutcome(fact)).toBe("unknown");
    const retry = vi.fn(),
      reconcile = vi.fn();
    const result = resolveFailure(fact, { operation: "mutation", outcome: "unknown" }, [
      { label: "重试", kind: "retry", onClick: retry },
      { label: "检查结果", kind: "reconcile", onClick: reconcile },
    ]);
    expect(result.actions.map((action) => action.kind)).toEqual(["reconcile"]);
    expect(retry).not.toHaveBeenCalled();
    expect(reconcile).not.toHaveBeenCalled();
  });
  it("does not let malformed diagnostic metadata crash rendering", () => {
    const fact = toFailure({
      source: "http",
      status: {},
      code: "internal_error",
      message: "请重试",
      requestId: {},
      retryAt: "tomorrow",
      issues: [{ path: null, message: {} }],
    });
    expect(fact).toMatchObject({
      status: null,
      requestId: undefined,
      retryAt: undefined,
      issues: [],
    });
  });
  it("keeps an explicit configuration rejection distinct from an unknown write", () => {
    const fact = toFailure(new ApiError("请先配置嵌入模型", 503, "embedding_not_configured"))!;
    expect(mutationOutcome(fact)).toBe("rejected");
    expect(
      resolveFailure(fact, { operation: "mutation", outcome: mutationOutcome(fact) }).family,
    ).toBe("configuration");
  });
});
