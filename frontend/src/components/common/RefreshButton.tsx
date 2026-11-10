import { useDelayedPending } from "@/hooks/useDelayedPending";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/Button";

export function RefreshButton({
  onClick,
  loading = false,
  label = "刷新列表",
  showProgress = true,
}: {
  onClick: () => void;
  loading?: boolean;
  label?: string;
  showProgress?: boolean;
}) {
  const visible = useDelayedPending(loading && showProgress);
  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      loading={visible}
      disabled={loading}
      aria-busy={loading}
      onClick={onClick}
      aria-label={label}
    >
      <RefreshCw aria-hidden="true" />
      刷新
    </Button>
  );
}
