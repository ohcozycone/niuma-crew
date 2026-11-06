import test from 'node:test';
import assert from 'node:assert/strict';
import { getDocSection, getSectionTree } from '../src/lib/docs-navigation.ts';

const page = (url) => ({ type: 'page', name: url, url });
const tree = {
  name: '文档',
  children: [
    {
      type: 'folder',
      name: '快速开始',
      index: page('/docs/start'),
      children: [page('/docs/start/first-conversation')],
    },
    { type: 'folder', name: '使用指南', children: [page('/docs/usage/knowledge')] },
    {
      type: 'folder',
      name: '部署与维护',
      children: [page('/docs/deployment/local'), page('/docs/deployment/operations')],
    },
    {
      type: 'folder',
      name: '开发指南',
      children: [page('/docs/development/architecture'), page('/docs/development/contributing')],
    },
  ],
  fallback: { name: '资料', children: [page('/docs/library/docs/architecture/frontend')] },
};

test('切换大分类后只保留其文章，分类标题不再次成为可展开目录', () => {
  for (const [path, expected] of [
    ['/docs/deployment/local/', ['/docs/deployment/local', '/docs/deployment/operations']],
    [
      '/docs/development/architecture',
      ['/docs/development/architecture', '/docs/development/contributing'],
    ],
    [
      '/docs/usage/knowledge',
      ['/docs/start', '/docs/start/first-conversation', '/docs/usage/knowledge'],
    ],
  ]) {
    const selected = getSectionTree(tree, path);
    assert.deepEqual(
      selected.children.map((entry) => entry.url),
      expected,
    );
    assert.ok(selected.children.every((entry) => entry.type === 'page'));
  }
  assert.equal(tree.children.length, 4);
});

test('直接进入进一步阅读时识别来源分类，并保留当前文章入口', () => {
  assert.equal(
    getDocSection('/docs/library/docs/reference/knowledge', 'docs/reference/knowledge.md').id,
    'usage',
  );
  assert.equal(
    getDocSection(
      '/docs/library/docs/guides/backend-operations',
      'docs/guides/backend-operations.md',
    ).id,
    'deployment',
  );
  const selected = getSectionTree(
    tree,
    '/docs/library/docs/architecture/frontend/',
    'docs/architecture/frontend.md',
  );
  assert.equal(selected.name, '开发指南');
  assert.equal(selected.children.at(-1).url, '/docs/library/docs/architecture/frontend');
  assert.equal(selected.children.length, 3);
});
