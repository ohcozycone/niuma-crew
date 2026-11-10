import { useContext } from "react";
import { CitationContext } from "./citationContext";
import { parseKnowledgeSourceLink } from "@/lib/knowledgeSourceLink";
import { useWorkspaceData } from "@/state/workspace/useWorkspaceData";
import { useResource } from "@/state/shared/useResource";

/** Old document URLs gain no authority; resolve only an exact registered reference in the message's Run. */
export function useKnowledgeSource(href: string) {
  const { sourceRunId } = useContext(CitationContext);
  const parts = parseKnowledgeSourceLink(href);
  const run = parts?.kind === "legacy" ? sourceRunId || "" : "";
  const resource = useWorkspaceData().knowledge.evidenceReferences(run);
  const state = useResource(resource);
  const target =
    parts?.kind === "evidence"
      ? href
      : !state.loading && !state.failure
        ? state.data?.find((item) => item.legacy_source_url === href)?.source_url
        : undefined;
  return { target, state, retry: () => resource.invalidate() };
}
