import test from 'node:test';
import assert from 'node:assert/strict';
import { getDocSection, getSectionTree } from '../src/lib/docs-navigation.ts';

const page = (url) => ({ type: 'page', name: url, url });
const tree = {
  name: '文档',
  children: [
    {
      type: 'folder',
      name: '平台介绍',
      index: page('/docs/start'),
      children: [page('/docs/start/assets'), page('/docs/start/first-conversation')],
    },
    { type: 'folder', name: '使用指南', children: [page('/docs/usage/knowledge')] },
    {
      type: 'folder',
      name: '部署维护',
      children: [page('/docs/deployment/local'), page('/docs/deployment/operations')],
    },
    {
      type: 'folder',
      name: '技术解析',
      children: [page('/docs/development/architecture'), page('/docs/development/contributing')],
    },
  ],
  fallback: { name: '资料', children: [page('/docs/library/docs/reference/runtime')] },
};

test('建设、技术和使用分开，既有操作网址按内容归类', () => {
  for (const [path, expected] of [
    ['/docs/start', ['/docs/start', '/docs/start/assets']],
    [
      '/docs/development/architecture',
      ['/docs/development/architecture', '/docs/development/contributing'],
    ],
    [
      '/docs/deployment/local/',
      [
        '/docs/start/first-conversation',
        '/docs/usage/knowledge',
        '/docs/deployment/local',
        '/docs/deployment/operations',
      ],
    ],
  ]) {
    const selected = getSectionTree(tree, path);
    assert.deepEqual(
      selected.children.map((entry) => entry.url),
      expected,
    );
    assert.ok(selected.children.every((entry) => entry.type === 'page'));
  }
  assert.equal(getDocSection('/docs/start/features/').id, 'usage');
  assert.equal(tree.children.length, 4);
});

test('技术正文进入契约后保持技术分类，操作与部署另有归属', () => {
  for (const file of [
    'docs/reference/runtime.md',
    'docs/reference/knowledge.md',
    'docs/design/README.md',
    'backend/app/runtime/execution/README.md',
    'docs/guides/local-development.md',
  ]) {
    assert.equal(getDocSection(`/docs/library/${file}`, file).id, 'development');
  }
  assert.equal(getDocSection('/docs/library/assets', 'docs/product/组织资产.md').id, 'platform');
  for (const file of ['docs/product/workflows.md', 'docs/guides/backend-operations.md']) {
    assert.equal(getDocSection(`/docs/library/${file}`, file).id, 'usage');
  }
  const selected = getSectionTree(
    tree,
    '/docs/library/docs/reference/runtime/',
    'docs/reference/runtime.md',
  );
  assert.equal(selected.name, '技术解析');
  assert.equal(selected.children.at(-1).url, '/docs/library/docs/reference/runtime');
  assert.equal(selected.children.length, 3);
});

test('同级主题按阅读顺序分组，进一步查阅不重复主文章', () => {
  const selected = getSectionTree(tree, '/docs/start', undefined, {
    '/docs/start': '平台介绍',
    '/docs/start/assets': '平台介绍',
  });
  assert.deepEqual(
    selected.children.map((entry) => (entry.type === 'separator' ? entry.name : entry.url)),
    ['/docs/start', '/docs/start/assets'],
  );
  const further = getSectionTree(
    tree,
    '/docs/library/docs/reference/runtime',
    'docs/reference/runtime.md',
    {
      '/docs/development/architecture': '架构设计',
      '/docs/development/contributing': '开发参考',
    },
  );
  assert.equal(further.children.at(-2).name, '更多资料');
  assert.equal(further.children.at(-1).url, '/docs/library/docs/reference/runtime');
});
