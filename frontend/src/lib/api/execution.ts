import { request } from "./http";

export type ExecutionAction = {
  id: string;
  sequence: number;
  action_key: string;
  parent_action_id: string | null;
  kind: string;
  status: string;
  safe_details: Record<string, unknown>;
  metrics?: {
    usage: {
      input_tokens?: number | null;
      output_tokens?: number | null;
      total_tokens?: number | null;
      reasoning_tokens?: number | null;
    };
    usage_source?: "response" | "action" | null;
    output_limit?: number | null;
    output_limit_field?: string | null;
  };
  output_text: string;
  reasoning_text: string;
  reasoning_truncated: boolean;
  error_code: string | null;
  started_at: string;
  finished_at: string | null;
};
export type ExecutionArtifact = {
  status: "available" | "restricted" | "not_collected" | "unavailable";
  size?: number;
  content_hash?: string;
  truncated?: boolean;
  document?: { schema_version: number; capture_stage: string; payload: Record<string, unknown> };
  preview?: string;
};
export type ExecutionTrace = {
  run: {
    id: string;
    agent_id: string;
    origin_kind: string;
    status: string;
    revision: number;
    error_code: string | null;
    started_at: string | null;
    finished_at: string | null;
    usage: unknown;
  };
  configuration: {
    agent_revision: number;
    agent_name?: string;
    model_id: string;
    schema_version: number;
  };
  context?: {
    question: string | null;
    input_message_id?: string;
    delivery: { status: string; error_code: string | null; content: string | null };
    attempts: { id: string; status: string }[];
  };
  can_inspect_inputs: boolean;
  actions: { items: ExecutionAction[]; total: number; offset: number; limit: number };
  failures?: { items: ExecutionAction[]; total: number };
  selected?: ExecutionAction & {
    request: ExecutionArtifact;
    response: ExecutionArtifact;
    saved_tool_feedback: unknown;
  };
  logs: {
    items: {
      time: string;
      level: string;
      event: string;
      action_key: string | null;
      error_code: string | null;
      error_type?: string | null;
      source?: string;
      frames?: string | null;
    }[];
    status: string;
    limit: number;
  } | null;
};
export function executionTrace(
  base: string,
  offset: number,
  actionId: string,
  signal: AbortSignal,
) {
  const query = new URLSearchParams({ offset: String(offset), limit: "100" });
  if (actionId) query.set("action_id", actionId);
  return request<ExecutionTrace>(`${base}/trace?${query}`, { signal });
}
export const executionEvidenceUrl = (base: string, action: string, direction: string) =>
  `/api/${base}/trace/actions/${action}/evidence/${direction}`;
