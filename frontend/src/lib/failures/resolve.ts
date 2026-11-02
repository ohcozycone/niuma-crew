import { ApiError } from "@/lib/api/http";
import { failureFamily, presentFailure } from "./catalog";
import type { Failure, FailureAction, FailureContext } from "./types";

export function clientFailure(code: string, message: string): Failure {
  return { source: "client", status: null, code, message };
}

function publicFacts(value: Record<string, unknown>): Failure | null {
  if (
    typeof value.source !== "string" ||
    !["http", "network", "client", "run"].includes(value.source) ||
    typeof value.code !== "string" ||
    typeof value.message !== "string"
  )
    return null;
  const issues = Array.isArray(value.issues)
    ? value.issues
        .flatMap((issue: unknown) => {
          if (
            !issue ||
            typeof issue !== "object" ||
            !("path" in issue) ||
            !("message" in issue) ||
            !Array.isArray(issue.path) ||
            typeof issue.message !== "string"
          )
            return [];
          return [
            {
              path: issue.path.filter(
                (part: unknown): part is string | number =>
                  typeof part === "string" ||
                  (typeof part === "number" && Number.isSafeInteger(part)),
              ),
              message: issue.message.slice(0, 300),
            },
          ];
        })
        .slice(0, 50)
    : undefined;
  return {
    source: value.source as Failure["source"],
    status:
      typeof value.status === "number" &&
      Number.isInteger(value.status) &&
      value.status >= 100 &&
      value.status <= 599
        ? value.status
        : null,
    code: value.code.slice(0, 128),
    message: value.message.slice(0, 4000),
    requestId:
      typeof value.requestId === "string" && /^[A-Za-z0-9._-]{1,64}$/.test(value.requestId)
        ? value.requestId
        : undefined,
    retryAt:
      typeof value.retryAt === "number" && Number.isSafeInteger(value.retryAt) && value.retryAt >= 0
        ? value.retryAt
        : undefined,
    issues,
  };
}

/** Explicit local strings are compatibility notices; unknown Error values stay private. */
export function toFailure(error: unknown): Failure | null {
  if (error == null || error === "") return null;
  if (error instanceof ApiError)
    return publicFacts({
      source: error.source,
      status: error.status || null,
      code: error.code ?? "http_error",
      message: error.message,
      requestId: error.requestId,
      retryAt: error.retryAt,
      issues: error.issues,
    });
  if (typeof error === "object") {
    const facts = publicFacts(error as Record<string, unknown>);
    if (facts) return facts;
  }
  if (error instanceof Error && error.name === "AbortError") return null;
  if (error instanceof Error && error.name === "TimeoutError")
    return clientFailure("client_timeout", "服务响应超时，请重新检查。");
  if (typeof error === "string") return clientFailure("client_notice", error);
  return clientFailure("client_unknown", "当前操作暂时无法完成，请重新检查。");
}

export function failureMessage(error: unknown): string {
  return toFailure(error)?.message ?? "";
}

/** A transport failure after a write cannot prove whether the write committed. */
export function mutationOutcome(failure: Failure | null): "rejected" | "unknown" {
  if (failure?.source === "http" && failureFamily(failure) === "configuration") return "rejected";
  return failure &&
    (failure.source === "network" ||
      (failure.status ?? 0) >= 500 ||
      ["client_timeout", "client_invalid_response", "client_unknown"].includes(failure.code))
    ? "unknown"
    : "rejected";
}

export function resolveFailure(
  failure: Failure,
  context: FailureContext,
  actions: readonly FailureAction[] = [],
) {
  const presentation = presentFailure(failure, context);
  const available = actions.filter(
    (action) =>
      (action.href || action.onClick) &&
      !(["configuration", "access"].includes(presentation.family) && action.kind === "retry") &&
      !(
        context.operation === "mutation" &&
        context.outcome === "unknown" &&
        action.kind === "retry"
      ),
  );
  const preferred =
    presentation.family === "not-found"
      ? "return"
      : presentation.family === "configuration"
        ? "configure"
        : "retry";
  available.sort((a, b) => Number(b.kind === preferred) - Number(a.kind === preferred));
  return { ...presentation, actions: available };
}
