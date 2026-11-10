import { useEffect, useState } from "react";
import { readDraft, readStaleDraft } from "@/lib/draft";

export function useDraft<T>(key: string, baseline: T, options?: { preserveStale: boolean }) {
  const [value, setValue] = useState<T>(() => readDraft(key, baseline));
  const [stale, setStale] = useState<T | null>(() =>
    options?.preserveStale ? readStaleDraft(key, baseline) : null,
  );
  useEffect(() => {
    if (stale) return;
    try {
      if (JSON.stringify(value) === JSON.stringify(baseline)) sessionStorage.removeItem(key);
      else
        sessionStorage.setItem(key, JSON.stringify({ baseline: JSON.stringify(baseline), value }));
    } catch {
      /* Storage denial must not prevent editing. */
    }
  }, [key, baseline, value, stale]);
  return [
    value,
    setValue,
    {
      stale,
      restore: () => {
        if (stale) setValue(stale);
        setStale(null);
      },
      discard: () => {
        setValue(baseline);
        setStale(null);
      },
    },
  ] as const;
}
