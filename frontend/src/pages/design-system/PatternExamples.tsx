import { EmptyState } from "@/components/common/EmptyState";
import { Card } from "@/components/ui/Card";
import { SearchInput } from "@/components/common/SearchInput";
import { useState } from "react";
import { useNavigate } from "react-router";
import { Users, Plus, Check, CircleAlert } from "lucide-react";
import { Button } from "@/components/ui/Button";

import { CapabilityCard } from "@/components/skills/CapabilityCard";
import { SkillCard } from "@/components/skills/SkillCard";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/Dialog";
import { Switch } from "@/components/ui/Switch";
import { initialAgents as fixtureAgents } from "@/pages/design-system/fixtures/agents";
import { toAgentPresentation } from "@/pages/agents";
import { AgentCard } from "@/pages/agents";
import type { AgentAction } from "@/pages/agents";
import { useThemeValues } from "./useThemeValues";
import { styles } from "./previewStyles";
import { FailureExamples } from "./FailureExamples";
import { ResourceLanguageExamples } from "./ResourceLanguageExamples";
const sampleAgents = fixtureAgents.map((agent) => ({
  ...agent,
  modelConnectionId: "demo-connection",
}));
const initialAgents = sampleAgents
  .filter((agent) => agent.id === "travel" || agent.id === "knowledge")
  .map(toAgentPresentation);
export function PatternExamples({ notify: setNotice }: { notify: (message: string) => void }) {
  const navigate = useNavigate();
  const { number } = useThemeValues();
  const [agents, setAgents] = useState(initialAgents);
  const [query, setQuery] = useState("");
  const [longText, setLongText] = useState(false);
  const [panel, setPanel] = useState(false);
  const [retried, setRetried] = useState(false);
  const [skillExpanded, setSkillExpanded] = useState(false);
  const [skillSelected, setSkillSelected] = useState(false);
  function action(id: string, next: AgentAction) {
    const agent = agents.find((item) => item.id === id);
    if (!agent) return;
    if (next === "favorite" || next === "toggle") {
      setAgents((current) =>
        current.map((item) =>
          item.id !== id
            ? item
            : next === "favorite"
              ? { ...item, favorite: !item.favorite }
              : {
                  ...item,
                  availability:
                    item.availability === "paused"
                      ? toAgentPresentation(sampleAgents.find((agent) => agent.id === item.id)!)
                          .availability
                      : "paused",
                },
        ),
      );
      setNotice(
        next === "favorite"
          ? "样板的收藏状态已更新"
          : agent.availability === "paused"
            ? "已恢复这位员工接单"
            : "员工已暂停接单，可随时恢复",
      );
      return;
    }
    // Catalogue examples have fixture IDs; never send them to persisted agent routes.
    navigate(next === "assign" ? "/" : "/?agent=new");
  }
  const visible = agents.filter((item) => `${item.name} ${item.subtitle}`.includes(query.trim()));
  return (
    <div className={"space-y-8"}>
      <ResourceLanguageExamples notify={setNotice} />
      <section id="agents" aria-label="员工卡片样板">
        <h3 className={"mb-2 font-semibold"}>员工卡片</h3>
        <p className={"mb-5 text-sm leading-relaxed text-text-muted"}>
          列表与配置预览共用正式组件，收藏与启停示例只影响本页。
        </p>
        <div className={styles.agentToolbar}>
          <SearchInput
            label="搜索样板员工"
            onChange={(nextValue) => setQuery(nextValue)}
            placeholder="搜索员工…"
            value={query}
            className="w-full sm:w-[260px]"
          />
          <div className={styles.toolbarActions}>
            <label className={styles.switchLine} htmlFor="long-text">
              长文本
              <Switch id="long-text" checked={longText} onCheckedChange={setLongText} />
            </label>
          </div>
        </div>
        <div className={styles.agents}>
          {visible.map((agent) => (
            <AgentCard
              key={agent.id}
              agent={
                longText
                  ? {
                      ...agent,
                      name: `${agent.name} · 跨团队协作与综合事务支持`,
                      description: agent.description.repeat(5),
                    }
                  : agent
              }
              onAction={action}
            />
          ))}
        </div>
        {!visible.length && (
          <EmptyState
            boxed
            headingLevel={3}
            text="没有找到员工"
            description="试试其他名称，或清空搜索条件。"
            icon={<Users size={24} aria-hidden="true" />}
            onReset={() => setQuery("")}
            resetLabel="清空搜索"
            density="compact"
          />
        )}
        <div className={styles.annotation}>
          <span>列表与配置预览共用 AgentCard</span>
          <span>
            人物与文字间距 {number("--os-card-gap")}px / 窄屏 {number("--os-card-gap-sm")}px
          </span>
          <span>技能 / 工具操作 / 知识库分别计数，零数量合并或隐藏</span>
          <span>描述最多两行，保留等高占位</span>
          <span>头像与背板略缩小，保留舒展留白与左右内边距</span>
          <span>边框保持稳定，阴影轻微变化</span>
        </div>
      </section>
      <section id="capability-patterns" aria-label="能力与配置面板样板">
        <h3 className="mb-2 font-semibold">能力卡片与配置面板</h3>
        <p className="mb-5 text-sm text-text-muted">
          复用正式能力卡片和侧边 Dialog。此处仅展示交互，不保存业务配置。
        </p>
        <p className="mb-4 text-sm text-text-muted">
          员工、能力与技能详情卡片共用 Card 表面、半像素边框和阴影；业务内容与操作各自保留。
        </p>
        <div className="employee-grid">
          <CapabilityCard
            configurationHref="/skills"
            item={{
              id: "sample-mcp",
              name: "网页调研",
              description: "搜索公开网页并提取文本，为员工提供可追溯的信息来源。",
              kind: "mcp_http",
              enabled: true,
            }}
          />
          <CapabilityCard
            configurationHref="/skills"
            item={{
              id: "sample-skill",
              name: "资料整理与长名称样板",
              description: "按工作指引整理材料。此说明用于验证两行等高摘要和窄屏排版。",
              kind: "skill",
              enabled: false,
            }}
          />
          <SkillCard
            skill={{
              id: "sample-skill-detail",
              name: "技能详情与装配样板",
              category: "资料整理",
              description: "保留详情展开与选择状态，外观使用同一个卡片底座。",
              input: "待整理的资料",
              output: "结构清晰的说明",
              example: "整理本周资料",
            }}
            expanded={skillExpanded}
            onExpand={() => setSkillExpanded((value) => !value)}
            selected={skillSelected}
            onSelectionChange={setSkillSelected}
          />
        </div>
        <div className="mt-4 flex items-center gap-4">
          <a
            className="inline-flex items-center gap-1 text-sm underline underline-offset-4"
            href="/brains"
            target="_blank"
            rel="noopener noreferrer"
          >
            去配置大脑（新标签页）
          </a>
          <Button variant="outline" onClick={() => setPanel(true)}>
            打开配置面板样板
          </Button>
        </div>
        <Dialog open={panel} onOpenChange={setPanel}>
          <DialogContent layout="side">
            <DialogHeader>
              <DialogTitle>能力配置样板</DialogTitle>
              <DialogDescription>面板完成更新员工草稿，员工页统一保存才生效。</DialogDescription>
            </DialogHeader>
            <div className="focus-gutter min-h-0 overflow-auto text-sm text-text-muted">
              正式页面根据已确认目录展示工具，或按 Skill 自身声明展示参数，不生成通用业务字段。
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setPanel(false)}>
                取消
              </Button>
              <Button
                onClick={() => {
                  setPanel(false);
                  setNotice("样板已完成，未保存业务配置");
                }}
              >
                完成样板
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </section>
      <section id="feedback" aria-label="反馈样板">
        <h3 className={"mb-2 font-semibold"}>状态与反馈</h3>
        <p className={"mb-5 text-sm text-text-muted"}>用文字说明状态，提供明确的下一步操作。</p>
        <div className={styles.statuses}>
          {[
            ["success", "可对话", "bg-success-bg text-success"],
            ["info", "执行中", "bg-info-bg text-info"],
            ["warning", "等待确认", "bg-warning-bg text-warning"],
            ["danger", "执行失败", "bg-danger-bg text-danger"],
          ].map(([tone, label, toneClass]) => (
            <span key={tone} className={toneClass}>
              <i />
              {label}
            </span>
          ))}
        </div>
        <div className={styles.feedbackGrid}>
          <Card
            as="div"
            variant="outline"
            radius="panel"
            className={styles.stateCard}
            aria-busy="true"
            aria-label="加载状态示例"
          >
            <div className={styles.skeleton} />
            <div className={styles.skeletonLine} />
            <div className={styles.skeletonLine} />
            <strong>正在读取员工</strong>
            <p>保留布局位置，避免内容跳动。</p>
          </Card>
          <Card as="div" variant="outline" radius="panel" className={styles.stateCard}>
            <Users size={24} />
            <strong>还没有数字员工</strong>
            <p>先定义一个职责明确的员工。</p>
            <Button size="sm" variant="outline" onClick={() => navigate("/?agent=new")}>
              <Plus />
              打开员工配置
            </Button>
          </Card>
          <Card as="div" variant="outline" radius="panel" className={styles.stateCard}>
            {retried ? <Check size={24} /> : <CircleAlert size={24} />}
            <strong>{retried ? "重试反馈已展示" : "员工列表读取失败"}</strong>
            <p>{retried ? "这是状态示例，不会请求后端。" : "保留筛选条件，提供原地重试。"}</p>
            <Button size="sm" variant="outline" onClick={() => setRetried((value) => !value)}>
              {retried ? "重置示例" : "重试示例"}
            </Button>
          </Card>
        </div>
        <FailureExamples />
      </section>
    </div>
  );
}
