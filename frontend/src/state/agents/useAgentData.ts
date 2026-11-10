import { useMemo, useSyncExternalStore } from "react";
import { useAtom } from "@/state/shared/useResource";
import { useWorkspaceData } from "@/state/workspace/useWorkspaceData";

export function useAgentState(id: string) {
  return useAtom(useWorkspaceData().agents.state(id));
}
export function useAgentStatistics(ids: readonly string[]) {
  const { agents } = useWorkspaceData();
  const statistics = useMemo(() => agents.statistics(ids), [agents, ids]);
  return useSyncExternalStore(statistics.subscribe, statistics.getSnapshot, statistics.getSnapshot);
}
export function useAgentLinks(ids: readonly string[]) {
  const { agents } = useWorkspaceData();
  const links = useMemo(() => agents.links(ids), [agents, ids]);
  return useSyncExternalStore(links.subscribe, links.getSnapshot, links.getSnapshot);
}
