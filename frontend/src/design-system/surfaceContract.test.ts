import { expect, it } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { cornerShapeExceptions } from "./spec";
const root = fileURLToPath(new URL("../", import.meta.url));
function sources(directory: string): [string, string][] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) return ["svg", "generated"].includes(entry.name) ? [] : sources(path);
    return /\.(tsx?|css)$/.test(path) && !path.includes(".test.") && !path.includes(".generated.")
      ? [[relative(root, path), readFileSync(path, "utf8")] as [string, string]]
      : [];
  });
}
const files = sources(root);
it("keeps card surface paint in one component instead of duplicating employee or capability borders", () => {
  for (const [path, source] of files) {
    if (!path.startsWith("pages/") && !path.startsWith("components/")) continue;
    if (path === "components/ui/Card.tsx") continue;
    expect(source, path).not.toMatch(
      /var\(--os-(?:card-border(?:-width)?|shadow-card|shadow-hover)\)/,
    );
  }
});
it("routes form selects through the shared popup and ordinary radii through semantic utilities", () => {
  for (const [path, source] of files) {
    if (path.startsWith("design-system/")) continue;
    expect(source, path).not.toMatch(/<select(?:\s|>)/);
    expect(source, path).not.toMatch(
      /rounded-(?:(?:tl|tr|bl|br|t|b|l|r)-)?(?:xs|sm|md|lg|xl|2xl|3xl)\b/,
    );
    if (/rounded-\[/.test(source))
      expect(
        cornerShapeExceptions.some((entry) => entry.file === path),
        path,
      ).toBe(true);
  }
});
it("keeps page-tab paint in the complete navigation component instead of per-page overrides", () => {
  for (const [path, source] of files) {
    if (!path.startsWith("pages/")) continue;
    expect(source, path).not.toMatch(/<Tabs(?:Header|List|Trigger)\b[^>]*\bclassName=/);
    expect(source, path).not.toMatch(/<DialogContent\b[^>]*className="overflow-y-auto"/);
  }
});
