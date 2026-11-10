import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { SvgAvatar, svgCharacters } from "./svgAvatar";

describe("local SVG avatar components", () => {
  it("renders all thirteen approved characters using the project's React version", () => {
    expect(svgCharacters).toHaveLength(13);
    for (const { id, label } of svgCharacters) {
      const markup = renderToStaticMarkup(
        createElement(SvgAvatar, { character: id, alt: label, size: 48 }),
      );
      expect(markup).toContain(`data-avatar-character="${id}"`);
      expect(markup).toContain(`aria-label="${label}"`);
      expect(markup).toContain('width="48" height="48"');
      expect(markup).not.toMatch(/<image|<img|<canvas|<script|\.wasm/);
    }
  });
  it("isolates every gradient, clip and translucent mask across repeated characters", () => {
    const markup = renderToStaticMarkup(
      createElement(
        "div",
        null,
        ...svgCharacters.flatMap(({ id }) => [
          createElement(SvgAvatar, { character: id, key: id + "-1" }),
          createElement(SvgAvatar, { character: id, key: id + "-2" }),
        ]),
      ),
    );
    const ids = [...markup.matchAll(/\bid="([^"]+)"/g)].map((match) => match[1]);
    expect(new Set(ids).size).toBe(ids.length);
    for (const match of markup.matchAll(/url\(#([^)]+)\)/g)) expect(ids).toContain(match[1]);
    expect(markup).toContain('aria-hidden="true"');
    expect(markup).toContain("<radialGradient");
    expect(markup).toContain('mask-type="luminance"');
    expect(markup).not.toContain("maskType=");
  });
});
