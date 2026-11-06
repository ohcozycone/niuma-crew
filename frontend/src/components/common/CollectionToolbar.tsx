import type { ReactNode } from "react";

export function CollectionToolbar({
  label,
  children,
  summary,
}: {
  label: string;
  children: ReactNode;
  summary?: ReactNode;
}) {
  return (
    <div role="search" aria-label={label} className="mb-6 flex flex-wrap items-center gap-3">
      {children}
      {summary && <span className="type-caption ml-auto">{summary}</span>}
    </div>
  );
}
