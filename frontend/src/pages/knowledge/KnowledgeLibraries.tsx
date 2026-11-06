import { ResourceIcon } from "@/components/common/ResourceIcon";
import { mutationOutcome } from "@/lib/failures/resolve";
import { FailureNotice } from "@/components/failure/FailureNotice";
import { FailureState } from "@/components/failure/FailureState";
import type { Failure, FailureAction, FailureResource } from "@/lib/failures/types";
import { FormField } from "@/components/common/FormField";
import { useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";
import { Plus, RefreshCw } from "lucide-react";
import { CollectionToolbar } from "@/components/common/CollectionToolbar";
import { PageActionsMenu } from "@/components/common/PageActionsMenu";
import { ButtonGroup } from "@/components/ui/ButtonGroup";
import { DropdownMenuItem } from "@/components/ui/DropdownMenu";
import { Button } from "@/components/ui/Button";
import { KnowledgeCard } from "./KnowledgeCard";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { PageContainer } from "@/components/common/PageContainer";
import { PageHeading } from "@/components/common/PageHeading";
import { EmptyState } from "@/components/common/EmptyState";
import { SearchInput } from "@/components/common/SearchInput";
import { useQueryState } from "@/hooks/useQueryState";
import { useWorkspaceData } from "@/state/workspace/useWorkspaceData";
import { useResource } from "@/state/shared/useResource";
import { useSaveOperation } from "@/state/editing/useSaveOperation";
import { useEditingRegistration } from "@/state/editing/useEditing";

export function KnowledgeFeedback({
  failure,
  loading,
  retry,
  hasUsableData = false,
  resource = "knowledge",
  returnTo,
  actions = [],
}: {
  failure: Failure | null;
  loading: boolean;
  retry: () => void;
  hasUsableData?: boolean;
  resource?: FailureResource;
  returnTo?: string;
  actions?: readonly FailureAction[];
}) {
  if (failure) {
    const Feedback = hasUsableData ? FailureNotice : FailureState;
    return (
      <Feedback
        failure={failure}
        context={{ operation: hasUsableData ? "refresh" : "initial-read", resource, hasUsableData }}
        actions={[
          { label: "重新加载", kind: "retry", onClick: retry },
          ...actions,
          ...(returnTo ? [{ label: "返回知识库", kind: "return" as const, href: returnTo }] : []),
        ]}
        className="my-4"
      />
    );
  }
  return loading ? (
    <p role="status" className="my-4 text-sm text-text-muted">
      正在加载…
    </p>
  ) : null;
}
export function KnowledgeLibraries() {
  const store = useWorkspaceData().knowledge;
  const resource = store.libraries();
  const state = useResource(resource);
  const [query, setQuery] = useQueryState("q");
  const libraries = state.data?.filter((kb) =>
    `${kb.name} ${kb.description}`.includes(query.trim()),
  );
  return (
    <section aria-label="知识库列表">
      <PageHeading
        title="知识库"
        description="按业务整理资料，为员工检索和回答提供依据。"
        actions={
          <ButtonGroup>
            <Button nativeButton={false} role="link" render={<Link to="/knowledge/new" />}>
              <Plus />
              新建知识库
            </Button>
            <PageActionsMenu label="知识库更多操作">
              <DropdownMenuItem onClick={store.refresh} disabled={state.loading}>
                <RefreshCw />
                重新加载列表
              </DropdownMenuItem>
            </PageActionsMenu>
          </ButtonGroup>
        }
      />
      <CollectionToolbar
        label="筛选知识库"
        summary={state.data && `${query ? "找到" : "共"} ${libraries?.length ?? 0} 个知识库`}
      >
        <SearchInput
          label="查找知识库"
          placeholder="搜索库名称或用途…"
          value={query}
          onChange={setQuery}
          className="w-80 max-sm:w-full"
        />
      </CollectionToolbar>
      <KnowledgeFeedback
        failure={state.failure}
        hasUsableData={state.data !== undefined}
        loading={state.loading}
        retry={() => resource.invalidate()}
      />
      {!!libraries?.length && (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,15rem),1fr))] gap-4">
          {libraries.map((kb) => (
            <KnowledgeCard key={kb.id} library={kb} />
          ))}
        </div>
      )}
      {libraries?.length === 0 && !state.loading && !state.error && (
        <EmptyState
          icon={<ResourceIcon kind="knowledge" size={28} />}
          text={query ? "没有匹配的知识库" : "先建立一个知识库"}
          description={
            query
              ? "试试其他名称，或清除搜索。"
              : "例如差旅报销、项目技术文档。创建后即可上传资料。"
          }
          onReset={query ? () => setQuery("") : undefined}
        />
      )}
    </section>
  );
}
export function KnowledgeCreate() {
  const store = useWorkspaceData().knowledge;
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const requestId = useRef(crypto.randomUUID());
  const save = useSaveOperation();
  useEditingRegistration({
    dirty: !!(name || description),
    saving: save.saving,
    isSaving: () => save.saving,
    discard: () => {
      setName("");
      setDescription("");
    },
  });
  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      const result = await save.run(() =>
        store.create(name.trim(), description.trim(), requestId.current),
      );
      setName("");
      setDescription("");
      navigate(`/knowledge/${result.id}`);
    } catch (error) {
      save.setError(error);
    }
  }
  return (
    <PageContainer>
      <Link to="/knowledge" className="mb-5 inline-block text-sm text-text-muted underline">
        返回知识库
      </Link>
      <PageHeading
        title="新建知识库"
        description="用一个明确的业务用途组织资料，文档将在这个库内检索。"
      />
      <form onSubmit={submit} className="mt-8 max-w-xl space-y-6">
        <FormField
          label={
            <>
              <span>知识库名称</span>
            </>
          }
        >
          <Input
            required
            maxLength={100}
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="例如：项目 A 技术文档"
            disabled={save.saving}
          />
          <p className="mt-2 text-xs text-text-muted">
            写清业务主题和适用对象，避免“资料1”等模糊名称。
          </p>
        </FormField>
        <FormField
          label={
            <>
              <span>用途说明（选填）</span>
            </>
          }
        >
          <Textarea
            maxLength={1000}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="说明包含哪些资料、适合回答什么问题。"
            disabled={save.saving}
          />
          <p className="mt-2 text-xs text-text-muted">
            包含哪些内容、适合回答什么问题？与实际资料保持一致，准确比长度重要。
          </p>
        </FormField>
        <FailureNotice
          failure={save.failure}
          context={{
            operation: "mutation",
            resource: "knowledge",
            outcome: mutationOutcome(save.failure),
          }}
        />
        <Button type="submit" disabled={save.saving || !name.trim()}>
          {save.saving ? "正在创建…" : "创建并添加文档"}
        </Button>
      </form>
    </PageContainer>
  );
}
