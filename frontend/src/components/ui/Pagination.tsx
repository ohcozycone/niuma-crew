// Adapted from shadcn/ui (MIT). See THIRD_PARTY_NOTICES.md.
import type { ComponentProps } from "react";
import { ChevronLeft, ChevronRight, MoreHorizontal } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "./Button";

export function Pagination({ className, ...props }: ComponentProps<"nav">) {
  return (
    <nav aria-label="分页" data-slot="pagination" className={cn("w-fit", className)} {...props} />
  );
}

export function PaginationContent({ className, ...props }: ComponentProps<"ul">) {
  return (
    <ul
      data-slot="pagination-content"
      className={cn("flex items-center gap-1", className)}
      {...props}
    />
  );
}

export function PaginationItem(props: ComponentProps<"li">) {
  return <li data-slot="pagination-item" {...props} />;
}

export function PaginationLink({
  isActive = false,
  ...props
}: ComponentProps<typeof Button> & { isActive?: boolean }) {
  return (
    <Button
      type="button"
      size="icon-sm"
      variant={isActive ? "outline" : "ghost"}
      aria-current={isActive ? "page" : undefined}
      {...props}
    />
  );
}

export function PaginationPrevious(props: ComponentProps<typeof PaginationLink>) {
  return (
    <PaginationLink aria-label="上一页" {...props}>
      <ChevronLeft aria-hidden="true" />
    </PaginationLink>
  );
}

export function PaginationNext(props: ComponentProps<typeof PaginationLink>) {
  return (
    <PaginationLink aria-label="下一页" {...props}>
      <ChevronRight aria-hidden="true" />
    </PaginationLink>
  );
}

export function PaginationEllipsis() {
  return (
    <span
      aria-hidden="true"
      className="flex size-(--os-control-small) items-center justify-center text-text-muted [@media(pointer:coarse)]:size-(--os-target-touch)"
    >
      <MoreHorizontal className="size-4" />
    </span>
  );
}
