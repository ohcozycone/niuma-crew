import { Card, CardFooter } from "@/components/ui/Card";
import { useDelayedPending } from "@/hooks/useDelayedPending";
import { cn } from "@/lib/utils";

export type LoadingShape =
  | "employees"
  | "cards"
  | "connections"
  | "table"
  | "form"
  | "field"
  | "detail"
  | "conversation"
  | "document";

function Block({ className }: { className?: string }) {
  return <div className={cn("rounded-small bg-muted", className)} />;
}

/** 只描述占位结构，真实数据与读取生命周期由宿主持有。 */
export function LoadingSkeleton({ shape = "table" }: { shape?: LoadingShape }) {
  if (shape === "employees" || shape === "cards" || shape === "connections")
    return (
      <div
        aria-hidden="true"
        className={
          shape === "employees"
            ? "employee-grid"
            : shape === "connections"
              ? "connection-grid"
              : "capability-grid"
        }
      >
        {Array.from({ length: shape === "connections" ? 2 : 4 }, (_, i) => (
          <Card key={i} interactive={false} className="p-(--os-card-padding)">
            {shape === "employees" ? (
              <>
                <div className="mt-6 flex min-h-22 items-center gap-(--os-card-gap)">
                  <Block className="h-22 w-24 shrink-0 rounded-panel" />
                  <div className="min-w-0 flex-1 space-y-3">
                    <Block className="h-5 w-3/4" />
                    <Block className="h-3 w-1/2" />
                    <Block className="h-3 w-1/3" />
                  </div>
                </div>
                <div className="my-3 min-h-12 space-y-3">
                  <Block className="h-3 w-full" />
                  <Block className="h-3 w-3/4" />
                </div>
              </>
            ) : (
              <div className="min-h-28 space-y-4">
                <Block className="h-5 w-1/2" />
                <Block className="h-3 w-full" />
                <Block className="h-3 w-3/4" />
              </div>
            )}
            <CardFooter>
              <Block className="h-3 w-20" />
              <Block className="h-8 w-24" />
            </CardFooter>
          </Card>
        ))}
      </div>
    );
  if (shape === "field")
    return (
      <div aria-hidden="true">
        <Block className="h-10 w-56 max-w-full" />
      </div>
    );
  if (shape === "form")
    return (
      <div aria-hidden="true" className="max-w-2xl space-y-6">
        {Array.from({ length: 3 }, (_, i) => (
          <div key={i} className="space-y-3">
            <Block className="h-3 w-24" />
            <Block className={i === 2 ? "h-32 w-full" : "h-10 w-full"} />
          </div>
        ))}
      </div>
    );
  if (shape === "detail")
    return (
      <div aria-hidden="true" className="space-y-6">
        <div className="flex items-center gap-6">
          <Block className="h-28 w-24 shrink-0 rounded-panel" />
          <div className="flex-1 space-y-4">
            <Block className="h-7 w-1/3" />
            <Block className="h-3 w-3/4" />
            <Block className="h-8 w-1/2" />
          </div>
        </div>
        <Block className="h-9 w-full" />
        <LoadingSkeleton shape="table" />
      </div>
    );
  if (shape === "conversation")
    return (
      <div aria-hidden="true" className="flex min-h-80 flex-col gap-6">
        <Block className="h-6 w-40" />
        <Block className="ml-auto h-16 w-1/2" />
        <div className="space-y-3">
          <Block className="h-3 w-3/4" />
          <Block className="h-3 w-2/3" />
          <Block className="h-3 w-1/2" />
        </div>
        <Block className="mt-12 h-20 w-full" />
      </div>
    );
  if (shape === "document")
    return (
      <div aria-hidden="true" className="max-w-prose space-y-4">
        <Block className="mb-8 h-7 w-1/2" />
        {Array.from({ length: 8 }, (_, i) => (
          <Block key={i} className={i % 3 === 2 ? "h-3 w-2/3" : "h-3 w-full"} />
        ))}
      </div>
    );
  return (
    <div aria-hidden="true" className="divide-y divide-border border-y border-border">
      {Array.from({ length: 4 }, (_, i) => (
        <div key={i} className="flex items-center gap-4 py-5">
          <Block className="h-8 w-8 shrink-0" />
          <div className="flex-1 space-y-3">
            <Block className="h-4 w-1/3" />
            <Block className="h-3 w-2/3" />
          </div>
          <Block className="h-6 w-16" />
        </div>
      ))}
    </div>
  );
}

export function LoadingFeedback({
  pending = true,
  refreshing = false,
  page = false,
  shape = "table",
  label = refreshing ? "正在更新内容…" : "正在加载内容…",
  className,
}: {
  pending?: boolean;
  refreshing?: boolean;
  page?: boolean;
  shape?: LoadingShape;
  label?: string;
  className?: string;
}) {
  const visible = useDelayedPending(pending);
  if (!visible) return null;
  return (
    <div role="status" aria-live="polite" className={cn("min-w-0", className)}>
      <span className="sr-only">{label}</span>
      {refreshing ? (
        <span aria-hidden="true" className="block h-0.5 w-12 rounded-full bg-brand/60" />
      ) : (
        <>
          {page && (
            <div aria-hidden="true">
              <div className="mb-(--os-heading-content-gap) space-y-4">
                <Block className="h-7 w-40" />
                <Block className="h-4 w-2/3 max-w-sm" />
              </div>
              {shape === "employees" && (
                <>
                  <Block className="h-10 w-full" />
                  <div className="my-4 flex flex-wrap gap-3">
                    <Block className="h-9 w-80 max-w-full" />
                    <Block className="h-9 w-32" />
                  </div>
                </>
              )}
            </div>
          )}
          <LoadingSkeleton shape={shape} />
        </>
      )}
    </div>
  );
}

export function NavigationProgress({ pending }: { pending: boolean }) {
  const visible = useDelayedPending(pending);
  return (
    <div className="pointer-events-none relative h-0 shrink-0" role="status" aria-live="polite">
      {visible && (
        <>
          <span className="sr-only">正在打开页面…</span>
          <div
            aria-hidden="true"
            className="navigation-progress absolute inset-x-0 top-0 z-10 h-0.5 overflow-hidden bg-brand/10"
          >
            <span className="block h-full w-1/3 bg-brand" />
          </div>
        </>
      )}
    </div>
  );
}
