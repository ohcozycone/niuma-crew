import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdir, mkdtemp, readFile, realpath, rm, stat, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { unified } from 'unified';
import remarkParse from 'remark-parse';
import { resolveRepositoryPath, selectSections, siteRoot, syncContent } from './sync-content.mjs';
import { chapters, pages } from './content.mjs';
import path from 'node:path';

test('内容引用解析限定在仓库内部，阻止编码后的目录穿越', () => {
  assert.equal(
    resolveRepositoryPath('docs/product/workflows.md', '../reference/auth.md'),
    'docs/reference/auth.md',
  );
  assert.equal(resolveRepositoryPath('docs/product/workflows.md', '../../../.env'), null);
  assert.equal(
    resolveRepositoryPath('docs/product/workflows.md', '%2e%2e/%2e%2e/%2e%2e/.env'),
    null,
  );
  assert.equal(resolveRepositoryPath('docs/product/workflows.md', '/etc/passwd'), null);
});

test('章节提取保留完整子节，遇到同级章节停止，缺失标题直接失败', () => {
  const tree = unified()
    .use(remarkParse)
    .parse(
      '# 文档\n\n## 主章\n\n### 目标\n\n正文。\n\n#### 子节\n\n补充。\n\n### 下一节\n\n不应出现。',
    );
  const selected = selectSections(tree, ['目标'], 'example.md');
  assert.deepEqual(
    selected.children.filter((node) => node.type === 'heading').map((node) => node.depth),
    [2, 3],
  );
  assert.equal(JSON.stringify(selected).includes('不应出现'), false);
  assert.throws(() => selectSections(tree, ['不存在'], 'example.md'), /找不到章节/);
});

test('发布后的所有内部链接都有正文、原文或资源目标', async () => {
  const read = async (file) =>
    JSON.parse(await readFile(path.join(siteRoot, '.generated', file), 'utf8'));
  const index = await read('page-index.json');
  const sources = await read('source-index.json');
  const report = await read('publish-report.json');
  assert.equal(chapters.length, 6);
  assert.equal(pages.length, 15);
  for (const page of pages) assert.equal(index[page.slug]?.primary, true, page.slug);
  for (const link of report.links) {
    const url = link.to.split('#')[0];
    if (url === '/') continue;
    if (url.startsWith('/docs/'))
      assert.ok(index[url.slice('/docs/'.length)], JSON.stringify(link));
    else if (url.startsWith('/sources/'))
      assert.ok(sources[url.slice('/sources/'.length)], JSON.stringify(link));
    else if (url.startsWith('/repository/')) await readFile(path.join(siteRoot, 'public', url));
    else assert.fail(`未处理的站内链接：${url}`);
  }
  assert.equal(
    Object.keys(sources).some((file) => /(?:^|\/)\.env$|\.(?:key|token|db|sqlite)$/.test(file)),
    false,
  );
});

async function fixture(t) {
  const root = await realpath(await mkdtemp(path.join(tmpdir(), 'docs-sync-test-')));
  t.after(() => rm(root, { recursive: true, force: true }));
  const write = async (file, text) => {
    const target = path.join(root, file);
    await mkdir(path.dirname(target), { recursive: true });
    await writeFile(target, text);
  };
  await write('docs/intro.md', '# 简介\n\n初始内容。\n\n![示意](diagram.svg)');
  await write('docs/diagram.svg', '<svg xmlns="http://www.w3.org/2000/svg" />');
  await write('frontend/src/design-system/theme.css', ':root { --os-text: black; }');
  for (const file of ['mark.svg', 'wordmark.svg', 'wordmark-dark.svg', 'icon-32.png']) {
    await write(`frontend/public/brand/${file}`, 'fixture');
  }
  const output = path.join(root, 'docs-site');
  const sync = () =>
    syncContent({
      repoRoot: root,
      siteRoot: output,
      pages: [{ slug: 'start', file: 'docs/intro.md', title: '简介' }],
      chapters: [{ slug: 'start', title: '快速开始' }],
    });
  await sync();
  return { root, output, write, sync };
}

test('正文更新不会删除或重写编译器正在使用的未变图片', async (t) => {
  const { output, write, sync } = await fixture(t);
  const asset = path.join(output, 'public/repository/docs/diagram.svg');
  const before = await stat(asset, { bigint: true });
  await write('docs/intro.md', '# 简介\n\n更新后的内容。\n\n![示意](diagram.svg)');
  await sync();
  const after = await stat(asset, { bigint: true });
  assert.equal(after.ino, before.ino);
  assert.equal(after.mtimeNs, before.mtimeNs);
  assert.match(
    await readFile(path.join(output, '.generated/content/docs/start/index.md'), 'utf8'),
    /更新后的内容/,
  );
});

test('文档引用的无扩展名 LICENSE 可作为原文发布，其他未知类型仍被拒绝', async (t) => {
  const { output, write, sync } = await fixture(t);
  await write('docs/LICENSE', 'Apache License 2.0');
  await write('docs/intro.md', '# 简介\n\n[数据许可](LICENSE)');
  await sync();
  const sources = JSON.parse(
    await readFile(path.join(output, '.generated/source-index.json'), 'utf8'),
  );
  assert.equal(sources['docs/LICENSE'].content, 'Apache License 2.0');
  await write('docs/private', 'not publishable');
  await write('docs/intro.md', '# 简介\n\n[未知文件](private)');
  await assert.rejects(sync, /禁止发布未明确允许的源码类型/);
});

test('原文引用暂时失效时保留最后一次成功生成的正文、图片和索引', async (t) => {
  const { output, write, sync } = await fixture(t);
  const files = [
    '.generated/content/docs/start/index.md',
    '.generated/page-index.json',
    '.generated/source-index.json',
    'public/repository/docs/diagram.svg',
  ];
  const snapshots = await Promise.all(files.map((file) => readFile(path.join(output, file))));
  await write('docs/intro.md', '# 简介\n\n尚未准备好的修改。\n\n![不存在](missing.svg)');
  await assert.rejects(sync, /不可访问的路径/);
  for (let i = 0; i < files.length; i++) {
    assert.deepEqual(await readFile(path.join(output, files[i])), snapshots[i], files[i]);
  }
});

test('成功同步清理过期正文，同时保留可能仍被旧编译模块引用的资源', async (t) => {
  const { output, write, sync } = await fixture(t);
  const stale = path.join(output, '.generated/content/docs/retired.md');
  await writeFile(stale, '# 已移除页面');
  await write('docs/intro.md', '# 简介\n\n已移除图片引用。');
  await sync();
  await assert.rejects(readFile(stale), { code: 'ENOENT' });
  assert.match(
    await readFile(path.join(output, 'public/repository/docs/diagram.svg'), 'utf8'),
    /<svg/,
  );
});
