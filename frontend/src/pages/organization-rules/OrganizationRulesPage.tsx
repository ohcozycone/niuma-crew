import { ResourceIcon } from "@/components/common/ResourceIcon";
import { FailureNotice } from "@/components/failure/FailureNotice";
import { FailureState } from "@/components/failure/FailureState";
import { clientFailure, toFailure, mutationOutcome } from "@/lib/failures/resolve";
import type { Failure } from "@/lib/failures/types";
import { Card } from "@/components/ui/Card";
import { useMemo, useRef, useState, type FormEvent } from "react";
import { Check, Save } from "lucide-react";
import { PageContainer } from "@/components/common/PageContainer";
import { PageHeading } from "@/components/common/PageHeading";
import { useIdentity } from "@/state/auth/useIdentity";
import { identityKey } from "@/lib/identity";
import { Button } from "@/components/ui/Button";
import { Textarea } from "@/components/ui/Textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/Dialog";
import { clearDraft, draftKey } from "@/lib/draft";
import { useDraft } from "@/hooks/useDraft";
import { useEditing, useEditingRegistration } from "@/state/editing/useEditing";
import { ApiError } from "@/lib/api/http";
import {
  loadOrganizationRules,
  saveOrganizationRules,
  type OrganizationRules,
} from "@/lib/api/organizationRules";
import { useOrganizationRules } from "@/components/organization-rules/useOrganizationRules";

const example = `## 行为准则
- 如实说明依据和不确定性，不编造政策、资料或操作结果。
- 没有实际执行的操作，不声称已经完成。

## 越界处理
- 以员工自身的工作指令判断岗位职责；超出职责时，说明能处理的范围，并给出可行的下一步。
- 属于职责范围但信息不足时，先澄清或说明无法确认。
- 可以参考：“这件事超出了我的岗位职责。我可以先帮你整理需要确认的信息，供负责人员处理。”

## 禁止事项
- 不披露访问凭证或无权访问的个人与公司信息。
- 不承诺未经实际授权和确认的审批、付款或系统变更。`;

const heading = {
  title: "全员规范",
  description: "为所有员工设定共同的行为准则与禁令，保存后从下一次提交起生效。",
};

export function OrganizationRulesPage() {
  const identity = useIdentity();
  return (
    <PageContainer>
      {identity.permissions.includes("organization_rules:read") ? (
        <RulesContent />
      ) : (
        <>
          <PageHeading {...heading} />
          <FailureState
            failure={clientFailure("permission_denied", "全员规范需要管理员权限。")}
            context={{ operation: "initial-read" }}
            actions={[{ label: "返回知识库", kind: "return", href: "/knowledge" }]}
          />
        </>
      )}
    </PageContainer>
  );
}
export { OrganizationRulesPage as Component };

function RulesContent() {
  const { rules, failure, reload } = useOrganizationRules();
  if (rules) return <RulesEditor initial={rules} />;
  return (
    <div>
      <PageHeading {...heading} />
      {failure ? (
        <FailureState
          failure={failure}
          context={{ operation: "initial-read" }}
          actions={[{ label: "重新加载", kind: "retry", onClick: reload }]}
        />
      ) : (
        <p role="status">正在加载规章制度…</p>
      )}
    </div>
  );
}

function RulesEditor({ initial }: { initial: OrganizationRules }) {
  const identity = useIdentity();
  const canUpdate = identity.permissions.includes("organization_rules:update");
  const [baseline, setBaseline] = useState(initial);
  const storageKey = draftKey(identityKey(identity), "organization-rules");
  const draftBaseline = useMemo(
    () => ({ instructions: baseline.instructions, revision: baseline.revision }),
    [baseline.instructions, baseline.revision],
  );
  const [draft, setDraft] = useDraft(storageKey, draftBaseline);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [conflictReadFailed, setConflictReadFailed] = useState(false);
  const [success, setSuccess] = useState("");
  const [conflict, setConflict] = useState<OrganizationRules | null>(null);
  const [confirmation, setConfirmation] = useState<"load" | "overwrite" | null>(null);
  const { setSaving: setNavigationSaving } = useEditing();
  const dirty = draft.instructions !== baseline.instructions;
  useEditingRegistration({
    dirty,
    saving,
    isSaving: () => savingRef.current,
    discard: () => {
      clearDraft(storageKey);
      setDraft(draftBaseline);
    },
  });

  function accept(value: OrganizationRules) {
    clearDraft(storageKey);
    setBaseline(value);
    setDraft({ instructions: value.instructions, revision: value.revision });
    setConflict(null);
    setFailure(null);
    setConflictReadFailed(false);
  }

  async function save(revision = baseline.revision) {
    if (savingRef.current || !canUpdate || !dirty) return;
    savingRef.current = true;
    setSaving(true);
    setNavigationSaving(true);
    setFailure(null);
    setConflictReadFailed(false);
    setSuccess("");
    setConfirmation(null);
    try {
      const saved = await saveOrganizationRules(draft.instructions, revision);
      accept(saved);
      setSuccess(
        saved.instructions
          ? "已保存，所有员工后续提交的任务将采用此规则。"
          : "已清空全局规则，后续提交继续使用员工自身的工作指令。",
      );
    } catch (failure) {
      setFailure(toFailure(failure));
      if (failure instanceof ApiError && failure.code === "rules_revision_conflict") {
        try {
          setConflict(await loadOrganizationRules());
        } catch (error) {
          setConflict(null);
          setConflictReadFailed(true);
          setFailure(toFailure(error));
        }
      }
    } finally {
      savingRef.current = false;
      setSaving(false);
      setNavigationSaving(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void save();
  }

  return (
    <div>
      <form onSubmit={submit} className="min-w-0" aria-busy={saving}>
        <PageHeading
          {...heading}
          actions={
            canUpdate && (
              <Button type="submit" disabled={!dirty} loading={saving}>
                {dirty ? <Save size={16} /> : <Check size={16} />}
                <span className="min-w-[4em]">
                  {saving ? "保存中…" : dirty ? "保存规范" : "已保存"}
                </span>
              </Button>
            )
          }
        />
        <div className="mb-6 text-sm leading-7 text-text-muted">
          <p>
            <ResourceIcon kind="rules" className={"mr-2 inline"} size={16} aria-hidden="true" />
            {baseline.instructions ? `当前版本 ${baseline.revision}` : "尚未配置全局规则"} ·
            岗位职责仍由各员工的工作指令定义
          </p>
          <p>已排队或执行中的任务保留提交时的规范。</p>
        </div>
        {success && (
          <p role="status" className={"mb-4 text-sm"}>
            {success}
          </p>
        )}
        <FailureNotice
          failure={failure}
          context={{ operation: "mutation", outcome: mutationOutcome(failure) }}
          description={
            conflictReadFailed
              ? "规则版本已变化，但最新内容读取失败。草稿已保留，请稍后再次保存以重新核对。"
              : undefined
          }
          className="mb-4"
        />
        {conflict && (
          <Card
            as="section"
            variant="outline"
            radius="panel"
            aria-label="规则版本冲突"
            className="mb-6 p-4 text-sm leading-7"
          >
            <p>你的草稿已保留。最新版本为 {conflict.revision}，请核对后选择如何继续。</p>
            <details>
              <summary className={"cursor-pointer"}>查看最新制度原文</summary>
              <div className={"my-3 max-h-64 overflow-auto whitespace-pre-wrap break-words"}>
                {conflict.instructions || "最新版本为空规则。"}
              </div>
            </details>
            <div className={"mt-3 flex flex-wrap gap-2"}>
              <Button
                type="button"
                variant="outline"
                disabled={saving}
                onClick={() => setConfirmation("load")}
              >
                载入最新版本
              </Button>
              <Button
                type="button"
                variant="outline"
                disabled={saving}
                onClick={() => setConfirmation("overwrite")}
              >
                用当前草稿替换最新版本
              </Button>
            </div>
          </Card>
        )}
        <div className={"mb-3 flex flex-wrap items-center justify-between gap-2"}>
          <label htmlFor="organization-rules" className={"font-semibold"}>
            制度正文
          </label>
          {canUpdate && !draft.instructions.trim() && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={saving}
              onClick={() => {
                setDraft({ ...draft, instructions: example });
                setSuccess("");
              }}
            >
              填入规范示例
            </Button>
          )}
        </div>
        <Textarea
          id="organization-rules"
          value={draft.instructions}
          readOnly={!canUpdate}
          disabled={saving}
          maxLength={20000}
          className={"min-h-96 resize-y leading-7"}
          aria-describedby="rules-help rules-length"
          placeholder="使用 Markdown 填写全员通用的行为准则、越界处理和明确的禁止事项。"
          onChange={(event) => {
            setDraft({ ...draft, instructions: event.target.value });
            setSuccess("");
          }}
        />
        <div className={"mt-3 flex flex-wrap justify-between gap-2 text-sm text-text-muted"}>
          <p id="rules-help">支持 Markdown；留空保存可清空规则。</p>
          <span id="rules-length">
            {Array.from(draft.instructions).length.toLocaleString()} / 20,000
          </span>
        </div>
        <p className={"mt-3 text-sm text-text-muted"}>
          最近更新：{new Date(baseline.updated_at).toLocaleString("zh-CN")}
        </p>
      </form>
      <Dialog
        open={confirmation !== null}
        onOpenChange={(open) => {
          if (!open) setConfirmation(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {confirmation === "load" ? "放弃草稿并载入最新版本？" : "用当前草稿替换最新规则？"}
            </DialogTitle>
            <DialogDescription>
              {confirmation === "load"
                ? "当前未保存的草稿将被清除。"
                : `将用当前草稿替换版本 ${conflict?.revision} 的完整正文，影响所有员工后续提交的任务。`}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmation(null)}>
              继续编辑
            </Button>
            <Button
              onClick={() => {
                if (!conflict) return;
                if (confirmation === "load") {
                  accept(conflict);
                  setSuccess("");
                  setConfirmation(null);
                } else void save(conflict.revision);
              }}
            >
              {confirmation === "load" ? "载入最新版本" : "确认替换并保存"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
