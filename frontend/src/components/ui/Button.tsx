import type { StyledProps } from "./styledProps";
// Adapted from shadcn/ui (MIT). Project UI component; see THIRD_PARTY_NOTICES.md.
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";
import { Button as Primitive } from "@base-ui/react/button";

const buttonVariants = cva(
  "[@media(pointer:coarse)]:min-h-(--os-target-touch) [@media(pointer:coarse)]:min-w-(--os-target-touch) inline-flex shrink-0 items-center justify-center gap-2 rounded-control text-body leading-5 duration-fast font-medium whitespace-nowrap transition-all outline-none focus-visible:border-focus focus-visible:ring-[3px] focus-visible:ring-focus/50 disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-danger aria-invalid:ring-danger/20 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default: "bg-action text-action-text hover:bg-action-hover",
        destructive: "bg-danger text-danger-text hover:bg-danger/90 focus-visible:ring-danger/20",
        outline: "border border-border bg-surface shadow-xs hover:bg-muted hover:text-text",
        secondary: "bg-selected text-text hover:bg-selected/80",
        ghost: "hover:bg-muted hover:text-text",
        link: "text-action underline-offset-4 hover:underline",
      },
      size: {
        default: "h-[var(--os-control-default)] px-4 py-2 has-[>svg]:px-3",
        xs: "h-6 gap-1 rounded-control px-2 text-body leading-[calc(4/3)] has-[>svg]:px-1.5 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-[var(--os-control-small)] gap-1.5 rounded-control px-3 has-[>svg]:px-2.5",
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
  ...props
}: StyledProps<Primitive.Props> & VariantProps<typeof buttonVariants>) {
  return (
    <Primitive
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  );
}

const ButtonBase = Primitive;
export { Button, ButtonBase, buttonVariants };
