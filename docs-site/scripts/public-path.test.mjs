import assert from 'node:assert/strict';
import test from 'node:test';

for (const base of ['', '/docs']) {
  test(`图片、搜索、示例与 Markdown 地址使用挂载前缀：${base || '独立站点'}`, async () => {
    const previous = process.env.NEXT_PUBLIC_DOCS_BASE_PATH;
    try {
      process.env.NEXT_PUBLIC_DOCS_BASE_PATH = base;
      const { publicPath } = await import(
        `../src/lib/public-path.ts?base=${encodeURIComponent(base)}`
      );
      for (const path of [
        '/api/search.json',
        '/brand/mark.svg',
        '/repository/docs/architecture/diagram/example.svg',
        '/design-examples/design-examples.html?category=controls',
        '/llms.mdx/docs/development/backend/content.md',
      ]) {
        assert.equal(publicPath(path), `${base}${path}`);
      }
      for (const path of [
        'https://example.com/image.png',
        '//example.com/image.png',
        '#part',
        'file.png',
      ]) {
        assert.equal(publicPath(path), path);
      }
    } finally {
      if (previous === undefined) delete process.env.NEXT_PUBLIC_DOCS_BASE_PATH;
      else process.env.NEXT_PUBLIC_DOCS_BASE_PATH = previous;
    }
  });
}
