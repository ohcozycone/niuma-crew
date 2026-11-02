import { useCallback, useContext, useSyncExternalStore } from "react";
import { ConversationContext } from "./conversationContext";

/** 读取指定消息及绑定其 ID 的操作；显式 null/未加载 ID 返回空消息，不发请求。 */
export function useMessage(messageId: string | null) {
  const store = useContext(ConversationContext);
  if (!store) throw new Error("useMessage 必须在 ConversationProvider 内调用。");
  if (messageId === undefined)
    throw new Error("useMessage 必须显式提供消息 ID；没有目标时传 null。");
  const getSnapshot = useCallback(() => store.getMessage(messageId), [store, messageId]);
  return useSyncExternalStore(store.subscribe, getSnapshot, getSnapshot);
}
