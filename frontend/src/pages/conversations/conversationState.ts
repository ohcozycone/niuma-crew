import type { Failure } from "@/lib/failures/types";
import { answerContent, isActive, isPublished } from "@/lib/api/conversations";
import type { ChatMessage, Conversation, Reply } from "@/lib/api/conversations";
import type { ConversationInput } from "@/lib/api/conversationTransport";
import type { FileRef } from "@/lib/api/files";

/** 当前交互阶段；后台执行不因浏览器断线而停止。 */
export type ConversationPhase =
  /** 已有记录尚未读取成功，暂不接受新输入。 */
  | "loading"
  /** 可以开始下一次交互，上一轮结果由对应消息展示。 */
  | "ready"
  /** 正在确认提交、结果未知或排队等待执行。 */
  | "submitted"
  /** 助手已开始执行，包含工具处理和等待取消确认。 */
  | "streaming";

/** 用户可直接消费的错误及恢复操作。 */
export type ConversationError = {
  failure?: Failure | null;
  /** 可展示的说明。 */
  message: string;
  /** 恢复连接不会重发工作；retry 用于原请求或末次失败。 */
  recovery: "retry" | "reconnect" | null;
};

/** 一次待确认命令，重发必须沿用相同 key。 */
export type PendingCommand = {
  /** client_request_id。 */
  key: string;
  /** 普通发送的不可变输入；retry 时省略。 */
  input?: ConversationInput;
  /** 重试所针对的原 Reply。 */
  retryId?: string;
  /** 提交未确认时收到的停止意图。 */
  stopRequested?: boolean;
};

/** 直接用于展示的消息，不伪造数据库消息序号。 */
export type ConversationMessage = {
  files?: readonly FileRef[];
  conversationId?: string;
  /** 后端分配的稳定消息 ID。 */
  id: string;
  /** 公开消息角色。 */
  role: "user" | "assistant";
  /** 可见正文或本轮生成草稿。 */
  content: string;
  published: boolean;
  /** 助手消息对应的完整 Reply（含步骤），用户消息为空。 */
  run: Reply | null;
};

export type ConversationState = {
  id: string;
  conversation: Conversation | null;
  messages: ConversationMessage[];
  run: Reply | null;
  loading: boolean;
  submitting: boolean;
  pending: PendingCommand | null;
  submissionError: ConversationError | null;
  connectionError: ConversationError | null;
  cursor: number | null;
  loadingOlder: boolean;
  historyError: string | null;
  historyFailure?: Failure | null;
};

type Action =
  | { type: "reset"; state: ConversationState }
  | { type: "draft_ready" }
  | { type: "metadata"; conversation: Conversation }
  | {
      type: "loaded";
      conversation: Conversation;
      messages: ChatMessage[];
      cursor: number | null;
      run: Reply | null;
      replace?: boolean;
    }
  | { type: "snapshot"; run: Reply }
  | { type: "submit"; command: PendingCommand }
  | { type: "accepted"; command: PendingCommand; run: Reply }
  | { type: "submit_failed"; uncertain: boolean; error: ConversationError }
  | { type: "submission_error"; error: ConversationError | null }
  | { type: "connection_error"; error: ConversationError | null }
  | { type: "older_loading" }
  | { type: "older_cancelled" }
  | { type: "pending_stop"; command: PendingCommand }
  | { type: "older"; messages: ChatMessage[]; cursor: number | null }
  | { type: "older_failed"; message: string; failure?: Failure | null };

/** 对历史和实时快照使用同一条消息投影，草稿规则也保持一致。 */
export function fromMessage(message: ChatMessage): ConversationMessage {
  return {
    id: message.id,
    files: message.files,
    conversationId: message.conversation_id,
    role: message.role,
    content: message.run ? answerContent(message.run) : message.content,
    published: message.published,
    run: message.run,
  };
}

/** 未变化的步骤保留引用；流式片段只重新渲染实际变化的行。 */
function shareRun(run: Reply, previous?: Reply | null): Reply {
  if (!previous || previous.id !== run.id) return run;
  const byId = new Map(previous.steps.map((step) => [step.id, step]));
  const steps = run.steps.map((step) => {
    const saved = byId.get(step.id);
    return saved &&
      Object.keys(step).every((key) => {
        const field = key as keyof typeof step;
        return field === "safe_details"
          ? JSON.stringify(saved[field]) === JSON.stringify(step[field])
          : saved[field] === step[field];
      })
      ? saved
      : step;
  });
  return {
    ...run,
    steps:
      steps.length === previous.steps.length && steps.every((step, i) => step === previous.steps[i])
        ? previous.steps
        : steps,
  };
}

function mergePage(current: ConversationMessage[], incoming: ChatMessage[], prepend = false) {
  const existing = new Map(current.map((message) => [message.id, message]));
  const received = incoming.map((dto) => {
    const message = fromMessage(dto);
    const previous = existing.get(message.id);
    if (previous && !message.run) return previous;
    // 读取历史不能清掉已经观察到的进度、错误或更晚的终态。
    if (
      previous?.run &&
      message.run &&
      (previous.run.version >= message.run.version ||
        (!isActive(previous.run.status) && previous.run.status !== message.run.status))
    )
      return previous;
    return previous && message.run
      ? { ...message, run: shareRun(message.run, previous.run) }
      : message;
  });
  const updates = new Map(received.map((message) => [message.id, message]));
  const merged = new Map(
    (prepend
      ? [...received, ...current.map((message) => updates.get(message.id) ?? message)]
      : [...current, ...received]
    ).map((message) => [message.id, message]),
  );
  const result = [...merged.values()];
  return result.length === current.length && result.every((message, i) => message === current[i])
    ? current
    : result;
}

function withRun(state: ConversationState, run: Reply): ConversationState {
  if (
    run.conversation_id !== state.id &&
    !(
      state.id.startsWith("draft:") &&
      (!state.conversation || state.conversation.id === run.conversation_id)
    )
  )
    return state;
  const messageRun = state.messages.find((message) => message.id === run.id)?.run;
  if (
    messageRun &&
    (messageRun.version > run.version ||
      (!isActive(messageRun.status) && messageRun.status !== run.status))
  ) {
    return { ...state, run: messageRun };
  }
  const previous = state.run;
  if (
    previous?.id === run.id &&
    (previous.version >= run.version ||
      (!isActive(previous.status) && previous.status !== run.status))
  )
    return state;
  const shared = shareRun(run, previous ?? messageRun);
  const messages = state.messages.map((message) =>
    message.id === run.id
      ? {
          ...message,
          content: answerContent(run),
          files: run.files,
          conversationId: run.conversation_id,
          published: isPublished(run),
          run: shared,
        }
      : message,
  );
  return { ...state, run: shared, messages };
}

/** 单次业务事件完成合并；网络请求和随机 ID 不在 reducer 内执行。 */
export function conversationReducer(state: ConversationState, action: Action): ConversationState {
  switch (action.type) {
    case "reset":
      return action.state;
    case "draft_ready":
      return state.loading ? { ...state, loading: false } : state;
    case "metadata":
      return { ...state, conversation: newerConversation(state.conversation, action.conversation) };
    case "snapshot": {
      const scoped = {
        ...state,
        conversation: newerConversation(state.conversation, action.run.scope),
      };
      return state.run?.id === action.run.id ? withRun(scoped, action.run) : scoped;
    }
    case "loaded": {
      const next = {
        ...state,
        conversation: newerConversation(state.conversation, action.conversation),
        loading: false,
        connectionError: null,
        cursor: action.cursor,
        messages: mergePage(action.replace ? [] : state.messages, action.messages),
      };
      const latest =
        state.conversation && state.conversation.version > action.conversation.version && state.run
          ? state.run
          : state.run &&
              (!action.run ||
                (state.run.id === action.run.id && state.run.version >= action.run.version))
            ? state.run
            : action.run;
      // 历史合入后重新应用已观察快照，即使 revision 没有改变。
      return latest ? withRun({ ...next, run: null }, latest) : next;
    }
    case "submit":
      return { ...state, submitting: true, pending: action.command, submissionError: null };
    case "accepted": {
      const run =
        state.run?.id === action.run.id && state.run.version > action.run.version
          ? state.run
          : action.run;
      let messages = state.messages;
      if (action.command.input && !messages.some((m) => m.id === action.run.reply_to_message_id))
        messages = [
          ...messages,
          {
            id: action.run.reply_to_message_id,
            files: action.command.input.files,
            conversationId: action.run.conversation_id,
            role: "user",
            content: action.command.input.content,
            published: true,
            run: null,
          },
        ];
      if (!messages.some((m) => m.id === action.run.id))
        messages = [
          ...messages,
          {
            id: action.run.id,
            role: "assistant",
            content: "",
            published: false,
            run: null,
          },
        ];
      const conversation = newerConversation(state.conversation, action.run.scope);
      const previousLatest =
        run.scope &&
        state.run &&
        conversation?.last_response_id === state.run.id &&
        run.id !== state.run.id
          ? state.run
          : null;
      const accepted = withRun(
        {
          ...state,
          conversation,
          messages,
          pending: null,
          submitting: false,
          loading: false,
          run: null,
          submissionError: null,
        },
        run,
      );
      return previousLatest ? { ...accepted, run: previousLatest } : accepted;
    }
    case "submit_failed":
      return {
        ...state,
        submitting: false,
        pending: action.uncertain ? state.pending : null,
        submissionError: action.error,
      };
    case "connection_error":
      return state.connectionError?.message === action.error?.message &&
        state.connectionError?.recovery === action.error?.recovery &&
        state.connectionError?.failure === action.error?.failure
        ? state
        : { ...state, connectionError: action.error };
    case "submission_error":
      return state.submissionError?.message === action.error?.message &&
        state.submissionError?.recovery === action.error?.recovery &&
        state.submissionError?.failure === action.error?.failure
        ? state
        : { ...state, submissionError: action.error };
    case "older_loading":
      return { ...state, loadingOlder: true, historyError: null, historyFailure: null };
    case "older_cancelled":
      return state.loadingOlder || state.historyError
        ? { ...state, loadingOlder: false, historyError: null, historyFailure: null }
        : state;
    case "pending_stop":
      return { ...state, pending: action.command };
    case "older":
      return {
        ...state,
        messages: mergePage(state.messages, action.messages, true),
        cursor: action.cursor,
        loadingOlder: false,
        historyError: null,
      };
    case "older_failed":
      return {
        ...state,
        loadingOlder: false,
        historyError: action.message,
        historyFailure: action.failure,
      };
  }
}

/** 只让页面判断能否发送，不要求组合底层命令及连接状态。 */
export function conversationPhase(state: ConversationState): ConversationPhase {
  if (state.loading) return "loading";
  if (
    state.run?.acceptance === "pending" ||
    state.pending ||
    state.submitting ||
    state.run?.status === "queued" ||
    (state.conversation?.active_response_id &&
      state.conversation.active_response_id !== state.run?.id)
  )
    return "submitted";
  return isActive(state.run?.status) ? "streaming" : "ready";
}

function newerConversation(
  current: Conversation | null,
  incoming?: Conversation | null,
): Conversation | null {
  if (!incoming) return current;
  return !current || current.id !== incoming.id || incoming.version > current.version
    ? incoming
    : current;
}
