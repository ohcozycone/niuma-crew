import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router";
import { ArrowLeft, Check, X } from "lucide-react";
import { BrandLogo } from "@/components/brand/BrandLogo";
import { PageHeading } from "@/components/common/PageHeading";
import { NavigationItem } from "@/components/ui/NavigationItem";
import { ThemeSwitcher } from "@/components/theme/ThemeSwitcher";
import { useTheme } from "@/state/theme/useTheme";
import { designSystem } from "@/design-system/spec";
import { ColorCatalog } from "./ColorCatalog";
import { TypographyCatalog } from "./TypographyCatalog";
import { ComponentExamples } from "./ComponentExamples";
import { PatternExamples } from "./PatternExamples";
import { LayoutCatalog } from "./LayoutCatalog";

const categories = [
  { id: "colors", title: "颜色", description: "基础色板、语义用途与组件映射" },
  { id: "layout", title: "布局与响应式", description: "组件预算、容器宽度与响应式组合" },
  { id: "typography", title: "排版与尺度", description: "文字角色、间距、圆角与动效" },
  { id: "controls", title: "基础组件", description: "导航、按钮、输入与浮层的交互样板" },
  { id: "patterns", title: "业务样板", description: "正式员工卡片与状态反馈的组合" },
] as const;
const targets: Record<string, string> = {
  foundation: "colors",
  "account-navigation": "controls",
  "agent-navigation": "controls",
  agents: "patterns",
  feedback: "patterns",
  "resource-language": "patterns",
  boundaries: "controls",
  buttons: "controls",
};
export function DesignSystemPage() {
  const { hash } = useLocation();
  const requested = hash.slice(1);
  const active =
    categories.find((category) => category.id === (targets[requested] ?? requested)) ??
    categories[0];
  const { resolved } = useTheme();
  const [notice, setNotice] = useState("");
  useEffect(() => {
    if (requested && document.getElementById(requested))
      document.getElementById(requested)!.scrollIntoView({ block: "start" });
    else window.scrollTo(0, 0);
  }, [requested]);
  return (
    <div className={"workspace-region min-h-dvh bg-canvas text-text"}>
      <a
        href="#design-main"
        onClick={(event) => {
          event.preventDefault();
          document.getElementById("design-main")?.focus();
        }}
        className={"fixed top-[-60px] left-4 z-50 rounded-control bg-surface p-3 focus:top-3"}
      >
        跳到规范内容
      </a>
      <aside
        aria-label="设计系统目录"
        className={
          "relative border-b border-border bg-surface p-4 lg:fixed lg:inset-y-0 lg:left-0 lg:flex lg:w-(--os-navigation-width) lg:flex-col lg:border-r lg:border-b-0 lg:p-5"
        }
      >
        <div className={"flex items-center justify-between gap-4 lg:block"}>
          <Link to="/" className={"inline-flex items-center [--brand-logo-scale:0.85]"}>
            <BrandLogo />
          </Link>
          <p className={"hidden text-xs text-text-muted lg:mt-6 lg:block"}>
            DESIGN SYSTEM <span className={"ml-1 font-mono"}>{designSystem.version}</span>
          </p>
        </div>
        <nav aria-label="规范分类" className={"mt-5 flex flex-wrap gap-1 pb-1 lg:flex-col lg:pb-0"}>
          {categories.map((category, index) => (
            <NavigationItem
              key={category.id}
              render={<Link to={`#${category.id}`} />}
              active={active.id === category.id}
              className="w-auto lg:w-full"
              aria-current={active.id === category.id ? "page" : undefined}
            >
              <span className={"font-mono text-xs opacity-70"}>0{index + 1}</span>
              {category.title}
            </NavigationItem>
          ))}
        </nav>
        <div
          className={
            "absolute top-5 right-4 flex items-center gap-3 lg:static lg:mt-auto lg:block lg:border-t lg:border-border lg:pt-4"
          }
        >
          <div className={"flex items-center gap-3"}>
            <ThemeSwitcher />
            <span className={"hidden text-xs text-text-muted lg:inline"}>
              {resolved === "dark" ? "夜间" : "日间"}
            </span>
          </div>
          <Link
            to="/help/"
            className={"flex items-center gap-2 text-xs text-text-muted hover:text-text lg:mt-5"}
          >
            <ArrowLeft size={14} aria-hidden="true" />
            返回帮助
          </Link>
        </div>
      </aside>
      <div className="workspace-region lg:ml-(--os-navigation-width)">
        <main id="design-main" tabIndex={-1} className={"page-frame py-6 outline-none"}>
          <PageHeading
            title="设计系统"
            description="按用途选择令牌，用实际组件核对视觉与交互。"
            meta={`v${designSystem.version} · ${designSystem.updated}`}
          />
          <section aria-labelledby="catalog-title" className={"mt-7 min-w-0"}>
            <div className={"mb-6 border-b border-border pb-5"}>
              <h2 id="catalog-title" className={"type-section"}>
                {active.title}
              </h2>
              <p className={"mt-2 text-sm text-text-muted"}>{active.description}</p>
            </div>
            {active.id === "colors" && <ColorCatalog notify={setNotice} />}
            {active.id === "layout" && <LayoutCatalog />}
            {active.id === "typography" && <TypographyCatalog />}
            {active.id === "controls" && <ComponentExamples notify={setNotice} />}
            {active.id === "patterns" && <PatternExamples notify={setNotice} />}
          </section>
          <footer
            className={"mt-10 border-t border-border pt-5 text-xs leading-relaxed text-text-muted"}
          >
            令牌来源：theme.css · 样板复用正式组件 · 示例数据仅影响本页
          </footer>
        </main>
      </div>
      {notice && (
        <div
          role="status"
          aria-live="polite"
          className={
            "fixed right-4 bottom-4 z-50 flex max-w-[calc(100vw-32px)] items-center gap-3 rounded-control border border-border bg-surface p-4 text-sm shadow-lg"
          }
        >
          <Check size={16} className={"shrink-0 text-success"} aria-hidden="true" />
          <span className={"break-all"}>{notice}</span>
          <button
            type="button"
            aria-label="关闭提示"
            className={"shrink-0 rounded-small p-1"}
            onClick={() => setNotice("")}
          >
            <X size={14} />
          </button>
        </div>
      )}
    </div>
  );
}
