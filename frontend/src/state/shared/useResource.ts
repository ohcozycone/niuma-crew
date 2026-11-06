import { useLayoutEffect, useRef, useSyncExternalStore } from "react";
import type { Atom } from "./atom";
import type { Resource } from "./resource";

export function useAtom<T>(atom: Atom<T>) {
  return useSyncExternalStore(atom.subscribe, atom.getSnapshot, atom.getSnapshot);
}
export function useResource<T>(resource: Resource<T>) {
  return useSyncExternalStore(resource.subscribe, resource.getSnapshot, resource.getSnapshot);
}
/** 条件变化时保留当前身份的上一页，仍以 loading/error 标明新条件尚未完成。 */
export function useRetainedResource<T>(resource: Resource<T>, owner: object) {
  const snapshot = useResource(resource);
  const previous = useRef<{ owner: object; data: T } | null>(null);
  const inaccessible =
    snapshot.failure?.source === "http" && [401, 403].includes(snapshot.failure.status ?? 0);
  useLayoutEffect(() => {
    if (inaccessible) previous.current = null;
    else if (snapshot.data !== undefined) previous.current = { owner, data: snapshot.data };
  }, [snapshot.data, owner, inaccessible]);
  return {
    ...snapshot,
    data: inaccessible
      ? undefined
      : (snapshot.data ?? (previous.current?.owner === owner ? previous.current.data : undefined)),
  };
}
