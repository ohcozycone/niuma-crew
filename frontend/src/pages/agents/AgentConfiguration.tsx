import { mutationOutcome } from "@/lib/failures/resolve";
import { useFailureState } from "@/state/shared/useFailureState";
import { FailureNotice } from "@/components/failure/FailureNotice";
import { clientFailure } from "@/lib/failures/resolve";
import { PageContainer } from "@/components/common/PageContainer";
import { AgentCapabilityAssembly } from "./AgentCapabilityAssembly";
import { FormField } from "@/components/common/FormField";
import { AgentInstructions } from "./AgentInstructions";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/Dialog";
import { useEditingRegistration } from "@/state/editing/useEditing";
import { ConfigurationConflict } from "@/components/configuration/ConfigurationConflict";
import { StaleDraftNotice } from "@/components/configuration/StaleDraftNotice";
import { ApiError } from "@/lib/api/http";
import { useIdentity } from "@/state/auth/useIdentity";
import { identityKey } from "@/lib/identity";
import { useDraft } from "@/hooks/useDraft";
import { draftKey, clearDraft } from "@/lib/draft";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowRight, Camera, Check, Eye, Save } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { ButtonGroup } from "@/components/ui/ButtonGroup";
import { PageHeading } from "@/components/common/PageHeading";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { TabsContent } from "@/components/ui/Tabs";
import { PageTabs } from "@/components/common/PageTabs";
import { SelectField } from "@/components/ui/SelectField";
import { AgentModelConnectionField } from "@/pages/agents/AgentModelConnectionField";
import { defaultAvatarId, findAvatar } from "@/components/avatars/index";
import { AvatarPicker } from "@/components/avatars/index";
import { AgentAvatar } from "@/components/avatars/index";
import { AgentCard } from "@/pages/agents/AgentCard";

import { toAgentPresentation } from "./agentPresentation";
import { type Agent as Agent } from "@/lib/models/agent";
import { type SkillListItem } from "@/lib/models/skill";
const categories = ["财务行政", "知识管理", "内容创作", "研究分析", "客户服务", "研发协作", "其他"];
export type ConfigurationTab = "identity" | "instructions" | "capabilities";
function initialDraft(value: Agent | "new") {
  const agent = value === "new" ? null : value;
  return {
    revision: agent?.revision ?? 0,
    toolGrants: agent?.toolGrants ?? [],
    name: agent?.name || "",
    description: agent?.description || "",
    category: agent?.category || "财务行政",
    avatarId: agent?.avatarId || defaultAvatarId,
    systemPrompt: agent?.systemPrompt || "",
    assignmentSettings: Object.fromEntries(
      (agent?.skillAssignments ?? []).map((a) => [
        a.skillId,
        {
          enabled: a.enabled,
          parameters: JSON.stringify(a.parameters, null, 2),
        },
      ]),
    ) as Record<string, { enabled: boolean; parameters: string }>,
    modelConnectionId: agent?.modelConnectionId ?? null,
    skills: agent?.skills || [],
  };
}
function snapshot(draft: ReturnType<typeof initialDraft>) {
  return JSON.stringify({ ...draft, skills: [...draft.skills].sort() });
}
export function AgentConfiguration({
  value,
  skills,
  saving,
  onDelete,
  initialTab = "identity",
  onClose,
  onSave,
  onSaved,
  onTabChange,
}: {
  value: Agent | "new";
  skillTotal?: number;
  skills: SkillListItem[];
  saving: boolean;
  onDelete?: () => void;
  initialTab?: ConfigurationTab;
  onTabChange?: (tab: string) => void;
  onClose: () => void;
  onSave: (agent: Agent) => Promise<Agent>;
  onSaved: () => void;
}) {
  const availableSkills = skills;
  const { failure: saveFailure, setError: setSaveError } = useFailureState();
  const [toolsValid, setToolsValid] = useState(true);
  const [conflict, setConflict] = useState(false);
  const editing = value === "new" ? null : value;
  const [baseline, setBaseline] = useState(() => initialDraft(value));
  const [saved, setSaved] = useState(false);
  const submitting = useRef(false);
  const pendingNavigation = useRef(false);
  const identity = useIdentity();
  const storageKey = draftKey(identityKey(identity), `agent:${editing?.id ?? "new"}`);
  const [draft, setDraft, recovery] = useDraft(storageKey, baseline, {
    preserveStale: true,
  });
  const tab = initialTab;
  const setTab = (next: string) => onTabChange?.(next);
  const [avatarOpen, setAvatarOpen] = useState(false);
  const [error, setError] = useState("");
  const dirty = snapshot(draft) !== snapshot(baseline);
  const unchanged = !!editing && !dirty;
  const avatar = findAvatar(draft.avatarId);
  const [modelReady, setModelReady] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const preview: Agent = {
    id: editing?.id || "new",
    code: editing?.code || "",
    role: editing?.role || "",
    icon: editing?.icon || "custom",
    active: editing?.active ?? true,
    favorite: editing?.favorite ?? false,
    toolCount: (draft.toolGrants ?? baseline.toolGrants)
      .filter((grant) => grant.enabled)
      .reduce((count, grant) => count + grant.tools.length, 0),
    knowledgeBaseCount: editing?.knowledgeBaseCount ?? 0,
    deliverables: editing?.deliverables ?? [],
    exampleTasks: editing?.exampleTasks ?? [],
    ...draft,
    toolGrants: draft.toolGrants ?? baseline.toolGrants,
    revision: draft.revision,
    configurationLoaded: editing?.configurationLoaded ?? false,
    skillAssignments: draft.skills.map((skillId) => ({
      skillId,
      enabled: draft.assignmentSettings[skillId]?.enabled ?? true,
      parameters: {},
    })),
  };
  useEditingRegistration({
    dirty,
    saving,
    isSaving: () => saving,
    discard: () => {
      clearDraft(storageKey);
      setDraft(baseline);
    },
  });
  useEffect(() => {
    // 离页保护在 layout effect 中接收已确认的草稿与新修订，再执行导航。
    if (!saved || dirty || saving || !pendingNavigation.current) return;
    pendingNavigation.current = false;
    submitting.current = false;
    onSaved();
  }, [saved, dirty, saving, onSaved]);
  useEffect(() => {
    if (error && tab === "identity") document.getElementById("agent-name")?.focus();
  }, [error, tab]);
  function update<K extends keyof typeof draft>(key: K, value: (typeof draft)[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
    if (key === "name") setError("");
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (saving || submitting.current) return;
    if (editing && !dirty) return;
    if (!toolsValid) {
      setSaveError("请先修正工具范围约束的 JSON 格式。");
      setTab("capabilities");
      return;
    }
    setSaveError("");
    setError("");
    setConflict(false);
    if (!draft.name.trim()) {
      setError("先为这位员工起个名字。其他配置可以稍后完善。");
      setTab("identity");
      return;
    }
    // Preserve an existing retired selection until the user explicitly changes it.
    if (!avatar && !(editing && draft.avatarId === editing.avatarId)) {
      setSaveError("当前头像不可用，请重新选择头像。");
      setTab("identity");
      return;
    }
    try {
      const input = {
        ...preview,
        id: editing?.id || "",
        name: draft.name.trim(),
        description: draft.description.trim(),
        skillAssignments: draft.skills.map((skillId) => {
          const settings = draft.assignmentSettings[skillId];
          let parameters: unknown;
          try {
            parameters = JSON.parse(settings?.parameters || "{}");
          } catch {
            setTab("capabilities");
            throw clientFailure("invalid_skill_parameters", "技能参数必须为有效的 JSON 对象。");
          }
          if (!parameters || typeof parameters !== "object" || Array.isArray(parameters)) {
            setTab("capabilities");
            throw clientFailure("invalid_skill_parameters", "技能参数必须为 JSON 对象。");
          }
          return {
            skillId,
            enabled: settings?.enabled ?? true,
            parameters: parameters as Record<string, unknown>,
          };
        }),
      };
      submitting.current = true;
      setSaved(false);
      const confirmed = await onSave(input);
      const next = initialDraft(confirmed);
      setBaseline(next);
      setDraft(next);
      clearDraft(storageKey);
      pendingNavigation.current = true;
      setSaved(true);
    } catch (error) {
      submitting.current = false;
      if (error instanceof ApiError && error.code === "agent_name_conflict") {
        setError(error.message);
        setTab("identity");
        return;
      }
      setConflict(error instanceof ApiError && error.code === "configuration_revision_conflict");
      setSaveError(error);
    }
  }
  const presentation = toAgentPresentation({
    ...preview,
    name: draft.name.trim() || "等待一位新同事",
  });
  if (preview.active && !modelReady) presentation.availability = "unconfigured";
  const previewCard = <AgentCard agent={presentation} preview />;
  return (
    <PageContainer className="agent-editor-frame">
      <form onSubmit={submit} noValidate>
        <StaleDraftNotice
          visible={!!recovery.stale}
          onRestore={() => {
            recovery.restore();
            setConflict(true);
          }}
          onDiscard={recovery.discard}
        />
        <fieldset disabled={saving || !!recovery.stale} className="min-w-0">
          <PageHeading
            title={editing ? "编辑员工" : "创建数字员工"}
            description="配置身份、工作要求与可用能力。"
            actions={
              <div className="flex flex-wrap items-center gap-6 @max-[640px]/page:gap-3">
                {onDelete && (
                  <Button type="button" variant="destructive-ghost" onClick={onDelete}>
                    删除员工
                  </Button>
                )}
                <ButtonGroup aria-label="员工配置操作" role="group">
                  <Button type="button" variant="outline" onClick={onClose}>
                    返回
                  </Button>
                  <Button type="submit" loading={saving} disabled={unchanged}>
                    {unchanged ? <Check size={16} /> : <Save size={16} />}
                    <span className="min-w-[4em]">
                      {saving ? "保存中…" : unchanged ? "已保存" : "保存配置"}
                    </span>
                  </Button>
                </ButtonGroup>
              </div>
            }
          />
          {saveFailure && (
            <FailureNotice
              failure={saveFailure}
              context={{
                operation: "mutation",
                outcome: mutationOutcome(saveFailure),
                resource: "agent",
              }}
            />
          )}
          {conflict && editing && (
            <ConfigurationConflict
              resource={`agents/${editing.id}`}
              onUseRevisions={(value) => {
                if (value.revision) update("revision", value.revision);
                setConflict(false);
                setSaveError("");
              }}
            />
          )}
          <PageTabs
            value={tab}
            onValueChange={setTab}
            label="员工配置"
            items={[
              { value: "identity", label: "基础配置" },
              { value: "instructions", label: "指令与知识" },
              {
                value: "capabilities",
                label: "能力装配",
                count: draft.skills.length + (draft.toolGrants ?? baseline.toolGrants).length,
              },
            ]}
          >
            <TabsContent value="identity" className="m-0 pt-2">
              <div className="configuration-layout gap-10">
                <section
                  aria-labelledby="agent-profile-heading"
                  className="min-w-0 space-y-8 @container/identity"
                >
                  <h2
                    id="agent-profile-heading"
                    className="type-section border-b border-border pb-4"
                  >
                    员工资料
                  </h2>
                  <div className="flex min-w-0 flex-wrap items-center gap-x-8 gap-y-5">
                    <Button
                      type="button"
                      variant="ghost"
                      className="group relative size-28 shrink-0 rounded-full p-0 hover:bg-transparent has-[>svg]:px-0"
                      aria-label="更换头像"
                      aria-haspopup="dialog"
                      aria-expanded={avatarOpen}
                      title="更换头像"
                      onClick={() => setAvatarOpen(true)}
                    >
                      <span className="flex size-full shrink-0 items-center justify-center overflow-hidden rounded-full bg-avatar-bg transition-colors group-hover:bg-muted">
                        <AgentAvatar
                          avatarId={preview.avatarId}
                          size="100%"
                          alt={avatar?.name ?? "当前员工头像"}
                          className="size-full"
                        />
                      </span>
                      <span
                        aria-hidden="true"
                        className="absolute -right-1 bottom-1 flex size-6 items-center justify-center rounded-full bg-action/65 text-action-text transition-colors group-hover:bg-action/80"
                      >
                        <Camera strokeWidth={1.5} className="size-3.5" />
                      </span>
                    </Button>
                    <div className="min-w-0 flex-1 basis-44">
                      <AgentModelConnectionField
                        value={draft.modelConnectionId}
                        onChange={(id) => update("modelConnectionId", id)}
                        onReadinessChange={setModelReady}
                      />
                    </div>
                  </div>
                  <div className="@container">
                    <div className="form-grid items-start gap-8">
                      <FormField
                        label={
                          <>
                            员工名称{" "}
                            <span aria-hidden="true" className="text-brand">
                              *
                            </span>
                          </>
                        }
                        htmlFor="agent-name"
                        error={error || undefined}
                      >
                        <Input
                          id="agent-name"
                          autoComplete="off"
                          aria-required="true"
                          maxLength={24}
                          placeholder="为员工起个名字"
                          value={draft.name}
                          onChange={(event) => update("name", event.target.value)}
                        />
                      </FormField>
                      <FormField label="岗位分类" htmlFor="agent-category">
                        <SelectField
                          options={categories.map((value) => ({ value, label: value }))}
                          value={draft.category}
                          onValueChange={(value) => update("category", value)}
                          id="agent-category"
                          className="w-full"
                        />
                      </FormField>
                    </div>
                  </div>
                  <FormField
                    label="员工简介"
                    htmlFor="agent-description"
                    description="展示在员工卡片中，帮助同事了解适合交给他的工作。"
                  >
                    <Textarea
                      id="agent-description"
                      value={draft.description}
                      maxLength={500}
                      rows={4}
                      className="min-h-36 [field-sizing:fixed]"
                      placeholder="例如：协助技术方案设计与问题排查，说明依据和下一步。"
                      onChange={(event) => update("description", event.target.value)}
                    />
                  </FormField>
                  <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
                    <span className="type-caption">
                      {modelReady && draft.name.trim()
                        ? "名称和大脑已配置，保存后可开始对话。"
                        : "可先保存资料，装配可用大脑后再开始对话。"}
                    </span>
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      onClick={() => setTab("instructions")}
                    >
                      继续配置指令与知识
                      <ArrowRight size={16} />
                    </Button>
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="@min-[1008px]/page:hidden"
                    onClick={() => setPreviewOpen(true)}
                  >
                    <Eye size={16} />
                    预览员工卡片
                  </Button>
                </section>
                <aside
                  aria-label="员工配置预览"
                  className="hidden min-w-0 @min-[1008px]/page:block"
                >
                  {previewCard}
                </aside>
              </div>
            </TabsContent>
            <TabsContent value="instructions" className="m-0 pt-2">
              <AgentInstructions
                value={draft.systemPrompt}
                onChange={(value) => update("systemPrompt", value)}
                agentId={editing?.id}
                agentName={draft.name}
              />
            </TabsContent>
            <TabsContent value="capabilities" className="m-0 pt-2">
              <AgentCapabilityAssembly
                personalConnectionsHref={editing ? `/agents/${editing.id}/connections` : undefined}
                tools={{
                  value: draft.toolGrants ?? baseline.toolGrants,
                  onChange: (grants) => update("toolGrants", grants),
                  onValidityChange: setToolsValid,
                }}
                skills={{
                  ids: draft.skills,
                  skills: availableSkills,
                  settings: draft.assignmentSettings,
                  onChange: (settings) => update("assignmentSettings", settings),
                  onSelectionChange: (ids) => update("skills", ids),
                }}
              />
            </TabsContent>
          </PageTabs>
        </fieldset>
      </form>
      {avatarOpen && (
        <AvatarPicker
          value={draft.avatarId}
          onSelect={(id) => {
            update("avatarId", id);
            setAvatarOpen(false);
          }}
          onClose={() => setAvatarOpen(false)}
        />
      )}
      <Dialog open={previewOpen} onOpenChange={setPreviewOpen}>
        <DialogContent size="small">
          <DialogHeader>
            <DialogTitle>员工卡片预览</DialogTitle>
          </DialogHeader>
          {previewCard}
        </DialogContent>
      </Dialog>
    </PageContainer>
  );
}
