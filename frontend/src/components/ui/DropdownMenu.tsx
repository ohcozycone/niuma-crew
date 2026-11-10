import type { StyledProps } from "./styledProps";
import { Menu as Primitive } from "@base-ui/react/menu";
import { cn } from "@/lib/utils";

const DropdownMenu = Primitive.Root;
const DropdownMenuTrigger = Primitive.Trigger;
const DropdownMenuRadioGroup = Primitive.RadioGroup;
const DropdownMenuRadioItem = Primitive.RadioItem;
const DropdownMenuRadioItemIndicator = Primitive.RadioItemIndicator;
function DropdownMenuGroupLabel({ className, ...props }: StyledProps<Primitive.GroupLabel.Props>) {
  return (
    <Primitive.GroupLabel
      className={cn("px-2 py-1 text-xs font-medium text-text-muted", className)}
      {...props}
    />
  );
}
type ContentProps = Omit<Primitive.Popup.Props, "className"> &
  Pick<Primitive.Positioner.Props, "side" | "align" | "sideOffset" | "collisionPadding"> & {
    className?: string;
  };
function DropdownMenuContent({
  className,
  sideOffset = 8,
  side = "bottom",
  align = "start",
  collisionPadding = 12,
  ...props
}: ContentProps) {
  return (
    <Primitive.Portal>
      <Primitive.Positioner
        side={side}
        align={align}
        sideOffset={sideOffset}
        collisionPadding={collisionPadding}
        className={"z-50 outline-none"}
      >
        <Primitive.Popup
          data-slot="dropdown-menu-content"
          className={cn(
            "min-w-[min(var(--anchor-width),var(--os-popover-max),calc(100vw-24px))] max-w-[min(var(--os-popover-max),calc(100vw-24px))] max-h-(--available-height) overflow-y-auto rounded-control border border-border bg-surface p-(--os-space-1) text-text shadow-popover outline-none",
            className,
          )}
          {...props}
        />
      </Primitive.Positioner>
    </Primitive.Portal>
  );
}
function DropdownMenuItem({
  className,
  tone = "default",
  ...props
}: StyledProps<Primitive.Item.Props> & { tone?: "default" | "destructive" }) {
  return (
    <Primitive.Item
      data-slot="dropdown-menu-item"
      data-tone={tone}
      className={cn(
        "flex min-h-(--os-control-default) [@media(pointer:coarse)]:min-h-(--os-target-touch) focus-inset cursor-pointer items-center gap-(--os-space-2) rounded-small p-(--os-space-2) text-(length:--os-text-caption) outline-none data-highlighted:bg-hover data-disabled:cursor-default data-disabled:text-text-muted [&>svg]:size-4 [&>svg]:shrink-0",
        tone === "destructive" &&
          "text-danger data-highlighted:bg-danger-bg data-highlighted:text-danger",
        className,
      )}
      {...props}
    />
  );
}
export {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuRadioItemIndicator,
  DropdownMenuGroupLabel,
};
