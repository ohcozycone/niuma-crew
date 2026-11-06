import type { ExecutionAction } from "@/lib/api/execution";

export const asRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
export const tokenCount = (value: unknown): number | undefined =>
  typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : undefined;
export const formatCount = (value: unknown) =>
  tokenCount(value)?.toLocaleString("zh-CN") ?? "未报告";
export const percentage = (part: number | undefined, whole: number | undefined) =>
  part != null && whole != null && whole > 0 ? `${((part / whole) * 100).toFixed(1)}%` : undefined;
export function elapsedSeconds(start: string | null, finish: string | null) {
  if (!start || !finish) return undefined;
  const elapsed = (Date.parse(finish) - Date.parse(start)) / 1000;
  return Number.isFinite(elapsed) && elapsed >= 0 ? elapsed : undefined;
}
export function modelUsage(action: ExecutionAction) {
  const usage = asRecord(action.metrics?.usage ?? action.safe_details.usage);
  return {
    input: tokenCount(usage.input_tokens),
    output: tokenCount(usage.output_tokens),
    total: tokenCount(usage.total_tokens),
    reasoning: tokenCount(usage.reasoning_tokens ?? asRecord(usage.output_token_details).reasoning),
  };
}
