import type { Failure } from "@/lib/failures/types";

type ErrorMetadata = Pick<Failure, "requestId" | "retryAt" | "issues"> & {
  source?: Failure["source"];
};

export class ApiError extends Error {
  readonly source: Failure["source"];
  readonly requestId?: string;
  readonly retryAt?: number;
  readonly issues?: Failure["issues"];
  constructor(
    message: string,
    public status: number,
    public code?: string,
    metadata: ErrorMetadata = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.source = metadata.source ?? (status ? "http" : "network");
    this.requestId = metadata.requestId;
    this.retryAt = metadata.retryAt;
    this.issues = metadata.issues;
  }
}

export function retryDeadline(value: string | null, now = Date.now()): number | undefined {
  if (!value?.trim()) return;
  const text = value.trim();
  if (/^\d+$/.test(text)) {
    const seconds = Number(text);
    const deadline = now + seconds * 1000;
    return Number.isSafeInteger(seconds) && Number.isSafeInteger(deadline) ? deadline : undefined;
  }
  // Accept canonical HTTP dates, not Date.parse's permissive guesses or invalid days.
  if (
    !/^(Mon|Tue|Wed|Thu|Fri|Sat|Sun), \d{2} (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{4} \d{2}:\d{2}:\d{2} GMT$/.test(
      text,
    )
  )
    return;
  const deadline = Date.parse(text);
  return Number.isFinite(deadline) && new Date(deadline).toUTCString() === text
    ? Math.max(now, deadline)
    : undefined;
}
const validationFields: Record<string, string> = {
  content: "消息",
  name: "名称",
  avatar_id: "员工头像",
  skill_assignments: "技能装配",
  selected_skill_ids: "技能选择",
  expected_revision: "配置修订",
  configuration_schema: "装配参数规范",
  model_connection_id: "大脑配置",
  client_request_id: "提交标识",
  system_prompt: "工作指令",
};

function validationMessage(detail: unknown[]): string {
  const messages = detail.slice(0, 3).flatMap((issue) => {
    if (!issue || typeof issue !== "object") return [];
    const { loc, msg, type } = issue as { loc?: unknown; msg?: unknown; type?: unknown };
    if (typeof msg !== "string" || !msg.trim()) return [];
    const path = Array.isArray(loc) ? loc.filter((part) => part !== "body") : [];
    const field =
      validationFields[path.join(".")] ?? validationFields[String(path[0])] ?? "提交字段";
    const reason =
      type === "missing"
        ? "此项必填。"
        : type === "uuid_parsing" || type === "uuid_type"
          ? "标识格式无效，请重新选择。"
          : type === "string_type"
            ? "请输入文字。"
            : type === "string_too_short"
              ? "内容不能为空或过短。"
              : type === "extra_forbidden"
                ? "包含不支持的字段，请刷新页面后重试。"
                : msg.replace(/^Value error,\s*/, "").slice(0, 300);
    return [`${field}：${reason}`];
  });
  return [...new Set(messages)].join("\n") || "提交内容不符合要求，请检查必填字段。";
}

function validationIssues(detail: unknown[]): Failure["issues"] {
  return detail.slice(0, 50).flatMap((issue) => {
    if (!issue || typeof issue !== "object") return [];
    const { loc, msg } = issue as { loc?: unknown; msg?: unknown };
    if (!Array.isArray(loc) || typeof msg !== "string") return [];
    return [
      {
        path: loc.filter(
          (part): part is string | number =>
            (typeof part === "string" || typeof part === "number") && part !== "body",
        ),
        message: msg.replace(/^Value error,\s*/, "").slice(0, 300),
      },
    ];
  });
}

function transportError(error: unknown, signal?: AbortSignal | null): never {
  if (signal?.aborted) {
    if (signal.reason?.name === "TimeoutError")
      throw new ApiError("服务响应超时，请重新检查。", 0, "client_timeout", { source: "client" });
    if (error instanceof Error && error.name === "AbortError") throw error;
    throw new DOMException("操作已取消", "AbortError");
  }
  throw new ApiError("连接暂时未能建立，请稍后重新连接。", 0, "client_connection_failed", {
    source: "network",
  });
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/${path}`, {
      ...init,
      cache: "no-store",
      headers: { "Content-Type": "application/json", ...init.headers },
    });
  } catch (error) {
    transportError(error, init.signal);
  }
  const rawRequestId = response.headers.get("X-Request-ID");
  const requestId =
    rawRequestId && /^[A-Za-z0-9._-]{1,64}$/.test(rawRequestId) ? rawRequestId : undefined;
  if (!response.ok) {
    const body = await response.json().catch((error: unknown) => {
      if (init.signal?.aborted) transportError(error, init.signal);
      return null;
    });
    const detail = body?.detail;
    const message =
      typeof detail?.message === "string"
        ? detail.message
        : Array.isArray(detail)
          ? validationMessage(detail)
          : "操作失败，请稍后重试。";
    if (typeof window !== "undefined" && !path.startsWith("auth/")) {
      if (response.status === 401 && detail?.code === "authentication_required")
        window.dispatchEvent(new Event("auth:session-ended"));
      else if (response.status === 403 && detail?.code === "permission_denied")
        window.dispatchEvent(new Event("auth:permissions-changed"));
    }
    throw new ApiError(
      message,
      response.status,
      typeof detail?.code === "string" ? detail.code : undefined,
      {
        requestId,
        retryAt: retryDeadline(response.headers.get("Retry-After")),
        issues: Array.isArray(detail) ? validationIssues(detail) : undefined,
      },
    );
  }
  if (response.status === 204) return undefined as T;
  try {
    return (await response.json()) as T;
  } catch (error) {
    if (init.signal?.aborted) transportError(error, init.signal);
    throw new ApiError(
      "服务返回的内容暂时无法读取，请重新检查。",
      response.status,
      "client_invalid_response",
      { source: "client", requestId },
    );
  }
}
