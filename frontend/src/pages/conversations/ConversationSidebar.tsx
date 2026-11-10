import { Link } from "react-router";
import { ArrowUpRight, PanelRightClose } from "lucide-react";
import { AgentAvatar } from "@/components/avatars";
import { Button } from "@/components/ui/Button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";
import type { AgentUsageDTO } from "@/lib/api/agents";
import { ConversationCapabilities } from "./ConversationCapabilities";
import { ConversationHistory } from "@/components/conversations/ConversationHistory";

export function ConversationSidebar({
  agent,
  activeId,
  returnTo,
  historyPath,
  refreshKey,
  onClose,
}: {
  agent: AgentUsageDTO;
  activeId: string;
  returnTo: string;
  historyPath: string;
  refreshKey?: string;
  onClose: () => void;
}) {
  return (
    <aside id="conversation-sidebar" className="conversation-sidebar" aria-label="员工对话与能力">
      <div className="flex shrink-0 items-start gap-3 px-5 pt-5 pb-4 max-sm:px-4 max-sm:pt-3 max-sm:pb-3">
        <AgentAvatar
          avatarId={agent.avatar_id}
          size={48}
          alt=""
          className="shrink-0 max-sm:size-8"
        />
        <div className="min-w-0 flex-1 pt-0.5">
          <h2 className="text-[length:var(--os-text-title)] font-semibold tracking-tight [overflow-wrap:anywhere]">
            {agent.name}
          </h2>
          <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-text-muted max-sm:hidden">
            {agent.description || "根据工作指令协助处理你的问题"}
          </p>
        </div>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label="收起侧栏"
          title="收起侧栏"
          className="-mr-2 text-text-muted"
          aria-expanded={true}
          aria-controls="conversation-sidebar"
          onClick={onClose}
        >
          <PanelRightClose size={16} />
        </Button>
      </div>
      <Tabs defaultValue="history" className="min-h-0 flex-1 gap-0">
        <div className="shrink-0 px-4 pb-4 max-sm:pb-2">
          <TabsList aria-label="对话辅助信息" className="w-full">
            <TabsTrigger value="history">历史对话</TabsTrigger>
            <TabsTrigger value="capabilities">员工能力</TabsTrigger>
          </TabsList>
        </div>
        <TabsContent
          value="history"
          className="focus-gutter min-h-0 overflow-y-auto overscroll-contain px-3 pb-4"
        >
          <ConversationHistory
            key={agent.id}
            agentId={agent.id}
            activeId={activeId}
            returnTo={returnTo}
            compact
            refreshKey={refreshKey}
          />
        </TabsContent>
        <TabsContent
          value="capabilities"
          className="focus-gutter min-h-0 overflow-y-auto overscroll-contain"
        >
          <ConversationCapabilities agent={agent} />
        </TabsContent>
      </Tabs>
      <Link
        to={historyPath}
        className="mx-5 flex shrink-0 items-center justify-between gap-2 border-t border-border/60 py-4 text-xs text-text-muted transition-colors hover:text-text max-sm:py-3"
      >
        查看全部对话记录
        <ArrowUpRight size={14} aria-hidden="true" />
      </Link>
    </aside>
  );
}
