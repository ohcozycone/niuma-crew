import { useNavigate } from "react-router";
import { FailureState } from "@/components/failure/FailureState";
import { clientFailure } from "@/lib/failures/resolve";
import { IdentityProvider } from "@/state/auth/IdentityProvider";
import { useIdentitySession } from "@/state/auth/useIdentity";

type AuthBoundaryProps = { children: React.ReactNode; permission?: string };

function AuthGate({ children, permission }: AuthBoundaryProps) {
  const navigate = useNavigate();
  const { identity, failure, reload } = useIdentitySession();
  if (failure)
    return (
      <FailureState
        failure={failure}
        layout="page"
        title="暂时无法确认登录状态"
        context={{ operation: "initial-read", resource: "page" }}
        actions={[{ label: "重新连接", kind: "retry", onClick: reload }]}
      />
    );
  if (!identity)
    return (
      <main className="page-frame py-6" aria-busy="true">
        <p role="status">正在确认登录状态…</p>
      </main>
    );
  if (permission && !identity.permissions.includes(permission))
    return (
      <FailureState
        failure={clientFailure("permission_denied", "此页面需要管理员权限。")}
        layout="page"
        title="无权访问此页面"
        context={{ operation: "initial-read", resource: "page" }}
        actions={[
          {
            label: "返回员工列表",
            kind: "return",
            onClick: () => navigate("/agents", { replace: true }),
          },
        ]}
      />
    );
  return children;
}

export function AuthBoundary({ children, permission }: AuthBoundaryProps) {
  return (
    <IdentityProvider>
      <AuthGate permission={permission}>{children}</AuthGate>
    </IdentityProvider>
  );
}
