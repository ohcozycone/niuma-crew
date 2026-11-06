import { FailureNotice } from "@/components/failure/FailureNotice";
import { FailureState } from "@/components/failure/FailureState";
import { Card } from "@/components/ui/Card";
import { ResourceIcon } from "@/components/common/ResourceIcon";
import { Link } from "react-router";
import { ORGANIZATION_RULES_URL } from "@/lib/navigation";
import { useIdentity } from "@/state/auth/useIdentity";
import { Button } from "@/components/ui/Button";
import { useOrganizationRules } from "./useOrganizationRules";
export function InheritedRules({ compact = false }: { compact?: boolean }) {
  const identity = useIdentity();
  if (!identity.permissions.includes("organization_rules:read")) return null;
  return <RulesSummary compact={compact} />;
}
function RulesSummary({ compact }: { compact: boolean }) {
  const { rules, failure, reload } = useOrganizationRules();
  const content = (
    <Card
      as="section"
      variant="outline"
      radius="panel"
      aria-label="继承的规章制度"
      className="p-4 text-sm leading-6"
    >
      <div className={"flex flex-wrap items-center justify-between gap-2"}>
        <h3 className={"font-semibold"}>公司规章制度</h3>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          render={<Link to={ORGANIZATION_RULES_URL} />}
          nativeButton={false}
        >
          查看与管理
        </Button>
      </div>
      {failure &&
        (rules ? (
          <FailureNotice
            failure={failure}
            context={{ operation: "refresh", hasUsableData: true }}
            actions={[{ label: "重试", kind: "retry", onClick: reload }]}
          />
        ) : (
          <FailureState
            failure={failure}
            layout="section"
            context={{ operation: "initial-read" }}
            actions={[{ label: "重试", kind: "retry", onClick: reload }]}
          />
        ))}
      {!rules ? (
        !failure && <p role="status">正在读取全局规则…</p>
      ) : rules.instructions ? (
        <>
          <p className={"text-text-muted"}>已自动继承 · 版本 {rules.revision} · 无需单独装配</p>
          <details className={"mt-2"}>
            <summary className={"cursor-pointer"}>查看制度原文</summary>
            <div className={"mt-3 max-h-64 overflow-auto whitespace-pre-wrap break-words"}>
              {rules.instructions}
            </div>
          </details>
        </>
      ) : (
        <p className={"text-text-muted"}>尚未配置全局规则。保存规章制度后，所有员工会自动继承。</p>
      )}
    </Card>
  );
  if (!compact) return content;
  return (
    <details className="text-sm">
      <summary className="flex cursor-pointer flex-wrap items-center gap-2">
        <ResourceIcon kind="rules" className="text-text-muted" />
        <span>公司规章制度</span>
        <span className="type-caption ml-auto">
          {failure
            ? "读取失败 · 查看"
            : !rules
              ? "正在读取…"
              : rules.instructions
                ? "已自动继承 · 查看"
                : "尚未配置 · 查看"}
        </span>
      </summary>
      <div className="mt-3">{content}</div>
    </details>
  );
}
