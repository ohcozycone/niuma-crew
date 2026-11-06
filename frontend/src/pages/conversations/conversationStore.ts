import type { Failure } from "@/lib/failures/types";
import { isActive, type Reply, type ReplyStep } from "@/lib/api/conversations";
import type { ConversationMessage } from "./conversationState";
import type { useConversationController } from "@/pages/conversations/useConversationController";

export type ConversationModel = ReturnType<typeof useConversationController>;
type HistoryView = Omit<ConversationModel["history"], "messages">;
export type ConversationView = Pick<
  ConversationModel,
  | "id"
  | "conversation"
  | "phase"
  | "latestQuestionId"
  | "lastMessageId"
  | "submissionError"
  | "connectionError"
  | "hasPendingSubmission"
  | "canCancelPending"
  | "submitting"
  | "sendMessage"
  | "resendPending"
  | "cancelPending"
  | "reconnect"
> & {
  title: string;
  messageIds: string[];
  history: HistoryView;
};
export type MessageView = {
  message: ConversationMessage | null;
  status: Reply["status"] | null;
  executionActions: readonly ReplyStep[];
  usage: Reply["usage"];
  error: Reply["error"];
  operationError: string | null;
  operationFailure: Failure | null;
  canStop: boolean;
  canRetry: boolean;
  pending: { stop: boolean; retry: boolean };
  actions: { stop: () => Promise<void>; retry: () => Promise<void>; copy: () => Promise<void> };
};
const emptySteps: readonly ReplyStep[] = [];

function preserve<T extends object>(previous: T | undefined, next: T): T {
  return previous &&
    Object.keys(previous).length === Object.keys(next).length &&
    (Object.keys(next) as Array<keyof T>).every((key) => previous[key] === next[key])
    ? previous
    : next;
}

/** 当前页面会话的已提交读取快照；不创建请求、不接受 SDK 事件。 */
export function createConversationStore(initial: ConversationModel) {
  let model = initial;
  let active = false;
  let messages = new Map<string, ConversationMessage>();
  let conversation: ConversationView;
  const snapshots = new Map<string | null, MessageView>();
  const listeners = new Set<() => void>();
  const requireActive = () => {
    if (!active) throw new Error("当前会话已离开，请重新打开后操作。");
  };
  const actions = {
    sendMessage: ((input) => {
      requireActive();
      return model.sendMessage(input);
    }) as ConversationView["sendMessage"],
    resendPending: () => {
      requireActive();
      return model.resendPending();
    },
    cancelPending: () => {
      requireActive();
      return model.cancelPending();
    },
    reconnect: () => {
      requireActive();
      model.reconnect();
    },
  };
  const historyActions = {
    jump: (id: string) => {
      requireActive();
      return model.history.jump(id);
    },
    showLatest: (refresh?: boolean) => {
      requireActive();
      return model.history.showLatest(refresh);
    },
    loadMore: () => {
      requireActive();
      return model.history.loadMore();
    },
    loadNewer: () => {
      requireActive();
      return model.history.loadNewer();
    },
  };

  function getMessage(id: string | null): MessageView {
    const previous = snapshots.get(id);
    const message = id === null ? null : (messages.get(id) ?? null);
    const run = message?.run;
    const operation = id === null ? undefined : model.messageOperations[id];
    const canStop =
      !!run &&
      id === model.lastMessageId &&
      isActive(run.status) &&
      run.status !== "cancelling" &&
      !model.hasPendingSubmission &&
      !operation?.stopping;
    const canRetry =
      !!run &&
      run.can_retry &&
      id === model.lastMessageId &&
      ["failed", "cancelled", "interrupted"].includes(run.status) &&
      model.phase === "ready" &&
      !model.hasPendingSubmission &&
      !operation?.retrying;
    const pending = preserve(previous?.pending, {
      stop: !!operation?.stopping,
      retry: !!operation?.retrying,
    });
    const messageActions = previous?.actions ?? {
      async stop() {
        requireActive();
        if (id === null || !getMessage(id).canStop) throw new Error("该消息当前不能停止。");
        await model.stopMessage(id);
      },
      async retry() {
        requireActive();
        if (id === null || !getMessage(id).canRetry) throw new Error("该消息当前不能重试。");
        await model.retryMessage(id);
      },
      async copy() {
        requireActive();
        const content = id === null ? null : messages.get(id)?.content;
        if (content) await navigator.clipboard?.writeText(content);
      },
    };
    const snapshot = preserve(previous, {
      message,
      status: run?.status ?? null,
      executionActions: run?.steps ?? emptySteps,
      usage: run?.usage ?? null,
      error: run?.error ?? null,
      operationError: operation?.error ?? null,
      operationFailure: operation?.error ? (operation.failure ?? null) : null,
      canStop,
      canRetry,
      pending,
      actions: messageActions,
    });
    snapshots.set(id, snapshot);
    return snapshot;
  }

  function publish(next: ConversationModel) {
    model = next;
    const incoming = new Map<string, ConversationMessage>();
    for (const message of [...model.liveMessages, ...model.messages]) {
      const existing = incoming.get(message.id) ?? messages.get(message.id);
      incoming.set(
        message.id,
        existing &&
          (!message.run ||
            (existing.run &&
              (existing.run.version >= message.run.version ||
                (!isActive(existing.run.status) && existing.run.status !== message.run.status))))
          ? existing
          : message,
      );
    }
    messages = incoming;
    const ids = model.messages.map((message) => message.id);
    const messageIds =
      conversation?.messageIds.length === ids.length &&
      ids.every((id, i) => id === conversation.messageIds[i])
        ? conversation.messageIds
        : ids;
    const historyView = preserve(conversation?.history, {
      position: model.history.position,
      isHistorical: model.history.isHistorical,
      hasMore: model.history.hasMore,
      hasNewer: model.history.hasNewer,
      isLoading: model.history.isLoading,
      loading: model.history.loading,
      error: model.history.error,
      failure: model.history.failure,
      errorOrigin: model.history.errorOrigin,
      ...historyActions,
    });
    conversation = preserve(conversation, {
      id: model.id,
      conversation: model.conversation,
      phase: model.phase,
      title:
        model.conversation?.title ||
        model.liveMessages.find((message) => message.role === "user")?.content.slice(0, 100) ||
        "新对话",
      messageIds,
      lastMessageId: model.lastMessageId,
      latestQuestionId: model.latestQuestionId,
      submissionError: model.submissionError,
      connectionError: model.connectionError,
      hasPendingSubmission: model.hasPendingSubmission,
      canCancelPending: model.canCancelPending,
      submitting: model.submitting,
      ...actions,
      history: historyView,
    });
    for (const listener of listeners) listener();
  }
  publish(initial);
  return {
    getConversation: () => conversation,
    getMessage,
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    publish,
    activate() {
      active = true;
    },
    deactivate() {
      active = false;
    },
  };
}
export type ConversationStore = ReturnType<typeof createConversationStore>;
