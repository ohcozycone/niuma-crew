import { FailureNotice } from "@/components/failure/FailureNotice";
import { toFailure, mutationOutcome } from "@/lib/failures/resolve";
import type { Failure } from "@/lib/failures/types";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/Dialog";

export function DeleteToolDialog({
  title,
  description,
  onDelete,
}: {
  title: string;
  description: string;
  onDelete: () => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);
  return (
    <>
      <Button
        type="button"
        variant="destructive-ghost"
        onClick={() => {
          setFailure(null);
          setOpen(true);
        }}
      >
        {title}
      </Button>
      <Dialog
        open={open}
        onOpenChange={(value) => {
          if (!busy) setOpen(value);
        }}
      >
        <DialogContent showCloseButton={!busy}>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
          <FailureNotice
            failure={failure}
            context={{
              operation: "mutation",
              resource: "connection",
              outcome: mutationOutcome(failure),
            }}
          />
          <DialogFooter>
            <Button type="button" variant="outline" disabled={busy} onClick={() => setOpen(false)}>
              取消
            </Button>
            <Button
              type="button"
              variant="destructive"
              loading={busy}
              onClick={async () => {
                setBusy(true);
                setFailure(null);
                try {
                  await onDelete();
                  setOpen(false);
                } catch (e) {
                  setFailure(toFailure(e));
                } finally {
                  setBusy(false);
                }
              }}
            >
              {busy ? "正在删除…" : "确认删除"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
