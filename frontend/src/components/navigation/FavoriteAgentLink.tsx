import { Link } from "react-router";
import { MessagesSquare } from "lucide-react";
import { AvatarBadge } from "@/components/avatars";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/Tooltip";

type FavoriteAgentLinkProps = {
  name: string;
  avatarId: string;
  to: string;
  label: string;
  conversationTo?: string;
};

export function FavoriteAgentLink({
  name,
  avatarId,
  to,
  label,
  conversationTo,
}: FavoriteAgentLinkProps) {
  return (
    <div
      className={
        "group/favorite flex shrink-0 items-center w-full min-w-0 rounded-control transition-colors duration-fast motion-reduce:transition-none hover:bg-hover"
      }
    >
      <Link
        to={to}
        aria-label={label}
        title={name}
        className={
          "flex flex-1 min-w-0 items-center self-stretch gap-(--os-favorite-gap) py-(--os-favorite-py) px-(--os-favorite-px) text-[length:var(--os-type-body-size)] [font-weight:var(--os-type-body-weight)] leading-[var(--os-type-body-leading)] tracking-[var(--os-type-body-tracking)] text-(--os-type-body-color) text-left no-underline rounded-control focus-inset focus-visible:outline-2 focus-visible:outline-focus focus-visible:outline-offset-[-2px]"
        }
      >
        <AvatarBadge avatarId={avatarId} size="navigation" />
        <span className={"flex-1 min-w-0 overflow-hidden text-ellipsis whitespace-nowrap"}>
          {name}
        </span>
      </Link>
      {conversationTo && (
        // Keep this slot outside the main link, even while hidden, so hover never changes a target.
        <div
          className={
            "flex shrink-0 items-center self-stretch pl-(--os-space-1) pr-(--os-space-1) before:content-[''] before:absolute before:h-(--os-space-5) before:w-px before:bg-border before:left-0 before:pointer-events-none before:opacity-0 group-hover/favorite:before:opacity-100 [@media(hover:_none)]:before:opacity-100 relative"
          }
        >
          <TooltipProvider delay={200}>
            <Tooltip>
              <TooltipTrigger
                render={
                  <Link
                    to={conversationTo}
                    aria-label={`与${name}新建对话`}
                    className={
                      "inline-flex shrink-0 items-center justify-center size-(--os-control-default) rounded-control text-text-muted hover:text-hover-text transition-colors duration-fast motion-reduce:transition-none no-underline opacity-0 pointer-events-none group-hover/favorite:opacity-100 group-hover/favorite:pointer-events-auto [@media(hover:_none)]:opacity-100 [@media(hover:_none)]:pointer-events-auto [@media(hover:_none)]:size-(--os-target-touch) [@media(any-pointer:_coarse)]:size-(--os-target-touch) focus-visible:opacity-100 focus-visible:pointer-events-auto focus-inset focus-visible:outline-2 focus-visible:outline-focus focus-visible:outline-offset-[-2px]"
                    }
                  />
                }
              >
                <MessagesSquare
                  className={
                    "size-(--os-space-4) pointer-events-none [stroke-width:var(--os-nav-icon-stroke)]"
                  }
                  aria-hidden="true"
                />
              </TooltipTrigger>
              <TooltipContent sideOffset={6}>新建对话</TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
      )}
    </div>
  );
}
