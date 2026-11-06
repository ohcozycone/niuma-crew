export type Identity = {
  actor: { kind: "user" | "guest"; user: { id: string; username: string } | null };
  permissions: string[];
  expires_at: string;
};

export function identityKey(identity: Identity): string {
  return JSON.stringify([identity.actor, identity.expires_at, [...identity.permissions].sort()]);
}

export function notifyIdentityChange() {
  if (typeof BroadcastChannel !== "undefined") {
    const channel = new BroadcastChannel("auth-session");
    channel.postMessage("changed");
    channel.close();
  }
}
