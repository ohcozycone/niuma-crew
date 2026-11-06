import { useRef, useState } from "react";
import { useEditing } from "./useEditing";
import { useFailureState } from "@/state/shared/useFailureState";

/** 完整表单的保存与离页保护；收藏等轻量操作使用各自记录的请求锁。 */
export function useSaveOperation() {
  const [saving, setSaving] = useState(false);
  const { failure, error, setError, clearError } = useFailureState();
  const locked = useRef(false);
  const { setSaving: setNavigationSaving } = useEditing();
  async function run<T>(action: () => Promise<T>): Promise<T> {
    if (locked.current) throw new Error("正在保存，请稍候。");
    locked.current = true;
    setSaving(true);
    setNavigationSaving(true);
    setError("");
    try {
      return await action();
    } finally {
      locked.current = false;
      setSaving(false);
      setNavigationSaving(false);
    }
  }
  return { saving, error, failure, setError, clearError, run };
}
