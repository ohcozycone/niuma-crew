// Adapted from the official shadcn/ui Base UI registry (MIT). See THIRD_PARTY_NOTICES.md.
import { PreviewCard as Primitive } from "@base-ui/react/preview-card";
import { cn } from "@/lib/utils";
import type { StyledProps } from "./styledProps";

const HoverCard = Primitive.Root;
const HoverCardTrigger = Primitive.Trigger;

function HoverCardContent({
  className,
  side = "bottom",
  sideOffset = 4,
  align = "center",
  alignOffset = 0,
  ...props
}: StyledProps<Primitive.Popup.Props> &
  Pick<Primitive.Positioner.Props, "align" | "alignOffset" | "side" | "sideOffset">) {
  return (
    <Primitive.Portal>
      <Primitive.Positioner
        side={side}
        sideOffset={sideOffset}
        align={align}
        alignOffset={alignOffset}
        collisionPadding={16}
        className="isolate z-50"
      >
        <Primitive.Popup
          data-slot="hover-card-content"
          className={cn(
            "w-80 max-w-[calc(100vw-32px)] max-h-(--available-height) overflow-y-auto rounded-panel border border-border bg-surface p-4 text-sm text-text shadow-popover outline-none",
            className,
          )}
          {...props}
        />
      </Primitive.Positioner>
    </Primitive.Portal>
  );
}
export { HoverCard, HoverCardTrigger, HoverCardContent };
