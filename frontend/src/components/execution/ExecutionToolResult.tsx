import { JsonInspector } from "@/components/ui/JsonInspector";
import { Markdown } from "@/components/common/Markdown";
import { asRecord } from "./executionMetrics";

/** Decode only complete JSON values; preserve the captured envelope for verification. */
function decode(value: unknown): unknown {
  if (typeof value !== "string" || !/^\s*[[{]/.test(value)) return value;
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}

export function ExecutionToolResult({ payload }: { payload: Record<string, unknown> }) {
  const content = decode(payload.content ?? payload);
  const result = asRecord(content);
  const hits = Array.isArray(result.hits) ? result.hits : null;
  const documents = hits
    ? new Set(hits.map((hit) => asRecord(hit).document_id).filter((id) => typeof id === "string"))
    : null;
  return (
    <div className="min-w-0 space-y-4">
      {hits ? (
        <section aria-label="知识检索命中" className="space-y-3">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="text-sm font-semibold">检索命中 · {hits.length} 条</h3>
            <p className="text-xs text-text-muted">
              {typeof result.status === "string" ? `返回状态：${result.status}` : ""}
              {documents?.size ? ` · ${documents.size} 份文档` : ""}
            </p>
          </div>
          {hits.length === 0 && <p className="text-sm text-text-muted">本次检索没有返回命中。</p>}
          <ol className="divide-y divide-border border-y border-border">
            {hits.map((raw, index) => {
              const hit = asRecord(raw);
              if (!Object.keys(hit).length)
                return (
                  <li key={index} className="py-3">
                    <JsonInspector value={raw} />
                  </li>
                );
              return (
                <li key={index} className="py-3">
                  <details open={index === 0}>
                    <summary className="cursor-pointer text-sm font-medium [overflow-wrap:anywhere]">
                      {index + 1}. {typeof hit.title === "string" ? hit.title : "未提供文档标题"}
                      {typeof hit.locator === "string" && (
                        <span className="mt-1 block pl-4 text-xs font-normal leading-6 text-text-muted">
                          {hit.locator}
                        </span>
                      )}
                    </summary>
                    <div className="mt-3 space-y-3 pl-4">
                      {typeof hit.content === "string" ? (
                        <div className="max-h-80 overflow-auto text-sm leading-7 [overflow-wrap:anywhere]">
                          <Markdown text={hit.content} />
                        </div>
                      ) : hit.content != null ? (
                        <JsonInspector value={hit.content} />
                      ) : (
                        <p className="text-xs text-text-muted">未提供片段正文。</p>
                      )}
                      {(hit.offset != null ||
                        hit.next_offset != null ||
                        hit.total_chars != null) && (
                        <p className="text-xs text-text-muted">
                          {hit.total_chars != null ? `片段总字符：${String(hit.total_chars)}` : ""}
                          {hit.offset != null ? ` · 起始偏移：${String(hit.offset)}` : ""}
                          {hit.next_offset != null ? ` · 后续偏移：${String(hit.next_offset)}` : ""}
                        </p>
                      )}
                      <details className="text-xs text-text-muted">
                        <summary>来源标识与命中字段</summary>
                        <div className="mt-2">
                          <JsonInspector
                            value={Object.fromEntries(
                              Object.entries(hit).filter(([key]) => key !== "content"),
                            )}
                          />
                        </div>
                      </details>
                    </div>
                  </details>
                </li>
              );
            })}
          </ol>
          {result.libraries != null && (
            <details className="text-xs text-text-muted">
              <summary>知识库检索状态</summary>
              <div className="mt-2">
                <JsonInspector value={result.libraries} />
              </div>
            </details>
          )}
          <p className="text-xs text-text-muted">
            按工具返回顺序展示，未对命中相关性或正确性作自动判定。
          </p>
        </section>
      ) : (
        <section aria-label="结构化工具结果">
          <JsonInspector value={content} />
        </section>
      )}
      <details className="text-xs text-text-muted">
        <summary>原始返回 JSON</summary>
        <div className="mt-3">
          <JsonInspector value={payload} />
        </div>
      </details>
    </div>
  );
}
