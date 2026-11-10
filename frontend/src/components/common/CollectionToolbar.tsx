import type { ReactNode } from "react";

export function CollectionToolbar({
  label,
  children,
  summary,
  actions,
}: {
  label: string;
  children: ReactNode;
  summary?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div role="search" aria-label={label} className="mb-6 flex flex-wrap items-center gap-3">
      {children}
      {(summary || actions) && (
        <div className="ml-auto flex flex-wrap items-center gap-3">
          {summary && <span className="type-caption">{summary}</span>}
          {actions}
        </div>
      )}
    </div>
  );
}
