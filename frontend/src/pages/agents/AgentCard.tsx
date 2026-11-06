import { FailureNotice } from "@/components/failure/FailureNotice";
import { Card, CardContent, CardFooter } from "@/components/ui/Card";
import { AgentAvatar } from "@/components/avatars/index";
import { ArrowUpRight, MoreHorizontal, Pause, Play, Settings2, Star } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/Tooltip";
import { useState } from "react";
import { ConfirmActionDialog } from "@/components/common/ConfirmActionDialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/DropdownMenu";
import styles from "./agentCardStyles";
import type { AgentCardProps } from "./types";
const labels = {
  available: "在岗",
  paused: "已暂停接单",
  unconfigured: "待配置模型",
};
function AgentActions({
  agent,
  onAction,
  statusPending,
}: Pick<AgentCardProps, "agent" | "onAction" | "statusPending">) {
  const paused = agent.availability === "paused";
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
      </TooltipProvider>
      <DropdownMenu>
        <DropdownMenuTrigger
          render={<Button type="button" variant="ghost" size="icon-sm" />}
          disabled={!onAction}
          aria-label={`${agent.name}的更多操作`}
        >
          <MoreHorizontal aria-hidden="true" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onClick={() => onAction?.(agent.id, "edit")}>
            <Settings2 aria-hidden="true" />
            编辑配置
          </DropdownMenuItem>
          <DropdownMenuItem
            disabled={statusPending}
            onClick={() => {
              if (paused) onAction?.(agent.id, "toggle");
              else setConfirming(true);
            }}
          >
            {paused ? <Play aria-hidden="true" /> : <Pause aria-hidden="true" />}
            {paused ? "恢复接单" : "暂停接单"}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <ConfirmActionDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={`暂停「${agent.name}」接单？`}
        description="暂停后无法开始对话，配置和历史对话继续保留；之后可通过「恢复接单」重新启用。"
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
  const canOpen = (!readOnly || usable) && Boolean(onAction);
  const hasResources = agent.skillCount > 0 || agent.toolCount > 0 || agent.knowledgeBaseCount > 0;
  const experienceUnavailable = readOnly && !usable;
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
            aria-label={`查看${agent.name}的员工主页`}
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
              {agent.subtitle || "未分类"}
            </span>
            <span className={styles.status} data-status={agent.availability}>
              <i aria-hidden="true" />
              {labels[agent.availability]}
            </span>
          </div>
        </div>
        <p className={styles.description}>{agent.description || "暂无职责简介"}</p>
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
            {(agent.skillCount > 0 || !hasResources) && (
              <button
                type="button"
                disabled={!onAction}
                className={styles.resource}
                onClick={() => onAction?.(agent.id, "skills")}
                aria-label={`${readOnly ? "查看" : "配置"}${agent.name}的技能，共 ${agent.skillCount} 项`}
              >
                <span>{hasResources ? "技能" : "未装配扩展能力"}</span>
                {hasResources && <span className={styles.resourceCount}>{agent.skillCount}</span>}
              </button>
            )}
            {agent.toolCount > 0 && (
              <span className={styles.resource}>
                <span>工具操作</span>
                <span className={styles.resourceCount}>{agent.toolCount}</span>
              </span>
            )}
            {agent.knowledgeBaseCount > 0 && (
              <span className={styles.resource}>
                <span>知识库</span>
                <span className={styles.resourceCount}>{agent.knowledgeBaseCount}</span>
              </span>
            )}
          </div>
          {!preview && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className={styles.assign}
              onClick={() => onAction?.(agent.id, "open")}
              disabled={!canOpen}
              aria-label={
                experienceUnavailable
                  ? "体验功能尚未开放"
                  : !onAction
                    ? "保存配置后可查看员工"
                    : `打开${agent.name}的员工主页`
              }
            >
              <ArrowUpRight />
              {experienceUnavailable ? "体验暂未开放" : "查看员工"}
            </Button>
          )}
        </CardFooter>
      </CardContent>
    </Card>
  );
}
