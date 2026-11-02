import { Card } from "@/components/ui/Card";
import { SearchInput } from "@/components/common/SearchInput";
import { useState } from "react";
import { Copy, Search } from "lucide-react";

import { TabsContent } from "@/components/ui/Tabs";
import { PageTabs } from "@/components/common/PageTabs";
import {
  colorGroups,
  colorLayers,
  colorRoles,
  componentColors,
  paletteFamilies,
} from "@/design-system/spec";
import { useThemeValues } from "./useThemeValues";

export function ColorCatalog({ notify }: { notify: (message: string) => void }) {
  const { values, declarations } = useThemeValues();
  const [query, setQuery] = useState("");
  const [level, setLevel] = useState("semantic");
  const match = (name: string, label: string) =>
    `${name} ${label} ${values[name]}`.toLowerCase().includes(query.trim().toLowerCase());
  const semantic = Object.entries(colorRoles).filter(([, role]) => role.group !== "component");
  const count = semantic.filter(([key, role]) => match(`--os-${key}`, role.label)).length;
  const paletteCount = Object.keys(declarations).filter((name) =>
    paletteFamilies.some(
      (family) =>
        name.startsWith(`--${family.id}-`) &&
        match(name, `${family.label} ${family.kind} ${family.usage}`),
    ),
  ).length;
  const componentCount = Object.entries(componentColors).filter(([name, label]) =>
    match(name, label),
  ).length;
  const summary =
    level === "semantic"
      ? `${count} 个语义用途`
      : level === "palette"
        ? `${paletteCount} 个基础色`
        : `${componentCount} 个组件映射`;
  async function copy(name: string) {
    try {
      await navigator.clipboard.writeText(`var(${name})`);
      notify(`已复制 var(${name})`);
    } catch {
      notify("复制失败，请选择变量名称后手动复制。");
    }
  }
  function row(name: string, label: string) {
    return (
      <div
        key={name}
        data-color-token={name}
        className={
          "flex min-w-0 items-center gap-3 border-b border-border py-3 last:border-0 sm:gap-4"
        }
      >
        <span
          aria-hidden="true"
          className={"size-10 shrink-0 rounded-control border border-border"}
          style={{ background: `var(${name})` }}
        />
        <div className={"min-w-0 flex-1"}>
          <p className={"text-sm font-medium"}>{label}</p>
          <button
            type="button"
            className={
              "mt-1 inline-flex max-w-full items-center gap-2 text-left font-mono text-xs text-text-muted hover:text-text"
            }
            onClick={() => void copy(name)}
            aria-label={`复制 ${name}`}
          >
            <span className={"break-all"}>{name}</span>
            <Copy size={12} className={"shrink-0"} aria-hidden="true" />
          </button>
          <p className={"mt-1 break-all font-mono text-[11px] text-text-muted"}>
            {declarations[name]}
          </p>
        </div>
        <code
          className={"max-w-24 shrink-0 break-all text-right text-xs text-text-muted sm:max-w-40"}
        >
          {values[name]}
        </code>
      </div>
    );
  }
  return (
    <div className={"space-y-6"}>
      <section aria-label="颜色分类依据">
        <p className={"text-sm leading-relaxed"}>
          颜色按在系统中的职责分成三类。页面开发先从“语义用途”选择。
        </p>
        <dl className={"mt-4 grid gap-x-6 gap-y-3 sm:grid-cols-3"}>
          {colorLayers.map((layer) => (
            <div key={layer.id} className={"border-l-2 border-border pl-3"}>
              <dt className={"text-sm font-medium"}>
                {layer.name}
                <span className={"ml-2 text-xs font-normal text-text-muted"}>{layer.purpose}</span>
              </dt>
              <dd className={"mt-1 text-xs leading-relaxed text-text-muted"}>
                {layer.description}
              </dd>
            </div>
          ))}
        </dl>
      </section>
      <div className={"relative max-w-md"}>
        <Search
          size={16}
          className={"absolute top-2.5 left-3 text-text-muted"}
          aria-hidden="true"
        />
        <SearchInput
          label="搜索颜色令牌"
          onChange={(nextValue) => setQuery(nextValue)}
          placeholder="搜索名称、用途或色值…"
          value={query}
          className="pl-9"
        />
      </div>
      <PageTabs
        value={level}
        onValueChange={setLevel}
        label="颜色分类"
        trailing={summary}
        items={colorLayers.map((layer) => ({ value: layer.id, label: layer.name }))}
      >
        <TabsContent value="semantic" className={"pt-5"}>
          <p className={"mb-5 text-sm leading-relaxed text-text-muted"}>
            例如卡片、输入框和浮层共用 <code className={"text-text"}>--os-surface</code>。
            切换主题可核对实际色值，点击变量名复制 CSS 引用。
          </p>
          {count ? (
            <div className={"min-w-0 columns-1 gap-5 lg:columns-2"}>
              {colorGroups
                .filter((group) => group.id !== "component")
                .map((group) => {
                  const entries = semantic.filter(
                    ([key, role]) => role.group === group.id && match(`--os-${key}`, role.label),
                  );
                  return (
                    entries.length > 0 && (
                      <Card
                        as="section"
                        variant="outline"
                        radius="panel"
                        key={group.id}
                        aria-label={`${group.name}颜色令牌`}
                        className="mb-5 break-inside-avoid p-5"
                      >
                        <h3 className={"font-semibold"}>{group.name}</h3>
                        <p className={"mt-1 mb-3 text-xs leading-relaxed text-text-muted"}>
                          {group.usage}
                        </p>
                        {entries.map(([key, role]) => row(`--os-${key}`, role.label))}
                      </Card>
                    )
                  );
                })}
            </div>
          ) : (
            <p role="status" className={"py-8 text-sm text-text-muted"}>
              没有匹配的语义令牌。
            </p>
          )}
        </TabsContent>
        <TabsContent value="palette" className={"space-y-6 pt-5"}>
          <p className={"text-sm leading-relaxed text-text-muted"}>
            例如 <code className={"text-text"}>--gray-25</code> 只记录一个颜色数值，
            由主题映射到具体用途。调整主题时维护这里，业务页面优先使用语义用途。
          </p>
          {paletteFamilies.map((family) => {
            const names = Object.keys(declarations).filter(
              (name) =>
                name.startsWith(`--${family.id}-`) &&
                match(name, `${family.label} ${family.kind} ${family.usage}`),
            );
            return (
              names.length > 0 && (
                <section key={family.id} aria-label={`${family.label}基础色板`}>
                  <h3 className={"font-semibold"}>
                    {family.label}
                    <span className={"ml-2 text-xs font-normal text-text-muted"}>
                      {family.kind} · {family.usage}
                    </span>
                  </h3>
                  <div className={"mt-3 grid grid-cols-3 gap-3 sm:grid-cols-5 xl:grid-cols-7"}>
                    {names.map((name) => (
                      <button
                        key={name}
                        type="button"
                        aria-label={`复制 ${name}`}
                        onClick={() => void copy(name)}
                        className={
                          "min-w-0 overflow-hidden rounded-control border border-border text-left hover:bg-muted"
                        }
                      >
                        <span
                          className={"block h-14 border-b border-border"}
                          style={{ background: `var(${name})` }}
                        />
                        <span className={"block space-y-1 p-2 font-mono text-[11px]"}>
                          <span className={"block break-all"}>{name}</span>
                          <span className={"block break-all text-text-muted"}>{values[name]}</span>
                        </span>
                      </button>
                    ))}
                  </div>
                </section>
              )
            );
          })}
          {!paletteFamilies.some((family) =>
            Object.keys(declarations).some(
              (name) =>
                name.startsWith(`--${family.id}-`) &&
                match(name, `${family.label} ${family.kind} ${family.usage}`),
            ),
          ) && (
            <p role="status" className={"py-8 text-sm text-text-muted"}>
              没有匹配的基础颜色。
            </p>
          )}
        </TabsContent>
        <TabsContent value="component" className={"pt-5"}>
          <p className={"mb-4 text-sm leading-relaxed text-text-muted"}>
            例如 <code className={"text-text"}>--os-card-border</code> 日间引用半透明中性墨色
            overlay-card、夜间引用
            border，让边界与各自表面自然衔接。只有组件需要独立的对应关系时才保留映射；普通正文和按钮直接使用通用语义。
          </p>
          <Card as="div" variant="outline" radius="panel" className="px-5">
            {Object.entries(componentColors)
              .filter(([name, label]) => match(name, label))
              .map(([name, label]) => row(name, label))}
          </Card>
          {!Object.entries(componentColors).some(([name, label]) => match(name, label)) && (
            <p role="status" className={"py-8 text-sm text-text-muted"}>
              没有匹配的组件映射。
            </p>
          )}
        </TabsContent>
      </PageTabs>
    </div>
  );
}
