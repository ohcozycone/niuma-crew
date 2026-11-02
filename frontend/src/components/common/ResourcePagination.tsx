import { useSearchParams } from "react-router";
import { Button } from "@/components/ui/Button";

export function ResourcePagination({
  total,
  prefix = "",
  onRefresh,
  loading = false,
}: {
  total: number;
  prefix?: string;
  onRefresh?: () => void;
  loading?: boolean;
}) {
  const [params, setParams] = useSearchParams();
  const offset = Math.max(0, Number(params.get(prefix + "offset")) || 0);
  function page(next: number) {
    setParams(
      (current) => {
        const result = new URLSearchParams(current);
        result.set(prefix + "offset", String(next));
        return result;
      },
      { preventScrollReset: true },
    );
  }
  return (
    <div
      className="mt-6 flex flex-wrap items-center justify-end gap-4 text-sm text-text-muted"
      aria-busy={loading}
    >
      {onRefresh && (
        <Button size="sm" variant="ghost" disabled={loading} onClick={onRefresh}>
          {loading ? "刷新中…" : "刷新"}
        </Button>
      )}
      <span>
        共 {total} 项 · 第 {Math.floor(offset / 20) + 1} 页
      </span>
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="outline"
          disabled={loading || offset === 0}
          onClick={() => page(Math.max(0, offset - 20))}
        >
          上一页
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={loading || offset + 20 >= total}
          onClick={() => page(offset + 20)}
        >
          下一页
        </Button>
      </div>
    </div>
  );
}
