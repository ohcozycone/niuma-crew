// Adapted from shadcn/ui (MIT). Project UI component; see THIRD_PARTY_NOTICES.md.
import * as React from "react";
import { cn } from "@/lib/utils";

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "flex field-sizing-content min-h-16 min-w-0 w-full rounded-field border border-input bg-surface px-3 py-2 text-body leading-normal shadow-none max-[600px]:text-base transition-[color,border-color,box-shadow] outline-none placeholder:text-text-muted disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-danger md:leading-5",
        "focus:border-field-focus focus:ring-[3px] focus:ring-field-focus/50 aria-invalid:focus:border-danger aria-invalid:focus:ring-danger/20",
        className,
      )}
      {...props}
    />
  );
}

export { Textarea };
