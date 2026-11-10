import { useIdentity } from "@/state/auth/useIdentity";
import { FailureNotice } from "@/components/failure/FailureNotice";
import type { ComponentProps } from "react";
import { ConversationComposer } from "./ConversationComposer";
import { useConversation } from "./useConversation";
import { useMessage } from "./useMessage";

type Props = Pick<
  ComponentProps<typeof ConversationComposer>,
  "agent" | "storageKey" | "acceptedInput"
>;

/** 编辑器读取会话末条消息的状态和操作。 */
export function ConversationControls(props: Props) {
  const identity = useIdentity();
  const conversation = useConversation();
  const message = useMessage(conversation.lastMessageId);
  if (!identity.permissions.includes("runs:create"))
    return (
      <p className="conversation-page-frame py-4 text-sm text-text-muted">
        游客只读浏览，登录后可发起对话。
      </p>
    );
  return (
    <>
      {message.operationError && (
        <FailureNotice
          compact
          failure={message.operationFailure}
          error={message.operationError}
          className="conversation-page-frame"
          context={{ operation: "mutation", resource: "conversation" }}
        />
      )}
      <ConversationComposer
        {...props}
        // 新草稿的 id 只用于本地作用域，文件列表必须使用已受理对话的正式编号。
        conversationId={conversation.conversation?.id}
        status={conversation.phase}
        canStop={
          conversation.hasPendingSubmission ? conversation.canCancelPending : message.canStop
        }
        canRetry={message.canRetry}
        onSend={conversation.sendMessage}
        onStop={
          conversation.hasPendingSubmission ? conversation.cancelPending : message.actions.stop
        }
        onRetry={message.actions.retry}
      />
    </>
  );
}
