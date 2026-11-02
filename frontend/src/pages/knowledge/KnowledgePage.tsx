import { Plus } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Link, useParams, useSearchParams } from "react-router";
import { useIdentity } from "@/state/auth/useIdentity";
import { PageContainer } from "@/components/common/PageContainer";
import { PageHeading } from "@/components/common/PageHeading";
import { TabsContent } from "@/components/ui/Tabs";
import { PageTabs } from "@/components/common/PageTabs";
import { OrganizationRulesEditor } from "./OrganizationRulesEditor";
import { KnowledgeLibraries, KnowledgeCreate } from "./KnowledgeLibraries";
import { KnowledgeLibrary } from "./KnowledgeLibrary";
import { KnowledgeDocumentPage } from "./KnowledgeDocumentPage";

export function KnowledgePage() {
  const identity = useIdentity();
  const { id, documentId } = useParams();
  const [params, setParams] = useSearchParams();
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
  const tab = canReadRules && params.get("tab") === "rules" ? "rules" : "documents";
  return (
    <PageContainer>
      <PageHeading
        title="知识库"
        description="按业务建立知识库，在库内上传资料、检索并核对来源。"
        actions={
          tab === "documents" ? (
            <Button nativeButton={false} role="link" render={<Link to="/knowledge/new" />}>
              <Plus size={16} />
              新建知识库
            </Button>
          ) : undefined
        }
      />
      <PageTabs
        label="知识库内容"
        items={[
          { value: "documents", label: "知识资料" },
          ...(canReadRules ? [{ value: "rules", label: "规章制度" }] : []),
        ]}
        value={tab}
        onValueChange={(next) =>
          setParams(
            (current) => {
              const copy = new URLSearchParams(current);
              if (next === "rules") copy.set("tab", next);
              else copy.delete("tab");
              return copy;
            },
            { preventScrollReset: true },
          )
        }
      >
        <TabsContent value="documents">
          <KnowledgeLibraries />
        </TabsContent>
        <TabsContent value="rules">
          <OrganizationRulesEditor />
        </TabsContent>
      </PageTabs>
    </PageContainer>
  );
}
export { KnowledgePage as Component };
