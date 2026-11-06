import type { ReactNode } from "react";
import { Tabs, TabsHeader, TabsList, TabsTrigger } from "@/components/ui/Tabs";
import { cn } from "@/lib/utils";

type TabItem = { value: string; label: ReactNode; count?: ReactNode; disabled?: boolean };
type Props = Omit<React.ComponentProps<typeof Tabs>, "children"> & {
  label: string;
  items: TabItem[];
  trailing?: ReactNode;
  placement?: "page" | "panel";
  activateOnFocus?: boolean;
  children?: ReactNode;
};
/** Complete line navigation. Consumers supply content and state, never tab paint. */
export function PageTabs({
  label,
  items,
  trailing,
  placement = "page",
  activateOnFocus = false,
  children,
  ...props
}: Props) {
  return (
    <Tabs {...props}>
      <TabsHeader
        className={cn(
          "border-b border-border",
          placement === "page" && "mb-4",
          placement === "panel" && "px-4 sm:px-6",
        )}
        trailing={trailing}
      >
        <TabsList
          variant="line"
          aria-label={label}
          activateOnFocus={activateOnFocus}
          className={placement === "panel" ? "min-h-14" : "min-h-11"}
        >
          {items.map(({ value, label: text, count, disabled }) => (
            <TabsTrigger key={value} value={value} disabled={disabled}>
              {text}
              {count !== undefined && (
                <>
                  {" "}
                  <span className="rounded-small bg-muted px-1 text-xs text-text-muted">
                    {count}
                  </span>
                </>
              )}
            </TabsTrigger>
          ))}
        </TabsList>
      </TabsHeader>
      {children}
    </Tabs>
  );
}
