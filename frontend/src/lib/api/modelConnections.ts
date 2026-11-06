import { request } from "./http";

export type ModelPreset = {
  id: string;
  name: string;
  provider: string;
  protocol: string;
  base_url: string;
  default_model_id: string;
  description: string;
  capability?: "chat" | "embedding";
};
export type ModelConnection = {
  enabled: boolean;
  capability: "chat" | "embedding";
  config_revision: number;
  credential_revision: number;
  id: string;
  name: string;
  preset_id: string;
  provider: string;
  protocol: string;
  base_url: string;
  model_id: string;
  has_api_key: boolean;
  agents: { id: string; name: string }[];
  created_at: string;
  updated_at: string;
};
export type ConnectionInput = {
  name: string;
  model_id: string;
  api_key: string;
  preset_id: string;
  enabled?: boolean;
};
export function connectionInput(value: ConnectionInput, editing: boolean) {
  return {
    enabled: value.enabled ?? true,
    name: value.name.trim(),
    model_id: value.model_id.trim(),
    ...(!editing ? { preset_id: value.preset_id } : {}),
    ...(!editing || value.api_key.trim() ? { api_key: value.api_key.trim() } : {}),
  };
}
export const loadModelConnections = (signal?: AbortSignal) =>
  all<ModelConnection>("model-connections", signal);
export const loadModelPresets = (signal?: AbortSignal) =>
  request<ModelPreset[]>("model-presets", { signal });
export const saveModelConnection = (input: ConnectionInput, editing?: ModelConnection) =>
  request<ModelConnection>(editing ? `model-connections/${editing.id}` : "model-connections", {
    method: editing ? "PATCH" : "POST",
    body: JSON.stringify({
      ...connectionInput(input, Boolean(editing)),
      ...(editing
        ? {
            expected_config_revision: editing.config_revision,
            expected_credential_revision: editing.credential_revision,
          }
        : {}),
    }),
  });
export const deleteModelConnection = (id: string) =>
  request<void>(`model-connections/${id}`, { method: "DELETE" });
export const testModelConnection = (id: string) =>
  request<{ ok: boolean; message: string }>(`model-connections/${id}/test`, {
    method: "POST",
    body: "{}",
  });

export async function all<T>(resource: string, signal?: AbortSignal): Promise<T[]> {
  const items: T[] = [];
  let offset = 0;
  while (true) {
    const page = await request<Page<T>>(`${resource}?offset=${offset}&limit=100`, { signal });
    items.push(...page.items);
    offset += page.items.length;
    if (offset >= page.total || !page.items.length) break;
  }
  return items;
}
type Page<T> = { items: T[]; total: number; offset: number; limit: number };
