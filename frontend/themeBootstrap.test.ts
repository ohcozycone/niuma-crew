import { JSDOM } from "jsdom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { themeAssets } from "./scripts/build-theme.mjs";
import { installThemeController } from "./src/state/theme/themeController";

afterEach(() => vi.unstubAllGlobals());

describe("theme before the React runtime", () => {
  it.each([
    { saved: "dark", systemDark: false, preference: "dark", resolved: "dark" },
    { saved: "invalid", systemDark: true, preference: "system", resolved: "dark" },
    { saved: null, systemDark: false, preference: "system", resolved: "light" },
  ])(
    "applies $preference / $resolved from the emitted bootstrap",
    async ({ saved, systemDark, preference, resolved }) => {
      const assets = await themeAssets();
      const dom = new JSDOM(
        `<html><head><style>${assets.css}</style><script>${assets.script}</script></head><body><div id="root"></div></body></html>`,
        {
          url: "http://fixture.local/",
          runScripts: "dangerously",
          beforeParse(window) {
            if (saved !== null) window.localStorage.setItem("niuma:theme", saved);
            window.matchMedia = (media) =>
              Object.assign(new window.EventTarget(), {
                media,
                matches: systemDark,
                onchange: null,
                addListener() {},
                removeListener() {},
              });
          },
        },
      );
      try {
        const root = dom.window.document.documentElement;
        expect(root.dataset.themePreference).toBe(preference);
        expect(root.dataset.theme).toBe(resolved);
        expect(root.style.colorScheme).toBe(resolved);
        expect(dom.window.document.getElementById("root")!.childElementCount).toBe(0);
        vi.stubGlobal("window", dom.window);
        vi.stubGlobal("document", dom.window.document);
        const controller = installThemeController();
        expect(controller.getSnapshot()).toEqual({ preference, resolved });
        expect(installThemeController()).toBe(controller);
      } finally {
        dom.window.close();
      }
    },
  );
});
