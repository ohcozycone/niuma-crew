import { useId } from "react";
import { Link } from "react-router";
import { Card, CardContent, CardFooter } from "@/components/ui/Card";
import type { KnowledgeBase } from "@/lib/api/knowledge";

export function KnowledgeCard({
  library,
}: {
  library: Pick<KnowledgeBase, "id" | "name" | "description" | "document_count" | "updated_at">;
}) {
  const titleId = useId();
  return (
    <Card as="article" interactive>
      <Link
        to={`/knowledge/${library.id}`}
        aria-labelledby={titleId}
        className="block h-full rounded-card focus-visible:outline-2 focus-visible:outline-focus focus-visible:outline-offset-2"
      >
        <CardContent className="flex h-full flex-col">
          <div className="flex min-w-0 flex-1 items-start gap-3">
            <img
              src="/knowledge/library-folder-clean.png"
              width={48}
              height={48}
              alt=""
              decoding="async"
              className="size-12 shrink-0 object-contain"
            />
            <div className="min-w-0 flex-1">
              <h2
                id={titleId}
                className="type-title line-clamp-2 [overflow-wrap:anywhere]"
                title={library.name}
              >
                {library.name}
              </h2>
              <p className="mt-2 min-h-10 line-clamp-2 text-sm text-text-muted [overflow-wrap:anywhere]">
                {library.description}
              </p>
            </div>
          </div>
          <CardFooter className="mt-4 text-xs text-text-muted">
            <span>
              {library.document_count ? `${library.document_count} 份文档` : "空库 · 等待添加"}
            </span>
            <time dateTime={library.updated_at}>
              更新于{" "}
              {new Date(library.updated_at).toLocaleDateString("zh-CN", {
                month: "numeric",
                day: "numeric",
              })}
            </time>
          </CardFooter>
        </CardContent>
      </Link>
    </Card>
  );
}
