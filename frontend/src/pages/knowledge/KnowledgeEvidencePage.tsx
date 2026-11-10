import { useLayoutEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { Button } from "@/components/ui/Button";
import { PageContainer } from "@/components/common/PageContainer";
import { PageHeading } from "@/components/common/PageHeading";
import { useWorkspaceData } from "@/state/workspace/useWorkspaceData";
import { useResource } from "@/state/shared/useResource";
import { KnowledgeFeedback } from "./KnowledgeLibraries";

function KnowledgeEvidence({ run, evidence }: { run: string; evidence: string }) {
  const [offset, setOffset] = useState(0);
  const resource = useWorkspaceData().knowledge.evidence(run, evidence, offset);
  useLayoutEffect(() => {
    if (!resource.active) resource.refresh();
  }, [resource]);
  const state = useResource(resource);
  const result = !state.loading && !state.failure ? state.data : undefined;
  return (
    <PageContainer>
      <KnowledgeFeedback
        shape="document"
        resource="document"
        failure={state.failure}
        loading={state.loading}
        hasUsableData={!!result}
        actions={[{ label: "返回员工", kind: "return", href: "/agents" }]}
        retry={() => resource.invalidate()}
      />
      {result && (
        <>
          <PageHeading
            title={result.title}
            description="本次任务已取得的知识来源片段"
            actions={
              <Button variant="ghost" nativeButton={false} render={<Link to="/agents" />}>
                返回员工
              </Button>
            }
          />
          <p className="mb-4 wrap-break-word text-sm text-text-muted">{result.locator}</p>
          <article
            aria-label="知识来源片段"
            className="max-w-prose whitespace-pre-wrap break-words text-sm leading-8"
          >
            {result.content}
          </article>
          <div className="mt-6 flex flex-wrap items-center gap-3 text-xs text-text-muted">
            <span>
              文档版本 {result.document_version.slice(0, 12)} · {offset + 1}—
              {offset + Array.from(result.content).length} / {result.total_chars} 字符
            </span>
            {offset > 0 && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setOffset(Math.max(0, offset - 2000))}
              >
                上一页
              </Button>
            )}
            {result.next_offset !== null && (
              <Button variant="outline" size="sm" onClick={() => setOffset(result.next_offset!)}>
                下一页
              </Button>
            )}
          </div>
        </>
      )}
    </PageContainer>
  );
}

export function KnowledgeEvidencePage() {
  const { runId = "", evidenceId = "" } = useParams();
  return <KnowledgeEvidence key={`${runId}:${evidenceId}`} run={runId} evidence={evidenceId} />;
}
export { KnowledgeEvidencePage as Component };
