import { useState, type ReactNode } from "react";
import { ArrowUpRight } from "lucide-react";
import { fileDownloadUrl } from "@/lib/api/files";
import {
  executionEvidenceUrl,
  type ExecutionTrace,
  type ExecutionArtifact,
} from "@/lib/api/execution";
import { JsonInspector } from "@/components/ui/JsonInspector";
import { PageTabs } from "@/components/common/PageTabs";
import { TabsContent } from "@/components/ui/Tabs";
import { ExecutionToolResult } from "./ExecutionToolResult";

const JsonText = JsonInspector;
const stages: Record<string, string> = {
  wire_request: "实际发送的模型请求",
  sdk_response: "SDK 解析后的模型响应",
  model_error: "模型调用错误",
  tool_request: "工具调用申请",
  tool_response: "返回给模型的工具结果",
};
type Action = NonNullable<ExecutionTrace["selected"]>;
const hasArtifact = (artifact: ExecutionArtifact) => artifact.status === "available";
const nonempty = (value: unknown) =>
  value != null && value !== "" && (typeof value !== "object" || Object.keys(value).length > 0);

export function ExecutionActionDetails({
  action,
  base,
  conversationId,
}: {
  action: Action;
  base: string;
  conversationId?: string;
}) {
  const [tab, setTab] = useState("");
  const call = ["model_call", "tool_call"].includes(action.kind);
  const model = action.kind === "model_call";
  const panels: { value: string; label: string; content: ReactNode }[] = [];
  const details = Object.fromEntries(
    Object.entries(action.safe_details).filter(
      ([key, value]) =>
        !["kind", "type", "name", "tool", "round", "purpose", "executed"].includes(key) &&
        nonempty(value),
    ),
  );
  const usage =
    action.safe_details.usage && typeof action.safe_details.usage === "object"
      ? (action.safe_details.usage as Record<string, unknown>)
      : {};
  if (hasArtifact(action.request))
    panels.push({
      value: "request",
      label: model ? "模型请求" : "调用参数",
      content: (
        <Artifact artifact={action.request} base={base} action={action.id} direction="request" />
      ),
    });
  if (hasArtifact(action.response) || action.output_text || action.saved_tool_feedback != null)
    panels.push({
      value: "response",
      label: model && hasArtifact(action.response) ? "完整响应" : model ? "已保存输出" : "返回结果",
      content: (
        <div className="space-y-4">
          {hasArtifact(action.response) ? (
            <Artifact
              artifact={action.response}
              base={base}
              action={action.id}
              direction="response"
            />
          ) : action.saved_tool_feedback != null ? (
            <section>
              <p className="mb-2 text-xs text-text-muted">
                以下来自已保存的工具恢复记录，不是独立响应快照。
              </p>
              <JsonInspector value={action.saved_tool_feedback} />
            </section>
          ) : (
            <JsonInspector value={action.output_text} />
          )}
          {conversationId && typeof action.safe_details.result_file_id === "string" && (
            <a
              className="inline-block text-sm underline"
              href={fileDownloadUrl(conversationId, action.safe_details.result_file_id)}
              download
            >
              下载工具原始结果
            </a>
          )}
        </div>
      ),
    });
  if (!call && Object.keys(details).length)
    panels.unshift({
      value: "record",
      label:
        action.kind === "knowledge"
          ? "知识检索记录"
          : action.kind === "skill_activation"
            ? "技能加载记录"
            : "步骤记录",
      content: <JsonInspector value={details} />,
    });
  const selected = panels.some((panel) => panel.value === tab)
    ? tab
    : panels.find((panel) => panel.value === "response")?.value || panels[0]?.value;
  const restricted =
    call && [action.request, action.response].some((artifact) => artifact.status === "restricted");
  const unavailable =
    call && [action.request, action.response].some((artifact) => artifact.status === "unavailable");
  const missing =
    call &&
    [action.request, action.response].some((artifact) => artifact.status === "not_collected");
  return (
    <div className="min-w-0 space-y-4">
      {Object.keys(usage).some((key) => typeof usage[key] === "number") ||
      action.safe_details.finish_reason ? (
        <dl className="flex flex-wrap gap-4 text-xs text-text-muted">
          {[
            ["输入 Token", usage.input_tokens],
            ["输出 Token", usage.output_tokens],
            ["结束原因", action.safe_details.finish_reason],
          ]
            .filter(([, value]) => value != null && value !== "")
            .map(([label, value]) => (
              <div key={String(label)} className="flex gap-2">
                <dt>{String(label)}</dt>
                <dd className="text-text tabular-nums">{String(value)}</dd>
              </div>
            ))}
        </dl>
      ) : null}
      {action.error_code && (
        <p className="break-all text-sm text-danger">步骤错误：{action.error_code}</p>
      )}
      {action.safe_details.executed === false && (
        <p className="text-sm text-danger">该工具申请未获执行许可，工具没有执行。</p>
      )}
      {restricted && (
        <p className="text-sm text-text-muted">
          当前身份可查看执行概况；完整输入与工具证据需要员工配置及全员规则查看权限。
        </p>
      )}
      {unavailable && (
        <p className="text-sm text-danger">部分证据暂不可读，请检查文件存储或刷新日志。</p>
      )}
      {missing && (
        <p className="text-xs text-text-muted">
          未采集
          {action.request.status === "not_collected" && action.response.status === "not_collected"
            ? "请求及响应"
            : action.request.status === "not_collected"
              ? "请求"
              : "响应"}
          快照。历史执行不会补造输入或响应。
        </p>
      )}
      {panels.length > 1 ? (
        <PageTabs
          label="步骤证据"
          placement="panel"
          value={selected}
          onValueChange={setTab}
          items={panels.map(({ value, label }) => ({ value, label }))}
        >
          {panels.map((panel) => (
            <TabsContent key={panel.value} value={panel.value} className="pt-3">
              {panel.content}
            </TabsContent>
          ))}
        </PageTabs>
      ) : panels.length === 1 ? (
        <section>
          <h3 className="mb-3 text-sm font-medium">{panels[0].label}</h3>
          {panels[0].content}
        </section>
      ) : !call ? (
        <p className="text-sm text-text-muted">此步骤仅记录了状态与耗时。</p>
      ) : null}
      {model &&
        action.reasoning_text &&
        !["reasoning_content", "reasoning", "thinking"].some(
          (key) =>
            typeof action.response.document?.payload[key] === "string" &&
            action.response.document.payload[key],
        ) && (
          <details>
            <summary className="text-sm text-text-muted">
              模型思考文本{action.reasoning_truncated ? "（已截断）" : ""}
            </summary>
            <div className="mt-3">
              <JsonInspector value={action.reasoning_text} />
            </div>
          </details>
        )}
    </div>
  );
}
function Artifact({
  artifact,
  base,
  action,
  direction,
}: {
  artifact: ExecutionArtifact;
  base: string;
  action: string;
  direction: string;
}) {
  if (artifact.status !== "available")
    return (
      <p className="py-4 text-sm leading-7 text-text-muted">
        {artifact.status === "restricted"
          ? "当前身份可查看执行概况；完整输入与工具证据需要员工配置及全员规则查看权限。"
          : artifact.status === "unavailable"
            ? "证据暂不可读，请检查文件存储或稍后刷新。"
            : "未采集。历史执行不会补造输入；新执行会在实际调用时采集。"}
      </p>
    );
  const doc = artifact.document;
  const messages =
    doc?.capture_stage === "wire_request" && Array.isArray(doc.payload.messages)
      ? (doc.payload.messages as Record<string, unknown>[])
      : null;
  const roles: Record<string, string> = {
    system: "系统指令",
    developer: "开发者指令",
    user: "用户输入 / 参考资料",
    assistant: "模型回复 / 工具申请",
    tool: "工具反馈",
  };
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-text-muted">
        <span>
          {stages[doc?.capture_stage || ""] || "调用证据"} ·{" "}
          {Math.ceil((artifact.size || 0) / 1024)} KB
        </span>
        <a
          className="inline-flex items-center gap-1 underline"
          href={executionEvidenceUrl(base, action, direction)}
          download
        >
          下载完整 JSON <ArrowUpRight size={12} />
        </a>
      </div>
      {messages ? (
        <ol className="divide-y divide-border">
          {messages.map((message, index) => (
            <li key={index} className="py-3 first:pt-0">
              <details open={message.role === "user" || message.role === "tool"}>
                <summary className="text-sm font-medium">
                  {index + 1}. {roles[String(message.role)] || String(message.role)}
                  {message.tool_call_id ? ` · ${message.tool_call_id}` : ""}
                </summary>
                <div className="mt-3 space-y-2">
                  {message.content != null ? (
                    <MessageContent value={message.content} />
                  ) : message.tool_calls == null ? (
                    <JsonText value={message} />
                  ) : null}
                  {message.tool_calls != null && <JsonText value={message.tool_calls} />}
                </div>
              </details>
            </li>
          ))}
        </ol>
      ) : doc?.capture_stage === "tool_request" ? (
        <div className="space-y-4">
          <p className="text-sm">
            执行许可：{doc.payload.authorization_status === "allowed" ? "允许执行" : "未获许可"}
          </p>
          <div className="grid gap-4 xl:grid-cols-2">
            <section className="min-w-0">
              <h3 className="mb-2 text-sm font-medium">模型申请的参数</h3>
              <JsonText value={doc.payload.requested_arguments} />
            </section>
            {doc.payload.effective_arguments != null && (
              <section>
                <h3 className="mb-2 text-sm font-medium">平台传入工具的参数</h3>
                <JsonText value={doc.payload.effective_arguments} />
              </section>
            )}
          </div>
          {doc.payload.error_code != null && (
            <p className="text-sm text-danger">{String(doc.payload.error_code)}</p>
          )}
        </div>
      ) : doc?.capture_stage === "tool_response" && !artifact.truncated ? (
        <ExecutionToolResult payload={doc.payload} />
      ) : (
        <JsonText
          value={artifact.truncated ? artifact.preview : doc?.payload}
          foldReasoning={direction === "response"}
        />
      )}
      {artifact.truncated && (
        <p className="text-xs text-text-muted">正文较大，仅预览前 256 KB；下载可查看完整文件。</p>
      )}
      {messages && (
        <details className="text-sm">
          <summary className="cursor-pointer text-text-muted">请求参数与工具定义</summary>
          <div className="mt-3">
            <JsonText
              value={Object.fromEntries(
                Object.entries(doc!.payload).filter(([key]) => key !== "messages"),
              )}
            />
          </div>
        </details>
      )}
      <details className="text-xs text-text-muted">
        <summary>证据校验</summary>
        <p className="mt-2 break-all">SHA-256：{artifact.content_hash}</p>
      </details>
    </div>
  );
}

function MessageContent({ value }: { value: unknown }) {
  if (Array.isArray(value))
    return (
      <div className="space-y-2">
        {value.map((block, index) => (
          <JsonText
            key={index}
            value={
              block && typeof block === "object" && typeof block.text === "string"
                ? block.text
                : block
            }
          />
        ))}
      </div>
    );
  return <JsonText value={value} />;
}
