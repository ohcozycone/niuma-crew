import { AgentAvatar } from "./AgentAvatar";

/** Workspace sizing only; role resolution and rendering stay in AgentAvatar. */
export function AvatarBadge({
  avatarId,
  size = "normal",
}: {
  avatarId: string;
  size?: "small" | "normal" | "large" | "navigation";
}) {
  return (
    <span
      className={`de-avatar [width:45px] [height:47px] rounded-panel inline-flex items-center justify-center shrink-0 bg-muted text-text-muted [border:1px_solid_var(--os-border)] relative overflow-hidden [&.de-avatar-image]:bg-muted [&.de-avatar-image]:border-border [&.de-avatar-image]:overflow-hidden [&.de-avatar-navigation]:[width:var(--os-avatar-size)] [&.de-avatar-navigation]:[height:var(--os-avatar-size)] [&.de-avatar-navigation]:p-0 [&.de-avatar-navigation]:[border:0] [&.de-avatar-navigation]:[border-radius:0] [&.de-avatar-navigation]:[background:transparent] [&.de-avatar-navigation]:overflow-visible de-avatar-${size} de-avatar-image [&_svg]:w-full [&_svg]:h-full [&_svg]:object-contain`}
      aria-hidden="true"
    >
      <AgentAvatar avatarId={avatarId} size="100%" />
    </span>
  );
}
