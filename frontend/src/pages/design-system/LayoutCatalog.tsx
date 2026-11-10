import { FormField } from "@/components/common/FormField";
import { useState } from "react";
import { layoutRoles } from "@/design-system/spec";
import { useThemeValues } from "./useThemeValues";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";

/** The catalogue reads the same computed tokens and layout utilities as product pages. */
export function LayoutCatalog() {
  const { values } = useThemeValues();
  const [compact, setCompact] = useState(false);
  return (
    <div className="space-y-8">
      <p className="article-measure text-sm leading-7 text-text-muted">
        先确定内容所需的空间，再选择页面宽度。资源与配置页沿用各自预算；对话使用居中阅读外框，
        常规为 960px，1920px 起放宽到 1120px，2560px 起为 1280px。正文行长单独控制，
        表格与代码使用整列空间。这些是项目设计取值，并非行业统一标准。
      </p>
      <dl className="capability-grid">
        {Object.entries(layoutRoles).map(([token, role]) => (
          <div key={token} className="min-w-0 border-t border-border py-4">
            <dt className="text-sm font-semibold">{role.label}</dt>
            <dd className="mt-2 text-sm tabular-nums">{values[token] || "—"}</dd>
            <dd className="mt-1 text-xs leading-6 text-text-muted">{role.usage}</dd>
          </div>
        ))}
      </dl>
      <section className="space-y-4" aria-label="容器响应样板">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="type-title">同一组件，按容器重排</h3>
          <Button variant="outline" onClick={() => setCompact((value) => !value)}>
            {compact ? "使用全部空间" : "预览窄容器"}
          </Button>
        </div>
        <div className={compact ? "@container max-w-(--os-preview-width)" : "@container"}>
          <Card variant="outline" className="form-panel">
            <div className="form-grid">
              <FormField label={<>展示名称</>}>
                <Input placeholder="例如：知识专员" />
              </FormField>
              <FormField label={<>岗位分类</>}>
                <Input placeholder="例如：知识管理" />
              </FormField>
              <p className="col-span-full text-xs leading-6 text-text-muted">
                字段达到双列预算才并排；放入窄预览时仍保留标签、输入和说明。
              </p>
            </div>
          </Card>
        </div>
      </section>
      <div className="article-measure space-y-3 text-sm leading-7 text-text-muted">
        <p>
          外壳在 768px
          切换侧栏；资源和配置页留白按工作区计算，对话在适中限宽内保留边距、宽屏再扩展；卡片和字段按自己的容器响应。
        </p>
        <p>完整组件分类、公式、响应式矩阵、设计取舍和官方参考由仓库设计规范维护。</p>
      </div>
    </div>
  );
}
