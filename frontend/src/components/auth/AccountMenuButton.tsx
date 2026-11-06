import { ChevronUp } from "lucide-react";
import type { ComponentPropsWithRef } from "react";
import { cn } from "@/lib/utils";
export function AccountMenuButton({
  username,
  roleLabel,
  initial,
  className,
  ...props
}: Omit<ComponentPropsWithRef<"button">, "children"> & {
  username: string;
  roleLabel: string;
  initial?: string;
}) {
  return (
    <button
      type="button"
      className={cn(
        "flex items-center gap-(--os-space-2) w-full min-w-0 min-h-[calc(var(--os-space-6)_*_2)] py-(--os-space-1) px-(--os-space-2) border-0 rounded-control bg-transparent text-text text-left transition-colors duration-fast motion-reduce:transition-none [button&:hover]:bg-hover [button&[data-open]]:bg-pressed [button&:hover_.de-account-avatar]:bg-canvas [&[data-open]_.de-account-avatar]:bg-canvas [&_strong]:overflow-hidden [&_strong]:text-[length:var(--os-text-body)] [&_strong]:leading-[var(--os-leading-heading)] [&_strong]:font-[500] [&_strong]:text-ellipsis [&_strong]:whitespace-nowrap [&_small]:text-[length:var(--os-text-caption)] [&_small]:text-text-muted [&[data-open]_.de-account-chevron]:[transform:rotate(180deg)]",
        className,
      )}
      {...props}
    >
      <span
        className="de-account-avatar grid place-items-center shrink-0 size-7 rounded-full bg-muted text-sm text-text-muted"
        aria-hidden="true"
      >
        {initial ?? username.slice(0, 1).toUpperCase()}
      </span>
      <span className="flex min-w-0 flex-1 flex-col leading-(--os-leading-compact)">
        <strong title={username}>{username}</strong>
        <small>{roleLabel}</small>
      </span>
      <ChevronUp
        className="de-account-chevron shrink-0 text-text-muted transition-transform duration-fast"
        size={16}
        aria-hidden="true"
      />
    </button>
  );
}
