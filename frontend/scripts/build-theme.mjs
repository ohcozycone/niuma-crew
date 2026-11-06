/** Inline root tokens and the shared controller before the first paint. */
import fs from "node:fs";
import ts from "typescript";
import { minify } from "terser";
export async function themeAssets() {
  const code = ts.transpileModule(
    fs.readFileSync(new URL("../src/state/theme/themeController.ts", import.meta.url), "utf8"),
    {
      compilerOptions: {
        target: ts.ScriptTarget.ES2020,
        module: ts.ModuleKind.ESNext,
      },
    },
  ).outputText;
  const { installThemeController } = await import(
    "data:text/javascript;base64," + Buffer.from(code).toString("base64")
  );
  const css =
    fs
      .readFileSync(new URL("../src/design-system/theme.css", import.meta.url), "utf8")
      .split("/* Tailwind utilities */")[0] +
    "body{margin:0;background:var(--os-surface);color:var(--os-text)}";
  const result = await minify(`(${installThemeController.toString()})();`, {
    compress: { passes: 2 },
    mangle: true,
  });
  if (!result.code) throw new Error("Theme bootstrap emission failed");
  return { css, script: result.code };
}
