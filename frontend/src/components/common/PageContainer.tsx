import { createElement, type ComponentPropsWithRef } from "react";
import { cn } from "@/lib/utils";

type PageElement = "div" | "main" | "section";
type PageContainerProps<Element extends PageElement = "div"> = ComponentPropsWithRef<Element> & {
  as?: Element;
  embedded?: boolean;
};

export function PageContainer<Element extends PageElement = "div">({
  as,
  embedded = false,
  className,
  ...props
}: PageContainerProps<Element>) {
  return createElement(as ?? "div", {
    ...props,
    "data-slot": "page-container",
    className: cn("min-w-0", !embedded && "page-frame py-(--os-space-6)", className),
  });
}
