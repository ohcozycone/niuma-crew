import { expect, it } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";
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

function tabStyleOverrides(source: string): string[] {
  const file = ts.createSourceFile(
    "page.tsx",
    source,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TSX,
  );
  const violations: string[] = [];
  function visit(node: ts.Node) {
    if (
      (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) &&
      /^Tabs(?:Header|List|Trigger)$/.test(node.tagName.getText(file))
    ) {
      for (const attribute of node.attributes.properties) {
        if (!ts.isJsxAttribute(attribute) || attribute.name.getText(file) !== "className") continue;
        const value = attribute.initializer;
        const literal = value && ts.isJsxExpression(value) ? value.expression : value;
        // Width and outer margin belong to placement; component paint stays shared.
        if (!literal || !ts.isStringLiteralLike(literal)) {
          violations.push(attribute.getText(file));
          continue;
        }
        violations.push(
          ...literal.text
            .split(/\s+/)
            .filter(
              (token) =>
                token &&
                !/^(?:[a-z0-9-]+:)*(?:(?:min-|max-)?w-[^\s]+|-?m[trblxyse]?-[^\s]+)$/.test(token),
            ),
        );
      }
    }
    ts.forEachChild(node, visit);
  }
  visit(file);
  return violations;
}

it.each(["w-full", "md:max-w-xl mx-auto", "min-w-0 max-sm:w-full", ""])(
  "allows external tab placement: %s",
  (classes) => expect(tabStyleOverrides(`<TabsList className="${classes}" />`)).toEqual([]),
);
it.each(["bg-red-500", "px-4", "text-xs", "border-0", "shadow-none", "rounded-none"])(
  "rejects internal tab paint: %s",
  (classes) =>
    expect(tabStyleOverrides(`<TabsTrigger className="${classes}" />`)).toEqual([classes]),
);
it("checks expression literals and rejects unreviewable dynamic tab overrides", () => {
  expect(tabStyleOverrides('<TabsHeader className={"w-full"} />')).toEqual([]);
  expect(tabStyleOverrides("<TabsList className={classes} />")).toHaveLength(1);
});
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
    expect(tabStyleOverrides(source), path).toEqual([]);
    expect(source, path).not.toMatch(/<DialogContent\b[^>]*className="overflow-y-auto"/);
  }
});

it("keeps documentation UI radii connected to the same semantic scale", () => {
  const source = readFileSync(
    new URL("../../../docs-site/src/app/global.css", import.meta.url),
    "utf8",
  );
  for (const [, value] of source.matchAll(/border-radius:\s*([^;]+);/g))
    expect(value.trim()).toMatch(/^(?:var\(--os-radius-[\w-]+\)|50%|0)$/);
});
