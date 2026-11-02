import { FormField } from "@/components/common/FormField";
import { Card } from "@/components/ui/Card";
import { Textarea } from "@/components/ui/Textarea";
import { Switch } from "@/components/ui/Switch";
import type { SkillListItem } from "@/lib/models/skill";

type Settings = Record<string, { enabled: boolean; parameters: string }>;
export function SkillAssignmentConfiguration({
  ids,
  skills,
  settings,
  onChange,
}: {
  ids: string[];
  skills: SkillListItem[];
  settings: Settings;
  onChange: (settings: Settings) => void;
}) {
  return (
    <div className="mt-5 space-y-4">
      {ids.map((id) => {
        const skill = skills.find((s) => s.id === id);
        const value = settings[id] ?? { enabled: true, parameters: "{}" };
        const update = (patch: Partial<typeof value>) =>
          onChange({ ...settings, [id]: { ...value, ...patch } });
        return (
          <Card as="div" variant="outline" radius="panel" className="p-4 space-y-3" key={id}>
            <label className="flex items-center gap-2">
              <Switch checked={value.enabled} onCheckedChange={(enabled) => update({ enabled })} />
              {skill?.name ?? "已装配技能"}
            </label>
            <FormField
              htmlFor={`skill-parameters-${id}`}
              label={<>装配参数（JSON 对象，不含密钥）</>}
            >
              <Textarea
                id={`skill-parameters-${id}`}
                rows={3}
                value={value.parameters}
                onChange={(e) => update({ parameters: e.target.value })}
              />
            </FormField>
          </Card>
        );
      })}
    </div>
  );
}
