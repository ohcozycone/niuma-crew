export type Skill = {
  id: string;
  skillMd?: string;
  protocolName?: string;
  sourcePath?: string | null;
  sourceMissing?: boolean;
  files?: SkillPackageFile[];
  packageFiles?: SkillPackageInput[];
  configurationLoaded?: boolean;
  revision?: number;
  assignmentCount?: number;
  active?: boolean;
  configurationSchema?: Record<string, unknown>;
  name: string;
  category: string;
  description: string;
  instructions?: string;
  input: string;
  output: string;
  example: string;
};

export type SkillSummary = Omit<
  Skill,
  "input" | "output" | "example" | "instructions" | "configurationSchema" | "configurationLoaded"
>;
export type SkillListItem = SkillSummary &
  Partial<
    Pick<
      Skill,
      | "input"
      | "output"
      | "example"
      | "instructions"
      | "configurationSchema"
      | "configurationLoaded"
    >
  >;

export type SkillPackageFile = {
  path: string;
  content_hash: string;
  size: number;
  media_type: string;
  is_text: boolean;
};
export type SkillPackageInput = { path: string; content?: string; content_base64?: string };
