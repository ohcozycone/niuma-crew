import { type ReactNode } from "react";
import { Search } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { cn } from "@/lib/utils";

export function EmptyState({
  text,
  description,
  icon,
  onReset,
  resetLabel = "清除筛选",
  boxed = false,
  density = "default",
  headingLevel = 2,
  className,
  children,
}: {
  text: ReactNode;
  description?: ReactNode;
  icon?: ReactNode;
  onReset?: () => void;
  resetLabel?: string;
  boxed?: boolean;
  density?: "default" | "compact";
  headingLevel?: 2 | 3 | false;
  className?: string;
  children?: ReactNode;
}) {
  const Heading = headingLevel === false ? "p" : headingLevel === 3 ? "h3" : "h2";
  const details =
    description !== undefined ? description : onReset ? "更换关键词，或清除筛选重新查看。" : null;
  const content = (
    <>
      {icon ?? <Search size={28} strokeWidth={1.4} aria-hidden="true" />}
      <Heading className={headingLevel ? "type-title" : "text-sm"}>{text}</Heading>
      {details && <p className="text-sm text-text-muted">{details}</p>}
      {onReset && (
        <Button type="button" variant="outline" onClick={onReset}>
          {resetLabel}
        </Button>
      )}
      {children}
    </>
  );
  const classes = cn(
    "flex min-w-0 flex-col items-center gap-3.5 px-4 text-center text-text-muted",
    density === "compact" ? "py-8" : "py-15",
    className,
  );
  return boxed ? (
    <Card variant="empty" radius="panel" className={classes}>
      {content}
    </Card>
  ) : (
    <div data-slot="empty-state" className={classes}>
      {content}
    </div>
  );
}
