import { useContext } from "react";
import { Sources } from "@/components/ui/Sources";
import { isKnowledgeSourceLink } from "@/lib/knowledgeSourceLink";
import { CitationContext } from "./citationContext";

export function KnowledgeSources({
  entries,
}: {
  entries: readonly { url: string; number: number }[];
}) {
  const { titles, streaming } = useContext(CitationContext);
  if (streaming) return null;
  const sources = entries
    .filter((entry) => isKnowledgeSourceLink(entry.url))
    .map((entry) => ({
      url: entry.url,
      title: titles.get(entry.url) || `知识来源 ${entry.number}`,
    }));
  return <Sources sources={sources} />;
}
