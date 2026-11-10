import { createContext } from "react";
import type { ConversationStore } from "./conversationStore";

/** Context 只传稳定的会话实例，消息更新通过各自快照订阅。 */
export const ConversationContext = createContext<ConversationStore | null>(null);
