import { StrictMode, useEffect } from "react";
import { createRoot } from "react-dom/client";
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

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Application />
  </StrictMode>,
);
