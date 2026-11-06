import { mutationOutcome, clientFailure } from "@/lib/failures/resolve";
import { useFailureState } from "@/state/shared/useFailureState";
import { FailureNotice } from "@/components/failure/FailureNotice";
import { useWorkspaceData } from "@/state/workspace/useWorkspaceData";
import { Card } from "@/components/ui/Card";
import { useEffect, useState, type RefObject } from "react";
import { Button } from "@/components/ui/Button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/Dialog";
import { skillLibrary, type SkillSyncResult } from "@/lib/api/skills";

const statuses = {
  added: "已添加",
  updated: "已更新",
  unchanged: "无变化",
  missing: "来源缺失",
  error: "未同步",
};
export function SkillLibrarySync({
  open,
  onClose,
  returnFocus,
}: {
  open: boolean;
  onClose: () => void;
  returnFocus?: RefObject<HTMLButtonElement | null>;
}) {
  const data = useWorkspaceData();
  const [directory, setDirectory] = useState("");
  const [result, setResult] = useState<SkillSyncResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const { failure, setError } = useFailureState();
  useEffect(() => {
    if (!open) return;
    let active = true;
    setLoading(true);
    setError("");
    setResult(null);
    setDirectory("");
    void skillLibrary()
      .then((value) => {
        if (active) setDirectory(value.directory);
      })
      .catch((error) => {
        if (active) setError(error);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [open, setError]);
  async function sync() {
    setBusy(true);
    setError("");
    try {
      const value = await data.skills.syncDirectory();
      setResult(value);
      setDirectory(value.directory);
    } catch (error) {
      setError(error);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog
      open={open}
      onOpenChange={(value) => {
        if (!value && !busy) onClose();
      }}
    >
      <DialogContent size="wide" showCloseButton={!busy} finalFocus={returnFocus}>
        <DialogHeader>
          <DialogTitle>从服务器目录同步技能</DialogTitle>
          <DialogDescription>
            扫描运行后端的机器上的指定目录，添加或更新标准 Skill
            包。保留别名和员工装配，不执行脚本；源文件缺失时保留已发布内容。
          </DialogDescription>
        </DialogHeader>
        {loading ? (
          <p role="status">正在读取目录设置…</p>
        ) : (
          <Card as="p" variant="muted" radius="control" className="break-all p-3 text-sm">
            {directory || "未能读取目录"}
          </Card>
        )}
        {failure && (
          <FailureNotice
            failure={failure}
            context={{ operation: "mutation", outcome: mutationOutcome(failure) }}
          />
        )}
        {result && (
          <div role="status" className="space-y-3">
            <p className="text-sm">
              同步完成：新增 {result.items.filter((item) => item.status === "added").length}，更新{" "}
              {result.items.filter((item) => item.status === "updated").length}，未同步{" "}
              {result.items.filter((item) => item.status === "error").length}。
            </p>
            {!result.items.length && (
              <p className="type-caption">
                没有发现技能。请将包含 SKILL.md 的技能目录安装到上方位置后重试。
              </p>
            )}
            <ul className="max-h-72 space-y-3 overflow-y-auto">
              {result.items.map((item, index) => (
                <li key={`${item.name}:${index}`} className="border-b border-border pb-3 text-sm">
                  <div className="flex items-start justify-between gap-3">
                    <span className="break-all">{item.name}</span>
                    <span
                      className={
                        item.status === "error"
                          ? "shrink-0 text-danger"
                          : "shrink-0 text-text-muted"
                      }
                    >
                      {statuses[item.status]}
                    </span>
                  </div>
                  {item.message &&
                    (item.status === "error" || item.status === "missing" ? (
                      <FailureNotice
                        compact
                        failure={clientFailure(
                          item.status === "missing" ? "skill_source_missing" : "skill_sync_failed",
                          item.message,
                        )}
                        context={{
                          operation: "mutation",
                          resource: "skill",
                          outcome: "rejected",
                        }}
                      />
                    ) : (
                      <p className="mt-1 text-text-muted">{item.message}</p>
                    ))}
                </li>
              ))}
            </ul>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" disabled={busy} onClick={onClose}>
            关闭
          </Button>
          <Button disabled={busy || loading || !directory} onClick={() => void sync()}>
            {busy ? "正在同步…" : result ? "再次同步" : "同步到能力库"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
