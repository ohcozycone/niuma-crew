/** Emit standalone error documents and the pre-React startup fallback from shared data. */
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { themeAssets } from "./build-theme.mjs";

const copyUrl = new URL("../src/lib/failures/copy.json", import.meta.url);
const defaultOutput = fileURLToPath(new URL("../dist/", import.meta.url));
const families = {
  404: "not-found",
  500: "service",
  502: "connection",
  503: "service",
  504: "waiting",
};

const styles = `
.failure-static,.startup-fallback{box-sizing:border-box;min-height:100svh;display:grid;place-items:center;padding:calc(var(--os-space-6,24px)*2) var(--os-failure-gutter,28px);font-family:system-ui,-apple-system,"Segoe UI",sans-serif}
.failure-static [hidden],.startup-fallback[hidden]{display:none!important}
.failure-static__group{display:flex;align-items:center;justify-content:center;gap:var(--os-failure-gap,48px);width:100%;min-width:0}
.failure-static__art{flex:none;width:var(--os-failure-art,240px);height:var(--os-failure-art,240px);object-fit:contain}
.failure-static__copy{min-width:0;width:100%;max-width:var(--os-failure-copy,384px);overflow-wrap:anywhere}
.failure-static__code{margin:0 0 12px;font-size:var(--os-failure-code,48px);line-height:1.1;font-weight:var(--os-failure-code-weight,500);letter-spacing:-.03em}
.failure-static__title{margin:0;font-size:var(--os-type-section-size,20px);line-height:var(--os-type-section-leading,1.4);font-weight:var(--os-type-section-weight,600)}
.failure-static__description{margin:12px 0 0;color:var(--os-text-muted);font-size:var(--os-type-body-size,14px);line-height:var(--os-type-body-leading,1.7)}
.failure-static__actions{display:flex;align-items:center;flex-wrap:wrap;gap:12px;margin-top:24px}
.failure-static__action{display:inline-flex;align-items:center;justify-content:center;min-height:36px;box-sizing:border-box;padding:8px 14px;border-radius:var(--os-radius-control,8px);font-size:14px;font-weight:500;line-height:20px;text-decoration:none;color:var(--os-action-text);background:var(--os-action)}
.failure-static__action--secondary{background:transparent;color:var(--os-text-muted)}
.failure-static__action:focus-visible{outline:2px solid var(--os-focus);outline-offset:4px}
.startup-fallback{text-align:center}.startup-fallback .failure-static__actions{justify-content:center}
@media(max-width:727px){.failure-static,.startup-fallback{padding-block:var(--os-space-8,32px)}.failure-static__group{flex-direction:column;gap:24px}.failure-static__art{width:var(--os-failure-art-compact,192px);height:var(--os-failure-art-compact,192px)}.failure-static__copy{text-align:center}.failure-static__code{font-size:var(--os-failure-code-compact,40px)}.failure-static__actions{justify-content:center}}
`;

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character];
  });
}

function actions(status) {
  return `<div class="failure-static__actions">${
    status === 404
      ? '<a class="failure-static__action" href="/agents">返回数字员工</a>'
      : '<a class="failure-static__action" href="">重新检查</a><a class="failure-static__action failure-static__action--secondary" href="/agents">返回数字员工</a>'
  }</div>`;
}

function installStartupObserver() {
  let mounted = false;
  let scriptFailed = false;
  const show = () => {
    if (mounted) return;
    const element = document.getElementById("app-startup-fallback");
    if (!element) return;
    element.hidden = false;
    document.getElementById("app-startup-title").textContent = scriptFailed
      ? "页面资源未能加载"
      : "页面加载时间较长";
    document.getElementById("app-startup-description").textContent = scriptFailed
      ? "请重新加载页面后再试。"
      : "仍在等待页面启动，可以稍后重新检查。";
  };
  const ready = () => {
    if (scriptFailed) show();
  };
  const onError = (event) => {
    const target = event.target;
    if (target?.tagName === "IMG" && target.hasAttribute("data-failure-image")) {
      target.hidden = true;
    } else if (
      target?.tagName === "SCRIPT" &&
      (target.hasAttribute("data-app-entry") || target.type === "module")
    ) {
      scriptFailed = true;
      show();
    }
  };
  const timer = window.setTimeout(show, 8000);
  const finish = () => {
    mounted = true;
    window.clearTimeout(timer);
    window.removeEventListener("error", onError, true);
    window.removeEventListener("app:mounted", finish);
    document.removeEventListener("DOMContentLoaded", ready);
    document.getElementById("app-startup-fallback")?.remove();
  };
  window.addEventListener("error", onError, true);
  window.addEventListener("app:mounted", finish);
  document.addEventListener("DOMContentLoaded", ready);
}

export function startupAssets() {
  return {
    css: styles,
    script: `(${installStartupObserver.toString()})();`,
    html: `<aside id="app-startup-fallback" class="startup-fallback" hidden role="status" aria-live="polite"><div class="failure-static__copy"><h1 id="app-startup-title" class="failure-static__title">页面加载时间较长</h1><p id="app-startup-description" class="failure-static__description">仍在等待页面启动，可以稍后重新检查。</p>${actions(500)}</div></aside><noscript><main class="startup-fallback"><div class="failure-static__copy"><h1 class="failure-static__title">请启用 JavaScript 后继续</h1><p class="failure-static__description">当前浏览器未运行页面脚本。启用后重新加载页面。</p><div class="failure-static__actions"><a class="failure-static__action" href="">重新加载页面</a></div></div></main></noscript>`,
  };
}

export async function failureDocuments() {
  const [copy, theme] = await Promise.all([
    fs.readFile(copyUrl, "utf8").then(JSON.parse),
    themeAssets(),
  ]);
  return Object.fromEntries(
    Object.entries(families).map(([status, family]) => {
      const { title, description } = copy[family];
      return [
        status,
        `<!doctype html>
<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex,nofollow"><meta name="color-scheme" content="light dark"><title>${status} · ${escapeHtml(title)} · NiumaCrew</title><link rel="icon" href="/brand/mark.svg" type="image/svg+xml"><style>${theme.css}${styles}</style><script>${theme.script};window.addEventListener("error",function(event){var target=event.target;if(target&&target.tagName==="IMG"&&target.hasAttribute("data-failure-image"))target.hidden=true;},true);</script></head>
<body><main class="failure-static"><div class="failure-static__group"><img class="failure-static__art" data-failure-image src="/failures/${family}.png" alt="" width="240" height="240"><section class="failure-static__copy" aria-labelledby="failure-title"><p class="failure-static__code">${status}</p><h1 id="failure-title" class="failure-static__title">${escapeHtml(title)}</h1><p class="failure-static__description">${escapeHtml(description)}</p>${actions(Number(status))}</section></div></main></body></html>`,
      ];
    }),
  );
}

export async function buildFailurePages(output = defaultOutput) {
  const documents = await failureDocuments();
  const directory = path.join(output, "failures");
  await fs.mkdir(directory, { recursive: true });
  await Promise.all(
    Object.entries(documents).map(([status, html]) =>
      fs.writeFile(path.join(directory, `${status}.html`), html),
    ),
  );
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await buildFailurePages(process.argv[2] || defaultOutput);
}
