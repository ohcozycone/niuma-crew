import { fileURLToPath } from "node:url";
import { defineConfig, loadEnv, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { themeAssets } from "./scripts/build-theme.mjs";
import { failureDocuments, startupAssets } from "./scripts/build-failure-pages.mjs";

function theme(): Plugin {
  return {
    name: "shared-theme",
    transformIndexHtml: {
      order: "pre",
      async handler(html) {
        const assets = await themeAssets();
        const startup = startupAssets();
        return html
          .replace("/* THEME_CSS */", assets.css)
          .replace("/* THEME_INIT */", assets.script)
          .replace("/* STARTUP_CSS */", startup.css)
          .replace("/* STARTUP_OBSERVER */", startup.script)
          .replace("<!-- STARTUP_HTML -->", startup.html);
      },
    },
    configureServer(server) {
      server.middlewares.use(async (request, response, next) => {
        const status = /^\/failures\/(404|500|502|503|504)\.html(?:\?.*)?$/.exec(
          request.url || "",
        )?.[1];
        if (!status || !["GET", "HEAD"].includes(request.method || "")) return next();
        try {
          const documents = await failureDocuments();
          const html = documents[status];
          response.writeHead(200, {
            "Content-Type": "text/html; charset=utf-8",
            "Content-Length": Buffer.byteLength(html),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
          });
          response.end(request.method === "HEAD" ? undefined : html);
        } catch (error) {
          next(error);
        }
      });
    },
  };
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    plugins: [react(), tailwindcss(), theme()],
    resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
    server: {
      host: "127.0.0.1",
      port: 3000,
      strictPort: true,
      proxy: {
        "/api": {
          target: env.BACKEND_URL || "http://127.0.0.1:8000",
          changeOrigin: false,
          configure(proxy) {
            proxy.on("proxyReq", (request) => {
              for (const header of [
                "forwarded",
                "x-forwarded-for",
                "x-forwarded-host",
                "x-forwarded-proto",
              ])
                request.removeHeader(header);
            });
            proxy.on("error", (_error, _request, response) => {
              if ("writeHead" in response && !response.headersSent) {
                response.writeHead(502, {
                  "Content-Type": "application/json",
                  "Cache-Control": "no-store",
                });
                response.end(
                  JSON.stringify({
                    detail: {
                      code: "backend_unavailable",
                      message:
                        "暂时无法连接后端服务。若刚提交过保存，请先刷新核对结果，再决定是否重试。",
                    },
                  }),
                );
              }
            });
          },
        },
      },
    },
    preview: { host: "127.0.0.1", port: 3000, strictPort: true },
  };
});
