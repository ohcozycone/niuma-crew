import { request } from "./http";

export type EmployeeKnowledgeSettings = {
  agent_id: string;
  revision: number;
  knowledge_base_ids: string[];
  mode: "on_demand" | "always";
  strategy: "auto" | "bm25" | "vector" | "hybrid";
  top_k: number;
  libraries: KnowledgeBase[];
};
export type EmployeeKnowledgeInput = Pick<
  EmployeeKnowledgeSettings,
  "knowledge_base_ids" | "mode" | "strategy" | "top_k"
> & {
  expected_revision: number;
};
export const getEmployeeKnowledge = (agentId: string, signal?: AbortSignal) =>
  request<EmployeeKnowledgeSettings>(`knowledge-bases/employee-bindings/${agentId}`, { signal });
export const saveEmployeeKnowledge = (agentId: string, data: EmployeeKnowledgeInput) =>
  request<EmployeeKnowledgeSettings>(`knowledge-bases/employee-bindings/${agentId}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });

export type KnowledgeBase = {
  id: string;
  name: string;
  description: string;
  document_count: number;
  chunk_count: number;
  updated_at: string;
  search_mode: "bm25";
  vector_status: "not_built" | "ready" | "partial" | "outdated" | "unavailable";
  vector_connection_id: string | null;
  vector_connection_name: string | null;
  vector_chunk_count: number;
  revision?: number;
  chunk_size?: number | null;
  chunk_overlap?: number | null;
  min_section_chars?: number | null;
  effective_chunk_size?: number;
  effective_chunk_overlap?: number;
  effective_min_section_chars?: number;
  keyword_document_count?: number;
  processing_document_count?: number;
};
export type KnowledgeDocument = {
  id: string;
  title: string;
  filename: string;
  size: number;
  content_hash: string;
  version: string;
  chunk_count: number;
  created_at: string;
  processing_state?: "pending" | "queued" | "processing" | "ready" | "failed" | "interrupted";
  processing_error?: string | null;
  keyword_ready?: boolean;
  vector_ready?: boolean;
  processing_rules?: Partial<ChunkingRules> & { split_version?: number };
};
export type KnowledgeChunk = {
  id: string;
  document_id: string;
  document_version: string;
  title: string;
  locator: string;
  start: number;
  end: number;
  text: string;
  spans?: { block_id: string; start: number; end: number }[];
};
export type DocumentDetail = KnowledgeDocument & {
  document: { text: string; version: string; parser: string } | null;
  chunks: KnowledgeChunk[];
};
export type CitationPreview = {
  title: string;
  locator: string;
  excerpt: string;
  has_more: boolean;
  source_url: string;
};
export const getKnowledgeCitation = (
  library: string,
  document: string,
  chunk: string,
  signal?: AbortSignal,
) =>
  request<CitationPreview>(`knowledge-bases/${library}/documents/${document}/chunks/${chunk}`, {
    signal,
  });
export type SearchResult = {
  knowledge_base_id: string;
  strategy: "bm25" | "vector" | "hybrid";
  hits: {
    rank: number;
    score: number | null;
    score_kind: "fts5_bm25_lower_better" | "cosine_distance_lower_better" | "rank_only";
    chunk: KnowledgeChunk;
  }[];
};
export const listKnowledgeBases = (signal?: AbortSignal) =>
  request<KnowledgeBase[]>("knowledge-bases", { signal });
export const getKnowledgeBase = (id: string, signal?: AbortSignal) =>
  request<KnowledgeBase>(`knowledge-bases/${id}`, { signal });
export const createKnowledgeBase = (name: string, description: string, clientRequestId: string) =>
  request<KnowledgeBase>("knowledge-bases", {
    method: "POST",
    body: JSON.stringify({ name, description, client_request_id: clientRequestId }),
  });
export const listKnowledgeDocuments = (id: string, signal?: AbortSignal) =>
  request<KnowledgeDocument[]>(`knowledge-bases/${id}/documents`, { signal });
export const getKnowledgeDocument = (kb: string, id: string, signal?: AbortSignal) =>
  request<DocumentDetail>(`knowledge-bases/${kb}/documents/${id}`, { signal });
export const uploadKnowledgeDocument = (
  kb: string,
  file: File,
  requestId: string,
  signal?: AbortSignal,
) =>
  request<KnowledgeDocument>(
    `knowledge-bases/${kb}/documents?${new URLSearchParams({ name: file.name, client_request_id: requestId })}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body: file,
      signal,
    },
  );
export const removeKnowledgeDocument = (kb: string, id: string) =>
  request<void>(`knowledge-bases/${kb}/documents/${id}`, { method: "DELETE" });
export const searchKnowledge = (
  kb: string,
  question: string,
  signal?: AbortSignal,
  strategy: "bm25" | "vector" | "hybrid" = "bm25",
) =>
  request<SearchResult>(`knowledge-bases/${kb}/search`, {
    method: "POST",
    body: JSON.stringify({ question, strategy }),
    signal,
  });

export type EmbeddingConnection = { id: string; name: string; model_id: string };
export const listEmbeddingConnections = (signal?: AbortSignal) =>
  request<EmbeddingConnection[]>("knowledge-bases/embedding-connections", { signal });
export const buildKnowledgeVectors = (kb: string, connectionId: string) =>
  request<KnowledgeBase>(`knowledge-bases/${kb}/vector-index`, {
    method: "POST",
    body: JSON.stringify({ model_connection_id: connectionId }),
  });
export const clearKnowledgeVectors = (kb: string) =>
  request<void>(`knowledge-bases/${kb}/vector-index`, { method: "DELETE" });
export const originalKnowledgeUrl = (kb: string, id: string) =>
  `/api/knowledge-bases/${kb}/documents/${id}/original`;

export const importKnowledgeDemo = (kb: string, preset: "travel" | "technical", id: string) =>
  request<KnowledgeDocument[]>(`knowledge-bases/${kb}/demo-import`, {
    method: "POST",
    body: JSON.stringify({ preset, client_request_id: id }),
  });

export type LibrarySettings = {
  expected_revision: number;
  name: string;
  description: string;
  chunk_size: number | null;
  chunk_overlap: number | null;
  min_section_chars?: number | null;
};
export type ChunkingRules = {
  chunk_size: number;
  chunk_overlap: number;
  min_section_chars: number;
};
export type ChunkPreview = {
  document_id: string;
  filename: string;
  rules: ChunkingRules;
  chunk_count: number;
  short_chunk_count: number;
  merged_chunk_count: number;
  min_length: number;
  max_length: number;
  offset: number;
  has_more: boolean;
  chunks: KnowledgeChunk[];
};
export const previewKnowledgeDocument = (
  kb: string,
  document: string,
  rules: ChunkingRules,
  offset: number,
  signal?: AbortSignal,
) =>
  request<ChunkPreview>(`knowledge-bases/${kb}/documents/${document}/preview`, {
    method: "POST",
    body: JSON.stringify({ rules, offset }),
    signal,
  });
export const updateKnowledgeBase = (kb: string, data: LibrarySettings) =>
  request<KnowledgeBase>(`knowledge-bases/${kb}`, { method: "PATCH", body: JSON.stringify(data) });
export type ProcessingBatch = {
  id: string;
  status: string;
  rules: {
    chunk_size: number;
    chunk_overlap: number;
    min_section_chars?: number;
    split_version?: number;
  };
  created_at: string;
  items: {
    id: string;
    document_id: string;
    filename: string;
    status: string;
    error: string | null;
  }[];
};
export const listKnowledgeProcessing = (kb: string, signal?: AbortSignal) =>
  request<ProcessingBatch[]>(`knowledge-bases/${kb}/processing`, { signal });
export const processKnowledgeDocuments = (
  kb: string,
  clientRequestId: string,
  documentIds?: string[],
  reprocess = false,
  rules?: ChunkingRules,
) =>
  request<ProcessingBatch>(`knowledge-bases/${kb}/processing`, {
    method: "POST",
    body: JSON.stringify({
      client_request_id: clientRequestId,
      document_ids: documentIds,
      reprocess,
      rules,
    }),
  });
export const cancelKnowledgeProcessing = (kb: string, batchId: string) =>
  request<ProcessingBatch>(`knowledge-bases/${kb}/processing/${batchId}/cancel`, {
    method: "POST",
    body: "{}",
  });
