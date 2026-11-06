import { FormField } from "@/components/common/FormField";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/Dialog";
import { SelectField } from "@/components/ui/SelectField";
import { evaluateDemoCall, toolDisplayName } from "./demoCatalog";
import type { DemoCapability, DemoConnection, DemoEmployee } from "./fixtures/capabilities";

export function DemoInvocationDialog({
  employee,
  capabilities,
  connections,
  open,
  onClose,
}: {
  employee: DemoEmployee;
  capabilities: DemoCapability[];
  connections: DemoConnection[];
  open: boolean;
  onClose: () => void;
}) {
  const available = employee.assignments.filter(
    (item) =>
      capabilities.find((capability) => capability.id === item.capabilityId)?.kind === "mcp",
  );
  const [selected, setSelected] = useState(available[0]?.capabilityId || "");
  const assignment = available.find((item) => item.capabilityId === selected);
  const connection = connections.find((item) => item.id === assignment?.connectionId);
  const names = [
    ...new Set([
      ...(assignment?.tools || []),
      ...(connection?.approved_catalog.map((tool) => tool.name) || []),
    ]),
  ];
  const [toolName, setToolName] = useState(assignment?.tools[0] || names[0] || "");
  const [result, setResult] = useState<ReturnType<typeof evaluateDemoCall> | null>(null);
  return (
    <Dialog
      open={open}
      onOpenChange={(value) => {
        if (!value) onClose();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>模拟调用检查</DialogTitle>
          <DialogDescription>
            使用{employee.agent.name}已保存的许可。只演示校验，不请求服务或执行程序。
          </DialogDescription>
        </DialogHeader>
        <FormField label={<>MCP 能力</>}>
          <SelectField
            value={selected}
            options={available.map((item) => ({
              value: item.capabilityId,
              label: capabilities.find((capability) => capability.id === item.capabilityId)!.name,
            }))}
            onValueChange={(value) => {
              setSelected(value);
              const next = available.find((item) => item.capabilityId === value);
              const nextConnection = connections.find((item) => item.id === next?.connectionId);
              setToolName(next?.tools[0] || nextConnection?.approved_catalog[0]?.name || "");
              setResult(null);
            }}
            aria-label="试运行 MCP 能力"
            className="w-full"
          />
        </FormField>
        <FormField label={<>操作</>}>
          <SelectField
            value={toolName}
            options={names.map((name) => ({
              value: name,
              label: connection ? toolDisplayName(connection, name) : name,
            }))}
            onValueChange={(value) => {
              setToolName(value);
              setResult(null);
            }}
            aria-label="试运行操作"
            className="w-full min-w-0 whitespace-normal text-left"
          />
        </FormField>
        <p className="type-caption">
          账号：{connection?.name || "未配置"}。依次核对员工许可、已确认定义、远端目标定义。
        </p>
        <Button
          disabled={!toolName}
          onClick={() => setResult(evaluateDemoCall(assignment, connection, toolName))}
        >
          执行模拟检查
        </Button>
        {result && (
          <div
            role="status"
            className={
              result.ok
                ? "rounded-control bg-success-bg p-4 text-sm text-success"
                : "rounded-control bg-warning-bg p-4 text-sm text-warning"
            }
          >
            <p className="mb-1 font-medium">{result.ok ? "模拟调用成功" : "调用已拦截"}</p>
            {result.message}
            <p className="mt-3 text-xs">本次检查不会批准新目录、修改名称、授权新工具或切换账号。</p>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
