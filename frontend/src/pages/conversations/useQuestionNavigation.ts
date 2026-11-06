import { useFailureState } from "@/state/shared/useFailureState";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  getQuestions,
  getQuestionPreview,
  type ConversationQuestion,
} from "@/lib/api/conversations";
import {
  maxVisibleQuestions,
  rulerStart,
  type QuestionNavigationSource,
} from "./questionNavigation";

const defaultSource: QuestionNavigationSource = {
  questions: getQuestions,
  preview: getQuestionPreview,
};
const minimumQuestions = 3;
const metadataLimit = 256;

/** 导航独立的只读模型；不读取页面 DOM，也不持有正文或执行订阅。 */
export function useQuestionNavigation({
  id,
  revision,
  currentAnchorId,
  source = defaultSource,
}: {
  id: string;
  revision?: string;
  currentAnchorId: string | null;
  source?: QuestionNavigationSource;
}) {
  const [questions, setQuestions] = useState<ConversationQuestion[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [anchor, setAnchor] = useState<ConversationQuestion | null>(null);
  const { failure: failureFact, error: failure, setError: setFailure } = useFailureState();
  const [reload, setReload] = useState(0);
  const [browsing, setBrowsing] = useState<{ anchor: string | null; start: number } | null>(null);
  // 正文换问题就结束独立翻阅，回到同一问题也不能复活旧窗口。
  if (browsing && browsing.anchor !== currentAnchorId) setBrowsing(null);
  const known = questions.find((q) => q.id === currentAnchorId);
  const current = known ?? (anchor?.id === currentAnchorId ? anchor : null);
  const count = total ?? 0;
  const currentNumber = current?.number ?? anchor?.number ?? Math.max(count, 1);
  const windowStart = browsing?.anchor === currentAnchorId ? browsing?.start : undefined;
  const rangeStart = windowStart ?? rulerStart(currentNumber, count, maxVisibleQuestions);
  const hidden = total !== null && total < minimumQuestions;
  const browse = useCallback(
    (delta: number, visible: number) => {
      setBrowsing((previous) => {
        const start =
          previous?.anchor === currentAnchorId
            ? previous.start
            : rulerStart(currentNumber, count, visible);
        return {
          anchor: currentAnchorId,
          start: Math.max(0, Math.min(start + delta, count - visible)),
        };
      });
    },
    [currentAnchorId, currentNumber, count],
  );
  const follow = useCallback(() => setBrowsing(null), []);
  const retry = useCallback(() => setReload((n) => n + 1), []);
  const merge = useCallback((incoming: ConversationQuestion[]) => {
    setQuestions((previous) =>
      [...new Map([...previous, ...incoming].map((q) => [q.id, q])).values()].slice(-metadataLimit),
    );
  }, []);
  useEffect(() => {
    const scope = new AbortController();
    void source
      .questions(id, "", undefined, scope.signal)
      .then((page) => {
        if (scope.signal.aborted) return;
        merge(page.items);
        setTotal(page.total);
        setFailure("");
      })
      .catch((reason: Error) => {
        if (!scope.signal.aborted) setFailure(reason);
      });
    return () => scope.abort();
  }, [id, revision, reload, merge, source, setFailure]);
  useEffect(() => {
    if (hidden || total === null || !currentAnchorId || known || anchor?.id === currentAnchorId)
      return;
    const scope = new AbortController();
    const timer = window.setTimeout(() => {
      void source
        .questions(id, "", undefined, scope.signal, { anchor: currentAnchorId, limit: 1 })
        .then((page) => {
          if (scope.signal.aborted) return;
          setTotal(page.total);
          if (!page.anchor) return;
          setAnchor(page.anchor);
          merge([page.anchor]);
        })
        .catch((reason: Error) => {
          if (!scope.signal.aborted) setFailure(reason);
        });
    }, 80);
    return () => {
      window.clearTimeout(timer);
      scope.abort();
    };
  }, [
    id,
    currentAnchorId,
    known,
    anchor?.id,
    revision,
    reload,
    hidden,
    total,
    merge,
    source,
    setFailure,
  ]);
  useEffect(() => {
    if (hidden || !count || (windowStart === undefined && !current && currentAnchorId)) return;
    const numbers = new Set(questions.map((q) => q.number));
    const size = Math.min(maxVisibleQuestions, count - rangeStart);
    if (Array.from({ length: size }, (_, i) => rangeStart + i + 1).every((n) => numbers.has(n)))
      return;
    const scope = new AbortController();
    const timer = window.setTimeout(() => {
      void source
        .questions(id, "", undefined, scope.signal, { startNumber: Math.max(1, rangeStart - 40) })
        .then((page) => {
          if (scope.signal.aborted) return;
          merge(page.items);
          setTotal(page.total);
          setFailure("");
        })
        .catch((reason: Error) => {
          if (!scope.signal.aborted) setFailure(reason);
        });
    }, 60);
    return () => {
      window.clearTimeout(timer);
      scope.abort();
    };
  }, [
    id,
    current,
    currentAnchorId,
    windowStart,
    rangeStart,
    count,
    questions,
    reload,
    hidden,
    merge,
    source,
    setFailure,
  ]);
  const byNumber = useMemo(() => {
    const result = new Map(questions.map((q) => [q.number, q]));
    if (current) result.set(current.number, current);
    return result;
  }, [questions, current]);
  return {
    total: count,
    pending: total === null && !failure,
    hidden,
    currentNumber,
    windowStart,
    byNumber,
    browse,
    follow,
    failure,
    failureFact,
    retry,
    source,
  };
}
