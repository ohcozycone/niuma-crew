import type { Item, Node, Root } from 'fumadocs-core/page-tree';
import { BookOpen, Code2, Compass } from 'lucide-react';

export const docSections = [
  {
    id: 'platform',
    title: '平台介绍',
    icon: Compass,
    url: '/docs/start',
    chapters: ['start'],
  },
  {
    id: 'development',
    title: '技术解析',
    icon: Code2,
    url: '/docs/development/start',
    chapters: ['development'],
  },
  {
    id: 'usage',
    title: '使用指南',
    icon: BookOpen,
    url: '/docs/start/first-conversation',
    chapters: ['usage', 'tutorials', 'deployment', 'help'],
  },
] as const;

export function getDocSection(pathname: string, sourceFile?: string) {
  const chapter = pathname.split('/')[2];
  // 既有操作网址继续可用，阅读分类按内容归属。
  if (/^\/docs\/start\/(?:first-conversation|features)\/?$/.test(pathname)) return docSections[2];
  if (chapter === 'library') {
    if (sourceFile === 'docs/guides/local-development.md') return docSections[1];
    if (sourceFile === 'docs/product/workflows.md' || sourceFile?.startsWith('docs/guides/'))
      return docSections[2];
    if (sourceFile?.startsWith('docs/product/')) return docSections[0];
    return docSections[1];
  }
  return (
    docSections.find((section) => section.chapters.some((value) => value === chapter)) ??
    docSections[0]
  );
}

function articleList(nodes: Node[]): Item[] {
  return nodes.flatMap((node) => {
    if (node.type === 'page') return [node];
    if (node.type === 'folder')
      return [...(node.index ? [node.index] : []), ...articleList(node.children)];
    return [];
  });
}

export function getSectionTree(
  tree: Root,
  pathname: string,
  sourceFile?: string,
  pageGroups: Record<string, string> = {},
): Root {
  const section = getDocSection(pathname, sourceFile);
  const articles = articleList(tree.children).filter(
    (page) => getDocSection(page.url).id === section.id,
  );
  // 进一步阅读沿用所属分类的主目录，并提供当前文章入口。
  const current = articleList(tree.fallback?.children ?? []).find(
    (page) => page.url.replace(/\/$/, '') === pathname.replace(/\/$/, ''),
  );
  if (current && !articles.some((page) => page.url === current.url)) articles.push(current);
  const groups = new Map<string, Item[]>();
  for (const page of articles) {
    const group = pageGroups[page.url.replace(/\/$/, '')] ?? '更多资料';
    const entries = groups.get(group) ?? [];
    entries.push(page);
    groups.set(group, entries);
  }
  // 无分组元数据时保持普通文章列表，避免把分类名重复渲染成目录。
  const children: Node[] =
    groups.size > 1
      ? [...groups].flatMap(([name, entries]) =>
          name === '开发参考' && entries.length === 1
            ? entries
            : [{ type: 'separator' as const, name }, ...entries],
        )
      : articles;
  return { $id: `docs-${section.id}-${pathname}`, name: section.title, children };
}
