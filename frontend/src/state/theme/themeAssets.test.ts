import { beforeAll, describe, expect, it } from "vitest";
import { execFileSync } from "node:child_process";
import { runInNewContext } from "node:vm";

let assets: { css: string; script: string };

beforeAll(() => {
  const generator = new URL("../../../scripts/build-theme.mjs", import.meta.url);
  // Exercise Node's actual build entry, including its source paths and data imports.
  assets = JSON.parse(
    execFileSync(
      process.execPath,
      [
        "--input-type=module",
        "--eval",
        `import { themeAssets } from ${JSON.stringify(generator.href)};
         process.stdout.write(JSON.stringify(await themeAssets()));`,
      ],
      { encoding: "utf8" },
    ),
  );
});

describe("generated first-paint theme assets", () => {
  it("generates browser-ready CSS from the current sources", () => {
    expect(assets.css).toContain("--os-surface:");
    expect(assets.css).toContain('[data-theme="dark"]');
    expect(assets.css).not.toMatch(/@theme|@utility/);
  });

  it.each([
    [null, false, "system", "light"],
    [null, true, "system", "dark"],
    ["light", true, "light", "light"],
    ["dark", false, "dark", "dark"],
    ["invalid", true, "system", "dark"],
  ])(
    "applies saved=%s with system dark=%s before React starts",
    (saved, dark, preference, resolved) => {
      const root = {
        dataset: {} as Record<string, string>,
        classList: { toggle() {} },
        style: { colorScheme: "" },
      };
      runInNewContext(assets.script, {
        document: { documentElement: root },
        window: {
          localStorage: { getItem: () => saved },
          matchMedia: () => ({ matches: dark, addEventListener() {} }),
          addEventListener() {},
        },
      });
      expect(root.dataset).toEqual({ theme: resolved, themePreference: preference });
      expect(root.style.colorScheme).toBe(resolved);
    },
  );
});
