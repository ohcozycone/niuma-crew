import * as React from "react";
import { Dialog as Primitive } from "@base-ui/react/dialog";
import { XIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "./Button";
import { ButtonGroup } from "./ButtonGroup";
import type { StyledProps } from "./styledProps";
const Dialog = Primitive.Root;
const DialogTrigger = Primitive.Trigger;
const DialogClose = Primitive.Close;
const DialogPortal = Primitive.Portal;
function DialogOverlay({ className, ...props }: StyledProps<Primitive.Backdrop.Props>) {
  return (
    <Primitive.Backdrop
      data-slot="dialog-overlay"
      className={cn("fixed inset-0 z-50 bg-modal-overlay", className)}
      {...props}
    />
  );
}
function DialogContent({
  className,
  children,
  showCloseButton = true,
  size = "standard",
  layout = "center",
  ...props
}: StyledProps<Primitive.Popup.Props> & {
  showCloseButton?: boolean;
  size?: "small" | "standard" | "wide" | "workspace";
  layout?: "center" | "side";
}) {
  return (
    <DialogPortal>
      <DialogOverlay />
      <Primitive.Popup
        data-slot="dialog-content"
        className={cn(
          "fixed z-50 grid min-w-0 gap-4 border border-border bg-surface shadow-popover outline-none",
          !(layout === "center" && size === "workspace") && "dialog-surface",
          layout === "center" &&
            "dialog-center top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 rounded-card",
          layout === "center" &&
            (size === "small"
              ? "dialog-small"
              : size === "workspace"
                ? "dialog-workspace"
                : size === "wide"
                  ? "dialog-wide"
                  : "dialog-standard"),
          layout === "side" &&
            "dialog-side top-0 right-0 left-auto h-dvh translate-x-0 translate-y-0 grid-rows-[auto_minmax(0,1fr)_auto] rounded-none",
          className,
        )}
        {...props}
      >
        {children}
        {showCloseButton && (
          <DialogClose
            render={<Button variant="ghost" size="icon" className="absolute top-2 right-2" />}
          >
            <XIcon />
            <span className={"sr-only"}>关闭</span>
          </DialogClose>
        )}
      </Primitive.Popup>
    </DialogPortal>
  );
}
function DialogHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="dialog-header"
      className={cn("flex min-w-0 flex-col gap-2 pr-8 text-left", className)}
      {...props}
    />
  );
}
function DialogFooter({
  className,
  children,
  showCloseButton = false,
  ...props
}: React.ComponentProps<"div"> & { showCloseButton?: boolean }) {
  return (
    <ButtonGroup data-slot="dialog-footer" className={className} {...props}>
      {children}
      {showCloseButton && <DialogClose render={<Button variant="outline" />}>关闭</DialogClose>}
    </ButtonGroup>
  );
}
function DialogTitle({ className, ...props }: StyledProps<Primitive.Title.Props>) {
  return (
    <Primitive.Title
      data-slot="dialog-title"
      className={cn(
        "pr-6 text-section leading-snug font-semibold [overflow-wrap:anywhere]",
        className,
      )}
      {...props}
    />
  );
}
function DialogDescription({ className, ...props }: StyledProps<Primitive.Description.Props>) {
  return (
    <Primitive.Description
      data-slot="dialog-description"
      className={cn("text-sm text-text-muted", className)}
      {...props}
    />
  );
}
export {
  Dialog,
  DialogTrigger,
  DialogClose,
  DialogPortal,
  DialogOverlay,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
};
