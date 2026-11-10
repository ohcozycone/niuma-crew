import { useEffect, useLayoutEffect, useRef, useState } from "react";

export function useDebouncedInput(
  value: string,
  onChange: (value: string) => void,
  delay: number,
  disabled = false,
) {
  const [state, setState] = useState({ source: value, draft: value });
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const composing = useRef(false);
  const commit = useRef(onChange);
  // URL 导航或外部重置优先于尚未提交的输入。
  if (state.source !== value) setState({ source: value, draft: value });

  useLayoutEffect(() => {
    commit.current = onChange;
  }, [onChange]);
  useLayoutEffect(() => {
    clearTimeout(timer.current);
    composing.current = false;
  }, [value, delay, disabled]);
  useEffect(() => () => clearTimeout(timer.current), []);

  function change(next: string, immediate = false) {
    setState({ source: value, draft: next });
    clearTimeout(timer.current);
    if (immediate) composing.current = false;
    if (disabled || (delay > 0 && composing.current)) return;
    if (delay <= 0) {
      commit.current(next);
    } else if (next !== value) {
      if (immediate || next === "") commit.current(next);
      else timer.current = setTimeout(() => commit.current(next), delay);
    }
  }
  return {
    value: delay > 0 ? state.draft : value,
    change,
    startComposition() {
      composing.current = true;
      clearTimeout(timer.current);
    },
    endComposition(next: string) {
      composing.current = false;
      if (delay > 0) change(next);
    },
    isComposing: () => composing.current,
  };
}
