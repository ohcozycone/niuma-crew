import type { StyledProps } from "./styledProps";
import * as React from "react";
import { Tabs as Primitive } from "@base-ui/react/tabs";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

type TabsProps = Omit<
  StyledProps<Primitive.Root.Props>,
  "value" | "defaultValue" | "onValueChange"
> & {
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string, details: Primitive.Root.ChangeEventDetails) => void;
};
function Tabs({ className, onValueChange, ...props }: TabsProps) {
  return (
    <Primitive.Root
      data-slot="tabs"
      className={cn("group/tabs flex gap-2 data-[orientation=horizontal]:flex-col", className)}
      onValueChange={(value, details) => {
        if (typeof value === "string") onValueChange?.(value, details);
      }}
      {...props}
    />
  );
}
function TabsHeader({
  className,
  children,
  trailing,
  ...props
}: React.ComponentProps<"div"> & { trailing?: React.ReactNode }) {
  return (
    <div
      data-slot="tabs-header"
      className={cn(
        "flex w-full min-w-0 flex-wrap items-center gap-x-(--os-space-4) gap-y-(--os-space-2)",
        className,
      )}
      {...props}
    >
      {children}
      {trailing != null && typeof trailing !== "boolean" && (
        <div
          data-slot="tabs-header-trailing"
          className={
            "ml-auto flex min-w-0 max-w-full flex-wrap items-center justify-end gap-(--os-space-2) text-end text-(length:--os-text-caption) text-text-muted [overflow-wrap:anywhere]"
          }
        >
          {trailing}
        </div>
      )}
    </div>
  );
}
const tabsListVariants = cva(
  "group/tabs-list relative inline-flex max-w-full overflow-x-auto overflow-y-hidden w-fit items-center justify-start rounded-control p-[3px] text-text-muted group-data-[orientation=vertical]/tabs:flex-col",
  {
    variants: {
      variant: {
        default:
          "bg-muted group-data-[orientation=horizontal]/tabs:h-9 group-data-[orientation=vertical]/tabs:h-fit",
        line: "gap-(--os-space-6) rounded-none bg-transparent p-0",
      },
    },
    defaultVariants: { variant: "default" },
  },
);
function TabsList({
  className,
  variant = "default",
  children,
  activateOnFocus = true,
  ...props
}: StyledProps<Primitive.List.Props> & VariantProps<typeof tabsListVariants>) {
  return (
    <Primitive.List
      data-slot="tabs-list"
      data-variant={variant}
      activateOnFocus={activateOnFocus}
      className={cn(tabsListVariants({ variant }), className)}
      {...props}
    >
      {children}
      {variant === "line" && (
        <Primitive.Indicator
          data-slot="tabs-indicator"
          className={
            "pointer-events-none absolute bottom-0 left-0 h-0.75 w-(--active-tab-width) translate-x-(--active-tab-left) rounded-t-tiny bg-brand transition-[translate,width,height] duration-(--os-motion-normal) ease-out group-data-[orientation=vertical]/tabs:top-0 group-data-[orientation=vertical]/tabs:right-[-1px] group-data-[orientation=vertical]/tabs:bottom-auto group-data-[orientation=vertical]/tabs:left-auto group-data-[orientation=vertical]/tabs:h-(--active-tab-height) group-data-[orientation=vertical]/tabs:w-0.75 group-data-[orientation=vertical]/tabs:translate-x-0 group-data-[orientation=vertical]/tabs:translate-y-(--active-tab-top) motion-reduce:transition-none"
          }
        />
      )}
    </Primitive.List>
  );
}
function TabsTrigger({ className, ...props }: StyledProps<Primitive.Tab.Props>) {
  return (
    <Primitive.Tab
      data-slot="tabs-trigger"
      className={cn(
        "relative inline-flex min-h-9 [@media(pointer:coarse)]:min-h-(--os-target-touch) h-[calc(100%-1px)] flex-1 items-center justify-center gap-1.5 rounded-soft border border-transparent px-2 py-1 text-sm font-medium whitespace-nowrap text-text-muted transition-[color,background-color,box-shadow] group-data-[orientation=vertical]/tabs:w-full group-data-[orientation=vertical]/tabs:justify-start not-data-active:hover:text-text focus-visible:border-focus focus-visible:ring-[3px] focus-visible:ring-focus/50 focus-visible:outline-1 focus-visible:outline-focus disabled:pointer-events-none disabled:opacity-50 data-active:bg-surface data-active:text-text group-data-[variant=default]/tabs-list:data-active:shadow-sm [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
        "focus-inset group-data-[variant=line]/tabs-list:flex-none group-data-[variant=line]/tabs-list:rounded-none group-data-[variant=line]/tabs-list:border-0 group-data-[variant=line]/tabs-list:px-0 group-data-[variant=line]/tabs-list:bg-transparent group-data-[variant=line]/tabs-list:data-active:bg-transparent group-data-[variant=line]/tabs-list:data-active:shadow-none",
        className,
      )}
      {...props}
    />
  );
}
function TabsContent({ className, ...props }: StyledProps<Primitive.Panel.Props>) {
  return (
    <Primitive.Panel
      data-slot="tabs-content"
      className={cn("min-w-0 flex-1 outline-none", className)}
      {...props}
    />
  );
}
export { Tabs, TabsHeader, TabsList, TabsTrigger, TabsContent, tabsListVariants };
