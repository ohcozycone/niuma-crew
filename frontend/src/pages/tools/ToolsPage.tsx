import { FailureNotice } from "@/components/failure/FailureNotice";
import { FailureState } from "@/components/failure/FailureState";
import { clientFailure, toFailure, mutationOutcome } from "@/lib/failures/resolve";
import type { Failure } from "@/lib/failures/types";
import { FormField } from "@/components/common/FormField";
import { PageContainer } from "@/components/common/PageContainer";
import { SelectField } from "@/components/ui/SelectField";
import { Card } from "@/components/ui/Card";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams, useNavigate } from "react-router";
import { useIdentity } from "@/state/auth/useIdentity";
import { PageHeading } from "@/components/common/PageHeading";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { Upload } from "lucide-react";
import { McpQuickImport, type McpImportEntry } from "./McpQuickImport";
import { OAuthConnectionPanel } from "./OAuthConnectionPanel";
import {
  OAuthConfigurationFields,
  emptyOAuthFields,
  oauthPublicConfig,
} from "./OAuthConfigurationFields";
import { McpSetupAccess } from "./McpSetupAccess";
import { useWorkspaceData } from "@/state/workspace/useWorkspaceData";
import { useEditingRegistration } from "@/state/editing/useEditing";
import {
  listToolConnections,
  createToolConnection,
  listMcpServices,
  createMcpService,
  patchMcpService,
  deleteMcpService,
  discoverTools,
  type McpInputField,
  toolCapabilities,
  type ToolConnection,
  type McpService,
} from "@/lib/api/tools";
import { ToolCatalogEditor } from "./ToolCatalogEditor";
import { ConnectionSettings } from "./ConnectionSettings";
import { DeleteToolDialog } from "./DeleteToolDialog";
import { ConfirmActionDialog } from "@/components/common/ConfirmActionDialog";
import { ResourceIcon } from "@/components/common/ResourceIcon";

export function ToolsPage() {
  const identity = useIdentity();
  const shared = useWorkspaceData();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [services, setServices] = useState<McpService[]>([]);
  const [connections, setConnections] = useState<ToolConnection[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const [disabling, setDisabling] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [inputFields, setInputFields] = useState<McpInputField[]>([]);
  const [notice, setNotice] = useState("");
  const [savedConnectionId, setSavedConnectionId] = useState<string | null>(null);
  const [transport, setTransport] = useState<"http" | "stdio">("http");
  const [capabilities, setCapabilities] = useState({
    stdio_enabled: false,
    stdio_registration_allowed: false,
    max_stdio_processes: 0,
  });
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [url, setUrl] = useState("");
  const [command, setCommand] = useState("");
  const [args, setArgs] = useState("[]");
  const [envKeys, setEnvKeys] = useState("");
  const [environment, setEnvironment] = useState<Record<string, string>>({});
  const [account, setAccount] = useState("");
  const [scope, setScope] = useState("personal");
  const [auth, setAuth] = useState("none");
  const [header, setHeader] = useState("X-API-Key");
  const [token, setToken] = useState("");
  const [oauth, setOAuth] = useState(emptyOAuthFields);
  const [stdioAuth, setStdioAuth] = useState("none");
  const [serviceEnvKeys, setServiceEnvKeys] = useState("");
  const [serviceEditing, setServiceEditing] = useState(false);
  const [serviceName, setServiceName] = useState("");
  const [serviceDescription, setServiceDescription] = useState("");
  const service = services.find((item) => item.id === params.get("service"));
  const native = params.get("native") === "1";
  const userId = identity.actor.user?.id;
  function clear() {
    setName("");
    setDescription("");
    setUrl("");
    setCommand("");
    setArgs("[]");
    setEnvKeys("");
    setAccount("");
    setToken("");
    setOAuth(emptyOAuthFields);
    setEnvironment({});
    setInputFields([]);
    setServiceEditing(false);
  }
  useEditingRegistration({
    dirty: !!(
      name ||
      description ||
      url ||
      command ||
      args !== "[]" ||
      envKeys ||
      account ||
      token ||
      oauth.scopes ||
      oauth.clientId ||
      oauth.clientSecret ||
      Object.values(environment).some(Boolean) ||
      serviceEditing
    ),
    saving: busy,
    isSaving: () => busy,
    discard: clear,
  });
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      listMcpServices(controller.signal),
      listToolConnections(controller.signal),
      toolCapabilities(controller.signal),
    ])
      .then(([definitions, accounts, supported]) => {
        if (!controller.signal.aborted) {
          setServices(definitions);
          setConnections(accounts);
          setCapabilities(supported);
          setFailure(null);
          setLoaded(true);
        }
      })
      .catch((e) => {
        if (!controller.signal.aborted) {
          const value = toFailure(e);
          setFailure(value);
          if ([401, 403, 404].includes(value?.status ?? 0)) {
            setServices([]);
            setConnections([]);
            setLoaded(false);
          }
        }
      });
    return () => controller.abort();
  }, [revision]);
  useEffect(() => {
    if (serviceEditing)
      document.getElementById("mcp-service-information")?.scrollIntoView?.({ block: "start" });
  }, [serviceEditing]);
  useEffect(() => {
    if (!loaded || !params.has("oauth_error")) return;
    setFailure(
      clientFailure("oauth_session_expired", "授权回调未完成，请重新打开对应 MCP 并连接账号。"),
    );
    const next = new URLSearchParams(params);
    next.delete("oauth_error");
    setParams(next, { replace: true });
  }, [loaded, params, setParams]);
  async function perform(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setFailure(null);
    setSavedConnectionId(null);
    try {
      await action();
    } catch (e) {
      setFailure(toFailure(e));
    } finally {
      setBusy(false);
    }
  }
  function updateConnection(value: ToolConnection) {
    setConnections((current) => [...current.filter((item) => item.id !== value.id), value]);
    if (value.id === savedConnectionId) {
      setFailure(null);
      setNotice("");
      setSavedConnectionId(null);
    }
  }
  function fillImport(
    entry: McpImportEntry,
    values: { credential: string; environment: Record<string, string> },
  ) {
    setName(entry.name);
    if (entry.description) setDescription(entry.description);
    setTransport(entry.transport);
    setUrl(entry.url ?? "");
    setCommand(entry.command ?? "");
    setArgs(JSON.stringify(entry.args ?? []));
    setEnvKeys((entry.env_keys ?? []).join("\n"));
    setInputFields(entry.input_fields ?? []);
    setEnvironment(values.environment);
    setToken(values.credential);
    setAuth(entry.auth_type);
    setStdioAuth(entry.auth_type === "env" ? "env" : "none");
    setHeader(entry.header_name ?? "X-API-Key");
  }
  async function addService(event: FormEvent) {
    event.preventDefault();
    await perform(async () => {
      let argv: unknown = [];
      if (transport === "stdio") {
        try {
          argv = JSON.parse(args);
        } catch {
          throw clientFailure("mcp_args_invalid", "程序参数必须为 JSON 字符串数组。");
        }
      }
      if (!Array.isArray(argv) || !argv.every((arg) => typeof arg === "string"))
        throw clientFailure("mcp_args_invalid", "程序参数必须为字符串数组。");
      const result = await createMcpService({
        name,
        description,
        transport,
        input_fields: inputFields,
        ...(transport === "http"
          ? { url }
          : { command, args: argv as string[], env_keys: envKeys.split(/[\s,]+/).filter(Boolean) }),
      });
      shared.capabilitiesChanged();
      setServices((current) => [result, ...current]);
      setParams({ service: result.id });
      const selected = Object.fromEntries(
        Object.entries(environment).filter(
          ([key, value]) => value.trim() && result.env_keys.includes(key),
        ),
      );
      const optionalHttp =
        inputFields.length > 0 && inputFields.every((field) => !field.is_required);
      const connectionAuth =
        transport === "stdio"
          ? stdioAuth === "env" && Object.keys(selected).length
            ? "env"
            : "none"
          : auth !== "none" && auth !== "oauth" && !token && optionalHttp
            ? "none"
            : auth;
      let saved: ToolConnection | null = null;
      try {
        const connection = await createToolConnection({
          service_id: result.id,
          name: account.trim() || `${result.name} · 我的访问设置`,
          account_scope: scope,
          kind: transport === "stdio" ? "mcp_stdio" : "mcp_http",
          auth_type: connectionAuth,
          public_config:
            transport === "stdio"
              ? {
                  command: result.command,
                  args: result.args,
                  env_keys: connectionAuth === "env" ? Object.keys(selected) : [],
                }
              : {
                  url: result.url,
                  ...(connectionAuth === "header" ? { header_name: header } : {}),
                  ...(connectionAuth === "oauth" ? { oauth: oauthPublicConfig(oauth) } : {}),
                },
          ...(connectionAuth === "oauth" && oauth.clientSecret
            ? { oauth_client_secret: oauth.clientSecret }
            : {}),
          ...(connectionAuth === "env"
            ? { environment: selected }
            : connectionAuth !== "none" && connectionAuth !== "oauth"
              ? { credential: token }
              : {}),
        });
        updateConnection(connection);
        saved = connection;
        clear();
        setNotice("配置已保存，正在测试连接并读取工具…");
        if (connection.auth_type === "oauth") {
          clear();
          setParams({ service: result.id, oauth_connect: connection.id });
          setNotice("访问设置已保存，请完成浏览器授权。");
          return;
        }
        const discovered = await discoverTools(connection.id);
        updateConnection(discovered);
        setNotice(
          `连接成功，发现 ${(discovered.discovery_candidate?.tools ?? discovered.approved_catalog).length} 个工具。核对下方列表并确认后，可到员工页面装配。`,
        );
      } catch (error) {
        setSavedConnectionId(saved?.id ?? null);
        setNotice(
          saved
            ? "访问设置已保存，连接测试未通过。修改访问设置后，可点“读取工具列表”重试。"
            : "服务已保存。尚未保存的密钥保留在下方访问设置，请核对后重试。",
        );
        throw error;
      }
    });
  }
  async function addConnection(event: FormEvent) {
    event.preventDefault();
    await perform(async () => {
      const stdio = service?.transport === "stdio";
      const result = await createToolConnection(
        native
          ? {
              name: account,
              kind: "native",
              provider_key: "workspace",
              public_config: { workspace_mode: params.get("mode") ?? "virtual" },
            }
          : {
              name: account,
              kind: stdio ? "mcp_stdio" : "mcp_http",
              service_id: service!.id,
              account_scope: scope,
              auth_type: stdio
                ? service!.env_keys.length && stdioAuth === "env"
                  ? "env"
                  : "none"
                : auth,
              public_config: stdio
                ? {
                    command: service!.command,
                    args: service!.args,
                    env_keys: stdioAuth === "env" ? service!.env_keys : [],
                  }
                : {
                    url: service!.url,
                    ...(auth === "header" ? { header_name: header } : {}),
                    ...(auth === "oauth" ? { oauth: oauthPublicConfig(oauth) } : {}),
                  },
              ...(auth === "oauth" && oauth.clientSecret
                ? { oauth_client_secret: oauth.clientSecret }
                : {}),
              ...(stdio
                ? { environment: stdioAuth === "env" ? environment : {} }
                : auth !== "none" && auth !== "oauth"
                  ? { credential: token }
                  : {}),
            },
      );
      updateConnection(result);
      if (result.auth_type === "oauth")
        setParams({ service: service!.id, oauth_connect: result.id });
      setOAuth(emptyOAuthFields);
      setAccount("");
      setToken("");
      setEnvironment({});
    });
  }
  const visible = connections.filter((item) =>
    native ? item.kind === "native" : service ? item.service_id === service.id : false,
  );
  const creating = !service && !native && !params.get("service");
  const ownService = service?.owner_user_id === userId;
  const initialAccessInvalid =
    creating &&
    (transport === "stdio" && stdioAuth === "env"
      ? !envKeys.trim() ||
        envKeys
          .split(/[\s,]+/)
          .filter(Boolean)
          .some(
            (key) =>
              (inputFields.find((field) => field.name === key)?.is_required ?? true) &&
              !environment[key]?.trim(),
          )
      : transport === "http" &&
        auth !== "none" &&
        auth !== "oauth" &&
        (!inputFields.length || inputFields.some((field) => field.is_required)) &&
        !token.trim());
  return (
    <PageContainer as="main" className="space-y-6">
      <PageHeading
        title={native ? "内置文件与代码工具" : (service?.name ?? "接入 MCP")}
        description={
          native
            ? "配置文件读写与代码执行的访问方式和可用操作，再到员工页面装配。可用能力取决于运行环境。"
            : service?.description || "登记服务，配置账号并确认目录，再由员工主动装配。"
        }
        actions={
          creating ? (
            <>
              <Button
                variant="outline"
                render={<Link to="/skills" />}
                nativeButton={false}
                disabled={busy}
                onClick={clear}
              >
                取消
              </Button>
              <Button
                type="submit"
                form="mcp-service"
                disabled={
                  busy ||
                  !loaded ||
                  initialAccessInvalid ||
                  !name.trim() ||
                  (transport === "http"
                    ? !url
                    : !command || !capabilities.stdio_registration_allowed)
                }
              >
                {busy
                  ? "正在保存…"
                  : auth === "oauth" && transport === "http"
                    ? "保存并连接账号"
                    : "保存并测试"}
              </Button>
            </>
          ) : serviceEditing && service ? (
            <>
              <Button variant="outline" disabled={busy} onClick={() => setServiceEditing(false)}>
                取消
              </Button>
              <Button
                disabled={busy || !serviceName.trim()}
                onClick={() =>
                  void perform(async () => {
                    const saved = await patchMcpService(service, {
                      name: serviceName,
                      description: serviceDescription,
                      ...(service.transport === "stdio"
                        ? { env_keys: serviceEnvKeys.split(/[\s,]+/).filter(Boolean) }
                        : {}),
                    });
                    shared.capabilitiesChanged();
                    setServices((current) =>
                      current.map((item) => (item.id === saved.id ? saved : item)),
                    );
                    setServiceEditing(false);
                  })
                }
              >
                {busy
                  ? "正在保存…"
                  : auth === "oauth" && transport === "http"
                    ? "保存并连接账号"
                    : "保存并测试"}
                信息
              </Button>
            </>
          ) : ownService ? (
            <>
              <Button
                variant="outline"
                onClick={() => {
                  setServiceName(service!.name);
                  setServiceDescription(service!.description);
                  setServiceEnvKeys(service!.env_keys.join("\n"));
                  setServiceEditing(true);
                }}
              >
                编辑服务信息
              </Button>
              <DeleteToolDialog
                title="删除 MCP"
                description={`删除“${service!.name}”和你在此服务下保存的连接与凭据。已有员工装配或其他用户连接时将拒绝删除；不会自动卸载员工。`}
                onDelete={async () => {
                  await deleteMcpService(service!);
                  shared.capabilitiesChanged();
                  setServices((current) => current.filter((item) => item.id !== service!.id));
                  setConnections((current) =>
                    current.filter((item) => item.service_id !== service!.id),
                  );
                  clear();
                  setParams({});
                  navigate("/skills");
                }}
              />
            </>
          ) : undefined
        }
      />
      {!loaded && !failure && <p role="status">正在读取…</p>}
      {notice && (
        <p role="status" className="text-sm">
          {notice}
        </p>
      )}
      {failure &&
        (loaded ? (
          <FailureNotice
            failure={failure}
            context={{
              operation: "mutation",
              resource: "connection",
              outcome: savedConnectionId ? "rejected" : mutationOutcome(failure),
            }}
            actions={
              savedConnectionId &&
              connections.some(
                (item) => item.id === savedConnectionId && item.created_by_user_id === userId,
              )
                ? [
                    {
                      label: "检查访问设置",
                      kind: "configure",
                      href: `#tool-connection-${savedConnectionId}`,
                    },
                  ]
                : []
            }
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
              { label: "返回能力库", kind: "return", href: "/skills" },
            ]}
          />
        ))}
      {loaded && creating && (
        <Card
          as="form"
          variant="outline"
          id="mcp-service"
          onSubmit={(e) => void addService(e)}
          className="form-panel space-y-6"
        >
          <fieldset disabled={busy} className="space-y-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="type-title">服务信息</h2>
              <Button type="button" variant="outline" size="sm" onClick={() => setImportOpen(true)}>
                <Upload />
                快捷导入
              </Button>
            </div>
            <FormField label={<>服务名称</>}>
              <Input required value={name} onChange={(e) => setName(e.target.value)} />
            </FormField>
            <FormField label={<>功能说明</>}>
              <Textarea
                rows={3}
                value={description}
                maxLength={4000}
                onChange={(e) => setDescription(e.target.value)}
              />
            </FormField>
            <FormField label={<>接入方式</>}>
              <SelectField
                value={transport}
                onValueChange={(nextValue) => {
                  setTransport(nextValue as "http" | "stdio");
                  setInputFields([]);
                  setEnvironment({});
                  setToken("");
                  setAuth("none");
                }}
                options={[
                  { value: "http", label: "远程 Streamable HTTP" },
                  {
                    value: "stdio",
                    label: "本地 stdio（管理员登记可信程序）",
                    disabled:
                      !capabilities.stdio_registration_allowed || !capabilities.stdio_enabled,
                  },
                ]}
              />
            </FormField>
            {!capabilities.stdio_enabled && (
              <p className="type-caption">
                当前部署未开启本地 stdio，只能接入远程 HTTP；开启后刷新页面即可选择。
              </p>
            )}
            {transport === "http" ? (
              <FormField
                label="MCP 服务地址"
                description="支持 HTTP(S)、本机和内网地址；认证方式在访问设置中选择。"
              >
                <Input
                  required
                  type="url"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://example.com/mcp"
                />
              </FormField>
            ) : (
              <>
                <p className="type-caption">
                  程序以平台宿主账号权限运行，不是安全沙箱。仅登记受信且固定版本的服务；解析不启动程序，“保存并测试”会启动并读取工具。
                </p>
                <FormField label={<>程序</>}>
                  <Input
                    required
                    value={command}
                    onChange={(e) => setCommand(e.target.value)}
                    placeholder="npx / bunx / python"
                  />
                </FormField>
                <FormField label={<>程序参数（JSON 字符串数组）</>}>
                  <Textarea
                    rows={3}
                    value={args}
                    onChange={(e) => setArgs(e.target.value)}
                    placeholder={'["-y", "example-mcp@1.0.0"]'}
                  />
                </FormField>
                <FormField label={<>凭据字段名称（高级设置，每行一个）</>}>
                  <Textarea
                    rows={3}
                    value={envKeys}
                    onChange={(e) => {
                      setEnvKeys(e.target.value);
                      setInputFields([]);
                    }}
                  />
                </FormField>
              </>
            )}
            <McpSetupAccess
              transport={transport}
              fields={inputFields}
              keys={envKeys.split(/[\s,]+/).filter(Boolean)}
              scope={scope}
              onScope={setScope}
              auth={transport === "stdio" ? stdioAuth : auth}
              onAuth={transport === "stdio" ? setStdioAuth : setAuth}
              header={header}
              onHeader={setHeader}
              token={token}
              onToken={setToken}
              oauth={oauth}
              onOAuth={setOAuth}
              environment={environment}
              onEnvironment={setEnvironment}
            />
          </fieldset>
        </Card>
      )}
      <McpQuickImport
        open={importOpen}
        onOpenChange={setImportOpen}
        hasValues={
          !!(
            name ||
            url ||
            command ||
            token ||
            description ||
            envKeys ||
            args !== "[]" ||
            auth !== "none" ||
            stdioAuth !== "none" ||
            Object.values(environment).some(Boolean)
          )
        }
        onFill={fillImport}
      />
      {serviceEditing && service && (
        <Card
          as="section"
          variant="outline"
          id="mcp-service-information"
          className="form-panel space-y-6"
        >
          <h2 className="type-title">服务信息</h2>
          <FormField label={<>服务名称</>}>
            <Input value={serviceName} onChange={(e) => setServiceName(e.target.value)} />
          </FormField>
          <FormField label={<>功能说明</>}>
            <Textarea
              rows={3}
              value={serviceDescription}
              onChange={(e) => setServiceDescription(e.target.value)}
            />
          </FormField>
          {service.transport === "stdio" && (
            <FormField
              label="允许配置的凭据字段（环境变量名，每行一个）"
              description="填写该 MCP 官方说明中的环境变量名，密钥的值在下方访问设置中填写。添加字段不会强制匿名连接提供密钥；正在使用的字段不能移除。"
            >
              <Textarea
                rows={3}
                value={serviceEnvKeys}
                onChange={(event) => setServiceEnvKeys(event.target.value)}
                placeholder="例如：CONTEXT7_API_KEY"
              />
            </FormField>
          )}
          <p className="type-caption">
            服务信息只定义接入和可用字段。API Key 请在下方已有连接的“配置密钥 /
            修改访问设置”中填写。
          </p>
        </Card>
      )}
      {loaded && params.get("service") && !service && !failure && (
        <FailureState
          failure={clientFailure("mcp_service_not_found", "MCP 服务不存在或不可访问。")}
          title="MCP 服务不存在或不可访问"
          context={{ operation: "initial-read", resource: "connection" }}
          actions={[{ label: "返回能力库", kind: "return", href: "/skills" }]}
        />
      )}
      {(service || native) && (
        <>
          {service && (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="flex min-w-0 items-center gap-2 break-all text-sm text-text-muted">
                <ResourceIcon kind="mcp" />
                {service.transport === "stdio"
                  ? `stdio · ${service.command} ${(service.args ?? []).join(" ")}`
                  : service.url}
              </p>
              {ownService && (
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() =>
                    service.enabled
                      ? setDisabling(true)
                      : void perform(async () => {
                          const saved = await patchMcpService(service, { enabled: true });
                          shared.capabilitiesChanged();
                          setServices((current) =>
                            current.map((item) => (item.id === saved.id ? saved : item)),
                          );
                        })
                  }
                >
                  {service.enabled ? "停用服务" : "启用服务"}
                </Button>
              )}
            </div>
          )}
          <Card as="details" variant="outline" className="form-panel" open={!visible.length}>
            <summary className="cursor-pointer type-title">
              {visible.length ? "添加另一组凭据" : "配置访问方式"}
            </summary>
            <p className="mt-3 type-description">
              {native
                ? "为内置工具建立访问配置，保存后确认可用操作。此处不会自动给员工授予工具许可。"
                : "选择浏览器授权、填写 API Key 或使用匿名访问。同一 MCP 可以使用不同账号或密钥，不需要重复创建服务。"}
            </p>
            <form onSubmit={(e) => void addConnection(e)} className="form-grid mt-5">
              <FormField label={<>连接名称</>}>
                <Input
                  required
                  value={account}
                  onChange={(e) => setAccount(e.target.value)}
                  placeholder="例如：我的工作账号"
                />
              </FormField>
              {!native && (
                <>
                  <FormField label={<>使用范围</>}>
                    <SelectField
                      value={scope}
                      onValueChange={(nextValue) => setScope(nextValue)}
                      options={[
                        { value: "personal", label: "个人账号，仅本人使用" },
                        ...(ownService
                          ? [{ value: "shared", label: "明确共用，供装配此账号的员工使用" }]
                          : []),
                      ]}
                    />
                  </FormField>
                  {service?.transport === "stdio" ? (
                    <>
                      <FormField label={<>认证方式</>}>
                        <SelectField
                          value={service.env_keys.length ? stdioAuth : "none"}
                          onValueChange={(nextValue) => setStdioAuth(nextValue)}
                          options={[
                            { value: "none", label: "不提供密钥（匿名访问）" },
                            {
                              value: "env",
                              label: "环境变量（API Key 等）",
                              disabled: !service.env_keys.length,
                            },
                          ]}
                        />
                      </FormField>
                      {stdioAuth === "env" &&
                        service.env_keys.map((key) => (
                          <FormField key={key} label={<>{key}</>}>
                            <Input
                              type="password"
                              autoComplete="off"
                              required
                              value={environment[key] ?? ""}
                              onChange={(event) =>
                                setEnvironment((current) => ({
                                  ...current,
                                  [key]: event.target.value,
                                }))
                              }
                            />
                          </FormField>
                        ))}
                    </>
                  ) : (
                    <>
                      <FormField label={<>认证方式</>}>
                        <SelectField
                          value={auth}
                          onValueChange={(nextValue) => setAuth(nextValue)}
                          options={[
                            { value: "bearer", label: "Bearer Token" },
                            { value: "header", label: "自定义认证头" },
                            { value: "oauth", label: "OAuth（浏览器授权）" },
                            { value: "none", label: "无需认证" },
                          ]}
                        />
                      </FormField>
                      {auth === "oauth" && (
                        <OAuthConfigurationFields value={oauth} onChange={setOAuth} />
                      )}
                      {auth === "header" && (
                        <FormField label={<>认证头名称</>}>
                          <Input
                            required
                            value={header}
                            onChange={(e) => setHeader(e.target.value)}
                          />
                        </FormField>
                      )}
                      {auth !== "none" && auth !== "oauth" && (
                        <FormField label={<>Token</>}>
                          <Input
                            required
                            type="password"
                            autoComplete="off"
                            value={token}
                            onChange={(e) => setToken(e.target.value)}
                            maxLength={4096}
                          />
                        </FormField>
                      )}
                    </>
                  )}
                </>
              )}
              {native && (
                <p className="type-description">
                  内置文件与代码能力仍需员工主动装配，每轮任务环境分别管理。
                </p>
              )}
              <div className="col-span-full">
                <Button
                  type="submit"
                  disabled={
                    busy ||
                    !account.trim() ||
                    (!native && !service?.enabled) ||
                    (service?.transport === "stdio" &&
                      stdioAuth === "env" &&
                      service.env_keys.some((key) => !environment[key]?.trim()))
                  }
                >
                  保存访问设置
                </Button>
              </div>
            </form>
          </Card>
          <div className="space-y-5">
            {!!visible.length && (
              <div>
                <h2 className="type-title">访问设置</h2>
                <p className="mt-1 type-description">
                  每条连接保存一组访问身份或凭据。通常只需一条，需要切换账号时再添加。
                </p>
              </div>
            )}
            {visible.map((connection) => {
              const own = connection.created_by_user_id === userId;
              return (
                <Card
                  as="section"
                  variant="outline"
                  key={connection.id}
                  id={`tool-connection-${connection.id}`}
                  aria-label={`${connection.name}的访问设置`}
                  className="form-panel space-y-6"
                >
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <h2 className="type-title inline-flex items-center gap-2">
                      <ResourceIcon kind="connection" />
                      {connection.name}
                    </h2>
                    <span className="type-caption">
                      {connection.account_scope === "shared" ? "共用账号" : "个人账号"} ·{" "}
                      {connection.enabled ? "已启用" : "已停用"}
                    </span>
                  </div>
                  {own && (
                    <ConnectionSettings
                      connection={connection}
                      service={service}
                      onChange={updateConnection}
                      onDelete={() =>
                        setConnections((current) =>
                          current.filter((item) => item.id !== connection.id),
                        )
                      }
                      onConfigureFields={
                        ownService
                          ? () => {
                              setServiceName(service!.name);
                              setServiceDescription(service!.description);
                              setServiceEnvKeys(service!.env_keys.join("\n"));
                              setServiceEditing(true);
                            }
                          : undefined
                      }
                    />
                  )}
                  {own && connection.auth_type === "oauth" && (
                    <OAuthConnectionPanel connection={connection} onChange={updateConnection} />
                  )}
                  <ToolCatalogEditor
                    key={`${connection.id}:${connection.annotations_revision}`}
                    connection={connection}
                    onChange={updateConnection}
                    editable={own}
                  />
                </Card>
              );
            })}
          </div>
        </>
      )}
      <ConfirmActionDialog
        open={disabling}
        onOpenChange={setDisabling}
        title={`停用「${service?.name}」服务？`}
        description="确认后立即阻止该 MCP 下所有连接的后续调用，相关员工会受到影响。服务和账号配置保留，可重新启用。"
        confirmLabel="确认停用服务"
        busy={busy}
        onConfirm={() => {
          if (service)
            void perform(async () => {
              const saved = await patchMcpService(service, { enabled: false });
              shared.capabilitiesChanged();
              setServices((current) =>
                current.map((item) => (item.id === saved.id ? saved : item)),
              );
              setDisabling(false);
            });
        }}
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
    </PageContainer>
  );
}
export { ToolsPage as Component };
