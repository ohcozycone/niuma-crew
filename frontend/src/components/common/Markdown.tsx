import { memo, useMemo, type ComponentProps } from "react";
import { defaultRehypePlugins, Streamdown } from "streamdown";
import { cjk } from "@streamdown/cjk";
import { createCodePlugin } from "@streamdown/code";
import codeTheme from "@/design-system/codeTheme.json";
import { isKnowledgeSourceLink } from "@/lib/knowledgeSourceLink";
import { knowledgeCitationBlock, rehypeKnowledgeCitations } from "@/lib/knowledgeCitations";
import { CitationContext } from "@/components/knowledge/citationContext";
import { KnowledgeInlineCitation } from "@/components/knowledge/KnowledgeInlineCitation";
import { KnowledgeSources } from "@/components/knowledge/KnowledgeSources";

const code = createCodePlugin({
  themes: [
    { ...codeTheme, name: "niuma-light", type: "light" },
    { ...codeTheme, name: "niuma-dark", type: "dark" },
  ],
});
const plugins = { cjk, code };
const rehypePlugins = [...Object.values(defaultRehypePlugins), rehypeKnowledgeCitations];
const emptyTitles = new Map<string, string>();
const components: ComponentProps<typeof Streamdown>["components"] = {
  a: ({ href, children, node }) => {
    const citation = node?.properties?.dataKnowledgeCitation;
    if (isKnowledgeSourceLink(href) && typeof citation === "number") {
      return <KnowledgeInlineCitation href={href} number={citation} />;
    }
    return /^(https?:\/\/|mailto:)/i.test(href || "") ? (
      <a href={href} target="_blank" rel="noopener noreferrer">
        {children}
      </a>
    ) : (
      <span>{children}</span>
    );
  },
  "knowledge-sources": ({ node }) => {
    const raw = node?.properties?.dataKnowledgeSources;
    if (typeof raw !== "string") return null;
    const entries = JSON.parse(raw) as { url: string; number: number }[];
    return <KnowledgeSources entries={entries} />;
  },
  img: ({ alt }) => <span>[图片：{alt || "未加载外部图片"}]</span>,
};

/** 独立的流式 Markdown；正文没变时不会因执行详情变化重新解析。 */
export const Markdown = memo(function Markdown({
  text,
  streaming = false,
  sourceTitles = emptyTitles,
}: {
  text: string;
  streaming?: boolean;
  sourceTitles?: ReadonlyMap<string, string>;
}) {
  const citations = useMemo(() => ({ titles: sourceTitles, streaming }), [sourceTitles, streaming]);
  return (
    <CitationContext.Provider value={citations}>
      <Streamdown
        className="answer-markdown size-full [&>*:first-child]:mt-0 [&>*:last-child]:mb-0"
        plugins={plugins}
        components={components}
        rehypePlugins={rehypePlugins}
        parseMarkdownIntoBlocksFn={
          text.includes("/knowledge/") ? knowledgeCitationBlock : undefined
        }
        skipHtml
        isAnimating={streaming}
      >
        {text}
      </Streamdown>
    </CitationContext.Provider>
  );
});
