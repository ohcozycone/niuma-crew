import { Select as Primitive } from "@base-ui/react/select";
import { Separator } from "@base-ui/react/separator";
import { CheckIcon, ChevronDownIcon, ChevronUpIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import type { StyledProps } from "./styledProps";

type SelectProps = Omit<Primitive.Root.Props<string>, "onValueChange"> & {
  onValueChange?: (value: string, details: Primitive.Root.ChangeEventDetails) => void;
};
function Select({ onValueChange, ...props }: SelectProps) {
  return (
    <Primitive.Root
      onValueChange={(value, details) => {
        if (value !== null) onValueChange?.(value, details);
      }}
      {...props}
    />
  );
}
const SelectGroup = Primitive.Group;
function SelectValue({ className, ...props }: StyledProps<Primitive.Value.Props>) {
  return (
    <Primitive.Value
      data-slot="select-value"
      className={cn("min-w-0 flex-1 truncate text-left", className)}
      {...props}
    />
  );
}
function SelectTrigger({
  className,
  size = "default",
  children,
  ...props
}: StyledProps<Primitive.Trigger.Props> & { size?: "sm" | "default" }) {
  return (
    <Primitive.Trigger
      data-slot="select-trigger"
      data-size={size}
      className={cn(
        "[@media(pointer:coarse)]:min-h-(--os-target-touch) flex min-w-0 max-w-full w-fit items-center justify-between gap-2 rounded-field border border-input bg-surface px-3 py-2 text-body leading-5 whitespace-nowrap shadow-none outline-none transition-[color,border-color,box-shadow] disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-danger data-placeholder:text-text-muted  [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0 [&_svg]:text-text-muted",
        size === "sm" ? "h-(--os-control-small)" : "h-(--os-control-default)",
        "focus:border-field-focus focus:ring-[3px] focus:ring-field-focus/50 data-popup-open:border-field-focus data-popup-open:ring-[3px] data-popup-open:ring-field-focus/50 aria-invalid:focus:border-danger aria-invalid:focus:ring-danger/20 aria-invalid:data-popup-open:border-danger aria-invalid:data-popup-open:ring-danger/20",
        className,
      )}
      {...props}
    >
      {children}
      <Primitive.Icon>
        <ChevronDownIcon className={"size-4 opacity-50"} />
      </Primitive.Icon>
    </Primitive.Trigger>
  );
}
type ContentProps = StyledProps<Primitive.Popup.Props> &
  Pick<Primitive.Positioner.Props, "side" | "align" | "sideOffset" | "alignItemWithTrigger">;
function SelectContent({
  className,
  children,
  side = "bottom",
  align = "start",
  sideOffset = 4,
  alignItemWithTrigger = false,
  ...props
}: ContentProps) {
  return (
    <Primitive.Portal>
      <Primitive.Positioner
        side={side}
        align={align}
        sideOffset={sideOffset}
        alignItemWithTrigger={alignItemWithTrigger}
        collisionPadding={8}
        className={"z-50 outline-none"}
      >
        <Primitive.Popup
          data-slot="select-content"
          className={cn(
            "relative max-h-(--available-height) min-w-[min(var(--anchor-width),calc(100vw-16px))] max-w-[calc(100vw-16px)] origin-(--transform-origin) overflow-x-hidden overflow-y-auto rounded-field border border-border bg-surface text-text shadow-popover",
            className,
          )}
          {...props}
        >
          <SelectScrollUpButton />
          <Primitive.List className={"p-1"}>{children}</Primitive.List>
          <SelectScrollDownButton />
        </Primitive.Popup>
      </Primitive.Positioner>
    </Primitive.Portal>
  );
}
function SelectLabel({ className, ...props }: StyledProps<Primitive.GroupLabel.Props>) {
  return (
    <Primitive.GroupLabel
      data-slot="select-label"
      className={cn("px-2 py-1.5 text-xs text-text-muted", className)}
      {...props}
    />
  );
}
function SelectItem({ className, children, ...props }: StyledProps<Primitive.Item.Props>) {
  return (
    <Primitive.Item
      data-slot="select-item"
      className={cn(
        "relative flex min-h-(--os-control-default) [@media(pointer:coarse)]:min-h-(--os-target-touch) w-full cursor-default items-center gap-2 rounded-small py-1.5 pr-8 pl-2 text-sm outline-none select-none data-highlighted:bg-muted data-highlighted:text-text data-disabled:pointer-events-none data-disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
        className,
      )}
      {...props}
    >
      <Primitive.ItemIndicator
        className={"absolute right-2 flex size-3.5 items-center justify-center"}
      >
        <CheckIcon className={"size-4"} />
      </Primitive.ItemIndicator>
      <Primitive.ItemText className="min-w-0 [overflow-wrap:anywhere]">
        {children}
      </Primitive.ItemText>
    </Primitive.Item>
  );
}
function SelectSeparator({ className, ...props }: StyledProps<Separator.Props>) {
  return (
    <Separator
      data-slot="select-separator"
      className={cn("pointer-events-none -mx-1 my-1 h-px bg-border", className)}
      {...props}
    />
  );
}
function SelectScrollUpButton(props: Primitive.ScrollUpArrow.Props) {
  return (
    <Primitive.ScrollUpArrow
      className={"flex cursor-default items-center justify-center py-1"}
      {...props}
    >
      <ChevronUpIcon className={"size-4"} />
    </Primitive.ScrollUpArrow>
  );
}
function SelectScrollDownButton(props: Primitive.ScrollDownArrow.Props) {
  return (
    <Primitive.ScrollDownArrow
      className={"flex cursor-default items-center justify-center py-1"}
      {...props}
    >
      <ChevronDownIcon className={"size-4"} />
    </Primitive.ScrollDownArrow>
  );
}
export {
  Select,
  SelectGroup,
  SelectValue,
  SelectTrigger,
  SelectContent,
  SelectLabel,
  SelectItem,
  SelectSeparator,
  SelectScrollUpButton,
  SelectScrollDownButton,
};
