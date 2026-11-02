import { FailureNotice } from "@/components/failure/FailureNotice";
import { toFailure, mutationOutcome } from "@/lib/failures/resolve";
import type { Failure } from "@/lib/failures/types";
import { AccountMenuButton } from "./AccountMenuButton";
import { useState } from "react";
import { LoaderCircle, LogOut } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/DropdownMenu";
import { Button } from "@/components/ui/Button";
import { request } from "@/lib/api/http";
import { useIdentity } from "@/state/auth/useIdentity";
import { notifyIdentityChange } from "@/lib/identity";
export function AccountMenu({ beforeLogout }: { beforeLogout?: () => boolean }) {
  const identity = useIdentity();
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);
  async function logout() {
    if (busy || (beforeLogout && !beforeLogout())) return;
    setBusy(true);
    setFailure(null);
    try {
      await request("auth/logout", { method: "POST", body: "{}" });
      notifyIdentityChange();
      window.dispatchEvent(new Event("auth:session-ended"));
    } catch (error) {
      setFailure(toFailure(error));
      setBusy(false);
    }
  }
  const guest = identity.actor.kind === "guest";
  const admin = identity.permissions.includes("resources:all");
  const username = identity.actor.user?.username ?? "游客浏览";
  const identityContent = (
    <>
      <span
        className={
          "de-account-avatar grid [place-items:center] shrink-0 w-7 h-7 rounded-full bg-muted text-[length:var(--os-text-caption)] font-[500] text-text-muted"
        }
        aria-hidden="true"
      >
        {identity.actor.user?.username.slice(0, 1).toUpperCase() ?? "访"}
      </span>
      <span className={"flex flex-1 flex-col min-w-0 leading-[var(--os-leading-compact)]"}>
        <strong title={username}>{username}</strong>
        <small>{guest ? "只读访问" : admin ? "平台管理员" : "普通用户"}</small>
      </span>
    </>
  );
  if (guest) {
    return (
      <div>
        <div
          className={
            "flex items-center gap-(--os-space-2) w-full min-w-0 min-h-[calc(var(--os-space-6)_*_2)] py-(--os-space-1) px-(--os-space-2) border-0 rounded-control bg-transparent text-text text-left [button&:hover]:bg-muted [button&[data-open]]:bg-muted [button&:hover_.de-account-avatar]:bg-canvas [&[data-open]_.de-account-avatar]:bg-canvas [&_strong]:overflow-hidden [&_strong]:text-[length:var(--os-text-body)] [&_strong]:leading-[var(--os-leading-heading)] [&_strong]:font-[500] [&_strong]:text-ellipsis [&_strong]:whitespace-nowrap [&_small]:text-[length:var(--os-text-caption)] [&_small]:text-text-muted [&[data-open]_.de-account-chevron]:[transform:rotate(180deg)]"
          }
        >
          {identityContent}
          <Button size="sm" variant="ghost" className={"shrink-0"} disabled={busy} onClick={logout}>
            {busy ? "正在退出…" : "登录"}
          </Button>
        </div>
        <FailureNotice
          failure={failure}
          context={{
            operation: "mutation",
            outcome: mutationOutcome(failure),
          }}
        />
      </div>
    );
  }
  return (
    <DropdownMenu
      modal={false}
      onOpenChange={(open, details) => {
        if (!open && details.reason === "escape-key") details.event.stopPropagation();
      }}
    >
      <DropdownMenuTrigger
        render={
          <AccountMenuButton
            username={username}
            roleLabel={admin ? "平台管理员" : "普通用户"}
            aria-label={`${username}，账户菜单`}
          />
        }
      />
      <DropdownMenuContent className={"de-account-menu"} side="top" align="start">
        <DropdownMenuItem
          closeOnClick={false}
          tone="destructive"
          disabled={busy}
          onClick={() => {
            void logout();
          }}
        >
          {busy ? (
            <LoaderCircle className={"animate-spin"} aria-hidden="true" />
          ) : (
            <LogOut aria-hidden="true" />
          )}
          {busy ? "正在退出…" : "退出登录"}
        </DropdownMenuItem>
        <FailureNotice
          failure={failure}
          context={{
            operation: "mutation",
            outcome: mutationOutcome(failure),
          }}
        />
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
