import { StrictMode, useEffect } from "react";
import { createRoot, type Root } from "react-dom/client";
import { RouterProvider } from "react-router/dom";
import { router } from "./router";
import "./globals.css";
import { installThemeController } from "./state/theme/themeController";

installThemeController();

function Application() {
  useEffect(() => {
    // Rendering is scheduled; only a real React commit may dismiss the startup fallback.
    window.dispatchEvent(new Event("app:mounted"));
  }, []);
  return <RouterProvider router={router} />;
}

// 入口可被 Vite 重新执行；同一容器必须继续使用原根实例，否则导航后会叠出两套外壳。
const root =
  (import.meta.hot?.data.root as Root | undefined) ?? createRoot(document.getElementById("root")!);
if (import.meta.hot) import.meta.hot.data.root = root;

root.render(
  <StrictMode>
    <Application />
  </StrictMode>,
);
