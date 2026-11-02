import type { Failure } from "@/lib/failures/types";
// Public display contract shared by the agent module and its showcase.
export type AgentPresentation = {
  id: string;
  name: string;
  subtitle: string;
  description: string;
  avatarId: string;
  favorite: boolean;
  skillCount: number;
  toolCount: number;
  knowledgeBaseCount: number;
  availability: "available" | "paused" | "unconfigured";
};
export type AgentAction = "open" | "skills" | "assign" | "edit" | "favorite" | "toggle";
export type AgentCardProps = {
  agent: AgentPresentation;
  readOnly?: boolean;
  preview?: boolean;
  usable?: boolean;
  statusPending?: boolean;
  statusError?: string;
  statusFailure?: Failure | null;
  statusRetry?: () => void;
  onAction?: (id: string, action: AgentAction) => void;
};
