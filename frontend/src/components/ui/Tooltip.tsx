import { Tooltip as Primitive } from "@base-ui/react/tooltip";
import { cn } from "@/lib/utils";
const Tooltip = Primitive.Root;
const TooltipTrigger = Primitive.Trigger;
function TooltipProvider({ delay = 0, ...props }: Primitive.Provider.Props) {
  return <Primitive.Provider delay={delay} {...props} />;
}
type ContentProps = Omit<Primitive.Popup.Props, "className"> &
  Pick<Primitive.Positioner.Props, "side" | "sideOffset" | "align"> & {
    className?: string;
    positionerClassName?: string;
    showArrow?: boolean;
  };
function TooltipContent({
  className,
  sideOffset = 0,
  side = "top",
  align = "center",
  positionerClassName,
  showArrow = true,
  children,
  ...props
}: ContentProps) {
  return (
    <Primitive.Portal>
      <Primitive.Positioner
        side={side}
        sideOffset={sideOffset}
        align={align}
        collisionPadding={8}
        className={cn("z-50", positionerClassName)}
      >
        <Primitive.Popup
          data-slot="tooltip-content"
          className={cn(
            "w-fit max-w-[min(var(--os-tooltip-max),calc(100vw-32px))] [overflow-wrap:anywhere] origin-(--transform-origin) rounded-soft bg-text px-3 py-1.5 text-xs text-balance text-surface",
            className,
          )}
          {...props}
        >
          {children}
          {showArrow && <Primitive.Arrow className={"size-2.5 fill-text"} />}
        </Primitive.Popup>
      </Primitive.Positioner>
    </Primitive.Portal>
  );
}
export { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider };
