import { useMemo, useState } from "react";
import type { Reply } from "@/lib/api/conversations";

const pageSize = 100;

/** 读取一条助手消息对应 Reply 的已有步骤；分页仅改变本地视图，不发请求。 */
export function useStepPagination(run: Reply) {
  const [requestedOffset, setOffset] = useState(0);
  const total = run.steps.length;
  const offset = Math.min(requestedOffset, Math.max(0, Math.ceil(total / pageSize) - 1) * pageSize);
  const items = useMemo(() => run.steps.slice(offset, offset + pageSize), [run.steps, offset]);
  return { items, total, offset, setOffset, pageSize };
}
