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
  const canUse = identity.permissions.includes("knowledge:manage");
  const canRead = canUse || identity.permissions.includes("knowledge:read");
  if (!canRead)
    return (
      <PageContainer>
        <PageHeading title="知识库" description="按业务整理资料，为检索和问答提供依据。" />
        <p className="mt-8 text-text-muted">
          {identity.actor.kind === "user"
            ? "知识库由管理员统一维护，请通过员工使用已配置的知识资料。"
            : "登录后可使用员工已配置的知识资料。"}
        </p>
        <Link
          className="mt-4 inline-block text-action underline"
          to={identity.actor.kind === "user" ? "/agents" : "/signin?next=%2Fknowledge"}
        >
          {identity.actor.kind === "user" ? "返回员工" : "登录"}
        </Link>
      </PageContainer>
    );
  if (documentId && id)
    return <KnowledgeDocumentPage key={`${id}:${documentId}`} kb={id} id={documentId} />;
  if (id === "new") return canUse ? <KnowledgeCreate /> : <Navigate replace to="/knowledge" />;
  if (id) return <KnowledgeLibrary key={id} id={id} />;
  if (canReadRules && params.get("tab") === "rules") return <Navigate replace to="/rules" />;
  return (
    <PageContainer>
      <KnowledgeLibraries />
    </PageContainer>
  );
}
export { KnowledgePage as Component };
