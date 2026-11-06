import { mutationOutcome } from "@/lib/failures/resolve";
import { useFailureState } from "@/state/shared/useFailureState";
import { FailureNotice } from "@/components/failure/FailureNotice";
import { useEffect, useRef, useState } from "react";
import { Paperclip } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Switch } from "@/components/ui/Switch";
import { uploadFile, listConversationFiles, type FileRef } from "@/lib/api/files";

export function ConversationFiles({
  conversationId,
  selected,
  onChange,
  disabled,
  onBusy,
  compact = false,
}: {
  conversationId?: string;
  selected: readonly FileRef[];
  onChange: (files: FileRef[]) => void;
  disabled: boolean;
  onBusy: (busy: boolean) => void;
  compact?: boolean;
}) {
  const [available, setAvailable] = useState<FileRef[]>([]);
  const { failure, setError } = useFailureState();
  const [busy, setBusy] = useState(false);
  const upload = useRef<AbortController | null>(null);
  useEffect(() => () => upload.current?.abort(), []);
  useEffect(() => {
    if (!conversationId) return;
    const controller = new AbortController();
    listConversationFiles(conversationId, controller.signal)
      .then(setAvailable)
      .catch((e) => {
        if (!controller.signal.aborted) setError(e);
      });
    return () => controller.abort();
  }, [conversationId, setError]);
  async function add(file: File) {
    if (busy || disabled) return;
    if (file.size > 10 * 1024 * 1024) {
      setError("单文件最多 10 MiB。");
      return;
    }
    setBusy(true);
    onBusy(true);
    setError("");
    const controller = new AbortController();
    upload.current = controller;
    try {
      const ref = await uploadFile(file, controller.signal);
      if (!controller.signal.aborted) onChange([...selected, ref]);
    } catch (e) {
      if (!controller.signal.aborted) setError(e);
    } finally {
      if (!controller.signal.aborted) {
        setBusy(false);
        onBusy(false);
      }
    }
  }
  return (
    <div className={`${compact ? "" : "mb-3"} min-w-0 space-y-2 text-xs`}>
      <label
        className={`inline-flex min-h-8 cursor-pointer items-center gap-1.5 rounded-control px-2 py-1.5 text-text-muted transition-colors hover:bg-muted focus-within:outline-2 focus-within:outline-focus [@media(pointer:coarse)]:min-h-(--os-target-touch) ${compact ? "" : "border border-border"}`}
      >
        {compact && <Paperclip size={15} aria-hidden="true" />}
        {busy ? "正在上传…" : compact ? "添加文件" : "上传输入文件"}
        <input
          className="sr-only"
          type="file"
          aria-label="上传输入文件"
          disabled={disabled || busy || selected.length >= 16}
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = "";
            if (file) void add(file);
          }}
        />
      </label>
      {selected.map((file) => (
        <div className="flex min-w-0 flex-wrap items-center gap-2" key={file.id}>
          <span className="min-w-0 flex-1 [overflow-wrap:anywhere]">{file.name}</span>
          <Button
            type="button"
            variant="ghost"
            size="xs"
            disabled={disabled || busy}
            onClick={() => onChange(selected.filter((item) => item.id !== file.id))}
          >
            移除
          </Button>
        </div>
      ))}
      {!!available.length && (
        <details>
          <summary>选择本对话已保存的文件</summary>
          <div className="mt-2 space-y-2">
            {available
              .filter((f) => !selected.some((s) => s.id === f.id))
              .map((file) => (
                <label className="flex min-w-0 items-center gap-2" key={file.id}>
                  <Switch
                    checked={false}
                    disabled={disabled || busy || selected.length >= 16}
                    onCheckedChange={() => onChange([...selected, file])}
                  />
                  <span className="min-w-0 [overflow-wrap:anywhere]">{file.name}</span>
                </label>
              ))}
          </div>
        </details>
      )}
      {failure && (
        <FailureNotice
          compact
          failure={failure}
          context={{ operation: "mutation", outcome: mutationOutcome(failure) }}
        />
      )}
    </div>
  );
}
