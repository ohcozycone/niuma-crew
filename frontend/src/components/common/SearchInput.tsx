import { type ComponentProps } from "react";
import { cn } from "@/lib/utils";
import { Search, X } from "lucide-react";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { useDebouncedInput } from "@/hooks/useDebouncedInput";

type SearchInputProps = Omit<
  ComponentProps<typeof Input>,
  "value" | "onChange" | "className" | "aria-label"
> & {
  label: string;
  value: string;
  onChange: (value: string) => void;
  className?: string;
  inputClassName?: string;
  debounceMs?: number;
};
export function SearchInput({
  label,
  value,
  onChange,
  className,
  inputClassName,
  disabled,
  debounceMs = 0,
  onKeyDown,
  onCompositionStart,
  onCompositionEnd,
  ...props
}: SearchInputProps) {
  const input = useDebouncedInput(value, onChange, debounceMs, disabled);
  return (
    <div className={cn("de-search-input relative w-77.5 max-w-full", className)}>
      <Search
        size={15}
        aria-hidden="true"
        className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-text-muted"
      />
      <Input
        {...props}
        aria-label={label}
        value={input.value}
        disabled={disabled}
        onChange={(event) => input.change(event.target.value)}
        onCompositionStart={(event) => {
          input.startComposition();
          onCompositionStart?.(event);
        }}
        onCompositionEnd={(event) => {
          input.endComposition(event.currentTarget.value);
          onCompositionEnd?.(event);
        }}
        onKeyDown={(event) => {
          onKeyDown?.(event);
          if (
            debounceMs > 0 &&
            event.key === "Enter" &&
            !input.isComposing() &&
            !event.nativeEvent.isComposing &&
            event.keyCode !== 229
          ) {
            event.preventDefault();
            input.change(event.currentTarget.value, true);
          }
        }}
        className={cn("pl-8.5 pr-9", inputClassName)}
      />
      {input.value && (
        <Button
          type="button"
          variant="ghost"
          size="icon-xs"
          aria-label={`清空${label}`}
          disabled={disabled}
          className="absolute top-1/2 right-1.5 -translate-y-1/2 text-text-muted"
          onClick={() => input.change("", true)}
        >
          <X size={13} />
        </Button>
      )}
    </div>
  );
}
