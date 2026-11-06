import { toFailure } from "@/lib/failures/resolve";
import type { Failure } from "@/lib/failures/types";
import { useEffect, useState } from "react";
import type { QuestionPreview } from "@/lib/api/conversations";
import type { QuestionNavigationSource } from "./questionNavigation";

/** 每次打开核对最新执行，不复用可能被重试取代的回答副本。 */
export function useQuestionPreview(
  id: string,
  questionId: string,
  read: QuestionNavigationSource["preview"],
) {
  const [result, setResult] = useState<{
    key: string;
    read: QuestionNavigationSource["preview"];
    data?: QuestionPreview;
    failure?: Failure | null;
  } | null>(null);
  const key = `${id}:${questionId}`;
  const current = result?.key === key && result.read === read ? result : null;
  useEffect(() => {
    const scope = new AbortController();
    void read(id, questionId, scope.signal)
      .then((data) => {
        if (!scope.signal.aborted) setResult({ key, read, data });
      })
      .catch((failure) => {
        if (!scope.signal.aborted) setResult({ key, read, failure: toFailure(failure) });
      });
    return () => scope.abort();
  }, [id, questionId, key, read]);
  return {
    data: current?.data ?? null,
    loading: !current,
    error: current?.failure?.message ?? null,
    failure: current?.failure ?? null,
  };
}
