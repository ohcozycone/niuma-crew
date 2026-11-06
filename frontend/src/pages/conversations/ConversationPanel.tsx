import { useFailureState } from "@/state/shared/useFailureState";
import { FailureState } from "@/components/failure/FailureState";
import { FailureNotice } from "@/components/failure/FailureNotice";
import { toFailure } from "@/lib/failures/resolve";
import { useCallback, useEffect, useMemo, useRef, useState, useLayoutEffect } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { PanelRightOpen, Plus } from "lucide-react";
import { PageToolbar } from "@/components/common/PageToolbar";
import { PageBreadcrumb } from "@/components/common/PageBreadcrumb";
import { ConversationTranscript } from "./ConversationTranscript";
import { Button } from "@/components/ui/Button";
import { MessageScrollerProvider, useMessageScroller } from "@/components/ui/MessageScroller";
import { useIdentity } from "@/state/auth/useIdentity";
import { identityKey } from "@/lib/identity";
import { draftKey } from "@/lib/draft";
import { returnPath } from "@/lib/navigation";
import { request } from "@/lib/api/http";
import type { AgentUsageDTO } from "@/lib/api/agents";
import {
  createConversationTransport,
  type ConversationInput,
} from "@/lib/api/conversationTransport";
import { ConversationSidebar } from "./ConversationSidebar";
import { ConversationControls } from "./ConversationControls";
import { ConversationProvider } from "./ConversationProvider";
import { useConversation } from "./useConversation";
import type { Reply } from "@/lib/api/conversations";
import { readConversationSession, saveConversationSession } from "./pendingSubmissionStorage";
import { clearAcceptedDraft, conversationSessionKey } from "./conversationDraft";

function ConversationSession({
  id,
  agentId,
  onHistoricalChange,
}: {
  id: string;
  agentId?: string;
  onHistoricalChange: (historical: boolean) => void;
}) {
  const identity = useIdentity();
  const owner = identityKey(identity);
  const storageKey = draftKey(owner, `chat:v3:${id}`);
  const [creationAgentId] = useState(agentId);
  const transport = useMemo(
    () =>
      createConversationTransport({
        create: creationAgentId ? { agentId: creationAgentId } : undefined,
      }),
    [creationAgentId],
  );
  const [acceptedInput, setAcceptedInput] = useState<ConversationInput | null>(null);
  const alive = useRef(false);
  const { scrollToEnd } = useMessageScroller();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const query = params.toString();
  useEffect(() => {
    const session = readConversationSession(conversationSessionKey(owner, id));
    const resolved = session.conversationId;
    if (creationAgentId && resolved) {
      saveConversationSession(conversationSessionKey(owner, resolved), session);
      navigate(`/conversations/${resolved}${query ? `?${query}` : ""}`, {
        replace: true,
        state: null,
      });
    }
  }, [creationAgentId, owner, id, navigate, query]);

  const onAccepted = useCallback(
    (input: ConversationInput, reply: Reply) => {
      clearAcceptedDraft(storageKey, input);
      if (alive.current) {
        if (creationAgentId) {
          const session = readConversationSession(conversationSessionKey(owner, id));
          saveConversationSession(conversationSessionKey(owner, reply.conversation_id), {
            ...session,
            persisted: true,
            conversationId: reply.conversation_id,
          });
        }
        setAcceptedInput(input);
        scrollToEnd();
        // Acceptance supplies the server-owned identity; replace the local draft route.
        if (creationAgentId)
          navigate(`/conversations/${reply.conversation_id}${query ? `?${query}` : ""}`, {
            replace: true,
            state: null,
          });
      }
    },
    [storageKey, scrollToEnd, creationAgentId, navigate, owner, id, query],
  );
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  return (
    <ConversationProvider
      id={id}
      transport={transport}
      storageKey={conversationSessionKey(owner, id)}
      onAccepted={onAccepted}
    >
      <ConversationContents
        id={id}
        creationAgentId={creationAgentId}
        storageKey={storageKey}
        acceptedInput={acceptedInput}
        onHistoricalChange={onHistoricalChange}
      />
    </ConversationProvider>
  );
}

function ConversationContents({
  id,
  creationAgentId,
  storageKey,
  acceptedInput,
  onHistoricalChange,
}: {
  id: string;
  creationAgentId?: string;
  storageKey: string;
  acceptedInput: ConversationInput | null;
  onHistoricalChange: (historical: boolean) => void;
}) {
  const identity = useIdentity();
  const chat = useConversation();
  const error = chat.submissionError ?? chat.connectionError;
  const [params] = useSearchParams();
  useLayoutEffect(
    () => onHistoricalChange(chat.history.isHistorical),
    [chat.history.isHistorical, onHistoricalChange],
  );
  const [agent, setAgent] = useState<AgentUsageDTO | null>(null);
  const { failure: agentFailure, setError: setAgentError } = useFailureState();
  const [agentReload, setAgentReload] = useState(0);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const sidebarToggle = useRef<HTMLButtonElement>(null);
  const canReadAgent = identity.permissions.includes("agents:read");
  const agentKey = chat.conversation?.agent_id ?? creationAgentId;
  const source = returnPath(params, "/conversations");
  const agentsPath = source.split("?")[0] === "/agents" ? source : "/agents";
  const historyPath = source.split("?")[0] === "/conversations" ? source : "/conversations";
  useEffect(() => {
    if (!agentKey) return;
    const controller = new AbortController();
    request<AgentUsageDTO>(canReadAgent ? `agents/${agentKey}` : `agents/${agentKey}/usage`, {
      signal: controller.signal,
    })
      .then((next) => {
        if (!controller.signal.aborted) {
          setAgent(next);
          setAgentError("");
        }
      })
      .catch((failure: Error) => {
        if (!controller.signal.aborted) {
          setAgentError(failure);
          if ([401, 403, 404].includes(toFailure(failure)?.status ?? 0)) setAgent(null);
        }
      });
    return () => controller.abort();
  }, [agentKey, agentReload, canReadAgent, setAgentError]);
  const initialFailure = !agent
    ? (agentFailure ?? error?.failure)
    : chat.phase === "loading" && !chat.conversation && !chat.messageIds.length
      ? (error?.failure ?? error)
      : null;
  if (initialFailure)
    return (
      <FailureState
        error={initialFailure}
        context={{ operation: "initial-read", resource: agentFailure ? "agent" : "conversation" }}
        actions={[
          {
            label: "重新加载",
            kind: "retry",
            onClick: () => {
              setAgentReload((n) => n + 1);
              chat.reconnect();
            },
          },
          { label: "返回对话记录", kind: "return", href: historyPath },
        ]}
      />
    );
  if (!agent)
    return (
      <div className="conversation-page-frame py-6">
        <p role="status">正在加载对话…</p>
      </div>
    );
  const title = chat.title;
  return (
    <section className="flex h-full min-h-0 flex-col bg-surface" aria-label="员工对话">
      <PageToolbar
        title={
          <div className="flex min-w-0 items-center gap-(--os-space-3)">
            <PageBreadcrumb
              parent={{ label: "数字员工", to: agentsPath }}
              current={agent.name}
              heading
              className="max-w-[60%] shrink-0"
            />
          </div>
        }
        actions={
          <>
            <Button
              ref={sidebarToggle}
              variant="ghost"
              size="icon-sm"
              aria-label={sidebarOpen ? "切换对话侧栏" : "展开侧栏"}
              title={sidebarOpen ? "收起侧栏" : "展开侧栏"}
              aria-expanded={sidebarOpen}
              aria-controls="conversation-sidebar"
              onClick={() => setSidebarOpen((open) => !open)}
            >
              <PanelRightOpen size={16} />
            </Button>
            <Button
              aria-label="新对话"
              title="新对话"
              variant="ghost"
              size="icon-sm"
              render={
                <Link
                  to={`/conversations/new?agent=${agent.id}&from=${encodeURIComponent(source)}`}
                />
              }
              nativeButton={false}
            >
              <Plus size={16} />
              <span className="sr-only">新对话</span>
            </Button>
          </>
        }
      />
      <div className="conversation-workspace flex-1" data-sidebar-open={sidebarOpen}>
        <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden" aria-label="对话主体">
          <header className="conversation-page-frame flex shrink-0 items-center gap-3 pt-6 pb-3 max-sm:pt-4">
            <h2
              className="min-w-0 truncate text-section font-semibold tracking-tight"
              title={title}
            >
              {title}
            </h2>
          </header>
          <ConversationTranscript
            agentName={agent.name}
            avatarId={agent.avatar_id}
            description={agent.description}
          />
          {agentFailure && (
            <FailureNotice
              compact
              failure={agentFailure}
              context={{ operation: "refresh", resource: "agent", hasUsableData: true }}
            />
          )}
          {error && (
            <FailureNotice
              compact
              failure={error.failure}
              error={error.message}
              className="conversation-page-frame"
              context={{
                operation: chat.submissionError ? "mutation" : "subscription",
                resource: "conversation",
                hasUsableData: true,
                ...(chat.hasPendingSubmission ? { outcome: "unknown" as const } : {}),
              }}
              actions={
                error.recovery === "retry"
                  ? [
                      {
                        label: "核对并重试原请求",
                        kind: "reconcile",
                        onClick: () => chat.resendPending().catch(() => {}),
                      },
                    ]
                  : error.recovery === "reconnect"
                    ? [{ label: "重新连接", kind: "retry", onClick: chat.reconnect }]
                    : []
              }
            />
          )}
          <ConversationControls
            agent={agent}
            storageKey={storageKey}
            acceptedInput={acceptedInput}
          />
        </div>
        {sidebarOpen && (
          <ConversationSidebar
            agent={agent}
            activeId={id}
            returnTo={source}
            historyPath={historyPath}
            refreshKey={`${chat.lastMessageId ?? ""}:${chat.conversation?.version ?? 0}`}
            onClose={() => {
              setSidebarOpen(false);
              sidebarToggle.current?.focus();
            }}
          />
        )}
      </div>
    </section>
  );
}

export function ConversationPanel(props: { id: string; agentId?: string }) {
  const [historical, setHistorical] = useState(false);
  return (
    <MessageScrollerProvider autoScroll={!historical} defaultScrollPosition="end">
      <ConversationSession {...props} onHistoricalChange={setHistorical} />
    </MessageScrollerProvider>
  );
}
