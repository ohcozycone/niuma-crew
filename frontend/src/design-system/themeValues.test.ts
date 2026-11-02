import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
const css = readFileSync(new URL("./theme.css", import.meta.url), "utf8");
import { themeDeclarations, themeValues } from "./themeValues";
import {
  colorRoles,
  componentColors,
  paletteFamilies,
  contrastExceptions,
  type ColorToken,
} from "./spec";

function contrast(a: string, b: string) {
  const luminance = (hex: string) => {
    const channels = hex
      .slice(1)
      .match(/../g)!
      .map((channel) => parseInt(channel, 16) / 255)
      .map((value) => (value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4));
    return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
  };
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (light + 0.05) / (dark + 0.05);
}
const pairs: [ColorToken, ColorToken, number][] = [
  ["text", "surface", 4.5],
  ["text-muted", "surface", 4.5],
  ["text", "selected", 4.5],
  ["text", "canvas", 4.5],
  ["text", "muted", 4.5],
  ["text-muted", "canvas", 3],
  ["nav-active-text", "nav-active", 4.5],
  ["text-muted", "nav-count-bg", 4.5],
  ["action-text", "action", 4.5],
  ["action-text", "action-hover", 4.5],
  // Default input borders follow shadcn's subtle neutral treatment, not a 3:1 boundary.
  // Keep the stronger fallback keyboard-focus contrast checked separately below.
  ["focus", "surface", 3],
  ["success", "success-bg", 4.5],
  ["warning", "warning-bg", 4.5],
  ["danger", "danger-bg", 4.5],
  ["danger-text", "danger", 4.5],
  ["info", "info-bg", 4.5],
];
describe("CSS token source", () => {
  it("resolves all declarations in both themes and preserves the shared interface", () => {
    expect(Object.keys(themeValues(css, "light")).sort()).toEqual(
      Object.keys(themeValues(css, "dark")).sort(),
    );
    for (const mode of ["light", "dark"] as const) {
      const values = themeValues(css, mode);
      for (const key of Object.keys(colorRoles)) expect(values[`--os-${key}`]).toMatch(/^(#|rgb)/);
      for (const key of Object.keys(componentColors)) expect(values[key]).toMatch(/^(#|rgb)/);
    }
  });
  it("registers colour literals once and uses references for semantic roles", () => {
    const declarations = themeDeclarations(css, "light");
    const palette = Object.entries(declarations).filter(([name]) =>
      paletteFamilies.some((family) => name.startsWith(`--${family.id}-`)),
    );
    expect(new Set(palette.map(([, value]) => value)).size).toBe(palette.length);
    for (const mode of ["light", "dark"] as const) {
      const roles = themeDeclarations(css, mode);
      for (const key of [
        ...Object.keys(colorRoles).map((name) => `--os-${name}`),
        ...Object.keys(componentColors),
      ])
        expect(roles[key]).toMatch(/^var\(--[\w-]+\)$/);
      expect(roles["--os-card-border"]).toBe(
        mode === "light" ? "var(--overlay-card)" : "var(--os-border)",
      );
    }
  });
  it("defines every literal theme reference consumed by the application", () => {
    const defined = new Set(Object.keys(themeDeclarations(css, "light")));
    const inspect = (directory: string) => {
      for (const entry of readdirSync(directory, { withFileTypes: true })) {
        const path = join(directory, entry.name);
        if (entry.isDirectory()) {
          if (entry.name !== "generated") inspect(path);
          continue;
        }
        if (!/\.(tsx?|css|html)$/.test(entry.name) || entry.name.includes(".test.")) continue;
        const source = readFileSync(path, "utf8");
        for (const [, name] of source.matchAll(/var\((--(?:os|login)-[\w-]+)\)/g))
          expect(defined.has(name), `${path}: ${name}`).toBe(true);
      }
    };
    inspect(fileURLToPath(new URL("../", import.meta.url)));
  });
  it("keeps selected navigation readable on neutral surfaces", () => {
    const light = themeValues(css, "light"),
      dark = themeValues(css, "dark");
    expect(light["--os-nav-active-text"]).toBe(light["--os-text"]);
    expect(dark["--os-nav-active-text"]).toBe(dark["--os-text"]);
    expect(light["--os-nav-count-bg"]).toBe(light["--os-muted"]);
    expect(dark["--os-nav-count-bg"]).toBe(dark["--os-selected"]);
  });
  it("rejects undefined references and cycles before asset generation", () => {
    expect(() => themeValues(":root { --a: var(--missing); }", "light")).toThrow("Undefined");
    expect(() => themeValues(":root { --a: var(--b); --b: var(--a); }", "light")).toThrow("Cyclic");
  });
  for (const mode of ["light", "dark"] as const) {
    for (const [foreground, background, minimum] of pairs) {
      const exception = contrastExceptions.find(
        (entry) =>
          entry.mode === mode && entry.foreground === foreground && entry.background === background,
      );
      it(`${mode}: ${foreground} against ${background}${exception ? " (accepted limitation)" : ""}`, () => {
        const values = themeValues(css, mode);
        const ratio = contrast(values[`--os-${foreground}`], values[`--os-${background}`]);
        if (exception) expect(ratio).toBeLessThan(exception.target);
        else expect(ratio).toBeGreaterThanOrEqual(minimum);
      });
    }
  }
});
