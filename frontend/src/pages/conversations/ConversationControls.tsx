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
  const conversation = useConversation();
  const message = useMessage(conversation.lastMessageId);
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
        conversationId={conversation.id}
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
