import { FailureNotice } from "@/components/failure/FailureNotice";
import { toFailure, mutationOutcome } from "@/lib/failures/resolve";
import type { Failure } from "@/lib/failures/types";
import { FormField } from "@/components/common/FormField";
import { Card } from "@/components/ui/Card";
import { ConfirmActionDialog } from "@/components/common/ConfirmActionDialog";
import { useState } from "react";
import { useEditingRegistration } from "@/state/editing/useEditing";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import {
  discoverTools,
  approveTools,
  discardCatalog,
  saveAnnotations,
  toolLabel,
  type ToolConnection,
  type CatalogAnnotation,
} from "@/lib/api/tools";

export function ToolCatalogEditor({
  connection,
  onChange,
  editable,
}: {
  connection: ToolConnection;
  onChange: (value: ToolConnection) => void;
  editable: boolean;
}) {
  const [annotations, setAnnotations] = useState<Record<string, CatalogAnnotation>>(
    connection.tool_annotations ?? {},
  );
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [notice, setNotice] = useState("");
  const [confirming, setConfirming] = useState(false);
  useEditingRegistration({
    dirty: JSON.stringify(annotations) !== JSON.stringify(connection.tool_annotations ?? {}),
    saving: busy,
    isSaving: () => busy,
    discard: () => setAnnotations(connection.tool_annotations ?? {}),
  });
  async function perform(action: () => Promise<ToolConnection>) {
    setBusy(true);
    setFailure(null);
    try {
      onChange(await action());
    } catch (e) {
      setFailure(toFailure(e));
    } finally {
      setBusy(false);
    }
  }
  const approved = connection.approved_catalog;
  const candidate = connection.discovery_candidate?.tools;
  const names = new Set((candidate ?? approved).map((tool) => tool.name));
  const tools = [...(candidate ?? approved), ...approved.filter((tool) => !names.has(tool.name))];
  const removals = approved.filter((tool) => !names.has(tool.name));
  const changes = (candidate ?? []).filter((tool) =>
    approved.some(
      (prior) => prior.name === tool.name && prior.descriptor_hash !== tool.descriptor_hash,
    ),
  );
  function applyCandidate() {
    void perform(async () => {
      const result = await approveTools(connection);
      setNotice("工具列表已保存；新增工具仍需到员工页面主动勾选。");
      setConfirming(false);
      return result;
    });
  }
  return (
    <section className="space-y-4 border-t border-border pt-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="type-title">可用工具</h3>
        {editable && !!editing && (
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={() => {
                setAnnotations(connection.tool_annotations ?? {});
                setEditing(null);
              }}
            >
              取消展示修改
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={busy}
              onClick={() => void perform(() => saveAnnotations(connection, annotations))}
            >
              保存展示设置
            </Button>
          </div>
        )}
        {editable && connection.kind !== "native" && (
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              disabled={busy || !connection.enabled}
              onClick={() =>
                void perform(async () => {
                  const result = await discoverTools(connection.id);
                  setNotice(
                    result.discovery_candidate
                      ? "已读取远端列表，请核对变化后应用。"
                      : "工具列表已是最新，没有变化。",
                  );
                  return result;
                })
              }
            >
              {approved.length ? "检查工具更新" : "读取工具列表"}
            </Button>
            {candidate && (
              <>
                <Button
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    removals.length || changes.length ? setConfirming(true) : applyCandidate()
                  }
                >
                  {approved.length ? "应用工具更新" : "确认工具列表"}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  disabled={busy}
                  onClick={() =>
                    void perform(async () => {
                      const result = await discardCatalog(connection);
                      setNotice("已忽略此次读取结果，继续保留原列表；远端服务不会因此回滚。");
                      return result;
                    })
                  }
                >
                  暂不更新
                </Button>
              </>
            )}
          </div>
        )}
      </div>
      <p className="type-description">
        当前已保存 {approved.length}{" "}
        项。检查只读取工具清单，不执行工具；新列表需确认后才用于员工装配。
      </p>
      {notice && (
        <p role="status" className="type-caption">
          {notice}
        </p>
      )}
      {(connection.discovery_candidate?.instructions || connection.approved_instructions) && (
        <Card as="details" variant="muted" radius="control" className="p-3 text-sm">
          <summary className="cursor-pointer text-text-muted">
            查看{candidate ? "本次读取的" : "当前保存的"}服务说明
          </summary>
          <p className="mt-2 whitespace-pre-wrap break-words">
            {connection.discovery_candidate?.instructions ?? connection.approved_instructions}
          </p>
          <p className="mt-2 type-caption">
            由 MCP 服务提供，确认后作为来源标明的使用指引送入模型；不改变平台权限。
          </p>
        </Card>
      )}
      {candidate && (
        <p role="status" className="type-label">
          待应用：新增{" "}
          {candidate.filter((item) => !approved.some((prior) => prior.name === item.name)).length}{" "}
          项，修改{" "}
          {
            candidate.filter((item) =>
              approved.some(
                (prior) =>
                  prior.name === item.name && prior.descriptor_hash !== item.descriptor_hash,
              ),
            ).length
          }{" "}
          项，移除 {approved.filter((item) => !names.has(item.name)).length}{" "}
          项。应用前保留原列表；新增和修改的工具不会自动获得员工授权。
        </p>
      )}
      {!tools.length && (
        <p className="type-caption">尚未读取工具列表。请先保存访问设置，再点击“读取工具列表”。</p>
      )}
      <div className="space-y-4">
        {tools.map((tool) => {
          const prior = approved.find((item) => item.name === tool.name);
          const state = !candidate
            ? "已确认"
            : !names.has(tool.name)
              ? "移除"
              : !prior
                ? "新增"
                : prior.descriptor_hash === tool.descriptor_hash
                  ? "未改变"
                  : "定义改变";
          const annotation = annotations[tool.name] ?? { display_name: "", note: "" };
          return (
            <Card as="article" key={tool.name} className="space-y-3 p-4">
              <div className="flex flex-wrap justify-between gap-2">
                <strong className="break-all text-sm">{toolLabel(connection, tool.name)}</strong>
                <span className="type-caption">{state}</span>
              </div>
              <p className="line-clamp-2 text-sm text-text-muted">
                {annotation.note || tool.description || "服务未提供说明"}
              </p>
              {editable && (
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => setEditing(editing === tool.name ? null : tool.name)}
                >
                  {editing === tool.name ? "收起编辑" : "编辑展示"}
                </Button>
              )}
              {editable && editing === tool.name && (
                <div className="grid gap-3">
                  <FormField className="max-w-sm" label={<>展示名称（可选）</>}>
                    <Input
                      aria-label={`${tool.name}展示名称`}
                      maxLength={100}
                      value={annotation.display_name}
                      onChange={(e) =>
                        setAnnotations((current) => ({
                          ...current,
                          [tool.name]: { ...annotation, display_name: e.target.value },
                        }))
                      }
                    />
                  </FormField>
                  <FormField label={<>补充说明（仅展示）</>}>
                    <Textarea
                      aria-label={`${tool.name}补充说明`}
                      rows={3}
                      maxLength={2000}
                      value={annotation.note}
                      onChange={(e) =>
                        setAnnotations((current) => ({
                          ...current,
                          [tool.name]: { ...annotation, note: e.target.value },
                        }))
                      }
                    />
                  </FormField>
                </div>
              )}
              <details className="text-sm">
                <summary className="cursor-pointer text-text-muted">查看原始工具说明</summary>
                <p className="mt-2 whitespace-pre-wrap break-words text-text-muted">
                  {tool.description || "服务未提供说明"}
                </p>
              </details>
              <details className="text-sm">
                <summary className="cursor-pointer text-text-muted">查看原始参数定义</summary>
                <pre className="mt-2 max-h-64 overflow-auto rounded-small bg-muted p-3 text-xs">
                  {JSON.stringify(tool.input_schema ?? {}, null, 2)}
                </pre>
                {candidate && prior && prior.descriptor_hash !== tool.descriptor_hash && (
                  <>
                    <p className="mt-2">原批准定义：</p>
                    <pre className="max-h-48 overflow-auto p-3 text-xs">
                      {JSON.stringify(prior.input_schema ?? {}, null, 2)}
                    </pre>
                  </>
                )}
              </details>
            </Card>
          );
        })}
      </div>
      <FailureNotice
        failure={failure}
        context={{
          operation: "mutation",
          resource: "connection",
          outcome: mutationOutcome(failure),
        }}
      />
      <ConfirmActionDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={`更新「${connection.name}」的工具列表？`}
        description={`本次会移除 ${removals.length} 项、修改 ${changes.length} 项工具定义。确认后立即生效，相关员工可能需要重新配置工具授权。新增和修改的工具不会自动获得授权。`}
        confirmLabel="确认应用更新"
        busy={busy}
        onConfirm={applyCandidate}
      >
        <FailureNotice
          failure={failure}
          context={{
            operation: "mutation",
            resource: "connection",
            outcome: mutationOutcome(failure),
          }}
        />
      </ConfirmActionDialog>
    </section>
  );
}
