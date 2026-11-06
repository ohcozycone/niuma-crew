import { Link, Navigate, useParams, useSearchParams } from "react-router";
import { useIdentity } from "@/state/auth/useIdentity";
import { PageContainer } from "@/components/common/PageContainer";
import { PageHeading } from "@/components/common/PageHeading";
import { KnowledgeLibraries, KnowledgeCreate } from "./KnowledgeLibraries";
import { KnowledgeLibrary } from "./KnowledgeLibrary";
import { KnowledgeDocumentPage } from "./KnowledgeDocumentPage";

export function KnowledgePage() {
  const identity = useIdentity();
  const { id, documentId } = useParams();
  const [params] = useSearchParams();
  const canReadRules = identity.permissions.includes("organization_rules:read");
  const canUse = identity.permissions.includes("knowledge:use");
  if (!canUse)
    return (
      <PageContainer>
        <PageHeading title="知识库" description="按业务整理资料，为检索和问答提供依据。" />
        <p className="mt-8 text-text-muted">登录后可创建知识库、上传文档和检索资料。</p>
        <Link className="mt-4 inline-block text-action underline" to="/signin?next=%2Fknowledge">
          登录
        </Link>
      </PageContainer>
    );
  if (documentId && id)
    return <KnowledgeDocumentPage key={`${id}:${documentId}`} kb={id} id={documentId} />;
  if (id === "new") return <KnowledgeCreate />;
  if (id) return <KnowledgeLibrary key={id} id={id} />;
  if (canReadRules && params.get("tab") === "rules") return <Navigate replace to="/rules" />;
  return (
    <PageContainer>
      <KnowledgeLibraries />
    </PageContainer>
  );
}
export { KnowledgePage as Component };
