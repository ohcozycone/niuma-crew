import { request } from "./http";

export type FileRef = {
  id: string;
  name: string;
  size: number;
  content_hash: string;
  media_type: string;
  purpose: string;
};
export const uploadFile = (file: File, signal?: AbortSignal) =>
  request<FileRef>(`files?name=${encodeURIComponent(file.name)}`, {
    method: "POST",
    headers: { "Content-Type": file.type || "application/octet-stream" },
    body: file,
    signal,
  });
export const listConversationFiles = (id: string, signal?: AbortSignal) =>
  request<FileRef[]>(`conversations/${id}/files`, { signal });
export const fileDownloadUrl = (conversationId: string, fileId: string) =>
  `/api/conversations/${encodeURIComponent(conversationId)}/files/${encodeURIComponent(fileId)}`;
