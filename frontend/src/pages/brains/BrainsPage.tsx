import { FailureState } from "@/components/failure/FailureState";
import { clientFailure } from "@/lib/failures/resolve";
import { PageContainer } from "@/components/common/PageContainer";
import { useIdentity } from "@/state/auth/useIdentity";
import { BrainWorkspace } from "./BrainWorkspace";
export function BrainsPage() {
  const identity = useIdentity();
  if (!identity.permissions.includes("agents:read"))
    return (
      <PageContainer>
        <FailureState
          failure={clientFailure("permission_denied", "大脑配置需要管理员权限。")}
          context={{ operation: "initial-read", resource: "connection" }}
          actions={[{ label: "返回员工列表", kind: "return", href: "/agents" }]}
        />
      </PageContainer>
    );
  return <BrainWorkspace />;
}

export { BrainsPage as Component };
