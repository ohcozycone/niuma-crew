import { readdir, stat, readFile } from 'node:fs/promises';
import { resolve, relative, join } from 'node:path';
import { fileURLToPath } from 'node:url';

export async function checkExport(output, basePath = '') {
  const root = resolve(output);
  const prefix = basePath.replace(/\/$/, '');
  let pages = 0;
  let images = 0;
  let frames = 0;
  const assets = new Set();

  async function visit(directory) {
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      const file = join(directory, entry.name);
      if (entry.isDirectory()) {
        await visit(file);
        continue;
      }
      if (!entry.isFile() || !entry.name.endsWith('.html')) continue;
      pages++;
      const html = await readFile(file, 'utf8');
      const page = `${prefix}/${relative(root, file).split('\\').join('/')}`;
      for (const match of html.matchAll(/<(img|iframe)\b[^>]*>/gi)) {
        const tag = match[1].toLowerCase();
        const src = /\bsrc\s*=\s*(?:"([^"]*)"|'([^']*)')/i.exec(match[0]);
        const value = (src?.[1] ?? src?.[2] ?? '').replaceAll('&amp;', '&');
        const context = `${relative(root, file)}: ${tag} src=${JSON.stringify(value)}`;
        if (!value || value.includes('[object Object]')) {
          throw new Error(`无效导出资源地址：${context}`);
        }
        if (tag === 'img') images++;
        else frames++;
        if (/^(?:[a-z][a-z\d+.-]*:|\/\/)/i.test(value)) continue;
        const url = new URL(value, `https://docs.invalid${page}`);
        if (prefix && !url.pathname.startsWith(`${prefix}/`)) {
          throw new Error(`导出资源缺少挂载前缀 ${prefix}：${context}`);
        }
        const assetPath = decodeURIComponent(url.pathname.slice(prefix.length));
        const target = resolve(root, `.${assetPath}`);
        const exists = await stat(target).catch(() => undefined);
        if (!exists?.isFile() || exists.size === 0) {
          throw new Error(`导出资源缺失或为空：${context}`);
        }
        assets.add(url.pathname);
      }
    }
  }

  await visit(root);
  if (pages === 0) throw new Error('没有找到导出页面');
  return { pages, images, frames, assets: [...assets].sort() };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const result = await checkExport('out', process.env.NEXT_PUBLIC_DOCS_BASE_PATH || '');
  console.log(
    `导出资源检查通过：${result.pages} 页、${result.images} 张图片、${result.frames} 个交互示例、${result.assets.length} 个本地资源`,
  );
}
