import { isKnowledgeSourceLink } from "./knowledgeSourceLink";

type MarkdownNode = {
  type: string;
  tagName?: string;
  properties?: Record<string, unknown>;
  children?: MarkdownNode[];
  value?: string;
};

/** Number actual parsed links, so code examples and escaped Markdown never consume a number. */
export function rehypeKnowledgeCitations() {
  return (tree: MarkdownNode) => {
    const numbers = new Map<string, number>();
    function visit(node: MarkdownNode) {
      const href = node.properties?.href;
      if (node.tagName === "a" && isKnowledgeSourceLink(href)) {
        const number = numbers.get(href) ?? numbers.size + 1;
        numbers.set(href, number);
        node.properties = { ...node.properties, dataKnowledgeCitation: number };
        node.children = [{ type: "text", value: `[${number}]` }];
        return;
      }
      node.children?.forEach(visit);
    }
    visit(tree);
    if (numbers.size && tree.children) {
      tree.children.push({
        type: "element",
        tagName: "knowledge-sources",
        properties: {
          dataKnowledgeSources: JSON.stringify(
            [...numbers].map(([url, number]) => ({ url, number })),
          ),
        },
        children: [],
      });
    }
  };
}

/** Tool metadata supplies labels; only the parsed answer decides which URLs are cited. */
export function knowledgeCitationTitles(
  steps: readonly { status: string; safe_details: Record<string, unknown> }[],
) {
  const titles = new Map<string, string>();
  for (const step of steps) {
    if (step.status !== "succeeded" || !Array.isArray(step.safe_details.sources)) continue;
    for (const source of step.safe_details.sources) {
      if (
        source &&
        typeof source === "object" &&
        isKnowledgeSourceLink(source.url) &&
        typeof source.title === "string" &&
        source.title.trim() &&
        source.status !== "failed"
      )
        titles.set(source.url, source.title.trim().slice(0, 300));
    }
  }
  return titles;
}

/** Streamdown normally parses paragraphs separately; citations need one answer-wide index. */
export function knowledgeCitationBlock(text: string) {
  return [text];
}
