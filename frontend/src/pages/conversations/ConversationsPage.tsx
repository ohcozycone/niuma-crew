import { useFailureState } from "@/state/shared/useFailureState";
import { FailureNotice } from "@/components/failure/FailureNotice";
import { PageContainer } from "@/components/common/PageContainer";
import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router";
import { Button } from "@/components/ui/Button";
import { getConversations } from "@/lib/api/conversations";
import { useIdentity } from "@/state/auth/useIdentity";
import { PageHeading } from "@/components/common/PageHeading";
import { ConversationHistory } from "./ConversationHistory";
import { ConversationPanel } from "./ConversationPanel";
import { identityKey } from "@/lib/identity";
import { createLocalConversation, localConversationAgent } from "./conversationDraft";
export function ConversationsPage() {
  const identity = useIdentity();
  return identity.permissions.includes("runs:create") ? (
    <ConversationHistory />
  ) : (
    <PageContainer>
      <PageHeading title="对话记录" description="暂无公开任务，真实对话和游客体验功能尚未开放。" />
    </PageContainer>
  );
}
export function ConversationPage() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const identity = useIdentity();
  const agent = params.get("agent") || undefined;
  const location = useLocation();
  if (!identity.permissions.includes("runs:create"))
    return <div className="conversation-page-frame py-6">请登录账号后使用员工对话。</div>;
  if (!id && !agent)
    return <div className="conversation-page-frame py-6">请先从员工目录选择员工。</div>;
  if (!id && agent && params.get("resume") === "1")
    return <RecentConversation key={agent} agentId={agent} />;
  if (!id && agent) return <NewConversation key={location.key} agentId={agent} />;
  const draftAgent = id
    ? (localConversationAgent(identityKey(identity), id) ?? location.state?.draftAgentId)
    : undefined;
  return <ConversationPanel key={id} id={id!} agentId={draftAgent} />;
}

function NewConversation({ agentId }: { agentId: string }) {
  const identity = useIdentity();
  const owner = identityKey(identity);
  const location = useLocation();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const query = params.toString();
  const allocated = useRef<string | null>(null);
  useEffect(() => {
    allocated.current ??= createLocalConversation(owner, agentId, location.key);
    navigate(`/conversations/${allocated.current}?${query}`, {
      replace: true,
      state: { draftAgentId: agentId },
    });
  }, [owner, agentId, location.key, navigate, query]);
  return (
    <p role="status" className="conversation-page-frame py-6">
      正在打开新对话…
    </p>
  );
}

function RecentConversation({ agentId }: { agentId: string }) {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { failure, error, setError } = useFailureState();
  const [revision, setRevision] = useState(0);
  const next = new URLSearchParams(params);
  next.delete("resume");
  const query = next.toString();
  useEffect(() => {
    const controller = new AbortController();
    getConversations({ agentId, limit: 1 }, controller.signal)
      .then((page) => {
        if (!controller.signal.aborted)
          navigate(`/conversations/${page.items[0]?.id ?? "new"}?${query}`, { replace: true });
      })
      .catch((failure: Error) => {
        if (!controller.signal.aborted) setError(failure);
      });
    return () => controller.abort();
  }, [agentId, navigate, query, revision, setError]);
  return (
    <div className="conversation-page-frame py-6">
      {error ? (
        <div className="flex flex-wrap items-center gap-3">
          <FailureNotice
            failure={failure}
            context={{ operation: "initial-read", resource: "conversation" }}
          />
          <Button
            variant="outline"
            onClick={() => {
              setError("");
              setRevision((v) => v + 1);
            }}
          >
            重新加载最近对话
          </Button>
          <Button render={<Link to={`/conversations/new?${query}`} />} nativeButton={false}>
            新对话
          </Button>
        </div>
      ) : (
        <p role="status">正在打开最近对话…</p>
      )}
    </div>
  );
}

export { ConversationsPage as Component };
