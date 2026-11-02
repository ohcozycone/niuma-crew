import { FailureNotice } from "@/components/failure/FailureNotice";
import { FailureState } from "@/components/failure/FailureState";
import { toFailure, mutationOutcome } from "@/lib/failures/resolve";
import type { Failure } from "@/lib/failures/types";
import { FormField } from "@/components/common/FormField";
import { PageContainer } from "@/components/common/PageContainer";
import { SelectField } from "@/components/ui/SelectField";
import { Card } from "@/components/ui/Card";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { PageHeading } from "@/components/common/PageHeading";
import { ConfirmActionDialog } from "@/components/common/ConfirmActionDialog";
import { ResourceIcon } from "@/components/common/ResourceIcon";
import { Button } from "@/components/ui/Button";
import {
  listToolConnections,
  myToolBindings,
  bindMyTool,
  type PersonalToolBinding,
  type ToolConnection,
} from "@/lib/api/tools";
import { useIdentity } from "@/state/auth/useIdentity";
export function PersonalConnectionsPage() {
  const { id } = useParams();
  const identity = useIdentity();
  return (
    <PersonalConnections
      key={`${id}:${identity.actor.user?.id ?? "guest"}`}
      id={id!}
      userId={identity.actor.user?.id}
    />
  );
}
function PersonalConnections({ id, userId }: { id: string; userId?: string }) {
  const [items, setItems] = useState<PersonalToolBinding[]>([]);
  const [connections, setConnections] = useState<ToolConnection[]>([]);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [pending, setPending] = useState<{ item: PersonalToolBinding; value: string } | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([myToolBindings(id!, controller.signal), listToolConnections(controller.signal)])
      .then(([data, rows]) => {
        if (!controller.signal.aborted) {
          setItems(data.items);
          setConnections(rows.filter((row) => row.created_by_user_id === userId));
          setLoaded(true);
          setFailure(null);
        }
      })
      .catch((e) => {
        if (!controller.signal.aborted) {
          const value = toFailure(e);
          setFailure(value);
          if ([401, 403, 404].includes(value?.status ?? 0)) {
            setItems([]);
            setConnections([]);
            setLoaded(false);
          }
        }
      });
    return () => controller.abort();
  }, [id, userId, revision]);
  async function bind(item: PersonalToolBinding, value: string) {
    setBusy(true);
    setFailure(null);
    try {
      setItems((await bindMyTool(id!, item, value || null)).items);
      setPending(null);
    } catch (e) {
      setFailure(toFailure(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <PageContainer as="main" className="space-y-6">
      <Link to={`/agents/${id}`} className="text-sm underline">
        返回员工
      </Link>
      <PageHeading
        title="我的工具连接"
        description="员工的工作方法由创建者维护；这里仅绑定你自己的账号。"
      />
      <Button render={<Link to={`/conversations/new?agent=${id}&resume=1`} />} nativeButton={false}>
        与员工对话
      </Button>
      {failure &&
        (loaded ? (
          <FailureNotice
            failure={failure}
            context={{
              operation: "mutation",
              resource: "connection",
              outcome: mutationOutcome(failure),
            }}
          />
        ) : (
          <FailureState
            failure={failure}
            context={{ operation: "initial-read", resource: "connection" }}
            actions={[
              {
                label: "重新加载",
                kind: "retry",
                onClick: () => setRevision((value) => value + 1),
              },
              { label: "返回员工", kind: "return", href: `/agents/${id}` },
            ]}
          />
        ))}
      {!loaded && !failure && <p role="status">正在读取连接…</p>}
      {loaded && !items.length && <p>此员工没有需要配置的 MCP 账号。</p>}
      {items.map((item) => (
        <Card as="section" variant="outline" key={item.grant_id} className="form-panel space-y-6">
          <h2 className="type-title flex items-center gap-2">
            <ResourceIcon kind="mcp" />
            {item.service_name}
          </h2>
          <p className="type-description">
            {item.account_mode === "shared"
              ? "本员工共用账号，由创建者维护。"
              : item.connected
                ? "已连接本人账号。"
                : "尚未连接兼容的本人账号，普通聊天仍可使用。"}
          </p>
          {item.account_mode === "personal" && (
            <>
              <FormField label={<>选择我的账号</>}>
                <SelectField
                  disabled={busy}
                  value={item.connection_id ?? ""}
                  onValueChange={(nextValue) => {
                    if (nextValue === (item.connection_id ?? "")) return;
                    if (item.connection_id || item.connected) {
                      setFailure(null);
                      setPending({ item, value: nextValue });
                    } else void bind(item, nextValue);
                  }}
                  options={[
                    { value: "", label: item.creator_default ? "沿用员工装配账号" : "未绑定" },
                    ...connections
                      .filter((row) => row.service_id === item.service_id)
                      .map((row) => ({
                        value: row.id,
                        label: `${row.name}${!row.enabled ? "（已停用）" : ""}`,
                      })),
                  ]}
                />
              </FormField>
              <Link to={`/tools?service=${item.service_id}`} className="text-sm underline">
                配置本人凭据与工具目录
              </Link>
              <p className="type-caption">
                新连接需先读取、确认目录，定义必须与员工所选操作一致；保存后重新发送任务即可使用。
              </p>
            </>
          )}
        </Card>
      ))}
      <ConfirmActionDialog
        open={!!pending}
        onOpenChange={(open) => {
          if (!open) setPending(null);
        }}
        title={
          pending?.value
            ? `切换「${pending.item.service_name}」的账号？`
            : `解除「${pending?.item.service_name ?? "工具"}」的本人绑定？`
        }
        description={
          pending?.value
            ? "保存后，后续任务将使用所选账号；员工的操作许可和原账号配置保持不变。"
            : pending?.item.creator_default
              ? "解除本人选择后将沿用员工装配账号，不删除账号或员工的工具许可。"
              : "解除后该个人账号不再用于此员工的后续任务，不删除账号或员工的工具许可。"
        }
        confirmLabel={pending?.value ? "确认切换" : "确认解除绑定"}
        busy={busy}
        onConfirm={() => {
          if (pending) void bind(pending.item, pending.value);
        }}
      >
        {failure && (
          <FailureNotice
            failure={failure}
            context={{
              operation: "mutation",
              resource: "connection",
              outcome: mutationOutcome(failure),
            }}
          />
        )}
      </ConfirmActionDialog>
    </PageContainer>
  );
}
export { PersonalConnectionsPage as Component };
