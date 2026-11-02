import { Card } from "@/components/ui/Card";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { request } from "@/lib/api/http";
import { FailureNotice } from "@/components/failure/FailureNotice";
import { toFailure } from "@/lib/failures/resolve";
import type { Failure } from "@/lib/failures/types";

type Revisions = { revision?: number; config_revision?: number; credential_revision?: number };
const fields: Record<string, string> = {
  name: "名称",
  code: "编号",
  category: "分类",
  description: "简介",
  role_label: "岗位",
  avatar_id: "头像",
  system_prompt: "岗位指令",
  instructions: "工作指引",
  model_connection_id: "大脑",
  model_id: "模型标识",
  is_active: "启用",
  enabled: "启用",
  is_favorite: "收藏",
  skill_assignments: "技能装配",
  configuration_schema: "参数规范",
  example_tasks: "示例任务",
  deliverables: "交付说明",
  input_description: "所需输入",
  output_description: "交付内容",
  example: "示例",
  has_api_key: "Key 已配置",
};
export function ConfigurationConflict({
  resource,
  onUseRevisions,
}: {
  resource: string;
  onUseRevisions: (value: Revisions) => void;
}) {
  const [latest, setLatest] = useState<Record<string, unknown> | null>(null);
  const [revisions, setRevisions] = useState<Revisions>({});
  const [failure, setFailure] = useState<Failure | null>(null);
  const [loading, setLoading] = useState(false);
  async function load() {
    setLoading(true);
    setFailure(null);
    try {
      const data = await request<Record<string, unknown>>(resource);
      setRevisions({
        revision: data.revision as number | undefined,
        config_revision: data.config_revision as number | undefined,
        credential_revision: data.credential_revision as number | undefined,
      });
      if (typeof data.model_connection_id === "string") {
        const connection = await request<{ name: string; model_id: string }>(
          `model-connections/${data.model_connection_id}`,
        );
        data.model_connection_id = `${connection.name} · ${connection.model_id}`;
      }
      if (Array.isArray(data.skill_assignments))
        data.skill_assignments = data.skill_assignments.map(
          (value: { name: string; enabled: boolean; parameters: unknown }) => ({
            名称: value.name,
            启用: value.enabled,
            参数: value.parameters,
          }),
        );
      setLatest(data);
    } catch (failure) {
      setFailure(toFailure(failure));
    } finally {
      setLoading(false);
    }
  }
  return (
    <Card as="div" variant="outline" radius="panel" className="my-4 p-4 text-sm space-y-3">
      <p>当前输入已保留。请核对服务器最新配置，再决定是否用当前草稿覆盖对应配置。</p>
      <Button type="button" variant="outline" disabled={loading} onClick={() => void load()}>
        {loading ? "正在读取…" : "查看服务器最新配置"}
      </Button>
      {failure && <FailureNotice compact failure={failure} context={{ operation: "refresh" }} />}
      {latest && (
        <>
          <dl className="max-h-72 overflow-y-auto space-y-2">
            {Object.entries(latest)
              .filter(([key]) => fields[key])
              .map(([key, value]) => (
                <div key={key}>
                  <dt className="font-medium">{fields[key]}</dt>
                  <dd className="whitespace-pre-wrap break-words text-text-muted">
                    {typeof value === "string"
                      ? value || "未填写"
                      : typeof value === "boolean"
                        ? value
                          ? "是"
                          : "否"
                        : value == null
                          ? "未配置"
                          : JSON.stringify(value, null, 2)}
                  </dd>
                </div>
              ))}
          </dl>
          <p>采用新修订不会立即保存；下次点击保存将提交当前草稿。</p>
          <Button type="button" variant="outline" onClick={() => onUseRevisions(revisions)}>
            采用最新修订并保留草稿
          </Button>
        </>
      )}
    </Card>
  );
}
