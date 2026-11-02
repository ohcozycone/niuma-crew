import { useState } from "react";
import { BrandLogo } from "@/components/brand/BrandLogo";
import { ThemeSwitcher } from "@/components/theme/ThemeSwitcher";
import { SelectField } from "@/components/ui/SelectField";
import { FailureState } from "@/components/failure/FailureState";
import { FailureNotice } from "@/components/failure/FailureNotice";
import { Button } from "@/components/ui/Button";
import type { Failure, FailureFamily } from "@/lib/failures/types";

const samples: Record<FailureFamily, Failure> = {
  "not-found": {
    source: "http",
    status: 404,
    code: "agent_not_found",
    message: "当前链接没有对应的可访问员工信息。",
  },
  access: {
    source: "http",
    status: 403,
    code: "permission_denied",
    message: "当前账号没有此页面的访问权限，可以返回数字员工。",
  },
  connection: {
    source: "network",
    status: null,
    code: "client_connection_failed",
    message: "连接暂时未能建立，请稍后重新连接。",
  },
  service: {
    source: "http",
    status: 500,
    code: "internal_error",
    message: "服务处理遇到了问题，请稍后重新检查。",
    requestId: "example-request",
  },
  waiting: {
    source: "http",
    status: 429,
    code: "rate_limited",
    message: "操作有点频繁，请稍后再试。",
  },
  configuration: {
    source: "http",
    status: 409,
    code: "model_not_configured",
    message: "这位员工还未装配可用的大脑，请检查配置后再试。",
  },
};
const labels: Record<FailureFamily, string> = {
  "not-found": "内容未找到",
  access: "身份与权限",
  connection: "连接问题",
  service: "服务异常",
  waiting: "等待与限流",
  configuration: "配置与冲突",
};

export function FailureExamples({ standalone = false }: { standalone?: boolean }) {
  const [family, setFamily] = useState<FailureFamily>("not-found");
  const [variant, setVariant] = useState("full");
  const [message, setMessage] = useState("");
  const [retryAt, setRetryAt] = useState<number>();
  const [noImage, setNoImage] = useState(false);
  const failure = { ...samples[family], ...(family === "waiting" ? { retryAt } : {}) };
  const actions =
    variant === "minimal" || variant === "short"
      ? []
      : [
          ...(family === "configuration"
            ? [
                {
                  label: "检查配置",
                  kind: "configure" as const,
                  onClick: () => setMessage("示例：打开有权限的配置入口。"),
                },
              ]
            : family !== "access" && family !== "not-found"
              ? [
                  {
                    label: "重新检查",
                    kind: "retry" as const,
                    onClick: () => setMessage("示例：重新读取当前资源，不重新提交工作。"),
                  },
                ]
              : []),
          {
            label: "返回数字员工",
            kind: "return" as const,
            onClick: () => setMessage("示例：返回数字员工，保留原列表条件。"),
          },
        ];
  return (
    <div
      className={
        standalone ? "flex min-h-dvh flex-col bg-canvas" : "my-6 flex min-h-144 flex-col bg-canvas"
      }
    >
      <header className="flex flex-wrap items-center gap-4 border-b border-border px-6 py-4">
        {standalone && <BrandLogo />}
        <span className="text-sm text-text-muted">错误状态组件示例</span>
        <SelectField
          aria-label="错误类型"
          className="w-44 max-w-full"
          value={family}
          onValueChange={(value) => {
            setFamily(value as FailureFamily);
            setMessage("");
            setRetryAt(undefined);
          }}
          options={[
            ...Object.entries(labels).map(([value, label]) => ({ value: value, label: label })),
          ]}
        />
        <SelectField
          aria-label="内容组合"
          className="w-48 max-w-full"
          value={variant}
          onValueChange={(value) => setVariant(value)}
          options={[
            { value: "full", label: "完整内容" },
            { value: "short", label: "短说明 · 无操作" },
            { value: "minimal", label: "仅错误码与标题" },
            { value: "long", label: "长文案" },
          ]}
        />
        <Button variant="outline" onClick={() => setNoImage((value) => !value)}>
          {noImage ? "显示配图" : "无图降级"}
        </Button>
        {family === "waiting" && (
          <Button variant="outline" onClick={() => setRetryAt(Date.now() + 8000)}>
            模拟等待 8 秒
          </Button>
        )}
        <ThemeSwitcher />
      </header>
      <div className="flex flex-1 flex-col">
        <FailureState
          failure={failure}
          context={{ operation: "initial-read", resource: "agent" }}
          illustration={!noImage}
          description={
            variant === "minimal"
              ? ""
              : variant === "short"
                ? samples[family].message
                : variant === "long"
                  ? `${samples[family].message} 如果这是之前保存的链接，可以回到所属列表重新查找。请先核对当前内容，再决定下一步操作；这里的文字用于检查换行与长内容，不会发起实际业务请求。`
                  : undefined
          }
          actions={actions}
        />
      </div>
      {message && (
        <p role="status" className="m-6 text-sm">
          {message}
        </p>
      )}
      {!standalone && (
        <FailureNotice
          failure={samples.connection}
          context={{ operation: "refresh", hasUsableData: true }}
          actions={[
            {
              label: "重新加载",
              kind: "retry",
              onClick: () => setMessage("示例：刷新失败时保留原内容。"),
            },
          ]}
        />
      )}
    </div>
  );
}
