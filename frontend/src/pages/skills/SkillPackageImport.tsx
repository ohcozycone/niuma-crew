import { mutationOutcome } from "@/lib/failures/resolve";
import { useFailureState } from "@/state/shared/useFailureState";
import { FailureNotice } from "@/components/failure/FailureNotice";
import { FormField } from "@/components/common/FormField";
import { Card } from "@/components/ui/Card";
import { useState } from "react";
import { useWorkspaceData } from "@/state/workspace/useWorkspaceData";
import { useNavigate } from "react-router";
import { Upload } from "lucide-react";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { previewSkillPackage, type SkillImportPreview } from "@/lib/api/skills";
export async function base64File(file: File): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let raw = "";
  for (let offset = 0; offset < bytes.length; offset += 8192)
    raw += String.fromCharCode(...bytes.subarray(offset, offset + 8192));
  return btoa(raw);
}
export function SkillPackageImport() {
  const navigate = useNavigate();
  const data = useWorkspaceData();
  const [archive, setArchive] = useState("");
  const [preview, setPreview] = useState<SkillImportPreview | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const { failure, setError } = useFailureState();
  return (
    <Card as="section" variant="outline" className="form-panel space-y-6">
      <h2 className="type-title flex items-center gap-2">
        <Upload size={18} />
        导入技能包
      </h2>
      <p className="type-description">
        上传含 SKILL.md 的 ZIP 包。先检查文件与标准元数据，确认后保存；上传不会执行 scripts
        或安装依赖。
      </p>
      <Input
        aria-label="选择技能 ZIP 技能包"
        type="file"
        accept=".zip,application/zip"
        disabled={busy}
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (!file) return;
          if (file.size > 12 * 1024 * 1024) {
            setError("技能包不能超过 12 MiB。");
            return;
          }
          setBusy(true);
          setError("");
          setPreview(null);
          void base64File(file)
            .then(async (encoded) => {
              const data = await previewSkillPackage(encoded);
              setArchive(encoded);
              setPreview(data);
              setName(data.name);
            })
            .catch((failure) => setError(failure))
            .finally(() => setBusy(false));
        }}
      />
      {busy && <p role="status">正在处理技能包…</p>}
      {preview && (
        <>
          <FormField label={<>展示名称</>}>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </FormField>
          <p className="type-caption">
            协议名：{preview.protocol_name} · {preview.files.length} 个文件
          </p>
          <p className="text-sm text-text-muted">{preview.description}</p>
          <ul className="max-h-60 space-y-1 overflow-auto text-sm">
            {preview.files.map((file) => (
              <li key={file.path} className="break-all">
                {file.path} <span className="text-text-muted">{file.size} B</span>
              </li>
            ))}
          </ul>
          {preview.warnings.map((warning) => (
            <p key={warning} className="text-sm text-text-muted">
              {warning}
            </p>
          ))}
          <Button
            type="button"
            disabled={busy || !name.trim()}
            onClick={() => {
              setBusy(true);
              setError("");
              void data.skills
                .importPackage(archive, name.trim())
                .then((skill) => {
                  navigate(`/skills/${skill.id}`);
                })
                .catch((failure) => {
                  setError(failure);
                  setBusy(false);
                });
            }}
          >
            确认导入并编辑
          </Button>
        </>
      )}
      {failure && (
        <FailureNotice
          failure={failure}
          context={{ operation: "mutation", outcome: mutationOutcome(failure) }}
        />
      )}
    </Card>
  );
}
