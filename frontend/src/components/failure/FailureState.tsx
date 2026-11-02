import { useState } from "react";
import { failureIllustrations } from "@/lib/failures/catalog";
import { resolveFailure, toFailure } from "@/lib/failures/resolve";
import type { Failure, FailureAction, FailureContext, FailureFamily } from "@/lib/failures/types";
import { cn } from "@/lib/utils";
import { FailureActions } from "./FailureActions";

export type FailureStateProps = {
  failure?: Failure | null;
  error?: unknown;
  context?: FailureContext;
  actions?: readonly FailureAction[];
  title?: string;
  description?: string;
  className?: string;
  layout?: "page" | "section";
  illustration?: boolean;
};

function Illustration({ family }: { family: FailureFamily }) {
  const [failed, setFailed] = useState(false);
  return failed ? null : (
    <figure className="failure-art" aria-hidden="true">
      <img
        src={failureIllustrations[family]}
        alt=""
        width={720}
        height={720}
        onError={() => setFailed(true)}
      />
    </figure>
  );
}

export function FailureState({
  failure,
  error,
  context = { operation: "initial-read" },
  actions = [],
  title,
  description,
  className,
  layout = "section",
  illustration = true,
}: FailureStateProps) {
  const fact = failure ?? toFailure(error);
  if (!fact) return null;
  const view = resolveFailure(fact, context, actions);
  const text = description ?? view.description;
  return (
    <section
      data-slot="failure-state"
      data-family={view.family}
      aria-label={title ?? view.title}
      className={cn("failure-region", layout === "page" && "failure-page", className)}
    >
      <div className="failure-content">
        {illustration && <Illustration key={view.family} family={view.family} />}
        <div className="failure-copy">
          <div className="failure-message" role="alert">
            {view.displayCode && (
              <p className="failure-status" aria-label={`错误码 ${view.displayCode}`}>
                {view.displayCode}
              </p>
            )}
            <h1>{title ?? view.title}</h1>
            {text && <p className="failure-description">{text}</p>}
          </div>
          <FailureActions
            key={`${fact.code}:${fact.retryAt ?? ""}`}
            actions={view.actions}
            retryAt={view.retryAt}
          />
          {view.requestId && <p className="failure-reference">问题编号：{view.requestId}</p>}
        </div>
      </div>
    </section>
  );
}
