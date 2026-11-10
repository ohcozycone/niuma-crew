// Adapted from shadcn/ui (MIT). See THIRD_PARTY_NOTICES.md.
import * as React from "react";
import { mergeProps } from "@base-ui/react/merge-props";
import { useRender } from "@base-ui/react/use-render";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

function BubbleGroup({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div data-slot="bubble-group" className={cn("flex min-w-0 flex-col", className)} {...props} />
  );
}

const bubbleVariants = cva(
  "group/bubble relative flex w-fit max-w-full min-w-0 flex-col rounded-card px-4 py-3",
  {
    variants: {
      variant: {
        default: "bg-selected text-text",
        secondary: "bg-muted text-text",
        muted: "bg-muted text-text-muted",
        tinted: "bg-selected text-text",
        outline: "border border-border",
        ghost: "bg-transparent",
        destructive: "bg-danger-bg text-danger",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

function Bubble({
  variant = "default",
  align = "start",
  className,
  ...props
}: React.ComponentProps<"div"> &
  VariantProps<typeof bubbleVariants> & {
    align?: "start" | "end";
  }) {
  return (
    <div
      data-slot="bubble"
      data-variant={variant}
      data-align={align}
      className={cn(bubbleVariants({ variant }), className)}
      {...props}
    />
  );
}

function BubbleContent({ className, render, ...props }: useRender.ComponentProps<"div">) {
  return useRender({
    defaultTagName: "div",
    props: mergeProps<"div">(
      {
        className: cn(
          "w-fit max-w-full min-w-0 wrap-break-word [button]:text-left [button,a]:transition-colors",
          className,
        ),
      },
      props,
    ),
    render,
    state: {
      slot: "bubble-content",
    },
  });
}

const bubbleReactionsVariants = cva("absolute z-10 flex w-fit items-center justify-center", {
  variants: {
    side: {
      top: "",
      bottom: "",
    },
    align: {
      start: "",
      end: "",
    },
  },
  defaultVariants: {
    side: "bottom",
    align: "end",
  },
});

function BubbleReactions({
  side = "bottom",
  align = "end",
  className,
  ...props
}: React.ComponentProps<"div"> & {
  align?: "start" | "end";
  side?: "top" | "bottom";
}) {
  return (
    <div
      data-slot="bubble-reactions"
      data-align={align}
      data-side={side}
      className={cn(bubbleReactionsVariants({ side, align }), className)}
      {...props}
    />
  );
}

export { BubbleGroup, Bubble, BubbleContent, BubbleReactions };
