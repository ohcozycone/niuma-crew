import { watch } from 'node:fs';
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import path from 'node:path';
import { repoRoot, siteRoot, syncContent } from './sync-content.mjs';

await syncContent();
const require = createRequire(import.meta.url);
const child = spawn(
  process.execPath,
  [
    require.resolve('next/dist/bin/next'),
    'dev',
    '--webpack',
    '--hostname',
    '127.0.0.1',
    '--port',
    '3001',
  ],
  { cwd: siteRoot, stdio: 'inherit' },
);
let timer;
let pending = Promise.resolve();
const watchers = ['docs', 'backend/app', 'frontend/src', 'frontend/public/brand'].map((dir) =>
  watch(path.join(repoRoot, dir), { recursive: true }, (_event, filename) => {
    if (
      !filename ||
      (!['.md', '.mdx', '.svg', '.png', '.jpg', '.jpeg', '.webp', '.gif', '.pdf'].includes(
        path.extname(filename),
      ) &&
        !filename.endsWith('theme.css') &&
        dir !== 'frontend/public/brand')
    )
      return;
    clearTimeout(timer);
    timer = setTimeout(() => {
      pending = pending.then(syncContent).catch((error) => {
        console.error('文档同步失败：', error.message);
      });
    }, 350);
  }),
);
watchers.push(
  watch(repoRoot, (_event, filename) => {
    if (filename !== 'README.md') return;
    clearTimeout(timer);
    timer = setTimeout(() => {
      pending = pending.then(syncContent).catch((error) => {
        console.error('文档同步失败：', error.message);
      });
    }, 350);
  }),
);

function close(signal = 'SIGTERM') {
  clearTimeout(timer);
  for (const watcher of watchers) watcher.close();
  child.kill(signal);
}
process.on('SIGINT', () => close('SIGINT'));
process.on('SIGTERM', () => close());
child.on('exit', (code) => {
  close();
  process.exitCode = code ?? 1;
});
