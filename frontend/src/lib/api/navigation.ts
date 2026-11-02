import { request } from "./http";
export type SearchItem = { id: string; name: string };
export type NavigationSummary = { agents: number; skills: number; favorites: number };
export async function searchResources(admin: boolean, query: string, signal: AbortSignal) {
  const prefix = admin ? "" : "public/";
  const params = new URLSearchParams({ q: query, offset: "0", limit: "20" });
  const [agents, skills] = await Promise.all([
    request<{ items: SearchItem[] }>(`${prefix}agents?${params}`, { signal }),
    request<{ items: SearchItem[] }>(`${prefix}skills?${params}`, { signal }),
  ]);
  return { agents: agents.items, skills: skills.items };
}
