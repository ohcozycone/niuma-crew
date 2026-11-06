import { mkdir, readFile, readdir, realpath, rename, rm, stat, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { unified } from 'unified';
import remarkParse from 'remark-parse';
import remarkGfm from 'remark-gfm';
import remarkStringify from 'remark-stringify';
import { visit } from 'unist-util-visit';
import { chapters, pages } from './content.mjs';

export const siteRoot = fileURLToPath(new URL('../', import.meta.url));
export const repoRoot = path.dirname(siteRoot);
const processor = unified()
  .use(remarkParse)
  .use(remarkGfm)
  .use(remarkStringify, { bullet: '-', fences: true });
const safeExtensions = new Set([
  '.md',
  '.mdx',
  '.py',
  '.ts',
  '.tsx',
  '.js',
  '.mjs',
  '.css',
  '.json',
  '.toml',
  '.yml',
  '.yaml',
  '.ini',
  '.txt',
  '.sh',
  '.sql',
  '.service',
  '.conf',
  '.html',
  '.lock',
]);
const assetExtensions = new Set([
  '.svg',
  '.png',
  '.jpg',
  '.jpeg',
  '.webp',
  '.gif',
  '.pdf',
  '.woff2',
]);

export function resolveRepositoryPath(from, target, root = repoRoot) {
  const absolute = path.resolve(root, path.dirname(from), decodeURIComponent(target));
  if (absolute !== root && !absolute.startsWith(`${root}${path.sep}`)) return null;
  return path.relative(root, absolute).split(path.sep).join('/');
}

export function selectSections(tree, names, file) {
  if (!names)
    return {
      ...tree,
      children: tree.children.filter((node) => node.type !== 'heading' || node.depth !== 1),
    };
  const children = [];
  for (const name of names) {
    const start = tree.children.findIndex(
      (node) => node.type === 'heading' && headingText(node) === name,
    );
    if (start < 0) throw new Error(`${file} 找不到章节：${name}`);
    const depth = tree.children[start].depth;
    const next = tree.children.findIndex(
      (node, i) => i > start && node.type === 'heading' && node.depth <= depth,
    );
    const selected = structuredClone(tree.children.slice(start, next < 0 ? undefined : next));
    // 从产品说明的三级标题提取成独立页面时，保持本页标题层级连续。
    visit({ type: 'root', children: selected }, 'heading', (node) => {
      node.depth -= depth - 2;
    });
    children.push(...selected);
  }
  return { type: 'root', children };
}

function headingText(node) {
  return (node.children ?? []).map((child) => child.value ?? headingText(child)).join('');
}

function isPublishedMarkdown(file) {
  if (!file.endsWith('.md')) return false;
  if (file.startsWith('backend/datasets/')) return false;
  if (/^docs\/(proposals|records|codebase|templates)\//.test(file)) return false;
  return file.startsWith('docs/') || /^(frontend|backend)\/(src\/|app\/)?/.test(file);
}

function librarySlug(file) {
  return `library/${file.replace(/\.md$/, '').replace(/\/README$/, '/overview')}`;
}

function stageJson(outputs, file, data) {
  outputs.set(file, `${JSON.stringify(data, null, 2)}\n`);
}

async function publishFiles(outputs) {
  for (const [file, content] of outputs) {
    const bytes = Buffer.isBuffer(content) ? content : Buffer.from(content);
    try {
      if ((await readFile(file)).equals(bytes)) continue;
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
    }
    await mkdir(path.dirname(file), { recursive: true });
    const temporary = path.join(path.dirname(file), `.${path.basename(file)}.${randomUUID()}.tmp`);
    try {
      await writeFile(temporary, bytes);
      await rename(temporary, file);
    } finally {
      await rm(temporary, { force: true });
    }
  }
}

async function removeStaleContent(directory, outputs) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const file = path.join(directory, entry.name);
    if (entry.isDirectory()) await removeStaleContent(file, outputs);
    else if (!outputs.has(file)) await rm(file);
  }
}

export async function syncContent(options = {}) {
  const sourceRoot = options.repoRoot ?? repoRoot;
  const outputRoot = options.siteRoot ?? siteRoot;
  const documentPages = options.pages ?? pages;
  const chapterList = options.chapters ?? chapters;
  const contentRoot = path.join(outputRoot, '.generated/content/docs');
  const outputs = new Map();
  const assetOutputs = new Map();
  const trees = new Map();
  const published = new Map();
  const pending = [];
  const sourceFiles = new Map();
  const assets = new Set();
  const links = [];
  const omitted = new Set();
  const canonical = new Map(
    documentPages.filter((page) => !page.sections).map((page) => [page.file, page.slug]),
  );

  async function treeFor(file) {
    if (!trees.has(file))
      trees.set(file, processor.parse(await readFile(path.join(sourceRoot, file), 'utf8')));
    return structuredClone(trees.get(file));
  }

  function enqueue(page) {
    if (published.has(page.slug)) return;
    published.set(page.slug, page);
    pending.push(page);
  }

  async function addSource(file) {
    if (sourceFiles.has(file)) return;
    const absolute = path.join(sourceRoot, file);
    const info = await stat(absolute);
    let text;
    if (info.isDirectory()) {
      const entries = await readdir(absolute, { withFileTypes: true });
      text = entries
        .filter((entry) => !entry.name.startsWith('.') && entry.name !== 'node_modules')
        .map((entry) => `${entry.name}${entry.isDirectory() ? '/' : ''}`)
        .sort()
        .join('\n');
    } else {
      if (
        !safeExtensions.has(path.extname(file)) &&
        !['Makefile', 'Dockerfile', 'LICENSE'].includes(path.basename(file)) &&
        !file.endsWith('/.env.example') &&
        !file.endsWith('.conf.example')
      ) {
        throw new Error(`禁止发布未明确允许的源码类型：${file}`);
      }
      text = await readFile(absolute, 'utf8');
    }
    sourceFiles.set(file, {
      path: file,
      content: text,
      historical: /^docs\/(records|proposals|codebase)\//.test(file),
    });
  }

  for (const page of documentPages) enqueue(page);
  const pageIndex = {};

  while (pending.length) {
    const page = pending.shift();
    const originalTree = await treeFor(page.file);
    const title =
      page.title ??
      headingText(
        originalTree.children.find((node) => node.type === 'heading') ?? { children: [] },
      );
    const tree = selectSections(originalTree, page.sections, page.file);
    await addSource(page.file);
    const destinations = [];
    visit(tree, (node) => {
      if (node.type === 'link' || node.type === 'image' || node.type === 'definition')
        destinations.push(node);
    });
    for (const node of destinations) {
      const value = node.url;
      if (!value || /^(?:[a-z][a-z\d+.-]*:|\/\/)/i.test(value) || value.startsWith('#')) continue;
      const [target, fragment] = value.split('#');
      const relative = resolveRepositoryPath(page.file, target, sourceRoot);
      if (relative === null) {
        omitted.add(value);
        node.type = 'text';
        node.value = `${headingText(node) || node.alt || '归档材料'}（仓库外归档）`;
        delete node.children;
        delete node.url;
        continue;
      }
      let resolved = relative;
      let info;
      try {
        info = await stat(path.join(sourceRoot, resolved));
        const actual = await realpath(path.join(sourceRoot, resolved));
        if (!actual.startsWith(`${sourceRoot}${path.sep}`)) throw new Error('符号链接越过仓库边界');
      } catch (error) {
        throw new Error(`${page.file} 引用了不可访问的路径 ${value}: ${error.message}`);
      }
      if (info.isDirectory()) {
        try {
          await stat(path.join(sourceRoot, resolved, 'README.md'));
          resolved = `${resolved}/README.md`;
          info = await stat(path.join(sourceRoot, resolved));
        } catch {
          /* 无 README 的源码目录使用只读目录清单。 */
        }
      }
      if (resolved === 'docs/README.md') {
        node.url = '/';
      } else if (isPublishedMarkdown(resolved)) {
        const slug = canonical.get(resolved) ?? librarySlug(resolved);
        enqueue({ slug, file: resolved });
        node.url = `/docs/${slug}${fragment ? `#${fragment}` : ''}`;
      } else if (assetExtensions.has(path.extname(resolved).toLowerCase())) {
        assets.add(resolved);
        node.url = `/repository/${resolved}${fragment ? `#${fragment}` : ''}`;
      } else {
        await addSource(resolved);
        node.url = `/sources/${resolved}`;
      }
      links.push({ from: `/docs/${page.slug}`, to: node.url });
    }
    const markdown = processor.stringify(tree);
    const frontmatter = `---\ntitle: ${JSON.stringify(title)}\ndescription: ${JSON.stringify(page.description ?? `来自 ${page.file} 的现行说明。`)}\n---\n\n`;
    const file = page.slug === 'start' ? 'start/index.md' : `${page.slug}.md`;
    outputs.set(path.join(contentRoot, file), frontmatter + markdown);
    pageIndex[page.slug] = {
      file: page.file,
      title,
      sections: page.sections ?? [],
      primary: documentPages.some((item) => item.slug === page.slug),
      searchDescription: page.searchDescription ?? null,
    };
  }

  stageJson(outputs, path.join(contentRoot, 'meta.json'), {
    title: '文档',
    pages: chapterList.map((chapter) => chapter.slug),
  });
  for (const chapter of chapterList) {
    const chapterPages = documentPages.filter((page) => page.slug.split('/')[0] === chapter.slug);
    stageJson(outputs, path.join(contentRoot, chapter.slug, 'meta.json'), {
      title: chapter.title,
      icon: chapter.icon,
      defaultOpen: true,
      pages: chapterPages.map((page) =>
        page.slug === chapter.slug ? 'index' : page.slug.split('/').slice(1).join('/'),
      ),
    });
  }
  for (const asset of assets) {
    assetOutputs.set(
      path.join(outputRoot, 'public/repository', asset),
      await readFile(path.join(sourceRoot, asset)),
    );
  }
  for (const file of ['mark.svg', 'wordmark.svg', 'wordmark-dark.svg', 'icon-32.png']) {
    assetOutputs.set(
      path.join(outputRoot, 'public/brand', file),
      await readFile(path.join(sourceRoot, 'frontend/public/brand', file)),
    );
  }
  const theme = await readFile(
    path.join(sourceRoot, 'frontend/src/design-system/theme.css'),
    'utf8',
  );
  const tokens = theme
    .split('@theme inline')[0]
    .replaceAll(':root[data-theme="dark"]', ':root.dark');
  outputs.set(path.join(outputRoot, '.generated/theme.css'), tokens);
  stageJson(outputs, path.join(outputRoot, '.generated/page-index.json'), pageIndex);
  stageJson(
    outputs,
    path.join(outputRoot, '.generated/source-index.json'),
    Object.fromEntries(sourceFiles),
  );
  stageJson(outputs, path.join(outputRoot, '.generated/publish-report.json'), {
    primary: documentPages.length,
    pages: published.size,
    sources: sourceFiles.size,
    assets: assets.size,
    omitted: [...omitted],
    links,
  });
  // 热更新时不能清空目录：Webpack 仍可能读取上一轮文档引用的资源。
  // 完整读取与校验成功后，先发布资源，再原子替换变化的正文；不改写未变文件。
  await publishFiles(assetOutputs);
  await publishFiles(outputs);
  await removeStaleContent(contentRoot, outputs);
  console.log(
    `文档同步：${documentPages.length} 篇主导航，${published.size} 篇正文，${sourceFiles.size} 份原文，${assets.size} 项资源。`,
  );
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url))
  await syncContent();
