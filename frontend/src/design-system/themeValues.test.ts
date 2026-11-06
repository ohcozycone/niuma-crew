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
  ["text", "raised", 4.5],
  ["text-muted", "raised", 4.5],
  ["text-muted", "muted", 4.5],
  ["text-muted", "selected", 4.5],
  ["text", "selected", 4.5],
  ["text", "canvas", 4.5],
  ["text", "muted", 4.5],
  ["text-muted", "canvas", 4.5],
  ["hover-text", "hover", 4.5],
  ["hover-text", "pressed", 4.5],
  ["text", "hover", 4.5],
  ["nav-active-text", "nav-active", 4.5],
  ["text-muted", "nav-count-bg", 4.5],
  ["action-text", "action", 4.5],
  ["action-text", "action-hover", 4.5],
  ["action-text", "action-pressed", 4.5],
  ["action-soft-text", "action-soft", 4.5],
  ["action-soft-text", "action-soft-hover", 4.5],
  ["action-soft-text", "action-soft-pressed", 4.5],
  ["danger-action-text", "danger-action", 4.5],
  ["danger-action-text", "danger-action-hover", 4.5],
  ["danger-action-text", "danger-action-pressed", 4.5],
  // Default input borders remain subtle; focused borders carry the stronger contrast.
  ["focus", "surface", 3],
  ["field-focus", "surface", 3],
  ["brand-text", "surface", 4.5],
  ["brand-text", "muted", 4.5],
  ["success", "surface", 4.5],
  ["warning", "surface", 4.5],
  ["danger", "surface", 4.5],
  ["info", "surface", 4.5],
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
      expect(roles["--os-card-border"]).toBe("var(--os-border)");
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
        if (!/\.(tsx?|css|html|json)$/.test(entry.name) || entry.name.includes(".test.")) continue;
        const source = readFileSync(path, "utf8");
        for (const [, name] of source.matchAll(/var\((--(?:os|login)-[\w-]+)\)/g))
          expect(defined.has(name), `${path}: ${name}`).toBe(true);
      }
    };
    inspect(fileURLToPath(new URL("../", import.meta.url)));
    inspect(fileURLToPath(new URL("../../../docs-site/src/", import.meta.url)));
  });
  it("keeps persistent navigation selection distinct from hover without introducing a separate ink colour", () => {
    const light = themeValues(css, "light"),
      dark = themeValues(css, "dark");
    for (const values of [light, dark]) {
      expect(values["--os-nav-active"]).not.toBe(values["--os-hover"]);
      expect(values["--os-nav-active-text"]).toBe(values["--os-text"]);
    }
    expect(light["--os-nav-count-bg"]).toBe(light["--os-muted"]);
    expect(dark["--os-nav-count-bg"]).toBe(dark["--os-selected"]);
  });
  it("rejects undefined references and cycles before asset generation", () => {
    expect(() => themeValues(":root { --a: var(--missing); }", "light")).toThrow("Undefined");
    expect(() => themeValues(":root { --a: var(--b); --b: var(--a); }", "light")).toThrow("Cyclic");
  });
  for (const mode of ["light", "dark"] as const) {
    it(`${mode}: inactive controls stay visibly subdued while retaining discernible labels`, () => {
      const values = themeValues(css, mode);
      for (const background of ["disabled-bg", "surface"] as const) {
        const ratio = contrast(values["--os-disabled-text"], values[`--os-${background}`]);
        expect(ratio, background).toBeGreaterThanOrEqual(2.5);
        expect(ratio, background).toBeLessThanOrEqual(3.5);
      }
    });
    it(`${mode}: syntax highlighting stays readable on the code surface`, () => {
      const values = themeValues(css, mode);
      for (const role of ["comment", "keyword", "string", "constant", "function"])
        expect(
          contrast(values[`--os-code-${role}`], values["--os-muted"]),
          role,
        ).toBeGreaterThanOrEqual(4.5);
    });
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
