import { LoadingFeedback } from "@/components/common/LoadingFeedback";
import { lazy, Suspense, useState } from "react";
import { Check, X } from "lucide-react";
const ColorCatalog = lazy(() =>
  import("./ColorCatalog").then((module) => ({ default: module.ColorCatalog })),
);
const TypographyCatalog = lazy(() =>
  import("./TypographyCatalog").then((module) => ({ default: module.TypographyCatalog })),
);
const ComponentExamples = lazy(() =>
  import("./ComponentExamples").then((module) => ({ default: module.ComponentExamples })),
);
const PatternExamples = lazy(() =>
  import("./PatternExamples").then((module) => ({ default: module.PatternExamples })),
);
const LayoutCatalog = lazy(() =>
  import("./LayoutCatalog").then((module) => ({ default: module.LayoutCatalog })),
);

/** 文档站内的真实组件示例；目录、规范正文及主题入口由文档站提供。 */
export function DesignSystemPage({
  category,
  assetBase = "",
}: {
  category: string;
  assetBase?: string;
}) {
  const [notice, setNotice] = useState("");
  return (
    <main className="p-4 sm:p-6" aria-label="设计系统交互示例">
      <Suspense fallback={<LoadingFeedback shape="table" label="正在加载示例…" />}>
        {category === "colors" && <ColorCatalog notify={setNotice} />}
        {category === "layout" && <LayoutCatalog />}
        {category === "typography" && <TypographyCatalog />}
        {category === "controls" && <ComponentExamples notify={setNotice} />}
        {category === "patterns" && <PatternExamples notify={setNotice} assetBase={assetBase} />}
      </Suspense>
      {notice && (
        <div
          role="status"
          aria-live="polite"
          className="fixed right-4 bottom-4 z-50 flex max-w-[calc(100vw-32px)] items-center gap-3 rounded-control border border-border bg-surface p-4 text-sm shadow-lg"
        >
          <Check size={16} className="shrink-0 text-success" aria-hidden="true" />
          <span className="break-all">{notice}</span>
          <button
            type="button"
            aria-label="关闭提示"
            className="shrink-0 rounded-small p-1"
            onClick={() => setNotice("")}
          >
            <X size={14} />
          </button>
        </div>
      )}
    </main>
  );
}
