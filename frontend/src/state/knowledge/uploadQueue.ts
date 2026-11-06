import { uploadKnowledgeDocument } from "@/lib/api/knowledge";
import { clientFailure, toFailure } from "@/lib/failures/resolve";
import type { Failure } from "@/lib/failures/types";
import { Atom } from "@/state/shared/atom";

export type UploadEntry = {
  id: string;
  kb: string;
  libraryName: string;
  file: File;
  status: "ready" | "queued" | "uploading" | "done" | "failed" | "cancelled";
  failure: Failure | null;
  message?: string;
};

/** Workspace writes survive route subscribers; identity disposal alone tears them down. */
export class KnowledgeUploadQueue {
  readonly state = new Atom<{ open: boolean; entries: UploadEntry[] }>({
    open: false,
    entries: [],
  });
  private busy = false;
  private disposed = false;
  private current: { id: string; controller: AbortController } | null = null;
  constructor(private readonly changed: () => void) {}
  private update(id: string, patch: Partial<UploadEntry>) {
    if (this.disposed) return;
    const state = this.state.getSnapshot();
    this.state.set({
      ...state,
      entries: state.entries.map((e) => (e.id === id ? { ...e, ...patch } : e)),
    });
  }
  setOpen = (open: boolean) => this.state.set({ ...this.state.getSnapshot(), open });
  add(kb: string, libraryName: string, files: File[]) {
    if (this.disposed) return;
    const state = this.state.getSnapshot();
    if (state.entries.length + files.length > 200)
      throw clientFailure("upload_queue_full", "上传列表最多保留200项，请先清理已完成项。");
    this.state.set({
      open: true,
      entries: [
        ...state.entries,
        ...files.map((file): UploadEntry => ({
          id: crypto.randomUUID(),
          kb,
          libraryName,
          file,
          status: "ready",
          failure: null,
        })),
      ],
    });
  }
  hasPending = () =>
    this.state
      .getSnapshot()
      .entries.some((e) => ["ready", "queued", "uploading"].includes(e.status));
  start(kb?: string) {
    const state = this.state.getSnapshot();
    this.state.set({
      ...state,
      open: true,
      entries: state.entries.map((e) =>
        e.status === "ready" && (!kb || e.kb === kb) ? { ...e, status: "queued" as const } : e,
      ),
    });
    void this.pump();
  }
  retry(id: string) {
    this.update(id, { status: "queued", failure: null });
    void this.pump();
  }
  cancel(id: string) {
    this.update(id, { status: "cancelled", failure: null });
    if (this.current?.id === id) this.current.controller.abort();
  }
  clearFinished() {
    const state = this.state.getSnapshot();
    this.state.set({
      ...state,
      entries: state.entries.filter((e) => !["done", "cancelled"].includes(e.status)),
    });
  }
  private async pump() {
    if (this.busy || this.disposed) return;
    const entry = this.state.getSnapshot().entries.find((e) => e.status === "queued");
    if (!entry) return;
    this.busy = true;
    const controller = new AbortController();
    this.current = { id: entry.id, controller };
    this.update(entry.id, { status: "uploading" });
    try {
      const result = await uploadKnowledgeDocument(
        entry.kb,
        entry.file,
        entry.id,
        controller.signal,
      );
      if (!this.disposed) {
        this.update(entry.id, {
          status: "done",
          message: result.keyword_ready ? "原件已保存 · 关键词可用" : "原件已保存 · 待手动处理",
        });
        this.changed();
      }
    } catch (error) {
      if (!this.disposed && !controller.signal.aborted)
        this.update(entry.id, { status: "failed", failure: toFailure(error) });
    } finally {
      this.current = null;
      this.busy = false;
      if (!this.disposed) void this.pump();
    }
  }
  dispose() {
    this.disposed = true;
    this.current?.controller.abort();
    this.state.set({ open: false, entries: [] });
    this.state.clear();
  }
}
