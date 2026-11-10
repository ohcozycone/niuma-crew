import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

/** Layout only: the caller keeps the action order and each button's meaning. */
export function ButtonGroup({
  className,
  align = "end",
  ...props
}: ComponentProps<"div"> & { align?: "start" | "end" }) {
  return (
    <div
      data-slot="button-group"
      className={cn(
        "flex min-w-0 flex-wrap items-center gap-2",
        align === "end" ? "justify-end" : "justify-start",
        className,
      )}
      {...props}
    />
  );
}
