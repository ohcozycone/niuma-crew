import { useState, type ReactNode } from "react";
import { Settings2, Unlink } from "lucide-react";
import { ConfirmActionDialog } from "@/components/common/ConfirmActionDialog";
import { ResourceType, type ResourceKind } from "@/components/common/ResourceIcon";
import { Button } from "@/components/ui/Button";
import { ButtonGroup } from "@/components/ui/ButtonGroup";
import { Switch } from "@/components/ui/Switch";

/** A selected capability row; each caller owns the draft and its validation messages. */
export function AssemblyItem({
  name,
  icon,
  kind,
  children,
  enabled,
  onEnabledChange,
  enableLabel,
  onConfigure,
  configurationDisabled,
  onRemove,
  removeLabel,
}: {
  name: string;
  icon: ReactNode;
  kind?: ResourceKind;
  children?: ReactNode;
  enabled: boolean;
  onEnabledChange: (enabled: boolean) => void;
  enableLabel: string;
  onConfigure: () => void;
  configurationDisabled?: boolean;
  onRemove: () => void;
  removeLabel: string;
}) {
  const [confirming, setConfirming] = useState(false);
  return (
    <div className="@container/row">
      <div className="flex min-h-20 flex-wrap items-center gap-4 px-5 py-4 max-sm:px-4">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-control bg-muted">
          {icon}
        </span>
        <div className="min-w-0 flex-1 @max-[560px]/row:basis-[calc(100%-64px)]">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <strong className="break-words text-sm">{name}</strong>
            {kind && <ResourceType kind={kind} showIcon={false} />}
          </div>
          {children}
        </div>
        <div className="flex shrink-0 items-center gap-3 @max-[560px]/row:ml-auto">
          <label className="inline-flex items-center gap-2 text-xs text-text-muted">
            <Switch aria-label={enableLabel} checked={enabled} onCheckedChange={onEnabledChange} />
            {enabled ? "已启用" : "已停用"}
          </label>
          <ButtonGroup>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={configurationDisabled}
              onClick={onConfigure}
            >
              <Settings2 />
              配置
            </Button>
            <Button
              type="button"
              variant="destructive-ghost"
              size="icon-sm"
              aria-label={removeLabel}
              onClick={() => setConfirming(true)}
            >
              <Unlink />
            </Button>
          </ButtonGroup>
        </div>
      </div>
      <ConfirmActionDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={`移除「${name}」的装配？`}
        description="只从当前员工草稿中移除，不删除能力定义或账号。保存员工配置后生效。"
        confirmLabel="确认移除"
        onConfirm={() => {
          onRemove();
          setConfirming(false);
        }}
      />
    </div>
  );
}
