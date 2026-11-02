import { Link } from "react-router";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

export function PageBreadcrumb({
  parent,
  current,
  heading = false,
  className,
}: {
  parent?: { label: string; to: string };
  current: string;
  heading?: boolean;
  className?: string;
}) {
  const Current = heading ? "h1" : "span";
  return (
    <nav
      aria-label="面包屑"
      className={cn(
        "flex min-w-0 items-center gap-(--os-space-2) whitespace-nowrap text-[length:var(--os-text-caption)]",
        className,
      )}
    >
      {parent && (
        <>
          <Link
            to={parent.to}
            aria-label={`返回${parent.label}`}
            className="shrink-0 text-text-muted no-underline hover:text-text hover:underline hover:underline-offset-3"
          >
            {parent.label}
          </Link>
          <ChevronRight size={12} className="shrink-0 text-text-muted" aria-hidden="true" />
        </>
      )}
      <Current
        aria-current="page"
        className="min-w-0 truncate text-[length:var(--os-text-caption)] font-normal text-text"
        title={current}
      >
        {current}
      </Current>
    </nav>
  );
}
