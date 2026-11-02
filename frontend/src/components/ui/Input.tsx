import type { StyledProps } from "./styledProps";
// Adapted from shadcn/ui (MIT). Project UI component; see THIRD_PARTY_NOTICES.md.
import { Input as Primitive } from "@base-ui/react/input";
import { cn } from "@/lib/utils";

function Input({ className, type, ...props }: StyledProps<Primitive.Props>) {
  return (
    <Primitive
      type={type}
      data-slot="input"
      className={cn(
        "[@media(pointer:coarse)]:min-h-(--os-target-touch) h-[var(--os-control-default)] w-full min-w-0 rounded-field border border-input bg-surface px-3 py-1 text-body leading-normal shadow-none max-[600px]:text-base transition-[color,border-color,box-shadow] outline-none selection:bg-action selection:text-action-text file:inline-flex file:h-7 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-text placeholder:text-text-muted disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 md:leading-5",
        "focus:border-field-focus focus:ring-[3px] focus:ring-field-focus/50 aria-invalid:border-danger aria-invalid:focus:border-danger aria-invalid:focus:ring-danger/20",
        className,
      )}
      {...props}
    />
  );
}

export { Input };
