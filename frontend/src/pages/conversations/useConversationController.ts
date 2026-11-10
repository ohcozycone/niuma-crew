import { toFailure, failureMessage } from "@/lib/failures/resolve";
import type { Failure } from "@/lib/failures/types";
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { ApiError } from "@/lib/api/http";
import { isActive, isObserving, readPage, type Reply } from "@/lib/api/conversations";
import {
  createConversationTransport,
  type ConversationInput,
  type ConversationTransport,
} from "@/lib/api/conversationTransport";
import {
  conversationReducer,
  conversationPhase,
  type ConversationError,
  type ConversationState,
  type PendingCommand,
} from "./conversationState";
import { readConversationSession, saveConversationSession } from "./pendingSubmissionStorage";
import { useResponseSubscription } from "./useResponseSubscription";
import { useConversationHistory } from "./useConversationHistory";

export type MessageOperation = {
  stopping: boolean;
  retrying: boolean;
  error: string | null;
  failure?: Failure | null;
};

const defaultTransport = createConversationTransport();

async function readLatest(id: string, transport: ConversationTransport, signal: AbortSignal) {
  const snapshot = await transport.getSnapshot(id, signal);
  const page = readPage(snapshot.messages);
  const run = page.items.findLast((message) => message.run)?.run ?? null;
  return { conversation: snapshot.conversation, page, run };
}

function initialState(
  id: string,
  transport: ConversationTransport,
  storageKey?: string,
): ConversationState {
  const saved = readConversationSession(storageKey);
  return {
    id,
    conversation: null,
    messages: [],
    run: null,
    loading: !transport.create || saved.persisted || !!saved.pending,
    submitting: false,
    pending: saved.pending,
    submissionError: null,
    connectionError: null,
    cursor: null,
    loadingOlder: false,
    historyError: null,
  };
}

/** 管理一个对话的消息和操作；调用方显式提供身份隔离的实例与存储作用域。 */
export function useConversationController({
  id,
  transport = defaultTransport,
  storageKey,
  onAccepted,
}: {
  /** 会话的稳定 ID；本地草稿可以先于数据库记录存在。 */
  id: string;
  /** 网络能力及首次创建参数，不隐式读取页面环境。 */
  transport?: ConversationTransport;
  /** 可选的待确认请求存储键，由宿主按用户和会话隔离。 */
  storageKey?: string;
  /** 已接受输入的通知，可清理匹配的草稿；不代表执行完成。 */
  onAccepted?: (input: ConversationInput, reply: Reply) => void;
}) {
  const [state, dispatch] = useReducer(conversationReducer, undefined, () =>
    initialState(id, transport, storageKey),
  );
  const [reload, setReload] = useState(0);
  const [messageOperations, setMessageOperations] = useState<Record<string, MessageOperation>>({});
  const setMessageOperation = useCallback((messageId: string, patch: Partial<MessageOperation>) => {
    setMessageOperations((previous) => ({
      ...previous,
      [messageId]: {
        ...(previous[messageId] ?? { stopping: false, retrying: false, error: null }),
        ...patch,
      },
    }));
  }, []);
  const lifetime = useRef<AbortController | null>(null);
  const target = useRef(id);
  const commandLock = useRef(false);
  const stopLock = useRef(false);
  const olderLock = useRef(false);
  const olderRequest = useRef<AbortController | null>(null);
  const commandGeneration = useRef(0);
  const acceptedCallback = useRef(onAccepted);
  const pending = useRef<PendingCommand | null>(state.pending);
  const initialSession = useMemo(() => readConversationSession(storageKey), [storageKey]);
  const persisted = useRef(initialSession.persisted || !transport.create);
  const resolved = useRef<string | null>(
    initialSession.conversationId ?? (transport.create ? null : id),
  );
  const saveSession = useCallback(
    (value: { persisted: boolean; pending: PendingCommand | null }) => {
      saveConversationSession(storageKey, { ...value, conversationId: resolved.current });
    },
    [storageKey],
  );

  useEffect(() => {
    acceptedCallback.current = onAccepted;
  }, [onAccepted]);

  const receive = useCallback((run: Reply) => {
    dispatch({ type: "snapshot", run });
    if (run.scope?.active_response_id && run.scope.active_response_id !== run.id)
      setReload((version) => version + 1);
  }, []);
  const feedback = useCallback(
    (error: ConversationError | null) => dispatch({ type: "connection_error", error }),
    [],
  );
  const activeRunId = state.id === id && isObserving(state.run) ? state.run!.id : null;
  useResponseSubscription(
    resolved.current ?? id,
    activeRunId,
    transport,
    receive,
    feedback,
    reload,
  );

  useEffect(() => {
    // 读取重连可以中止旧 GET；同一会话已发出的命令仍需接收确认。
    const scope = new AbortController();
    lifetime.current = scope;
    commandLock.current = stopLock.current = false;
    return () => scope.abort();
  }, [id, transport, storageKey]);

  useEffect(() => {
    const scope = new AbortController();
    olderRequest.current?.abort();
    olderLock.current = false;
    dispatch({ type: "older_cancelled" });
    if (target.current !== id) {
      target.current = id;
      const next = initialState(id, transport, storageKey);
      pending.current = next.pending;
      resolved.current =
        readConversationSession(storageKey).conversationId ?? (transport.create ? null : id);
      persisted.current = readConversationSession(storageKey).persisted || !transport.create;
      commandLock.current = stopLock.current = olderLock.current = false;
      dispatch({ type: "reset", state: next });
    }
    async function load() {
      const generation = commandGeneration.current;
      const notifyAccepted = acceptedCallback.current;
      const original = pending.current;
      if (transport.create && !persisted.current && !original) {
        dispatch({ type: "draft_ready" });
        return;
      }
      try {
        let accepted: Reply | null = null;
        if (original) {
          accepted = await transport.findRequest(resolved.current, original.key, scope.signal);
          if (scope.signal.aborted || generation !== commandGeneration.current) return;
          if (accepted) {
            resolved.current = accepted.conversation_id;
            persisted.current = true;
            pending.current = original.stopRequested && isActive(accepted.status) ? original : null;
            saveSession({ persisted: true, pending: pending.current });

            dispatch({ type: "accepted", command: original, run: accepted });
            if (original.stopRequested && isActive(accepted.status)) {
              try {
                accepted = await transport.cancel(resolved.current ?? id, accepted.id);
                if (scope.signal.aborted) return;
                receive(accepted);
                pending.current = null;
                saveSession({ persisted: true, pending: null });
              } catch (error) {
                if (!scope.signal.aborted)
                  setMessageOperation(accepted.id, {
                    error: failureMessage(error),
                    failure: toFailure(error),
                  });
              }
            }
          }
        }
        if (resolved.current === null) {
          dispatch({ type: "draft_ready" });
          dispatch({
            type: "submission_error",
            error: { message: "尚未确认原请求，可使用原提交标识重试。", recovery: "retry" },
          });
          return;
        }
        const {
          conversation,
          page,
          run: latestRun,
        } = await readLatest(resolved.current ?? id, transport, scope.signal);
        const run = latestRun ?? accepted;
        if (scope.signal.aborted || generation !== commandGeneration.current) return;
        persisted.current = true;
        saveSession({ persisted: true, pending: pending.current });
        dispatch({
          type: "loaded",
          conversation,
          messages: page.items,
          cursor: page.next_before_sequence,
          run,
        });
        if (accepted && original?.input) notifyAccepted?.(original.input, accepted);
        if (original && !accepted)
          dispatch({
            type: "submission_error",
            error: { message: "尚未确认原请求，可使用原提交标识重试。", recovery: "retry" },
          });
      } catch (error) {
        if (scope.signal.aborted || generation !== commandGeneration.current) return;
        feedback({
          message: failureMessage(error),
          failure: toFailure(error),
          recovery:
            error instanceof ApiError && [401, 403, 404].includes(error.status)
              ? null
              : "reconnect",
        });
      }
    }
    void load();
    return () => {
      scope.abort();
      olderRequest.current?.abort();
    };
  }, [id, transport, storageKey, receive, feedback, reload, setMessageOperation, saveSession]);

  const submit = useCallback(
    async (command: PendingCommand) => {
      if (commandLock.current) throw new Error("正在确认提交，请勿重复发送。");
      commandLock.current = true;
      commandGeneration.current += 1;
      olderRequest.current?.abort();
      olderLock.current = false;
      dispatch({ type: "older_cancelled" });
      const scope = lifetime.current;
      const notifyAccepted = acceptedCallback.current;
      pending.current = command;
      saveSession({ persisted: persisted.current, pending: command });
      dispatch({ type: "submit", command });
      try {
        const run = command.retryId
          ? await transport.retry(resolved.current ?? id, command.retryId, command.key)
          : await transport.send(resolved.current, command.input!, command.key);
        // 接受确认即使迟于卸载，也只清理它捕获的旧用户/旧会话存储。
        const stored = readConversationSession(storageKey);
        const sameScope = !!scope && !scope.signal.aborted && lifetime.current === scope;
        const shouldStop =
          (stored.pending?.key === command.key && stored.pending.stopRequested) ||
          (sameScope && pending.current?.key === command.key && pending.current.stopRequested);
        if (sameScope) resolved.current = run.conversation_id;
        saveConversationSession(storageKey, {
          persisted: true,
          conversationId: run.conversation_id,
          pending:
            stored.pending && stored.pending.key !== command.key
              ? stored.pending
              : shouldStop
                ? { ...command, stopRequested: true }
                : null,
        });

        if (!scope || scope.signal.aborted || lifetime.current !== scope) {
          if (command.input) notifyAccepted?.(command.input, run);
          return;
        }
        pending.current = null;
        persisted.current = true;
        dispatch({ type: "accepted", command, run });
        if (run.scope?.active_response_id && run.scope.active_response_id !== run.id)
          setReload((version) => version + 1);
        if (shouldStop && isActive(run.status)) {
          try {
            const stopped = await transport.cancel(run.conversation_id, run.id);
            saveConversationSession(storageKey, {
              persisted: true,
              pending: null,
              conversationId: run.conversation_id,
            });
            if (!scope.signal.aborted) receive(stopped);
          } catch (error) {
            if (!scope.signal.aborted)
              setMessageOperation(run.id, {
                error: failureMessage(error),
                failure: toFailure(error),
              });
          }
        }
        if (command.input) notifyAccepted?.(command.input, run);
        if (scope.signal.aborted) return;
      } catch (error) {
        if (!scope || scope.signal.aborted || lifetime.current !== scope) throw error;
        const uncertain = !(
          error instanceof ApiError &&
          error.status >= 400 &&
          error.status < 500 &&
          error.status !== 408
        );
        if (!uncertain) pending.current = null;
        saveSession({
          persisted: persisted.current,
          pending: pending.current,
        });
        dispatch({
          type: "submit_failed",
          uncertain,
          error: {
            message: failureMessage(error),
            failure: toFailure(error),
            recovery: uncertain ? "retry" : null,
          },
        });
        throw error;
      } finally {
        if (lifetime.current === scope) commandLock.current = false;
      }
    },
    [id, transport, storageKey, receive, setMessageOperation, saveSession],
  );

  const status = state.id === id ? conversationPhase(state) : "loading";

  const sendMessage = useCallback(
    async (input: ConversationInput) => {
      if (status !== "ready" || commandLock.current) throw new Error("当前对话尚未就绪。");
      if (!input.content.trim()) return;
      await submit({
        key: crypto.randomUUID(),
        input: {
          ...input,
          content: input.content.trim(),
          selectedSkillIds: [...(input.selectedSkillIds ?? [])],
        },
      });
    },
    [status, submit],
  );

  const resendPending = useCallback(async () => {
    if (!pending.current) throw new Error("没有待确认的提交。");
    await submit(pending.current);
  }, [submit]);
  const cancelPending = useCallback(async () => {
    if (!pending.current || pending.current.stopRequested) return;
    pending.current = { ...pending.current, stopRequested: true };
    saveSession({ persisted: persisted.current, pending: pending.current });
    dispatch({ type: "pending_stop", command: pending.current });
  }, [saveSession]);

  const retryMessage = useCallback(
    async (messageId: string) => {
      const run = state.run;
      if (
        pending.current ||
        commandLock.current ||
        !run ||
        run.id !== messageId ||
        !run.can_retry ||
        !["failed", "cancelled", "interrupted"].includes(run.status)
      )
        throw new Error("该消息当前不能重试。");
      const scope = lifetime.current;
      setMessageOperation(messageId, { retrying: true, error: null });
      try {
        await submit({ key: crypto.randomUUID(), retryId: run.id });
      } catch (error) {
        if (scope && !scope.signal.aborted && lifetime.current === scope) {
          if (!pending.current) {
            dispatch({ type: "submission_error", error: null });
            setMessageOperation(messageId, {
              error: failureMessage(error),
              failure: toFailure(error),
            });
          }
        }
        throw error;
      } finally {
        if (scope && !scope.signal.aborted && lifetime.current === scope)
          setMessageOperation(messageId, { retrying: false });
      }
    },
    [state.run, submit, setMessageOperation],
  );

  const stopMessage = useCallback(
    async (messageId: string) => {
      const run = state.run;
      if (
        pending.current ||
        !run ||
        run.id !== messageId ||
        !isActive(run.status) ||
        run.status === "cancelling"
      )
        throw new Error("该消息当前不能停止。");
      if (stopLock.current) return;
      stopLock.current = true;
      const scope = lifetime.current;
      setMessageOperation(messageId, { stopping: true, error: null });
      try {
        const next = await transport.cancel(resolved.current ?? id, run.id);
        if (scope && !scope.signal.aborted && lifetime.current === scope) receive(next);
      } catch (error) {
        if (scope && !scope.signal.aborted && lifetime.current === scope)
          setMessageOperation(messageId, {
            error: failureMessage(error),
            failure: toFailure(error),
          });
      } finally {
        if (lifetime.current === scope) {
          stopLock.current = false;
          if (scope && !scope.signal.aborted) setMessageOperation(messageId, { stopping: false });
        }
      }
    },
    [id, state.run, transport, receive, setMessageOperation],
  );

  const reconnect = useCallback(() => setReload((version) => version + 1), []);
  const cancelHistory = useCallback(() => {
    olderRequest.current?.abort();
    olderLock.current = false;
    dispatch({ type: "older_cancelled" });
  }, []);
  const loadMore = useCallback(async () => {
    if (!state.cursor || olderLock.current) return;
    olderLock.current = true;
    const scope = new AbortController();
    olderRequest.current = scope;
    dispatch({ type: "older_loading" });
    try {
      const page = await transport.getMessages(resolved.current ?? id, state.cursor, scope.signal);
      if (!scope?.signal.aborted)
        dispatch({ type: "older", messages: page.items, cursor: page.next_before_sequence });
    } catch (error) {
      if (!scope?.signal.aborted)
        dispatch({
          type: "older_failed",
          message: failureMessage(error),
          failure: toFailure(error),
        });
    } finally {
      if (olderRequest.current === scope) olderLock.current = false;
    }
  }, [id, state.cursor, transport]);
  const history = useMemo(
    () => ({
      hasMore: state.cursor !== null,
      isLoading: state.loadingOlder,
      error: state.historyError,
      failure: state.historyFailure,
      loadMore,
      cancel: cancelHistory,
    }),
    [
      state.cursor,
      state.loadingOlder,
      state.historyError,
      state.historyFailure,
      loadMore,
      cancelHistory,
    ],
  );
  const refreshLatest = useCallback(
    async (signal: AbortSignal) => {
      if (!persisted.current) return;
      const { conversation, page, run } = await readLatest(
        resolved.current ?? id,
        transport,
        signal,
      );
      if (!signal.aborted)
        dispatch({
          type: "loaded",
          conversation,
          messages: page.items,
          cursor: page.next_before_sequence,
          run,
          replace: true,
        });
    },
    [id, transport],
  );
  const transcript = useConversationHistory({
    id: resolved.current ?? id,
    transport,
    messages: state.messages,
    latestHistory: history,
    refreshLatest,
  });
  const { showLatest } = transcript;

  const sendAtLatest = useCallback(
    async (input: ConversationInput) => {
      void showLatest(false);
      await sendMessage(input);
    },
    [showLatest, sendMessage],
  );
  const retryAtLatest = useCallback(
    async (messageId: string) => {
      // 先校验绑定目标，再改变当前阅读窗口；历史按钮不能隐式操作最新消息。
      await retryMessage(messageId);
      void showLatest(false);
    },
    [showLatest, retryMessage],
  );

  return {
    id: resolved.current ?? id,
    conversation: state.id === id ? state.conversation : null,
    messages: state.id === id ? transcript.messages : [],
    liveMessages: state.id === id ? state.messages : [],
    latestQuestionId: state.messages.findLast((message) => message.role === "user")?.id ?? null,
    lastMessageId: state.messages.at(-1)?.id ?? null,
    phase: status,
    submissionError: state.id === id ? state.submissionError : null,
    connectionError: state.id === id ? state.connectionError : null,
    sendMessage: sendAtLatest,
    resendPending,
    cancelPending,
    stopMessage,
    retryMessage: retryAtLatest,
    reconnect,
    history: transcript,
    hasPendingSubmission: !!state.pending,
    canCancelPending: !!state.pending && !state.pending.stopRequested,
    submitting: state.submitting,
    messageOperations,
  };
}
