import { useLayoutEffect, useState, type ReactNode } from "react";
import { useConversationController } from "@/pages/conversations/useConversationController";
import { ConversationContext } from "./conversationContext";
import { createConversationStore } from "./conversationStore";

type Props = Parameters<typeof useConversationController>[0] & { children: ReactNode };

function ConversationScope({ children, ...options }: Props) {
  const model = useConversationController(options);
  const [store] = useState(() => createConversationStore(model));
  useLayoutEffect(() => {
    store.activate();
    return () => store.deactivate();
  }, [store]);
  // 只发布已提交的渲染；被挂起或丢弃的渲染不能修改订阅者读到的快照。
  useLayoutEffect(() => store.publish(model), [store, model]);
  return <ConversationContext.Provider value={store}>{children}</ConversationContext.Provider>;
}

/** 当前会话页的唯一加载、提交与订阅作用域；身份/会话切换销毁旧实例。 */
export function ConversationProvider(props: Props) {
  return <ConversationScope key={`${props.id}:${props.storageKey ?? ""}`} {...props} />;
}
