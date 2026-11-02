import { ResourceIcon } from "@/components/common/ResourceIcon";
import { FailureState } from "@/components/failure/FailureState";
import { FailureNotice } from "@/components/failure/FailureNotice";
import { SearchInput } from "@/components/common/SearchInput";
import { PageContainer } from "@/components/common/PageContainer";
import { Link, useNavigate, useSearchParams } from "react-router";
import { ArrowUpRight, ChevronDown, Plus, RefreshCw, Upload } from "lucide-react";
import { PageHeading } from "@/components/common/PageHeading";
import { CapabilityCard } from "@/components/skills/CapabilityCard";
import { ResourcePagination } from "@/components/common/ResourcePagination";
import { Button } from "@/components/ui/Button";

import { SelectField } from "@/components/ui/SelectField";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from "@/components/ui/DropdownMenu";
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/Tooltip";
import { useIdentity } from "@/state/auth/useIdentity";
import { useWorkspaceData } from "@/state/workspace/useWorkspaceData";
import { useRetainedResource } from "@/state/shared/useResource";
import { SkillLibrarySync } from "./SkillLibrarySync";

export function CapabilitiesPage() {
  const identity = useIdentity();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const shared = useWorkspaceData();
  const query = new URLSearchParams({
    q: params.get("q") ?? "",
    kind: params.get("kind") ?? "all",
    offset: params.get("offset") ?? "0",
    limit: "20",
  }).toString();
  const resource = shared.capabilities(new URLSearchParams(query));
  const result = useRetainedResource(resource, shared);
  const items = result.data?.items ?? [];
  const total = result.data?.total ?? 0;
  const loaded = !result.loading;
  const error = result.error;
  function filter(key: string, value: string) {
    setParams((current) => {
      const next = new URLSearchParams(current);
      next.set(key, value);
      next.delete("offset");
      return next;
    });
  }
  const tools = identity.permissions.includes("tools:read");
  const createSkill = identity.permissions.includes("skills:create");
  const types = [
    { value: "all", label: "全部类型" },
    { value: "skill", label: "技能" },
    ...(tools
      ? [
          { value: "mcp_http", label: "远程 MCP" },
          { value: "mcp_stdio", label: "本地 MCP" },
        ]
      : []),
  ];
  return (
    <PageContainer as="main" className="space-y-6">
      <PageHeading
        title="能力库"
        description="管理可复用的技能与 MCP 服务，按需装配给员工。"
        actions={
          (tools || createSkill) && (
            <DropdownMenu>
              <DropdownMenuTrigger render={<Button />}>
                <Plus />
                添加
                <ChevronDown />
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                {tools && (
                  <DropdownMenuItem onClick={() => navigate("/tools")}>
                    <ResourceIcon kind="mcp" />
                    添加 MCP 服务
                  </DropdownMenuItem>
                )}
                {createSkill && (
                  <DropdownMenuItem onClick={() => navigate("/skills/new")}>
                    <ResourceIcon kind="skill" />
                    新建技能
                  </DropdownMenuItem>
                )}
                {createSkill && (
                  <DropdownMenuItem onClick={() => navigate("/skills/new?import=1")}>
                    <Upload />
                    导入技能包
                  </DropdownMenuItem>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          )
        }
      />
      <div className="flex flex-wrap items-center gap-3">
        <SearchInput
          label="搜索能力"
          debounceMs={300}
          onChange={(nextValue) => filter("q", nextValue)}
          placeholder="搜索名称或功能…"
          value={params.get("q") ?? ""}
          className="min-w-48 flex-1 max-sm:basis-full"
        />
        <SelectField
          options={types}
          value={params.get("kind") ?? "all"}
          onValueChange={(value) => filter("kind", value)}
          aria-label="能力类型"
          className="w-36"
        />
        <span className="type-caption mr-auto">
          {params.get("q") || (params.get("kind") && params.get("kind") !== "all") ? "找到" : "共"}{" "}
          {total} 项能力
        </span>
        <Tooltip>
          <TooltipTrigger
            render={
              <Button
                variant="ghost"
                size="icon"
                aria-label="刷新能力列表"
                disabled={!loaded}
                onClick={resource.refresh}
              />
            }
          >
            <RefreshCw />
          </TooltipTrigger>
          <TooltipContent>刷新能力列表</TooltipContent>
        </Tooltip>
        {createSkill && identity.permissions.includes("skills:update") && <SkillLibrarySync />}
      </div>
      {tools && (
        <Link
          to="/tools?native=1"
          className="inline-flex items-center gap-1 text-sm text-text-muted underline underline-offset-4"
        >
          管理内置工具
          <ArrowUpRight size={14} />
        </Link>
      )}
      {result.failure &&
        (result.data ? (
          <FailureNotice
            failure={result.failure}
            context={{ operation: "refresh", resource: "skill", hasUsableData: true }}
            actions={[{ label: "重新加载", kind: "retry", onClick: resource.refresh }]}
          />
        ) : (
          <FailureState
            failure={result.failure}
            context={{ operation: "initial-read", resource: "skill" }}
            actions={[{ label: "重新加载", kind: "retry", onClick: resource.refresh }]}
          />
        ))}
      {!loaded && !error && <p role="status">{result.data ? "正在更新能力…" : "正在读取能力…"}</p>}
      <div aria-busy={!loaded} className="capability-grid">
        {items.map((item) => (
          <CapabilityCard key={`${item.kind}:${item.id}`} item={item} />
        ))}
      </div>
      {loaded && !items.length && !error && (
        <p className="py-8 text-text-muted">没有找到能力，可从“添加”新建技能 或接入 MCP。</p>
      )}
      <ResourcePagination total={total} loading={!loaded} />
    </PageContainer>
  );
}
export { CapabilitiesPage as Component };
