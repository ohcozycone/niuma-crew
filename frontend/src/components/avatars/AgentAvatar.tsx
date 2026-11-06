import { defaultAvatarId, findAvatar } from "../../lib/avatars/registry";
import type { CharacterSvgProps } from "./svgAvatar";
import { LazySvgAvatar } from "./LazySvgAvatar";

export type AgentAvatarProps = Pick<CharacterSvgProps, "size" | "alt" | "className"> & {
  avatarId: string;
};

/** Shared agent portrait: current SVG artwork with a display-only legacy fallback. */
export function AgentAvatar({ avatarId, ...props }: AgentAvatarProps) {
  const selected = findAvatar(avatarId);
  const asset = selected ?? findAvatar(defaultAvatarId)!;
  return (
    <LazySvgAvatar
      {...props}
      character={asset.svgCharacter}
      data-avatar-role={asset.id}
      data-avatar-renderer="svg"
      data-avatar-fallback={selected ? undefined : true}
    />
  );
}
