import { FormField } from "@/components/common/FormField";
import { Card } from "@/components/ui/Card";
import { useState } from "react";
import { ArrowLeft, Plus, RefreshCw } from "lucide-react";
import { PageHeading } from "@/components/common/PageHeading";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { SelectField } from "@/components/ui/SelectField";
import type { ToolDescriptor } from "@/lib/api/tools";
import { catalogDifferences, toolDisplayName } from "./demoCatalog";
import {
  demoSearchCatalog,
  type DemoAlias,
  type DemoCapability,
  type DemoConnection,
} from "./fixtures/capabilities";

const statusLabels = {
  added: "新增 · 默认未授权",
  changed: "定义改变 · 旧许可将失效",
  removed: "移除 · 保留历史许可记录",
  unchanged: "未变化 · 保留原许可",
};

export function McpCatalogManager({
  capability,
  connections,
  initialConnectionId,
  onChange,
  onCreate,
  onBack,
  onAssemble,
}: {
  capability: DemoCapability;
  connections: DemoConnection[];
  initialConnectionId: string;
  onChange: (connection: DemoConnection) => void;
  onCreate: (connection: DemoConnection) => void;
  onBack: () => void;
  onAssemble: () => void;
}) {
  const initial = connections.find((item) => item.id === initialConnectionId) || connections[0];
  const [connectionId, setConnectionId] = useState(initial?.id || "");
  const [aliases, setAliases] = useState<Record<string, DemoAlias>>(() =>
    structuredClone(initial?.aliases || {}),
  );
  const [creating, setCreating] = useState(!initial);
  const [accountName, setAccountName] = useState("");
  const [credentialFilled, setCredentialFilled] = useState(false);
  const [message, setMessage] = useState("");
  const [scenario, setScenario] = useState("");
  const connection = connections.find((item) => item.id === connectionId);
  const candidate = connection?.discovery_candidate;
  const changes = connection
    ? catalogDifferences(
        connection.approved_catalog,
        candidate?.tools || connection.approved_catalog,
      )
    : [];
  const baseline: ToolDescriptor[] =
    capability.id === "demo-tavily"
      ? structuredClone(demoSearchCatalog)
      : [
          {
            name: "demo_lookup",
            description: "Look up information from the simulated service.",
            descriptor_hash: "demo-lookup-v1",
          },
        ];
  const aliasDirty = JSON.stringify(aliases) !== JSON.stringify(connection?.aliases || {});

  function choose(id: string) {
    if (id === "__new") {
      setCreating(true);
      setMessage("");
      return;
    }
    setConnectionId(id);
    setAliases(structuredClone(connections.find((item) => item.id === id)?.aliases || {}));
    setCreating(false);
    setScenario("");
    setMessage("");
  }
  function create() {
    if (!credentialFilled || !accountName.trim()) {
      setMessage("请填写连接名称，并使用演示凭据。");
      return;
    }
    const next: DemoConnection = {
      id: `demo-connection-${Date.now()}`,
      capabilityId: capability.id,
      name: accountName.trim(),
      kind: "mcp_http",
      service_id: null,
      account_scope: "personal",
      created_by_user_id: null,
      tool_annotations: {},
      annotations_revision: 1,
      provider_key: null,
      auth_type: "bearer",
      public_config: { url: capability.url || "" },
      enabled: true,
      has_credential: true,
      config_revision: 1,
      credential_revision: 1,
      catalog_revision: 1,
      approved_catalog: [],
      discovery_candidate: null,
      aliases: {},
      remoteCatalog: baseline,
    };
    onCreate(next);
    setConnectionId(next.id);
    setAliases({});
    setCreating(false);
    setMessage("账号连接已模拟保存。接下来读取目录并确认，员工才能从中选择操作。");
  }
  function discover() {
    if (!connection) return;
    onChange({
      ...connection,
      discovery_candidate: {
        hash: `demo-candidate-${Date.now()}`,
        tools: structuredClone(connection.remoteCatalog),
      },
    });
    setMessage("已取得待确认目录。下面可编辑展示名称；确认之前，员工装配仍使用原来的目录。");
  }
  function confirm() {
    if (!connection) return;
    const next = candidate?.tools;
    const differs =
      next &&
      catalogDifferences(connection.approved_catalog, next).some(
        (item) => item.status !== "unchanged",
      );
    onChange({
      ...connection,
      aliases: structuredClone(aliases),
      ...(next
        ? {
            approved_catalog: structuredClone(next),
            discovery_candidate: null,
            catalog_revision: connection.catalog_revision + (differs ? 1 : 0),
          }
        : {}),
    });
    setScenario("");
    setMessage(
      next
        ? "目录已确认。新增操作仍未授权给任何员工；未变化操作保留许可，改变或移除的操作需回员工装配处理。"
        : "展示名称与说明已保存。原始工具名、定义和员工许可均未改变。",
    );
  }
  function simulate(action: "added" | "changed" | "renamed" | "removed" | "reset") {
    if (!connection) return;
    let next = baseline;
    if (action === "added")
      next = [
        ...baseline,
        {
          name: "demo_new_tool",
          description: "An additional operation from the simulated server.",
          descriptor_hash: "demo-new-v1",
        },
      ];
    if (action === "changed")
      next = baseline.map((tool, index) =>
        index === 0
          ? {
              ...tool,
              description: tool.description + " Now requires a language argument (simulation).",
              descriptor_hash: `${tool.descriptor_hash}-changed`,
            }
          : tool,
      );
    if (action === "renamed")
      next = baseline.map((tool, index) =>
        index === 0
          ? { ...tool, name: `${tool.name}_v2`, descriptor_hash: `${tool.descriptor_hash}-renamed` }
          : tool,
      );
    if (action === "removed") next = baseline.slice(1);
    onChange({ ...connection, remoteCatalog: structuredClone(next) });
    setScenario(
      {
        added: "远端新增了一个操作",
        changed: "远端改变了第一个工具的参数定义",
        renamed: "远端修改了第一个工具的原始名称",
        removed: "远端删除了第一个工具",
        reset: "远端恢复初始状态",
      }[action],
    );
    setMessage(
      "只改变了此连接看到的模拟远端服务。已确认目录与员工许可未更新，可先返回员工页观察，再检查更新。",
    );
  }
  const updateAlias = (name: string, patch: Partial<DemoAlias>) =>
    setAliases((items) => ({
      ...items,
      [name]: {
        name: items[name]?.name || "",
        description: items[name]?.description || "",
        ...patch,
      },
    }));

  return (
    <>
      <PageHeading
        title={capability.name}
        description="能力库 / MCP 连接与工具目录。在这里维护快照和名称，员工装配只选择许可。"
        actions={
          <>
            <Button variant="outline" onClick={onBack}>
              <ArrowLeft size={14} />
              返回能力库
            </Button>
            <Button onClick={onAssemble}>前往员工装配</Button>
          </>
        }
      />
      {message && (
        <Card
          as="p"
          variant="muted"
          radius="control"
          role="status"
          className="mb-5 p-3 text-sm leading-relaxed"
        >
          {message}
        </Card>
      )}
      <div className="file-layout items-start gap-6">
        <Card
          as="section"
          variant="outline"
          radius="panel"
          aria-label="账号连接管理"
          className="form-panel space-y-6"
        >
          <h2 className="type-title">账号连接</h2>
          <p className="break-all type-caption">{capability.url}</p>
          <SelectField
            value={creating ? "__new" : connectionId}
            options={[
              ...connections.map((item) => ({ value: item.id, label: item.name })),
              { value: "__new", label: "＋ 新建账号连接" },
            ]}
            onValueChange={choose}
            aria-label="管理账号连接"
            className="w-full min-w-0"
          />
          {creating ? (
            <div className="space-y-4">
              <FormField label={<>连接名称</>}>
                <Input
                  value={accountName}
                  onChange={(event) => setAccountName(event.target.value)}
                />
              </FormField>
              <FormField label={<>Bearer 凭据</>}>
                <Input
                  readOnly
                  value={credentialFilled ? "演示凭据已填写" : "本 Demo 不接收真实密钥"}
                />
              </FormField>
              <Button
                variant="outline"
                disabled={credentialFilled}
                onClick={() => setCredentialFilled(true)}
              >
                填入演示凭据
              </Button>
              <Button className="w-full" onClick={create}>
                保存演示连接
              </Button>
            </div>
          ) : (
            connection && (
              <>
                <Badge variant="secondary">
                  {connection.approved_catalog.length
                    ? `已确认目录 · 修订 ${connection.catalog_revision}`
                    : "尚未确认目录"}
                </Badge>
                <p className="type-caption">
                  同一服务的不同账号分别保存目录。切换连接不会继承其他账号的许可。
                </p>
                <Button variant="outline" className="w-full" onClick={discover}>
                  <RefreshCw size={14} />
                  {connection.approved_catalog.length ? "检查目录更新" : "读取工具目录"}
                </Button>
                {candidate && (
                  <Button
                    variant="ghost"
                    onClick={() => {
                      onChange({ ...connection, discovery_candidate: null });
                      setAliases(structuredClone(connection.aliases));
                      setMessage("已丢弃待确认目录，继续使用原快照。");
                    }}
                  >
                    丢弃本次检查
                  </Button>
                )}
              </>
            )
          )}
        </Card>
        <section aria-label="工具目录管理" className="min-w-0 space-y-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="type-title">{candidate ? "待确认的工具目录" : "当前已确认目录"}</h2>
              <p className="mt-2 type-caption">
                只编辑展示名称和补充说明。原始名称与原始定义保留，展示修改不影响权限。
              </p>
            </div>
            {connection && !creating && (
              <Button disabled={!candidate && !aliasDirty} onClick={confirm}>
                {candidate ? "确认目录更新" : "保存展示名称"}
              </Button>
            )}
          </div>
          {connection && !creating ? (
            <>
              {!changes.length && (
                <Card as="p" variant="outline" radius="panel" className="p-6 type-description">
                  还没有已确认目录。先读取工具目录，整理名称后确认保存。
                </Card>
              )}
              <div className="space-y-3">
                {changes.map(({ tool, status }) => (
                  <Card
                    as="article"
                    radius="panel"
                    key={tool.name}
                    aria-label={`目录工具 ${tool.name}`}
                    className="space-y-3 p-4"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <h3 className="min-w-0 break-all type-body font-medium">
                        {toolDisplayName({ ...connection, aliases }, tool.name)}
                      </h3>
                      {candidate && (
                        <Badge
                          variant={
                            status === "removed" || status === "changed"
                              ? "destructive"
                              : "secondary"
                          }
                        >
                          {statusLabels[status]}
                        </Badge>
                      )}
                    </div>
                    <p className="break-words type-caption">
                      原始说明：{tool.description || "服务未提供说明"}
                    </p>
                    {status !== "removed" && (
                      <div className="form-grid">
                        <label className="grid min-w-0 gap-2 text-xs">
                          展示名称（可选）
                          <Input
                            aria-label={`展示名称 ${tool.name}`}
                            value={aliases[tool.name]?.name || ""}
                            maxLength={60}
                            placeholder="未填写时显示原始名称"
                            onChange={(event) =>
                              updateAlias(tool.name, { name: event.target.value })
                            }
                          />
                        </label>
                        <label className="grid min-w-0 gap-2 text-xs">
                          补充说明（可选）
                          <Textarea
                            aria-label={`补充说明 ${tool.name}`}
                            rows={2}
                            maxLength={300}
                            value={aliases[tool.name]?.description || ""}
                            onChange={(event) =>
                              updateAlias(tool.name, { description: event.target.value })
                            }
                          />
                        </label>
                      </div>
                    )}
                    {status === "removed" && (
                      <p className="text-xs text-danger">
                        确认更新后，此工具不再可选；历史装配记录仍保留并标为失效。
                      </p>
                    )}
                  </Card>
                ))}
              </div>
              <Card as="details" variant="muted" radius="panel" className="p-4">
                <summary className="text-sm font-medium">模拟远端变化（仅演示）</summary>
                <div className="mt-4 space-y-3">
                  <p className="type-caption">
                    只改变此账号连接看到的远端目录，不会自动更新本地快照或员工开关。每个场景都从初始远端目录开始。
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {[
                      ["added", "模拟新增工具"],
                      ["changed", "模拟定义变化"],
                      ["renamed", "模拟工具改名"],
                      ["removed", "模拟删除工具"],
                      ["reset", "恢复远端初始状态"],
                    ].map(([value, label]) => (
                      <Button
                        key={value}
                        variant="outline"
                        size="sm"
                        onClick={() =>
                          simulate(value as "added" | "changed" | "renamed" | "removed" | "reset")
                        }
                      >
                        {value === "added" && <Plus size={13} />}
                        {label}
                      </Button>
                    ))}
                  </div>
                  {scenario && (
                    <p role="status" className="type-body">
                      {scenario}；请点击“检查目录更新”查看差异。
                    </p>
                  )}
                </div>
              </Card>
            </>
          ) : (
            <p className="p-6 type-description">先创建账号连接，再准备这个账号可用的目录。</p>
          )}
        </section>
      </div>
    </>
  );
}
