import assert from 'node:assert/strict';
import test from 'node:test';

test('subpath assets and fetches stay under the documentation mount', async () => {
  process.env.NEXT_PUBLIC_DOCS_BASE_PATH = '/docs';
  const { publicPath } = await import('../src/lib/public-path.ts');
  assert.equal(publicPath('/api/search'), '/docs/api/search');
  assert.equal(publicPath('/brand/mark.svg'), '/docs/brand/mark.svg');
  assert.equal(
    publicPath('/llms.mdx/docs/start/content.md'),
    '/docs/llms.mdx/docs/start/content.md',
  );
  assert.equal(publicPath('https://example.com/image.png'), 'https://example.com/image.png');
  assert.equal(publicPath('//example.com/image.png'), '//example.com/image.png');
});
