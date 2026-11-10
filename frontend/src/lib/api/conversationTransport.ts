import * as api from "./conversations";
import { request } from "./http";
import type { FileRef } from "./files";

/** 一次提交时固定的用户输入，不包含模型上下文或凭证。 */
export type ConversationInput = {
  files?: readonly FileRef[];
  /** 本次输入正文。 */
  content: string;
  /** 显式选择的技能；省略或空数组表示按需使用。 */
  selectedSkillIds?: readonly string[];
};

/** 会话所需的网络操作；不依赖 React、路由或身份 Provider。 */
export type ConversationTransport = {
  /** 本地新草稿的创建参数；已有会话省略。 */
  create?: { agentId: string };
  getSnapshot: typeof api.getSnapshot;
  getMessages: typeof api.getMessages;
  getResponse: typeof api.getResponse;
  cancel: typeof api.stopResponse;
  retry: typeof api.retryResponse;
  /** 同键重发必须使用相同的输入及创建参数。 */
  send: (id: string | null, input: ConversationInput, key: string) => Promise<api.Reply>;
  /** 只读核对幂等请求，未接受时返回 null。 */
  findRequest: (id: string | null, key: string, signal?: AbortSignal) => Promise<api.Reply | null>;
  /** 建立一次观察连接；关闭连接不取消执行。 */
  subscribe: (
    conversationId: string,
    runId: string,
    listener: {
      snapshot: (run: api.Reply) => void;
      disconnected: () => void;
      invalid: () => void;
      revoked: () => void;
    },
  ) => () => void;
};

/** 将当前 REST 与持久化 SSE 接口交给会话 hook 使用。 */
export function createConversationTransport(
  options: Pick<ConversationTransport, "create"> = {},
): ConversationTransport {
  return {
    ...options,
    getSnapshot: api.getSnapshot,
    getMessages: api.getMessages,
    getResponse: api.getResponse,
    cancel: api.stopResponse,
    retry: api.retryResponse,
    send: (id, input, key) =>
      api.sendMessage(
        id,
        input.content,
        key,
        input.selectedSkillIds ?? [],
        options.create?.agentId,
        input.files?.map((file) => file.id),
      ),
    async findRequest(id, key, signal) {
      const submission = await request<api.AcceptedSubmission | null>(
        id === null ? `conversations/requests/${key}` : `conversations/${id}/requests/${key}`,
        { signal },
      );
      return submission ? api.scopedReply(submission) : null;
    },
    subscribe(conversationId, runId, listener) {
      const source = new EventSource(`/api/${api.responsePath(conversationId, runId)}/events`);
      const receive = (event: MessageEvent) => {
        try {
          const value = api.scopedReply(JSON.parse(event.data) as api.ResponseSnapshot);
          if (
            value.id !== runId ||
            !Number.isSafeInteger(value.version) ||
            value.version < 0 ||
            typeof value.conversation_id !== "string" ||
            !Array.isArray(value.steps) ||
            !Object.hasOwn(api.statusLabel, value.status)
          )
            throw new Error("Invalid snapshot");
          listener.snapshot(value);
        } catch {
          listener.invalid();
        }
      };
      source.addEventListener("response.snapshot", receive as EventListener);
      source.addEventListener("response.finished", receive as EventListener);
      source.addEventListener("access.revoked", () => {
        // 空事件同时涵盖认证失效和撤权；由 auth/me 确认后再决定是否退出。
        source.close();
        window.dispatchEvent(new Event("auth:permissions-changed"));
        listener.revoked();
      });
      source.onerror = listener.disconnected;
      return () => source.close();
    },
  };
}
