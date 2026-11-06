import { request } from "./http";
import type { FileRef } from "./files";

export type Conversation = {
  id: string;
  agent_id: string;
  agent_name: string;
  owner_user_id: string;
  title: string;
  version: number;
  active_response_id: string | null;
  last_response_id: string | null;
  matched_response_id?: string | null;
  latest_response?: {
    id: string;
    status: ReplyStatus;
    acceptance: "pending" | "accepted" | "failed" | null;
  } | null;
  created_at: string;
  updated_at: string;
};
export type ConversationStats = { completed_rounds: number };
export const getConversationStats = (agentId: string, signal?: AbortSignal) =>
  request<ConversationStats>(`conversations/stats?agent_id=${encodeURIComponent(agentId)}`, {
    signal,
  });

export type ReplyStatus =
  "queued" | "running" | "cancelling" | "succeeded" | "failed" | "cancelled" | "interrupted";
/** 后端已选好的助手回复；页面无需解释 SDK 模型轮或工具请求。 */
export type Reply = {
  files?: FileRef[];
  id: string;
  conversation_id: string;
  sequence: number;
  role: "assistant";
  reply_to_message_id: string;
  retry_of_response_id?: string | null;
  version: number;
  status: ReplyStatus;
  acceptance?: "pending" | "accepted" | "failed" | null;
  acceptance_error?: string | null;
  content: string;
  content_state: "empty" | "draft" | "complete" | "partial";
  steps: ReplyStep[];
  usage: {
    input_tokens: number | null;
    output_tokens: number | null;
    total_tokens: number | null;
  } | null;
  error: { code: string; message: string } | null;
  can_retry: boolean;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  finished_at: string | null;
  /** 同一读取事务中的对话摘要；用于独立合并作用域版本。 */
  scope?: Conversation;
};
export type UserMessage = {
  files?: FileRef[];
  id: string;
  conversation_id: string;
  sequence: number;
  role: "user";
  content: string;
  created_at: string;
  updated_at: string;
};
export type ResponseSnapshot = { conversation: Conversation; response: Reply };
export type AcceptedSubmission = ResponseSnapshot & {
  client_request_id: string;
  input_message: UserMessage;
};
export type ConversationSnapshot = {
  conversation: Conversation;
  agent: { id: string; name: string; avatar_id: string };
  messages: WireMessagePage;
  question_count: number;
  latest_question_id: string | null;
};
/** 页面消息行可以包含操作状态；它不是后端数据表。 */
export type ChatMessage = {
  files?: FileRef[];
  id: string;
  conversation_id: string;
  sequence: number;
  role: "user" | "assistant";
  content: string;
  published: boolean;
  run: Reply | null;
  created_at: string;
  updated_at: string;
};
export type MessagePage = {
  items: ChatMessage[];
  next_before_sequence: number | null;
  has_more: boolean;
  next_after_sequence?: number | null;
};
type WireMessagePage = Omit<MessagePage, "items"> & { items: (UserMessage | Reply)[] };
export function readPage(page: WireMessagePage): MessagePage {
  return {
    ...page,
    items: page.items.map((message) => ({
      ...message,
      published: message.role === "user" || isPublished(message),
      run: message.role === "assistant" ? message : null,
    })),
  };
}
async function readMessagePage(path: string, options?: { signal?: AbortSignal }) {
  return readPage(await request<WireMessagePage>(path, options));
}
export const scopedReply = (snapshot: ResponseSnapshot): Reply => ({
  ...snapshot.response,
  scope: snapshot.conversation,
});
export const isActive = (status?: string | null) =>
  ["queued", "running", "cancelling"].includes(status ?? "");
export const isObserving = (reply?: Reply | null) =>
  !!reply && (isActive(reply.status) || reply.acceptance === "pending");
export const isPublished = (reply: Reply) =>
  !isActive(reply.status) && reply.acceptance !== "pending" && reply.acceptance !== "failed";
export const statusLabel: Record<ReplyStatus, string> = {
  queued: "等待执行",
  running: "执行中",
  cancelling: "正在停止",
  succeeded: "已完成",
  failed: "执行失败",
  cancelled: "已停止",
  interrupted: "执行中断",
};
export const getSnapshot = (id: string, signal?: AbortSignal) =>
  request<ConversationSnapshot>(`conversations/${id}/snapshot`, { signal });
export type ConversationQuestion = {
  id: string;
  sequence: number;
  number: number;
  preview: string;
  created_at: string;
};
export type QuestionPage = {
  items: ConversationQuestion[];
  total: number;
  next_after_sequence: number | null;
  /** 当前问题的全局轮次；不受搜索或目录分页限制。 */
  anchor?: ConversationQuestion | null;
};

/** 一个问题最新一次执行的公开短文本快照；不携带执行步骤。 */
export type QuestionPreview = {
  question_id: string;
  question: string;
  answer: string;
  response_id: string;
  version: number;
  status: ReplyStatus;
};

/** 对话列表的偏移分页结果；总数由后端统计。 */
export type ConversationPage = {
  /** 当前页对话摘要。 */
  items: Conversation[];
  /** 符合查询条件的对话总数，不是当前页长度。 */
  total: number;
  /** 当前页相对完整结果集的起始偏移。 */
  offset: number;
  /** 当前分页采用的条数上限。 */
  limit: number;
};
export function getConversations(
  {
    agentId,
    offset = 0,
    limit = 20,
    q = "",
    status = "",
  }: {
    agentId?: string;
    offset?: number;
    limit?: number;
    q?: string;
    status?: string;
  } = {},
  signal?: AbortSignal,
) {
  const query = new URLSearchParams({ offset: String(offset), limit: String(limit) });
  if (agentId) query.set("agent_id", agentId);
  if (q) query.set("q", q);
  if (status) query.set("status", status);
  return request<ConversationPage>(`conversations?${query}`, { signal });
}
export function getMessages(
  id: string,
  before?: number | null,
  signal?: AbortSignal,
  options: { after?: number; around?: string; limit?: number } = {},
) {
  const query = new URLSearchParams();
  if (before) query.set("before_sequence", String(before));
  if (options.after) query.set("after_sequence", String(options.after));
  if (options.around) query.set("around_message_id", options.around);
  if (options.limit !== undefined) query.set("limit", String(options.limit));
  return readMessagePage(`conversations/${id}/messages${query.size ? `?${query}` : ""}`, {
    signal,
  });
}
export function getQuestions(
  id: string,
  q = "",
  after?: number | null,
  signal?: AbortSignal,
  options: { anchor?: string; limit?: number; startNumber?: number } = {},
) {
  const query = new URLSearchParams({ q });
  if (after) query.set("after_sequence", String(after));
  if (options.anchor) query.set("anchor_message_id", options.anchor);
  if (options.limit) query.set("limit", String(options.limit));
  if (options.startNumber !== undefined) query.set("start_number", String(options.startNumber));
  return request<QuestionPage>(`conversations/${id}/questions?${query}`, { signal });
}
export const responsePath = (conversationId: string, responseId: string) =>
  `conversations/${conversationId}/responses/${responseId}`;
export const getResponse = async (
  conversationId: string,
  responseId: string,
  signal?: AbortSignal,
) =>
  scopedReply(
    await request<ResponseSnapshot>(responsePath(conversationId, responseId), { signal }),
  );
export const getQuestionPreview = (id: string, questionId: string, signal?: AbortSignal) =>
  request<QuestionPreview>(`conversations/${id}/questions/${questionId}/preview`, { signal });
export const sendMessage = async (
  id: string | null,
  content: string,
  clientRequestId: string,
  selectedSkillIds: readonly string[] = [],
  agentId?: string,
  fileIds?: readonly string[],
) =>
  scopedReply(
    await request<AcceptedSubmission>(
      id === null ? "conversations" : `conversations/${id}/messages`,
      {
        method: "POST",
        body: JSON.stringify({
          content,
          client_request_id: clientRequestId,
          selected_skill_ids: selectedSkillIds,
          ...(agentId ? { agent_id: agentId } : {}),
          ...(fileIds?.length ? { file_ids: fileIds } : {}),
        }),
      },
    ),
  );
export const stopResponse = async (conversationId: string, responseId: string) =>
  scopedReply(
    await request<ResponseSnapshot>(responsePath(conversationId, responseId) + "/stop", {
      method: "POST",
      body: "{}",
    }),
  );
export const retryResponse = async (
  conversationId: string,
  responseId: string,
  clientRequestId: string,
) =>
  scopedReply(
    await request<AcceptedSubmission>(responsePath(conversationId, responseId) + "/retry", {
      method: "POST",
      body: JSON.stringify({ client_request_id: clientRequestId }),
    }),
  );
export const answerContent = (reply: Reply): string => reply.content;
export function activityLabel(reply: Reply): string {
  if (reply.acceptance === "pending") return "执行已完成，正在保存回复";
  if (reply.acceptance === "failed") return "执行已完成，回复未保存";
  if (reply.status !== "running") return statusLabel[reply.status];
  const action = reply.steps.findLast((item) => item.status === "running");
  if (action?.kind === "tool_call")
    return action.safe_details.tool === "read_file"
      ? action.skill_id
        ? "正在读取技能"
        : "正在读取文件"
      : "正在执行工具";
  return reply.content_state === "draft" ? "生成中" : "正在处理";
}
export type ReplyStep = {
  /** 平台步骤 ID，页面以此作为稳定的行标识。 */
  id: string;
  /** 所属平台执行 ID。 */
  run_id: string;
  /** 本次执行内由持久化层分配的递增序号，不是 SDK 的 langgraph_step。 */
  sequence: number;
  /** 执行内用于步骤去重和收尾的稳定键，例如 model:1 或 tool:调用标识。 */
  action_key: string;
  /** SDK 逻辑调用键；恢复重放产生新的动作身份。 */
  call_key: string;
  /** 发起此工具请求的模型动作，无法确认时为 null。 */
  parent_action_id: string | null;
  /** 动作类型：model_call、skill_activation、tool_call、validation 或预留的 knowledge。 */
  kind: string;
  /** 动作状态：running、succeeded、failed、cancelled 或 interrupted。 */
  status: string;
  /** 已确认关联的技能 ID；动作没有技能关联时为 null。 */
  skill_id: string | null;
  /** 宿主允许公开的元数据；读取具体字段前需检查类型，不能视为任意工具原始结果。 */
  safe_details: Record<string, unknown>;
  /** 模型步骤保留的本轮文字；中间轮次不自动成为最终回答。 */
  output_text: string;
  /** 模型步骤保留的标准思考内容；由模型协议决定是否提供。 */
  reasoning_text: string;
  /** 本步骤思考展示是否被截断。 */
  reasoning_truncated: boolean;
  /** 关联结果的可选引用；不能直接当作可访问 URL。 */
  result_ref: string | null;
  /** 动作失败的稳定错误码；没有已记录错误时为 null。 */
  error_code: string | null;
  /** 动作开始时间，采用 ISO 8601 格式。 */
  started_at: string;
  /** 动作结束时间；running 时为 null。 */
  finished_at: string | null;
};
