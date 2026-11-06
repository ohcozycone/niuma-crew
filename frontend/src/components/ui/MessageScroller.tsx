import { MessageScroller as Primitive } from "@shadcn/react/message-scroller";
import type { ComponentProps } from "react";
import { ArrowDown } from "lucide-react";
import { cn } from "@/lib/utils";

export const MessageScrollerProvider = Primitive.Provider;
export const MessageScrollerItem = Primitive.Item;
export { useMessageScroller, useMessageScrollerVisibility } from "@shadcn/react/message-scroller";

export function MessageScroller({ className, ...props }: ComponentProps<typeof Primitive.Root>) {
  return (
    <Primitive.Root className={cn("relative flex min-h-0 flex-1 flex-col", className)} {...props} />
  );
}

export function MessageScrollerViewport({
  className,
  ...props
}: ComponentProps<typeof Primitive.Viewport>) {
  return (
    <Primitive.Viewport
      className={cn(
        "min-h-0 flex-1 overflow-y-auto overscroll-contain [overflow-anchor:none] data-pending-scroll:invisible",
        className,
      )}
      {...props}
    />
  );
}

export function MessageScrollerContent({
  className,
  ...props
}: ComponentProps<typeof Primitive.Content>) {
  return (
    <Primitive.Content
      className={cn("flex min-w-0 flex-col gap-(--os-space-8)", className)}
      {...props}
    />
  );
}

export function MessageScrollerButton({
  onClick,
  forceVisible = false,
}: {
  onClick?: () => void;
  forceVisible?: boolean;
}) {
  const className =
    "absolute bottom-0 left-1/2 z-10 flex size-10 -translate-x-1/2 items-center justify-center rounded-full border border-border bg-surface text-text shadow-popover transition-opacity";
  if (forceVisible)
    return (
      <button
        type="button"
        aria-label="回到最新消息"
        title="回到最新消息"
        className={className}
        onClick={onClick}
      >
        <ArrowDown size={18} />
      </button>
    );
  return (
    <Primitive.Button
      aria-label="回到最新消息"
      title="回到最新消息"
      onClick={(event) => {
        // 宿主先刷新最新窗口；失败时保留当前位置，不能提前执行默认滚动。
        if (onClick) {
          event.preventDefault();
          onClick();
        }
      }}
      className={cn(
        className,
        "data-[active=false]:pointer-events-none data-[active=false]:opacity-0",
      )}
    >
      <ArrowDown size={18} />
    </Primitive.Button>
  );
}
