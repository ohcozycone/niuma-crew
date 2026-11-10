import { ResourceType, capabilityResourceKind } from "@/components/common/ResourceIcon";
import { Card, CardFooter } from "@/components/ui/Card";
import { Link } from "react-router";
import { ArrowUpRight } from "lucide-react";
import { Button } from "@/components/ui/Button";
export type CapabilityCardItem = {
  id: string;
  name: string;
  protocol_name?: string | null;
  description: string;
  kind: "skill" | "mcp_http" | "mcp_stdio";
  enabled: boolean;
};
export function CapabilityCard({
  item,
  configurationHref,
}: {
  item: CapabilityCardItem;
  configurationHref?: string;
}) {
  const kind = capabilityResourceKind(item.kind);
  return (
    <Card as="article" className="@container/resource-card">
      <div className="resource-card-content flex flex-col gap-3">
        <h2 className="type-title break-words">
          {item.name}
          {item.protocol_name && item.protocol_name !== item.name && (
            <span className="ml-1 text-sm font-normal text-text-muted">
              （{item.protocol_name}）
            </span>
          )}
        </h2>
        <p className="line-clamp-2 min-h-10 break-words text-sm text-text-muted">
          {item.description || "尚未填写功能说明"}
        </p>
        <CardFooter className="mt-auto">
          <span className="type-caption inline-flex items-center gap-1.5">
            <ResourceType kind={kind} />
            {item.kind === "mcp_stdio" && <span>· 本机程序</span>}
            <span>· {item.enabled ? "已启用" : "已停用"}</span>
          </span>
          <Button
            size="sm"
            variant="ghost"
            render={
              <Link
                to={
                  configurationHref ??
                  (item.kind === "skill" ? `/skills/${item.id}` : `/tools?service=${item.id}`)
                }
              />
            }
            nativeButton={false}
          >
            查看配置
            <ArrowUpRight size={14} />
          </Button>
        </CardFooter>
      </div>
    </Card>
  );
}
