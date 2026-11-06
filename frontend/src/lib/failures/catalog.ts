import copy from "./copy.json";
import type { Failure, FailureContext, FailureFamily, FailurePresentation } from "./types";

export const failureCopy = copy;
export const failureIllustrations: Record<FailureFamily, string> = Object.fromEntries(
  Object.keys(copy).map((family) => [family, `/failures/${family}.png`]),
) as Record<FailureFamily, string>;

const configurationCodes = new Set([
  "model_not_configured",
  "model_credentials_unavailable",
  "tool_credentials_unavailable",
  "embedding_not_configured",
  "embedding_model_unsupported",
  "sandbox_not_ready",
  "skill_not_ready",
  "agent_inactive",
  "upstream_auth_failed",
  "upstream_forbidden",
  "tool_auth_required",
  "tool_permission_denied",
  "tool_catalog_changed",
  "model_configuration_changed",
  "skill_access_revoked",
  "tool_access_revoked",
  "knowledge_index_outdated",
  "knowledge_vector_not_ready",
  "skill_source_missing",
  "configuration_revision_conflict",
  "rules_revision_conflict",
]);
const connectionCodes = new Set([
  "client_connection_failed",
  "backend_unavailable",
  "client_stream_disconnected",
  "tool_connection_failed",
  "tool_connection_timeout",
  "tool_dns_failed",
  "tool_upstream_failed",
  "stdio_session_closed",
  "upstream_unavailable",
  "upstream_stream_error",
  "embedding_unavailable",
]);
const waitingCodes = new Set([
  "rate_limited",
  "run_capacity_exceeded",
  "subscription_limit",
  "embedding_rate_limited",
  "sandbox_capacity_exceeded",
  "stdio_capacity_exhausted",
  "upstream_rate_limited",
  "run_timeout",
  "queue_timeout",
  "client_timeout",
  "client_submission_unknown",
  "agent_budget_exceeded",
  "context_limit_exceeded",
  "output_limit_exceeded",
  "knowledge_build_timeout",
  "knowledge_build_busy",
]);

export function failureFamily(failure: Failure): FailureFamily {
  if (failure.code === "page_not_found") return "not-found";
  if (
    [
      "permission_denied",
      "agent_edit_denied",
      "authentication_required",
      "invalid_credentials",
    ].includes(failure.code)
  )
    return "access";
  if (failure.code === "invalid_origin") return "configuration";
  if (configurationCodes.has(failure.code)) return "configuration";
  if (connectionCodes.has(failure.code) || failure.source === "network") return "connection";
  if (waitingCodes.has(failure.code)) return "waiting";
  if (failure.source === "run") return "service";
  if (failure.status === 404) return "not-found";
  if (failure.status === 401 || failure.status === 403) return "access";
  if (failure.status === 429 || failure.status === 408 || failure.status === 504) return "waiting";
  if (failure.status === 502) return "connection";
  if ([400, 409, 413, 415, 422].includes(failure.status ?? 0)) return "configuration";
  return "service";
}

const resourceTitles = {
  agent: "没找到这位数字员工",
  evaluation: "没找到这条考核记录",
  skill: "没找到这个技能",
  knowledge: "没找到这个知识库",
  document: "没找到这份文档",
  conversation: "没找到这条对话记录",
  connection: "没找到这项连接",
  page: copy["not-found"].title,
};

export function presentFailure(failure: Failure, context: FailureContext): FailurePresentation {
  const family = failureFamily(failure);
  const base = copy[family];
  let title = base.title;
  let description = failure.message || base.description;
  if (family === "not-found" && context.operation === "initial-read") {
    title = resourceTitles[context.resource ?? "page"];
    description = "当前链接没有对应的可访问内容。内容可能已移除，或当前账号无法查看。";
  }
  if (context.operation === "mutation") {
    title = family === "not-found" ? "操作关联的内容已无法访问" : "这次操作未能完成";
    if (context.outcome === "unknown") {
      title = "还无法确认是否提交成功";
      description = "请先检查服务器结果，再决定是否重试。";
    }
  } else if (context.operation === "refresh" && context.hasUsableData) {
    title = "暂时无法更新";
    description = `当前显示的是此前读取的内容。${description}`;
  }
  if (
    failure.code === "configuration_revision_conflict" ||
    failure.code === "rules_revision_conflict"
  )
    title = "这份配置已被更新";
  if (failure.code === "client_notice") title = "请检查当前内容";
  if (failure.source === "run") title = "这次执行未能完成";
  return {
    family: context.outcome === "unknown" ? "waiting" : family,
    title,
    description,
    status: failure.status && failure.status >= 400 ? failure.status : null,
    displayCode:
      failure.status && failure.status >= 400
        ? String(failure.status)
        : failure.code === "page_not_found"
          ? "404"
          : null,
    code: failure.code,
    requestId: failure.requestId,
    retryAt: failure.retryAt,
  };
}
