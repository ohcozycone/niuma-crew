// Adapted from shadcn/ui (MIT). Project UI component; see THIRD_PARTY_NOTICES.md.
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";
import { useRender } from "@base-ui/react/use-render";

const badgeVariants = cva(
  "inline-flex w-fit shrink-0 items-center justify-center gap-1 overflow-hidden rounded-small border border-border px-2 py-0.5 text-xs font-medium whitespace-nowrap transition-[color,box-shadow] focus-visible:border-focus focus-visible:ring-[3px] focus-visible:ring-focus/50 aria-invalid:border-danger aria-invalid:ring-danger/20 [&>svg]:pointer-events-none [&>svg]:size-3",
  {
    variants: {
      variant: {
        default: "bg-action text-action-text [a&]:hover:bg-action/90",
        secondary: "bg-selected text-text [a&]:hover:bg-selected/90",
        destructive:
          "bg-danger text-danger-text focus-visible:ring-danger/20 [a&]:hover:bg-danger/90",
        outline: "border-border text-text [a&]:hover:bg-muted [a&]:hover:text-text",
        ghost: "[a&]:hover:bg-muted [a&]:hover:text-text",
        link: "text-action underline-offset-4 [a&]:hover:underline",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

function Badge({
  className,
  variant = "default",
  render,
  ...props
}: useRender.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return useRender({
    defaultTagName: "span",
    render,
    props: {
      ...props,
      "data-slot": "badge",
      "data-variant": variant,
      className: cn(badgeVariants({ variant }), className),
    },
  });
}

export { Badge, badgeVariants };
