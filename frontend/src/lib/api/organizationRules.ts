import { request } from "./http";

export type OrganizationRules = {
  instructions: string;
  revision: number;
  updated_at: string;
};

export function loadOrganizationRules(signal?: AbortSignal) {
  return request<OrganizationRules>("organization-rules", { signal });
}

export function saveOrganizationRules(instructions: string, revision: number) {
  return request<OrganizationRules>("organization-rules", {
    method: "PUT",
    body: JSON.stringify({ instructions, revision }),
  });
}
