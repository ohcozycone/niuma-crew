import { FailureNotice } from "@/components/failure/FailureNotice";
import { Card, CardContent, CardFooter } from "@/components/ui/Card";
import { AgentAvatar } from "@/components/avatars/index";
import { ArrowUpRight, RotateCcw, Scissors, Settings2, Star } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/Tooltip";
import { useState } from "react";
import { ConfirmActionDialog } from "@/components/common/ConfirmActionDialog";
import styles from "./agentCardStyles";
import type { AgentCardProps } from "./types";
const labels = {
  available: "可对话",
  paused: "已被优化",
  unconfigured: "待配置模型",
};
function AgentActions({
  agent,
  onAction,
  statusPending,
}: Pick<AgentCardProps, "agent" | "onAction" | "statusPending">) {
  const optimized = agent.availability === "paused";
  const [confirming, setConfirming] = useState(false);
  return (
    <>
      <TooltipProvider delay={200}>
        <Tooltip>
          <TooltipTrigger
            render={
              <Button
                type="button"
                disabled={!onAction || statusPending}
                variant="ghost"
                size="icon-sm"
                className={styles.favorite}
                aria-label={`收藏${agent.name}`}
                aria-pressed={agent.favorite}
                aria-busy={statusPending}
                onClick={() => onAction?.(agent.id, "favorite")}
              />
            }
          >
            <Star fill={agent.favorite ? "currentColor" : "none"} aria-hidden="true" />
          </TooltipTrigger>
          <TooltipContent sideOffset={6}>{agent.favorite ? "取消收藏" : "收藏员工"}</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger
            render={
              <Button
                type="button"
                disabled={!onAction}
                variant="ghost"
                size="icon-sm"
                aria-label={`编辑${agent.name}的配置`}
                onClick={() => onAction?.(agent.id, "edit")}
              />
            }
          >
            <Settings2 aria-hidden="true" />
          </TooltipTrigger>
          <TooltipContent sideOffset={6}>编辑员工配置</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger
            render={
              <Button
                type="button"
                disabled={!onAction || statusPending}
                variant="ghost"
                size="icon-sm"
                aria-label={`${optimized ? "返聘" : "优化"}${agent.name}`}
                aria-busy={statusPending}
                onClick={() => {
                  if (!statusPending) {
                    if (optimized) onAction?.(agent.id, "toggle");
                    else setConfirming(true);
                  }
                }}
              />
            }
          >
            {optimized ? <RotateCcw aria-hidden="true" /> : <Scissors aria-hidden="true" />}
          </TooltipTrigger>
          <TooltipContent sideOffset={6}>
            {optimized ? "返聘它 · 恢复在岗" : "优化它 · 暂停接单"}
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
      <ConfirmActionDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={`优化「${agent.name}」？`}
        description="这会暂停员工接单，配置和历史对话继续保留；之后可通过返聘恢复在岗。"
        confirmLabel="确认暂停接单"
        busy={statusPending}
        onConfirm={() => {
          onAction?.(agent.id, "toggle");
          setConfirming(false);
        }}
      />
    </>
  );
}
export function AgentCard({
  agent,
  onAction,
  readOnly = false,
  preview = false,
  usable = false,
  statusPending = false,
  statusError = "",
  statusFailure,
  statusRetry,
}: AgentCardProps) {
  const canAssign =
    (!readOnly || usable) && Boolean(onAction) && agent.availability === "available";
  return (
    <Card as="article" interactive className="@container/agent" aria-label={agent.name}>
      <CardContent className={styles.card}>
        {!readOnly && !preview && (
          <div className={styles.actions} role="group" aria-label={`${agent.name}的操作`}>
            <AgentActions agent={agent} onAction={onAction} statusPending={statusPending} />
          </div>
        )}
        <div className={styles.identity}>
          <button
            type="button"
            disabled={!onAction}
            className={styles.portrait}
            aria-label={`查看${agent.name}的${readOnly ? "介绍" : "配置"}`}
            onClick={() => onAction?.(agent.id, "open")}
          >
            <AgentAvatar avatarId={agent.avatarId} size="100%" />
          </button>
          <div className={styles.nameBlock}>
            <button
              type="button"
              disabled={!onAction}
              className={styles.name}
              onClick={() => onAction?.(agent.id, "open")}
              title={agent.name}
            >
              <h3>{agent.name}</h3>
            </button>
            <span className={styles.subtitle} title={agent.subtitle}>
              {agent.subtitle || "职责待完善"}
            </span>
            <span className={styles.status} data-status={agent.availability}>
              <i aria-hidden="true" />
              {labels[agent.availability]}
            </span>
          </div>
        </div>
        <p className={styles.description}>
          {agent.description || "尚未填写职责，可在员工配置中补充工作范围。"}
        </p>
        {statusError && (
          <FailureNotice
            compact
            failure={statusFailure}
            error={statusError}
            context={{
              operation: "mutation",
              resource: "agent",
              outcome: statusRetry ? "unknown" : "rejected",
            }}
            actions={
              statusRetry ? [{ label: "重新核对", kind: "reconcile", onClick: statusRetry }] : []
            }
          />
        )}
        <CardFooter>
          <div className={styles.resources} role="group" aria-label={`${agent.name}的资源配置数量`}>
            <button
              type="button"
              disabled={!onAction}
              className={styles.resource}
              onClick={() => onAction?.(agent.id, "skills")}
              aria-label={`${readOnly ? "查看" : "配置"}${agent.name}的技能，共 ${agent.skillCount} 项`}
            >
              <span>技能</span>
              <span className={styles.resourceCount}>{agent.skillCount}</span>
            </button>
            <span className={styles.resource}>
              <span>工具操作</span>
              <span className={styles.resourceCount}>{agent.toolCount}</span>
            </span>
            <span className={styles.resource}>
              <span>知识库</span>
              <span className={styles.resourceCount}>{agent.knowledgeBaseCount}</span>
            </span>
          </div>
          {!preview && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className={styles.assign}
              onClick={() => onAction?.(agent.id, "assign")}
              disabled={!canAssign}
              aria-label={
                readOnly && !usable
                  ? "体验功能尚未开放"
                  : !onAction
                    ? "保存配置后可开始对话"
                    : canAssign
                      ? `与${agent.name}开始对话`
                      : agent.availability === "paused"
                        ? "返聘员工后可开始对话"
                        : "配置模型后可开始对话"
              }
            >
              {readOnly ? "体验暂未开放" : "开始对话"}
              <ArrowUpRight />
            </Button>
          )}
        </CardFooter>
      </CardContent>
    </Card>
  );
}
