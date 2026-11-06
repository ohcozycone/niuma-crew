import { FormField } from "@/components/common/FormField";
import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";
import { Search } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { EmptyState } from "@/components/common/EmptyState";
import { useWorkspaceData } from "@/state/workspace/useWorkspaceData";
import { useResource } from "@/state/shared/useResource";
import { KnowledgeFeedback } from "./KnowledgeLibraries";
import { KnowledgeVectors, vectorStatusLabels } from "./KnowledgeVectors";
import { SelectField } from "@/components/ui/SelectField";

export function KnowledgeSearch({ id }: { id: string }) {
  const [params, setParams] = useSearchParams();
  const question = params.get("question") || "";
  const requested = params.get("strategy");
  const strategy = requested === "vector" || requested === "hybrid" ? requested : "bm25";
  const [input, setInput] = useState(question);
  const store = useWorkspaceData().knowledge;
  const library = useResource(store.library(id));
  const vectorReady =
    library.data?.vector_status === "ready" || library.data?.vector_status === "partial";
  const blocked = strategy !== "bm25" && !vectorReady;
  const resource = store.search(id, blocked ? "" : question, strategy);
  const state = useResource(resource);
  function submit(event: FormEvent) {
    event.preventDefault();
    if (input.trim() === question) resource.invalidate();
    else
      setParams((current) => {
        const copy = new URLSearchParams(current);
        copy.set("question", input.trim());
        return copy;
      });
  }
  return (
    <section aria-label="检索测试">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="type-title">检索测试</h2>
        <KnowledgeVectors id={id} />
      </div>
      <p className="mt-2 mb-5 max-w-prose text-sm text-text-muted">
        输入问题，检查当前知识库命中的原文片段。支持关键词、语义和混合检索，不生成回答。
      </p>
      <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
        <FormField htmlFor="knowledge-strategy" label="检索方式" className="shrink-0">
          <SelectField
            options={[
              { value: "bm25", label: "关键词检索（BM25）" },
              { value: "vector", label: "向量检索", disabled: !vectorReady },
              { value: "hybrid", label: "混合检索", disabled: !vectorReady },
            ]}
            value={strategy}
            onValueChange={(value) =>
              setParams((current) => {
                const copy = new URLSearchParams(current);
                copy.set("strategy", value);
                return copy;
              })
            }
            id="knowledge-strategy"
            className="w-fit"
          />
        </FormField>

        <FormField
          className="min-w-0 flex-1 basis-64"
          label={
            <>
              <span>检索问题</span>
            </>
          }
        >
          <Input
            required
            maxLength={1000}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="例如：发布失败后应该怎样回滚？"
          />
        </FormField>
        <Button type="submit" disabled={!input.trim() || state.loading || blocked}>
          <Search size={16} />
          检索
        </Button>
      </form>
      <p className="mt-3 mb-5 text-xs text-text-muted" role="status">
        {vectorReady
          ? `${vectorStatusLabels[library.data?.vector_status ?? "ready"]} · ${library.data?.vector_chunk_count} / ${library.data?.chunk_count} 个片段 · ${library.data?.vector_connection_name}`
          : `${vectorStatusLabels[library.data?.vector_status ?? "not_built"]}。可先用 BM25，或打开“检索设置”。`}
      </p>

      {!!question && !blocked && (
        <KnowledgeFeedback
          failure={state.failure}
          hasUsableData={state.data !== undefined}
          loading={state.loading}
          retry={() => resource.invalidate()}
        />
      )}
      {state.data && !blocked && (
        <p className="mb-3 text-xs text-text-muted">
          {{ bm25: "BM25", vector: "向量检索", hybrid: "混合检索" }[state.data.strategy]} ·{" "}
          {state.data.hits.length} 个结果 · 最多显示 6 个片段
        </p>
      )}
      {!blocked &&
        state.data?.hits.map((hit) => (
          <article key={hit.chunk.id} className="border-t border-border py-5">
            <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
              <h3 className="min-w-0 max-w-full flex-1 text-sm font-medium [overflow-wrap:anywhere]">
                {hit.rank}. {hit.chunk.title} / {hit.chunk.locator}
              </h3>
              <Link
                className="text-sm text-action underline"
                to={`/knowledge/${id}/documents/${hit.chunk.document_id}?${new URLSearchParams({ chunk: hit.chunk.id, from: `/knowledge/${id}?${params}` })}`}
              >
                查看来源
              </Link>
            </div>
            <p className="max-w-prose whitespace-pre-wrap break-words text-sm leading-7 text-text-muted">
              {hit.chunk.text}
            </p>
            <details className="mt-3 text-xs text-text-muted">
              <summary className="cursor-pointer">检索诊断</summary>
              <p className="mt-2">
                {hit.score_kind === "rank_only"
                  ? `融合排序第 ${hit.rank} 项`
                  : `${hit.score_kind === "cosine_distance_lower_better" ? "向量距离" : "BM25 分数"}：${hit.score?.toFixed(4)}（越小越靠前，不代表回答置信度）`}{" "}
                · 正文区间 [{hit.chunk.start}, {hit.chunk.end})
              </p>
            </details>
          </article>
        ))}
      {!blocked && state.data?.hits.length === 0 && !state.loading && !state.error && (
        <EmptyState
          text="没有找到相关片段"
          description="尝试文档中使用的术语，或检查相关文档是否已经入库。"
        />
      )}
    </section>
  );
}
