import { Link } from "react-router";
import { FileText, ArrowUpRight } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Textarea } from "@/components/ui/Textarea";
import { ResourceIcon } from "@/components/common/ResourceIcon";
import { InheritedRules } from "@/components/organization-rules/InheritedRules";
import { EmployeeKnowledge } from "@/components/knowledge/EmployeeKnowledge";

const instructionTemplate = `岗位目标
[填写服务对象，以及希望帮助他们完成什么。]

职责范围
- [填写主要负责的工作。]
- [如有需要，说明不承担的工作。]

工作方式
- [填写完成任务需要的信息及处理步骤。]
- [说明信息不足时如何处理。]
- [如有需要，说明哪些事项交由人工确认。]

交付要求
[填写期望的输出内容、格式和表达方式。]`;

export function AgentInstructions({
  value,
  onChange,
  agentId,
  agentName,
}: {
  value: string;
  onChange: (value: string) => void;
  agentId?: string;
  agentName: string;
}) {
  return (
    <div className="agent-instructions-layout">
      <section className="min-w-0" aria-labelledby="agent-instructions-heading">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 id="agent-instructions-heading" className="type-section">
              <label htmlFor="agent-system-prompt">工作指令</label>
            </h2>
            <p className="type-description mt-1">定义这位员工的职责、工作边界与答复方式。</p>
          </div>
          {!value.trim() && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => onChange(instructionTemplate)}
            >
              <FileText size={16} />
              填入指令模板
            </Button>
          )}
        </div>
        <Textarea
          id="agent-system-prompt"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          maxLength={20000}
          rows={18}
          aria-describedby="prompt-help"
          placeholder="岗位目标\n这位员工帮助谁，解决什么问题？\n\n职责与边界\n哪些工作可以处理，哪些需要交给人工？\n\n工作方式\n资料不足时如何确认，如何组织答案与引用来源？"
          className="min-h-96 resize-y bg-raised p-5 text-sm leading-7 [field-sizing:fixed] max-sm:min-h-80 max-sm:p-4"
        />
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-text-muted">
          <p id="prompt-help">保存配置后生效。具体问题与任务在对话中交代。</p>
          <span className="tabular-nums">{value.length.toLocaleString()} / 20,000 字</span>
        </div>
        <details className="mt-5 border-t border-border pt-4 text-sm">
          <summary className="w-fit cursor-pointer rounded-small text-text-muted hover:text-text">
            怎样写出清楚的工作指令？
          </summary>
          <ul className="mt-3 grid list-disc gap-2 pl-5 text-text-muted leading-6 sm:grid-cols-2">
            <li>写清服务对象与岗位目标。</li>
            <li>明确职责范围和人工确认条件。</li>
            <li>说明缺少信息时如何处理。</li>
            <li>约定答复格式与资料引用要求。</li>
          </ul>
        </details>
      </section>
      <aside className="min-w-0 space-y-5" aria-label="规则与知识资料">
        <Card
          as="section"
          variant="outline"
          radius="panel"
          className="bg-raised p-5"
          aria-label="我的参考知识"
        >
          <h2 className="flex items-center gap-2 type-title">
            <ResourceIcon kind="knowledge" size={18} />
            我的参考知识
          </h2>
          <p className="mt-2 text-xs leading-6 text-text-muted">
            仅影响你使用这位员工时的资料范围，独立保存。
          </p>
          <div className="mt-4">
            <EmployeeKnowledge agentId={agentId} agentName={agentName} />
          </div>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="mt-3 -ml-2"
            render={<Link to="/knowledge" target="_blank" rel="noopener noreferrer" />}
            nativeButton={false}
          >
            管理知识库
            <ArrowUpRight size={14} />
            <span className="sr-only">（新标签页）</span>
          </Button>
        </Card>
        <InheritedRules />
      </aside>
    </div>
  );
}
