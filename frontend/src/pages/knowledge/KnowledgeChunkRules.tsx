import { Input } from "@/components/ui/Input";
import { FormField } from "@/components/common/FormField";
import type { ChunkingRules } from "@/lib/api/knowledge";

export type ChunkRuleInputs = { size: string; overlap: string; minimum: string };

export function resolveChunkRules(value: ChunkRuleInputs): { rules: ChunkingRules; error: string } {
  const size = value.size === "" ? 800 : Number(value.size);
  const overlap = value.overlap === "" ? 120 : Number(value.overlap);
  const minimum =
    value.minimum === "" ? Math.max(0, Math.min(200, size - overlap)) : Number(value.minimum);
  const rules = { chunk_size: size, chunk_overlap: overlap, min_section_chars: minimum };
  const error = ![size, overlap, minimum].every(Number.isInteger)
    ? "请输入整数。"
    : size < 100 || size > 2000 || overlap < 0 || overlap > 1000 || minimum < 0 || minimum > 2000
      ? "切分长度为100—2000，重叠为0—1000，短章节阈值为0—2000。"
      : overlap >= size
        ? "重叠必须小于切分字符数。"
        : minimum > size - overlap
          ? "短章节阈值不能超过切分字符数减去重叠字符数。"
          : "";
  return { rules, error };
}

export function KnowledgeChunkRules({
  value,
  onChange,
  disabled = false,
}: {
  value: ChunkRuleInputs;
  onChange: (next: ChunkRuleInputs) => void;
  disabled?: boolean;
}) {
  const { rules, error } = resolveChunkRules(value);
  return (
    <fieldset disabled={disabled} className="space-y-3">
      <legend className="text-sm font-medium">切分规则</legend>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <FormField label="切分字符数">
          <Input
            type="number"
            min={100}
            max={2000}
            value={value.size}
            placeholder="默认800"
            onChange={(e) => onChange({ ...value, size: e.target.value })}
          />
        </FormField>
        <FormField label="重叠字符数">
          <Input
            type="number"
            min={0}
            max={1000}
            value={value.overlap}
            placeholder="默认120"
            onChange={(e) => onChange({ ...value, overlap: e.target.value })}
          />
        </FormField>
        <FormField label="短章节合并阈值">
          <Input
            type="number"
            min={0}
            max={Math.max(0, rules.chunk_size - rules.chunk_overlap)}
            value={value.minimum}
            placeholder={`默认${Math.max(0, Math.min(200, rules.chunk_size - rules.chunk_overlap))}`}
            onChange={(e) => onChange({ ...value, minimum: e.target.value })}
          />
        </FormField>
      </div>
      <p className="text-xs text-text-muted">
        留空继承平台默认。仅合并同一父标题下相邻且短于阈值的章节，保留标题与来源；0关闭合并。
      </p>
      <p className={`text-xs ${error ? "text-danger" : "text-text-muted"}`} role="status">
        生效规则：{rules.chunk_size}字符 / 重叠{rules.chunk_overlap}字符 / 短章节阈值
        {rules.min_section_chars}字符
        {error && `；${error}`}
      </p>
    </fieldset>
  );
}
