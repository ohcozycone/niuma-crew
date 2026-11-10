import { ResourceIcon, type ResourceKind } from "@/components/common/ResourceIcon";
import { memo, useState } from "react";
import {
  Trace,
  TraceLine,
  TraceIcon,
  TraceTitle,
  TraceDescription,
  TraceCollapsible,
  TraceCollapsibleTrigger,
  TraceCollapsibleContent,
} from "@/components/ui/Trace";
import { Button } from "@/components/ui/Button";
import { isActive, type Reply, type ReplyStep } from "@/lib/api/conversations";
import { RunProgress } from "./RunProgress";
import { useStepPagination } from "./actionPagination";
import { fileDownloadUrl } from "@/lib/api/files";
import { isKnowledgeSourceLink } from "@/lib/knowledgeSourceLink";

const labels: Record<string, string> = {
  model_call: "模型调用",
  tool_call: "工具调用",
  skill_activation: "加载技能",
  validation: "结果校验",
  knowledge: "知识读取",
};
const statuses: Record<string, string> = {
  running: "进行中",
  succeeded: "已完成",
  failed: "失败",
  cancelled: "已取消",
  interrupted: "已中断",
  unknown: "结果未确认",
};

const StepRow = memo(function StepRow({
  step,
  showOutput,
  conversationId,
}: {
  step: ReplyStep;
  showOutput: boolean;
  conversationId: string;
}) {
  const status = step.status;
  const reasoning = step.reasoning_text;
  const truncated = step.reasoning_truncated;
  const text = step.output_text;
  const tool = typeof step.safe_details.tool === "string" ? step.safe_details.tool : "";
  const name = typeof step.safe_details.name === "string" ? step.safe_details.name : "";
  const knowledgeTool = tool === "search_knowledge" || tool === "read_knowledge_source";
  const historyKnowledge =
    step.kind === "knowledge" && step.safe_details.operation === "history_reuse";
  const round = typeof step.safe_details.round === "number" ? step.safe_details.round : null;
  const kind: ResourceKind =
    step.kind === "model_call"
      ? "brain"
      : step.kind === "skill_activation" || (tool === "read_file" && !!step.skill_id)
        ? "skill"
        : tool === "read_file"
          ? "document"
          : step.kind === "knowledge" || knowledgeTool
            ? "knowledge"
            : "tool";
  const traceStatus = status === "running" ? "running" : status === "failed" ? "error" : undefined;
  const title = historyKnowledge
    ? "核对历史知识来源"
    : tool === "search_knowledge"
      ? "检索知识库"
      : tool === "read_knowledge_source"
        ? "读取知识来源"
        : tool === "read_file"
          ? step.skill_id
            ? "读取技能"
            : "读取文件"
          : (labels[step.kind] ?? "执行记录");
  const sources = Array.isArray(step.safe_details.sources)
    ? (step.safe_details.sources as {
        url?: string;
        title?: string;
        status?: string;
        full_text?: boolean;
        text_obtained?: boolean;
        content_kind?: "extracted" | "snippet";
        file_id?: string;
      }[])
    : [];
  const line = (
    <TraceLine status={traceStatus}>
      <TraceIcon>
        <ResourceIcon kind={kind} />
      </TraceIcon>
      <TraceTitle>
        {title}
        {round ? ` · 第 ${round} 轮` : ""}
        {step.kind === "tool_call" && !knowledgeTool && tool !== "read_file" && tool
          ? ` · ${tool}`
          : ""}
        {name ? ` · ${name}` : ""}
      </TraceTitle>
      <TraceDescription>{statuses[status] ?? status}</TraceDescription>
    </TraceLine>
  );
  return (
    <div className="space-y-2" data-action-id={step.id}>
      {step.kind === "tool_call" || historyKnowledge ? (
        <TraceCollapsible>
          <TraceCollapsibleTrigger>{line}</TraceCollapsibleTrigger>
          <TraceCollapsibleContent keepMounted>
            {historyKnowledge ? (
              <p>平台接受本轮任务时已核对挂载权限与原文版本，以下历史来源可在本轮继续使用。</p>
            ) : (
              <p>工具：{tool || "未提供名称"}</p>
            )}
            {name && <p>目标：{name}</p>}
            {!historyKnowledge && (
              <p>
                {status === "succeeded"
                  ? tool === "read_file" && step.skill_id
                    ? "技能方法已读取。"
                    : "工具调用已完成。"
                  : (statuses[status] ?? status)}
              </p>
            )}
            {step.error_code && <p className="text-danger">错误：{step.error_code}</p>}
            {typeof step.safe_details.query === "string" && step.safe_details.query && (
              <p>查询：{step.safe_details.query}</p>
            )}
            {typeof step.safe_details.result_file_id === "string" && (
              <a
                className="underline"
                href={fileDownloadUrl(conversationId, step.safe_details.result_file_id)}
                download
              >
                下载完整工具结果
              </a>
            )}
            <ul className="space-y-2">
              {sources.map((source, index) => (
                <li key={index} className="space-x-2">
                  {typeof source.url === "string" &&
                  (/^https?:\/\//i.test(source.url) || isKnowledgeSourceLink(source.url)) ? (
                    <a
                      className="underline"
                      href={source.url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {source.title || source.url}
                    </a>
                  ) : (
                    <span>{source.title || "来源"}</span>
                  )}
                  <span>
                    {source.status === "failed"
                      ? "读取失败"
                      : isKnowledgeSourceLink(source.url)
                        ? "已取得知识片段"
                        : source.full_text
                          ? "已取得完整正文"
                          : source.text_obtained || source.content_kind === "extracted"
                            ? "已取得提取文本"
                            : "搜索摘要"}
                  </span>
                  {source.file_id && (
                    <a
                      className="underline"
                      href={fileDownloadUrl(conversationId, source.file_id)}
                      download
                    >
                      已保存资料
                    </a>
                  )}
                </li>
              ))}
            </ul>
          </TraceCollapsibleContent>
        </TraceCollapsible>
      ) : (
        line
      )}
      {(reasoning || truncated) && (
        <TraceCollapsible className="pl-6">
          <TraceCollapsibleTrigger>
            <TraceLine>
              <TraceTitle>模型思考</TraceTitle>
            </TraceLine>
          </TraceCollapsibleTrigger>
          <TraceCollapsibleContent keepMounted>
            <p className="max-h-80 overflow-auto whitespace-pre-wrap leading-6">{reasoning}</p>
            {truncated && <p>展示已截断</p>}
          </TraceCollapsibleContent>
        </TraceCollapsible>
      )}
      {showOutput && (
        <TraceCollapsible className="pl-6">
          <TraceCollapsibleTrigger>
            <TraceLine>
              <TraceTitle>本轮过程文字</TraceTitle>
            </TraceLine>
          </TraceCollapsibleTrigger>
          <TraceCollapsibleContent keepMounted>
            <p className="max-h-80 overflow-auto whitespace-pre-wrap leading-6">{text}</p>
          </TraceCollapsibleContent>
        </TraceCollapsible>
      )}
    </div>
  );
});

/** 官方 Trace 组合：整次执行可折叠，步骤详情与最终正文分开。 */
export const RunActions = memo(function RunActions({
  run,
  finalText,
}: {
  run: Reply;
  finalText: string;
}) {
  const [open, setOpen] = useState(false);
  const page = useStepPagination(run);
  if (page.total === 0) return null;
  return (
    <Trace>
      <TraceCollapsible open={open} onOpenChange={(value) => setOpen(value)}>
        <TraceCollapsibleTrigger aria-label="执行过程">
          <TraceLine
            className="flex-wrap gap-y-1"
            status={
              run.status === "failed" || run.acceptance === "failed"
                ? "error"
                : isActive(run.status)
                  ? "running"
                  : undefined
            }
          >
            <RunProgress run={run} total={page.total} />
          </TraceLine>
        </TraceCollapsibleTrigger>
        <TraceCollapsibleContent keepMounted className="ml-2 border-l border-border pl-4">
          {page.items.map((step) => {
            const text = step.output_text;
            const hasTools = step.safe_details.has_tool_calls === true;
            const showOutput =
              step.kind === "model_call" &&
              !!text &&
              text !== finalText &&
              (hasTools || !isActive(run.status));
            return (
              <StepRow
                key={step.id}
                step={step}
                showOutput={showOutput}
                conversationId={run.conversation_id}
              />
            );
          })}
          {page.total > page.pageSize && (
            <div className="flex items-center gap-2">
              <Button
                size="xs"
                variant="ghost"
                disabled={page.offset === 0}
                onClick={() => page.setOffset((n) => n - page.pageSize)}
              >
                上一页
              </Button>
              <span>
                {Math.floor(page.offset / page.pageSize) + 1} /{" "}
                {Math.ceil(page.total / page.pageSize)}
              </span>
              <Button
                size="xs"
                variant="ghost"
                disabled={page.offset + page.pageSize >= page.total}
                onClick={() => page.setOffset((n) => n + page.pageSize)}
              >
                下一页
              </Button>
            </div>
          )}
        </TraceCollapsibleContent>
      </TraceCollapsible>
    </Trace>
  );
});
