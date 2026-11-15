import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { checkExport } from './check-export.mjs';

for (const base of ['', '/docs']) {
  test(`导出图片和交互示例必须对应真实资源：${base || '独立站点'}`, async (t) => {
    const root = await mkdtemp(join(tmpdir(), 'docs-export-'));
    t.after(() => rm(root, { recursive: true, force: true }));
    await mkdir(join(root, 'article'));
    await mkdir(join(root, '_next/static/media'), { recursive: true });
    await writeFile(join(root, '_next/static/media/architecture.svg'), '<svg/>');
    await writeFile(join(root, 'article/local.svg'), '<svg/>');
    await writeFile(join(root, 'example.html'), '<main>示例</main>');
    const page = join(root, 'article/index.html');
    await writeFile(
      page,
      `<img src="${base}/_next/static/media/architecture.svg"><img src="local.svg"><iframe src="${base}/example.html?theme=dark&amp;size=small"></iframe>`,
    );
    const result = await checkExport(root, base);
    assert.equal(result.images, 2);
    assert.equal(result.frames, 1);
    assert.equal(result.assets.length, 3);

    await writeFile(page, '<img src="[object Object]">');
    await assert.rejects(checkExport(root, base), /无效导出资源地址/);
    await writeFile(page, `<img src="${base}/missing.svg">`);
    await assert.rejects(checkExport(root, base), /导出资源缺失/);
    if (base) {
      await writeFile(page, '<img src="/_next/static/media/architecture.svg">');
      await assert.rejects(checkExport(root, base), /缺少挂载前缀/);
    }
  });
}
