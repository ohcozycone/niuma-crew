import { FormField } from "@/components/common/FormField";
import { SelectField } from "@/components/ui/SelectField";
import { CardFooter } from "@/components/ui/Card";
import { SearchInput } from "@/components/common/SearchInput";
import { Card } from "@/components/ui/Card";
import { PageContainer } from "@/components/common/PageContainer";
import { useRef, useState, type ReactNode } from "react";
import { Check, FlaskConical, FolderOpen, Plus, Save, Users } from "lucide-react";
import { BrandLogo } from "@/components/brand/BrandLogo";
import { ResourceIcon, resourceIdentity } from "@/components/common/ResourceIcon";
import { PageBreadcrumb } from "@/components/common/PageBreadcrumb";
import { PageHeading } from "@/components/common/PageHeading";
import { ThemeSwitcher } from "@/components/theme/ThemeSwitcher";
import { AvatarBadge } from "@/components/avatars";
import { SkillCard } from "@/components/skills/SkillCard";
import cardStyles from "@/components/skills/skillCardStyles";
import collectionStyles from "@/components/skills/skillCollectionStyles";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { Switch } from "@/components/ui/Switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";
import { PageTabs } from "@/components/common/PageTabs";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/Dialog";
import { AgentCard, toAgentPresentation } from "@/pages/agents";
import type { Skill } from "@/lib/models/skill";
import { cn } from "@/lib/utils";
import {
  assignmentFor,
  createDemoConnections,
  createDemoEmployees,
  demoSkills,
  initialCapabilities,
  type DemoAssignment,
  type DemoConnection,
} from "./fixtures/capabilities";
import { McpCatalogManager } from "./McpCatalogManager";
import { DemoInvocationDialog } from "./DemoInvocationDialog";
import { toolDisplayName, validGrantedTools } from "./demoCatalog";

const kindNames = { skill: "Skill", mcp: "远程 MCP", native: "内置工具" };

const sampleSkill =
  "---\nname: document-summary\ndescription: 整理资料要点并保留出处\n---\n\n# 资料整理\n\n阅读用户提供的资料，整理核心结论，注明来源与待确认事项。";
const sampleMcp = JSON.stringify(
  {
    mcpServers: {
      search: {
        url: "https://mcp.example.com/mcp",
        headers: { Authorization: "Bearer ${API_TOKEN}" },
      },
    },
  },
  null,
  2,
);

function Field({ label, children, help }: { label: string; children: ReactNode; help?: string }) {
  return (
    <FormField label={label} description={help}>
      {children}
    </FormField>
  );
}

function FeatureNote({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-control bg-warning-bg p-3 text-xs leading-relaxed text-warning">
      {children}
    </p>
  );
}

/** Development-only preview: all mutations stay in this component's memory. */
export function CapabilityDemoPage() {
  const [employees, setEmployees] = useState(createDemoEmployees);
  const [employeeId, setEmployeeId] = useState("knowledge");
  const [draft, setDraft] = useState(() => createDemoEmployees()[0]);
  const [connections, setConnections] = useState(createDemoConnections);
  const [capabilities, setCapabilities] = useState(initialCapabilities);
  const [skills, setSkills] = useState(demoSkills);
  const [view, setView] = useState("employee");
  const [tab, setTab] = useState("capabilities");
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState("all");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [dialog, setDialog] = useState<"config" | "picker" | "new" | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [managedId, setManagedId] = useState("demo-tavily");
  const [resumeConfiguration, setResumeConfiguration] = useState(false);
  const [testOpen, setTestOpen] = useState(false);
  const [assignment, setAssignment] = useState<DemoAssignment | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState<{ view?: string; employeeId?: string } | null>(null);
  const [newKind, setNewKind] = useState("skill");
  const [newName, setNewName] = useState("");
  const [source, setSource] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const saved = employees.find((employee) => employee.agent.id === employeeId)!;
  const dirty = JSON.stringify(draft) !== JSON.stringify(saved);
  const current = capabilities.find((capability) => capability.id === editingId);
  const chosenConnection = connections.find(
    (connection) => connection.id === assignment?.connectionId,
  );
  const currentSkill = skills.find((skill) => skill.id === current?.skillId);
  const updateAssignment = (patch: Partial<DemoAssignment>) =>
    setAssignment((value) => (value ? { ...value, ...patch } : value));

  function notice(text: string) {
    setMessage(text);
  }
  function saveEmployee() {
    if (!draft.agent.name.trim()) {
      setTab("identity");
      notice("请先填写员工名称。");
      return false;
    }
    const selectedSkills = draft.assignments.filter(
      (item) =>
        capabilities.find((capability) => capability.id === item.capabilityId)?.kind === "skill",
    );
    const updated = {
      ...draft,
      agent: {
        ...draft.agent,
        skills: selectedSkills.map((item) => item.capabilityId),
        skillAssignments: selectedSkills.map((item) => ({
          skillId: item.capabilityId,
          enabled: item.enabled,
          parameters: JSON.parse(item.parameters) as Record<string, unknown>,
        })),
      },
    };
    setDraft(updated);
    setEmployees((items) =>
      items.map((item) => (item.agent.id === employeeId ? structuredClone(updated) : item)),
    );
    notice(`已模拟保存${draft.agent.name}的配置；正式员工、连接和数据库均未修改。`);
    return true;
  }
  function changeLocation(next: { view?: string; employeeId?: string }) {
    if (dirty) {
      setPending(next);
      return;
    }
    move(next);
  }
  function move(next: { view?: string; employeeId?: string }) {
    if (next.view) setView(next.view);
    if (next.employeeId) {
      setEmployeeId(next.employeeId);
      setDraft(
        structuredClone(employees.find((employee) => employee.agent.id === next.employeeId)!),
      );
    }
    setPending(null);
    setMessage("");
  }
  function openConfiguration(id: string) {
    setEditingId(id);
    setAssignment(
      structuredClone(
        draft.assignments.find((item) => item.capabilityId === id) ?? assignmentFor(id),
      ),
    );
    setError("");
    setDialog("config");
  }
  function applyConfiguration() {
    if (!assignment || !current) return;
    try {
      const parameters: unknown = JSON.parse(assignment.parameters);
      if (!parameters || typeof parameters !== "object" || Array.isArray(parameters))
        throw Error("装配参数必须是 JSON 对象。");
      if (
        current.kind === "skill" &&
        !Object.keys(currentSkill?.configurationSchema || {}).length &&
        Object.keys(parameters).length
      )
        throw Error("此技能没有定义参数规范，当前契约只接受空对象 {}。补充说明请填在独立区域。");
      if (
        current.kind === "mcp" &&
        assignment.enabled &&
        assignment.tools.some(
          (name) =>
            !chosenConnection?.approved_catalog.some(
              (tool) => tool.name === name && assignment.toolHashes[name] === tool.descriptor_hash,
            ),
        )
      )
        throw Error("有旧许可已失效，请移除旧许可或按新定义重新开启操作。");
      setDraft((value) => ({
        agent: value.agent,
        assignments: [
          ...value.assignments.filter((item) => item.capabilityId !== current.id),
          structuredClone(assignment),
        ],
      }));
      setDialog(null);
      setView("employee");
      setTab("capabilities");
      notice("配置已应用到员工草稿，点击“保存配置”后在本次演示中生效。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "配置无效。");
    }
  }
  function openCatalog(id: string, resume = false) {
    setManagedId(id);
    setResumeConfiguration(resume);
    setDialog(null);
    changeLocation({ view: "catalog" });
  }
  function updateConnection(connection: DemoConnection) {
    setConnections((items) => items.map((item) => (item.id === connection.id ? connection : item)));
  }
  function createCapability() {
    setError("");
    if (!newName.trim()) {
      setError("请填写能力名称。");
      return;
    }
    const id = `demo-import-${Date.now()}`;
    try {
      if (newKind === "skill") {
        if (
          !/^---\s*\r?\n[\s\S]*?\r?\n---/.test(source) ||
          !/\nname\s*:/.test(source) ||
          !/\ndescription\s*:/.test(source)
        )
          throw Error("需要带 name 和 description 的 SKILL.md 文件头。");
        const skill: Skill = {
          id,
          name: newName.trim(),
          description: "本次演示导入的技能内容。导入不执行代码，也不自动授权。",
          category: "其他",
          instructions: source,
          input: "用户提供的任务上下文",
          output: "遵循技能说明的答复",
          example: "按这项技能处理资料。",
          configurationSchema: {},
          configurationLoaded: true,
          active: true,
        };
        setSkills((items) => [...items, skill]);
        setCapabilities((items) => [
          ...items,
          {
            id,
            kind: "skill",
            name: skill.name,
            description: skill.description,
            skillId: id,
            tools: [],
          },
        ]);
      } else {
        const parsed: unknown = JSON.parse(source);
        if (!parsed || typeof parsed !== "object" || !("mcpServers" in parsed))
          throw Error("需要包含 mcpServers 的配置对象。");
        const servers = parsed.mcpServers;
        if (!servers || typeof servers !== "object" || Array.isArray(servers))
          throw Error("mcpServers 必须是对象。");
        const entries = Object.values(servers) as Record<string, unknown>[];
        if (
          entries.length !== 1 ||
          !entries[0] ||
          entries[0].command ||
          typeof entries[0].url !== "string"
        )
          throw Error("本演示每次导入一个远程 HTTP 服务；当前正式平台未开放 stdio。");
        const url = new URL(entries[0].url);
        if (
          !["http:", "https:"].includes(url.protocol) ||
          url.username ||
          url.password ||
          url.search ||
          url.hash
        )
          throw Error("请输入不含凭据或查询参数的 HTTP(S) 服务地址。");
        if (
          entries[0].headers &&
          Object.values(entries[0].headers).some(
            (value) => typeof value !== "string" || !/\$\{[A-Z0-9_]+\}/.test(value),
          )
        )
          throw Error("此演示只接收凭据占位符，请勿粘贴真实密钥。");
        setCapabilities((items) => [
          ...items,
          {
            id,
            kind: "mcp",
            name: newName.trim(),
            description: "待配置账号、发现并批准工具目录的远程 MCP。",
            url: url.toString(),
            tools: [],
          },
        ]);
      }
      setDialog(null);
      setView("library");
      setKind("all");
      setQuery("");
      notice(
        "能力已加入演示库，尚未装配给任何员工。标准包与配置导入是拟议增量，此处仅做本地内容预览。",
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法解析配置。");
    }
  }
  const filtered = capabilities.filter(
    (item) =>
      (kind === "all" || item.kind === kind) &&
      `${item.name} ${item.description}`.includes(query.trim()),
  );
  const usableToolCount = (item: DemoAssignment) =>
    capabilities.find((capability) => capability.id === item.capabilityId)?.kind === "mcp"
      ? validGrantedTools(
          item,
          connections.find((connection) => connection.id === item.connectionId),
        ).length
      : item.tools.length;
  const preview = {
    ...draft.agent,
    skills: draft.assignments
      .filter(
        (item) =>
          capabilities.find((capability) => capability.id === item.capabilityId)?.kind === "skill",
      )
      .map((item) => item.capabilityId),
    skillAssignments: draft.assignments
      .filter(
        (item) =>
          capabilities.find((capability) => capability.id === item.capabilityId)?.kind === "skill",
      )
      .map((item) => ({ skillId: item.capabilityId, enabled: item.enabled, parameters: {} })),
    toolCount: draft.assignments.reduce(
      (total, item) => total + (item.enabled ? usableToolCount(item) : 0),
      0,
    ),
  };
  function readiness(item: DemoAssignment) {
    const capability = capabilities.find((value) => value.id === item.capabilityId)!;
    if (!item.enabled) return "已停用";
    if (capability.kind === "mcp")
      return !item.connectionId
        ? "待配置连接"
        : !connections.find((connection) => connection.id === item.connectionId)?.approved_catalog
              .length
          ? "待在能力库确认目录"
          : !item.tools.length
            ? "待授予操作许可"
            : item.tools.length !== usableToolCount(item)
              ? `${usableToolCount(item)} 项可用 · ${item.tools.length - usableToolCount(item)} 项旧许可失效`
              : `${usableToolCount(item)} 项操作已授权`;
    if (capability.kind === "native")
      return item.tools.length ? `${item.tools.length} 项操作已授权（模拟）` : "待选择操作";
    return item.supplement ? "含员工补充说明（拟新增）" : "已装配";
  }

  return (
    <div className="min-h-screen bg-canvas text-text">
      <aside
        className="fixed inset-y-0 left-0 flex w-(--os-navigation-width) flex-col border-r border-border bg-canvas px-4 py-5 max-[767px]:hidden"
        aria-label="演示导航"
      >
        <div className="mb-5 [--brand-logo-scale:0.85]">
          <BrandLogo subtitle />
        </div>
        <nav aria-label="平台导航" className="space-y-1">
          {[
            { id: "employee", label: "数字员工", icon: Users },
            { id: "library", label: "能力库", icon: resourceIdentity.capabilities.icon },
            { id: "brains", label: "大脑配置", icon: resourceIdentity.brain.icon },
            { id: "history", label: "对话记录", icon: resourceIdentity.conversation.icon },
            { id: "knowledge", label: "知识库", icon: resourceIdentity.knowledge.icon },
          ].map((item) => (
            <button
              key={item.id}
              type="button"
              disabled={!["employee", "library"].includes(item.id)}
              aria-current={
                (view === "catalog" ? "library" : view) === item.id ? "page" : undefined
              }
              onClick={() => changeLocation({ view: item.id })}
              className={cn(
                "flex min-h-10.5 w-full items-center gap-[11px] rounded-control px-3 py-2.5 text-left text-caption disabled:opacity-40",
                (view === "catalog" ? "library" : view) === item.id
                  ? "bg-nav-active font-semibold text-nav-active-text"
                  : "hover:bg-muted",
              )}
            >
              <item.icon size={17} aria-hidden="true" />
              {item.label}
            </button>
          ))}
        </nav>
        <div className="mt-7 px-3">
          <p className="type-label">演示员工</p>
          {employees.map((employee) => (
            <button
              key={employee.agent.id}
              type="button"
              onClick={() => changeLocation({ employeeId: employee.agent.id, view: "employee" })}
              className="mt-3 flex w-full items-center gap-2 rounded-control py-1 text-sm"
            >
              <AvatarBadge avatarId={employee.agent.avatarId} size="small" />
              <span>{employee.agent.name}</span>
              {employeeId === employee.agent.id && <Check size={13} className="ml-auto" />}
            </button>
          ))}
        </div>
        <p className="mt-auto px-3 pt-8 text-xs leading-relaxed text-text-muted">
          <FlaskConical size={15} className="mb-2" />
          页面组合预览
          <br />
          复用现有组件，模拟保存
        </p>
      </aside>
      <div className="workspace-region ml-(--os-navigation-width) max-[767px]:ml-0">
        <header className="flex min-h-12 min-w-0 flex-wrap items-center justify-between gap-2 border-b border-border page-gutters py-2">
          <PageBreadcrumb
            current={
              view === "employee"
                ? "编辑员工"
                : view === "catalog"
                  ? "能力库 / MCP 连接与目录"
                  : "能力库（整合预览）"
            }
          />
          <div className="flex items-center gap-3">
            <Badge variant="outline">开发 Demo · 模拟数据</Badge>
            <ThemeSwitcher />
          </div>
          <div className="hidden w-full flex-wrap gap-2 max-[767px]:flex">
            <Button
              size="sm"
              variant={view === "employee" ? "secondary" : "ghost"}
              onClick={() => changeLocation({ view: "employee" })}
            >
              数字员工
            </Button>
            <Button
              size="sm"
              variant={view !== "employee" ? "secondary" : "ghost"}
              onClick={() => changeLocation({ view: "library" })}
            >
              能力库
            </Button>
          </div>
        </header>
        <PageContainer as="main">
          <Card
            as="div"
            variant="muted"
            radius="control"
            className="mb-5 flex flex-wrap items-center justify-between gap-3 px-4 py-3 text-xs text-text-muted"
          >
            <span>先在能力库确认工具目录，再给员工开启操作；模拟远端变化不会自动扩大许可。</span>
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              <span>切换演示员工</span>
              <div className="min-w-36">
                <SelectField
                  aria-label="切换演示员工"
                  value={employeeId}
                  options={employees.map((employee) => ({
                    value: employee.agent.id,
                    label: employee.agent.name,
                  }))}
                  onValueChange={(value) => changeLocation({ employeeId: value })}
                />
              </div>
            </div>
          </Card>
          {message && (
            <p
              role="status"
              className="mb-4 rounded-control bg-success-bg p-3 text-sm text-success"
            >
              {message}
            </p>
          )}
          {view === "employee" ? (
            <>
              <PageHeading
                title="编辑员工"
                description="定义员工身份、工作方式与技能。"
                actions={
                  <>
                    <span className="type-caption">{dirty ? "有未保存的修改" : "已模拟保存"}</span>
                    <Button variant="outline" disabled={dirty} onClick={() => setTestOpen(true)}>
                      模拟调用
                    </Button>
                    <Button
                      variant="outline"
                      onClick={() => {
                        setDraft(structuredClone(saved));
                        notice("已还原为本次演示中上次保存的配置。");
                      }}
                    >
                      取消
                    </Button>
                    <Button onClick={saveEmployee} disabled={!dirty}>
                      <Save size={15} />
                      保存配置
                    </Button>
                  </>
                }
              />
              <div className="configuration-layout">
                <Card
                  as="section"
                  variant="outline"
                  radius="panel"
                  className={cn("min-w-0 overflow-hidden")}
                >
                  <PageTabs
                    value={tab}
                    onValueChange={setTab}
                    placement="panel"
                    label="员工配置"
                    items={[
                      { value: "identity", label: "基本信息" },
                      { value: "instructions", label: "工作指令" },
                      {
                        value: "capabilities",
                        label: "能力装配（可选）",
                        count: draft.assignments.length,
                      },
                    ]}
                  >
                    <TabsContent value="identity" className="form-panel space-y-6">
                      <h2 className="type-title">先认识一下</h2>
                      <div className="flex items-center gap-4">
                        <AvatarBadge avatarId={draft.agent.avatarId} size="large" />
                        <div>
                          <p className="type-body">{draft.agent.name}</p>
                          <p className="type-caption">沿用当前设计样板的员工与正式头像。</p>
                        </div>
                      </div>
                      <Field label="员工名称">
                        <Input
                          value={draft.agent.name}
                          maxLength={24}
                          onChange={(event) =>
                            setDraft((value) => ({
                              ...value,
                              agent: { ...value.agent, name: event.target.value },
                            }))
                          }
                        />
                      </Field>
                      <Field label="岗位说明">
                        <Textarea
                          value={draft.agent.description}
                          onChange={(event) =>
                            setDraft((value) => ({
                              ...value,
                              agent: { ...value.agent, description: event.target.value },
                            }))
                          }
                        />
                      </Field>
                    </TabsContent>
                    <TabsContent value="instructions" className="form-panel space-y-6">
                      <h2 className="type-title">明确工作方式</h2>
                      <Field label="工作指令">
                        <Textarea
                          rows={10}
                          value={draft.agent.systemPrompt}
                          onChange={(event) =>
                            setDraft((value) => ({
                              ...value,
                              agent: { ...value.agent, systemPrompt: event.target.value },
                            }))
                          }
                        />
                      </Field>
                      <Field label="模型连接">
                        <Input value="沿用示例模型配置，本 Demo 不调用模型" readOnly />
                      </Field>
                    </TabsContent>
                    <TabsContent value="capabilities" className="form-panel space-y-6">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <h2 className="type-title">为工作配齐能力</h2>
                          <p className="mt-2 type-caption">
                            选好能力，在同一个入口配置员工自己的使用方式。
                          </p>
                        </div>
                        <Button variant="outline" onClick={() => setDialog("picker")}>
                          <Plus size={15} />
                          添加能力
                        </Button>
                      </div>
                      <div className="divide-y divide-border">
                        {draft.assignments.map((item) => {
                          const capability = capabilities.find(
                            (value) => value.id === item.capabilityId,
                          )!;
                          return (
                            <article
                              key={item.capabilityId}
                              aria-label={`${capability.name}装配`}
                              className="flex flex-wrap items-start justify-between gap-3 py-5 first:pt-0"
                            >
                              <div className="min-w-0 flex-1">
                                <div className="flex flex-wrap items-center gap-2">
                                  <h3 className="type-body font-medium">{capability.name}</h3>
                                  <Badge variant="secondary">{kindNames[capability.kind]}</Badge>
                                </div>
                                <p className="mt-2 type-caption">{readiness(item)}</p>
                                {item.connectionId && (
                                  <p className="mt-1 type-caption">
                                    账号：
                                    {
                                      connections.find(
                                        (connection) => connection.id === item.connectionId,
                                      )?.name
                                    }
                                  </p>
                                )}
                              </div>
                              <Button
                                variant="outline"
                                size="sm"
                                aria-label={`配置${capability.name}`}
                                onClick={() => openConfiguration(capability.id)}
                              >
                                配置
                              </Button>
                            </article>
                          );
                        })}
                      </div>
                      <p className="type-caption">
                        技能说明不授予工具权限。未批准的 MCP 操作不会因为装配 Skill 而开放。
                      </p>
                    </TabsContent>
                  </PageTabs>
                </Card>
                <aside aria-label="员工配置预览" className="space-y-3">
                  <p className="flex justify-between type-caption">
                    <span>员工预览</span>
                    <span>随配置更新</span>
                  </p>
                  <AgentCard agent={toAgentPresentation(preview)} />
                  <p className="px-1 type-caption">
                    复用当前员工卡片。能力数量随演示草稿变化，保存不会发起真实任务。
                  </p>
                </aside>
              </div>
            </>
          ) : view === "catalog" ? (
            <McpCatalogManager
              key={managedId}
              capability={capabilities.find((item) => item.id === managedId)!}
              connections={connections.filter((item) => item.capabilityId === managedId)}
              initialConnectionId={
                draft.assignments.find((item) => item.capabilityId === managedId)?.connectionId ||
                ""
              }
              onChange={updateConnection}
              onCreate={(connection) => setConnections((items) => [...items, connection])}
              onBack={() => changeLocation({ view: "library" })}
              onAssemble={() => {
                setView("employee");
                setTab("capabilities");
                if (resumeConfiguration && assignment?.capabilityId === managedId)
                  setDialog("config");
                else openConfiguration(managedId);
              }}
            />
          ) : (
            <>
              <PageHeading
                title="能力库"
                description="整合当前技能库与工具连接；保留能力类型，装配时再配置员工许可。"
                actions={
                  <Button
                    onClick={() => {
                      setNewKind("skill");
                      setNewName("");
                      setSource("");
                      setError("");
                      setDialog("new");
                    }}
                  >
                    <Plus size={15} />
                    新增能力
                  </Button>
                }
              />
              <div className={collectionStyles.toolbar}>
                <SearchInput
                  label="搜索能力"
                  onChange={(nextValue) => setQuery(nextValue)}
                  placeholder="搜索能力名称或用途…"
                  value={query}
                  className="flex-[1_1_200px] max-w-90 w-full"
                />
                <div className="min-w-36">
                  <SelectField
                    aria-label="能力类型"
                    value={kind}
                    onValueChange={setKind}
                    options={[
                      { value: "all", label: "全部类型" },
                      ...Object.entries(kindNames).map(([value, label]) => ({ value, label })),
                    ]}
                  />
                </div>
                <span className="ml-auto type-caption">
                  显示 {filtered.length} / {capabilities.length} 项
                </span>
              </div>
              <div className={collectionStyles.grid}>
                {filtered.map((capability) => {
                  const skill = skills.find((value) => value.id === capability.skillId);
                  const assigned = draft.assignments.some(
                    (item) => item.capabilityId === capability.id,
                  );
                  return (
                    <section key={capability.id} className="min-w-0">
                      <div className="mb-2 flex items-center justify-between px-1">
                        <Badge variant="outline">{kindNames[capability.kind]}</Badge>
                      </div>
                      {skill ? (
                        <SkillCard
                          skill={skill}
                          expanded={expanded === skill.id}
                          onExpand={() => setExpanded(expanded === skill.id ? null : skill.id)}
                          usageCount={
                            employees.filter((employee) =>
                              employee.assignments.some((item) => item.capabilityId === skill.id),
                            ).length
                          }
                        />
                      ) : (
                        <Card as="article" className={cardStyles.card}>
                          <div className={cardStyles.top}>
                            <span className={cardStyles.icon}>
                              <ResourceIcon
                                kind={capability.kind === "native" ? "native-tool" : "mcp"}
                                size={18}
                              />
                            </span>
                            <Badge variant="secondary">
                              {capability.kind === "native" ? "内置工具" : "MCP"}
                            </Badge>
                          </div>
                          <h3 className={cardStyles.title}>{capability.name}</h3>
                          <p className={cardStyles.description}>{capability.description}</p>
                          <CardFooter className={cardStyles.footer}>
                            <span className="type-caption">
                              {capability.kind === "mcp"
                                ? `${connections.filter((connection) => connection.capabilityId === capability.id).length} 个账号连接`
                                : "运行环境状态为模拟"}
                            </span>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() =>
                                capability.kind === "mcp"
                                  ? openCatalog(capability.id)
                                  : setExpanded(expanded === capability.id ? null : capability.id)
                              }
                            >
                              {capability.kind === "mcp" ? "管理连接与目录" : "查看详情"}
                            </Button>
                          </CardFooter>
                          {expanded === capability.id && (
                            <p className="mt-4 break-all type-caption">
                              {capability.url || "文件区域与命令执行沿用当前工作区许可。"}
                            </p>
                          )}
                        </Card>
                      )}
                      <Button
                        variant="outline"
                        className="mt-2 w-full"
                        onClick={() => openConfiguration(capability.id)}
                      >
                        {assigned ? `配置${draft.agent.name}的装配` : `装配给${draft.agent.name}`}
                      </Button>
                    </section>
                  );
                })}
              </div>
              {!filtered.length && (
                <p className="p-8 text-center type-description">没有找到相关能力。</p>
              )}
            </>
          )}
        </PageContainer>
      </div>

      <Dialog
        open={dialog === "picker"}
        onOpenChange={(open) => {
          if (!open) setDialog(null);
        }}
      >
        <DialogContent size="wide">
          <DialogHeader>
            <DialogTitle>添加能力</DialogTitle>
            <DialogDescription>
              为{draft.agent.name}选择能力，账号与权限分别配置。
            </DialogDescription>
          </DialogHeader>
          <div className="divide-y divide-border">
            {capabilities.map((capability) => {
              const exists = draft.assignments.some((item) => item.capabilityId === capability.id);
              return (
                <div
                  key={capability.id}
                  className="flex flex-wrap items-center justify-between gap-3 py-4"
                >
                  <div>
                    <p className="type-body">{capability.name}</p>
                    <Badge variant="secondary">{kindNames[capability.kind]}</Badge>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => openConfiguration(capability.id)}
                  >
                    {exists ? "配置" : "添加并配置"}
                  </Button>
                </div>
              );
            })}
          </div>
        </DialogContent>
      </Dialog>

      <Dialog
        open={dialog === "config"}
        onOpenChange={(open) => {
          if (!open) setDialog(null);
        }}
      >
        <DialogContent size="wide">
          <DialogHeader>
            <DialogTitle>{current?.name}</DialogTitle>
            <DialogDescription>
              配置{draft.agent.name}的装配。共享能力正文不在这里修改。
            </DialogDescription>
          </DialogHeader>
          {current && assignment && (
            <div className="space-y-6">
              <div className="flex items-center justify-between gap-3">
                <Badge variant="secondary">{kindNames[current.kind]}</Badge>
                <label className="flex items-center gap-2 text-sm">
                  <Switch
                    checked={assignment.enabled}
                    onCheckedChange={(enabled) => updateAssignment({ enabled })}
                  />
                  启用这项能力
                </label>
              </div>
              {current.kind === "skill" ? (
                <>
                  <Card as="details" variant="muted" radius="control" className="p-3 text-sm">
                    <summary className="cursor-pointer">查看共享技能内容</summary>
                    <p className="mt-3 whitespace-pre-wrap break-words type-caption">
                      {currentSkill?.instructions}
                    </p>
                  </Card>
                  <Field
                    label="员工补充说明（可选）"
                    help="拟新增的平台装配信息，独立于标准 Skill 内容和当前 JSON 参数。"
                  >
                    <Textarea
                      rows={3}
                      maxLength={1000}
                      placeholder="这位员工使用此技能时，需要遵循哪些额外要求？"
                      value={assignment.supplement}
                      onChange={(event) => updateAssignment({ supplement: event.target.value })}
                    />
                  </Field>
                  <FeatureNote>
                    拟新增：补充说明在此演示中独立保存。正式后端目前没有这项通用字段，也尚未接入运行上下文。
                  </FeatureNote>
                  <Card as="details" variant="outline" radius="control" className="p-3">
                    <summary className="text-sm">现有高级配置：技能装配参数</summary>
                    <div className="mt-3 space-y-3">
                      <Field
                        label="装配参数（JSON 对象，不含密钥）"
                        help="沿用当前员工设置页。此示例的参数规范为空，因此只接受 {}。"
                      >
                        <Textarea
                          rows={3}
                          value={assignment.parameters}
                          onChange={(event) => updateAssignment({ parameters: event.target.value })}
                        />
                      </Field>
                      <p className="type-caption">
                        没有参数定义时，不从技能正文自动生成额外输入框。
                      </p>
                    </div>
                  </Card>
                </>
              ) : current.kind === "mcp" ? (
                <>
                  <Field label="MCP 地址">
                    <Input value={current.url || ""} readOnly />
                  </Field>
                  <Field label="账号连接">
                    <SelectField
                      aria-label="账号连接"
                      value={assignment.connectionId}
                      onValueChange={(connectionId) => {
                        updateAssignment({ connectionId, tools: [], toolHashes: {} });
                      }}
                      options={[
                        { value: "", label: "请选择已准备的账号连接" },
                        ...connections
                          .filter((connection) => connection.capabilityId === current.id)
                          .map((connection) => ({
                            value: connection.id,
                            label:
                              connection.name +
                              (connection.approved_catalog.length ? "" : " · 目录待准备"),
                          })),
                      ]}
                    />
                  </Field>
                  <Card
                    as="div"
                    variant="muted"
                    radius="control"
                    className="flex flex-wrap items-center justify-between gap-3 p-3"
                  >
                    <p className="type-caption">
                      {chosenConnection?.approved_catalog.length
                        ? `使用已确认目录 · 修订 ${chosenConnection.catalog_revision}`
                        : "先在能力库准备账号和目录。"}
                      {chosenConnection?.discovery_candidate
                        ? " 有待确认更新，当前列表保持原快照。"
                        : ""}
                    </p>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => openCatalog(current.id, true)}
                    >
                      管理连接与目录
                    </Button>
                  </Card>
                  <section className="space-y-3">
                    <h3 className="type-body font-medium">员工可用操作</h3>
                    {chosenConnection?.approved_catalog.length ? (
                      chosenConnection.approved_catalog.map((tool) => (
                        <label key={tool.name} className="flex items-start gap-3 text-sm">
                          <Switch
                            checked={
                              assignment.tools.includes(tool.name) &&
                              assignment.toolHashes[tool.name] === tool.descriptor_hash
                            }
                            onCheckedChange={(checked) =>
                              updateAssignment({
                                tools: checked
                                  ? [...new Set([...assignment.tools, tool.name])]
                                  : assignment.tools.filter((name) => name !== tool.name),
                                toolHashes: {
                                  ...assignment.toolHashes,
                                  [tool.name]: checked ? tool.descriptor_hash : "",
                                },
                              })
                            }
                          />
                          <span className="min-w-0">
                            <span className="block break-all">
                              {toolDisplayName(chosenConnection, tool.name)}
                            </span>
                            <span className="mt-1 block type-caption">
                              {chosenConnection.aliases[tool.name]?.description || tool.description}
                            </span>
                            {assignment.tools.includes(tool.name) &&
                              assignment.toolHashes[tool.name] !== tool.descriptor_hash && (
                                <span className="block text-xs text-warning">
                                  原许可已失效；重新开启表示按新定义授权。
                                </span>
                              )}
                          </span>
                        </label>
                      ))
                    ) : (
                      <p className="type-caption">
                        本页不读取远端目录。完成连接管理并确认目录后，再回来选择操作。
                      </p>
                    )}
                    {assignment.tools.some(
                      (name) =>
                        !chosenConnection?.approved_catalog.some(
                          (tool) =>
                            tool.name === name &&
                            assignment.toolHashes[name] === tool.descriptor_hash,
                        ),
                    ) && (
                      <div className="space-y-2 rounded-control bg-warning-bg p-3 text-xs text-warning">
                        <p>
                          旧许可已失效：
                          {assignment.tools
                            .filter(
                              (name) =>
                                !chosenConnection?.approved_catalog.some(
                                  (tool) =>
                                    tool.name === name &&
                                    assignment.toolHashes[name] === tool.descriptor_hash,
                                ),
                            )
                            .join("、")}
                          。目录更新没有自动迁移这些许可。
                        </p>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() =>
                            updateAssignment({
                              tools: validGrantedTools(assignment, chosenConnection),
                            })
                          }
                        >
                          移除失效许可
                        </Button>
                      </div>
                    )}
                  </section>
                  <Field label="每轮调用次数上限">
                    <Input
                      type="number"
                      min={1}
                      max={32}
                      value={assignment.maxCalls}
                      onChange={(event) =>
                        updateAssignment({
                          maxCalls: Math.max(1, Math.min(32, Number(event.target.value) || 1)),
                        })
                      }
                    />
                  </Field>
                  <p className="type-caption">
                    沿用现有员工工具许可与调用预算。资源权限仍需受限上游账号或平台已实现的可靠参数约束。
                  </p>
                </>
              ) : (
                <>
                  <p className="type-caption">
                    沿用当前原生沙箱工作区连接。这里的就绪状态与授权均为模拟。
                  </p>
                  <div className="form-grid">
                    {current.tools.map((tool) => (
                      <label key={tool.name} className="flex items-center gap-2 text-sm">
                        <Switch
                          checked={assignment.tools.includes(tool.name)}
                          onCheckedChange={(checked) =>
                            updateAssignment({
                              tools: checked
                                ? [...assignment.tools, tool.name]
                                : assignment.tools.filter((name) => name !== tool.name),
                            })
                          }
                        />
                        {tool.label}
                        <span className="type-caption">{tool.name}</span>
                      </label>
                    ))}
                  </div>
                  <Field label="每轮调用次数上限">
                    <Input
                      type="number"
                      min={1}
                      max={32}
                      value={assignment.maxCalls}
                      onChange={(event) =>
                        updateAssignment({
                          maxCalls: Math.max(1, Math.min(32, Number(event.target.value) || 1)),
                        })
                      }
                    />
                  </Field>
                  <p className="type-caption">
                    读取范围：输入、资料、工作区、成果；写入范围：工作区、成果。执行命令固定走沙箱，不由
                    Skill 决定。
                  </p>
                </>
              )}
            </div>
          )}
          {error && (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
          )}
          <DialogFooter>
            <Button
              variant="ghost"
              onClick={() => {
                setDraft((value) => ({
                  ...value,
                  assignments: value.assignments.filter((item) => item.capabilityId !== editingId),
                }));
                setDialog(null);
                notice("已从员工草稿移除，保存配置后生效。");
              }}
            >
              移除装配
            </Button>
            <Button variant="outline" onClick={() => setDialog(null)}>
              取消
            </Button>
            <Button onClick={applyConfiguration}>应用到员工</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={dialog === "new"}
        onOpenChange={(open) => {
          if (!open) setDialog(null);
        }}
      >
        <DialogContent size="wide">
          <DialogHeader>
            <DialogTitle>新增能力</DialogTitle>
            <DialogDescription>新增只进入共享能力库，不自动装配给员工。</DialogDescription>
          </DialogHeader>
          <Tabs
            value={newKind}
            onValueChange={(value) => {
              setNewKind(value);
              setSource("");
              setError("");
            }}
          >
            <TabsList aria-label="新增能力类型">
              <TabsTrigger value="skill">导入 Skill</TabsTrigger>
              <TabsTrigger value="mcp">接入远程 MCP</TabsTrigger>
            </TabsList>
          </Tabs>
          <Field label="能力名称">
            <Input value={newName} onChange={(event) => setNewName(event.target.value)} />
          </Field>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              onClick={() => {
                setSource(newKind === "skill" ? sampleSkill : sampleMcp);
                setNewName(newKind === "skill" ? "资料整理示例" : "团队检索服务");
              }}
            >
              载入示例
            </Button>
            {newKind === "skill" && (
              <Button variant="outline" onClick={() => fileInput.current?.click()}>
                <FolderOpen size={15} />
                选择 SKILL.md
              </Button>
            )}
          </div>
          <input
            ref={fileInput}
            hidden
            type="file"
            accept=".md"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (!file) return;
              if (file.size > 16384) {
                setError("演示只读取 16 KB 以内的 SKILL.md。");
                return;
              }
              void file.text().then((text) => setSource(text));
            }}
          />
          <Field label={newKind === "skill" ? "SKILL.md 内容预览" : "MCP 连接配置 JSON"}>
            <Textarea
              rows={9}
              value={source}
              spellCheck={false}
              onChange={(event) => setSource(event.target.value)}
            />
          </Field>
          <FeatureNote>
            {newKind === "skill"
              ? "拟新增：标准包导入入口。此 Demo 仅读取单个 SKILL.md，不解压 ZIP，也不执行脚本。"
              : "拟新增：连接配置导入。只解析远程 HTTP 地址与凭据占位符，不发起真实请求。"}
          </FeatureNote>
          {error && (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialog(null)}>
              取消
            </Button>
            <Button onClick={createCapability}>加入能力库</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={!!pending}
        onOpenChange={(open) => {
          if (!open) setPending(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>当前员工有未保存修改</DialogTitle>
            <DialogDescription>切换前可以保存演示配置，或放弃本次草稿。</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPending(null)}>
              继续编辑
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                if (pending) {
                  const next = pending;
                  setDraft(structuredClone(saved));
                  move(next);
                }
              }}
            >
              放弃并继续
            </Button>
            <Button
              onClick={() => {
                if (pending) {
                  const next = pending;
                  if (!saveEmployee()) {
                    setPending(null);
                    return;
                  }
                  if (next.employeeId && next.employeeId !== employeeId)
                    setDraft(
                      structuredClone(
                        employees.find((employee) => employee.agent.id === next.employeeId)!,
                      ),
                    );
                  if (next.employeeId) setEmployeeId(next.employeeId);
                  if (next.view) setView(next.view);
                  setPending(null);
                }
              }}
            >
              保存并继续
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      {testOpen && (
        <DemoInvocationDialog
          key={employeeId}
          employee={saved}
          capabilities={capabilities}
          connections={connections}
          open
          onClose={() => setTestOpen(false)}
        />
      )}
    </div>
  );
}
