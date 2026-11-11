import { useState } from "react";
import { Download, Trash2 } from "lucide-react";
import { originalKnowledgeUrl, type KnowledgeDocument } from "@/lib/api/knowledge";
import { Button } from "@/components/ui/Button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/Dialog";
import { useWorkspaceData } from "@/state/workspace/useWorkspaceData";
import { useResource } from "@/state/shared/useResource";
import { useIdentity } from "@/state/auth/useIdentity";
import { useSaveOperation } from "@/state/editing/useSaveOperation";
import { ConfirmActionDialog } from "@/components/common/ConfirmActionDialog";
import { FailureNotice } from "@/components/failure/FailureNotice";
import { mutationOutcome } from "@/lib/failures/resolve";
import { KnowledgeFeedback } from "./KnowledgeLibraries";
import { KnowledgeDocumentContent, type KnowledgeDocumentView } from "./KnowledgeDocumentContent";

export function KnowledgeDocumentDialog({
  kb,
  document,
  view,
  returnFocus,
  onClose,
}: {
  kb: string;
  document: KnowledgeDocument;
  view: KnowledgeDocumentView;
  returnFocus: HTMLElement;
  onClose: () => void;
}) {
  const store = useWorkspaceData().knowledge;
  const resource = store.document(kb, document.id);
  const state = useResource(resource);
  const detail = state.data;
  const writable = useIdentity().permissions.includes("knowledge:manage");
  const [confirm, setConfirm] = useState(false);
  const save = useSaveOperation();
  async function remove() {
    try {
      await save.run(() => store.remove(kb, document.id));
      onClose();
    } catch (error) {
      save.setError(error);
    }
  }
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent
        size="wide"
        finalFocus={() => returnFocus}
        className="h-[calc(100dvh-var(--os-space-4)*2)] grid-rows-[auto_minmax(0,1fr)] gap-0 overflow-hidden p-0"
      >
        <DialogHeader className="gap-3 border-b-0 p-4 pr-12 pb-3 sm:p-6 sm:pr-12 sm:pb-3">
          <DialogTitle>{detail?.title ?? document.title}</DialogTitle>
          <DialogDescription className="break-words text-xs [overflow-wrap:anywhere]">
            {detail?.filename ?? document.filename} ·{" "}
            {((detail?.size ?? document.size) / 1024).toFixed(1)} KiB
            {detail?.version && ` · 原文快照 ${detail.version.slice(0, 12)}`}
          </DialogDescription>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              nativeButton={false}
              role="link"
              render={<a href={originalKnowledgeUrl(kb, document.id)} download />}
            >
              <Download size={14} />
              下载原件
            </Button>
            {writable && detail && (
              <Button size="sm" variant="ghost" onClick={() => setConfirm(true)}>
                <Trash2 size={14} />
                移除文档
              </Button>
            )}
          </div>
        </DialogHeader>
        <div className="flex min-h-0 min-w-0 flex-col overflow-hidden">
          <div className="min-h-0 shrink-0 overflow-y-auto px-4 sm:px-6">
            <KnowledgeFeedback
              shape="document"
              resource="document"
              failure={state.failure}
              loading={state.loading}
              hasUsableData={detail !== undefined}
              retry={() => resource.invalidate()}
            />
          </div>
          {detail && (
            <KnowledgeDocumentContent document={detail} initialView={view} className="flex-1" />
          )}
        </div>
        <ConfirmActionDialog
          open={confirm}
          onOpenChange={setConfirm}
          title={`移除「${detail?.title ?? document.title}」？`}
          description="从当前知识库移除文档及其检索片段，确认后立即生效。其他文档继续保留。"
          confirmLabel="确认移除"
          busy={save.saving}
          onConfirm={() => void remove()}
        >
          <FailureNotice
            failure={save.failure}
            context={{
              operation: "mutation",
              resource: "knowledge",
              outcome: mutationOutcome(save.failure),
            }}
          />
        </ConfirmActionDialog>
      </DialogContent>
    </Dialog>
  );
}
