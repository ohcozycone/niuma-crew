import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { colorRoles, componentColors } from "./spec";
import { themeValues } from "./themeValues";

const css = readFileSync(new URL("./theme.css", import.meta.url), "utf8");
const legacyColours =
  "background|foreground|primary(?:-foreground)?|secondary(?:-foreground)?|accent(?:-foreground)?|card(?:-foreground)?|popover(?:-foreground)?|muted-foreground|destructive(?:-foreground)?|ring";
const legacyUtility = new RegExp(
  `(?:^|[^\\w-])(?:bg|text|border|ring|ring-offset|outline|fill|stroke|divide|placeholder|decoration|from|via|to)-(?:${legacyColours})(?=[\\s/:"'\x60\\[\\]}]|$)`,
);

function sources(directory: string, extensions: RegExp): [string, string][] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) return entry.name === "generated" ? [] : sources(path, extensions);
    return extensions.test(entry.name) && !entry.name.includes(".test.")
      ? [[path, readFileSync(path, "utf8")] as [string, string]]
      : [];
  });
}

describe("public token contract", () => {
  it("exposes every application colour to Tailwind under the same semantic name", () => {
    for (const role of [
      ...Object.keys(colorRoles),
      ...Object.keys(componentColors)
        .filter((name) => name.startsWith("--os-"))
        .map((name) => name.slice(5)),
    ]) {
      expect(css).toContain(`--color-${role}: var(--os-${role});`);
    }
  });

  it("keeps consumers free of legacy variables, colour classes and the body theme wrapper", () => {
    const index = fileURLToPath(new URL("../../index.html", import.meta.url));
    const consumers: [string, string][] = [
      ...sources(fileURLToPath(new URL("../", import.meta.url)), /\.(tsx?|css|html)$/),
      ...sources(fileURLToPath(new URL("../../scripts/", import.meta.url)), /\.(mjs|css|html)$/),
      [index, readFileSync(index, "utf8")],
    ];
    for (const [path, source] of consumers) {
      expect(source, path).not.toMatch(
        /--pv-|\bpv-(?:app|portal)\b|theme\.module\.css|\bdesignTheme\b/,
      );
      expect(source.match(legacyUtility), path).toBeNull();
    }
  });

  it("keeps authored UI colours in the shared theme, including gallery and docs controls", () => {
    const consumers = [
      ...sources(fileURLToPath(new URL("../", import.meta.url)), /\.(tsx?|css|json)$/),
      ...sources(fileURLToPath(new URL("../../scripts/", import.meta.url)), /\.(mjs|css|html)$/),
      ...sources(
        fileURLToPath(new URL("../../../docs-site/src/", import.meta.url)),
        /\.(tsx?|css)$/,
      ),
    ];
    for (const [path, original] of consumers) {
      // Original SVG artwork and its fallback ink are assets, not UI surfaces.
      if (/\/generated\/|\/svg\/|\/theme\.css$|\/wordmarkSource\.ts$/.test(path)) continue;
      const source = original.replace("var(--logo-ink, #202126)", "var(--logo-ink)");
      expect(source, path).not.toMatch(/#[\da-f]{3,8}\b|\b(?:rgb|hsl|oklch)a?\(/i);
      expect(source, path).not.toMatch(
        /(?:bg|text|border|ring|fill|stroke)-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|pink|rose)-\d/,
      );
      expect(source, path).not.toMatch(/(?:bg|text|border|fill|stroke)-(?:white|black)\b/);
    }
  });

  it("maps the installed Markdown renderer's theme colours in both modes", () => {
    const directory = fileURLToPath(
      new URL("../../node_modules/streamdown/dist/", import.meta.url),
    );
    const utilities = new RegExp(
      `(?:^|[^\\w-])(?:bg|text|border|ring|ring-offset|outline|fill|stroke|divide)-(${legacyColours}|sidebar|muted|border|input)(?=[\\s/:"'\x60\\[\\]}]|$)`,
      "g",
    );
    const colours = new Set<string>();
    for (const [, source] of sources(directory, /\.js$/)) {
      for (const [, name] of source.matchAll(utilities)) colours.add(name);
    }
    expect(colours.size).toBeGreaterThan(0);
    const mappings = new Map(
      [...css.matchAll(/--color-([\w-]+)\s*:\s*([^;]+);/g)].map(([, name, value]) => [
        name,
        value.trim(),
      ]),
    );
    for (const mode of ["light", "dark"] as const) {
      const values = themeValues(css, mode);
      for (const name of colours) {
        const mapping = mappings.get(name);
        expect(mapping, `${mode}: ${name}`).toBeDefined();
        const resolved = mapping?.replace(/var\((--[\w-]+)\)/g, (_, role) => values[role] ?? "");
        expect(resolved, `${mode}: ${name}`).toMatch(/^(#|rgb|transparent$)/);
      }
    }
  });
});
