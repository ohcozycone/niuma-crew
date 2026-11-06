import { ResourceIcon } from "@/components/common/ResourceIcon";
import { FailureNotice } from "@/components/failure/FailureNotice";
import { Button } from "@/components/ui/Button";
import { useWorkspaceData } from "@/state/workspace/useWorkspaceData";
import { useRetainedResource } from "@/state/shared/useResource";

export function GlobalSearch({
  query,
  onNavigate,
}: {
  query: string;
  onNavigate: (path: string) => void;
}) {
  const data = useWorkspaceData();
  const resource = data.search(query);
  const result = useRetainedResource(resource, data);
  const results = result.data;
  const error = result.error;
  return (
    <div className="focus-gutter max-h-[55dvh] overflow-y-auto" aria-busy={result.loading}>
      {error && (
        <FailureNotice
          compact
          failure={result.failure}
          context={{ operation: results ? "refresh" : "initial-read", hasUsableData: !!results }}
          actions={[{ label: "重新搜索", kind: "retry", onClick: resource.refresh }]}
        />
      )}
      {!results && !error && <p role="status">正在搜索…</p>}
      {results && result.loading && <p role="status">正在搜索…</p>}
      {results?.agents.map((item) => (
        <Button
          className="flex w-full justify-start"
          variant="ghost"
          key={item.id}
          onClick={() => onNavigate(`/agents/${item.id}`)}
        >
          <ResourceIcon kind="employees" />
          员工 · {item.name}
        </Button>
      ))}
      {results?.skills.map((item) => (
        <Button
          className="flex w-full justify-start"
          variant="ghost"
          key={item.id}
          onClick={() => onNavigate(`/skills/${item.id}`)}
        >
          <ResourceIcon kind="skill" />
          技能 · {item.name}
        </Button>
      ))}
      {results && !results.agents.length && !results.skills.length && <p>未找到结果。</p>}
      {results && (
        <p className="mt-2 text-xs text-text-muted">每类最多展示 20 项，可进入目录继续筛选。</p>
      )}
    </div>
  );
}
