import { useState } from "react";
import { Check, Plus, Save, Settings2, Trash2, Unlink } from "lucide-react";
import {
  ResourceIcon,
  resourceIdentity,
  type ResourceKind,
} from "@/components/common/ResourceIcon";
import { ConfirmActionDialog } from "@/components/common/ConfirmActionDialog";
import { Button } from "@/components/ui/Button";

const kinds: ResourceKind[] = [
  "skill",
  "mcp",
  "native-tool",
  "capabilities",
  "connection",
  "brain",
  "embedding",
  "knowledge",
  "document",
  "instructions",
  "rules",
  "conversation",
];
const actions = [
  { icon: Plus, label: "添加" },
  { icon: Settings2, label: "配置" },
  { icon: Check, label: "完成并更新草稿" },
  { icon: Save, label: "保存" },
  { icon: Unlink, label: "移除关系" },
  { icon: Trash2, label: "永久删除" },
];

export function ResourceLanguageExamples({ notify }: { notify: (message: string) => void }) {
  const [confirming, setConfirming] = useState(false);
  return (
    <section id="resource-language" aria-label="对象与动作语言">
      <h3 className="mb-2 font-semibold">对象与动作语言</h3>
      <p className="mb-5 text-sm leading-relaxed text-text-muted">
        同一对象跨列表、装配、选择与执行保留相同图形和名称；状态使用独立文字表达。
      </p>
      <div className="grid gap-x-6 sm:grid-cols-2 lg:grid-cols-3">
        {kinds.map((kind) => (
          <div key={kind} className="flex items-center gap-3 border-b border-border py-3 text-sm">
            <ResourceIcon kind={kind} size={20} />
            <span>{resourceIdentity[kind].label}</span>
          </div>
        ))}
      </div>
      <div className="mt-5 flex flex-wrap gap-x-6 gap-y-3 text-sm">
        {actions.map(({ icon: Icon, label }) => (
          <span key={label} className="inline-flex items-center gap-2">
            <Icon size={16} aria-hidden="true" />
            {label}
          </span>
        ))}
      </div>
      <div className="mt-5 flex flex-wrap items-center gap-3">
        <Button variant="outline" onClick={() => setConfirming(true)}>
          <Unlink />
          查看移除确认样板
        </Button>
        <span className="type-caption">
          取消不修改内容；只有明确确认后执行。此样板不操作业务数据。
        </span>
      </div>
      <ConfirmActionDialog
        open={confirming}
        onOpenChange={setConfirming}
        title="移除「资料整理」的装配？"
        description="只从当前员工草稿中移除，不删除技能定义。保存员工配置后生效。"
        confirmLabel="确认移除"
        onConfirm={() => {
          setConfirming(false);
          notify("已确认移除样板，业务数据未改变");
        }}
      />
    </section>
  );
}
