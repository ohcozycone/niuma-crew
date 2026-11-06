import { request } from "./http";
import type { Skill, SkillSummary, SkillPackageFile, SkillPackageInput } from "@/lib/models/skill";

export type SkillDTO = {
  source_path?: string | null;
  source_missing?: boolean;
  skill_md?: string;
  protocol_name?: string;
  files?: SkillPackageFile[];
  assignment_count: number;
  revision: number;
  is_active: boolean;
  configuration_schema: Record<string, unknown>;
  id: string;
  name: string;
  category: string;
  description: string;
  instructions: string;
  input_description: string;
  output_description: string;
  example: string;
  created_at: string;
  updated_at: string;
};
type Page<T> = { items: T[]; total: number; offset: number; limit: number };
export function fromSkill(data: SkillDTO): Skill {
  return {
    configurationLoaded: true,
    skillMd: data.skill_md,
    protocolName: data.protocol_name,
    sourcePath: data.source_path,
    sourceMissing: data.source_missing,
    files: data.files,
    id: data.id,
    name: data.name,
    category: data.category,
    description: data.description,
    instructions: data.instructions,
    revision: data.revision,
    active: data.is_active,
    configurationSchema: data.configuration_schema,
    assignmentCount: data.assignment_count,
    input: data.input_description,
    output: data.output_description,
    example: data.example,
  };
}
export function skillInput(data: Skill, create = false) {
  return {
    ...(!create ? { expected_revision: data.revision } : {}),
    is_active: data.active ?? true,
    configuration_schema: data.configurationSchema ?? {},
    ...skillFields(data),
    ...(data.skillMd !== undefined ? { skill_md: data.skillMd } : {}),
    ...(data.packageFiles !== undefined ? { package_files: data.packageFiles } : {}),
  };
}
function skillFields(data: Skill) {
  return {
    name: data.name.trim() || null,
    category: data.category,
    description: data.description,
    instructions: data.instructions ?? "",
    input_description: data.input,
    output_description: data.output,
    example: data.example,
  };
}
export async function saveSkill(skill: Skill, create: boolean) {
  if (!create && !skill.configurationLoaded) throw new Error("请先读取技能详情，再保存配置。");
  return fromSkill(
    await request<SkillDTO>(create ? "skills" : `skills/${skill.id}`, {
      method: create ? "POST" : "PATCH",
      body: JSON.stringify(skillInput(skill, create)),
    }),
  );
}
export const deleteSkill = (id: string) => request<void>(`skills/${id}`, { method: "DELETE" });
export type SkillSyncResult = {
  directory: string;
  items: {
    name: string;
    status: "added" | "updated" | "unchanged" | "missing" | "error";
    skill_id?: string;
    message: string;
  }[];
};
export const skillLibrary = () => request<{ directory: string }>("skills/library");
export const syncSkillLibrary = () =>
  request<SkillSyncResult>("skills/sync", { method: "POST", body: "{}" });
export type SkillSummaryDTO = Pick<
  SkillDTO,
  "id" | "name" | "category" | "description" | "is_active" | "revision" | "updated_at"
> & { assignment_count: number };
export function fromSkillSummary(data: SkillSummaryDTO): SkillSummary {
  return {
    id: data.id,
    name: data.name,
    category: data.category,
    description: data.description,
    active: data.is_active,
    revision: data.revision,
    assignmentCount: data.assignment_count,
  };
}
export const skillPage = (query: URLSearchParams, signal?: AbortSignal) =>
  request<Page<SkillSummaryDTO>>(`skills?${query}`, { signal });
export const getSkill = async (id: string, signal?: AbortSignal) =>
  fromSkill(await request<SkillDTO>(`skills/${id}`, { signal }));
export type PublicSkill = {
  assignment_count?: number;
  id: string;
  name: string;
  category: string;
  description: string;
  input_description: string;
  output_description: string;
  example: string;
};

export function fromPublicSkill(item: PublicSkill): Skill {
  return {
    assignmentCount: item.assignment_count ?? 0,
    id: item.id,
    name: item.name,
    category: item.category,
    description: item.description,
    input: item.input_description,
    output: item.output_description,
    example: item.example,
  };
}

export const readSkillFile = (id: string, path: string, signal?: AbortSignal) =>
  request<SkillPackageInput & { media_type: string; is_text: boolean }>(
    `skills/${id}/files?${new URLSearchParams({ path })}`,
    { signal },
  );
export type SkillImportPreview = {
  name: string;
  description: string;
  protocol_name: string;
  skill_md: string;
  files: SkillPackageFile[];
  warnings: string[];
};
export const previewSkillPackage = (archive: string) =>
  request<SkillImportPreview>("skills/import/preview", {
    method: "POST",
    body: JSON.stringify({ archive_base64: archive }),
  });
export const importSkillPackage = async (archive: string, name?: string, category?: string) =>
  fromSkill(
    await request<SkillDTO>("skills/import", {
      method: "POST",
      body: JSON.stringify({ archive_base64: archive, name, category }),
    }),
  );
