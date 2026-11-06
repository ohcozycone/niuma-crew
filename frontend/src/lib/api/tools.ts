import { request } from "./http";

export type ToolDescriptor = {
  name: string;
  description: string;
  descriptor_hash: string;
  input_schema?: Record<string, unknown>;
};
export type ToolConnection = {
  id: string;
  service_id: string | null;
  account_scope: "personal" | "shared";
  created_by_user_id: string | null;
  tool_annotations: Record<string, CatalogAnnotation>;
  annotations_revision: number;
  name: string;
  kind: "native" | "mcp_http" | "mcp_stdio";
  provider_key: string | null;
  auth_type: string;
  public_config: Record<string, unknown>;
  enabled: boolean;
  has_credential: boolean;
  oauth_status?: "disconnected" | "connected" | "reauth_required" | null;
  config_revision: number;
  credential_revision: number;
  catalog_revision: number;
  approved_catalog: ToolDescriptor[];
  approved_instructions?: string;
  discovery_candidate: { hash: string; tools: ToolDescriptor[]; instructions?: string } | null;
};
export type ToolGrant = {
  id?: string;
  account_mode?: "shared" | "personal";
  connection_id: string;
  tools: { name: string; descriptor_hash: string }[];
  scope_policy: Record<string, unknown>;
  enabled: boolean;
};
export const listToolConnections = (signal?: AbortSignal) =>
  request<ToolConnection[]>("tool-connections", { signal });
export const createToolConnection = (data: unknown) =>
  request<ToolConnection>("tool-connections", { method: "POST", body: JSON.stringify(data) });
export const patchToolConnection = (connection: ToolConnection, changes: unknown) =>
  request<ToolConnection>(`tool-connections/${connection.id}`, {
    method: "PATCH",
    body: JSON.stringify({
      expected_config_revision: connection.config_revision,
      expected_credential_revision: connection.credential_revision,
      ...(changes as object),
    }),
  });
export const deleteToolConnection = (connection: ToolConnection) =>
  request<void>(
    `tool-connections/${connection.id}?expected_config_revision=${connection.config_revision}&expected_credential_revision=${connection.credential_revision}`,
    { method: "DELETE" },
  );
export const discoverTools = (id: string) =>
  request<ToolConnection>(`tool-connections/${id}/discover`, { method: "POST", body: "{}" });

export type OAuthSession = {
  id: string;
  status:
    | "preparing"
    | "awaiting_consent"
    | "exchanging"
    | "succeeded"
    | "failed"
    | "cancelled"
    | "expired";
  authorization_url: string | null;
  error_code: string | null;
  error_message: string | null;
};
export const startToolOAuth = (connection: ToolConnection) =>
  request<OAuthSession>(`tool-connections/${connection.id}/oauth/sessions`, {
    method: "POST",
    body: JSON.stringify({
      expected_config_revision: connection.config_revision,
      expected_credential_revision: connection.credential_revision,
    }),
  });
export const readToolOAuth = (id: string, session: string, signal?: AbortSignal) =>
  request<OAuthSession>(`tool-connections/${id}/oauth/sessions/${session}`, { signal });
export const cancelToolOAuth = (id: string, session: string) =>
  request<void>(`tool-connections/${id}/oauth/sessions/${session}`, { method: "DELETE" });
export const disconnectToolOAuth = (connection: ToolConnection) =>
  request<ToolConnection>(`tool-connections/${connection.id}/oauth/disconnect`, {
    method: "POST",
    body: JSON.stringify({
      expected_config_revision: connection.config_revision,
      expected_credential_revision: connection.credential_revision,
    }),
  });
export const approveTools = (connection: ToolConnection) =>
  request<ToolConnection>(`tool-connections/${connection.id}/approve`, {
    method: "POST",
    body: JSON.stringify({
      expected_config_revision: connection.config_revision,
      expected_catalog_revision: connection.catalog_revision,
      candidate_hash: connection.discovery_candidate?.hash,
    }),
  });
export type McpService = {
  id: string;
  name: string;
  description: string;
  transport: "http" | "stdio";
  url: string | null;
  command: string | null;
  args: string[];
  env_keys: string[];
  input_fields?: McpInputField[];
  owner_user_id: string | null;
  revision: number;
  enabled: boolean;
};
export type McpInputField = {
  name: string;
  description: string;
  is_required: boolean;
  is_secret: boolean;
};
export type CatalogAnnotation = { display_name: string; note: string };
export type PersonalToolBinding = {
  creator_default?: boolean;
  grant_id: string;
  service_id: string;
  service_name: string;
  account_mode: "shared" | "personal";
  tools: { name: string; descriptor_hash: string }[];
  connection_id: string | null;
  connected: boolean;
  revision: number;
};
export const listMcpServices = (signal?: AbortSignal) =>
  request<McpService[]>("mcp-services", { signal });
export type McpServiceInput = {
  name: string;
  description: string;
  transport?: "http" | "stdio";
  url?: string | null;
  command?: string | null;
  args?: string[];
  env_keys?: string[];
  input_fields?: McpInputField[];
};
export const createMcpService = (data: McpServiceInput) =>
  request<McpService>("mcp-services", { method: "POST", body: JSON.stringify(data) });
export const patchMcpService = (
  service: McpService,
  changes: { enabled?: boolean; name?: string; description?: string; env_keys?: string[] },
) =>
  request<McpService>(`mcp-services/${service.id}`, {
    method: "PATCH",
    body: JSON.stringify({ expected_revision: service.revision, ...changes }),
  });
export const deleteMcpService = (service: McpService) =>
  request<void>(`mcp-services/${service.id}?expected_revision=${service.revision}`, {
    method: "DELETE",
  });
export const previewMcpConfig = (configuration: string) =>
  request<{
    warnings?: string[];
    entries: {
      name: string;
      transport: "http" | "stdio";
      url: string | null;
      command: string | null;
      args: string[];
      env_keys: string[];
      auth_type: string;
      header_name: string | null;
      has_credential: boolean;
      description?: string;
      input_fields?: McpInputField[];
    }[];
  }>("mcp-config/preview", { method: "POST", body: JSON.stringify({ configuration }) });
export const saveAnnotations = (
  connection: ToolConnection,
  annotations: Record<string, CatalogAnnotation>,
) =>
  request<ToolConnection>(`tool-connections/${connection.id}/annotations`, {
    method: "PUT",
    body: JSON.stringify({
      expected_annotations_revision: connection.annotations_revision,
      annotations,
    }),
  });
export const discardCatalog = (connection: ToolConnection) =>
  request<ToolConnection>(`tool-connections/${connection.id}/discard`, {
    method: "POST",
    body: JSON.stringify({
      expected_config_revision: connection.config_revision,
      expected_catalog_revision: connection.catalog_revision,
      candidate_hash: connection.discovery_candidate?.hash,
    }),
  });
export const myToolBindings = (agent: string, signal?: AbortSignal) =>
  request<{ items: PersonalToolBinding[] }>(`agents/${agent}/my-tool-bindings`, { signal });
export const bindMyTool = (
  agent: string,
  binding: PersonalToolBinding,
  connection: string | null,
) =>
  request<{ items: PersonalToolBinding[] }>(
    `agents/${agent}/my-tool-bindings/${binding.grant_id}`,
    {
      method: "PUT",
      body: JSON.stringify({ connection_id: connection, expected_revision: binding.revision }),
    },
  );
export function toolLabel(connection: ToolConnection, name: string) {
  const alias = connection.tool_annotations?.[name]?.display_name.trim();
  return alias ? `${alias}（${name}）` : name;
}

export type ToolGrantInput = {
  connection_id: string;
  tools: string[];
  expected_descriptors: Record<string, string>;
  scope_policy: Record<string, unknown>;
  enabled: boolean;
  account_mode: "personal" | "shared";
};

export const toolCapabilities = (signal?: AbortSignal) =>
  request<{
    stdio_enabled: boolean;
    stdio_registration_allowed: boolean;
    max_stdio_processes: number;
  }>("tool-capabilities", { signal });
