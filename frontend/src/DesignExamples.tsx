import { useEffect } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, useLocation } from "react-router";
import { DesignSystemPage } from "./pages/design-system/DesignSystemPage";
import { installThemeController } from "./state/theme/themeController";

const category = new URLSearchParams(window.location.search).get("category") ?? "colors";
const controller = installThemeController();
const parentOrigin = window.location.origin;
function send(message: object) {
  window.parent.postMessage(message, parentOrigin);
}

window.addEventListener("message", (event) => {
  if (event.source !== window.parent || event.origin !== parentOrigin) return;
  if (event.data?.type === "design:theme" && ["light", "dark"].includes(event.data.theme))
    controller.setPreference(event.data.theme);
});

// 所有跳往正式页面的操作交给文档宿主，示例不加载业务路由或请求业务接口。
document.addEventListener(
  "click",
  (event) => {
    const anchor = event.target instanceof Element ? event.target.closest("a") : null;
    const href = anchor?.getAttribute("href");
    if (!href?.startsWith("/") || href.startsWith("//")) return;
    event.preventDefault();
    event.stopPropagation();
    send({
      type: "design:navigate",
      path: href,
      newTab:
        anchor?.getAttribute("target") === "_blank" ||
        event.metaKey ||
        event.ctrlKey ||
        event.shiftKey,
    });
  },
  true,
);

export function DesignExamples() {
  const location = useLocation();
  useEffect(() => {
    if (location.key !== "default")
      send({ type: "design:navigate", path: location.pathname + location.search });
  }, [location]);
  return (
    <DesignSystemPage
      category={category}
      assetBase={new URL("../", window.location.href).pathname.replace(/\/$/, "")}
    />
  );
}

const root = document.getElementById("root")!;
createRoot(root).render(
  <MemoryRouter>
    <DesignExamples />
  </MemoryRouter>,
);
new ResizeObserver(() => {
  send({ type: "design:resize", height: Math.ceil(root.getBoundingClientRect().height) });
}).observe(root);
send({ type: "design:ready" });
