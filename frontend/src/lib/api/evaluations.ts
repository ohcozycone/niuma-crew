import { request } from "./http";

export type EvaluationSuite = {
  id: string;
  name: string;
  category: string;
  total: number;
  version: string;
  grader_version: string;
  scope: string;
  source_url: string;
};
export type EvaluationBatch = {
  id: string;
  agent_id: string;
  name: string;
  suite_id: string;
  suite_version: string;
  grader_version: string;
  configuration_hash: string;
  agent_revision: number;
  model_id: string;
  scope: string;
  status: string;
  total: number;
  completed: number;
  scored: number;
  passed: number;
  failed: number;
  errors: number;
  cancelled: number;
  pass_rate: number | null;
  error_code: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};
export type EvaluationCase = {
  id: string;
  ordinal: number;
  question_id: string;
  status: string;
  question: string;
  functions: unknown[];
  expected: unknown[] | null;
  answer: string | null;
  grading: { valid: boolean; error: string[]; error_type: string } | null;
  run_id: string | null;
  run_status: string | null;
  error_code: string | null;
  usage: unknown;
};
export type EvaluationPage<T> = { items: T[]; total: number; offset: number; limit: number };
export type EvaluationReport = {
  batch: EvaluationBatch;
  cases: EvaluationPage<EvaluationCase>;
};
export const activeEvaluation = (status: string) =>
  ["queued", "running", "cancelling"].includes(status);
export const evaluationSuites = (signal?: AbortSignal) =>
  request<EvaluationSuite[]>("evaluations/suites", { signal });
export const evaluationList = (agentId: string, offset: number, signal?: AbortSignal) =>
  request<EvaluationPage<EvaluationBatch>>(
    `evaluations?${new URLSearchParams({ agent_id: agentId, offset: String(offset), limit: "20" })}`,
    { signal },
  );
export const evaluationReport = (id: string, offset: number, signal?: AbortSignal) =>
  request<EvaluationReport>(`evaluations/${id}?offset=${offset}&limit=20`, { signal });
export const createEvaluation = (agentId: string, suiteId: string, count: number, key: string) =>
  request<EvaluationBatch>("evaluations", {
    method: "POST",
    body: JSON.stringify({
      agent_id: agentId,
      suite_id: suiteId,
      sample_count: count,
      client_request_id: key,
    }),
  });
export const cancelEvaluation = (id: string) =>
  request<EvaluationBatch>(`evaluations/${id}/cancel`, { method: "POST" });
