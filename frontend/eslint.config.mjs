import js from "@eslint/js";
import ts from "typescript-eslint";
import hooks from "eslint-plugin-react-hooks";
import react from "eslint-plugin-react";
import checkFile from "eslint-plugin-check-file";
import boundaries from "eslint-plugin-boundaries";
import globals from "globals";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("./", import.meta.url));
const element = (type, pattern, extra = {}) => ({ type, pattern, ...extra });
const shared = [
  "component",
  "ui",
  "state",
  "hook",
  "utility",
  "api",
  "model",
  "avatar-data",
  "design",
];
const types = (values) =>
  values.map((type) =>
    ["entry", "router"].includes(type) ? { file: { categories: type } } : { element: { type } },
  );
const allow = (from, targets) => ({ from: types(from), allow: { to: types(targets) } });
const styles = {
  group: ["**/*.css", "**/*.css?*", "styled-components", "@emotion/**"],
  message: "Use Tailwind utilities and the central globals.css entry.",
};
const radixLibraries = ["radix-ui", "radix-ui/**", "@radix-ui/**"];
const headlessLibraries = [
  "@base-ui/react",
  "@base-ui/react/**",
  "@shadcn/react",
  "@shadcn/react/**",
  ...radixLibraries,
];
const inlineStyleProperty =
  ":matches(JSXAttribute[name.name='style'] > JSXExpressionContainer > ObjectExpression, JSXAttribute[name.name='style'] > JSXExpressionContainer > :matches(TSAsExpression, TSSatisfiesExpression) > ObjectExpression) > Property";
const syntax = [
  {
    selector: "JSXOpeningElement[name.name=/^(select|option)$/]",
    message: "Use SelectField with an options array for dropdown choices.",
  },
  {
    selector: `${inlineStyleProperty}:matches([value.type='Literal'], [value.type='TemplateLiteral'][value.expressions.length=0], [value.type='UnaryExpression'][value.operator=/^[+-]$/][value.argument.type='Literal'])`,
    message:
      "Use static Tailwind classes; style is reserved for runtime values and library styles.",
  },
  {
    selector: "ImportExpression[source.type!='Literal']",
    message: "Use explicit module paths so dependency boundaries can be checked.",
  },
  {
    selector: "ImportExpression[source.value=/\\.css($|[?])/]",
    message: "CSS is loaded through the central globals.css entry.",
  },
  {
    selector: "CallExpression[callee.name='require']",
    message: "Application source uses ES module imports with explicit paths.",
  },
];

// Only compare public value-export names; component detection belongs to React/TypeScript.
const matchingComponentExport = {
  meta: {
    type: "suggestion",
    schema: [],
    messages: { missing: "Export a value named '{{name}}' matching the component filename." },
  },
  create(context) {
    const name = path.basename(context.filename, ".tsx");
    let matches = false;
    const isValue = (node, local) =>
      context.sourceCode.getScope(node).set.get(local)?.isValueVariable === true;
    return {
      ExportNamedDeclaration(node) {
        if (node.exportKind === "type") return;
        const declaration = node.declaration;
        if (["FunctionDeclaration", "ClassDeclaration"].includes(declaration?.type))
          matches ||= declaration.id?.name === name;
        if (declaration?.type === "VariableDeclaration")
          matches ||= declaration.declarations.some((item) => item.id.name === name);
        matches ||= node.specifiers.some(
          (item) =>
            item.exportKind !== "type" &&
            (item.exported.name ?? item.exported.value) === name &&
            (Boolean(node.source) || isValue(node, item.local.name)),
        );
      },
      ExportDefaultDeclaration(node) {
        const declaration = node.declaration;
        if (["FunctionDeclaration", "ClassDeclaration"].includes(declaration.type))
          matches ||= declaration.id?.name === name;
        if (declaration.type === "Identifier")
          matches ||= declaration.name === name && isValue(node, declaration.name);
      },
      "Program:exit"(node) {
        if (!matches) context.report({ node, messageId: "missing", data: { name } });
      },
    };
  },
};
export default ts.config(
  {
    ignores: [
      "dist/**",
      "public/**",
      "src/components/avatars/svg/**",
      "src/lib/avatars/manifest.generated.ts",
    ],
  },
  js.configs.recommended,
  ...ts.configs.recommended,
  { languageOptions: { globals: { ...globals.browser, ...globals.node } } },
  {
    files: ["src/**/*.{ts,tsx}"],
    plugins: { "react-hooks": hooks, react, "check-file": checkFile, boundaries },
    settings: {
      react: { version: "19.3" },
      "import/resolver": {
        typescript: { project: fileURLToPath(new URL("./tsconfig.json", import.meta.url)) },
      },
      "boundaries/root-path": root,
      "boundaries/elements": [
        element("showcase", "src/pages/design-system"),
        element("page", "src/pages/*", { capture: ["module"] }),
        element("ui", "src/components/ui"),
        element("component", "src/components/*"),
        element("state", "src/state/*"),
        element("hook", "src/hooks"),
        element("api", "src/lib/api"),
        element("model", "src/lib/models"),
        element("avatar-data", "src/lib/avatars"),
        element("utility", "src/lib"),
        element("design", "src/design-system"),
      ],
      "boundaries/files": [
        { category: "router", pattern: "src/router.tsx" },
        { category: "entry", pattern: "src/*.{ts,tsx,css}" },
        { category: "test", pattern: "**/*.test.{ts,tsx}" },
        { category: "public-asset", pattern: "public/**" },
      ],
      "boundaries/dependency-nodes": ["import", "export", "dynamic-import", "require"],
    },
    rules: {
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      "react/jsx-pascal-case": "error",
      "no-restricted-syntax": ["error", ...syntax],
      "check-file/filename-naming-convention": [
        "error",
        { "src/**/*.tsx": "PASCAL_CASE", "src/**/*.ts": "CAMEL_CASE" },
        { ignoreMiddleExtensions: true },
      ],
      "check-file/folder-naming-convention": ["error", { "src/**/": "KEBAB_CASE" }],
      "@typescript-eslint/naming-convention": [
        "error",
        {
          selector: "variable",
          format: ["camelCase", "PascalCase", "UPPER_CASE"],
          leadingUnderscore: "allow",
        },
        { selector: "function", format: ["camelCase", "PascalCase"] },
        { selector: "parameter", format: ["camelCase", "PascalCase"], leadingUnderscore: "allow" },
        { selector: "typeLike", format: ["PascalCase"] },
      ],
      "no-restricted-imports": ["error", { patterns: [styles] }],
      "boundaries/dependencies": [
        "error",
        {
          default: "disallow",
          checkAllOrigins: true,
          checkUnknownLocals: true,
          policies: [
            { allow: { to: { module: { origin: ["external", "core"] } } } },
            allow(["router"], [...shared, "entry"]),
            {
              from: { file: { categories: "router" } },
              allow: {
                to: { element: { type: ["page", "showcase"], fileInternalPath: "**/*Page.tsx" } },
              },
            },
            allow(["entry"], [...shared, "entry", "router"]),
            allow(["page"], shared),
            {
              from: { element: { type: "page" } },
              allow: {
                to: {
                  element: {
                    type: "page",
                    captured: { module: "{{from.element.captured.module}}" },
                  },
                },
              },
            },
            allow(["showcase"], shared),
            {
              from: { element: { type: "showcase" } },
              allow: { to: { element: { type: "page", fileInternalPath: "index.ts" } } },
            },
            allow(["component"], shared),
            allow(["ui"], ["ui", "hook", "utility", "design"]),
            allow(["state"], ["state", "hook", "utility", "api", "model", "avatar-data"]),
            allow(["hook"], ["hook", "utility", "api", "model", "avatar-data"]),
            allow(
              ["utility", "api", "model", "avatar-data"],
              ["utility", "api", "model", "avatar-data"],
            ),
            allow(["design"], ["design"]),
            {
              from: { file: { categories: "test" } },
              allow: { to: { file: { categories: "public-asset" } } },
            },
            {
              from: types([
                ...shared.filter((type) => type !== "ui"),
                "page",
                "showcase",
                "entry",
                "router",
              ]),
              disallow: {
                to: {
                  module: {
                    origin: "external",
                    source: headlessLibraries,
                  },
                },
              },
            },
            {
              from: types(["ui"]),
              disallow: { to: { module: { origin: "external", source: radixLibraries } } },
            },
            {
              from: types([
                ...shared.filter((type) => type !== "ui"),
                "page",
                "showcase",
                "entry",
                "router",
              ]),
              disallow: {
                to: { element: { type: "ui", fileInternalPath: "Select.tsx" } },
              },
            },
            {
              from: types(["utility", "api", "model", "avatar-data"]),
              disallow: {
                to: {
                  module: {
                    origin: "external",
                    source: [
                      "react",
                      "react/**",
                      "react-dom",
                      "react-dom/**",
                      "react-router",
                      "react-router/**",
                    ],
                  },
                },
              },
            },
          ],
        },
      ],
    },
  },
  {
    files: ["src/lib/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-syntax": [
        "error",
        ...syntax,
        { selector: "JSXElement, JSXFragment", message: "lib cannot define JSX." },
      ],
    },
  },
  {
    // The showcase reads the canonical token source as data, without loading a stylesheet.
    files: ["src/pages/design-system/useThemeValues.ts"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [{ ...styles, group: [...styles.group, "!@/design-system/theme.css?raw"] }],
        },
      ],
    },
  },
  {
    files: ["src/**/[A-Z]*.tsx"],
    ignores: ["**/*.test.tsx", "**/*.spec.tsx"],
    plugins: { project: { rules: { "matching-component-export": matchingComponentExport } } },
    rules: { "project/matching-component-export": "error" },
  },
  {
    files: ["src/**/use*.tsx"],
    rules: {
      "check-file/filename-naming-convention": [
        "error",
        { "src/**/*.tsx": "CAMEL_CASE" },
        { ignoreMiddleExtensions: true },
      ],
    },
  },
  {
    files: ["src/**/*.test.tsx"],
    rules: {
      "check-file/filename-naming-convention": [
        "error",
        { "src/**/*.tsx": "@(*([A-Z]*([a-z0-9]))|+([a-z])*([a-z0-9])*([A-Z]*([a-z0-9])))" },
        { ignoreMiddleExtensions: true },
      ],
    },
  },
  {
    files: ["src/main.tsx", "src/router.tsx"],
    rules: { "check-file/filename-naming-convention": "off" },
  },
  {
    files: ["src/main.tsx"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              ...styles,
              group: [...styles.group, "!./globals.css"],
              message: "Only globals.css is the global style entry.",
            },
          ],
          paths: [],
        },
      ],
    },
  },
);
