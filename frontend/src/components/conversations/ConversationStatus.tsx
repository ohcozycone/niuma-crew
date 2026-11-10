import { Circle, CircleCheck, CircleX, LoaderCircle, PauseCircle } from "lucide-react";
import type { Conversation } from "@/lib/api/conversations";
import { statusLabel } from "@/lib/api/conversations";

export function ConversationStatus({ item }: { item: Conversation }) {
  const reply = item.latest_response;
  let label = "暂无回复",
    color = "text-text-muted",
    Icon = Circle;
  if (reply?.acceptance === "failed") {
    label = "保存失败";
    color = "text-danger";
    Icon = CircleX;
  } else if (reply?.acceptance === "pending") {
    label = "保存中";
    color = "text-info";
    Icon = LoaderCircle;
  } else if (reply?.status === "succeeded") {
    label = "已回复";
    color = "text-success";
    Icon = CircleCheck;
  } else if (reply) {
    label = statusLabel[reply.status];
    if (["queued", "running", "cancelling"].includes(reply.status)) {
      color = "text-info";
      Icon = LoaderCircle;
    } else if (["failed", "interrupted"].includes(reply.status)) {
      color = "text-danger";
      Icon = CircleX;
    } else Icon = PauseCircle;
  } else if (item.active_response_id) {
    label = "执行中";
    color = "text-info";
    Icon = LoaderCircle;
  }
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap text-xs ${color}`}>
      <Icon size={14} aria-hidden="true" />
      {label}
    </span>
  );
}
