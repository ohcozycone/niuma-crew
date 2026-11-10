// Official shadcn/ui Base UI Sources pattern, adapted to private documents (MIT).
import { ArrowUpRight, BookOpen, FileText } from "lucide-react";
import {
  Trace,
  TraceCollapsible,
  TraceCollapsibleContent,
  TraceCollapsibleTrigger,
  TraceIcon,
  TraceLine,
  TraceTitle,
} from "./Trace";

export function Sources({ sources }: { sources: readonly { url: string; title: string }[] }) {
  if (!sources.length) return null;
  return (
    <Trace>
      <TraceCollapsible>
        <TraceCollapsibleTrigger>
          <TraceLine>
            <TraceIcon>
              <BookOpen />
            </TraceIcon>
            <TraceTitle>引用了 {sources.length} 个来源</TraceTitle>
          </TraceLine>
        </TraceCollapsibleTrigger>
        <TraceCollapsibleContent>
          <Trace>
            {sources.map((source) => (
              <a
                key={source.url}
                href={source.url}
                target="_blank"
                rel="noopener noreferrer"
                className="rounded-small py-1"
              >
                <TraceLine>
                  <TraceIcon>
                    <FileText />
                  </TraceIcon>
                  <TraceTitle>
                    {source.title}
                    <span className="sr-only">（新标签页查看原文）</span>
                  </TraceTitle>
                  <TraceIcon>
                    <ArrowUpRight />
                  </TraceIcon>
                </TraceLine>
              </a>
            ))}
          </Trace>
        </TraceCollapsibleContent>
      </TraceCollapsible>
    </Trace>
  );
}
