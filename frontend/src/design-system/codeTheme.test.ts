import { expect, it } from "vitest";
import { createCodePlugin, type HighlightResult } from "@streamdown/code";
import codeTheme from "./codeTheme.json";

it("highlights real code with theme references instead of an independent palette", async () => {
  const plugin = createCodePlugin({
    themes: [
      { ...codeTheme, name: "niuma-light", type: "light" },
      { ...codeTheme, name: "niuma-dark", type: "dark" },
    ],
  });
  const result = await new Promise<HighlightResult>((resolve) => {
    const immediate = plugin.highlight(
      {
        code: '// comment\nconst greeting = "hello";\nconsole.log(greeting);',
        language: "javascript",
        themes: plugin.getThemes(),
      },
      resolve,
    );
    if (immediate) resolve(immediate);
  });
  const output = JSON.stringify(result);
  expect(
    result.tokens
      .flat()
      .map((token) => token.content)
      .join(""),
  ).toContain("greeting");
  for (const role of ["comment", "keyword", "string"])
    expect(output).toContain(`var(--os-code-${role})`);
  expect(output).not.toMatch(/#[\da-f]{3,8}\b/i);
});
