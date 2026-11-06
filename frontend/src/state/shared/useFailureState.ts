import { useCallback, useState } from "react";
import { toFailure } from "@/lib/failures/resolve";
import type { Failure } from "@/lib/failures/types";

/** 局部错误只存一份事实；兼容文字由它派生，不拥有请求或恢复策略。 */
export function useFailureState() {
  const [failure, setFailure] = useState<Failure | null>(null);
  const setError = useCallback((error: unknown) => {
    setFailure(error === "" || error == null ? null : toFailure(error));
  }, []);
  const clearError = useCallback(() => setFailure(null), []);
  return { failure, error: failure?.message ?? "", setError, clearError };
}
