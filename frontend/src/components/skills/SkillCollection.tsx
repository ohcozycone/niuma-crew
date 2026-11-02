import { EmptyState } from "@/components/common/EmptyState";
import { SearchInput } from "@/components/common/SearchInput";
import { Search } from "lucide-react";

import { SelectField } from "@/components/ui/SelectField";
import { type SkillListItem } from "@/lib/models/skill";
import { SkillCard } from "./SkillCard";
import styles from "./skillCollectionStyles";

type SkillCollectionProps = {
  skills: SkillListItem[];
  onEdit?: (skill: SkillListItem) => void;
  onDelete?: (skill: SkillListItem) => void;
  query: string;
  onQueryChange: (query: string) => void;
  category: string;
  onCategoryChange: (category: string) => void;
  expandedId: string | null;
  onExpandedChange: (id: string | null) => void;
} & (
  | {
      selectedIds: string[];
      onSelectionChange: (id: string, selected: boolean) => void;
      usageCounts?: never;
      onUsage?: never;
    }
  | {
      selectedIds?: never;
      onSelectionChange?: never;
      usageCounts: Record<string, number>;
      onUsage: (id: string) => void;
    }
);

export function SkillCollection({
  skills,
  onEdit,
  onDelete,
  query,
  onQueryChange,
  category,
  onCategoryChange,
  expandedId,
  onExpandedChange,
  selectedIds,
  onSelectionChange,
  usageCounts,
  onUsage,
}: SkillCollectionProps) {
  const categories = [
    ...new Set([
      ...(category === "all" ? [] : [category]),
      ...skills.map((skill) => skill.category),
    ]),
  ].filter(Boolean);
  const visible = skills.filter(
    (skill) =>
      `${skill.name} ${skill.description}`.toLowerCase().includes(query.trim().toLowerCase()) &&
      (category === "all" || category === skill.category),
  );
  return (
    <div>
      <div className={styles.toolbar}>
        <SearchInput
          label="搜索技能"
          onChange={(nextValue) => onQueryChange(nextValue)}
          placeholder="搜索技能名称或用途…"
          value={query}
          onKeyDown={(event) => {
            if (event.key === "Enter") event.preventDefault();
          }}
          className="flex-[1_1_200px] max-w-90 w-full"
        />
        <SelectField
          options={[
            { value: "all", label: "全部分类" },
            ...categories.map((value) => ({ value, label: value })),
          ]}
          value={category}
          onValueChange={onCategoryChange}
          aria-label="按技能分类"
          className="w-fit"
        />
      </div>
      <div className={styles.grid}>
        {visible.map((skill) => (
          <SkillCard
            key={skill.id}
            skill={skill}
            onEdit={onEdit ? () => onEdit(skill) : undefined}
            onDelete={onDelete ? () => onDelete(skill) : undefined}
            expanded={expandedId === skill.id}
            onExpand={() => onExpandedChange(expandedId === skill.id ? null : skill.id)}
            selected={selectedIds?.includes(skill.id)}
            onSelectionChange={
              onSelectionChange ? (selected) => onSelectionChange(skill.id, selected) : undefined
            }
            usageCount={usageCounts?.[skill.id]}
            onUsage={onUsage ? () => onUsage(skill.id) : undefined}
          />
        ))}
      </div>
      {!visible.length && (
        <EmptyState
          headingLevel={false}
          text={skills.length ? "没有找到相关技能" : "还没有技能，可先在技能库创建"}
          description={null}
          icon={<Search size={24} aria-hidden="true" />}
          onReset={() => {
            onQueryChange("");
            onCategoryChange("all");
          }}
          density="compact"
        />
      )}
    </div>
  );
}
