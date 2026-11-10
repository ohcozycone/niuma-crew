import { useContext } from "react";
import { Sources } from "@/components/ui/Sources";
import { isKnowledgeSourceLink, parseKnowledgeSourceLink } from "@/lib/knowledgeSourceLink";
import { CitationContext } from "./citationContext";
import { useWorkspaceData } from "@/state/workspace/useWorkspaceData";
import { useResource } from "@/state/shared/useResource";

export function KnowledgeSources({
  entries,
}: {
  entries: readonly { url: string; number: number }[];
}) {
  const { titles, streaming, sourceRunId } = useContext(CitationContext);
  const needsMapping = entries.some(
    (entry) => parseKnowledgeSourceLink(entry.url)?.kind === "legacy",
  );
  const references = useResource(
    useWorkspaceData().knowledge.evidenceReferences(
      needsMapping && !streaming ? sourceRunId || "" : "",
    ),
  );
  if (streaming) return null;
  const sources = entries
    .filter((entry) => isKnowledgeSourceLink(entry.url))
    .flatMap((entry) => {
      const url =
        parseKnowledgeSourceLink(entry.url)?.kind === "evidence"
          ? entry.url
          : !references.loading && !references.failure
            ? references.data?.find((item) => item.legacy_source_url === entry.url)?.source_url
            : undefined;
      return url && parseKnowledgeSourceLink(url)?.kind === "evidence"
        ? [
            {
              url,
              title: titles.get(entry.url) || `知识来源 ${entry.number}`,
            },
          ]
        : [];
    });
  return <Sources sources={sources} />;
}
