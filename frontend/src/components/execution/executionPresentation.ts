import type { ExecutionAction, ExecutionTrace } from "@/lib/api/execution";

export const actionKinds: Record<string, string> = {
  model_call: "模型调用",
  tool_call: "工具调用",
  knowledge: "知识读取",
  skill_activation: "加载技能",
  validation: "结果校验",
};
export function actionTitle(action: ExecutionAction) {
  const details = action.safe_details;
  return action.kind === "model_call"
    ? `${details.purpose === "summary" ? "上下文摘要" : "模型调用"}${typeof details.round === "number" ? ` · 第 ${details.round} 次` : ""}`
    : String(details.tool || details.name || actionKinds[action.kind] || "执行动作");
}
export function failedActions(data: ExecutionTrace) {
  return (
    data.failures?.items ??
    data.actions.items.filter((item) => item.status === "failed" || item.error_code)
  );
}
export function isErrorEvent(line: NonNullable<ExecutionTrace["logs"]>["items"][number]) {
  return !!line.error_code || ["ERROR", "CRITICAL"].includes(line.level.toUpperCase());
}
