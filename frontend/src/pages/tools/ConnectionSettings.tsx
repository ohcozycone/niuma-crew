import { FailureNotice } from "@/components/failure/FailureNotice";
import { toFailure, mutationOutcome } from "@/lib/failures/resolve";
import type { Failure } from "@/lib/failures/types";
import { FormField } from "@/components/common/FormField";
import { SelectField } from "@/components/ui/SelectField";
import { Card } from "@/components/ui/Card";
import { useState } from "react";
import { useEditingRegistration } from "@/state/editing/useEditing";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import {
  patchToolConnection,
  deleteToolConnection,
  type ToolConnection,
  type McpService,
} from "@/lib/api/tools";
import { DeleteToolDialog } from "./DeleteToolDialog";
import { ConfirmActionDialog } from "@/components/common/ConfirmActionDialog";

import {
  OAuthConfigurationFields,
  oauthPublicConfig,
  type OAuthFieldsValue,
} from "./OAuthConfigurationFields";

export function ConnectionSettings({
  connection,
  service,
  onChange,
  onDelete,
  onConfigureFields,
}: {
  connection: ToolConnection;
  service?: McpService;
  onChange: (value: ToolConnection) => void;
  onDelete: () => void;
  onConfigureFields?: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(connection.name);
  const [auth, setAuth] = useState(connection.auth_type);
  const [header, setHeader] = useState(String(connection.public_config.header_name ?? "X-API-Key"));
  const [secret, setSecret] = useState("");
  const [oauth, setOAuth] = useState<OAuthFieldsValue>({
    scopes: (
      (connection.public_config.oauth as { scopes?: string[] } | undefined)?.scopes ?? []
    ).join(" "),
    clientId:
      (connection.public_config.oauth as { client_id?: string } | undefined)?.client_id ?? "",
    clientSecret: "",
  });
  const [environment, setEnvironment] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [disabling, setDisabling] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);
  const stdio = connection.kind === "mcp_stdio";
  const suggestedHeader = service?.input_fields?.[0]?.name;
  const keys =
    auth === connection.auth_type && auth === "env"
      ? ((connection.public_config.env_keys as string[] | undefined) ?? service?.env_keys ?? [])
      : (service?.env_keys ?? []);
  const replacingEnvironment = Object.values(environment).some(Boolean);
  const needsSecret =
    auth !== "none" &&
    auth !== "oauth" &&
    (!connection.has_credential || auth !== connection.auth_type);
  const invalid =
    stdio && auth === "env"
      ? !keys.length ||
        ((needsSecret || replacingEnvironment) && keys.some((key) => !environment[key]))
      : needsSecret && !secret;
  function clear() {
    setEditing(false);
    setSecret("");
    setOAuth((value) => ({ ...value, clientSecret: "" }));
    setEnvironment({});
  }
  useEditingRegistration({
    dirty:
      editing &&
      (name !== connection.name ||
        auth !== connection.auth_type ||
        header !== String(connection.public_config.header_name ?? "X-API-Key") ||
        !!secret ||
        (auth === "oauth" &&
          (oauth.scopes !==
            (
              (connection.public_config.oauth as { scopes?: string[] } | undefined)?.scopes ?? []
            ).join(" ") ||
            oauth.clientId !==
              ((connection.public_config.oauth as { client_id?: string } | undefined)?.client_id ??
                "") ||
            !!oauth.clientSecret)) ||
        replacingEnvironment),
    saving: busy,
    isSaving: () => busy,
    discard: clear,
  });
  async function perform(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setFailure(null);
    try {
      await action();
    } catch (e) {
      setFailure(toFailure(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <p className="mr-auto type-caption">
          {connection.auth_type === "oauth"
            ? connection.oauth_status === "connected"
              ? "OAuth 账号已连接"
              : connection.oauth_status === "reauth_required"
                ? "OAuth 授权需要重新连接"
                : "OAuth 账号尚未连接"
            : connection.auth_type === "none"
              ? "当前不提供密钥（匿名访问）"
              : "已配置凭据，密钥不会回显"}{" "}
          · {connection.enabled ? "已启用" : "已停用"}
        </p>
        {!editing && connection.kind !== "native" && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => {
              setName(connection.name);
              setAuth(
                connection.auth_type === "none"
                  ? stdio
                    ? service?.env_keys.length
                      ? "env"
                      : "none"
                    : suggestedHeader && suggestedHeader.toLowerCase() !== "authorization"
                      ? "header"
                      : "bearer"
                  : connection.auth_type,
              );
              setHeader(
                String(connection.public_config.header_name ?? suggestedHeader ?? "X-API-Key"),
              );
              setFailure(null);
              setOAuth({
                scopes: (
                  (connection.public_config.oauth as { scopes?: string[] } | undefined)?.scopes ??
                  []
                ).join(" "),
                clientId:
                  (connection.public_config.oauth as { client_id?: string } | undefined)
                    ?.client_id ?? "",
                clientSecret: "",
              });
              setEditing(true);
            }}
          >
            {connection.auth_type === "none" ? "配置密钥" : "修改访问设置"}
          </Button>
        )}
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={busy}
          onClick={() =>
            connection.enabled
              ? setDisabling(true)
              : void perform(async () => {
                  onChange(await patchToolConnection(connection, { enabled: true }));
                })
          }
        >
          {connection.enabled ? "停用连接" : "启用连接"}
        </Button>
        <DeleteToolDialog
          title="删除连接"
          description={`删除“${connection.name}”及其保存的凭据。已被员工装配或个人绑定的连接不能删除，需先解除引用。`}
          onDelete={async () => {
            await deleteToolConnection(connection);
            onDelete();
          }}
        />
      </div>
      <ConfirmActionDialog
        open={disabling}
        onOpenChange={setDisabling}
        title={`停用「${connection.name}」连接？`}
        description="确认后立即阻止此连接的后续工具调用，使用该连接的员工和个人绑定都会受到影响。配置与凭据保留，可重新启用。"
        confirmLabel="确认停用连接"
        busy={busy}
        onConfirm={() =>
          void perform(async () => {
            onChange(await patchToolConnection(connection, { enabled: false }));
            setDisabling(false);
          })
        }
      >
        <FailureNotice
          failure={failure}
          context={{
            operation: "mutation",
            resource: "connection",
            outcome: mutationOutcome(failure),
          }}
        />
      </ConfirmActionDialog>
      {editing && (
        <Card
          as="form"
          variant="muted"
          radius="control"
          aria-label="修改访问设置"
          className="form-grid p-4"
          onSubmit={(event) => {
            event.preventDefault();
            void perform(async () => {
              const config: Record<string, unknown> = {
                ...connection.public_config,
                ...(stdio
                  ? { env_keys: auth === "none" ? [] : keys }
                  : auth === "header"
                    ? { header_name: header }
                    : {}),
              };
              if (!stdio && auth !== "header") delete config.header_name;
              if (auth === "oauth") config.oauth = oauthPublicConfig(oauth);
              else delete config.oauth;
              const saved = await patchToolConnection(connection, {
                name,
                auth_type: auth,
                public_config: config,
                ...(auth === "oauth" && oauth.clientSecret
                  ? { oauth_client_secret: oauth.clientSecret }
                  : {}),
                ...(stdio
                  ? replacingEnvironment
                    ? { environment }
                    : {}
                  : secret
                    ? { credential: secret }
                    : {}),
              });
              onChange(saved);
              clear();
            });
          }}
        >
          <FormField label={<>连接名称</>}>
            <Input required value={name} onChange={(e) => setName(e.target.value)} />
          </FormField>
          <FormField label={<>认证方式</>}>
            <SelectField
              value={auth}
              onValueChange={(nextValue) => {
                setAuth(nextValue);
                setSecret("");
                setEnvironment({});
              }}
              options={[
                { value: "none", label: "不提供密钥（匿名访问）" },
                ...(stdio
                  ? [
                      {
                        value: "env",
                        label: "环境变量（API Key 等）",
                        disabled: !service?.env_keys.length,
                      },
                    ]
                  : [
                      { value: "bearer", label: "API Key / Bearer Token" },
                      { value: "header", label: "自定义认证头" },
                      { value: "oauth", label: "OAuth（浏览器授权）" },
                    ]),
              ]}
            />
          </FormField>
          {stdio && !service?.env_keys.length && (
            <p className="type-caption col-span-full">
              此服务尚未声明密钥字段。
              {onConfigureFields ? (
                <Button type="button" variant="link" onClick={onConfigureFields}>
                  设置凭据字段
                </Button>
              ) : (
                "请联系服务创建者补充允许的环境变量名。"
              )}
            </p>
          )}
          {auth === "oauth" && <OAuthConfigurationFields value={oauth} onChange={setOAuth} />}
          {auth === "header" && (
            <FormField label={<>认证头名称</>}>
              <Input required value={header} onChange={(e) => setHeader(e.target.value)} />
            </FormField>
          )}
          {stdio && auth === "env"
            ? keys.map((key) => (
                <FormField key={key} label={<>{key}</>}>
                  <Input
                    type="password"
                    autoComplete="off"
                    required={needsSecret || replacingEnvironment}
                    value={environment[key] ?? ""}
                    placeholder={
                      needsSecret
                        ? "填写 API Key 或对应参数值"
                        : "留空保留已保存值；更换时填写全部字段"
                    }
                    onChange={(e) =>
                      setEnvironment((current) => ({ ...current, [key]: e.target.value }))
                    }
                  />
                </FormField>
              ))
            : auth !== "none" &&
              auth !== "oauth" && (
                <FormField label={<>API Key / Token</>}>
                  <Input
                    type="password"
                    autoComplete="off"
                    required={needsSecret}
                    value={secret}
                    placeholder={needsSecret ? "填写 API Key" : "留空保留已保存密钥"}
                    onChange={(e) => setSecret(e.target.value)}
                  />
                </FormField>
              )}
          <p className="type-caption col-span-full">
            更换密钥或认证方式后，需要重新读取并确认工具列表；不会自动切换员工使用的账号。
          </p>
          <div className="flex justify-end gap-2 col-span-full">
            <Button type="button" variant="outline" disabled={busy} onClick={clear}>
              取消
            </Button>
            <Button type="submit" disabled={busy || invalid || !name.trim()}>
              保存访问设置
            </Button>
          </div>
        </Card>
      )}
      <FailureNotice
        failure={failure}
        context={{
          operation: "mutation",
          resource: "connection",
          outcome: mutationOutcome(failure),
        }}
      />
    </div>
  );
}
