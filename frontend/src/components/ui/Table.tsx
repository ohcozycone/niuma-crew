import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

// Native table semantics; business columns and responsive layouts stay with the caller.
export function Table({ className, ...props }: ComponentProps<"table">) {
  return (
    <table
      data-slot="table"
      className={cn("w-full table-fixed text-left text-sm", className)}
      {...props}
    />
  );
}
export function TableHeader({ className, ...props }: ComponentProps<"thead">) {
  return (
    <thead
      className={cn("border-b border-border bg-muted/50 text-xs text-text-muted", className)}
      {...props}
    />
  );
}
export function TableBody({ className, ...props }: ComponentProps<"tbody">) {
  return <tbody className={cn("divide-y divide-border", className)} {...props} />;
}
export function TableRow({ className, ...props }: ComponentProps<"tr">) {
  return <tr className={cn("transition-colors hover:bg-muted/50", className)} {...props} />;
}
export function TableHead({ className, ...props }: ComponentProps<"th">) {
  return <th scope="col" className={cn("h-10 px-4 font-medium", className)} {...props} />;
}
export function TableCell({ className, ...props }: ComponentProps<"td">) {
  return <td className={cn("px-4 py-3 align-middle", className)} {...props} />;
}
