/** Failure facts survive transport, state and presentation without owning recovery. */
export type FailureFamily =
  "not-found" | "access" | "connection" | "service" | "waiting" | "configuration";

export type Failure = {
  source: "http" | "network" | "client" | "run";
  status: number | null;
  code: string;
  message: string;
  requestId?: string;
  retryAt?: number;
  issues?: readonly { path: readonly (string | number)[]; message: string }[];
};

export type FailureResource =
  | "agent"
  | "evaluation"
  | "skill"
  | "knowledge"
  | "document"
  | "conversation"
  | "connection"
  | "page";

export type FailureContext = {
  operation: "initial-read" | "refresh" | "mutation" | "subscription" | "render";
  resource?: FailureResource;
  hasUsableData?: boolean;
  outcome?: "rejected" | "unknown";
};

export type FailureAction = {
  label: string;
  kind?: "retry" | "reconcile" | "configure" | "return" | "back";
  href?: string;
  onClick?: () => void | Promise<unknown>;
  disabled?: boolean;
};

export type FailurePresentation = {
  family: FailureFamily;
  title: string;
  description: string;
  status: number | null;
  /** 页面逻辑码可独立于 HTTP 状态，例如 SPA 未知路由的 404。 */
  displayCode: string | null;
  code: string;
  requestId?: string;
  retryAt?: number;
};
