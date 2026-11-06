/** Build/test adapter for the flat declarations in theme.css; UI reads computed CSS. */
export type ThemeMode = "light" | "dark";

export function themeDeclarations(css: string, mode: ThemeMode): Record<string, string> {
  const clean = css.replace(/\/\*[\s\S]*?\*\//g, "");
  const declarations = (selector: string) => {
    const body = clean.match(new RegExp(`${selector}\\s*\\{([^}]+)\\}`))?.[1];
    if (!body) throw new Error(`Missing theme selector: ${selector}`);
    return Object.fromEntries(
      [...body.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)].map(([, name, value]) => [
        name,
        value.trim(),
      ]),
    );
  };
  return {
    ...declarations(":root"),
    ...(mode === "dark" ? declarations(':root\\[data-theme="dark"\\]') : {}),
  };
}

export function themeValues(css: string, mode: ThemeMode): Record<string, string> {
  const values = themeDeclarations(css, mode);
  const resolved: Record<string, string> = {};
  function resolve(name: string, chain: string[] = []): string {
    if (resolved[name] !== undefined) return resolved[name];
    if (!(name in values)) throw new Error(`Undefined theme variable: ${name}`);
    if (chain.includes(name))
      throw new Error(`Cyclic theme variable: ${[...chain, name].join(" → ")}`);
    return (resolved[name] = values[name].replace(/var\((--[\w-]+)\)/g, (_, dependency) =>
      resolve(dependency, [...chain, name]),
    ));
  }
  for (const name of Object.keys(values)) resolve(name);
  return resolved;
}
