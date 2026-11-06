import { useRender } from "@base-ui/react/use-render";
import { cn } from "@/lib/utils";

export function NavigationItem({
  active = false,
  render,
  className,
  ...props
}: Omit<useRender.ComponentProps<"button">, "className"> & {
  active?: boolean;
  className?: string;
}) {
  return useRender({
    defaultTagName: "button",
    render,
    props: {
      type: render ? undefined : "button",
      ...props,
      "data-slot": "navigation-item",
      className: cn(
        "flex items-center [gap:11px] min-h-10.5 [@media(pointer:coarse)]:min-h-(--os-target-touch) w-full [padding:10px_12px] [margin:4px_0] text-text [font-size:var(--os-text-caption)] [font-weight:var(--os-nav-weight)] text-left rounded-control [&_>_svg]:shrink-0 [&_>_svg]:[width:var(--os-nav-icon-size)] [&_>_svg]:[height:var(--os-nav-icon-size)] [&_>_svg]:text-text-muted [&_>_svg]:[stroke-width:var(--os-nav-icon-stroke)] [&.is-active_>_svg]:[color:inherit] [&.is-active_>_svg]:[stroke-width:var(--os-nav-icon-active-stroke)] [&:not(.is-active):hover]:bg-hover [&:not(.is-active):active]:bg-pressed transition-colors duration-fast motion-reduce:transition-none [&.is-active]:[box-shadow:none] [&.is-active]:bg-nav-active [&.is-active]:text-nav-active-text [&.is-active]:[font-weight:var(--os-nav-active-weight)] [&_small]:[margin-left:auto] [&_small]:[font-size:var(--os-text-caption)] [&_small]:bg-nav-count-bg [&_small]:rounded-small [&_small]:[min-width:21px] [&_small]:text-center [&_small]:text-text-muted [&_small]:[font-weight:inherit] [&_small]:[padding:1px_4px] [&.is-active_small]:[background:none] [&.is-active_small]:[color:inherit] [text-decoration:none]",
        active && "is-active",
        className,
      ),
    },
  });
}
