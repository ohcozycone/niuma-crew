import { useEffect, useState } from "react";

/** 只延迟反馈，不延迟工作；每次等待结束或卸载都会释放计时器。 */
export function useDelayedPending(pending: boolean, delay = 200) {
  const [state, setState] = useState({ pending, visible: false });
  if (state.pending !== pending) setState({ pending, visible: false });
  useEffect(() => {
    if (!pending) return;
    const timer = window.setTimeout(() => setState({ pending: true, visible: true }), delay);
    return () => window.clearTimeout(timer);
  }, [pending, delay]);
  return pending && state.pending && state.visible;
}
