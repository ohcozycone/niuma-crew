import { FailureNotice } from "@/components/failure/FailureNotice";
import { clientFailure, toFailure } from "@/lib/failures/resolve";
import type { Failure } from "@/lib/failures/types";
import { Card } from "@/components/ui/Card";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/Dialog";
import { previewMcpConfig } from "@/lib/api/tools";

export type McpImportEntry = Awaited<ReturnType<typeof previewMcpConfig>>["entries"][number];
export function importSecret(value: unknown) {
  return typeof value === "string" &&
    !/(?:\$\{|\{\{|^<|^YOUR[_ -]|^REPLACE[_ -]|^PASTE[_ -])/i.test(value.trim())
    ? value
    : "";
}

export function McpQuickImport({
  open,
  onOpenChange,
  hasValues,
  onFill,
}: {
  open: boolean;
  onOpenChange: (value: boolean) => void;
  hasValues: boolean;
  onFill: (
    entry: McpImportEntry,
    values: { credential: string; environment: Record<string, string> },
  ) => void;
}) {
  const [text, setText] = useState("");
  const [entries, setEntries] = useState<McpImportEntry[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [overwrite, setOverwrite] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [busy, setBusy] = useState(false);
  const generation = useRef(0);
  useEffect(() => {
    if (!open) {
      generation.current++;
      setText("");
      setEntries([]);
      setWarnings([]);
      setFailure(null);
      setOverwrite(false);
      setBusy(false);
    }
  }, [open]);
  function fill(entry: McpImportEntry) {
    const raw = JSON.parse(text);
    const source = raw.mcpServers?.[entry.name];
    const firstHeader = source ? Object.values(source.headers ?? {})[0] : "";
    const secret = importSecret(firstHeader);
    onFill(entry, {
      credential:
        entry.auth_type === "bearer" && secret.startsWith("Bearer ") ? secret.slice(7) : secret,
      environment: Object.fromEntries(
        (entry.env_keys ?? []).map((key) => [key, importSecret(source?.env?.[key])]),
      ),
    });
    onOpenChange(false);
  }
  async function parse() {
    const request = ++generation.current;
    setBusy(true);
    setFailure(null);
    try {
      const result = await previewMcpConfig(text);
      if (request !== generation.current) return;
      setWarnings(result.warnings ?? []);
      if (result.entries.length === 1 && !hasValues && !result.warnings?.length)
        fill(result.entries[0]);
      else setEntries(result.entries);
    } catch (error) {
      if (request === generation.current) setFailure(toFailure(error));
    } finally {
      if (request === generation.current) setBusy(false);
    }
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="wide">
        <DialogHeader>
          <DialogTitle>快捷导入 MCP</DialogTitle>
          <DialogDescription>
            粘贴官方客户端 JSON 或 Registry
            服务描述，也可以选择文件。解析只回填当前表单，保存并测试后才连接。
          </DialogDescription>
        </DialogHeader>
        <Textarea
          disabled={busy}
          aria-label="MCP 配置 JSON"
          rows={8}
          maxLength={65536}
          value={text}
          onChange={(event) => {
            setText(event.target.value);
            setEntries([]);
            setWarnings([]);
            setFailure(null);
          }}
          placeholder={'{"mcpServers":{"example":{"url":"https://example.com/mcp"}}}'}
        />
        <Input
          disabled={busy}
          type="file"
          aria-label="上传 MCP 配置文件"
          accept=".json,application/json"
          onChange={(event) => {
            const file = event.target.files?.[0];
            const current = ++generation.current;
            if (file) {
              if (file.size > 65536)
                setFailure(clientFailure("mcp_config_too_large", "配置文件不能超过 64 KiB。"));
              else
                void file
                  .text()
                  .then((value) => {
                    if (generation.current === current) {
                      setText(value);
                      setEntries([]);
                      setFailure(null);
                    }
                  })
                  .catch(() => {
                    if (generation.current === current)
                      setFailure(clientFailure("file_read_failed", "无法读取文件，请重新选择。"));
                  });
            }
            event.target.value = "";
          }}
        />
        <FailureNotice
          failure={failure}
          context={{ operation: "mutation", resource: "connection" }}
        />
        {warnings.map((warning, index) => (
          <p key={index} className="type-caption">
            {warning}
          </p>
        ))}
        {!!entries.length && hasValues && (
          <label className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              checked={overwrite}
              onChange={(event) => setOverwrite(event.target.checked)}
            />
            覆盖当前的名称、接入配置和访问设置；未导入的功能说明保留。
          </label>
        )}
        {entries.map((entry, index) => (
          <Card
            as="div"
            variant="muted"
            radius="control"
            key={`${entry.transport}:${index}`}
            className="flex flex-wrap items-center justify-between gap-3 p-3"
          >
            <span className="min-w-0 break-all text-sm">
              {entry.name} ·{" "}
              {entry.transport === "stdio"
                ? `本地 ${entry.command} ${(entry.args ?? []).join(" ")}`
                : `远程 ${entry.url}`}
            </span>
            <Button
              type="button"
              variant="outline"
              disabled={hasValues && !overwrite}
              onClick={() => fill(entry)}
            >
              填入接入表单
            </Button>
          </Card>
        ))}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button disabled={busy || !text.trim()} onClick={() => void parse()}>
            {busy ? "正在解析…" : "解析并填入"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
