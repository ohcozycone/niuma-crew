import * as api from "@/lib/api/knowledge";
import { clientFailure } from "@/lib/failures/resolve";
import { ResourceCache } from "@/state/shared/resource";
import { KnowledgeUploadQueue } from "./uploadQueue";

/** Identity-scoped API state; originals and indexes never live in the browser cache. */
export class KnowledgeStore {
  private queries = new ResourceCache(24);
  private locks = new Set<string>();
  private disposed = false;
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
  buildVectors = (kb: string, connection: string) =>
    this.write(kb, () => api.buildKnowledgeVectors(kb, connection));
  clearVectors = (kb: string) => this.write(kb, () => api.clearKnowledgeVectors(kb));
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
    this.queries.dispose();
  }
}
