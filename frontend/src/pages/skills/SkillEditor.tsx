import { mutationOutcome } from "@/lib/failures/resolve";
import { useFailureState } from "@/state/shared/useFailureState";
import { FailureNotice } from "@/components/failure/FailureNotice";
import { clientFailure } from "@/lib/failures/resolve";
import { FormField } from "@/components/common/FormField";
import { ConfirmActionDialog } from "@/components/common/ConfirmActionDialog";
import { ResourceIcon } from "@/components/common/ResourceIcon";
import { Card } from "@/components/ui/Card";
import { PageContainer } from "@/components/common/PageContainer";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Download, FilePlus2, Trash2, Upload } from "lucide-react";
import { ConfigurationConflict } from "@/components/configuration/ConfigurationConflict";
import { StaleDraftNotice } from "@/components/configuration/StaleDraftNotice";
import { ApiError } from "@/lib/api/http";
import { readSkillFile } from "@/lib/api/skills";
import { Switch } from "@/components/ui/Switch";
import { useIdentity } from "@/state/auth/useIdentity";
import { identityKey } from "@/lib/identity";
import { useDraft } from "@/hooks/useDraft";
import { draftKey, clearDraft } from "@/lib/draft";
import { useEditingRegistration } from "@/state/editing/useEditing";
import { Button } from "@/components/ui/Button";
import { PageHeading } from "@/components/common/PageHeading";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { type Skill, type SkillPackageInput } from "@/lib/models/skill";
import { SkillPackageImport, base64File } from "./SkillPackageImport";
const template =
  "---\nname: custom-skill\ndescription: Describe when this skill should be used.\n---\n\n# 工作指引\n\n在这里编写工作步骤，使用相对路径引用 scripts/、references/ 和 assets/ 文件。\n";
export function SkillEditor({
  value,
  onSave,
  onClose,
}: {
  value: Skill | "new";
  onSave: (skill: Skill) => Promise<void>;
  onClose: () => void;
}) {
  const [baseline] = useState(() => {
    const base: Skill =
      value === "new"
        ? {
            id: "",
            active: true,
            configurationSchema: {},
            name: "",
            category: "其他",
            description: "",
            instructions: "",
            input: "",
            output: "",
            example: "",
            skillMd: template,
          }
        : { ...value, assignmentCount: undefined };
    return {
      ...base,
      files: undefined,
      packageFiles: undefined,
      schemaText: JSON.stringify(base.configurationSchema ?? {}, null, 2),
      skillMd: base.skillMd ?? template,
    };
  });
  const identity = useIdentity();
  const storageKey = draftKey(identityKey(identity), `skill:${baseline.id || "new"}`);
  const [draft, setDraft, recovery] = useDraft(storageKey, baseline, { preserveStale: true });
  const [assets, setAssets] = useState<Record<string, SkillPackageInput>>({});
  const [assetsLoading, setAssetsLoading] = useState(
    value !== "new" && !!value.files?.some((file) => file.path !== "SKILL.md"),
  );
  const {
    failure: assetsFailure,
    error: assetsError,
    setError: setAssetsError,
  } = useFailureState();
  const [assetsRevision, setAssetsRevision] = useState(0);
  const [assetsDirty, setAssetsDirty] = useState(false);
  const [selected, setSelected] = useState("SKILL.md");
  const [removingPath, setRemovingPath] = useState<string | null>(null);
  const [newPath, setNewPath] = useState("");
  const [saving, setSaving] = useState(false);
  const busy = useRef(false);
  const { failure, setError } = useFailureState();
  const [conflict, setConflict] = useState(false);
  const [discard, setDiscard] = useState(false);
  const dirty = JSON.stringify(draft) !== JSON.stringify(baseline) || assetsDirty;
  const skillId = value === "new" ? "" : value.id;
  const pathsKey =
    value === "new"
      ? ""
      : (value.files ?? [])
          .filter((file) => file.path !== "SKILL.md")
          .map((file) => file.path)
          .join("\n");
  useEffect(() => {
    if (!skillId || !pathsKey) return;
    const controller = new AbortController();
    Promise.all(pathsKey.split("\n").map((path) => readSkillFile(skillId, path, controller.signal)))
      .then((files) => {
        if (!controller.signal.aborted) {
          setAssets(
            Object.fromEntries(
              files.map(({ path, content, content_base64: encoded }) => [
                path,
                content !== undefined ? { path, content } : { path, content_base64: encoded },
              ]),
            ),
          );
          setAssetsLoading(false);
        }
      })
      .catch((failure) => {
        if (!controller.signal.aborted) {
          setAssetsError(failure);
          setAssetsLoading(false);
        }
      });
    return () => controller.abort();
  }, [skillId, pathsKey, setAssetsError, assetsRevision]);
  useEditingRegistration({
    dirty,
    saving,
    isSaving: () => busy.current,
    discard: () => {
      clearDraft(storageKey);
      setDraft(baseline);
      setAssetsDirty(false);
    },
  });
  function close() {
    if (!busy.current) {
      if (dirty) setDiscard(true);
      else onClose();
    }
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy.current || assetsLoading || assetsError) return;
    busy.current = true;
    setSaving(true);
    setError("");
    setConflict(false);
    try {
      let schema: unknown;
      try {
        schema = JSON.parse(draft.schemaText);
      } catch {
        throw clientFailure("invalid_skill_schema", "参数规范必须为有效的 JSON 对象。");
      }
      if (!schema || typeof schema !== "object" || Array.isArray(schema))
        throw clientFailure("invalid_skill_schema", "参数规范必须为 JSON 对象。");
      await onSave({
        ...draft,
        configurationSchema: schema as Record<string, unknown>,
        name: draft.name.trim(),
        category: draft.category.trim() || "其他",
        skillMd: draft.skillMd,
        packageFiles: [{ path: "SKILL.md", content: draft.skillMd }, ...Object.values(assets)],
      });
    } catch (failure) {
      setConflict(
        failure instanceof ApiError && failure.code === "configuration_revision_conflict",
      );
      setError(failure);
    } finally {
      busy.current = false;
      setSaving(false);
    }
  }
  function addText() {
    const path = newPath.trim();
    if (!path || path === "SKILL.md" || path in assets) {
      setError("请填写新的相对文件路径。");
      return;
    }
    setAssets((current) => ({ ...current, [path]: { path, content: "" } }));
    setAssetsDirty(true);
    setSelected(path);
    setNewPath("");
    setError("");
  }
  const selectedFile = assets[selected];
  return (
    <PageContainer as="section" className="space-y-6">
      <PageHeading
        title={value === "new" ? "新建技能" : "编辑技能"}
        description="以标准 SKILL.md 和支持文件组织工作方法。上传不执行代码，脚本由获准的沙箱工具运行。"
        actions={
          <>
            <Button type="button" variant="outline" disabled={saving} onClick={close}>
              取消
            </Button>
            <Button
              type="submit"
              form="skill-editor"
              disabled={assetsLoading || !!assetsError || !!recovery.stale}
              loading={saving}
            >
              {saving ? "正在保存…" : "保存技能"}
            </Button>
          </>
        }
      />
      {value === "new" && (
        <details open={new URLSearchParams(window.location.search).get("import") === "1"}>
          <summary className="cursor-pointer text-sm text-text-muted">已有技能包？导入 ZIP</summary>
          <div className="mt-4">
            <SkillPackageImport />
          </div>
        </details>
      )}
      <form id="skill-editor" onSubmit={submit} className="space-y-5">
        <StaleDraftNotice
          visible={!!recovery.stale}
          onRestore={() => {
            recovery.restore();
            setConflict(true);
          }}
          onDiscard={recovery.discard}
        />
        {conflict && baseline.id && (
          <ConfigurationConflict
            resource={`skills/${baseline.id}`}
            onUseRevisions={(revision) => {
              setDraft({ ...draft, revision: revision.revision });
              setConflict(false);
              setError("");
            }}
          />
        )}
        <fieldset disabled={saving || !!recovery.stale} className="space-y-5">
          <Card as="section" variant="outline" className="form-panel">
            <div className="form-grid">
              <FormField htmlFor="skill-name" label={<>展示别名（可选）</>}>
                <Input
                  id="skill-name"
                  placeholder="留空使用技能包的标准名称"
                  value={draft.name}
                  onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                />
              </FormField>
              <FormField htmlFor="skill-category" label={<>分类（平台设置）</>}>
                <Input
                  id="skill-category"
                  value={draft.category}
                  onChange={(e) => setDraft({ ...draft, category: e.target.value })}
                />
              </FormField>
              <p className="type-caption col-span-full">
                协议名称与触发描述写在 SKILL.md 的 name、description；展示名称可使用中文。
              </p>
              {baseline.sourcePath && (
                <p className="type-caption break-all col-span-full">
                  标准目录：{baseline.sourcePath}。保存会写回目录；命令行修改后，请先在能力库同步。
                  {baseline.sourceMissing && (
                    <span className="text-danger"> 来源缺失，当前显示已发布版本。</span>
                  )}
                </p>
              )}
            </div>
          </Card>
          <Card as="section" variant="outline" className="@container/files overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border p-4">
              <h2 className="type-title">技能文件</h2>
              {baseline.id && (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  render={<a href={`/api/skills/${baseline.id}/export`} download />}
                  nativeButton={false}
                >
                  <Download />
                  导出已保存技能包
                </Button>
              )}
            </div>
            <div className="file-layout min-h-112">
              <aside className="min-w-0 border-b border-border p-4 @min-[800px]/files:border-r @min-[800px]/files:border-b-0">
                <details open>
                  <summary className="mb-4 cursor-pointer text-sm">技能文件目录与资源</summary>
                  <div className="space-y-4">
                    <div className="focus-gutter max-h-72 space-y-1 overflow-auto">
                      {["SKILL.md", ...Object.keys(assets).sort()].map((path) => (
                        <button
                          type="button"
                          key={path}
                          className={`flex w-full items-start gap-2 rounded-control p-2 text-left text-sm break-all ${selected === path ? "bg-selected" : "hover:bg-muted"}`}
                          onClick={() => setSelected(path)}
                        >
                          <ResourceIcon kind="document" size={15} className="mt-0.5 shrink-0" />
                          {path}
                        </button>
                      ))}
                    </div>
                    <FormField label={<>新文件路径</>}>
                      <Input
                        placeholder="scripts/analyze.py"
                        value={newPath}
                        onChange={(e) => setNewPath(e.target.value)}
                      />
                    </FormField>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      disabled={assetsLoading}
                      onClick={addText}
                    >
                      <FilePlus2 />
                      新增文本文件
                    </Button>
                    <FormField
                      label={
                        <>
                          <span className="inline-flex items-center gap-2">
                            <Upload size={15} />
                            上传资源或替换文件
                          </span>
                        </>
                      }
                    >
                      <Input
                        type="file"
                        disabled={assetsLoading}
                        onChange={(e) => {
                          const file = e.target.files?.[0];
                          e.target.value = "";
                          if (!file) return;
                          if (file.size > 10 * 1024 * 1024) {
                            setError("单文件不能超过 10 MiB。");
                            return;
                          }
                          const path = newPath.trim() || file.name;
                          if (path === "SKILL.md") {
                            void file.text().then((content) => {
                              setDraft((current) => ({ ...current, skillMd: content }));
                              setSelected("SKILL.md");
                            });
                            return;
                          }
                          void base64File(file).then((encoded) => {
                            setAssets((current) => ({
                              ...current,
                              [path]: { path, content_base64: encoded },
                            }));
                            setAssetsDirty(true);
                            setSelected(path);
                            setNewPath("");
                          });
                        }}
                      />
                    </FormField>
                    <p className="type-caption">
                      路径可为 scripts/、references/、assets/
                      下文件；保存时统一校验。二进制资源原样保存。
                    </p>
                  </div>
                </details>
              </aside>
              <div className="min-w-0 space-y-3 p-4">
                <div className="flex items-center justify-between gap-3">
                  <strong className="break-all text-sm">{selected}</strong>
                  {selected !== "SKILL.md" && (
                    <Button
                      type="button"
                      size="icon-sm"
                      variant="ghost"
                      aria-label={`删除${selected}`}
                      onClick={() => setRemovingPath(selected)}
                    >
                      <Trash2 />
                    </Button>
                  )}
                </div>
                {assetsLoading ? (
                  <p role="status">正在读取支持文件…</p>
                ) : assetsError ? (
                  <FailureNotice
                    failure={assetsFailure}
                    title="无法读取完整技能包"
                    context={{ operation: "initial-read", resource: "skill" }}
                    actions={[
                      {
                        label: "重新读取支持文件",
                        kind: "retry",
                        onClick: () => {
                          setAssetsError("");
                          setAssetsLoading(true);
                          setAssetsRevision((n) => n + 1);
                        },
                      },
                    ]}
                  />
                ) : selected === "SKILL.md" ? (
                  <Textarea
                    aria-label="SKILL.md 内容"
                    rows={22}
                    className="min-h-96 font-mono text-sm"
                    value={draft.skillMd}
                    onChange={(e) => setDraft({ ...draft, skillMd: e.target.value })}
                  />
                ) : selectedFile?.content !== undefined ? (
                  <Textarea
                    aria-label={`${selected}内容`}
                    rows={22}
                    className="min-h-96 font-mono text-sm"
                    value={selectedFile.content}
                    onChange={(e) => {
                      const content = e.target.value;
                      setAssets((current) => ({
                        ...current,
                        [selected]: { path: selected, content },
                      }));
                      setAssetsDirty(true);
                    }}
                  />
                ) : (
                  <Card as="div" variant="muted" radius="control" className="p-5 text-sm">
                    <p>二进制或大型资源文件，已保留原始内容。</p>
                    <p className="mt-2 text-text-muted">
                      可选择同一路径上传替换，或导出已保存技能包查看。
                    </p>
                  </Card>
                )}
              </div>
            </div>
          </Card>
          <Card as="details" variant="outline" className="form-panel">
            <summary className="cursor-pointer text-sm">平台装配设置</summary>
            <div className="mt-4 space-y-4">
              <label className="flex items-center gap-2 text-sm">
                <Switch
                  checked={draft.active ?? true}
                  onCheckedChange={(active) => setDraft({ ...draft, active })}
                />
                启用技能
              </label>
              <FormField
                htmlFor="skill-schema"
                label={<>装配参数规范（JSON Schema，仅非秘密配置）</>}
                description="此处是平台扩展，不是 Skill 标准字段。空规范无需员工填写参数；不自动授予脚本执行权限。"
              >
                <Textarea
                  id="skill-schema"
                  rows={7}
                  className="font-mono text-xs"
                  value={draft.schemaText}
                  onChange={(e) => setDraft({ ...draft, schemaText: e.target.value })}
                />
              </FormField>
            </div>
          </Card>
        </fieldset>
        {failure && (
          <FailureNotice
            failure={failure}
            context={{
              operation: "mutation",
              outcome: mutationOutcome(failure),
              resource: "skill",
            }}
          />
        )}
        {discard && (
          <Card as="div" variant="outline" radius="control" role="alert" className="p-4">
            <p className="text-sm">放弃未保存的技能修改？资源修改仅保留在当前页面。</p>
            <div className="mt-3 flex gap-2">
              <Button type="button" variant="outline" onClick={() => setDiscard(false)}>
                继续编辑
              </Button>
              <Button type="button" variant="destructive" onClick={onClose}>
                放弃修改
              </Button>
            </div>
          </Card>
        )}
      </form>
      <ConfirmActionDialog
        open={!!removingPath}
        onOpenChange={(open) => {
          if (!open) setRemovingPath(null);
        }}
        title={`移除文件「${removingPath ?? ""}」？`}
        description="从当前技能包草稿中移除这个支持文件，保存技能后生效。其他文件和主文继续保留。"
        confirmLabel="确认移除文件"
        onConfirm={() => {
          if (!removingPath) return;
          setAssets((current) => {
            const next = { ...current };
            delete next[removingPath];
            return next;
          });
          setAssetsDirty(true);
          setSelected("SKILL.md");
          setRemovingPath(null);
        }}
      />
    </PageContainer>
  );
}
