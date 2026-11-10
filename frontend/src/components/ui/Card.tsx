import { createElement, type ComponentPropsWithRef } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const cardVariants = cva(
  "min-w-0 border-solid [border-width:var(--os-card-border-width)] border-card-border bg-surface",
  {
    variants: {
      variant: {
        plain: "border-0 bg-transparent shadow-none",
        raised: "bg-raised [box-shadow:var(--os-shadow-card)]",
        outline: "shadow-none",
        muted: "border-0 bg-muted shadow-none",
        empty: "border-dashed border-border bg-transparent shadow-none",
      },
      radius: {
        none: "rounded-none",
        card: "rounded-card",
        panel: "rounded-panel",
        control: "rounded-control",
      },
      interactive: {
        true: "[transition:box-shadow_var(--os-motion-normal)_ease] [@media(hover:_hover)]:[&:hover]:[box-shadow:var(--os-shadow-hover)]",
      },
    },
    defaultVariants: { variant: "raised", radius: "card", interactive: false },
  },
);
type CardElement = "div" | "article" | "section" | "form" | "fieldset" | "details" | "ul" | "p";
type CardProps<Element extends CardElement = "div"> = ComponentPropsWithRef<Element> &
  VariantProps<typeof cardVariants> & { as?: Element };

/** Owns surface styling; business cards retain their content, semantics and actions. */
export function Card<Element extends CardElement = "div">({
  as,
  variant = "raised",
  radius = "card",
  interactive,
  className,
  ...props
}: CardProps<Element>) {
  return createElement(as ?? "div", {
    ...props,
    "data-slot": "card",
    "data-variant": variant,
    className: cn(
      cardVariants({ variant, radius, interactive: interactive ?? variant === "raised" }),
      className,
    ),
  });
}

export function CardFooter({ className, ...props }: ComponentPropsWithRef<"div">) {
  return (
    <div
      data-slot="card-footer"
      className={cn(
        "flex flex-wrap items-center justify-between gap-2 border-t border-border pt-(--os-space-3)",
        className,
      )}
      {...props}
    />
  );
}

/** Shared resource-card spacing, also used by employee cards. */
export function CardContent({ className, ...props }: ComponentPropsWithRef<"div">) {
  return (
    <div
      data-slot="card-content"
      className={cn("relative grid p-(--os-card-padding)", className)}
      {...props}
    />
  );
}
