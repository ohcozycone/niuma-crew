import type { StyledProps } from "./styledProps";
// Adapted from shadcn/ui (MIT). Project UI component; see THIRD_PARTY_NOTICES.md.
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";
import { Button as Primitive } from "@base-ui/react/button";
import { LoaderCircle } from "lucide-react";

const buttonVariants = cva(
  "[@media(pointer:coarse)]:min-h-(--os-target-touch) [@media(pointer:coarse)]:min-w-(--os-target-touch) relative inline-flex shrink-0 items-center justify-center gap-2 rounded-control border border-transparent text-body leading-5 font-medium whitespace-nowrap text-text transition-[color,background-color,border-color,box-shadow] duration-fast motion-reduce:transition-none outline-none focus-visible:ring-[3px] focus-visible:ring-focus/50 disabled:pointer-events-none data-disabled:pointer-events-none button-availability aria-invalid:border-danger aria-invalid:ring-danger/20 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4 data-loading:[&>svg:not([data-slot=button-spinner])]:hidden",
  {
    variants: {
      variant: {
        default: "bg-action text-action-text hover:bg-action-hover active:bg-action-pressed",
        destructive:
          "bg-danger-action text-danger-action-text hover:bg-danger-action-hover active:bg-danger-action-pressed focus-visible:ring-danger/30",
        "destructive-ghost":
          "text-danger hover:bg-danger-bg active:bg-danger-bg focus-visible:ring-danger/30",
        outline: "border-border bg-raised hover:border-input hover:bg-hover active:bg-pressed",
        secondary:
          "bg-action-soft text-action-soft-text hover:bg-action-soft-hover active:bg-action-soft-pressed",
        ghost:
          "text-text-muted hover:bg-hover hover:text-hover-text active:bg-pressed aria-pressed:bg-action-soft aria-pressed:text-action-soft-text aria-pressed:hover:bg-action-soft-hover aria-pressed:active:bg-action-soft-pressed",
        link: "text-brand-text underline-offset-4 hover:underline active:text-text",
      },
      size: {
        default: "h-[var(--os-control-default)] px-4 py-2 has-[>svg]:px-3",
        xs: "h-6 gap-1 px-2 text-xs leading-4 has-[>svg]:px-1.5 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-[var(--os-control-small)] gap-1.5 px-3 text-[length:var(--os-text-support)] has-[>svg]:px-2.5",
        lg: "h-[var(--os-control-large)] rounded-control px-6 has-[>svg]:px-4",
        icon: "size-[var(--os-control-default)]",
        "icon-xs": "size-6 rounded-control [&_svg:not([class*='size-'])]:size-3",
        "icon-sm": "size-[var(--os-control-small)]",
        "icon-lg": "size-[var(--os-control-large)]",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

function Button({
  className,
  variant = "default",
  size = "default",
  loading = false,
  disabled,
  children,
  "aria-busy": ariaBusy,
  ...props
}: StyledProps<Primitive.Props> & VariantProps<typeof buttonVariants> & { loading?: boolean }) {
  return (
    <Primitive
      data-slot="button"
      data-variant={variant}
      data-size={size}
      data-loading={loading || undefined}
      disabled={disabled || loading}
      aria-busy={loading || ariaBusy || undefined}
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    >
      {loading && (
        <LoaderCircle
          data-slot="button-spinner"
          className="motion-safe:animate-spin"
          aria-hidden="true"
        />
      )}
      {children}
    </Primitive>
  );
}

export { Button, buttonVariants };
