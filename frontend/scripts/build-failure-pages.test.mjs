// @vitest-environment jsdom
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

const generator = path.join(process.cwd(), "scripts/build-failure-pages.mjs");
let startup;
beforeAll(() => {
  startup = JSON.parse(
    execFileSync(
      process.execPath,
      [
        "--input-type=module",
        "--eval",
        `import { startupAssets } from ${JSON.stringify(pathToFileURL(generator).href)};process.stdout.write(JSON.stringify(startupAssets()));`,
      ],
      { encoding: "utf8" },
    ),
  );
});

afterEach(() => {
  window.dispatchEvent(new Event("app:mounted"));
  vi.useRealTimers();
  document.body.replaceChildren();
});

describe("standalone failure document generation", () => {
  it("builds five documents from shared copy and theme without React or a live service", () => {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), "niuma-failure-pages-"));
    try {
      execFileSync(process.execPath, [generator, directory]);
      const copy = JSON.parse(
        fs.readFileSync(path.join(process.cwd(), "src/lib/failures/copy.json"), "utf8"),
      );
      const families = {
        404: "not-found",
        500: "service",
        502: "connection",
        503: "service",
        504: "waiting",
      };
      for (const [status, family] of Object.entries(families)) {
        const html = fs.readFileSync(path.join(directory, "failures", `${status}.html`), "utf8");
        expect(html).toContain(copy[family].title);
        expect(html).toContain(copy[family].description);
        expect(html).toContain(`/failures/${family}.png`);
        expect(html).toContain("--os-surface:");
        expect(html).toContain('[data-theme="dark"]');
        expect(html).toContain(`failure-static__code">${status}`);
        expect(html).not.toMatch(/type="module"|\/api\/|react|@utility|@theme/);
      }
    } finally {
      fs.rmSync(directory, { recursive: true, force: true });
    }
  });
});

function observeStartup() {
  vi.useFakeTimers();
  const assets = startup;
  document.body.innerHTML = assets.html;
  window.eval(assets.script);
  return document.getElementById("app-startup-fallback");
}

describe("pre-React startup observation", () => {
  it("reports a slow startup without claiming a script failure", () => {
    const fallback = observeStartup();
    expect(fallback.hidden).toBe(true);
    vi.advanceTimersByTime(8000);
    expect(fallback.hidden).toBe(false);
    expect(fallback.textContent).toContain("页面加载时间较长");
    expect(fallback.textContent).not.toContain("页面资源未能加载");
    expect(fallback.querySelector("a").getAttribute("href")).toBe("");
  });

  it("uses a confirmed entry-script failure and does not blame an image error", () => {
    const fallback = observeStartup();
    const image = document.createElement("img");
    image.setAttribute("data-failure-image", "");
    document.body.append(image);
    image.dispatchEvent(new Event("error"));
    expect(image.hidden).toBe(true);
    expect(fallback.hidden).toBe(true);
    const entry = document.createElement("script");
    entry.setAttribute("data-app-entry", "");
    document.body.append(entry);
    entry.dispatchEvent(new Event("error"));
    expect(fallback.hidden).toBe(false);
    expect(fallback.textContent).toContain("页面资源未能加载");
  });

  it("cleans up only when the real React commit event arrives", () => {
    observeStartup();
    window.dispatchEvent(new Event("app:mounted"));
    vi.advanceTimersByTime(30000);
    expect(document.getElementById("app-startup-fallback")).toBeNull();
  });

  it("recognizes the rewritten production module tag after Vite removes custom attributes", () => {
    const fallback = observeStartup();
    const entry = document.createElement("script");
    entry.type = "module";
    entry.src = "/assets/index-fingerprint.js";
    document.body.append(entry);
    entry.dispatchEvent(new Event("error"));
    expect(fallback.hidden).toBe(false);
    expect(fallback.textContent).toContain("页面资源未能加载");
  });

  it("retains an early script failure until the fallback HTML has been parsed", () => {
    observeStartup();
    document.body.replaceChildren();
    const entry = document.createElement("script");
    entry.type = "module";
    document.body.append(entry);
    entry.dispatchEvent(new Event("error"));
    document.body.innerHTML = startup.html;
    document.dispatchEvent(new Event("DOMContentLoaded"));
    const fallback = document.getElementById("app-startup-fallback");
    expect(fallback.hidden).toBe(false);
    expect(fallback.textContent).toContain("页面资源未能加载");
  });
});
