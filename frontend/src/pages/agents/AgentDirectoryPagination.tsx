import { useSearchParams } from "react-router";
import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/Pagination";

export function AgentDirectoryPagination({
  total,
  pageSize,
  loading,
}: {
  total: number;
  pageSize: number;
  loading: boolean;
}) {
  const [params, setParams] = useSearchParams();
  const offset = Math.max(0, Number(params.get("offset")) || 0);
  const count = Math.max(1, Math.ceil(total / pageSize));
  const current = Math.min(count, Math.floor(offset / pageSize) + 1);
  const pages: (number | string)[] =
    count <= 5
      ? Array.from({ length: count }, (_, index) => index + 1)
      : current <= 3
        ? [1, 2, 3, "after", count]
        : current >= count - 2
          ? [1, "before", count - 2, count - 1, count]
          : [1, "before", current, "after", count];
  function go(page: number) {
    if (loading || page < 1 || page > count || page === current) return;
    setParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        if (page === 1) next.delete("offset");
        else next.set("offset", String((page - 1) * pageSize));
        return next;
      },
      { preventScrollReset: true },
    );
  }
  if (count < 2) return null;
  return (
    <div
      className="ml-auto flex max-w-full flex-wrap items-center justify-end gap-3"
      aria-busy={loading}
    >
      <span className="type-caption whitespace-nowrap tabular-nums">共 {count} 页</span>
      <Pagination aria-label="员工分页">
        <PaginationContent className="flex-wrap justify-end">
          <PaginationItem>
            <PaginationPrevious
              disabled={loading || current === 1}
              onClick={() => go(current - 1)}
            />
          </PaginationItem>
          {pages.map((page) => (
            <PaginationItem
              key={page}
              className={page === current ? undefined : "@max-[400px]/page:hidden"}
            >
              {typeof page === "number" ? (
                <PaginationLink
                  aria-label={`第 ${page} 页`}
                  isActive={page === current}
                  disabled={loading || total === 0}
                  onClick={() => go(page)}
                >
                  {page}
                </PaginationLink>
              ) : (
                <PaginationEllipsis />
              )}
            </PaginationItem>
          ))}
          <PaginationItem>
            <PaginationNext
              disabled={loading || current === count}
              onClick={() => go(current + 1)}
            />
          </PaginationItem>
        </PaginationContent>
      </Pagination>
    </div>
  );
}
