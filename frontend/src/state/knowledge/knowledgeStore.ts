import * as api from "@/lib/api/knowledge";
import { clientFailure, mutationOutcome, toFailure } from "@/lib/failures/resolve";
import type { Failure } from "@/lib/failures/types";
import { Atom } from "@/state/shared/atom";
import { ResourceCache } from "@/state/shared/resource";
import { KnowledgeUploadQueue } from "./uploadQueue";

type VectorOperation = {
  busy: boolean;
  failure: Failure | null;
  request: { id: string; connectionId: string } | null;
};

/** Identity-scoped API state; originals and indexes never live in the browser cache. */
export class KnowledgeStore {
  private queries = new ResourceCache(24);
  private locks = new Set<string>();
  private disposed = false;
  readonly vectorOperations = new Atom<Record<string, VectorOperation>>({});
  readonly uploads = new KnowledgeUploadQueue(() => this.refresh());
  evidence(run: string, evidence: string, offset = 0) {
    return this.queries.get(
      `knowledge:evidence:${run}:${evidence}:${offset}`,
      (signal) => api.getKnowledgeEvidence(run, evidence, offset, signal),
      ["knowledge"],
      { discardOnMissing: true },
    );
  }
  evidenceReferences(run: string) {
    return this.queries.get(
      `knowledge:evidence:${run}:references`,
      (signal) => (run ? api.listKnowledgeEvidence(run, signal) : Promise.resolve([])),
      ["knowledge"],
      { discardOnMissing: true },
    );
  }
  processing(id: string) {
    return this.queries.get(
      `knowledge:${id}:processing`,
      (signal) => api.listKnowledgeProcessing(id, signal),
      ["knowledge"],
    );
  }
  vectorJobs(id: string) {
    return this.queries.get(
      `knowledge:${id}:vector-jobs`,
      (signal) => api.listKnowledgeVectorJobs(id, signal),
      ["knowledge"],
      {
        discardOnMissing: true,
        accept: (jobs) => {
          const previous = this.vectorJobs(id).getSnapshot().data?.[0];
          if (jobs[0] && (jobs[0].id !== previous?.id || jobs[0].status !== previous?.status)) {
            this.library(id).invalidate();
            this.documents(id).invalidate();
          }
          return jobs;
        },
      },
    );
  }
  libraries() {
    return this.queries.get("knowledge:list", api.listKnowledgeBases, ["knowledge"]);
  }
  library(id: string) {
    return this.queries.get(
      `knowledge:${id}`,
      (signal) => api.getKnowledgeBase(id, signal),
      ["knowledge"],
      { discardOnMissing: true },
    );
  }
  documents(id: string) {
    return this.queries.get(
      `knowledge:${id}:documents`,
      (signal) => api.listKnowledgeDocuments(id, signal),
      ["knowledge"],
    );
  }
  document(kb: string, id: string) {
    return this.queries.get(
      `knowledge:${kb}:document:${id}`,
      (signal) => api.getKnowledgeDocument(kb, id, signal),
      ["knowledge"],
      { discardOnMissing: true },
    );
  }
  preview(kb: string, document: string, rules: api.ChunkingRules, offset: number) {
    return this.queries.get(
      `knowledge:${kb}:preview:${document}:${JSON.stringify(rules)}:${offset}`,
      (signal) => api.previewKnowledgeDocument(kb, document, rules, offset, signal),
      ["knowledge"],
      { discardOnMissing: true },
    );
  }
  embeddingConnections() {
    return this.queries.get("knowledge:embedding-connections", api.listEmbeddingConnections, [
      "knowledge",
    ]);
  }
  search(kb: string, question: string, strategy: "auto" | "bm25" | "vector" | "hybrid" = "auto") {
    return this.queries.get(
      `knowledge:${kb}:search:${strategy}:${question}`,
      (signal) =>
        question ? api.searchKnowledge(kb, question, signal, strategy) : Promise.resolve(null),
      ["knowledge"],
    );
  }
  private async write<T>(key: string, action: () => Promise<T>) {
    if (this.disposed)
      throw clientFailure("workspace_closed", "当前工作台已关闭，请重新打开页面。");
    if (this.locks.has(key)) throw clientFailure("operation_in_progress", "正在处理，请稍候。");
    this.locks.add(key);
    try {
      const value = await action();
      if (!this.disposed) this.queries.invalidate("knowledge");
      return value;
    } finally {
      this.locks.delete(key);
    }
  }
  create = (name: string, description: string, id: string) =>
    this.write("create", () => api.createKnowledgeBase(name, description, id));
  upload = (kb: string, file: File, id: string) =>
    this.write(kb, () => api.uploadKnowledgeDocument(kb, file, id));
  remove = (kb: string, id: string) => this.write(kb, () => api.removeKnowledgeDocument(kb, id));
  importDemo = (kb: string, preset: "travel" | "technical", id: string) =>
    this.write(kb, () => api.importKnowledgeDemo(kb, preset, id));
  private setVectorOperation(kb: string, update: Partial<VectorOperation>) {
    if (this.disposed) return;
    const current = this.vectorOperations.getSnapshot();
    this.vectorOperations.set({
      ...current,
      [kb]: { ...(current[kb] ?? { busy: false, failure: null, request: null }), ...update },
    });
  }
  private async vectorWrite<T>(kb: string, action: () => Promise<T>) {
    if (this.disposed)
      throw clientFailure("workspace_closed", "当前工作台已关闭，请重新打开页面。");
    if (this.vectorOperations.getSnapshot()[kb]?.busy)
      throw clientFailure("operation_in_progress", "正在提交，请稍候。");
    this.setVectorOperation(kb, { busy: true, failure: null });
    try {
      return await this.write(kb, action);
    } catch (error) {
      this.setVectorOperation(kb, { failure: toFailure(error) });
      throw error;
    } finally {
      this.setVectorOperation(kb, { busy: false });
      // A lost submission/cancellation response must be reconciled with server records.
      if (!this.disposed) this.refresh();
    }
  }
  buildVectors = (kb: string, connection: string) =>
    this.vectorWrite(kb, async () => {
      const previous = this.vectorOperations.getSnapshot()[kb]?.request;
      if (
        !previous &&
        this.vectorJobs(kb)
          .getSnapshot()
          .data?.some((job) => job.status === "queued" || job.status === "running")
      )
        throw clientFailure("operation_in_progress", "已有向量任务正在处理，请等待或取消。");
      // Keep the original model and key across navigation and ambiguous transport failures.
      const request = previous ?? { id: crypto.randomUUID(), connectionId: connection };
      this.setVectorOperation(kb, { request });
      try {
        const job = await api.buildKnowledgeVectors(kb, request.connectionId, request.id);
        if (!this.disposed) {
          this.vectorJobs(kb).update((jobs) =>
            [job, ...jobs.filter((item) => item.id !== job.id)].slice(0, 20),
          );
          this.setVectorOperation(kb, { request: null });
        }
        return job;
      } catch (error) {
        if (mutationOutcome(toFailure(error)) === "rejected")
          this.setVectorOperation(kb, { request: null });
        throw error;
      }
    });
  cancelVectors = (kb: string, job: string) =>
    this.vectorWrite(kb, async () => {
      const cancelled = await api.cancelKnowledgeVectorJob(kb, job);
      if (!this.disposed)
        this.vectorJobs(kb).update((jobs) =>
          jobs.map((item) => (item.id === job ? cancelled : item)),
        );
      return cancelled;
    });
  clearVectors = (kb: string) =>
    this.vectorWrite(kb, async () => {
      await api.clearKnowledgeVectors(kb);
      if (!this.disposed) {
        this.vectorJobs(kb).update((jobs) =>
          jobs.map((job) =>
            job.status === "queued" || job.status === "running"
              ? { ...job, status: "cancelled", error: null }
              : job,
          ),
        );
        this.library(kb).update((library) => ({
          ...library,
          vector_status: "not_built",
          vector_connection_id: null,
          vector_connection_name: null,
          vector_chunk_count: 0,
        }));
        this.setVectorOperation(kb, { request: null });
      }
    });
  update = (kb: string, data: api.LibrarySettings) =>
    this.write(kb, () => api.updateKnowledgeBase(kb, data));
  process = (kb: string, request: string, documents: string[], rules: api.ChunkingRules) =>
    this.write(kb, () => api.processKnowledgeDocuments(kb, request, documents, rules));
  cancelProcessing = (kb: string, batch: string) =>
    this.write(kb, () => api.cancelKnowledgeProcessing(kb, batch));
  refresh = () => this.queries.invalidate("knowledge");
  dispose() {
    this.disposed = true;
    this.uploads.dispose();
    this.vectorOperations.set({});
    this.vectorOperations.clear();
    this.queries.dispose();
  }
}
