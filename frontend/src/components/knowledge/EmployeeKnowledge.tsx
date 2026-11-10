import { useState } from "react";
import { SearchInput } from "@/components/common/SearchInput";
import { FormField } from "@/components/common/FormField";
import { LoadingFeedback } from "@/components/common/LoadingFeedback";
import { FailureNotice } from "@/components/failure/FailureNotice";
import { Input } from "@/components/ui/Input";
import { SelectField } from "@/components/ui/SelectField";
import type { AgentKnowledge } from "@/lib/models/agent";
import { useWorkspaceData } from "@/state/workspace/useWorkspaceData";
import { useRetainedResource } from "@/state/shared/useResource";

export function EmployeeKnowledge({
  value,
  onChange,
  readOnly = false,
}: {
  value: AgentKnowledge;
  onChange: (value: AgentKnowledge) => void;
  readOnly?: boolean;
}) {
  const [query, setQuery] = useState("");
  const data = useWorkspaceData();
  const resource = data.knowledge.libraries();
  const state = useRetainedResource(resource, data);
  const libraries = state.data ?? [];
  const selected = new Set(value.knowledge_base_ids);
  const visible = libraries.filter((library) =>
    `${library.name} ${library.description ?? ""}`
      .toLocaleLowerCase()
      .includes(query.toLocaleLowerCase()),
  );
  const missing = value.knowledge_base_ids.filter(
    (id) => !libraries.some((item) => item.id === id),
  );
  return (
    <div className="space-y-4">
      <LoadingFeedback
        pending={state.loading && !state.data}
        shape="field"
        label="正在读取组织知识库…"
      />
      {state.failure && (
        <FailureNotice
          failure={state.failure}
          context={{
            operation: "initial-read",
            resource: "knowledge",
            hasUsableData: !!state.data,
          }}
          actions={[{ label: "重新加载", kind: "retry", onClick: () => resource.refresh() }]}
        />
      )}
      <SearchInput
        label="搜索组织知识库"
        placeholder="搜索名称或用途…"
        value={query}
        onChange={setQuery}
      />
      <fieldset disabled={readOnly} className="min-w-0 space-y-4">
        <legend className="mb-2 text-sm font-medium">资料范围</legend>
        {state.data && !libraries.length && (
          <p className="type-caption">还没有组织知识库，请先在知识库管理中准备资料。</p>
        )}
        <div className="max-h-64 space-y-1 overflow-y-auto">
          {visible.map((library) => (
            <label
              key={library.id}
              className="flex cursor-pointer items-start gap-3 rounded-control p-2 hover:bg-muted"
            >
              <input
                type="checkbox"
                className="mt-1 size-4 shrink-0 accent-action"
                checked={selected.has(library.id)}
                disabled={!selected.has(library.id) && selected.size >= 10}
                onChange={(event) =>
                  onChange({
                    ...value,
                    knowledge_base_ids: event.target.checked
                      ? [...value.knowledge_base_ids, library.id].sort()
                      : value.knowledge_base_ids.filter((id) => id !== library.id),
                  })
                }
              />
              <span className="min-w-0">
                <span className="block break-words text-sm">{library.name}</span>
                <span className="type-caption">
                  {library.document_count} 份文档 · {library.chunk_count} 个可检索片段
                </span>
              </span>
            </label>
          ))}
          {missing.map((id) => (
            <label key={id} className="flex items-start gap-3 p-2 text-sm text-warning">
              <input
                type="checkbox"
                checked
                className="mt-1 size-4 accent-action"
                onChange={() =>
                  onChange({
                    ...value,
                    knowledge_base_ids: value.knowledge_base_ids.filter((item) => item !== id),
                  })
                }
              />
              <span>知识库已不可用，请移除后保存。</span>
            </label>
          ))}
        </div>
        <FormField label={<>检索时机</>}>
          <SelectField
            value={value.mode}
            onValueChange={(mode) => onChange({ ...value, mode: mode as AgentKnowledge["mode"] })}
            options={[
              { value: "on_demand", label: "按需检索" },
              { value: "always", label: "每次回答前检索" },
            ]}
          />
        </FormField>
        <p className="type-caption">
          {value.mode === "always"
            ? "系统先查一次，模型仍可继续检索和补读。"
            : "模型根据当前问题决定何时检索和补读。"}
          系统按各库可用能力自动检索，未处理文件不参与。
        </p>
        <FormField label={<>每次检索的片段上限</>}>
          <Input
            type="number"
            min={1}
            max={12}
            required
            value={value.top_k}
            onChange={(event) => onChange({ ...value, top_k: Number(event.target.value) })}
          />
        </FormField>
      </fieldset>
      <p className="type-caption">
        已选择 {selected.size}/10 个知识库。修改随员工“保存配置”统一生效。
      </p>
    </div>
  );
}
