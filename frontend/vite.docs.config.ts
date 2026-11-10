import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  base: "./",
  publicDir: false,
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  build: {
    outDir: "../docs-site/public/design-examples",
    // 热更新期间旧 iframe 可能仍在使用上一版哈希资源。
    emptyOutDir: false,
    rolldownOptions: { input: "design-examples.html" },
  },
});
