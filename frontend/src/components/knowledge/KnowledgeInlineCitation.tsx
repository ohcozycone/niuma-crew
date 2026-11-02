import { useContext, useLayoutEffect, useState } from "react";
import { ArrowUpRight } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { HoverCard, HoverCardContent, HoverCardTrigger } from "@/components/ui/HoverCard";
import { parseKnowledgeSourceLink } from "@/lib/knowledgeSourceLink";
import { useWorkspaceData } from "@/state/workspace/useWorkspaceData";
import { useResource } from "@/state/shared/useResource";
import { CitationContext } from "./citationContext";

function CitationPreview({ href, title }: { href: string; title: string }) {
  const { knowledge } = useWorkspaceData();
  const parts = parseKnowledgeSourceLink(href)!;
  const resource = knowledge.citationPreview(parts.library, parts.document, parts.chunk);
  // Refresh before paint on each reopening; concurrent previews share an active read.
  useLayoutEffect(() => {
    if (!resource.active) resource.refresh();
  }, [resource]);
  const state = useResource(resource);
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div className="font-medium wrap-break-word">
        {state.loading || state.error ? title : state.data?.title || title}
      </div>
      {state.loading ? (
        <p className="text-xs text-text-muted" role="status">
          正在读取来源片段…
        </p>
      ) : state.error ? (
        <div className="space-y-2">
          <p role="alert" className="text-xs text-danger">
            {state.error}
          </p>
          <Button size="xs" variant="outline" onClick={resource.refresh}>
            重新读取
          </Button>
        </div>
      ) : state.data ? (
        <>
          <p className="text-xs leading-relaxed text-text-muted wrap-break-word">
            {state.data.locator}
          </p>
          <blockquote className="line-clamp-6 whitespace-pre-wrap text-sm leading-relaxed text-text-muted">
            {state.data.excerpt || "该片段暂无可展示正文。"}
          </blockquote>
        </>
      ) : null}
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex w-fit items-center gap-1 rounded-small text-xs font-medium underline-offset-4 hover:underline"
      >
        查看原文
        <ArrowUpRight className="size-3.5" aria-hidden="true" />
        <span className="sr-only">（新标签页）</span>
      </a>
    </div>
  );
}

/** Official Inline Citation composition: Hover Card on a secondary Button. */
export function KnowledgeInlineCitation({ href, number }: { href: string; number: number }) {
  const { titles } = useContext(CitationContext);
  const title = titles.get(href) || `知识来源 ${number}`;
  const [open, setOpen] = useState(false);
  return (
    <HoverCard open={open} onOpenChange={setOpen}>
      <HoverCardTrigger
        delay={10}
        closeDelay={100}
        render={<Button variant="secondary" size="xs" />}
        className="mx-0.5 inline-flex h-5 max-w-44 min-w-0 rounded-full px-1.5 text-xs font-medium align-baseline [@media(pointer:coarse)]:min-h-0 [@media(pointer:coarse)]:min-w-0"
        aria-label={`预览来源 ${number}：${title}`}
        aria-expanded={open}
        onClick={() => setOpen(true)}
      >
        <span className="truncate">{title}</span>
      </HoverCardTrigger>
      <HoverCardContent role="region" aria-label={`来源预览：${title}`}>
        {open && <CitationPreview href={href} title={title} />}
      </HoverCardContent>
    </HoverCard>
  );
}
