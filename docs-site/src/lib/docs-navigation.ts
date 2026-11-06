import type { Item, Node, Root } from 'fumadocs-core/page-tree';

export const docSections = [
  {
    id: 'usage',
    title: '使用文档',
    url: '/docs/start',
    chapters: ['start', 'usage', 'tutorials', 'help'],
  },
  { id: 'deployment', title: '部署指南', url: '/docs/deployment/local', chapters: ['deployment'] },
  {
    id: 'development',
    title: '开发指南',
    url: '/docs/development/architecture',
    chapters: ['development'],
  },
] as const;

export function getDocSection(pathname: string, sourceFile?: string) {
  const chapter = pathname.split('/')[2];
  if (chapter === 'library') {
    if (
      sourceFile &&
      /(?:^docs\/guides\/(?:local-development|backend-operations|database-configuration)\.md$)/.test(
        sourceFile,
      )
    )
      return docSections[1];
    if (sourceFile && /^(?:docs\/(?:product|reference)\/)/.test(sourceFile)) return docSections[0];
    return docSections[2];
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

export function getSectionTree(tree: Root, pathname: string, sourceFile?: string): Root {
  const section = getDocSection(pathname, sourceFile);
  const articles = articleList(tree.children).filter((page) =>
    section.chapters.some(
      (chapter) => page.url.startsWith(`/docs/${chapter}/`) || page.url === `/docs/${chapter}`,
    ),
  );
  // 进一步阅读沿用所属分类的主目录，并提供当前文章入口。
  const current = articleList(tree.fallback?.children ?? []).find(
    (page) => page.url.replace(/\/$/, '') === pathname.replace(/\/$/, ''),
  );
  if (current && !articles.some((page) => page.url === current.url)) articles.push(current);
  return { $id: `docs-${section.id}-${pathname}`, name: section.title, children: articles };
}
