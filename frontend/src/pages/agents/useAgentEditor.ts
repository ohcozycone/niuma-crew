import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router";
import { useWorkspaceData } from "@/state/workspace/useWorkspaceData";
import { useRetainedResource } from "@/state/shared/useResource";
import { useSaveOperation } from "@/state/editing/useSaveOperation";
import * as api from "@/lib/api/agents";
import { request } from "@/lib/api/http";
import type { Agent } from "@/lib/models/agent";
import { toFailure } from "@/lib/failures/resolve";
import type { Failure } from "@/lib/failures/types";

type Detail = {
  owner: object;
  id: string;
  agent?: Agent;
  publicAgent?: api.PublicAgent;
  failure: Failure | null;
};
export function useAgentEditor() {
  const data = useWorkspaceData();
  const [params] = useSearchParams();
  const { id = "" } = useParams();
  const operation = useSaveOperation();
  const [refresh, setRefresh] = useState(0);
  const [detail, setDetail] = useState<Detail | null>(null);
  const query = new URLSearchParams({
    offset: params.get("skill_offset") ?? "0",
    limit: "20",
    q: params.get("skill_q") ?? "",
  });
  if (params.get("skill_category") && params.get("skill_category") !== "all")
    query.set("category", params.get("skill_category")!);
  const resource = data.skills.page(query);
  const skills = useRetainedResource(resource, data);
  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const value =
          id && id !== "new"
            ? data.admin
              ? await api.getAgent(id, controller.signal)
              : await request<api.PublicAgent>(`public/agents/${id}`, { signal: controller.signal })
            : undefined;
        if (!controller.signal.aborted)
          setDetail({
            owner: data,
            id,
            ...(data.admin
              ? { agent: value as Agent | undefined }
              : { publicAgent: value as api.PublicAgent | undefined }),
            failure: null,
          });
      } catch (failure) {
        if (!controller.signal.aborted) {
          const reason = toFailure(failure);
          // 只保留同身份同资源的成功详情；明确不存在/撤权不能继续显示旧内容。
          setDetail((previous) => ({
            ...(previous?.owner === data &&
            previous.id === id &&
            ![401, 403, 404].includes(reason?.status ?? 0)
              ? previous
              : {}),
            owner: data,
            id,
            failure: reason,
          }));
        }
      }
    }
    void load();
    return () => controller.abort();
  }, [data, id, refresh]);
  const current = detail?.owner === data && detail.id === id ? detail : null;
  return {
    agents: current?.agent ? [current.agent] : [],
    publicAgents: current?.publicAgent ? [current.publicAgent] : [],
    skills: skills.data?.items ?? [],
    skillTotal: skills.data?.total ?? 0,
    ready:
      current !== null &&
      (!current.failure || !!current.agent || !!current.publicAgent) &&
      skills.data !== undefined,
    error: current?.failure?.message || skills.error,
    failure: current?.failure || skills.failure,
    reload: () => {
      setRefresh((value) => value + 1);
      resource.refresh();
    },
    saving: operation.saving,
    mutationError: operation.error,
    mutationFailure: operation.failure,
    clearMutationError: operation.clearError,
    saveAgent: (value: Agent, create: boolean) =>
      operation.run(() => data.agents.save(value, create)),
    deleteAgent: (id: string) =>
      operation.run(async () => {
        try {
          await data.agents.remove(id);
          return true;
        } catch (failure) {
          operation.setError(failure);
          return false;
        }
      }),
  };
}
