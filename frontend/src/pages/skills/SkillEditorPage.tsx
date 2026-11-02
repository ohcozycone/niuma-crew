import { FailureState } from "@/components/failure/FailureState";
import { PageContainer } from "@/components/common/PageContainer";
import { useNavigate, useParams, useSearchParams, Link } from "react-router";
import { useIdentity } from "@/state/auth/useIdentity";
import { identityKey } from "@/lib/identity";
import { Button } from "@/components/ui/Button";
import { PageHeading } from "@/components/common/PageHeading";
import { ResourceStatus } from "@/components/configuration/ResourceStatus";
import { useSkillEditor } from "./useSkillEditor";
import { clearDraft, draftKey } from "@/lib/draft";
import { returnPath } from "@/lib/navigation";
import { SkillEditor } from "./SkillEditor";
import { SkillPackageImport } from "./SkillPackageImport";
export function SkillEditorPage() {
  const data = useSkillEditor();
  return (
    <ResourceStatus data={data} resource="skill" returnTo="/skills">
      <Editor data={data} />
    </ResourceStatus>
  );
}
function Editor({ data }: { data: ReturnType<typeof useSkillEditor> }) {
  const { id } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const identity = useIdentity();
  const skill = data.skills.find((s) => s.id === id);
  if (!identity.permissions.includes("agents:read"))
    return (
      <PageContainer>
        <PageHeading
          title={skill?.name ?? "技能详情"}
          description={skill?.description ?? "当前账号仅可浏览技能。"}
        />
        {skill && (
          <dl className="mt-6 space-y-4 text-sm">
            <div>
              <dt className="font-medium">输入说明</dt>
              <dd className="mt-1 whitespace-pre-wrap text-text-muted">
                {skill.input || "未填写"}
              </dd>
            </div>
            <div>
              <dt className="font-medium">使用方式</dt>
              <dd className="mt-1 text-text-muted">
                由员工在任务中按需使用，工作方法由创建者维护。
              </dd>
            </div>
          </dl>
        )}
        <Link className="mt-6 inline-block underline" to="/skills">
          返回能力库
        </Link>
      </PageContainer>
    );
  if (id && !skill)
    return (
      <FailureState
        failure={{ source: "http", status: 404, code: "skill_not_found", message: "技能不存在。" }}
        context={{ operation: "initial-read", resource: "skill" }}
        actions={[{ label: "返回能力库", kind: "return", href: "/skills" }]}
      />
    );
  function close() {
    clearDraft(draftKey(identityKey(identity), `skill:${id || "new"}`));
    navigate(returnPath(params, "/skills"));
  }
  if (!id && params.get("import") === "1")
    return (
      <PageContainer className="space-y-6">
        <PageHeading
          title="导入技能包"
          description="检查文件与元数据，确认后进入同一个技能编辑器。"
          actions={
            <Button variant="outline" onClick={close}>
              取消
            </Button>
          }
        />
        <SkillPackageImport />
      </PageContainer>
    );
  return (
    <SkillEditor
      key={id || "new"}
      value={skill ?? "new"}
      onSave={async (value) => {
        await data.saveSkill(value, !id);
        close();
      }}
      onClose={close}
    />
  );
}
export { SkillEditorPage as Component };
