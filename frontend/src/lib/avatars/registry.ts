import { catalog } from "./manifest.generated";

export const agentAvatars = catalog.assets;
export const defaultAvatarId = "intern";
const aliases: Readonly<Record<string, string>> = catalog.aliases;

/** Unknown and retired IDs stay unresolved so unrelated saves preserve stored values. */
export function findAvatar(id: string) {
  return agentAvatars.find((avatar) => avatar.id === (aliases[id] ?? id));
}
