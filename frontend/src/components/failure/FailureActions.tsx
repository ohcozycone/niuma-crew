import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { toFailure } from "@/lib/failures/resolve";
import type { FailureAction } from "@/lib/failures/types";

export function FailureActions({
  actions,
  retryAt,
}: {
  actions: readonly FailureAction[];
  retryAt?: number;
}) {
  const [busy, setBusy] = useState<number | null>(null);
  const inFlight = useRef(false);
  const [error, setError] = useState("");
  const [remaining, setRemaining] = useState(() =>
    retryAt ? Math.max(0, Math.ceil((retryAt - Date.now()) / 1000)) : 0,
  );
  useEffect(() => {
    if (!retryAt) return;
    const tick = () => {
      const seconds = Math.max(0, Math.ceil((retryAt - Date.now()) / 1000));
      setRemaining(seconds);
      if (!seconds) clearInterval(timer);
    };
    const timer = setInterval(tick, 1000);
    tick();
    return () => clearInterval(timer);
  }, [retryAt]);
  if (!actions.length) return null;
  async function run(action: FailureAction, index: number) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(index);
    setError("");
    try {
      await action.onClick?.();
    } catch (failure) {
      setError(toFailure(failure)?.message ?? "");
    } finally {
      inFlight.current = false;
      setBusy(null);
    }
  }
  return (
    <div className="failure-recovery">
      <div className="failure-actions">
        {actions.map((action, index) => {
          const disabled =
            action.disabled || busy !== null || (action.kind === "retry" && remaining > 0);
          return action.href && !disabled ? (
            <Button
              key={`${index}:${action.label}`}
              render={<a href={action.href} />}
              nativeButton={false}
              role="link"
              variant={index ? "outline" : "default"}
            >
              {action.label}
            </Button>
          ) : (
            <Button
              key={`${index}:${action.label}`}
              type="button"
              disabled={disabled}
              variant={index ? "outline" : "default"}
              onClick={() => void run(action, index)}
            >
              {busy === index ? "正在处理…" : action.label}
            </Button>
          );
        })}
      </div>
      {remaining > 0 && actions.some((action) => action.kind === "retry") && (
        <p className="failure-wait">
          可在{" "}
          {remaining >= 3600
            ? `${Math.ceil(remaining / 3600)} 小时`
            : remaining >= 60
              ? `${Math.ceil(remaining / 60)} 分钟`
              : `${remaining} 秒`}
          后重试
        </p>
      )}
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
