import type { PendingCommand } from "./conversationState";

/** 当前会话在本标签页的接受确认和待核对命令。 */
export type ConversationSession = { persisted: boolean; pending: PendingCommand | null };

export function readConversationSession(key?: string): ConversationSession {
  try {
    const value = JSON.parse(key ? (sessionStorage.getItem(key) ?? "null") : "null");
    const pending = value?.pending;
    return {
      persisted: value?.persisted === true,
      pending:
        pending &&
        typeof pending.key === "string" &&
        (typeof pending.retryId === "string" || typeof pending.input?.content === "string")
          ? {
              ...pending,
              ...(pending.input && Object.hasOwn(pending.input, "work")
                ? { retiredInput: true }
                : {}),
              ...(value.version !== 2 && pending.retryId ? { legacyRetryTarget: true } : {}),
            }
          : null,
    };
  } catch {
    return { persisted: false, pending: null };
  }
}

export function saveConversationSession(key: string | undefined, value: ConversationSession) {
  if (!key) return;
  try {
    sessionStorage.setItem(key, JSON.stringify({ ...value, version: 2 }));
  } catch {
    /* 存储不可用时仍可在当前页面交互。 */
  }
}
