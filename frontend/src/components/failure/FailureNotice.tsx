import { AlertTriangle, Clock3, SearchX, Settings2, ShieldAlert, Unplug } from "lucide-react";
import type { ReactNode } from "react";
import { resolveFailure, toFailure } from "@/lib/failures/resolve";
import type { FailureStateProps } from "./FailureState";
import { FailureActions } from "./FailureActions";
import { cn } from "@/lib/utils";

const icons = {
  "not-found": SearchX,
  access: ShieldAlert,
  connection: Unplug,
  service: AlertTriangle,
  waiting: Clock3,
  configuration: Settings2,
};

export function FailureNotice({
  failure,
  error,
  context = { operation: "mutation" },
  actions = [],
  title,
  description,
  className,
  children,
  compact = false,
}: Omit<FailureStateProps, "layout"> & {
  children?: ReactNode;
  compact?: boolean;
}) {
  const fact = failure ?? toFailure(error);
  if (!fact) return null;
  const view = resolveFailure(fact, context, actions);
  const Icon = icons[view.family];
  return (
    <div
      data-slot="failure-notice"
      data-family={view.family}
      className={cn("failure-notice", compact && "failure-notice-compact", className)}
    >
      {!compact && <Icon size={18} strokeWidth={1.6} aria-hidden="true" />}
      <div className="failure-notice-copy">
        <div className="failure-message whitespace-pre-wrap" role="alert">
          {!compact && <p className="font-medium">{title ?? view.title}</p>}
          {(description ?? view.description) && <p>{description ?? view.description}</p>}
        </div>
        <FailureActions
          key={`${fact.code}:${fact.retryAt ?? ""}`}
          actions={view.actions}
          retryAt={view.retryAt}
        />
        {!compact && view.requestId && (
          <p className="failure-reference">问题编号：{view.requestId}</p>
        )}
        {children}
      </div>
    </div>
  );
}
