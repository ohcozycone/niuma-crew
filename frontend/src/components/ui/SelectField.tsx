import type { ComponentProps, ComponentPropsWithRef, ReactNode } from "react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./Select";
import { cn } from "@/lib/utils";

export type SelectOption = { value: string; label: string; disabled?: boolean };
type SelectFieldProps = Omit<
  ComponentPropsWithRef<typeof SelectTrigger>,
  "children" | "value" | "defaultValue" | "onChange" | "render"
> & {
  options: readonly SelectOption[];
  value: string;
  onValueChange: (value: string) => void;
  name?: string;
  required?: boolean;
  placeholder?: string;
  icon?: ReactNode;
  displayValue?: ReactNode;
  contentProps?: Pick<
    ComponentProps<typeof SelectContent>,
    "align" | "side" | "sideOffset" | "alignItemWithTrigger" | "className"
  >;
};

/** Complete select: callers provide options once; the shared adapter owns its popup and items. */
export function SelectField({
  value,
  onValueChange,
  name,
  disabled,
  required,
  className,
  options,
  placeholder,
  icon,
  displayValue,
  contentProps,
  ...triggerProps
}: SelectFieldProps) {
  return (
    <Select
      items={options.map(({ value, label }) => ({ value, label }))}
      value={value}
      onValueChange={onValueChange}
      name={name}
      disabled={disabled}
      required={required}
    >
      <SelectTrigger className={cn("w-full", className)} {...triggerProps}>
        {icon && (
          <span className="flex shrink-0 items-center" aria-hidden="true">
            {icon}
          </span>
        )}
        <SelectValue placeholder={placeholder}>{displayValue}</SelectValue>
      </SelectTrigger>
      <SelectContent {...contentProps}>
        {options.map((option) => (
          <SelectItem key={option.value} value={option.value} disabled={option.disabled}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
