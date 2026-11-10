import { ResourceIcon } from "@/components/common/ResourceIcon";
import { Card, CardFooter } from "@/components/ui/Card";
import { useId } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { type SkillListItem } from "@/lib/models/skill";
import styles from "./skillCardStyles";

export function SkillCard({
  skill,
  expanded,
  onExpand,
  selected,
  onSelectionChange,
  usageCount,
  onUsage,
  onEdit,
  onDelete,
}: {
  skill: SkillListItem;
  expanded: boolean;
  onExpand: () => void;
  selected?: boolean;
  onSelectionChange?: (selected: boolean) => void;
  usageCount?: number;
  onUsage?: () => void;
  onEdit?: () => void;
  onDelete?: () => void;
}) {
  const detailsId = useId();
  return (
    <Card
      as="article"
      className="@container/resource-card [&[data-selected]]:border-focus"
      data-selected={selected || undefined}
      aria-label={skill.name}
    >
      <div className={styles.card}>
        <div className={styles.top}>
          <span className={styles.icon}>
            <ResourceIcon kind="skill" size={18} aria-hidden="true" />
          </span>
          <Badge variant="secondary">{skill.category}</Badge>
        </div>
        <h3 className={styles.title}>
          <button
            type="button"
            onClick={onExpand}
            aria-expanded={expanded}
            aria-controls={detailsId}
          >
            {skill.name}
          </button>
        </h3>
        <p className={styles.description}>{skill.description}</p>
        <CardFooter className={styles.footer}>
          {onSelectionChange ? (
            <label className={styles.selection}>
              <input
                type="checkbox"
                checked={Boolean(selected)}
                onChange={(event) => onSelectionChange(event.target.checked)}
                aria-label={`装配${skill.name}`}
              />
              {selected ? "已选择" : "装配此技能"}
            </label>
          ) : (
            <button type="button" onClick={onUsage} disabled={!onUsage} className={styles.usage}>
              {usageCount ?? 0} 位员工使用
            </button>
          )}
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={onExpand}
            aria-expanded={expanded}
            aria-controls={detailsId}
            aria-label={`${expanded ? "收起" : "查看"}${skill.name}详情`}
          >
            {expanded ? "收起详情" : "查看详情"}
            {expanded ? <ChevronUp /> : <ChevronDown />}
          </Button>
        </CardFooter>
        <dl className={styles.details} id={detailsId} hidden={!expanded}>
          <div>
            <dt>所需输入</dt>
            <dd>{skill.input}</dd>
          </div>
          <div>
            <dt>交付内容</dt>
            <dd>{skill.output}</dd>
          </div>
          <div>
            <dt>示例任务</dt>
            <dd>{skill.example}</dd>
          </div>
          {skill.instructions && (
            <div>
              <dt>工作指引</dt>
              <dd className="whitespace-pre-wrap">{skill.instructions}</dd>
            </div>
          )}
        </dl>
        {(onEdit || onDelete) && (
          <div className="flex flex-wrap gap-2 pt-3">
            {onEdit && (
              <Button variant="outline" size="sm" onClick={onEdit} aria-label={`编辑${skill.name}`}>
                编辑
              </Button>
            )}
            {onDelete && (
              <Button variant="ghost" size="sm" onClick={onDelete} aria-label={`删除${skill.name}`}>
                删除
              </Button>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}
