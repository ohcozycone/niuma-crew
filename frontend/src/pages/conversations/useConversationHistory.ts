import { useFailureState } from "@/state/shared/useFailureState";
import type { Failure } from "@/lib/failures/types";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ConversationTransport } from "@/lib/api/conversationTransport";
import { fromMessage, type ConversationMessage } from "./conversationState";

type Window = {
  id: string;
  messages: ConversationMessage[];
  before: number | null;
  after: number | null;
};
type Operation = "older" | "newer" | "jump" | "latest";
type LatestHistory = {
  hasMore: boolean;
  isLoading: boolean;
  error: string | null;
  failure?: Failure | null;
  loadMore: () => Promise<void>;
  cancel: () => void;
};
export type TranscriptPosition = { key: number; target: string | "end" };

/** 历史窗口与持续接收 SSE 的最新窗口分开，不能拼接存在空洞的两段历史。 */
export function useConversationHistory({
  id,
  transport,
  messages: live,
  latestHistory,
  refreshLatest,
}: {
  id: string;
  transport: ConversationTransport;
  messages: ConversationMessage[];
  latestHistory: LatestHistory;
  refreshLatest: (signal: AbortSignal) => Promise<void>;
}) {
  const [storedWindow, setWindow] = useState<Window | null>(null);
  const window = storedWindow?.id === id ? storedWindow : null;
  const [loading, setLoading] = useState<Operation | null>(null);
  const { failure, error, setError } = useFailureState();
  const [errorOrigin, setErrorOrigin] = useState<Operation | null>(null);
  const [position, setPosition] = useState<TranscriptPosition | null>(null);
  const request = useRef<AbortController | null>(null);
  const generation = useRef(0);
  const { cancel } = latestHistory;
  useEffect(() => {
    setWindow(null);
    setLoading(null);
    setError(null);
    setPosition(null);
    return () => {
      request.current?.abort();
      request.current = null;
    };
  }, [id, transport, setError]);

  const messages = useMemo(() => {
    if (!window) return live;
    const current = new Map(live.map((m) => [m.id, m]));
    return window.messages.map((message) => {
      const latest = current.get(message.id);
      // 定位请求可能先于 SSE 拿到较新版本，旧的实时窗口不能覆盖它。
      return latest && (!message.run || (latest.run && latest.run.version >= message.run.version))
        ? latest
        : message;
    });
  }, [window, live]);
  const positionAt = useCallback((target: string) => {
    setPosition({ key: ++generation.current, target });
  }, []);
  const showLatest = useCallback(
    async (refresh = true) => {
      cancel();
      request.current?.abort();
      const scope = new AbortController();
      request.current = scope;
      setError(null);
      setLoading(refresh ? "latest" : null);
      try {
        if (refresh) await refreshLatest(scope.signal);
        if (scope.signal.aborted) return;
        setWindow(null);
        positionAt("end");
      } catch (failure) {
        if (!scope.signal.aborted) {
          setError(failure);
          setErrorOrigin("latest");
        }
      } finally {
        if (request.current === scope) {
          request.current = null;
          setLoading(null);
        }
      }
    },
    [positionAt, cancel, refreshLatest, setError],
  );

  const jump = useCallback(
    async (messageId: string) => {
      cancel();
      request.current?.abort();
      const scope = new AbortController();
      request.current = scope;
      setError(null);
      setLoading("jump");
      if (messages.some((m) => m.id === messageId)) {
        request.current = null;
        setLoading(null);
        positionAt(messageId);
        return true;
      }
      if (live.some((m) => m.id === messageId)) {
        request.current = null;
        setWindow(null);
        setLoading(null);
        positionAt(messageId);
        return true;
      }
      try {
        const page = await transport.getMessages(id, undefined, scope.signal, {
          around: messageId,
        });
        if (scope.signal.aborted) return false;
        if (!page.items.some((m) => m.id === messageId))
          throw new Error("目标问题已不可用，请刷新目录。");
        setWindow({
          id,
          messages: page.items.map(fromMessage),
          before: page.next_before_sequence,
          after: page.next_after_sequence ?? null,
        });
        positionAt(messageId);
        return true;
      } catch (failure) {
        if (!scope.signal.aborted) {
          setError(failure);
          setErrorOrigin("jump");
        }
        return false;
      } finally {
        if (request.current === scope) {
          request.current = null;
          setLoading(null);
        }
      }
    },
    [id, transport, messages, live, positionAt, cancel, setError],
  );

  const load = useCallback(
    async (direction: "older" | "newer") => {
      if (request.current || latestHistory.isLoading) return;
      if (!window) {
        if (direction === "older") await latestHistory.loadMore();
        return;
      }
      const cursor = direction === "older" ? window.before : window.after;
      if (cursor === null) return;
      const scope = new AbortController();
      request.current = scope;
      setLoading(direction);
      setError(null);
      try {
        const page = await transport.getMessages(
          id,
          direction === "older" ? cursor : undefined,
          scope.signal,
          direction === "newer" ? { after: cursor } : {},
        );
        if (scope.signal.aborted) return;
        setWindow((previous) => {
          if (!previous) return previous;
          const incoming = page.items.map(fromMessage);
          const rows =
            direction === "older"
              ? [...incoming, ...previous.messages]
              : [...previous.messages, ...incoming];
          return {
            id,
            messages: [...new Map(rows.map((m) => [m.id, m])).values()],
            before: direction === "older" ? page.next_before_sequence : previous.before,
            after: direction === "newer" ? (page.next_after_sequence ?? null) : previous.after,
          };
        });
      } catch (failure) {
        if (!scope.signal.aborted) {
          setError(failure);
          setErrorOrigin(direction);
        }
      } finally {
        if (request.current === scope) {
          request.current = null;
          setLoading(null);
        }
      }
    },
    [id, transport, window, latestHistory, setError],
  );
  return {
    messages,
    position,
    jump,
    showLatest,
    isHistorical: window !== null,
    hasMore: window ? window.before !== null : latestHistory.hasMore,
    hasNewer: window ? window.after !== null : false,
    isLoading: loading !== null || latestHistory.isLoading,
    loading,
    error: error || (window ? null : latestHistory.error),
    failure: failure || (window ? null : latestHistory.failure),
    errorOrigin: error ? errorOrigin : !window && latestHistory.error ? "older" : null,
    loadMore: () => load("older"),
    loadNewer: () => load("newer"),
  };
}
