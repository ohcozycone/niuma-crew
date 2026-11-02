import {
  Brain,
  CircleHelp,
  FileText,
  LibraryBig,
  KeyRound,
  ListChecks,
  MessagesSquare,
  Network,
  Plug,
  Puzzle,
  ShieldCheck,
  UsersRound,
  Wrench,
  type LucideProps,
} from "lucide-react";
import { cn } from "@/lib/utils";

// Object identity stays stable across discovery, configuration, selection and execution.
export const resourceIdentity = {
  employees: { label: "数字员工", icon: UsersRound },
  capabilities: { label: "能力库", icon: Plug },
  skill: { label: "技能", icon: Puzzle },
  mcp: { label: "MCP", icon: Plug },
  "native-tool": { label: "内置工具", icon: Wrench },
  tool: { label: "工具", icon: Wrench },
  connection: { label: "账号连接", icon: KeyRound },
  brain: { label: "大脑", icon: Brain },
  embedding: { label: "向量模型", icon: Network },
  knowledge: { label: "知识库", icon: LibraryBig },
  document: { label: "文档", icon: FileText },
  instructions: { label: "工作指令", icon: ListChecks },
  rules: { label: "公司规章制度", icon: ShieldCheck },
  conversation: { label: "对话", icon: MessagesSquare },
  unknown: { label: "未知类型", icon: CircleHelp },
} as const;

export type ResourceKind = keyof typeof resourceIdentity;
export type CapabilityKind = "skill" | "mcp" | "native-tool";

export function capabilityResourceKind(kind: string): CapabilityKind | "unknown" {
  if (kind === "skill") return "skill";
  if (kind === "native") return "native-tool";
  if (kind === "mcp_http" || kind === "mcp_stdio" || kind === "mcp") return "mcp";
  return "unknown";
}

export function ResourceIcon({
  kind,
  className,
  size = 16,
  ...props
}: LucideProps & { kind: ResourceKind }) {
  const Icon = resourceIdentity[kind].icon;
  return (
    <Icon
      aria-hidden="true"
      {...props}
      size={size}
      data-resource-kind={kind}
      className={cn("shrink-0", className)}
    />
  );
}

export function ResourceType({
  kind,
  className,
  showIcon = true,
}: {
  kind: ResourceKind;
  className?: string;
  showIcon?: boolean;
}) {
  return (
    <span className={cn("type-caption inline-flex items-center gap-1.5", className)}>
      {showIcon && <ResourceIcon kind={kind} />}
      {resourceIdentity[kind].label}
    </span>
  );
}
