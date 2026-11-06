/** Derive the application lockup from the approved signin vector; no runtime SDK. */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const code = ts.transpileModule(
  fs.readFileSync(path.join(root, "src/components/brand/wordmarkSource.ts"), "utf8"),
  {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2020,
    },
  },
).outputText;
const { signinLogo } = await import(
  "data:text/javascript;base64," + Buffer.from(code).toString("base64")
);
const valuesCode = ts.transpileModule(
  fs.readFileSync(path.join(root, "src/design-system/themeValues.ts"), "utf8"),
  {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2020,
    },
  },
).outputText;
const { themeValues } = await import(
  "data:text/javascript;base64," + Buffer.from(valuesCode).toString("base64")
);
const themeCss = fs.readFileSync(path.join(root, "src/design-system/theme.css"), "utf8");
const output = path.join(root, "public/brand");
// The application lockup has the settled letters; only the lids blink gently.
const blink = `<style>@keyframes brand-left-blink{0%,91%,95%,100%{d:path('M20 60C19 45 30 43 40 46C48 48 51 56 50 61Q35 57 20 61Z')}93%{d:path('M20 60C19 45 30 43 40 46C48 48 51 56 50 78Q35 83 20 78Z')}}@keyframes brand-right-blink{0%,91%,95%,100%{d:path('M57 58C57 45 69 43 76 48C81 51 82 55 81 59Q68 56 57 59Z')}93%{d:path('M57 58C57 45 69 43 76 48C81 51 82 55 81 75Q68 80 57 75Z')}}#brand-left-lid{animation:brand-left-blink 6.8s ease-in-out infinite}#brand-right-lid{animation:brand-right-blink 6.8s ease-in-out infinite}@media(prefers-reduced-motion:reduce){#brand-left-lid,#brand-right-lid{animation:none}}</style>`;
const lockup = (ink) =>
  signinLogo
    .replace(
      '<g id="l-logo-art">',
      `<style>:root{--logo-ink:${ink}}</style>` + blink + '<g id="l-logo-art">',
    )
    .replace('<path d="M20 60', '<path id="brand-left-lid" d="M20 60')
    .replace('<path d="M57 58', '<path id="brand-right-lid" d="M57 58');
fs.mkdirSync(output, { recursive: true });
fs.writeFileSync(
  path.join(output, "wordmark.svg"),
  lockup(themeValues(themeCss, "light")["--os-text"]) + "\n",
);
fs.writeFileSync(
  path.join(output, "wordmark-dark.svg"),
  lockup(themeValues(themeCss, "dark")["--os-text"]) + "\n",
);
// The favicon has its own square composition; cropping the lockup includes part of N.
fs.copyFileSync(path.join(root, "src/components/brand/mark.svg"), path.join(output, "mark.svg"));
console.log("Brand vectors generated from signin and standalone mark sources");
