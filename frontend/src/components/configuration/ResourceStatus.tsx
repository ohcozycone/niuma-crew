import { PageContainer } from "@/components/common/PageContainer";
import { FailureState } from "@/components/failure/FailureState";
import { FailureNotice } from "@/components/failure/FailureNotice";
import type { Failure, FailureResource } from "@/lib/failures/types";

export function ResourceStatus({
  children,
  data,
  resource,
  returnTo,
}: {
  children: React.ReactNode;
  data: {
    ready: boolean;
    error: string;
    failure?: Failure | null;
    reload: () => void;
  };
  resource?: FailureResource;
  returnTo?: string;
}) {
  const actions = [
    { label: "重新加载", kind: "retry" as const, onClick: data.reload },
    ...(returnTo ? [{ label: "返回列表", kind: "return" as const, href: returnTo }] : []),
  ];
  if (!data.ready)
    return data.failure || data.error ? (
      <FailureState
        failure={data.failure}
        error={data.error}
        context={{ operation: "initial-read", resource }}
        actions={actions}
      />
    ) : (
      <PageContainer aria-busy>
        <p role="status">正在加载…</p>
      </PageContainer>
    );
  return (
    <>
      {(data.failure || data.error) && (
        <PageContainer className="pb-0">
          <FailureNotice
            failure={data.failure}
            error={data.error}
            context={{ operation: "refresh", resource, hasUsableData: true }}
            actions={actions}
          />
        </PageContainer>
      )}
      {children}
    </>
  );
}
