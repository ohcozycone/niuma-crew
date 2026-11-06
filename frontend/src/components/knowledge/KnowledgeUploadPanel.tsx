import { useEffect } from "react";
import { Link } from "react-router";
import { Upload, X } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { useWorkspaceData } from "@/state/workspace/useWorkspaceData";
import { useAtom } from "@/state/shared/useResource";

const labels = {
  ready: "等待开始上传",
  queued: "排队中",
  uploading: "上传中，等待保存确认…",
  done: "原件已保存 · 待手动处理",
  failed: "上传失败",
  cancelled: "传输已取消，请核对库内是否已保存",
};

/** Non-modal observer: closing the panel never owns or cancels a write. */
export function KnowledgeUploadPanel() {
  const queue = useWorkspaceData().knowledge.uploads;
  const { open, entries } = useAtom(queue.state);
  const pending = entries.filter((e) => ["ready", "queued", "uploading"].includes(e.status)).length;
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (queue.hasPending()) {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [queue]);
  if (!entries.length) return null;
  return (
    <aside
      aria-label="全局上传列表"
      className="fixed bottom-4 right-4 z-40 max-w-[calc(100vw-2rem)]"
    >
      {open ? (
        <section className="w-96 max-w-full rounded-card border border-border bg-surface shadow-popover">
          <div className="flex items-center justify-between gap-3 p-4">
            <h2 className="text-sm font-semibold">文件上传 · {pending} 项待完成</h2>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="收起上传列表"
              onClick={() => queue.setOpen(false)}
            >
              <X size={16} />
            </Button>
          </div>
          <p className="px-4 pb-3 text-xs text-text-muted">
            切换页面或收起列表会继续上传；刷新或关闭浏览器可能中断传输。
          </p>
          <ul className="max-h-64 overflow-y-auto divide-y divide-border px-4" aria-live="polite">
            {entries.map((entry) => (
              <li key={entry.id} className="py-3 text-sm">
                <p className="break-all font-medium">{entry.file.name}</p>
                <Link className="text-xs underline" to={`/knowledge/${entry.kb}`}>
                  {entry.libraryName}
                </Link>
                <p className="mt-1 break-words text-xs text-text-muted">
                  {entry.failure?.message ?? entry.message ?? labels[entry.status]}
                </p>
                <div className="mt-2 flex gap-2">
                  {["ready", "queued", "uploading"].includes(entry.status) && (
                    <Button variant="ghost" size="sm" onClick={() => queue.cancel(entry.id)}>
                      取消
                    </Button>
                  )}
                  {["failed", "cancelled"].includes(entry.status) && (
                    <Button variant="outline" size="sm" onClick={() => queue.retry(entry.id)}>
                      重试上传
                    </Button>
                  )}
                </div>
              </li>
            ))}
          </ul>
          <div className="flex flex-wrap justify-between gap-2 p-4">
            <Button variant="ghost" size="sm" onClick={() => queue.clearFinished()}>
              清理已完成项
            </Button>
            <Button
              size="sm"
              disabled={!entries.some((e) => e.status === "ready")}
              onClick={() => queue.start()}
            >
              开始上传
            </Button>
          </div>
        </section>
      ) : (
        <Button onClick={() => queue.setOpen(true)}>
          <Upload size={16} />
          上传列表{pending ? `（${pending}）` : ""}
        </Button>
      )}
    </aside>
  );
}
