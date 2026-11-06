import { mutationOutcome } from "@/lib/failures/resolve";
import { FailureNotice } from "@/components/failure/FailureNotice";
import type { Failure } from "@/lib/failures/types";
import { useState } from "react";
import { Trash2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/Dialog";

const confirmationText = "确认删除";

export function AgentDeletionDialog({
  agentName,
  saving,
  error,
  failure,
  onClose,
  onConfirm,
}: {
  agentName: string;
  saving: boolean;
  error: string;
  failure?: Failure | null;
  onClose: () => void;
  onConfirm: () => void;
}) {
  const [confirmation, setConfirmation] = useState("");
  const canDelete = confirmation === confirmationText && !saving;

  return (
    <Dialog
      open
      onOpenChange={(open, details) => {
        if (saving) {
          details.cancel();
          return;
        }
        if (!open) onClose();
      }}
    >
      <DialogContent
        size="small"

        showCloseButton={!saving}
        aria-busy={saving}
      >
        <DialogHeader className={"min-w-0 text-left"}>
          <DialogTitle>删除员工？</DialogTitle>
          <DialogDescription className={"leading-relaxed [overflow-wrap:anywhere]"}>
            即将永久删除「{agentName}」的员工配置，此操作无法撤销。
          </DialogDescription>
        </DialogHeader>
        <div className={"space-y-3 text-sm text-text-muted"}>
          <ul className={"list-disc space-y-1 pl-5"}>
            <li>一并移除该员工的技能装配关系。</li>
            <li>共享的技能和大脑配置会保留，其他员工不受影响。</li>
          </ul>
          <p>已有对话历史的员工无法删除。若只需停用，请在员工目录选择「优化它」。</p>
        </div>
        <Input
          aria-label="删除确认文字"
          value={confirmation}
          onChange={(event) => setConfirmation(event.target.value)}
          placeholder={`请输入「${confirmationText}」`}
          autoComplete="off"
          disabled={saving}
        />
        {error && (
          <FailureNotice
            compact
            failure={failure}
            error={error}
            context={{
              operation: "mutation",
              outcome: mutationOutcome(failure ?? null),
              resource: "agent",
            }}
          />
        )}
        <DialogFooter>
          <Button type="button" variant="outline" disabled={saving} onClick={onClose}>
            取消
          </Button>
          <Button
            type="button"
            variant="destructive"
            loading={saving}
            disabled={!canDelete}
            onClick={() => {
              if (canDelete) onConfirm();
            }}
          >
            <Trash2 aria-hidden="true" />
            {saving ? "删除中…" : "永久删除"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
