import { ESLint } from "eslint";
import { describe, expect, it } from "vitest";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("./", import.meta.url));
const eslint = new ESLint({ cwd: root });
async function rules(file: string, code: string) {
  const [result] = await eslint.lintText(code, { filePath: path.join(root, file) });
  return result.messages
    .filter((message) => message.severity === 2)
    .map((message) => message.ruleId);
}

describe("ESLint project configuration", () => {
  it("allows the complete select entry and its internal primitive adapter", async () => {
    expect(
      await rules(
        "src/pages/agents/Example.tsx",
        "import { SelectField } from '@/components/ui/SelectField'; export function Example() { return <SelectField aria-label='岗位' options={[{value: 'a', label: 'A'}]} value='a' onValueChange={() => {}} />; }",
      ),
    ).not.toContain("boundaries/dependencies");
    expect(
      await rules(
        "src/components/ui/Example.tsx",
        "import { Select } from './Select'; export function Example() { return <Select />; }",
      ),
    ).not.toContain("boundaries/dependencies");
  });
  it.each([
    "import { Select } from '@/components/ui/Select'; export function Example() { return <Select />; }",
    "import { Select } from '../../components/ui/Select'; export function Example() { return <Select />; }",
    "export { Select as Example } from '@/components/ui/Select';",
    "export async function Example() { return import('@/components/ui/Select'); }",
  ])("rejects business access to select primitives: %s", async (code) => {
    expect(await rules("src/pages/agents/Example.tsx", code)).toContain("boundaries/dependencies");
  });
  it.each(["<select />", "<option value='a'>A</option>"])(
    "rejects native dropdown choices outside the shared UI layer: %s",
    async (jsx) => {
      expect(
        await rules("src/pages/agents/Example.tsx", `export function Example() { return ${jsx}; }`),
      ).toContain("no-restricted-syntax");
    },
  );
  it.each([
    ["src/components/common/Example.tsx", "export function Example() { return <div/>; }"],
    [
      "src/components/common/Example.tsx",
      "export const Example = () => <div/>; export const ExampleTitle = () => <h2/>;",
    ],
    [
      "src/components/common/Example.tsx",
      "import { memo } from 'react'; export const Example = memo(function Example() { return <div/>; });",
    ],
    [
      "src/components/common/Example.tsx",
      "function Card() { return <div/>; } export { Card as Example };",
    ],
    [
      "src/components/common/Example.tsx",
      "export { Button as Example } from '@/components/ui/Button';",
    ],
    ["src/components/common/Example.tsx", "export default function Example() { return <div/>; }"],
    ["src/components/common/Example.tsx", "const Example = () => <div/>; export default Example;"],
    [
      "src/components/common/Example.tsx",
      "import { memo } from 'react'; export const Example = memo(function render() { return <div/>; });",
    ],
    ["src/components/common/example.ts", "export function useExample() { return 1; }"],
    [
      "src/components/common/example.ts",
      "import { useState } from 'react'; export function useExample() { return useState(0); }",
    ],
    ["src/hooks/index.ts", "import { useDraft } from './useDraft'; export { useDraft };"],
    ["src/hooks/useExample.test.tsx", "export const value = <div/>;"],
    ["src/hooks/useExample.ts", "export function useExample() { return 1; }"],
    [
      "src/components/common/Example.tsx",
      "export function Example({ offset }: { offset: number }) { return <div className='translate-x-(--indicator-x)' style={{ '--indicator-x': `${offset}px` } as React.CSSProperties}/>; }",
    ],
    [
      "src/components/common/Example.tsx",
      "function cssValue({ value, unit }: { value: number; unit: string }) { return `${value}${unit}`; } export function Example({ offset }: { offset: number }) { return <div style={{ width: cssValue({ value: offset, unit: 'px' }) }}/>; }",
    ],
    ["src/lib/example.test.ts", "export const example = 1;"],
    ["src/main.tsx", "export const root = <div/>;"],
    ["src/router.tsx", "export const routes = [{ element: <div/> }];"],
    ["src/pages/help/ExamplePage.tsx", "export function ExamplePage() { return <main/>; }"],
    ["src/lib/api/example.ts", "export type ExampleDTO = { resource_id: string };"],
    [
      "src/pages/design-system/useThemeValues.ts",
      "import css from '@/design-system/theme.css?raw'; export const source = css;",
    ],
    [
      "src/components/ui/Example.tsx",
      "export { MessageScroller as Example } from '@shadcn/react/message-scroller';",
    ],
  ])("accepts the role of %s", async (file, code) => {
    expect(await rules(file, code)).toEqual([]);
  });

  it.each([
    [
      "src/components/common/example-card.tsx",
      "export function ExampleCard() { return <div/>; }",
      "check-file/filename-naming-convention",
    ],
    [
      "src/lib/example-name.ts",
      "export const example = 1;",
      "check-file/filename-naming-convention",
    ],
    [
      "src/components/BadFolder/Example.tsx",
      "export function Example() { return <div/>; }",
      "check-file/folder-naming-convention",
    ],
    [
      "src/components/common/Example.tsx",
      "export function WrongName() { return <div/>; }",
      "project/matching-component-export",
    ],
    [
      "src/components/common/Example.tsx",
      "export type Example = { value: string }; export function WrongName() { return <div/>; }",
      "project/matching-component-export",
    ],
    [
      "src/components/common/Example.tsx",
      "type Example = { value: string }; export { Example };",
      "project/matching-component-export",
    ],
    [
      "src/components/common/Example.tsx",
      "type Example = { value: string }; export default Example;",
      "project/matching-component-export",
    ],
    [
      "src/components/common/Example.tsx",
      "function Example() { return <div/>; } export { Example as Other };",
      "project/matching-component-export",
    ],
    [
      "src/components/common/Example.tsx",
      "export default () => <div/>;",
      "project/matching-component-export",
    ],
    [
      "src/components/common/Example.tsx",
      "export function Example() { return <div style={{ height: 32 }}/>; }",
      "no-restricted-syntax",
    ],
    [
      "src/components/common/Example.tsx",
      "export function Example() { return <div style={{ color: 'red' }}/>; }",
      "no-restricted-syntax",
    ],
    [
      "src/components/common/Example.tsx",
      "export function Example() { return <div style={{ top: -8 }}/>; }",
      "no-restricted-syntax",
    ],
    [
      "src/components/common/Example.tsx",
      "export function Example() { return <div style={{ height: 32 } as React.CSSProperties}/>; }",
      "no-restricted-syntax",
    ],
    [
      "src/components/common/Example.tsx",
      "export function Example() { return <div style={{ color: `red` } satisfies React.CSSProperties}/>; }",
      "no-restricted-syntax",
    ],
    [
      "src/lib/example.ts",
      "const modulePath = '@/components/ui/Button'; export const load = () => import(modulePath);",
      "no-restricted-syntax",
    ],
    [
      "src/components/common/example.ts",
      "export const load = () => import('./page.css');",
      "no-restricted-syntax",
    ],
    [
      "src/components/common/example.ts",
      "export const load = () => import('package/page.css?inline');",
      "no-restricted-syntax",
    ],
    [
      "src/components/common/example.ts",
      "import css from 'package/page.css?inline'; export { css };",
      "no-restricted-imports",
    ],
    [
      "src/components/common/example.ts",
      "import css from '@/design-system/theme.css?raw'; export { css };",
      "no-restricted-imports",
    ],
    [
      "src/lib/example.ts",
      "export const load = require('../components/ui/Button');",
      "no-restricted-syntax",
    ],
    [
      "src/router.tsx",
      "export const load = () => import('./pages/agents/AgentCard');",
      "boundaries/dependencies",
    ],
    ["src/lib/example.ts", "export const bad_name = 1;", "@typescript-eslint/naming-convention"],
    [
      "src/pages/help/ExamplePage.tsx",
      "import './page.css'; export function ExamplePage() { return <main/>; }",
      "no-restricted-imports",
    ],
    [
      "src/lib/example.ts",
      "import { useState } from 'react'; export const state = useState;",
      "boundaries/dependencies",
    ],
    [
      "src/pages/help/ExamplePage.tsx",
      "import { MessageScroller } from '@shadcn/react/message-scroller'; export const ExamplePage = MessageScroller.Root;",
      "boundaries/dependencies",
    ],
    [
      "src/pages/help/ExamplePage.tsx",
      "import { Tabs } from '@base-ui/react/tabs'; export const ExamplePage = Tabs.Root;",
      "boundaries/dependencies",
    ],
  ])("rejects the invalid role of %s", async (file, code, rule) => {
    expect(await rules(file, code)).toContain(rule);
  });

  it.each([
    ["src/lib/example.ts", "import { useState } from 'react'; export const state = useState;"],
    [
      "src/pages/help/ExamplePage.tsx",
      "import { Tabs } from '@base-ui/react/tabs'; export const ExamplePage = Tabs.Root;",
    ],
    ["src/components/ui/example.ts", "export const load = () => import('radix-ui');"],
  ])("reports a restricted library once in %s", async (file, code) => {
    expect(await rules(file, code)).toEqual(["boundaries/dependencies"]);
  });

  it.each([
    "export const load = () => import('./pages/agents/AgentCard');",
    "export const load = () => import('@/pages/agents/AgentCard');",
    "export const load = () => import('././pages/agents/AgentCard');",
    "export { AgentCard } from './pages/agents/AgentCard';",
    "export * from '@/pages/agents/AgentCard';",
  ])("restricts router imports to resolved Page entries: %s", async (code) => {
    expect(await rules("src/router.tsx", code)).toEqual(["boundaries/dependencies"]);
  });

  it.each([
    "export const load = () => import('./pages/agents/AgentsPage');",
    "export const load = () => import('@/pages/design-system/DesignSystemPage');",
    "export const load = () => import('././pages/agents/AgentsPage');",
  ])("accepts a resolved router Page entry: %s", async (code) => {
    expect(await rules("src/router.tsx", code)).toEqual([]);
  });

  it.each([
    "export { Button } from '@/components/ui/Button';",
    "export { Button } from '../components/ui/Button';",
    "export const load = () => import('@/components/ui/Button');",
    "export const load = () => import('../components/ui/Button');",
    "export { useTheme } from '@/state/theme/useTheme';",
    "export { useDraft } from '@/hooks/useDraft';",
  ])("rejects a reverse lib dependency: %s", async (code) => {
    expect(await rules("src/lib/example.ts", code)).toContain("boundaries/dependencies");
  });

  it.each([
    "export { DesignSystemPage } from '@/pages/design-system/DesignSystemPage';",
    "export const load = () => import('../../pages/design-system/DesignSystemPage');",
  ])("rejects production dependencies on the showcase", async (code) => {
    expect(await rules("src/components/common/example.ts", code)).toContain(
      "boundaries/dependencies",
    );
  });

  it("keeps page internals private while allowing the showcase public display entry", async () => {
    expect(
      await rules(
        "src/pages/skills/example.ts",
        "export { AgentCard } from '../agents/AgentCard';",
      ),
    ).toContain("boundaries/dependencies");
    expect(
      await rules("src/pages/design-system/example.ts", "export { AgentCard } from '../agents';"),
    ).toEqual([]);
    expect(
      await rules(
        "src/pages/design-system/example.ts",
        "export { AgentConfiguration } from '../agents/AgentConfiguration';",
      ),
    ).toContain("boundaries/dependencies");
  });

  it.each([
    [
      "src/components/ui/example.ts",
      "export { useWorkspaceData } from '@/state/workspace/useWorkspaceData';",
    ],
    ["src/components/ui/example.ts", "export { loadConfiguration } from '@/lib/api/agents';"],
    ["src/components/ui/example.ts", "export type { Agent } from '@/lib/models/agent';"],
    ["src/state/auth/example.ts", "export { Button } from '@/components/ui/Button';"],
    ["src/hooks/useExample.ts", "export { useIdentity } from '@/state/auth/useIdentity';"],
    ["src/components/common/example.ts", "export { AgentCard } from '@/pages/agents';"],
  ])("rejects an invalid layer dependency in %s", async (file, code) => {
    expect(await rules(file, code)).toContain("boundaries/dependencies");
  });

  it("accepts an ordinary JSX rendering helper within a component", async () => {
    expect(
      await rules(
        "src/components/common/Example.tsx",
        "function row() { return <span/>; } export function Example() { return <div>{row()}</div>; }",
      ),
    ).toEqual([]);
  });

  it("accepts dependencies within one page module", async () => {
    expect(
      await rules("src/pages/agents/example.ts", "export { AgentCard } from './AgentCard';"),
    ).toEqual([]);
  });

  it.each(["export const load = () => import('react');", "export { useState } from 'react';"])(
    "rejects dynamic and re-exported React dependencies in lib",
    async (code) => {
      expect(await rules("src/lib/example.ts", code)).toContain("boundaries/dependencies");
    },
  );

  it("excludes source-managed avatar assets and generated catalogues explicitly", async () => {
    expect(
      await eslint.isPathIgnored(path.join(root, "src/components/avatars/svg/intern-bull.tsx")),
    ).toBe(true);
    expect(
      await eslint.isPathIgnored(path.join(root, "src/lib/avatars/manifest.generated.ts")),
    ).toBe(true);
    expect(await eslint.isPathIgnored(path.join(root, "src/pages/agents/AgentsPage.tsx"))).toBe(
      false,
    );
  });
});
