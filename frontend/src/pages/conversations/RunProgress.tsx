import { useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  BookOpen,
  Brain,
  CircleAlert,
  CircleStop,
  ClipboardCheck,
  Clock,
  FileText,
  MessageCircleCheck,
  Wrench,
} from "lucide-react";
import { TraceDescription, TraceIcon, TraceTitle } from "@/components/ui/Trace";
import { isActive, type Reply } from "@/lib/api/conversations";
import { cn } from "@/lib/utils";

const phases = {
  queued: { icon: "waiting", label: "排队中" },
  running: { icon: "brain", label: "执行中" },
  thinking: { icon: "brain", label: "思考中" },
  generating: { icon: "brain", label: "生成回复中" },
  tool: { icon: "tool", label: "调用工具中" },
  knowledge: { icon: "knowledge", label: "读取知识中" },
  skill: { icon: "skill", label: "加载技能中" },
  validation: { icon: "validation", label: "校验结果中" },
  saving: { icon: "waiting", label: "正在保存回复" },
  unsaved: { icon: "error", label: "回复未保存" },
  succeeded: { icon: "complete", label: "已完成" },
  failed: { icon: "error", label: "执行失败" },
  cancelling: { icon: "stopped", label: "正在停止" },
  cancelled: { icon: "stopped", label: "已取消" },
  interrupted: { icon: "error", label: "已中断" },
} as const;
type Phase = keyof typeof phases;

function currentPhase(run: Reply): Phase {
  if (run.acceptance === "failed") return "unsaved";
  if (run.acceptance === "pending") return "saving";
  if (run.status !== "running") return run.status;
  // 模型与多个工具可能同时保留 running；任何在途工具都应显示工具阶段。
  if (run.steps.some((step) => step.status === "running" && step.kind === "tool_call"))
    return "tool";
  const step = run.steps.findLast((item) => item.status === "running");
  if (step?.kind === "model_call")
    return step.output_text && step.safe_details.has_tool_calls !== true
      ? "generating"
      : "thinking";
  if (step?.kind === "knowledge") return "knowledge";
  if (step?.kind === "skill_activation") return "skill";
  if (step?.kind === "validation") return "validation";
  return "running";
}

const icons = {
  brain: Brain,
  tool: Wrench,
  complete: MessageCircleCheck,
  error: CircleAlert,
  stopped: CircleStop,
  waiting: Clock,
  knowledge: BookOpen,
  skill: FileText,
  validation: ClipboardCheck,
};
type IconName = keyof typeof icons;

function PhaseIcon({ name }: { name: IconName }) {
  const element = useRef<HTMLSpanElement>(null);
  const previous = useRef(name);
  useLayoutEffect(() => {
    const oldName = previous.current;
    previous.current = name;
    if (oldName === name || window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    const container = element.current;
    if (!container) return;
    const nodes = container.querySelectorAll<HTMLElement>("[data-phase-icon]");
    const duration = Number.parseFloat(
      getComputedStyle(container).getPropertyValue("--os-motion-swap"),
    );
    if (!Number.isFinite(duration)) return;
    const animations: Animation[] = [];
    nodes.forEach((node) => {
      if (typeof node.animate !== "function") return;
      if (node.dataset.phaseIcon === oldName) {
        animations.push(
          node.animate(
            [
              { opacity: 1, transform: "translateX(0)", filter: "blur(0)" },
              { opacity: 0, transform: "translateX(-2px)", filter: "blur(.7px)" },
            ],
            { duration: duration * 0.45, easing: "ease-out" },
          ),
        );
      }
      if (node.dataset.phaseIcon === name) {
        animations.push(
          node.animate(
            [
              { opacity: 0, transform: "translateX(3px)", filter: "blur(.7px)" },
              { opacity: 1, transform: "translateX(0)", filter: "blur(0)" },
            ],
            {
              duration,
              delay: duration * 0.16,
              easing: "cubic-bezier(.16,1,.3,1)",
              fill: "backwards",
            },
          ),
        );
      }
    });
    return () => animations.forEach((animation) => animation.cancel());
  }, [name]);
  return (
    <TraceIcon ref={element} className="relative size-5 overflow-hidden">
      {Object.entries(icons).map(([key, Icon]) => (
        <span
          key={key}
          data-phase-icon={key}
          data-current={key === name || undefined}
          className={cn(
            "absolute inset-0 flex items-center justify-center [&_svg]:stroke-[1.7]",
            key === name ? "opacity-100" : "opacity-0",
          )}
        >
          <Icon />
        </span>
      ))}
    </TraceIcon>
  );
}

/** 只消费已有动作；短暂阶段稳定后呈现，终态不等待动画或防抖。 */
export function RunProgress({ run, total }: { run: Reply; total: number }) {
  const target = currentPhase(run);
  const [settled, setSettled] = useState(target);
  const [now, setNow] = useState(Date.now);
  const active = isActive(run.status);
  const smooth =
    run.status === "running" && run.acceptance !== "pending" && run.acceptance !== "failed";
  useEffect(() => {
    if (!smooth) return;
    const timer = setTimeout(() => setSettled(target), 120);
    return () => clearTimeout(timer);
  }, [target, smooth]);
  useEffect(() => {
    if (!active || !run.started_at) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [active, run.started_at]);
  const phase = phases[smooth ? settled : target];
  const end = run.finished_at ? Date.parse(run.finished_at) : now;
  const seconds = run.started_at
    ? Math.max(0, Math.floor((end - Date.parse(run.started_at)) / 1000))
    : null;
  const duration =
    seconds === null
      ? ""
      : seconds >= 60
        ? `${Math.floor(seconds / 60)}分${seconds % 60}秒`
        : `${seconds}秒`;
  return (
    <>
      <PhaseIcon name={phase.icon} />
      <TraceTitle aria-live="polite">{phase.label}</TraceTitle>
      <TraceDescription>
        {duration ? `用时 ${duration} · ` : ""}
        {total} 项记录
      </TraceDescription>
    </>
  );
}
