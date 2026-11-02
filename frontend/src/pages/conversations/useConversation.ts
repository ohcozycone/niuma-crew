import { useContext, useSyncExternalStore } from "react";
import { ConversationContext } from "./conversationContext";

/** 读取当前作用域的会话与消息顺序；网络生命周期由 Provider 统一持有。 */
export function useConversation() {
  const store = useContext(ConversationContext);
  if (!store) throw new Error("useConversation 必须在 ConversationProvider 内调用。");
  return useSyncExternalStore(store.subscribe, store.getConversation, store.getConversation);
}
