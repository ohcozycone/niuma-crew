import { Card } from "@/components/ui/Card";
import { useState, type CSSProperties } from "react";
import { typographyRoles, cornerShapeExceptions } from "@/design-system/spec";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Switch } from "@/components/ui/Switch";
import { useThemeValues } from "./useThemeValues";
const typeClasses = {
  page: "type-page",
  section: "type-section",
  title: "type-title",
  label: "type-label",
  description: "type-description",
  body: "type-body",
  caption: "type-caption",
} as const;

export function TypographyCatalog() {
  const [smoothPreview, setSmoothPreview] = useState(false);
  const supportsSmoothCorners =
    typeof CSS !== "undefined" && CSS.supports("corner-shape", "squircle");
  const { values, declarations } = useThemeValues();
  const names = (prefix: string) =>
    Object.keys(declarations).filter((name) => name.startsWith(prefix));
  return (
    <div className={"space-y-6"}>
      <Card
        as="section"
        variant="outline"
        radius="panel"
        className="form-panel"
        aria-label="文字角色"
      >
        <h3 className={"font-semibold"}>文字角色</h3>
        <p className={"mt-2 mb-5 text-sm text-text-muted"}>
          每种角色组合字号、字重、行高、字距和前景。页面使用一组排版规则，数值引用共享尺度。
        </p>
        {Object.entries(typographyRoles).map(([role, meta]) => (
          <div
            key={role}
            data-typography-token={role}
            className={
              "grid min-w-0 gap-3 border-t border-border py-5 sm:grid-cols-[minmax(0,1fr)_auto]"
            }
          >
            <div className={"min-w-0"}>
              <p className={`${typeClasses[role as keyof typeof typeClasses]} break-words`}>
                {meta.sample}
              </p>
              <p className={"mt-2 text-xs text-text-muted"}>
                {meta.label} · {meta.usage}
              </p>
            </div>
            <div className={"text-xs leading-relaxed text-text-muted sm:text-right"}>
              <code className={"text-text"}>type-{role}</code>
              <p>
                {values[`--os-type-${role}-size`]} / {values[`--os-type-${role}-weight`]}
              </p>
              <p>
                行高 {values[`--os-type-${role}-leading`]} · 字距{" "}
                {values[`--os-type-${role}-tracking`]}
              </p>
            </div>
          </div>
        ))}
        <details className={"border-t border-border pt-4 text-xs text-text-muted"}>
          <summary>查看文字令牌的命名与引用</summary>
          <p className={"mt-3 leading-relaxed"}>
            例如 <code>--os-type-page-size</code> →{" "}
            <code>{declarations["--os-type-page-size"]}</code>。属性统一为
            size、weight、leading、tracking、color。
          </p>
        </details>
      </Card>
      <div className={"connection-grid"}>
        <Card as="section" variant="outline" radius="panel" className="form-panel">
          <h3 className={"mb-5 font-semibold"}>间距</h3>
          <div className={"flex flex-wrap items-end gap-5"}>
            {names("--os-space-").map((name) => (
              <div key={name} className={"space-y-2 text-center"}>
                <span
                  className={"mx-auto block w-6 rounded-small bg-action"}
                  style={{ height: values[name] }}
                />
                <code className={"block text-xs text-text-muted"}>
                  {name.replace("--os-space-", "")}
                </code>
                <p className={"text-xs"}>{values[name]}</p>
              </div>
            ))}
          </div>
          <p className={"mt-5 text-xs leading-relaxed text-text-muted"}>
            统一按 space 尺度组合，组件间距通过引用表达关系。
          </p>
        </Card>
        <Card as="section" variant="outline" radius="panel" className="form-panel">
          <h3 className={"mb-5 font-semibold"}>圆角</h3>
          <label className="mb-4 flex items-center justify-between gap-3 text-sm">
            超椭圆（本组可切换对比）
            <Switch
              checked={smoothPreview}
              onCheckedChange={setSmoothPreview}
              disabled={!supportsSmoothCorners}
            />
          </label>
          <div
            className="space-y-4"
            data-corner-preview={smoothPreview ? "squircle" : "round"}
            style={
              {
                "--os-corner-shape": smoothPreview ? "squircle" : "round",
              } as CSSProperties
            }
          >
            <div className={"grid grid-cols-2 gap-3 sm:grid-cols-4"}>
              {names("--os-radius-").map((name) => (
                <div
                  key={name}
                  className={
                    "flex h-20 flex-col items-center justify-center gap-2 bg-muted [corner-shape:var(--os-corner-shape)]"
                  }
                  style={{ borderRadius: values[name] }}
                >
                  <span className={"text-sm"}>{name.replace("--os-radius-", "")}</span>
                  <code className={"text-xs text-text-muted"}>{values[name]}</code>
                </div>
              ))}
            </div>
            <Card className="space-y-3 p-4">
              <h4 className="type-title">共用卡片表面</h4>
              <Input aria-label="圆角输入框样板" placeholder="输入框与按钮使用同一圆角入口" />
              <Button variant="outline" type="button">
                边框按钮样板
              </Button>
            </Card>
          </div>
          <p className="mt-4 text-xs leading-relaxed text-text-muted">
            正式界面当前使用 {values["--os-corner-shape"]}
            ；此开关仅预览本组，不保存主题偏好。
            {!supportsSmoothCorners && "当前浏览器暂不支持原生超椭圆，继续显示普通圆角。"}
          </p>
          <details className="mt-4 border-t border-border pt-4 text-xs text-text-muted">
            <summary>独立造型与验收范围</summary>
            <ul className="mt-3 space-y-2">
              {cornerShapeExceptions.map((entry) => (
                <li key={entry.file}>{entry.reason}</li>
              ))}
              <li>圆形状态点、开关滑块与头像保持圆形；SVG 原画与图标路径不参与表面圆角替换。</li>
            </ul>
          </details>
        </Card>
        <Card as="section" variant="outline" radius="panel" className="form-panel">
          <h3 className={"mb-4 font-semibold"}>控件与动效</h3>
          <dl className={"space-y-3 text-sm"}>
            {[...names("--os-control-"), ...names("--os-motion-")].map((name) => (
              <div key={name} className={"flex flex-wrap justify-between gap-2"}>
                <dt className={"break-all font-mono text-xs text-text-muted"}>{name}</dt>
                <dd>{values[name]}</dd>
              </div>
            ))}
          </dl>
          <p className={"mt-4 text-xs text-text-muted"}>减少动态效果时，交互直接呈现最终状态。</p>
        </Card>
        <Card as="section" variant="outline" radius="panel" className="form-panel">
          <h3 className={"mb-4 font-semibold"}>组件组合</h3>
          <dl className={"space-y-3 text-sm"}>
            {[
              "--os-heading-gap",
              "--os-heading-content-gap",
              "--os-card-gap",
              "--os-card-gap-sm",
              "--os-avatar-size",
              "--os-favorite-gap",
            ].map((name) => (
              <div key={name} className={"flex flex-wrap justify-between gap-2"}>
                <dt className={"break-all font-mono text-xs text-text-muted"}>{name}</dt>
                <dd>
                  {declarations[name]} · {values[name]}
                </dd>
              </div>
            ))}
          </dl>
        </Card>
      </div>
    </div>
  );
}
