import { favoriteQuery } from "@/state/agents/agentStore";
import { useResource } from "@/state/shared/useResource";
import { useWorkspaceData } from "@/state/workspace/useWorkspaceData";
import { useAgentLinks } from "@/state/agents/useAgentData";

const emptyIds: string[] = [];

export function useNavigationSummary() {
  const data = useWorkspaceData();
  const summary = useResource(data.summary);
  const resource = data.agents.page(favoriteQuery());
  const page = useResource(resource);
  const links = useAgentLinks(page.data?.ids ?? emptyIds);
  const favorites = data.admin
    ? links
    : (page.data?.publicAgents ?? []).map((agent) => ({
        id: agent.id,
        name: agent.name,
        avatarId: agent.avatar_id,
      }));
  return {
    globalTotals: summary.data
      ? {
          agents: summary.data.agents,
          skills: summary.data.skills,
          favorites: page.data?.total ?? 0,
        }
      : null,
    favorites,
    summaryError: page.error || summary.error,
    summaryFailure: page.failure || summary.failure,
    ready: page.data !== undefined,
    reload: () => {
      resource.refresh();
      data.summary.refresh();
    },
  };
}
