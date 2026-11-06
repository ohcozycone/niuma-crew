import { ResourceIcon } from "@/components/common/ResourceIcon";
import { memo, useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { ArrowUp, Square, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { InputGroup, InputGroupAddon, InputGroupTextarea } from "@/components/ui/InputGroup";
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from "@/components/ui/Collapsible";
import { useDraft } from "@/hooks/useDraft";
import type { AgentUsageDTO } from "@/lib/api/agents";
import type { ConversationInput } from "@/lib/api/conversationTransport";
import type { ConversationPhase } from "./conversationState";
import { composeInput } from "./conversationDraft";
import { ConversationFiles } from "./ConversationFiles";
import type { FileRef } from "@/lib/api/files";

/** 输入与技能选择留在此处，按键不更新消息列表。 */
export const ConversationComposer = memo(function ConversationComposer({
  agent,
  storageKey,
  status,
  canStop,
  canRetry,
  onSend,
  onStop,
  onRetry,
  acceptedInput,
  conversationId,
}: {
  agent: AgentUsageDTO;
  storageKey: string;
  status: ConversationPhase;
  canStop: boolean;
  canRetry: boolean;
  onSend: (input: ConversationInput) => Promise<void>;
  onStop: () => Promise<void>;
  onRetry: () => Promise<void>;
  acceptedInput: ConversationInput | null;
  conversationId?: string;
}) {
  const [baseline] = useState(() => ({ content: "" }));
  const [input, setInput] = useDraft(storageKey, baseline);
  const [selectedSkillIds, setSelectedSkillIds] = useState<string[]>([]);
  const [files, setFiles] = useState<FileRef[]>([]);
  const [uploading, setUploading] = useState(false);
  const cleared = useRef<ConversationInput | null>(null);
  useEffect(() => {
    if (!acceptedInput || cleared.current === acceptedInput) return;
    cleared.current = acceptedInput;
    setFiles((current) =>
      current.filter((file) => !acceptedInput.files?.some((saved) => saved.id === file.id)),
    );
    if (input.content.trim() === acceptedInput.content) setInput({ content: "" });
  }, [acceptedInput, input.content, setInput]);
  const ready = agent.is_active && (agent.model_configured ?? !!agent.model_connection_id);
  const busy = status === "submitted" || status === "streaming";
  const canSend = status === "ready" && !uploading && ready && !!input.content.trim();
  return (
    <footer className="conversation-page-frame shrink-0 pt-2 pb-4">
      {!ready && (
        <p className="mb-2 text-xs text-text-muted">
          {agent.is_active ? "员工尚未装配大脑。" : "员工已停用。"}{" "}
          <Link className="underline" to={`/agents/${agent.id}?tab=identity`}>
            前往员工配置
          </Link>
        </p>
      )}
      {agent.skill_assignments.length > 0 && (
        <Collapsible className="relative z-20 mb-3 text-sm">
          <CollapsibleTrigger className="flex items-center gap-2 rounded-control text-xs text-text-muted">
            <ResourceIcon kind="skill" size={16} />
            选用技能
            {selectedSkillIds.length ? ` · 已选 ${selectedSkillIds.length} 项` : " · 自动判断"}
          </CollapsibleTrigger>
          <CollapsibleContent>
            <fieldset disabled={status !== "ready"} className="mt-2 space-y-2">
              <legend className="sr-only">按需使用技能（不选时自动判断）</legend>
              {agent.skill_assignments.map((skill) => (
                <label key={skill.skill_id} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    className="size-4 shrink-0 accent-action"
                    disabled={!skill.ready}
                    checked={selectedSkillIds.includes(skill.skill_id)}
                    onChange={(event) =>
                      setSelectedSkillIds((ids) =>
                        event.target.checked
                          ? [...ids, skill.skill_id]
                          : ids.filter((id) => id !== skill.skill_id),
                      )
                    }
                  />
                  {skill.name}
                  {!skill.ready && (
                    <span className="text-text-muted"> · {skill.readiness_reason}</span>
                  )}
                </label>
              ))}
            </fieldset>
          </CollapsibleContent>
        </Collapsible>
      )}
      <div className="relative isolate">
        <form
          data-slot="conversation-composer"
          className="relative z-10"
          onSubmit={(event) => {
            event.preventDefault();
            if (canSend)
              void onSend({
                ...composeInput(input.content, selectedSkillIds),
                ...(files.length ? { files } : {}),
              }).catch(() => {
                /* 错误由会话反馈展示，草稿保留。 */
              });
          }}
        >
          <InputGroup className="p-4">
            <InputGroupTextarea
              data-slot="conversation-input"
              className="block min-h-12 max-h-36 w-full resize-none rounded-none border-0 bg-transparent px-1.5 py-1 text-sm leading-6 text-text shadow-none [field-sizing:content] placeholder:text-text-muted max-sm:text-base"
              aria-label="消息"
              placeholder={`发消息给${agent.name}…`}
              value={input.content}
              disabled={!ready || status === "loading" || status === "submitted"}
              onChange={(event) => setInput({ content: event.target.value })}
              rows={2}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
            />
            <InputGroupAddon
              align="block-end"
              className="mt-3 items-end justify-between gap-3 px-0 py-0"
            >
              <div className="min-w-0 flex-1">
                <ConversationFiles
                  conversationId={conversationId}
                  selected={files}
                  onChange={setFiles}
                  disabled={status !== "ready"}
                  onBusy={setUploading}
                  compact
                />
              </div>
              <div className="flex shrink-0 flex-wrap gap-2">
                {canRetry && status === "ready" && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={!ready}
                    onClick={() => {
                      void onRetry().catch(() => {});
                    }}
                  >
                    <RotateCcw size={14} />
                    重试回答
                  </Button>
                )}
                {busy ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={!canStop}
                    onClick={() => {
                      void onStop().catch(() => {});
                    }}
                  >
                    <Square size={14} />
                    {canStop ? "停止生成" : "正在停止"}
                  </Button>
                ) : (
                  <Button type="submit" size="sm" disabled={!canSend}>
                    <ArrowUp size={16} />
                    发送
                  </Button>
                )}
              </div>
            </InputGroupAddon>
          </InputGroup>
        </form>
      </div>
      <p className="mt-2 text-center text-[11px] text-text-muted">
        <span className="max-sm:hidden">Enter 发送 · Shift + Enter 换行</span>
      </p>
    </footer>
  );
});
