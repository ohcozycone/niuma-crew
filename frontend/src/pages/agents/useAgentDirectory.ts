import { useEffect } from "react";
import { useSearchParams } from "react-router";
import { useWorkspaceData } from "@/state/workspace/useWorkspaceData";
import { useResource, useRetainedResource } from "@/state/shared/useResource";
import { useAgentStatistics } from "@/state/agents/useAgentData";
import { favoriteQuery } from "@/state/agents/agentStore";

const pageSize = 20;
const emptyIds: string[] = [];
export function useAgentDirectory() {
  const data = useWorkspaceData();
  const [params, setParams] = useSearchParams();
  const query = new URLSearchParams({
    offset: params.get("offset") ?? "0",
    limit: String(pageSize),
    q: params.get("q") ?? "",
  });
  if (params.get("category") && params.get("category") !== "all")
    query.set("category", params.get("category")!);
  if (params.get("skill")) query.set("skill_id", params.get("skill")!);
  const filter = params.get("filter");
  if (filter === "favorites") query.set("is_favorite", "true");
  if (filter === "paused") query.set("is_active", "false");
  if (filter === "active") {
    query.set("is_active", "true");
    query.set("model_configured", "true");
  }
  const resource = data.agents.page(query);
  const page = useRetainedResource(resource, data);
  const summary = useResource(data.summary);
  const ids = page.data?.ids ?? emptyIds;
  const statistics = useAgentStatistics(ids);
  const fresh = resource.getSnapshot().data;
  const offset = Number(params.get("offset")) || 0;
  useEffect(() => {
    if (!fresh || offset === 0 || offset < fresh.total) return;
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        next.set("offset", String(Math.max(0, Math.ceil(fresh.total / pageSize) - 1) * pageSize));
        return next;
      },
      { replace: true, preventScrollReset: true },
    );
  }, [fresh, offset, setParams]);
  return {
    ids,
    pageSize,
    categories: statistics.categories,
    availableCount: statistics.available,
    publicAgents: page.data?.publicAgents ?? [],
    agentTotal: page.data?.total ?? 0,
    ready: page.data !== undefined,
    loading: page.loading,
    listError: page.error,
    directoryTotal: summary.data?.agents ?? null,
    error: page.error || summary.error,
    failure: page.failure || summary.failure,
    reload: () => {
      resource.refresh();
      data.summary.refresh();
      const favorites = data.agents.page(favoriteQuery());
      if (favorites !== resource) favorites.refresh();
    },
  };
}
