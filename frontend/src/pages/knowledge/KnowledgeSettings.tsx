import { useRef, useState, type FormEvent } from "react";
import { Settings2 } from "lucide-react";
import type { KnowledgeBase } from "@/lib/api/knowledge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { FormField } from "@/components/common/FormField";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/Dialog";
import { useWorkspaceData } from "@/state/workspace/useWorkspaceData";
import { useSaveOperation } from "@/state/editing/useSaveOperation";
import { useEditingRegistration } from "@/state/editing/useEditing";
import { FailureNotice } from "@/components/failure/FailureNotice";
import { mutationOutcome } from "@/lib/failures/resolve";
import { KnowledgeChunkRules, resolveChunkRules } from "./KnowledgeChunkRules";

export function KnowledgeSettings({ library }: { library: KnowledgeBase }) {
  const store = useWorkspaceData().knowledge;
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [size, setSize] = useState("");
  const [overlap, setOverlap] = useState("");
  const [minimum, setMinimum] = useState("");
  const baseline = useRef("");
  const revision = useRef(1);
  const save = useSaveOperation();
  const current = JSON.stringify([name, description, size, overlap, minimum]);
  const dirty = open && current !== baseline.current;
  const invalid = !!resolveChunkRules({ size, overlap, minimum }).error;
  function load(source = library) {
    const values = [
      source.name,
      source.description,
      source.chunk_size?.toString() ?? "",
      source.chunk_overlap?.toString() ?? "",
      source.min_section_chars?.toString() ?? "",
    ];
    setName(values[0]);
    setDescription(values[1]);
    setSize(values[2]);
    setOverlap(values[3]);
    setMinimum(values[4]);
    baseline.current = JSON.stringify(values);
    revision.current = source.revision ?? 1;
  }
  useEditingRegistration({
    dirty,
    saving: save.saving,
    isSaving: () => save.saving,
    discard: () => setOpen(false),
  });
  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      await save.run(() =>
        store.update(library.id, {
          expected_revision: revision.current,
          name: name.trim(),
          description: description.trim(),
          chunk_size: size === "" ? null : Number(size),
          chunk_overlap: overlap === "" ? null : Number(overlap),
          min_section_chars: minimum === "" ? null : Number(minimum),
        }),
      );
      setOpen(false);
    } catch (error) {
      save.setError(error);
    }
  }
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (save.saving) return;
        if (!next && dirty && !window.confirm("放弃尚未保存的知识库设置？")) return;
        if (next) {
          load();
          save.clearError();
        }
        setOpen(next);
      }}
    >
      <DialogTrigger render={<Button variant="outline" />}>
        <Settings2 size={16} />
        知识库设置
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>知识库设置</DialogTitle>
          <DialogDescription>
            维护资料范围与切分规则。修改规则不自动重处理已有文件。
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          <FormField label="知识库名称">
            <Input
              required
              maxLength={100}
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={save.saving}
            />
            <p className="text-xs text-text-muted">
              写清业务主题和适用对象，避免“资料1”等模糊名称。
            </p>
          </FormField>
          <FormField label="用途与内容范围（选填）">
            <Textarea
              maxLength={1000}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={save.saving}
            />
            <p className="text-xs text-text-muted">
              包含哪些内容、适合回答什么问题？与实际资料保持一致，准确比长度重要。
            </p>
          </FormField>
          <KnowledgeChunkRules
            value={{ size, overlap, minimum }}
            onChange={(next) => {
              setSize(next.size);
              setOverlap(next.overlap);
              setMinimum(next.minimum);
            }}
            disabled={save.saving}
          />
          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled={save.saving}
            onClick={() => {
              setSize("");
              setOverlap("");
              setMinimum("");
            }}
          >
            恢复默认规则
          </Button>
          <FailureNotice
            failure={save.failure}
            context={{
              operation: "mutation",
              resource: "knowledge",
              outcome: mutationOutcome(save.failure),
            }}
          />
          {save.failure?.status === 409 && (
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                const resource = store.library(library.id);
                resource.invalidate();
                void resource.ensure().then(() => {
                  const latest = resource.getSnapshot();
                  if (latest.data && !latest.failure) {
                    load(latest.data);
                    save.clearError();
                  }
                });
              }}
            >
              载入最新设置
            </Button>
          )}
          <DialogFooter>
            <Button type="submit" disabled={save.saving || invalid || !name.trim()}>
              {save.saving ? "正在保存…" : "保存设置"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
