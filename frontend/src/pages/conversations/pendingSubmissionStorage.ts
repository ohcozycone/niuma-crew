import type { PendingCommand } from "./conversationState";

/** 当前会话在本标签页的接受确认和待核对命令。 */
export type ConversationSession = {
  persisted: boolean;
  pending: PendingCommand | null;
  conversationId?: string | null;
};

export function readConversationSession(key?: string): ConversationSession {
  try {
    const value = JSON.parse(key ? (sessionStorage.getItem(key) ?? "null") : "null");
    const pending = value?.pending;
    return {
      persisted: value?.persisted === true,
      conversationId: typeof value?.conversationId === "string" ? value.conversationId : null,
      pending:
        pending &&
        typeof pending.key === "string" &&
        (typeof pending.retryId === "string" || typeof pending.input?.content === "string")
          ? pending
          : null,
    };
  } catch {
    return { persisted: false, pending: null };
  }
}

export function saveConversationSession(key: string | undefined, value: ConversationSession) {
  if (!key) return;
  try {
    sessionStorage.setItem(key, JSON.stringify({ ...value, version: 3 }));
  } catch {
    /* 存储不可用时仍可在当前页面交互。 */
  }
}
