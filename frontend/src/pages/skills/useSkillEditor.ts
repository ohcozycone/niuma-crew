import { useParams } from "react-router";
import { useWorkspaceData } from "@/state/workspace/useWorkspaceData";
import { useResource } from "@/state/shared/useResource";
import { useSaveOperation } from "@/state/editing/useSaveOperation";
import type { Skill } from "@/lib/models/skill";

export function useSkillEditor() {
  const data = useWorkspaceData();
  const { id = "" } = useParams();
  const resource = data.skills.detail(id);
  const detail = useResource(resource);
  const operation = useSaveOperation();
  const inaccessible = [401, 403, 404].includes(detail.failure?.status ?? 0);
  return {
    skills: detail.data && !inaccessible ? [detail.data] : [],
    ready: detail.data !== undefined && !inaccessible,
    error: detail.error,
    failure: detail.failure,
    reload: resource.refresh,
    saving: operation.saving,
    mutationError: operation.error,
    mutationFailure: operation.failure,
    clearMutationError: operation.clearError,
    saveSkill: (value: Skill, create: boolean) =>
      operation.run(() => data.skills.save(value, create)),
  };
}
